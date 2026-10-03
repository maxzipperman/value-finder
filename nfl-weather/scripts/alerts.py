"""Weather betting alerts, tiered to match STRATEGY.md. Meant to run on a schedule
(scripts/install_alerts.sh sets up a macOS launchd job). Each run refreshes the
schedule, forecasts and lines, then alerts once per event:

RULE B (the forward-tested betting rule; see STRATEGY.md for stakes)
  WIND UNDER   outdoor game, kickoff wind forecast >= 15 mph, 1-3 days out, AND a posted
               total with an under price no worse than -115 and positive expected value
               at that line and price under the registered pricing model. Priced at Pinnacle
               it is the registered test (board status "SIGNAL"); priced at the backup
               consensus line it is labelled SECONDARY PRICE and reported separately.
               A wind trigger without a usable price is a WATCH.
  LINE LAG     same gates, plus the kickoff wind forecast rose >= 5 mph since the last
               check while a total present at both checks moved less than half a point.

WATCH (paper-track only; log them, don't bet them yet)
  MODEL LEAN   pre-registered rule: model P(under) >= 55% (or <= 45% for overs).
  EDGE         model vs the de-vigged price >= 5 points.
  COLD VISITOR dome or warm-climate visitor, forecast <= 32F: home side / visitor team-total under.

Every bet alert ends with timing advice (market.timing_note, issue #5): unders now,
overs and underdogs later, favorites now. Log what you actually got with
scripts/log_fill.py so score_forward.py can measure the cost of waiting.

Delivery: macOS notification, plus an iPhone push when NTFY_TOPIC is set in .env.
State lives in data/forward/alert_state.json so nothing is sent twice: each alert is marked sent,
and the file saved, right after it goes out, so a send that fails part way can't repeat the earlier
ones next run. The ledger is saved before the state is read, so a damaged state file can't cost a
ledger row: it is kept beside the new one, the run starts from an empty state, one notice says so, and
the run is still recorded "ok", with a note (a run is "failed" only when a step fails or an alert can't
be built or sent). Every run, finished or failed, leaves one row in data/forward/runs.csv; a failed run
prints the error with any key blanked and exits with status 1. ops/RUN_RECORDS.md explains the records.

    python scripts/alerts.py              # normal run
    python scripts/alerts.py --dry-run    # print what would be sent (nflverse lines; no Odds API credit)
    python scripts/alerts.py --test       # send one test notification
"""
import argparse
import math
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import board, notify, oddsapi, runlog
from nflweather.config import ROOT

sys.path.insert(0, str(ROOT.parent))
from ops.collector_guard import alert_occurrence
from nflweather.features import RAIN_IN, SNOW_IN
from nflweather.market import timing_note


ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--test", action="store_true")
ap.add_argument("--scheduled-occurrence-utc", help="explicit reviewed trigger occurrence, YYYY-MM-DDTHH:MM:00Z; not proof of scheduler provenance")
ap.add_argument("--days", type=int, default=8)
ap.add_argument("--edge", type=float, default=0.05)
args = ap.parse_args()

if args.test:
    ok = notify.send("NFL weather alerts", "Test alert: notifications are working.")
    print("mac notification sent;", "phone push sent" if ok else "no phone push (NTFY_TOPIC not set)")
    sys.exit()

STATE = ROOT / "data" / "forward" / "alert_state.json"
RUNS = ROOT / "data" / "forward" / "runs.csv"
JOB = "nfl-alerts"
outbox = []      # (game's state, key, title, body): alerts built on this run and not yet sent
unsaved = []     # a state write that failed: the alerts still go out, and the run is recorded as failed


def record(status, **kw):
    """One row in runs.csv. A record that can't be written is reported and never stops the alerts."""
    if args.dry_run:
        return
    try:
        runlog.record_run(RUNS, JOB, board.RULES_VERSION, status, **kw)
    except Exception as e:
        print(f"  the run record could not be written: {type(e).__name__}: {runlog.scrub(e)}")


def damaged_notice(kept):
    """The one notice for a run that found alert_state.json damaged. The run itself goes on and is recorded
    "ok"; a notice that can't be sent is reported and never stops the alerts."""
    try:
        notify.send("NFL weather alerts: the alert record was damaged",
                    f"alert_state.json could not be read, so a copy was kept as {kept}. This run's ledger row "
                    f"was saved. The job started over from an empty alert record, so some alerts you have "
                    f"already had may arrive once more. See data/forward/runs.csv.")
    except Exception as e:
        print(f"  the damaged-record notice could not be sent: {type(e).__name__}")


def number(v):
    """A wind or total saved in alert_state.json, or None when it isn't a number (a hand edit): that game
    then has no earlier check to compare with, rather than failing its alerts on every run."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def fire(key, title, body, s):
    """Queue each (game, trigger) once; `key` changes when the trigger escalates. The key is marked sent
    in the game's state `s` only after the alert has gone out (run's send loop)."""
    if key in s.get("sent", []) or any(q is s and k == key for q, k, _, _ in outbox):
        return
    outbox.append((s, key, title, body))


def save_state(state, waiting, seen):
    """Save the alert state (not on a dry run). A game's wind and total from this run (`seen`) are saved
    only once none of its alerts is still `waiting` to go out, so a send that fails can't cost that
    game's LINE LAG on the next run."""
    busy = {id(s) for s, *_ in waiting}
    for s, now_seen in seen:
        if id(s) not in busy:
            s.update(now_seen)
    if not args.dry_run:
        try:
            runlog.write_alert_state(STATE, state)
        except OSError as e:        # a missed alert is worse than a repeated one: keep sending
            unsaved.append(e)


def game_alerts(r, s, game):
    """Every alert this game has earned on this run. `s` is the game's saved state."""
    total = "–" if pd.isna(r.mkt_total) else f"{r.mkt_total:.1f} ({r.line_src})"
    detail = f"{r.conditions}; total {total}; forecast {r.lead_days}d out"
    wet = (r.wx_precip or 0) >= RAIN_IN or (r.wx_snow or 0) >= SNOW_IN
    second = r.rule_b == "SIGNAL_SECONDARY"      # passed Rule B at the backup price, not Pinnacle's

    # RULE B: only a full signal (trigger + horizon + posted line + acceptable price + positive EV) is actionable
    price = "" if pd.isna(r.mkt_under) else f" at {r.mkt_under:+.0f}"
    if r.rule_b in board.SIGNALS:
        storm = " (rain/snow also forecast)" if wet else ""
        shop = (f" Best under at this number: {r.best_under:+.0f} ({r.best_under_book})."
                if pd.notna(r.best_under) and pd.notna(r.mkt_under) and r.best_under > r.mkt_under else "")
        # the highest number is worth naming only when the model prices it above the rule's own quote
        if pd.notna(r.best_line) and r.best_line > r.mkt_total and r.ev_best_line > r.ev_under:
            shop += (f" Best number: under {r.best_line:.1f} at {r.best_line_under:+.0f} ({r.best_line_book}), "
                     f"expected value {100 * r.ev_best_line:+.1f}%.")
        note = (" SECONDARY PRICE: Pinnacle had no quote, so this is the consensus line. It is logged and "
                "reported separately, and it is not part of the registered test.") if second else ""
        fire("ruleb_secondary" if second else "ruleb",
             f"RULE B WIND UNDER{' (secondary price)' if second else ''} {r.mkt_total:.1f}{price}: {game}",
             f"{detail}{storm}. Expected value {100 * r.ev_under:+.1f}% at this line and price.{shop}{note} "
             f"Bet only this number or better; paper-log the price you actually get (scripts/log_fill.py). "
             f"{timing_note('under')}", s)
    elif r.rule_b in ("no_price", "price_too_high", "negative_ev"):
        fire(f"ruleb_{r.rule_b}", f"WATCH wind {r.wx_wind:.0f} mph, no bet ({r.rule_b.replace('_', ' ')}): {game}",
             detail + f"{price}. Rule B needs a posted total, an under price of -115 or better, and positive EV.", s)

    # RULE B: forecast jumped while a posted total sat still (both totals must exist)
    w_prev, t_prev = number(s.get("wind")), number(s.get("total"))
    if (r.rule_b in board.SIGNALS and w_prev is not None and r.wx_wind - w_prev >= 5
            and t_prev is not None and abs(r.mkt_total - t_prev) < 0.5):
        fire(f"lag{round(r.wx_wind)}",
             f"RULE B LINE LAG{' (secondary price)' if second else ''} {r.mkt_total:.1f}{price}: {game}",
             f"Kickoff wind {w_prev:.0f} → {r.wx_wind:.0f} mph since the last check; total still {total}. "
             + ("Secondary price: not part of the registered test. " if second else "")
             + timing_note("under"), s)

    # WATCH: pre-registered model lean and model-vs-market edge
    side = "UNDER" if r.lean.startswith("UNDER") else "OVER" if r.lean.startswith("OVER") else ""
    if side:
        mk = f" vs market {100 * r.p_market:.0f}%" if pd.notna(r.p_market) else ""
        fire(f"lean{side}", f"WATCH model {side.lower()}: {game}",
             f"{detail}; model P(under) {100 * r.p_under:.0f}%{mk}. Paper only (PREREGISTRATION.md). "
             f"{timing_note(side.lower())}", s)
    elif pd.notna(r.edge) and abs(r.edge) >= args.edge:
        fire("edge", f"WATCH edge {100 * r.edge:+.0f} pts: {game}",
             detail + ". Paper only. " + timing_note("under" if r.edge > 0 else "over"), s)

    # WATCH: cold-weather visitor from a dome or a warm week
    warm_vis = (r.v_dome == 1) or (pd.notna(r.v_city_temp7) and r.v_city_temp7 >= 60)
    if pd.notna(r.wx_temp) and r.wx_temp <= 32 and warm_vis and 1 <= r.lead_days <= 3:
        why = "dome team" if r.v_dome == 1 else f"home week {r.v_city_temp7:.0f}°F"
        home = "" if pd.isna(r.spread_line) else "favorite" if r.spread_line > 0 else "underdog"  # > 0: home favored
        fire("coldvis", f"WATCH cold visitor ({why}): {game}",
             detail + f". Home side{f' ({home})' if home else ''} / visitor team-total under. Paper only."
             + (f" {timing_note(home)}" if home else ""), s)


def run(at):
    """One alert run. `at` holds the stage the run has reached and what it has counted so far, so a
    failure anywhere is recorded with both."""
    # a dry run spends no Odds API credits
    occurrence = None if args.dry_run else alert_occurrence(args.scheduled_occurrence_utc)
    up = board.compute(days=args.days, refresh=True, pinnacle=oddsapi.has_key() and not args.dry_run, odds_role="nfl-alert", odds_slot=occurrence)
    now = pd.Timestamp.now(tz="UTC")
    if up.empty:
        return print(f"{now:%Y-%m-%d %H:%M}Z no games in the next {args.days} days")
    at["counts"] = dict(games=len(up), signals=int(up.rule_b.isin(board.SIGNALS).sum()),
                        priced=int(up.mkt_total.notna().sum()), unmapped="; ".join(board.LAST_UNMAPPED),
                        rule_priced=int((up.line_src == board.PRIMARY_SRC).sum()))
    at["stage"] = "saving the ledger"
    if not args.dry_run:
        board.save(up)
    # read after the ledger is saved: a damaged state file is kept aside and can't cost a ledger row
    at["stage"] = "reading the alert state"
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state, at["note"], kept = runlog.read_alert_state(STATE, keep_copy=not args.dry_run)
    if at["note"]:
        print(f"  {runlog.scrub(at['note'])}")
    if kept:        # a damaged state file: tell the owner once (a dry run keeps no copy and sends nothing)
        damaged_notice(kept)
    at["stage"] = "building the alerts"
    kick = pd.to_datetime(up.gameday + " " + up.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    up = up[(kick > now) & (up.wx_src == "era5")]
    problems, seen = [], []
    for r in up.itertuples():
        s = state.setdefault(r.game_id, {})
        game = f"{r.away_team} @ {r.home_team} {r.gameday[5:]} {r.gametime} ET"
        try:        # one game's alert can't cost the others theirs
            game_alerts(r, s, game)
        except Exception as e:
            problems.append(f"{game}: {type(e).__name__}: {e}")
            continue    # its wind and total stay as last saved, so its next LINE LAG isn't lost
        seen.append((s, dict(wind=None if pd.isna(r.wx_wind) else round(float(r.wx_wind), 1),
                             total=None if pd.isna(r.mkt_total) else float(r.mkt_total),
                             seen_utc=now.strftime("%Y-%m-%dT%H:%MZ"))))
    at["stage"] = "sending the alerts"
    save_state(state, outbox, seen)                      # games with nothing to send: saved now, as before
    for i, (s, key, title, body) in enumerate(outbox):
        print(f"ALERT  {title}\n       {body}")
        if not args.dry_run:
            notify.send(title, body)
        s.setdefault("sent", []).append(key)
        save_state(state, outbox[i + 1:], seen)          # saved as sent before the next alert goes out
    if not outbox:
        print(f"{now:%Y-%m-%d %H:%M}Z checked {len(up)} outdoor games, nothing new")
    save_state(state, [], seen)
    if unsaved:     # every alert went out, but which ones is not on disk: some may repeat next run
        at["stage"] = "saving the alert state"
        also = f"; also {len(problems)} game(s) raised: " + " | ".join(problems) if problems else ""
        raise RuntimeError(f"alert_state.json could not be saved ({type(unsaved[-1]).__name__}: {unsaved[-1]}){also}")
    if problems:
        at["stage"] = "building the alerts"
        raise RuntimeError(f"{len(problems)} game(s) raised: " + " | ".join(problems))


at = {"stage": "building the board", "counts": {}, "note": ""}
try:
    run(at)
except BaseException as e:      # log, don't drop: a run that fails at any stage leaves a record and says so
    why = runlog.scrub(f"while {at['stage']}: {type(e).__name__}: {e}")
    record("failed", error="; ".join(filter(None, (why, at["note"]))), **at["counts"])
    if not args.dry_run:
        try:
            notify.send("NFL weather alerts: run failed", f"{why[:300]}. See data/forward/runs.csv.")
        except Exception as e2:
            print(f"  the failure notice could not be sent: {type(e2).__name__}")
    # never the raw exception: its text can hold a key, and alerts.log is pushed to GitHub
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in traceback.extract_tb(e.__traceback__)[::-1][:3])
    print(f"{pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M}Z run failed {why} (at {where})", flush=True)
    sys.exit(1)
record("ok", error=at["note"], **at["counts"])
