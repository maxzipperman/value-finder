"""Record the closing total for each kickoff slot (PREREGISTRATION.md, amendment 2).

Runs every 15 minutes (ops/capture_closes.sh, launchd). When FBS games kick off in
2–20 minutes and that kickoff time hasn't been captured yet, one Odds API call
(1 credit) records the current total and prices for every game in the slot:
Pinnacle when it lists the game, else DraftKings, as on the board. Rows are appended
to data/forward/closes.csv. A slot that fails (no key, quota low, API down), or that
comes back without a total for some game, is retried on the next run while it's still
inside the window (at most MAX_TRIES calls per slot). What is still missing then stays
missing: score_forward.py reports missing closes and never imputes them. The scorer
takes each game's last captured row.

Each game takes one feed listing (since Sep 29, 2026): the listing of its two teams that
starts nearest the scheduled kickoff, and only within NEAR (6 hours) of it. The feed can list
the same two teams more than once (a relisted event, or a rematch such as a conference title
game), and matching on the teams alone wrote a row for every listing. Two listings equally
near kickoff are a tie: the game takes neither and is recorded as missing, like a game the
feed doesn't list. Every such case is printed. Listings that match no game due now are ignored.

    python scripts/capture_close.py [--now 2026-10-01T23:50:00Z]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cfbweather import fetch
from cfbweather.board import odds_team_names
from cfbweather.build import schedules
from cfbweather.config import ROOT

WINDOW = (pd.Timedelta(minutes=2), pd.Timedelta(minutes=20))
MAX_TRIES = 2
NEAR = pd.Timedelta(hours=6)       # a listing belongs to a game only if it starts within this of the kickoff
FWD = ROOT / "data" / "forward"
CLOSES, STATE = FWD / "closes.csv", FWD / "close_state.json"


def one_listing(due, feed):
    """The feed listing (its `listing` number; the parsed feed keeps no event id) each due game takes: same
    home and away teams, starting within NEAR of the scheduled kickoff, the nearest if several do. A tie for
    nearest takes none. Returns the (game_id, listing) pairs and a note for each game with more than one
    listing of its teams, or none near."""
    c = due[["game_id", "start_utc", "home_team", "away_team"]].merge(
        feed[["listing", "home_team", "away_team", "commence_utc"]], on=["home_team", "away_team"])
    c["gap"] = (pd.to_datetime(c.commence_utc, utc=True) - c.start_utc).abs()
    pick, notes = [], []
    for gid, x in c.groupby("game_id", sort=False):
        near = x[x.gap <= NEAR]
        best = near[near.gap == near.gap.min()]
        head = (f"{gid}: {len(x)} feed listing{'s' * (len(x) > 1)} of {x.away_team.iloc[0]} at "
                f"{x.home_team.iloc[0]}, starting {', '.join(x.commence_utc)}")
        if len(best) == 1:
            pick.append((gid, best.listing.iloc[0]))
            if len(x) > 1:
                notes.append(f"{head}; kept the one starting {best.commence_utc.iloc[0]}, nearest the kickoff")
        elif len(best) > 1:
            notes.append(f"{head}; {len(best)} are equally near the kickoff, so none is kept and the close is missing")
        else:
            notes.append(f"{head}; none starts within 6 hours of the kickoff, so the close is missing")
    return pd.DataFrame(pick, columns=["game_id", "listing"]), notes


ap = argparse.ArgumentParser()
ap.add_argument("--now", help="pretend it's this UTC time (testing)")
args = ap.parse_args()
now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")

s = schedules()
s = s[(s.season == s.season.max()) & ~s.tbd & s.home_points.isna()]
if "home_division" in s:
    s = s[s.home_division.astype(str).str.lower().eq("fbs") | s.away_division.astype(str).str.lower().eq("fbs")]
state = json.loads(STATE.read_text()) if STATE.exists() else {"captured": []}
state.setdefault("tries", {})
due = s[(s.start_utc - now).between(*WINDOW)]
slots = sorted({t.strftime("%Y-%m-%dT%H:%MZ") for t in due.start_utc} - set(state["captured"]))
if not slots:
    sys.exit()

due = due[due.start_utc.dt.strftime("%Y-%m-%dT%H:%MZ").isin(slots)]
oa = fetch.odds_api_totals(odds_team_names()).dropna(subset=["home_team", "away_team"])
if oa.empty:
    sys.exit(print(f"{now:%Y-%m-%d %H:%M}Z close capture: no prices for {', '.join(slots)}; will retry inside the window"))
oa = oa.reset_index(drop=True).rename_axis("listing").reset_index()
pick, notes = one_listing(due, oa)
oa = oa.merge(pick, on="listing")             # only the listing each due game takes, labelled with its game
got = due[["game_id", "start_utc", "home_team", "away_team"]].merge(
    oa.drop(columns=["commence_utc", "listing"]), on=["game_id", "home_team", "away_team"], how="left")
rows = got.rename(columns={"mkt_total": "close_total", "mkt_under": "close_under", "mkt_over": "close_over",
                           "quote_utc": "capture_utc"})
rows["start_utc"] = rows.start_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
cols = ["capture_utc", "game_id", "start_utc", "home_team", "away_team", "line_src", "close_total", "close_under",
        "close_over"]
FWD.mkdir(parents=True, exist_ok=True)
rows[cols].to_csv(CLOSES, mode="a", header=not CLOSES.exists(), index=False)
slot_of = dict(zip(due.game_id, due.start_utc.dt.strftime("%Y-%m-%dT%H:%MZ")))
have = set(rows.loc[rows.close_total.notna(), "game_id"])
for slot in slots:
    state["tries"][slot] = state["tries"].get(slot, 0) + 1
    complete = all(g in have for g, sl in slot_of.items() if sl == slot)
    if complete or state["tries"][slot] >= MAX_TRIES:
        state["captured"] = sorted(set(state["captured"]) | {slot})
STATE.write_text(json.dumps(state))
print(f"{now:%Y-%m-%d %H:%M}Z close capture: {int(rows.close_total.notna().sum())}/{len(rows)} games priced "
      f"for {', '.join(slots)}")
for note in notes:
    print(f"{now:%Y-%m-%d %H:%M}Z close capture: {note}")
