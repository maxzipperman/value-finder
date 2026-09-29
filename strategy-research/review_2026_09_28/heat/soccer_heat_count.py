"""Task C Part 3: for every OPEN venue used by MLS, Liga MX, Brasileirao, J1 and K League 1 in 2024 and 2025,
count days in the odds5m.yaml season window where the NWS heat index at 19:00 LOCAL >= 90 F (also 85/95, also
at 16:00 local and the daily max), from Open-Meteo's ERA5 archive (free). Then turn hot-day fractions into an
expected number of qualifying home MATCHES per league-season. Counts only; no odds, no scores.
Run from sharp-markets with:  uv run python <this file>
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import requests
import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "sharp-markets" / "src"))
from markets.weather.heat import heat_index_f                 # noqa: E402
from markets.weather.venues import home_venue, venues          # noqa: E402

CACHE = REPO / "strategy-research" / "data" / "heat"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
CFG = yaml.safe_load((REPO / "sharp-markets" / "config" / "odds5m.yaml").read_text())
S = requests.Session()
S.headers["User-Agent"] = "value-finder-taskC/0.1 (research; cache-first)"

# Top-flight membership by season, spelled as in config/venues/soccer_homes.csv. From league records as I know
# them (UNVERIFIED against a fixture source; the repo forbids ESPN here). Home matches per club per season:
# MLS 17 (34-game season), Liga MX 17 (two 17-round short tournaments per calendar year, half at home),
# Brasileirao 19, J1 19 (20 clubs from 2024), K League 1 19 (33 rounds + 5 split-round matches, ~half at home).
MLS_2024 = ["Atlanta United FC", "Austin FC", "Charlotte FC", "Chicago Fire", "FC Cincinnati", "Colorado Rapids",
            "Columbus Crew", "D.C. United", "FC Dallas", "Houston Dynamo", "Inter Miami CF", "LA Galaxy",
            "Los Angeles FC", "Minnesota United FC", "CF Montréal", "Nashville SC", "New England Revolution",
            "New York City FC", "New York Red Bulls", "Orlando City SC", "Philadelphia Union", "Portland Timbers",
            "Real Salt Lake", "San Jose Earthquakes", "Seattle Sounders FC", "Sporting Kansas City",
            "St. Louis City SC", "Toronto FC", "Vancouver Whitecaps FC"]
LIGAMX = ["Club América", "Cruz Azul", "Pumas UNAM", "Guadalajara", "Atlas", "Monterrey", "Tigres UANL", "Toluca",
          "Santos Laguna", "Pachuca", "León", "Necaxa", "Club Tijuana", "Puebla", "Querétaro", "Atlético San Luis",
          "FC Juárez", "Mazatlán FC"]
BRA_2024 = ["Atlético Mineiro", "Athletico Paranaense", "Atlético Goianiense", "Bahia", "Botafogo", "Corinthians",
            "Criciúma", "Cruzeiro", "Cuiabá", "Flamengo", "Fluminense", "Fortaleza", "Grêmio", "Internacional",
            "Juventude", "Palmeiras", "Red Bull Bragantino", "São Paulo", "Vasco da Gama", "Vitória"]
BRA_2025 = ["Atlético Mineiro", "Bahia", "Botafogo", "Ceará", "Corinthians", "Cruzeiro", "Flamengo", "Fluminense",
            "Fortaleza", "Grêmio", "Internacional", "Juventude", "Mirassol", "Palmeiras", "Red Bull Bragantino",
            "Santos", "São Paulo", "Sport Recife", "Vasco da Gama", "Vitória"]
J1_2024 = ["Kashima Antlers", "Kashiwa Reysol", "Urawa Red Diamonds", "FC Tokyo", "Tokyo Verdy", "FC Machida Zelvia",
           "Kawasaki Frontale", "Yokohama F. Marinos", "Shonan Bellmare", "Albirex Niigata", "Jubilo Iwata",
           "Nagoya Grampus", "Kyoto Sanga", "Gamba Osaka", "Cerezo Osaka", "Vissel Kobe", "Sanfrecce Hiroshima",
           "Avispa Fukuoka", "Sagan Tosu", "Hokkaido Consadole Sapporo"]
J1_2025 = ["Kashima Antlers", "Kashiwa Reysol", "Urawa Red Diamonds", "FC Tokyo", "Tokyo Verdy", "FC Machida Zelvia",
           "Kawasaki Frontale", "Yokohama F. Marinos", "Yokohama FC", "Shonan Bellmare", "Albirex Niigata",
           "Shimizu S-Pulse", "Nagoya Grampus", "Kyoto Sanga", "Gamba Osaka", "Cerezo Osaka", "Vissel Kobe",
           "Sanfrecce Hiroshima", "Avispa Fukuoka", "Fagiano Okayama"]
K1_2024 = ["Ulsan HD", "Pohang Steelers", "Gwangju FC", "Jeonbuk Hyundai Motors", "Incheon United", "Daegu FC",
           "FC Seoul", "Daejeon Hana Citizen", "Suwon FC", "Gangwon FC", "Jeju United", "Gimcheon Sangmu"]
K1_2025 = ["Ulsan HD", "Pohang Steelers", "Gwangju FC", "Jeonbuk Hyundai Motors", "Daegu FC", "FC Seoul",
           "Daejeon Hana Citizen", "Suwon FC", "Gangwon FC", "Jeju United", "Gimcheon Sangmu", "FC Anyang"]
LEAGUES = {
    "soccer_usa_mls": {"2024": (MLS_2024, 17), "2025": (MLS_2024 + ["San Diego FC"], 17)},
    "soccer_mexico_ligamx": {"2024": (LIGAMX, 17), "2025": (LIGAMX, 17)},
    "soccer_brazil_campeonato": {"2024": (BRA_2024, 19), "2025": (BRA_2025, 19)},
    "soccer_japan_j_league": {"2024": (J1_2024, 19), "2025": (J1_2025, 19)},
    "soccer_korea_kleague1": {"2024": (K1_2024, 19), "2025": (K1_2025, 19)},
}
THRESHOLDS = (85, 90, 95)


def get_json(params: dict, cache_file: Path) -> dict:
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    for attempt in range(6):
        r = S.get(ARCHIVE, params=params, timeout=180)
        if r.status_code == 200:
            cache_file.write_text(r.text)
            time.sleep(0.8)
            return r.json()
        print(f"  HTTP {r.status_code} {params['latitude']},{params['longitude']}: {r.text[:200]}", file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    raise SystemExit(f"gave up on {params}")


def window(sport: str, label: str) -> tuple[date, date]:
    w = next(w for w in CFG["sports"][sport]["windows"] if str(w["label"]) == label)
    return w["from"], w["to"]


def days_between(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def hot_days(vid: str, lat: float, lon: float, lo: date, hi: date) -> dict[date, dict]:
    """Per local day: heat index at 16:00 and 19:00 local, and the daily max heat index."""
    today = date.today()
    hi = min(hi, today - timedelta(days=6))                    # ERA5 lags about 5 days
    p = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "start_date": lo.isoformat(), "end_date": hi.isoformat(),
         "hourly": "temperature_2m,relative_humidity_2m", "timezone": "auto", "temperature_unit": "fahrenheit"}
    body = get_json(p, CACHE / f"era5_soccer_{vid}_{lo}_{hi}.json")
    h = body["hourly"]
    out: dict[date, dict] = {}
    for t, temp, rh in zip(h["time"], h["temperature_2m"], h["relative_humidity_2m"]):
        if temp is None or rh is None:
            continue
        d = date.fromisoformat(t[:10])
        hix = heat_index_f(temp, rh)
        row = out.setdefault(d, {"max": -999.0, "t16": None, "t19": None, "temp19": None})
        row["max"] = max(row["max"], hix)
        if t.endswith("T16:00"):
            row["t16"] = hix
        if t.endswith("T19:00"):
            row["t19"], row["temp19"] = hix, temp
    return out


def main() -> None:
    V = venues()
    weather_cache: dict[tuple, dict] = {}
    venue_rows, team_rows = [], []
    league_tot: dict[tuple, Counter] = defaultdict(Counter)
    for sport, seasons in LEAGUES.items():
        for label, (teams, home_matches) in seasons.items():
            lo, hi = window(sport, label)
            ndays = (hi - lo).days + 1
            for team in teams:
                by_venue: Counter = Counter()          # days of the window at each venue
                hot: dict[str, Counter] = defaultdict(Counter)
                unresolved = 0
                for d in days_between(lo, hi):
                    vid, how = home_venue(sport, team, d)
                    if vid is None:
                        unresolved += 1
                        continue
                    by_venue[vid] += 1
                    v = V[vid]
                    if v.roof != "open":
                        continue
                    key = (vid, lo, hi)
                    if key not in weather_cache:
                        weather_cache[key] = hot_days(vid, v.lat, v.lon, lo, hi)
                    w = weather_cache[key].get(d)
                    if w is None:
                        hot[vid]["no_weather"] += 1
                        continue
                    hot[vid]["days_with_weather"] += 1
                    for thr in THRESHOLDS:
                        if w["t19"] is not None and w["t19"] >= thr:
                            hot[vid][f"hi19>={thr}"] += 1
                        if w["t16"] is not None and w["t16"] >= thr:
                            hot[vid][f"hi16>={thr}"] += 1
                        if w["max"] >= thr:
                            hot[vid][f"himax>={thr}"] += 1
                    if w["temp19"] is not None and w["temp19"] >= 90:
                        hot[vid]["temp19>=90"] += 1
                roofs = {vid: V[vid].roof for vid in by_venue}
                open_days = sum(n for vid, n in by_venue.items() if roofs[vid] == "open")
                c = Counter()
                for vid, cc in hot.items():
                    c.update(cc)
                frac19 = c["hi19>=90"] / open_days if open_days else 0.0
                exp_matches_19 = home_matches * (open_days / ndays) * frac19    # uniform-through-window assumption
                team_rows.append({"sport": sport, "season": label, "team": team, "venues": dict(by_venue),
                                  "roofs": roofs, "window_days": ndays, "open_days": open_days,
                                  "unresolved_days": unresolved, "home_matches": home_matches,
                                  **{k: c[k] for k in sorted(c)},
                                  "exp_matches_hi19_90": round(exp_matches_19, 2),
                                  "exp_matches_hi19_85": round(home_matches * (open_days / ndays) * (c["hi19>=85"] / open_days if open_days else 0), 2),
                                  "exp_matches_himax_90": round(home_matches * (open_days / ndays) * (c["himax>=90"] / open_days if open_days else 0), 2),
                                  "exp_matches_hi16_90": round(home_matches * (open_days / ndays) * (c["hi16>=90"] / open_days if open_days else 0), 2)})
                lt = league_tot[(sport, label)]
                lt["teams"] += 1
                lt["home_matches"] += home_matches
                lt["open_home_matches"] += home_matches * open_days / ndays
                for k in ("exp_matches_hi19_90", "exp_matches_hi19_85", "exp_matches_himax_90", "exp_matches_hi16_90"):
                    lt[k] += team_rows[-1][k]
                lt["unresolved_team_days"] += unresolved
            # venue-level table for the season (each venue once)
            for (vid, wlo, whi), w in weather_cache.items():
                if (wlo, whi) != (lo, hi):
                    continue
                c = Counter()
                for d, row in w.items():
                    if not (lo <= d <= hi):
                        continue
                    c["days"] += 1
                    for thr in THRESHOLDS:
                        if row["t19"] is not None and row["t19"] >= thr:
                            c[f"hi19>={thr}"] += 1
                        if row["max"] >= thr:
                            c[f"himax>={thr}"] += 1
                    if row["t16"] is not None and row["t16"] >= 90:
                        c["hi16>=90"] += 1
                venue_rows.append({"sport": sport, "season": label, "venue_id": vid, "name": V[vid].name,
                                   "city": V[vid].city, "window": f"{lo}..{hi}", **dict(c),
                                   "one_home_match_per_week_matches_hi19_90": round(c["hi19>=90"] / 7, 1)})
    (CACHE / "soccer_team_rows.json").write_text(json.dumps(team_rows, indent=1, ensure_ascii=False, default=str))
    (CACHE / "soccer_venue_rows.json").write_text(json.dumps(venue_rows, indent=1, ensure_ascii=False, default=str))
    (CACHE / "soccer_league_totals.json").write_text(json.dumps({f"{k[0]}|{k[1]}": dict(v) for k, v in league_tot.items()},
                                                                indent=1))
    print("\n=== venue-level hot days (window days; heat index at 19:00 local >= 85/90/95; daily max >= 90; 16:00 >= 90) ===")
    print(f"{'league':26s} {'season':6s} {'venue':38s} {'days':>4s} {'19>=85':>6s} {'19>=90':>6s} {'19>=95':>6s} {'max>=90':>7s} {'16>=90':>6s}")
    for r in sorted(venue_rows, key=lambda r: (r["sport"], r["season"], -r.get("hi19>=90", 0))):
        print(f"{r['sport']:26s} {r['season']:6s} {r['name'][:38]:38s} {r.get('days', 0):4d} {r.get('hi19>=85', 0):6d} "
              f"{r.get('hi19>=90', 0):6d} {r.get('hi19>=95', 0):6d} {r.get('himax>=90', 0):7d} {r.get('hi16>=90', 0):6d}")
    print("\n=== league-season totals: expected qualifying HOME matches (home matches x share of window days at an open venue x hot-day fraction) ===")
    print(f"{'league':26s} {'season':6s} {'teams':>5s} {'home_m':>6s} {'open_m':>7s} {'E[HI19>=90]':>11s} {'E[HI19>=85]':>11s} {'E[HImax>=90]':>12s} {'E[HI16>=90]':>11s} {'unres_days':>10s}")
    g = Counter()
    for (sport, label), c in sorted(league_tot.items()):
        print(f"{sport:26s} {label:6s} {c['teams']:5d} {c['home_matches']:6d} {c['open_home_matches']:7.1f} "
              f"{c['exp_matches_hi19_90']:11.1f} {c['exp_matches_hi19_85']:11.1f} {c['exp_matches_himax_90']:12.1f} "
              f"{c['exp_matches_hi16_90']:11.1f} {c['unresolved_team_days']:10d}")
        for k in ("home_matches", "open_home_matches", "exp_matches_hi19_90", "exp_matches_hi19_85", "exp_matches_himax_90", "exp_matches_hi16_90"):
            g[k] += c[k]
    print(f"{'TOTAL 2024+2025':33s} {'':5s} {g['home_matches']:6.0f} {g['open_home_matches']:7.1f} {g['exp_matches_hi19_90']:11.1f} "
          f"{g['exp_matches_hi19_85']:11.1f} {g['exp_matches_himax_90']:12.1f} {g['exp_matches_hi16_90']:11.1f}")
    print(f"\nOpen-Meteo calls (unique venue x window): {len(weather_cache)}")


if __name__ == "__main__":
    main()
