"""Opening + closing lines from the Sportsbook Reviews Online archive
(2007-08 through 2021-22 seasons; the archive stops after 2021).

nflverse only carries closing lines. Opening lines let us ask whether weather
gets priced in late (line moves between open and close), which is where a
bettor with an early read on the forecast would find value.
"""
from __future__ import annotations

import re
import time
from io import StringIO

import numpy as np
import pandas as pd

from .config import RAW
from .fetch import session

URL = "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nfl-odds-{a}-{b:02d}/"
FIRST, LAST = 2007, 2021

TEAMS = {
    "Arizona": "ARI", "Atlanta": "ATL", "Baltimore": "BAL", "Buffalo": "BUF", "Carolina": "CAR",
    "Chicago": "CHI", "Cincinnati": "CIN", "Cleveland": "CLE", "Dallas": "DAL", "Denver": "DEN",
    "Detroit": "DET", "GreenBay": "GB", "Houston": "HOU", "Indianapolis": "IND", "Jacksonville": "JAX",
    "KansasCity": "KC", "KCChiefs": "KC", "LVRaiders": "LV", "LasVegas": "LV", "Oakland": "OAK",
    "LAChargers": "LAC", "SanDiego": "SD", "LARams": "LA", "LosAngeles": "LA", "St.Louis": "STL",
    "StLouis": "STL", "Miami": "MIA", "Minnesota": "MIN", "NewEngland": "NE", "NewOrleans": "NO",
    "NYGiants": "NYG", "NYJets": "NYJ", "Philadelphia": "PHI", "Pittsburgh": "PIT",
    "SanFrancisco": "SF", "Seattle": "SEA", "TampaBay": "TB", "Tampa": "TB", "Tennessee": "TEN",
    "Washington": "WAS", "Washingtom": "WAS", "HoustonTexans": "HOU", "LAClippers": "LAC",
    "BuffaloBills": "BUF", "Kansas": "KC",
}


def _num(x):
    s = str(x).strip().lower()
    if s in ("pk", "pick", "p"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return np.nan


def fetch_season(season, force=False):
    dest = RAW / "odds" / f"sbr_{season}.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or force:
        r = session.get(URL.format(a=season, b=(season + 1) % 100), timeout=60,
                        headers={"User-Agent": "Mozilla/5.0 (research; low volume)"})
        r.raise_for_status()
        dest.write_text(r.text)
        time.sleep(3)
    return dest


def parse_season(season):
    html = fetch_season(season).read_text()
    t = pd.read_html(StringIO(html))[0]
    t.columns = t.iloc[0]
    t = t.iloc[1:].reset_index(drop=True)
    rows = []
    for i in range(0, len(t) - 1, 2):
        v, h = t.iloc[i], t.iloc[i + 1]
        if v.VH not in ("V", "N") or h.VH not in ("H", "N"):
            continue
        md = int(v.Date)
        month, day = md // 100, md % 100
        year = season if month >= 8 else season + 1
        rec = dict(date=pd.Timestamp(year, month, day), away=TEAMS.get(v.Team, v.Team),
                   home=TEAMS.get(h.Team, h.Team), neutral=v.VH == "N")
        for when in ("Open", "Close"):
            a, b = _num(v[when]), _num(h[when])
            if np.isnan(a) or np.isnan(b):
                rec[f"total_{when.lower()}"] = rec[f"spread_{when.lower()}"] = np.nan
                continue
            # the larger number is the total; the smaller sits on the favorite's row
            if a >= b:
                rec[f"total_{when.lower()}"], rec[f"spread_{when.lower()}"] = a, b   # home favored by b
            else:
                rec[f"total_{when.lower()}"], rec[f"spread_{when.lower()}"] = b, -a  # away favored by a
        rows.append(rec)
    return pd.DataFrame(rows)


def fetch_all(force=False):
    frames = []
    for s in range(FIRST, LAST + 1):
        d = parse_season(s)
        d["season"] = s
        frames.append(d)
        print(f"  SBR {s}: {len(d)} games", flush=True)
    out = pd.concat(frames, ignore_index=True)
    # archive typos: totals outside a sane range, or opens that are clearly a different market
    bad_t = ~out.total_open.between(25, 75) | ~out.total_close.between(25, 75) | ((out.total_open - out.total_close).abs() > 10)
    bad_s = (out.spread_open.abs() > 30) | ((out.spread_open - out.spread_close).abs() > 14)
    out.loc[bad_t, ["total_open", "total_close"]] = np.nan
    out.loc[bad_s, ["spread_open", "spread_close"]] = np.nan
    print(f"  dropped {int(bad_t.sum())} total / {int(bad_s.sum())} spread lines as archive typos", flush=True)
    out.to_parquet(RAW / "odds" / "sbr_open_close.parquet", index=False)
    return out


def match_to_games(sbr, games):
    """Attach nflverse game_id by season + teams (+ nearest date)."""
    g = games[["game_id", "season", "date", "home_team", "away_team"]].copy()
    # "NewYork" is ambiguous in the archive: try both teams, the date match picks one
    ny = sbr[(sbr.home == "NewYork") | (sbr.away == "NewYork")]
    sbr = pd.concat([sbr.drop(ny.index)] + [ny.replace({"home": {"NewYork": t}, "away": {"NewYork": t}})
                                           for t in ("NYG", "NYJ")], ignore_index=True)
    m = sbr.merge(g, left_on=["season", "home", "away"], right_on=["season", "home_team", "away_team"], how="left",
                  suffixes=("", "_g"))
    m["dd"] = (m.date - m.date_g).abs().dt.days
    m = m.sort_values("dd").drop_duplicates(["season", "home", "away", "date"])
    m = m[m.dd <= 3]
    # neutral-site games are sometimes listed with home/away flipped
    unmatched = sbr.merge(m[["season", "home", "away", "date"]], how="left", indicator=True)
    unmatched = unmatched[unmatched._merge == "left_only"].drop(columns="_merge")
    flip = unmatched.merge(g, left_on=["season", "home", "away"], right_on=["season", "away_team", "home_team"],
                           suffixes=("", "_g"))
    flip["dd"] = (flip.date - flip.date_g).abs().dt.days
    flip = flip[flip.dd <= 3].copy()
    for c in ("open", "close"):
        flip[f"spread_{c}"] = -flip[f"spread_{c}"]
    return pd.concat([m, flip], ignore_index=True)[
        ["game_id", "total_open", "total_close", "spread_open", "spread_close"]].rename(
        columns={"total_close": "sbr_total_close", "spread_close": "sbr_spread_close"})
