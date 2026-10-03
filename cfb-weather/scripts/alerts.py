"""College football alerts for the two pre-registered rules (see STRATEGY.md):

  Rule B   only a full signal is actionable; a 15+ mph wind forecast without a usable
           price arrives as WATCH.
  Rule HT  high-total under, paper only. It is graded at the last quote before kickoff,
           so it alerts only on the last scheduled run before the game
           (board.is_last_run_before: no scheduled run falls between now and kickoff),
           telling you to take the latest number. That run's row is the scored entry
           unless a later manual snapshot is logged.

Mac notification plus the same iPhone ntfy topic as the NFL alerts.
State: data/forward/alert_state.json, so nothing is sent twice: each alert is marked sent, and the
file saved, right after it goes out, so a send that fails part way can't repeat the earlier ones
next run. The ledger is saved before the state is read, so a damaged state file can't cost a ledger
row: it is kept beside the new one, the run starts from an empty state, one notice says so, and the run
is still recorded "ok", with a note (a run is "failed" only when a step fails or an alert can't be built
or sent). Every run, finished or failed, leaves one row in data/forward/runs.csv; a failed run prints the
error with any key blanked and exits with status 1. ops/RUN_RECORDS.md explains the records.

    python scripts/alerts.py [--dry-run | --test]    # --dry-run: ESPN prices only, no Odds API credit
"""
import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cfbweather import board, fetch, notify, runlog
from cfbweather.market import timing_note
from cfbweather.config import ROOT

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--test", action="store_true")
args = ap.parse_args()
if args.test:
    ok = notify.send("CFB weather alerts", "Test alert: notifications are working.")
    sys.exit(print("mac notification sent;", "phone push sent" if ok else "no phone push (NTFY_TOPIC not set)"))

STATE = ROOT / "data" / "forward" / "alert_state.json"
RUNS = ROOT / "data" / "forward" / "runs.csv"
JOB = "cfb-alerts"


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
        notify.send("CFB weather alerts: the alert record was damaged",
                    f"alert_state.json could not be read, so a copy was kept as {kept}. This run's ledger row "
                    f"was saved. The job started over from an empty alert record, so some alerts you have "
                    f"already had may arrive once more. See data/forward/runs.csv.")
    except Exception as e:
        print(f"  the damaged-record notice could not be sent: {type(e).__name__}")


def run(at):
    """One alert run. `at` holds the stage the run has reached and what it has counted so far, so a
    failure anywhere is recorded with both."""
    up = board.compute(prices=not args.dry_run, odds_role="cfb-alert")  # a dry run spends no Odds API credits
    if up.empty:
        return print("no FBS games in the next 8 days")
    at["counts"] = dict(games=len(up), signals=int((up.rule_b == "SIGNAL").sum() + (up.rule_ht == "SIGNAL").sum()),
                        priced=int(up.mkt_total.notna().sum()), unmapped="; ".join(fetch.LAST_UNMAPPED),
                        rule_priced=int(up.line_src.isin(fetch.RULE_BOOKS).sum()))   # Odds API at a rule book
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
    now = pd.Timestamp.now(tz="UTC")
    outbox, problems = [], []       # outbox: (game's state, key, title, body), built and not yet sent
    for r in up.itertuples():
        s = state.setdefault(str(r.game_id), {"sent": []})
        game = f"{r.away_team} @ {r.home_team} {r.kick_et} ET"
        try:        # one game's alert can't cost the others theirs
            for key, title, body in game_alerts(r, game, now):
                if key not in s.setdefault("sent", []) and not any(q is s and k == key for q, k, _, _ in outbox):
                    outbox.append((s, key, title, body))
        except Exception as e:
            problems.append(f"{game}: {type(e).__name__}: {e}")
    at["stage"] = "sending the alerts"
    unsaved = []

    def save():
        """Save the alert state (not on a dry run). A write that fails doesn't stop the sends: a missed
        alert is worse than a repeated one. The run is then recorded as failed."""
        if not args.dry_run:
            try:
                runlog.write_alert_state(STATE, state)
            except OSError as e:
                unsaved.append(e)
    for s, key, title, body in outbox:
        print(f"ALERT  {title}\n       {body}")
        if not args.dry_run:
            notify.send(title, body)
        s["sent"].append(key)
        save()                                      # saved as sent before the next alert goes out
    if not outbox:
        print(f"{pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M}Z checked {len(up)} FBS games, nothing new")
    save()
    if unsaved:     # every alert went out, but which ones is not on disk: some may repeat next run
        at["stage"] = "saving the alert state"
        also = f"; also {len(problems)} game(s) raised: " + " | ".join(problems) if problems else ""
        raise RuntimeError(f"alert_state.json could not be saved ({type(unsaved[-1]).__name__}: {unsaved[-1]}){also}")
    if problems:
        at["stage"] = "building the alerts"
        raise RuntimeError(f"{len(problems)} game(s) raised: " + " | ".join(problems))


def game_alerts(r, game, now):
    """(key, title, body) for each alert this game has earned on this run."""
    out = []
    if r.rule_ht == "SIGNAL" and board.is_last_run_before(r.start_utc, now):
        out.append(("ht", f"CFB HIGH TOTAL UNDER {r.mkt_total:.1f} at {r.mkt_under:+.0f} (paper): {game}",
                    f"Total is at least {r.ht_threshold:.1f} (last season's mean + 10). Rule HT takes the "
                    f"latest number before kickoff; paper only through 2027 (PREREGISTRATION.md). "
                    f"{timing_note('high_total_under')}"))
    if r.rule_b == "SIGNAL":
        shop = (f" Best under at this number: {r.best_under:+.0f} ({r.best_under_book})."
                if pd.notna(r.best_under) and r.best_under > r.mkt_under else "")
        # the highest number is worth naming only when the model prices it above the rule's own quote
        if pd.notna(r.best_line) and r.best_line > r.mkt_total and r.ev_best_line > r.ev_under:
            shop += (f" Best number: under {r.best_line:.1f} at {r.best_line_under:+.0f} ({r.best_line_book}), "
                     f"expected value {100 * r.ev_best_line:+.1f}%.")
        out.append(("ruleb", f"CFB RULE B WIND UNDER {r.mkt_total:.1f} at {r.mkt_under:+.0f}: {game}",
                    f"{r.wx_wind:.0f} mph, {r.wx_temp:.0f}°F forecast {r.lead_days}d out; EV {100 * r.ev_under:+.1f}% "
                    f"at this line ({r.line_src}).{shop} Bet only this number or better; log your fill "
                    f"(scripts/log_fill.py). {timing_note('under')}"))
    elif r.rule_b in ("no_price", "price_too_high", "negative_ev"):
        out.append((f"watch_{r.rule_b}",
                    f"CFB WATCH wind {r.wx_wind:.0f} mph, no bet ({r.rule_b.replace('_', ' ')}): {game}",
                    "Rule B needs a posted total, an under price of -115 or better, and positive EV."))
    return out


at = {"stage": "building the board", "counts": {}, "note": ""}
try:
    run(at)
except BaseException as e:      # log, don't drop: a run that fails at any stage leaves a record and says so
    why = runlog.scrub(f"while {at['stage']}: {type(e).__name__}: {e}")
    record("failed", error="; ".join(filter(None, (why, at["note"]))), **at["counts"])
    if not args.dry_run:
        try:
            notify.send("CFB weather alerts: run failed", f"{why[:300]}. See data/forward/runs.csv.")
        except Exception as e2:
            print(f"  the failure notice could not be sent: {type(e2).__name__}")
    # never the raw exception: its text can hold a key, and alerts.log is pushed to GitHub
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in traceback.extract_tb(e.__traceback__)[::-1][:3])
    print(f"{pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M}Z run failed {why} (at {where})", flush=True)
    sys.exit(1)
record("ok", error=at["note"], **at["counts"])
