"""Task C Part 3 addendum: rough qualifying-match estimate for the S-H1 tournaments at OPEN venues
(Copa America 2024, Club World Cup 2025, Gold Cup 2025, Leagues Cup 2025; Euro 2024 venues are all
covered/retractable so contribute 0). Matches per venue are APPROXIMATE from memory (UNVERIFIED; the repo has no
fixture table for these). Hot-day fractions come from ERA5 at 16:00 and 19:00 local over the tournament window.
Run from sharp-markets with:  uv run python <this file>
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "sharp-markets" / "src"))
from markets.weather.heat import heat_index_f      # noqa: E402
from markets.weather.venues import venues           # noqa: E402

CACHE = REPO / "strategy-research" / "data" / "heat"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
S = requests.Session()
S.headers["User-Agent"] = "value-finder-taskC/0.1 (research; cache-first)"
V = venues()

# (tournament, window, {venue_id: approx matches at that venue}, kickoff proxy hour weights)
T = [
    ("Copa America 2024", date(2024, 6, 20), date(2024, 7, 14),
     {"metlife_stadium": 3, "hard_rock_stadium": 4, "levi_s_stadium": 3, "geha_field_at_arrowhead_stadium": 2,
      "children_s_mercy_park": 2, "q2_stadium": 2, "inter_co_stadium": 2, "bank_of_america_stadium": 2},
     {"t19": 1.0}),
    ("Club World Cup 2025", date(2025, 6, 14), date(2025, 7, 13),
     {"metlife_stadium": 9, "hard_rock_stadium": 7, "lincoln_financial_field": 8, "rose_bowl": 6,
      "camping_world_stadium": 6, "inter_co_stadium": 2, "audi_field": 6, "geodis_park": 3, "tql_stadium": 3,
      "bank_of_america_stadium": 5, "lumen_field": 6},
     {"t16": 0.5, "t19": 0.5}),
    ("Gold Cup 2025", date(2025, 6, 14), date(2025, 7, 6),
     {"dignity_health_sports_park": 3, "levi_s_stadium": 3, "paypal_park": 3, "snapdragon_stadium": 3, "q2_stadium": 2,
      "shell_energy_stadium": 3, "energizer_park": 2},
     {"t19": 1.0}),
    ("Leagues Cup 2025", date(2025, 7, 29), date(2025, 8, 31),
     {v: 60 / 28 for v in ["q2_stadium", "bank_of_america_stadium", "soldier_field", "tql_stadium", "dick_s_sporting_goods_park",
                           "scottsmiracle_gro_field", "audi_field", "toyota_stadium", "shell_energy_stadium", "chase_stadium",
                           "dignity_health_sports_park", "bmo_stadium", "allianz_field", "stade_saputo", "geodis_park",
                           "gillette_stadium", "yankee_stadium", "red_bull_arena", "inter_co_stadium", "subaru_park",
                           "providence_park", "america_first_field", "paypal_park", "lumen_field", "children_s_mercy_park",
                           "energizer_park", "bmo_field", "snapdragon_stadium"]},
     {"t19": 1.0}),
]


def fetch(vid: str, lo: date, hi: date) -> dict:
    v = V[vid]
    p = {"latitude": f"{v.lat:.4f}", "longitude": f"{v.lon:.4f}", "start_date": lo.isoformat(), "end_date": hi.isoformat(),
         "hourly": "temperature_2m,relative_humidity_2m", "timezone": "auto", "temperature_unit": "fahrenheit"}
    f = CACHE / f"era5_tourn_{vid}_{lo}_{hi}.json"
    if f.exists():
        return json.loads(f.read_text())
    for attempt in range(6):
        r = S.get(ARCHIVE, params=p, timeout=120)
        if r.status_code == 200:
            f.write_text(r.text)
            time.sleep(0.8)
            return r.json()
        time.sleep(10 * (attempt + 1))
    raise SystemExit(f"gave up {vid}")


def fractions(body: dict) -> dict:
    h = body["hourly"]
    n = {"t16": 0, "t19": 0}
    hot = {"t16": 0, "t19": 0}
    for t, temp, rh in zip(h["time"], h["temperature_2m"], h["relative_humidity_2m"]):
        for k, hh in (("t16", "T16:00"), ("t19", "T19:00")):
            if t.endswith(hh) and temp is not None and rh is not None:
                n[k] += 1
                if heat_index_f(temp, rh) >= 90:
                    hot[k] += 1
    return {k: (hot[k] / n[k] if n[k] else 0.0) for k in n}


grand = 0.0
for name, lo, hi, per_venue, weights in T:
    tot = 0.0
    print(f"\n{name} ({lo}..{hi}): open venues only; matches per venue approximate")
    for vid, m in per_venue.items():
        if V[vid].roof != "open":
            print(f"  {V[vid].name}: roof={V[vid].roof}, skipped")
            continue
        fr = fractions(fetch(vid, lo, hi))
        p = sum(w * fr[k] for k, w in weights.items())
        tot += m * p
        print(f"  {V[vid].name:34s} matches~{m:4.1f}  frac(HI16>=90)={fr['t16']:.2f} frac(HI19>=90)={fr['t19']:.2f}  E[qualifying]={m*p:.1f}")
    print(f"  => {name}: ~{tot:.1f} expected qualifying matches at open venues")
    grand += tot
print(f"\nTournaments total (2024-25, open venues, rough): ~{grand:.0f}")
