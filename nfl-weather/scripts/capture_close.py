"""Record Pinnacle's closing total for each kickoff slot (PREREGISTRATION.md, amendment 3).

Runs every 15 minutes (ops/capture_closes.sh, launchd). When NFL games kick off in
2–20 minutes and that kickoff time hasn't been captured yet, one Odds API call
(1 credit) records the current total and prices of every logged book (LIVE_BOOKS) for
every game in the slot; the secondary CLV uses Pinnacle's.
Rows are appended to data/forward/closes.csv. A slot that fails (no key, quota low,
API down), or that comes back without Pinnacle's total for some game, is retried on the
next run while it's still inside the window (at most MAX_TRIES calls per slot). What is
still missing then stays missing: score_forward.py reports missing closes and never
imputes them. The scorer takes each game's last captured row.

Each game takes at most one feed listing (since Sep 29, 2026). The feed can list the same two
teams more than once (a relisted event, or a rematch later in the season), and matching on the
teams alone wrote every listing's rows. Now a listing counts for a game only if it has the
game's two teams and starts within NEAR (6 hours) of the scheduled kickoff; one with no readable
start time never counts. Among those, a listing with a complete Pinnacle quote (a total and a
valid under price) comes first, as on the board (board.one_row_per_game); then the one starting
nearest the kickoff. Two listings that are equally good and equally near are a tie, and the game
takes neither. A tie, or no listing within 6 hours, leaves the game's close missing, like a game
the feed doesn't list, and the slot is retried like any other missing close. Every such case is
printed. Listings that match no game due now are ignored.

    python scripts/capture_close.py [--now 2026-10-09T00:05:00Z]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import oddsapi
from nflweather.config import RAW, ROOT
from nflweather.market import valid_odds

WINDOW = (pd.Timedelta(minutes=2), pd.Timedelta(minutes=20))
MAX_TRIES = 2
NEAR = pd.Timedelta(hours=6)       # a listing belongs to a game only if it starts within this of the kickoff
FWD = ROOT / "data" / "forward"
CLOSES, STATE = FWD / "closes.csv", FWD / "close_state.json"


def one_listing(due, feed):
    """The feed listing (event_id) each due game takes: same home and away teams, starting within NEAR of
    the scheduled kickoff. Among those, one with a complete Pinnacle quote first (as board.one_row_per_game
    ranks them), then the nearest the kickoff. A tie between equally good listings takes none. Returns the
    (game_id, event_id) pairs and a note for each game with more than one listing of its teams, or none taken."""
    ev = feed[["event_id", "home_team", "away_team", "commence_utc"]].drop_duplicates("event_id")
    pin = feed[feed.book.eq(oddsapi.RULE_BOOK)].drop_duplicates("event_id")
    quoted = set(pin.event_id[pin.close_total.notna() & valid_odds(pin.close_under)])
    c = due[["game_id", "kick_utc", "home_team", "away_team"]].merge(ev, on=["home_team", "away_team"])
    start = pd.to_datetime(c.commence_utc, utc=True, format="ISO8601", errors="coerce")   # unreadable: NaT
    c["gap"] = (start - c.kick_utc).abs()
    c["quoted"] = c.event_id.isin(quoted)
    pick, notes = [], []
    for gid, x in c.groupby("game_id", sort=False):
        near = x[x.gap <= NEAR]
        if near.quoted.any():
            near = near[near.quoted]
        best = near[near.gap == near.gap.min()]
        seen = "; ".join(f"{e} starting {t}" if isinstance(t, str) else f"{e}, no start time"
                         for t, e in zip(x.commence_utc, x.event_id))
        head = (f"{gid}: {len(x)} feed listing{'s' * (len(x) > 1)} of {x.away_team.iloc[0]} at "
                f"{x.home_team.iloc[0]} ({seen})")
        if len(best) == 1:
            pick.append((gid, best.event_id.iloc[0]))
            if len(x) > 1:
                why = ("the nearest the kickoff with a Pinnacle quote" if best.quoted.iloc[0]
                       else "the nearest the kickoff; none has a Pinnacle quote")
                notes.append(f"{head}; kept {best.event_id.iloc[0]}, {why}")
        elif len(best) > 1:
            notes.append(f"{head}; {len(best)} are equally good and equally near the kickoff, so none is kept "
                         "and the close is missing")
        else:
            notes.append(f"{head}; none starts within 6 hours of the kickoff, so the close is missing")
    return pd.DataFrame(pick, columns=["game_id", "event_id"]), notes


ap = argparse.ArgumentParser()
ap.add_argument("--now", help="pretend it's this UTC time (testing)")
args = ap.parse_args()
now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")

g = pd.read_csv(RAW / "games.csv")
g = g[g.result.isna() & g.gametime.notna()].copy()
g["kick_utc"] = pd.to_datetime(g.gameday + " " + g.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
state = json.loads(STATE.read_text()) if STATE.exists() else {"captured": []}
state.setdefault("tries", {})
due = g[(g.kick_utc - now).between(*WINDOW)]
slots = sorted({t.strftime("%Y-%m-%dT%H:%MZ") for t in due.kick_utc} - set(state["captured"]))
if not slots:
    sys.exit()

due = due[due.kick_utc.dt.strftime("%Y-%m-%dT%H:%MZ").isin(slots)]
try:
    pin = oddsapi.live(markets=("totals",))
except SystemExit as e:
    sys.exit(print(f"{now:%Y-%m-%d %H:%M}Z close capture: no prices for {', '.join(slots)} ({e}); "
                   "will retry inside the window"))
pin = pin[pin.market == "totals"].rename(columns={"home": "home_team", "away": "away_team", "total": "close_total",
                                                  "under_price": "close_under", "over_price": "close_over",
                                                  "snapshot_utc": "capture_utc"})
pick, notes = one_listing(due, pin)
pin = pin.merge(pick, on="event_id")          # only the listing each due game takes, labelled with its game
rows = due[["game_id", "kick_utc", "home_team", "away_team"]].merge(
    pin[["game_id", "home_team", "away_team", "capture_utc", "book", "close_total", "close_under", "close_over",
         "book_update"]],
    on=["game_id", "home_team", "away_team"], how="left")
rows["kick_utc"] = rows.kick_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
FWD.mkdir(parents=True, exist_ok=True)
rows.to_csv(CLOSES, mode="a", header=not CLOSES.exists(), index=False)
slot_of = dict(zip(due.game_id, due.kick_utc.dt.strftime("%Y-%m-%dT%H:%MZ")))
have = set(rows.loc[rows.book.eq("pinnacle") & rows.close_total.notna(), "game_id"])
for slot in slots:
    state["tries"][slot] = state["tries"].get(slot, 0) + 1
    complete = all(g in have for g, sl in slot_of.items() if sl == slot)
    if complete or state["tries"][slot] >= MAX_TRIES:
        state["captured"] = sorted(set(state["captured"]) | {slot})
STATE.write_text(json.dumps(state))
pin_games = len(have)
print(f"{now:%Y-%m-%d %H:%M}Z close capture: Pinnacle close for {pin_games}/{due.game_id.nunique()} games, "
      f"{rows.book.nunique()} books logged, for {', '.join(slots)}")
for note in notes:
    print(f"{now:%Y-%m-%d %H:%M}Z close capture: {note}")
