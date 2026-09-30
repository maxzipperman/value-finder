"""The names-only preflight (amendment 1, item 8). It reads NO price and prints NO score.

The protocol, registered in amendment 1: on Thursday, after `markets odds5m probe` has saved its schedules (team
names and kickoffs only) and BEFORE any F1 price is opened, the hub runs this. Any further alias comes only from
its list of names, judged on names and schedules and never on a price or a result, and is recorded in a dated
note with the list. It also counts games that appear under two event ids; if they are more than 1 in 100 games,
the hub decides what to do before any price is opened, and says so in the note.

Input: the schedules the probe saves from historical /events sweeps, <raw_dir>/_schedules/<sport>.parquet, which
hold only id, sport, commence_time, home_team, away_team and first_seen (bulk.SCHEDULE_SCHEMA). Games in a sealed
season window (2026) or outside every window are dropped as they are read, before anything looks at them.

It runs the engine's own name resolution and its own outcomes.match() on those events, with every final score
in the score tables replaced by the table's row number, so it predicts which F1 games will get no final score,
and why, and which score-table game each event lands on, without reading out a score:
  names.csv                 every distinct team name, the school or team it resolves to, and how (the alias
                            table, the team files, an exact school name, the prefix rule, or unresolved); prefix
                            and unresolved rows first. A prefix row is right only if the school is the one the
                            name means: read it by eye.
  unmatched.csv             every unmatched 2020-25 event: sport, event id, kickoff, home, away, reason
  unreached.csv             FBS schools (score table, 2020-25) that no name reaches
  one_game_two_events.csv   score-table games that two or more event ids both match (a relisted game would be
                            bet and graded twice; until the hub decides, that is a known limit)

Usage, from sharp-markets/ in the checkout that holds the probe's saved schedules:
  uv run python -m markets.research.price_engine.names_preflight --out <scratch dir>
      [--raw-dir data/raw] [--cfb-raw <cfbfastR folder>]
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ...oddsapi import bulk
from ...settings import RAW_DIR
from . import outcomes as o
from .model import CFB, NFL, REPO

COLS = ["id", "commence_time", "home_team", "away_team"]
TWO_EVENT_LIMIT = 0.01          # more than 1 in 100 games under two event ids: the hub decides before any price


def load_events(raw_dir: Path, cfg: dict) -> tuple[pd.DataFrame, Counter]:
    """The probe's saved schedules as events (sport, event_id, kickoff, home, away), 2020-25 only."""
    dropped: Counter = Counter()
    frames = []
    for sport in (NFL, CFB):
        path = bulk.schedule_path(raw_dir, sport)
        if not path.exists():
            dropped[f"{sport}: no schedule file"] += 1
            continue
        s = pq.read_table(path, columns=COLS).to_pandas()
        s["commence_time"] = pd.to_datetime(s.commence_time, utc=True)
        keep = pd.Series([(lambda w: w is not None and not w["sealed"])(bulk.window_for(cfg, sport, k.to_pydatetime()))
                          for k in s.commence_time], index=s.index, dtype=bool)
        dropped[f"{sport}: sealed or outside the season windows"] += int((~keep).sum())
        s = s[keep]
        frames.append(pd.DataFrame(dict(sport=sport, event_id=s["id"], kickoff=s.commence_time,
                                        home=s.home_team, away=s.away_team)))
    ev = (pd.concat(frames, ignore_index=True) if frames
          else pd.DataFrame(columns=["sport", "event_id", "kickoff", "home", "away"]))
    return ev, dropped


def fbs_schools(path: Path | None = None) -> set[str]:
    """Schools listed as FBS in the college score table, 2020-25 (read with the season filter: no 2026 row)."""
    gp = pd.read_parquet(path or REPO / "cfb-weather/data/processed/games.parquet",
                         columns=["season", "home_team", "home_division", "away_team", "away_division"],
                         filters=o.SEASON_FILTER)
    out: set[str] = set()
    for t, d in ((gp.home_team, gp.home_division), (gp.away_team, gp.away_division)):
        out |= set(t[d.astype(str).str.lower() == "fbs"])
    return out


def _planted(t: pd.DataFrame) -> pd.DataFrame:
    """The score table with both scores replaced by the row number: nothing real can be read out, and two events
    that land on one game show the same number."""
    t = t.reset_index(drop=True).copy()
    t["home_score"] = t.index.astype(float)
    t["away_score"] = t.index.astype(float)
    return t


def check(ev: pd.DataFrame, nfl: pd.DataFrame, cfb: pd.DataFrame, cfb_raw: Path | None,
          fbs: set[str]) -> dict:
    """The preflight on events and score tables (scores are planted here, whatever the tables hold)."""
    detail: dict = {}
    scores, why = o.match(ev, nfl=_planted(nfl), cfb=_planted(cfb), cfb_raw=cfb_raw, detail=detail)
    names = detail["names"]
    order = {o.PREFIX: 0, o.UNRESOLVED: 1}
    names = names.assign(fbs=[(s in fbs) if isinstance(s, str) and sp == CFB else None
                              for sp, s in zip(names.sport, names.resolves_to)])
    names = names.sort_values(["how"], key=lambda h: h.map(order).fillna(2), kind="stable").reset_index(drop=True)
    names["sport"] = names.sport.map({NFL: "NFL", CFB: "CFB"})
    un = detail["unmatched"].merge(ev, on=["sport", "event_id"], how="left")
    un = un[["sport", "event_id", "kickoff", "home", "away", "reason"]]
    shared = scores[scores.duplicated(["sport", "home_score"], keep=False)].merge(ev, on=["sport", "event_id"])
    shared = shared.rename(columns={"home_score": "score_table_row"}).drop(columns="away_score")
    games = scores.drop_duplicates(["sport", "home_score"])
    two = shared.drop_duplicates(["sport", "score_table_row"])
    reached = set(names[names.sport == "CFB"].resolves_to.dropna())
    summary = {"events": len(ev), "matched_events": len(scores), "unmatched_by_reason": dict(why),
               "score_table_games_matched": len(games), "games_under_two_or_more_event_ids": len(two),
               "share_under_two_event_ids": len(two) / len(games) if len(games) else 0.0,
               "cfb_team_files": detail.get("cfb_team_files"),
               "names_by_how": names.groupby(["sport", "how"]).size().to_dict()}
    summary["hub_decides_before_any_price"] = summary["share_under_two_event_ids"] > TWO_EVENT_LIMIT
    return {"names": names, "unmatched": un, "unreached": pd.DataFrame(dict(school=sorted(fbs - reached))),
            "one_game_two_events": shared, "summary": summary}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="names-only preflight for the price engine (reads no price)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw-dir", default=str(RAW_DIR))
    ap.add_argument("--cfb-raw", default=str(REPO / "cfb-weather/data/raw/cfbfastr"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfb_raw = Path(a.cfb_raw)
    n_files = len(o.team_files(cfb_raw))
    print("cfbfastR team files:", f"FOUND ({n_files})" if n_files else
          "MISSING (college names resolve by the alias table, exact school names and the prefix rule only)", cfb_raw)
    ev, dropped = load_events(Path(a.raw_dir), bulk.load_config())
    print("schedule events kept (2020-25):", ev.groupby("sport").size().to_dict(), "| left out:", dict(dropped))
    if ev.empty:
        print("No saved schedule events: nothing to check.")
        return 0
    res = check(ev, o.nfl_games(), o.cfb_games(), cfb_raw, fbs_schools())
    for name in ("names", "unmatched", "unreached", "one_game_two_events"):
        res[name].to_csv(out / f"{name}.csv", index=False)
    s = res["summary"]
    print("names by how they resolved:", s["names_by_how"])
    print("matched events:", s["matched_events"], "of", s["events"], "| unmatched by reason:", s["unmatched_by_reason"])
    print(f"score-table games under two or more event ids: {s['games_under_two_or_more_event_ids']:,} of "
          f"{s['score_table_games_matched']:,} matched games ({s['share_under_two_event_ids']:.2%})"
          + (": MORE THAN 1 IN 100, the hub decides what to do before any F1 price is opened"
             if s["hub_decides_before_any_price"] else ""))
    print("FBS schools (2020-25) no name reaches:", list(res["unreached"].school))
    print(f"wrote {out}/names.csv, unmatched.csv, unreached.csv, one_game_two_events.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
