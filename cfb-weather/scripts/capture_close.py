"""Record the closing total for each kickoff slot (PREREGISTRATION.md, amendment 2).

Runs every 15 minutes (ops/capture_closes.sh, launchd). When FBS games kick off in
2–20 minutes and that kickoff time hasn't been captured yet, one Odds API call
(1 credit) records the current total and prices for every game in the slot:
Pinnacle when it lists the game, else DraftKings, as on the board. Rows are appended
to data/forward/closes.csv. A slot that fails (no key, quota low, API down), or that
comes back without a total for some game, is retried on the next run while it's still
inside the window (at most MAX_TRIES calls per slot). What is still missing then stays
missing: score_forward.py reports missing closes and never imputes them. The scorer
uses a captured row only for the listing it was captured for: one captured 2 to 20
minutes (both ends included) before that listing's kickoff, the last such row in the
file; a row outside that window is refused or set aside, counted and named (draft
amendment 6, section 1).

A feed event is one event in The Odds API's odds feed: a game as the feed lists it, with its own start
time and books. Each game takes at most one feed event (since Sep 29, 2026). The feed can list the same two
teams more than once (a relisted event, or a rematch such as a conference title game), and matching on the
teams alone wrote a row for every feed event. Now a feed event counts for a game only if it has the game's
two teams and starts within NEAR (6 hours) of the scheduled kickoff; one with no readable start time never
counts. Among those, a feed event priced at Pinnacle comes first, then one priced at DraftKings, then one
priced at neither, as on the board (board.one_row_per_game, fetch.RULE_BOOKS); then the one starting nearest
the kickoff. Two feed events that are equally good and equally near are a tie, and the game takes neither.
A tie, or no feed event within 6 hours, leaves the game's close missing, like a game the feed doesn't list,
and the slot is retried like any other missing close. Every such case is printed. Feed events that match no
game due now are ignored.

Amendment 5 (reading 2) registers that rule, with one change: when the equally near feed events are all
priced at the same rule book with the same quote (the same total and the same prices), they are the same
game listed twice, and the first in the feed is taken. A tie between different quotes, or between feed
events priced at neither book, still takes neither.

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

sys.path.insert(0, str(ROOT.parent))
from ops.collector_guard import close_slot
from ops import close_observation

WINDOW = (pd.Timedelta(minutes=2), pd.Timedelta(minutes=20))
MAX_TRIES = 2
NEAR = pd.Timedelta(hours=6)       # a feed event belongs to a game only if it starts within this of the kickoff
BOOK_NAME = {"pinnacle": "Pinnacle", "draftkings": "DraftKings"}   # for the printed notes only
FWD = ROOT / "data" / "forward"
CLOSES, STATE = FWD / "closes.csv", FWD / "close_state.json"


def one_event(due, feed):
    """The feed event (its `event` number, its place in the feed; the parsed feed keeps no event id) each due
    game takes: same home and away teams, starting within NEAR of the scheduled kickoff. Among those,
    Pinnacle's price first, then DraftKings', then neither (fetch.RULE_BOOKS, as board.one_row_per_game ranks
    them), then the nearest the kickoff. A tie between equally good feed events takes none, unless they are all
    priced at the same rule book with the same quote (the same total and prices): then they are the same game
    listed twice, and the first in the feed is taken (amendment 5, reading 2). Returns the (game_id, event)
    pairs and a note for each game with more than one feed event of its teams, or none taken."""
    c = due[["game_id", "start_utc", "home_team", "away_team"]].merge(
        feed[["event", "home_team", "away_team", "commence_utc", "line_src", "mkt_total", "mkt_under", "mkt_over"]],
        on=["home_team", "away_team"])
    start = pd.to_datetime(c.commence_utc, utc=True, format="ISO8601", errors="coerce")   # unreadable: NaT
    c["gap"] = (start - c.start_utc).abs()
    c["rank"] = c.line_src.map({b: i for i, b in enumerate(fetch.RULE_BOOKS)}).fillna(len(fetch.RULE_BOOKS))
    c["seen"] = [f"starting {t}" if isinstance(t, str) else "no start time" for t in c.commence_utc]
    c["quote"] = [(src, *(None if pd.isna(v) else float(v) for v in q))   # the rule book and its total and prices
                  for src, *q in zip(c.line_src, c.mkt_total, c.mkt_under, c.mkt_over)]
    pick, notes = [], []
    for gid, x in c.groupby("game_id", sort=False):
        near = x[x.gap <= NEAR]
        near = near[near["rank"] == near["rank"].min()]
        best = near[near.gap == near.gap.min()]
        head = (f"{gid}: {len(x)} feed event{'s' * (len(x) > 1)} of {x.away_team.iloc[0]} at "
                f"{x.home_team.iloc[0]} ({'; '.join(x.seen)})")
        if len(best) > 1 and best.line_src.isin(fetch.RULE_BOOKS).all() and best.quote.nunique() == 1:
            first = best.sort_values("event").iloc[0]
            pick.append((gid, first.event))
            notes.append(f"{head}; kept the one {first.seen}, the first in the feed: the {len(best)} feed events "
                         f"equally near the kickoff carry the same {BOOK_NAME.get(first.line_src, first.line_src)} "
                         "quote, so they are the same game listed twice")
        elif len(best) == 1:
            pick.append((gid, best.event.iloc[0]))
            if len(x) > 1:
                src = best.line_src.iloc[0]
                why = (f"the nearest the kickoff priced at {BOOK_NAME.get(src, src)}" if src
                       else "the nearest the kickoff; none is priced at Pinnacle or DraftKings")
                notes.append(f"{head}; kept the one {best.seen.iloc[0]}, {why}")
        elif len(best) > 1:
            notes.append(f"{head}; {len(best)} are equally good and equally near the kickoff, so none is kept "
                         "and the close is missing")
        else:
            notes.append(f"{head}; none starts within 6 hours of the kickoff, so the close is missing")
    return pd.DataFrame(pick, columns=["game_id", "event"]), notes


ap = argparse.ArgumentParser()
ap.add_argument("--now", help="pretend it's this UTC time (testing)")
args = ap.parse_args()
now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")

s = schedules()
s = s[(s.season == s.season.max()) & ~s.tbd & s.home_points.isna()]
if "home_division" in s:
    s = s[s.home_division.astype(str).str.lower().eq("fbs") | s.away_division.astype(str).str.lower().eq("fbs")]
close_observation.recover(CLOSES, STATE)
state = json.loads(STATE.read_text()) if STATE.exists() else {"captured": []}
state.setdefault("tries", {})
observation = close_slot((), {}, now.to_pydatetime())
if close_observation.seen(state, observation):
    sys.exit(print("close capture: scheduled observation already applied"))
due = s[(s.start_utc - now).between(*WINDOW)]
slots = sorted({t.strftime("%Y-%m-%dT%H:%MZ") for t in due.start_utc} - set(state["captured"]))
if not slots:
    sys.exit()

due = due[due.start_utc.dt.strftime("%Y-%m-%dT%H:%MZ").isin(slots)]
oa = fetch.odds_api_totals(odds_team_names(), role="cfb-close",
                        request_slot=observation).dropna(subset=["home_team", "away_team"])
if oa.empty:
    if oa.attrs.get("admission_conclusive", False):
        close_observation.apply(CLOSES, STATE, observation, before_state=state)
    sys.exit(print(f"{now:%Y-%m-%d %H:%M}Z close capture: no prices for {', '.join(slots)}; later scheduled observation only; uncertain admission remains held"))
oa = oa.reset_index(drop=True).rename_axis("event").reset_index()     # each feed event, numbered in feed order
pick, notes = one_event(due, oa)
oa = oa.merge(pick, on="event")               # only the feed event each due game takes, labelled with its game
got = due[["game_id", "start_utc", "home_team", "away_team"]].merge(
    oa.drop(columns=["commence_utc", "event"]), on=["game_id", "home_team", "away_team"], how="left")
rows = got.rename(columns={"mkt_total": "close_total", "mkt_under": "close_under", "mkt_over": "close_over",
                           "quote_utc": "capture_utc"})
rows["start_utc"] = rows.start_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
cols = ["capture_utc", "game_id", "start_utc", "home_team", "away_team", "line_src", "close_total", "close_under",
        "close_over"]
slot_of = dict(zip(due.game_id, due.start_utc.dt.strftime("%Y-%m-%dT%H:%MZ")))
have = set(rows.loc[rows.close_total.notna(), "game_id"])
complete_slots = {slot for slot in slots if all(g in have for g, sl in slot_of.items() if sl == slot)}
state = close_observation.apply(CLOSES, STATE, observation, before_state=state,
                                rows=rows[cols], slots=slots,
                                complete=complete_slots, max_tries=MAX_TRIES)
print(f"{now:%Y-%m-%d %H:%M}Z close capture: {int(rows.close_total.notna().sum())}/{len(rows)} games priced "
      f"for {', '.join(slots)}")
for note in notes:
    print(f"{now:%Y-%m-%d %H:%M}Z close capture: {note}")
