"""Task C Part 2: count MLB regular-season games at OPEN-roof parks with first-pitch-hour temperature
>= 85/90/95 F, 2024 and 2025, from the MLB Stats API schedule (free, no key) and Open-Meteo ERA5 archive.
Counts only. No scores, no odds. Every response is cached under strategy-research/data/heat/.
Run from sharp-markets with:  uv run python <this file>
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "sharp-markets" / "src"))
from markets.weather.heat import heat_index_f          # noqa: E402  (read-only import from the repo)
from markets.weather.venues import venue_by_name, venues  # noqa: E402

CACHE = REPO / "strategy-research" / "data" / "heat"
CACHE.mkdir(parents=True, exist_ok=True)
STATSAPI = "https://statsapi.mlb.com/api/v1/schedule"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
SEASONS = [2024, 2025]
HOT_CITY_PARKS = {"chase_field": "Arizona", "daikin_park": "Houston", "globe_life_field": "Texas",
                  "loandepot_park": "Miami", "american_family_field": "Milwaukee", "rogers_centre": "Toronto",
                  "t_mobile_park": "Seattle"}
S = requests.Session()
S.headers["User-Agent"] = "value-finder-taskC/0.1 (research; cache-first)"


def get_json(url: str, params: dict, cache_file: Path) -> dict:
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    for attempt in range(5):
        r = S.get(url, params=params, timeout=120)
        if r.status_code == 200:
            cache_file.write_text(r.text)
            return r.json()
        print(f"  HTTP {r.status_code} {url} {params.get('startDate', params.get('latitude'))}: {r.text[:200]}", file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"gave up on {url} {params}")


def schedule(season: int) -> list[dict]:
    body = get_json(STATSAPI, {"sportId": 1, "season": season, "gameType": "R", "hydrate": "venue(location)"},
                    CACHE / f"statsapi_schedule_{season}_R.json")
    games = []
    for d in body.get("dates", []):
        for g in d.get("games", []):
            v = g.get("venue") or {}
            loc = ((v.get("location") or {}).get("defaultCoordinates") or {})
            games.append({"gamePk": g["gamePk"], "gameDate": g["gameDate"], "gameType": g.get("gameType"),
                          "status": (g.get("status") or {}).get("detailedState"),
                          "coded": (g.get("status") or {}).get("codedGameState"),
                          "venue_name": v.get("name"), "venue_mlb_id": v.get("id"),
                          "lat": loc.get("latitude"), "lon": loc.get("longitude"),
                          "home": g["teams"]["home"]["team"]["name"], "away": g["teams"]["away"]["team"]["name"],
                          "dh": g.get("doubleHeader"), "series": g.get("seriesDescription")})
    return games


def kick_hour(iso: str) -> datetime:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    return (t + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)


def era5(vid: str, lat: float, lon: float, start: str, end: str) -> dict:
    p = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "start_date": start, "end_date": end,
         "hourly": "temperature_2m,relative_humidity_2m", "timezone": "UTC", "temperature_unit": "fahrenheit"}
    body = get_json(ARCHIVE, p, CACHE / f"era5_mlb_{vid}_{start}_{end}.json")
    time.sleep(0.7)   # stay far below Open-Meteo's free-tier rate
    return body


def main() -> None:
    V = venues()
    out_rows = []
    summary = {}
    for season in SEASONS:
        games = schedule(season)
        print(f"\n=== {season} regular season: {len(games):,} schedule rows ===")
        print("status counts:", dict(Counter(g["status"] for g in games)))
        # Count only games that were actually played (Final / Completed Early), so postponed duplicates drop out.
        played = [g for g in games if g["coded"] == "F"]
        print(f"played (codedGameState=F): {len(played):,}")
        unmatched = Counter()
        for g in played:
            g["venue_id"] = venue_by_name(g["venue_name"])
            if g["venue_id"] is None:
                unmatched[g["venue_name"]] += 1
        print("venue names not in config/venues/mlb_parks.csv:", dict(unmatched))
        by_roof = Counter((V[g["venue_id"]].roof if g["venue_id"] else "unknown") for g in played)
        print("games by roof:", dict(by_roof))
        # One ERA5 call per park per season (open parks + the 7 hot-city roofed parks for the exclusion count)
        by_park = defaultdict(list)
        for g in played:
            if g["venue_id"]:
                by_park[g["venue_id"]].append(g)
        per_park = {}
        for vid, gs in sorted(by_park.items()):
            v = V[vid]
            if v.roof != "open" and vid not in HOT_CITY_PARKS:
                continue
            days = sorted(kick_hour(g["gameDate"]).date() for g in gs)
            start, end = days[0].isoformat(), (days[-1] + timedelta(days=1)).isoformat()
            body = era5(vid, v.lat, v.lon, start, end)
            h = body["hourly"]
            idx = {t: i for i, t in enumerate(h["time"])}
            c = Counter()
            for g in gs:
                k = kick_hour(g["gameDate"]).strftime("%Y-%m-%dT%H:00")
                i = idx.get(k)
                t = h["temperature_2m"][i] if i is not None else None
                rh = h["relative_humidity_2m"][i] if i is not None else None
                hi = heat_index_f(t, rh) if t is not None else None
                c["n"] += 1
                if t is None:
                    c["missing"] += 1
                    continue
                for thr in (85, 90, 95):
                    if t >= thr:
                        c[f"t>={thr}"] += 1
                if hi is not None and hi >= 90:
                    c["hi>=90"] += 1
                out_rows.append({"season": season, "gamePk": g["gamePk"], "venue_id": vid, "roof": v.roof,
                                 "kick_hour_utc": k, "temp_f": t, "rh": rh, "heat_index_f": hi})
            per_park[vid] = {"name": v.name, "roof": v.roof, **c}
        summary[season] = per_park
        print(f"\n{'park':32s} {'roof':11s} {'n':>4s} {'>=85':>5s} {'>=90':>5s} {'>=95':>5s} {'HI>=90':>6s} {'miss':>4s}")
        tot = Counter()
        for vid, c in sorted(per_park.items(), key=lambda kv: -kv[1].get("t>=90", 0)):
            print(f"{c['name'][:32]:32s} {c['roof']:11s} {c['n']:4d} {c.get('t>=85', 0):5d} {c.get('t>=90', 0):5d} "
                  f"{c.get('t>=95', 0):5d} {c.get('hi>=90', 0):6d} {c.get('missing', 0):4d}")
            if c["roof"] == "open":
                for k in ("n", "t>=85", "t>=90", "t>=95", "hi>=90", "missing"):
                    tot[k] += c.get(k, 0)
        print(f"{'TOTAL open parks':32s} {'':11s} {tot['n']:4d} {tot['t>=85']:5d} {tot['t>=90']:5d} {tot['t>=95']:5d} "
              f"{tot['hi>=90']:6d} {tot['missing']:4d}")
        roofed = Counter()
        for vid, c in per_park.items():
            if vid in HOT_CITY_PARKS:
                for k in ("n", "t>=85", "t>=90", "t>=95"):
                    roofed[k] += c.get(k, 0)
        print(f"{'7 hot-city roofed parks (excluded)':32s} {'':11s} {roofed['n']:4d} {roofed['t>=85']:5d} {roofed['t>=90']:5d} {roofed['t>=95']:5d}")
    (CACHE / "mlb_game_temps.json").write_text(json.dumps(out_rows))
    (CACHE / "mlb_summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
