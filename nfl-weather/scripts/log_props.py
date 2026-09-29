"""NFL props, alternate lines and team totals, logged live at T-48h, T-24h, T-2h and the close
(launchd com.valuefinder.propslog every 15 minutes, ops/install_live_uses.sh). Logging only. See
nflweather/live.py for the markets and books (the historical F2/F3 series, continued).

The event list is free; each due snapshot costs 1 credit per market returned (up to 9). A background
logger: it runs only on a paid plan and stops at the background floor (quota.py). A slot missed
while the Mac slept stays missing; nothing is imputed.

Prices are requested in decimal odds, as the historical F2/F3 pulls are (sharp-markets/config/odds5m.yaml).
props_state.json is rewritten (temp file, then rename) after every captured slot, so an error part
way through never re-fetches a slot it already paid for.

    python scripts/log_props.py [--now 2026-10-11T15:00:00Z]

--now is a dry run: it lists the slots that would be due then (the event list is free) and spends
nothing, writes nothing and consumes no real slot.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ODDS_QUOTA_KIND", "background")

import pandas as pd

from nflweather import live, oddsapi, quota
from nflweather.config import ROOT

FWD = ROOT / "data" / "forward"
OUT, STATE = FWD / "props_log.csv", FWD / "props_state.json"

ap = argparse.ArgumentParser()
ap.add_argument("--now", help="pretend it's this UTC time when picking slots (testing; a dry run)")
args = ap.parse_args()
now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")

why = quota.check()
if why and not args.now:
    sys.exit()          # free plan or below the floor: silent, the job runs every 15 minutes
try:
    events = oddsapi._get(f"/sports/{oddsapi.SPORT}/events", dict(dateFormat="iso")).json()   # free
except SystemExit as e:
    sys.exit(print(f"{now:%Y-%m-%d %H:%M}Z props log: no event list ({e})"))
state = json.loads(STATE.read_text()) if STATE.exists() else {"captured": []}
captured = set(state["captured"])
due = live.props_due(events, captured, now)
if args.now:
    sys.exit(print(f"{now:%Y-%m-%d %H:%M}Z props log (dry run): {len(due)} slots due: "
                   + ("; ".join(f"{ev['away_team']} @ {ev['home_team']} T-{h}h" for ev, h in due) or "none")))
done, spent = [], 0
for ev, h in due:
    why = quota.check()
    if why:
        print(f"  stopping: {why}")
        break
    try:
        r = oddsapi._get(f"/sports/{oddsapi.SPORT}/events/{ev['id']}/odds",
                         dict(bookmakers=",".join(live.PROP_BOOKS), markets=",".join(live.PROP_MARKETS),
                              oddsFormat=live.PROP_ODDS_FORMAT, dateFormat="iso"))
    except SystemExit as e:
        print(f"  {ev['away_team']} @ {ev['home_team']} T-{h}h: no prices ({e}); retried while the slot is open")
        continue
    last = int(float(r.headers.get("x-requests-last") or 0))
    spent += last
    stamp = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    # The raw text goes to disk, and the slot is marked captured, before anything is parsed: a crash
    # after this point never re-fetches (and re-bills) the slot. Rows can be rebuilt from the raw file.
    dest = oddsapi.CACHE / "props" / f"{stamp.replace(':', '')}_{ev['id']}_T{h}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"snapshot_utc": stamp, "offset_h": h, "credits_last": last,
                                "credits_remaining": r.headers.get("x-requests-remaining"),
                                "odds_format": live.PROP_ODDS_FORMAT, "body": r.text}))
    captured.add(f"{ev['id']}:{h}")
    state["captured"] = sorted(captured)
    live.save_state(STATE, state)
    try:
        rows = live.props_rows(json.loads(r.text), stamp, h)
    except ValueError as e:
        print(f"  {ev['away_team']} @ {ev['home_team']} T-{h}h: unreadable body ({e}); raw kept in {dest.name}")
        continue
    if len(rows):
        FWD.mkdir(parents=True, exist_ok=True)
        rows.to_csv(OUT, mode="a", header=not OUT.exists(), index=False)
    done.append(f"{ev['away_team']} @ {ev['home_team']} T-{h}h ({len(rows)} quotes, {last} cr)")
    if last > len(live.PROP_MARKETS):
        print(f"  circuit breaker: one call billed {last} credits, more than {len(live.PROP_MARKETS)} markets")
        break
if done:
    print(f"{now:%Y-%m-%d %H:%M}Z props log: {len(done)} snapshots, {spent} credits: " + "; ".join(done))
