"""Thursday names-only preflight for the price engine. Reads NO price.

Input: the schedules `markets odds5m probe` saves from historical /events sweeps,
  <raw_dir>/_schedules/americanfootball_nfl.parquet and americanfootball_ncaaf.parquet
which hold only: id, sport, commence_time, home_team, away_team, first_seen (bulk.SCHEDULE_SCHEMA). Games in a
sealed season window (2026) or outside every window are dropped on read, before anything looks at them.

It runs the engine's own name functions and its own outcomes.match() on those events, so it predicts exactly
which F1 games will get no final score, and why, before any F1 price is opened:
  names.csv       every distinct team name, the school/team it resolves to, and how (alias / prefix / unresolved)
  unmatched.csv   every unmatched 2020-25 event: sport, id, kickoff, home, away, reason
  unreached.csv   FBS schools (score table 2020-25) that no feed name reaches
  one_game_two_events.csv   score-table games that two event ids both match (a relisted game would be bet twice)
Read names.csv by eye, prefix rows first: a prefix row is right only if the school is the one the name means.

Usage (from sharp-markets/ in the checkout that holds the probe's cache):
  uv run python thursday_names_preflight.py --out <scratch dir> [--raw-dir data/raw] [--cfb-raw <cfbfastr dir>]
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from markets.oddsapi import bulk
from markets.research.price_engine import outcomes as o
from markets.research.price_engine.model import CFB, NFL, REPO
from markets.settings import RAW_DIR
from markets.sport import load_teams

COLS = ["id", "commence_time", "home_team", "away_team"]


def load_events(raw_dir: Path, cfg: dict) -> tuple[pd.DataFrame, Counter]:
    dropped: Counter = Counter()
    frames = []
    for sport in (NFL, CFB):
        path = bulk.schedule_path(raw_dir, sport)
        if not path.exists():
            dropped[f"{sport}: no schedule file"] += 1
            continue
        s = pq.read_table(path, columns=COLS).to_pandas()
        s["commence_time"] = pd.to_datetime(s.commence_time, utc=True)
        keep = []
        for k in s.commence_time:
            w = bulk.window_for(cfg, sport, k.to_pydatetime())
            keep.append(w is not None and not w["sealed"])
        keep = pd.Series(keep, index=s.index)
        dropped[f"{sport}: sealed or outside the season windows"] += int((~keep).sum())
        s = s[keep]
        frames.append(pd.DataFrame(dict(sport=sport, event_id=s["id"], kickoff=s.commence_time,
                                        home=s.home_team, away=s.away_team)))
    ev = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["sport", "event_id", "kickoff",
                                                                                     "home", "away"])
    return ev, dropped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw-dir", default=str(RAW_DIR))
    ap.add_argument("--cfb-raw", default=str(REPO / "cfb-weather/data/raw/cfbfastr"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfb_raw = Path(a.cfb_raw)
    print("cfbfastR team files:", "FOUND" if any(cfb_raw.glob("team_info_*.parquet")) else
          "MISSING (the engine would fall back to the prefix rule alone)", cfb_raw)
    ev, dropped = load_events(Path(a.raw_dir), bulk.load_config())
    print("schedule events kept (2020-25):", ev.groupby("sport").size().to_dict(), "| left out:", dict(dropped))
    if ev.empty:
        return

    # names, resolved the engine's way
    g = o.cfb_games()
    schools = sorted(set(g.home_team) | set(g.away_team))
    fbs_schools = set()
    gp = pd.read_parquet(REPO / "cfb-weather/data/processed/games.parquet",
                         columns=["season", "home_team", "home_division", "away_team", "away_division"])
    gp = gp[gp.season.between(2020, 2025)]
    for t, d in ((gp.home_team, gp.home_division), (gp.away_team, gp.away_division)):
        fbs_schools |= set(t[d.astype(str).str.lower() == "fbs"])
    lookup = o.cfb_names(schools, cfb_raw)
    by_len = sorted(((o.norm(s), s) for s in schools), key=lambda x: -len(x[0]))
    teams = load_teams("nfl")
    rows = []
    for sport, name in sorted({(s, n) for s, h, w in zip(ev.sport, ev.home, ev.away) for n in (h, w)}):
        games = int(((ev.sport == sport) & ((ev.home == name) | (ev.away == name))).sum())
        if sport == NFL:
            code = teams.from_name(name) or o.EXTRA_NFL.get(o.norm(name))
            rows.append(dict(sport="NFL", name=name, resolves_to=code, how="alias" if code else "UNRESOLVED",
                             games=games))
        else:
            n = o.norm(name)
            s = o._school(name, lookup, by_len)
            how = ("alias" if n in lookup else "UNRESOLVED" if s is None else
                   "exact name" if n == o.norm(s) else f"PREFIX '{o.norm(s)}'")
            rows.append(dict(sport="CFB", name=name, resolves_to=s, how=how, games=games,
                             fbs=bool(s in fbs_schools) if s else None))
    names = pd.DataFrame(rows)
    names["order"] = names.how.map(lambda h: 0 if h.startswith("PREFIX") else 1 if h == "UNRESOLVED" else 2)
    names = names.sort_values(["order", "sport", "name"]).drop(columns="order")
    names.to_csv(out / "names.csv", index=False)
    print("names:", names.groupby(["sport", names.how.str.split(" ").str[0]]).size().to_dict())

    # the engine's own match, on the schedule's kickoffs. The score tables' score columns are replaced by the row
    # number (planted), so nothing real is read out, and two events landing on one game show up.
    cfb_t = o.cfb_games().reset_index(drop=True)
    nfl_t = o.nfl_games().reset_index(drop=True)
    for t in (cfb_t, nfl_t):
        t["home_score"] = t.index.astype(float)
        t["away_score"] = t.index.astype(float)
    scores, why = o.match(ev, nfl=nfl_t, cfb=cfb_t, cfb_raw=cfb_raw)
    shared = scores[scores.duplicated(["sport", "home_score"], keep=False)].merge(ev, on=["sport", "event_id"])
    shared = shared.rename(columns={"home_score": "score_table_row"}).drop(columns="away_score")
    shared.to_csv(out / "one_game_two_events.csv", index=False)
    print("score-table games matched by more than one event id:", shared.groupby("sport").score_table_row.nunique().to_dict())
    un = ev[~ev.set_index(["sport", "event_id"]).index.isin(scores.set_index(["sport", "event_id"]).index)].copy()
    un["reason"] = [("name" if (e.sport == CFB and (o._school(e.home, lookup, by_len) is None
                                                  or o._school(e.away, lookup, by_len) is None))
                     or (e.sport == NFL and not ((teams.from_name(e.home) or o.EXTRA_NFL.get(o.norm(e.home)))
                                                 and (teams.from_name(e.away) or o.EXTRA_NFL.get(o.norm(e.away)))))
                     else "no game within the window") for e in un.itertuples(index=False)]
    un.drop(columns=[]).to_csv(out / "unmatched.csv", index=False)
    print("matched:", scores.groupby("sport").size().to_dict(), "| unmatched by reason:", dict(why))

    reached = set(names[names.sport == "CFB"].resolves_to.dropna())
    unreached = sorted(fbs_schools - reached)
    pd.DataFrame(dict(school=unreached)).to_csv(out / "unreached.csv", index=False)
    print("FBS schools (2020-25) no name reaches:", unreached)
    print(f"wrote {out}/names.csv, unmatched.csv, unreached.csv, one_game_two_events.csv")


if __name__ == "__main__":
    main()
