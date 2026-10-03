"""What each screen's API returns. Every builder works from one snapshot (data.Store), never raises for
bad data, and says in plain words what it couldn't read."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from . import backtests as backtests_mod
from . import health as health_mod
from . import signals as signals_mod
from . import status_md, words, operations
from .data import JOBS, PROJECTS, SPORT_OF, DEFAULT_RUN_TIMES, Snap, Store, schedule_words
from .ledger import I, RULES, get

UTC = timezone.utc
GAME_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
SPORT_WORDS = {"nfl": "NFL", "cfb": "College football"}
TESTS = [
    {"id": "nfl_rule_b", "project": "nfl-weather", "sport": "nfl", "column": "rule_b",
     "signals": ("SIGNAL", "SIGNAL_SECONDARY"), "decision_ids": ("RULE_B:2026", "RULE_B:2026-27"),
     "scorer_key": "RULE_B", "target": 40},
    {"id": "nfl_lean", "project": "nfl-weather", "sport": "nfl", "column": "lean",
     "signals": ("UNDER lean", "OVER lean"), "decision_ids": ("MODEL_LEAN:2026", "MODEL_LEAN:2026-27"),
     "scorer_key": "MODEL_LEAN", "target": 40},
    {"id": "cfb_rule_b", "project": "cfb-weather", "sport": "cfb", "column": "rule_b", "signals": ("SIGNAL",),
     "decision_ids": ("CFB_RULE_B",), "scorer_key": "RULE_B", "target": 40},
    {"id": "cfb_rule_ht", "project": "cfb-weather", "sport": "cfb", "column": "rule_ht", "signals": ("SIGNAL",),
     "decision_ids": ("CFB_RULE_HT",), "scorer_key": "RULE_HT", "target": None},
]
RULE_NAMES = {"rule_b": "Rule B", "rule_ht": "Rule HT", "lean": "Model lean"}
# Rule B statuses a row reaches only once the wind trigger is met (nflweather/live.py and cfbweather/live.py
# call this set TRIGGERED). Rule B's expected value is priced from the frozen cohort of outdoor games with 15+ mph
# wind, so it means something only on these rows, though the jobs log it on every priced row.
WIND_TRIGGER_MET = ("SIGNAL", "SIGNAL_SECONDARY", "price_too_high", "negative_ev", "no_price", "outside_horizon")
# Of those, the statuses on which the Board and Game screens show the value: a signal, at either price; and
# "negative_ev", where the value (not above zero) is what says why there is no signal. On any other status a
# positive value would read as a priced edge on a game that is not a signal, so a dash is shown and the status
# says why ("Wind trigger, outside the 1 to 3 day window", "Wind trigger, price too high", ...). The value at the
# best number is shown on a signal only: on a "negative_ev" row it can be above zero at another book.
WIND_VALUE_SHOWN = ("SIGNAL", "SIGNAL_SECONDARY", "negative_ev")
WIND_BEST_SHOWN = ("SIGNAL", "SIGNAL_SECONDARY")


class Screen:
    """Collects a screen's payload and anything that couldn't be read for it."""

    def __init__(self, store: Store):
        self.store = store
        self.snap: Snap = store.snapshot()
        self.now: datetime = store.clock()
        self.tz = store.cfg.tz
        self.notes: list[str] = list(self.snap.notes)     # what was read only in part (cut lines, bad rows)

    def when(self, dt):
        return words.when(dt, self.tz, self.now)

    def part(self, what: str, fn, default=None):
        """Build one part of a screen; if it fails, say so and show the rest."""
        try:
            return fn()
        except Exception as e:                            # noqa: BLE001 (never an error page)
            self.notes.append(f"The {what} could not be shown ({type(e).__name__}); the rest of the screen is "
                              "as read.")
            return default

    def header(self, label: str, at: datetime | None) -> dict:
        h = health_mod.assess(self.snap, self.now, self.tz)
        live = self.part("count of live signals", lambda: signals_live(on_board(self.store, self.snap, self.now)), 0)
        return {"last_written": f"{label} {self.when(at)}" if at else f"{label}: nothing recorded yet",
                "last_written_utc": words.iso_z(at), "read_at": f"Read at {words.clock(self.now, self.tz)}",
                "health": h.level, "problems": h.problems, "signals_live": live}

    def done(self, payload: dict) -> dict:
        payload["notes"] = list(dict.fromkeys(self.notes))
        payload["generated_utc"] = words.iso_z(self.now)
        return payload


# ---------------------------------------------------------------- shared pieces

def latest_alert_run(snap: Snap) -> datetime | None:
    best = None
    for p in PROJECTS:
        r = snap.runs.get(p)
        t, _ = health_mod.last_run(r.data[1] if r is not None and r.data else [])
        if t is not None and (best is None or t > best):
            best = t
    if best is None:                                      # no run record: the newest ledger row
        for L in snap.ledgers.values():
            t = words.parse_utc(L.latest_snapshot)
            if t is not None and (best is None or t > best):
                best = t
    return best


def run_times(snap: Snap) -> list[tuple[int, int]]:
    times = set()
    for lbl in ("com.nflweather.alerts", "com.cfbweather.alerts"):
        s = snap.plists.get(lbl)
        if s:
            times.update(s["times"])
    return sorted(times) or DEFAULT_RUN_TIMES


def to_play(L, r, now: datetime) -> bool:
    """Not yet kicked off; a game whose time isn't set, until its date has passed in Eastern time."""
    u = L.until(r)
    return u is not None and u > now


def board_set(snap: Snap, now: datetime) -> list[tuple]:
    """The one set of games that the board lists and that games_on_board, signals_live and leans_live count, so
    the menu-bar light, Home and the board never disagree. For each sport, each as (sport, ledger, row, listed):

    - every game in the latest run that hasn't kicked off (one whose time isn't set: until its date has passed in
      Eastern time), with its row from that run (listed True);
    - every game whose newest row has no kickoff time set, whose date (Eastern) hasn't ended, and which the latest
      run no longer lists, with that newest row (listed False). The college job stops logging such a game at its
      first run after the placeholder kickoff, midnight Eastern, hours before the game is played.

    A game with a time set that the latest run doesn't list is in neither part, whatever its older rows say."""
    out = []
    for sport, L in snap.ledgers.items():
        gid_i = I["game_id"]
        listed = {L.rows[n][gid_i] for n in L.latest_rows}
        for gid, idx in L.by_game.items():
            r = L.rows[idx[-1]]                          # the newest row; for a listed game, the latest run's
            if gid in listed:
                if to_play(L, r, now):
                    out.append((sport, L, r, True))
            elif not L.time_set(r) and to_play(L, r, now):
                out.append((sport, L, r, False))
    return out


def on_board(store: Store, snap: Snap, now: datetime) -> list[tuple]:
    """board_set, worked out once per snapshot and minute (at the minute's start), so that every screen and the
    light asked within the same minute get the same games, whichever asked first."""
    minute = now.replace(second=0, microsecond=0)
    return store.derived(("on_board", snap.built, minute), lambda: board_set(snap, minute))


def signals_live(games: list[tuple]) -> int:
    """Games on the board whose row is a signal under Rule B (either price) or Rule HT. The NFL model lean is a
    watch, as the alert job and runs.csv count it, and is counted apart (leans_live)."""
    return sum(1 for _, L, r, _ in games if L.signal(r))


def leans_live(games: list[tuple]) -> int:
    """NFL games on the board whose row is a model lean (under or over)."""
    return sum(1 for sport, _, r, _ in games
               if sport == "nfl" and get(r, "lean").strip() in ("UNDER lean", "OVER lean"))


def summary(store: Store, snap: Snap | None = None, now: datetime | None = None) -> dict:
    """GET /api/summary: the menu-bar light's contract, exactly these fields."""
    snap = snap or store.snapshot()
    now = now or store.clock()
    tz = store.cfg.tz
    h = health_mod.assess(snap, now, tz)
    nxt = words.next_run(run_times(snap), now, tz)
    q = snap.quota or {}
    credits = q.get("remaining")
    games = on_board(store, snap, now)
    return {
        "generated_utc": words.iso_z(now),
        "health": h.level,
        "signals_live": int(signals_live(games)),
        "games_on_board": len(games),
        "next_run_local": nxt.astimezone(tz).strftime("%H:%M") if nxt else "--:--",
        "credits_remaining": credits if isinstance(credits, int) else None,
        "problems": list(h.problems),
    }


def forecast_words(sport: str, r) -> str:
    src = get(r, "wx_src")
    wind, temp = words.num(get(r, "wx_wind")), words.num(get(r, "wx_temp"))
    if src in ("era5", "forecast") and wind is not None:
        return f"{round(wind)} mph" + (f", {round(temp)}°F" if temp is not None else "")
    return {"indoor": "Indoors", "open_roof": "Open roof", "missing": "No forecast yet", "no_forecast": "No forecast yet",
            "no_venue": "Venue not known", "time_tbd": "Kickoff time not set", "": "Not logged"}.get(
        src, f"Forecast: {src}")


def best_words(r) -> str:
    line, price, bk = get(r, "best_line"), get(r, "best_line_under"), get(r, "best_line_book")
    if words.num(line) is None:
        return ""
    return f"{words.total(line)} at {words.odds(price)}" + (f" ({words.book(bk)})" if bk else "")


def rule_cells(sport: str, r) -> list[dict]:
    out = []
    for rule in RULES[sport]:
        v = get(r, rule)
        out.append({"rule": RULE_NAMES[rule], "value": v,
                    "words": words.status_words(rule, v, get(r, "wx_src"), get(r, "ht_threshold")),
                    "signal": words.is_signal(rule, v), "lean": rule == "lean" and v.strip() in ("UNDER lean",
                                                                                                "OVER lean"),
                    "badge": words.badge(rule, v)})
    return out


def wind_rule_met(r) -> bool:
    """Rule B's wind trigger was met: the row's Rule B status is one the rule reaches only after the wind gate."""
    return get(r, "rule_b").strip() in WIND_TRIGGER_MET


def wind_rule_bar(snap: Snap) -> str:
    """One sentence under the board: whether Rule B clears the project's multiple-testing bar, read from the
    evidence list every time (its Rule B results have "rule-b" in their id), never written into the page."""
    raw = snap.evidence.data
    raw = raw.get("entries", []) if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    results = [e for e in raw if isinstance(e, dict) and "rule-b" in str(e.get("id", ""))
               and e.get("title") and e.get("result")]
    if not results:
        return ("Rule B is not counted as clearing the project’s multiple-testing bar: the evidence list has no Rule B "
                "result that can be read.")
    n, k = len(results), sum(1 for e in results if e.get("clears_bar") is True)
    if not k:
        return (f"Rule B has not cleared the project’s multiple-testing bar: none of its {n:,} results on the "
                "Research screen does.")
    return (f"{k:,} of Rule B’s {n:,} results on the Research screen {'clears' if k == 1 else 'clear'} the project’s "
            "multiple-testing bar; a signal is still a paper entry for the forward test, not a proven bet.")


def lean_model_applies(sport: str, r) -> bool:
    """The NFL lean model's chance of the under means something only for an outdoor NFL game with a forecast (the
    lean rule's own gate, wx_src "era5"); the jobs log p_under on every row."""
    return sport == "nfl" and get(r, "wx_src").strip() == "era5"


def game_row(scr: Screen, sport: str, L, r, listed: bool = True) -> dict:
    """One logged row as the Board and Game screens show it. `listed` is False for a game on the board that the
    latest run no longer lists (its time isn't set; see board_set): its time note says when it was last logged."""
    k = L.kickoff(r)
    timed = L.time_set(r)
    logged = L.logged(r)
    met = wind_rule_met(r)
    b = get(r, "rule_b").strip()
    rules = rule_cells(sport, r)
    return {
        "sport": SPORT_OF[L.project], "sport_key": sport, "game_id": get(r, "game_id"),
        "kickoff": words.kickoff_et(k) if timed or k is None else f"{words.day_label(k, words.EASTERN)}, time not set",
        "kick_day": words.day_label(k, words.EASTERN) if k else "", "time_set": timed,
        "kick_utc": words.iso_z(k) if timed else None, "listed": listed,
        "time_note": ("" if timed or k is None else "Time not set" if listed
                      else f"Time not set. Last logged {scr.when(logged)}."),
        "matchup": f"{get(r, 'away_team')} at {get(r, 'home_team')}", "venue": get(r, "venue"),
        "forecast": forecast_words(sport, r), "wind": words.num(get(r, "wx_wind")),
        "total": words.total(get(r, "total")), "total_num": words.num(get(r, "total")),
        "under": words.odds(get(r, "under")), "over": words.odds(get(r, "over")),
        "source": words.book(get(r, "line_src")) if get(r, "line_src") else "",
        "market_chance": words.pct(get(r, "p_market")),
        # Rule B's expected value, priced as a 15+ mph wind game: only on a signal, or where it is why there is none
        "wind_rule_met": met,
        "wind_value": words.pct(get(r, "ev_under"), signed=True, digits=1) if b in WIND_VALUE_SHOWN else "",
        "wind_value_best": words.pct(get(r, "ev_best_line"), signed=True, digits=1) if b in WIND_BEST_SHOWN else "",
        # the NFL lean model's chance of the under, a different model: outdoor NFL games only
        "lean_chance": words.pct(get(r, "p_under")) if lean_model_applies(sport, r) else "",
        "rules": rules, "signal": L.signal(r), "badge": words.strongest([c["badge"] for c in rules]),
        "best": best_words(r),
        "days": words.days_to(k, scr.now, scr.tz), "lead_days": get(r, "lead_days"),
        "logged": scr.when(logged), "logged_utc": words.iso_z(logged), "rules_version": get(r, "rules_version"),
    }


def tests_content(scr: Screen) -> dict:
    c = scr.snap.tests_content.data
    if isinstance(c, list):
        return {t.get("id"): t for t in c if isinstance(t, dict) and t.get("id")}
    if isinstance(c, dict):
        return {k: v for k, v in c.items() if isinstance(v, dict)}
    return {}


def scorer_counts(doc: dict | None) -> dict:
    """Each test's counts, from the scorer's document: {test id: {signals, settled, pending, void}}."""
    out = {}
    for t in (doc or {}).get("tests", []):
        c = t.get("counts", {})
        if all(isinstance(c.get(k), int) for k in ("signals", "settled", "pending", "void")):
            out[t["id"]] = {k: c[k] for k in ("signals", "settled", "pending", "void")}
    return out


def decisions_for(scr: Screen, test: dict) -> list[dict]:
    r = scr.snap.decisions.get(test["project"])
    rows = r.data[1] if r is not None and r.data else []
    out = []
    for d in rows:
        if (d.get("decision_id") or "").strip() in test["decision_ids"]:
            t = words.parse_utc(d.get("decided_utc", ""))
            verdict = words.strip_markdown(d.get("verdict", "")) or "no verdict written"
            out.append({"id": d.get("decision_id"), "verdict": verdict, "decided": words.when_full(t, scr.tz),
                        "horizon": d.get("horizon", ""), "n_bets": d.get("n_bets", ""),
                        "text": f"Decision recorded: {verdict}, on {words.when_full(t, scr.tz)}, on "
                                f"{d.get('n_bets', '?')} bets ({d.get('horizon', 'horizon not written')})."})
    return out


def ledger_counts(scr: Screen, test: dict, start: datetime | None) -> dict:
    """From the ledger as logged (the scorer decides what counts): games with a kickoff on or after the
    test's start, the games that signalled at least once (in all, and at each signal status), and each
    game's latest status."""
    L = scr.snap.ledgers[test["sport"]]
    col = test["column"]
    games, any_signal, signalled, latest = 0, 0, {v: 0 for v in test["signals"]}, {}
    for idx in L.by_game.values():
        last = L.rows[idx[-1]]
        k = L.kickoff(last)
        if start is not None and (k is None or k < start):
            continue
        games += 1
        seen = {L.rows[n][I[col]] for n in idx}
        any_signal += bool(seen & set(test["signals"]))
        for v in test["signals"]:
            if v in seen:
                signalled[v] += 1
        v = last[I[col]]
        w = words.status_words(col, v, get(last, "wx_src"), get(last, "ht_threshold"))
        latest[w] = latest.get(w, 0) + 1
    by_signal = [{"words": words.status_words(col, v), "games": n} for v, n in signalled.items()]
    return {"games_logged": games, "signals": any_signal, "signals_by_status": by_signal,
            "by_latest_status": [{"words": w, "games": n} for w, n in sorted(latest.items(), key=lambda x: -x[1])]}


def scorer_trouble(project: str, s, then: str = "The counts above are from the ledger.") -> str:
    """What went wrong with a scorer's preview, in plain words ("" when it ran and printed its document)."""
    name = "NFL" if project == "nfl-weather" else "college football"
    return {
        "ok": "",
        "waiting": f"The {name} scorer's read is being prepared; it appears here when it is ready.",
        "missing": (f"The {name} scorer can't be run here: its Python environment "
                    f"({project}/.venv) or its script is missing. {then}"),
        "timed_out": f"The {name} scorer took more than 60 seconds and was stopped. {then}",
        "failed": f"The {name} scorer stopped with an error, so its read is not shown in full. {then}",
        "not_document": (f"The {name} scorer printed something that is not the report the dashboard reads (its "
                         f"--json document), so its read is not shown. {then}"),
        "skipped": (f"The {name} scorer was not started: starting it would create "
                    f"{'this folder' if ',' not in s.error else 'these folders'} ({s.error}), and the dashboard never "
                    f"changes the project folders. {then}"),
    }[s.status]


def scorer_block(scr: Screen, project: str, wait: bool) -> dict:
    s = scr.store.scorer(project, wait=wait)
    return {"project": project, "status": s.status, "words": scorer_trouble(project, s), "text": s.text or "",
            "error": s.error[-1200:] if s.status in ("failed", "not_document") else "",
            "error_label": "What it printed" if s.status == "not_document" else "What it printed as an error",
            "ran": scr.when(s.ran_at) if s.ran_at and s.status != "skipped" else None,
            "counts": scorer_counts(s.doc) if s.status == "ok" else {}}


def forward_tests(scr: Screen, wait: bool) -> list[dict]:
    content = tests_content(scr)
    if not content:
        scr.notes.append("The descriptions of the forward tests (dashboard/content/forward_tests.json) could not be "
                         "read; the counts are shown without them.")
    blocks = {p: scorer_block(scr, p, wait) for p in PROJECTS}
    out = []
    for t in TESTS:
        c = content.get(t["id"], {})
        start = words.parse_utc(c.get("starts_utc", ""))
        started = start is not None and scr.now >= start
        counts = scr.part(f"ledger counts for {c.get('name', t['id'])}", 
                          lambda t=t, start=start: ledger_counts(scr, t, start), {})
        sc = blocks[t["project"]]
        sk = sc["counts"].get(t["scorer_key"])
        target = t["target"]
        logged = words.count((counts or {}).get("signals", 0), "signal")
        if not started:
            progress = f"Starts {c.get('starts_text', 'on a date not written in the content file')}"
            detail = "Not started yet. Games before the start don't count."
        elif sk is not None:                              # only from a scorer that finished (scorer_block)
            progress = (f"{sk['settled']} of {target} settled" if target else f"{sk['settled']} settled") + (
                f", {sk['pending']} waiting for a result" if sk["pending"] else "")
            detail = (f"{sk['signals']} signals, {sk['settled']} settled, {sk['pending']} waiting for a result, "
                      f"{sk['void']} void (the scorer's count)")
        elif sc["status"] in ("failed", "timed_out", "missing", "skipped", "not_document"):
            why = {"failed": "stopped with an error", "timed_out": "took too long and was stopped",
                   "missing": "can't be run here", "skipped": "was not started",
                   "not_document": "printed something the dashboard can't read"}[sc["status"]]
            progress = f"The scorer {why}; {logged} logged (from the ledger)"
            detail = progress
        else:
            progress = f"{logged} logged; the settled count comes from the scorer"
            detail = progress
        decisions = decisions_for(scr, t)
        gate = c.get("money_gate", "not chosen")
        out.append({"id": t["id"], "project": t["project"], "sport": SPORT_OF[t["project"]],
                    "name": c.get("name", t["id"]), "rule": c.get("rule", ""), "starts": c.get("starts_text", ""),
                    "decided": c.get("decided_text", ""), "started": started, "progress": progress,
                    "progress_detail": detail, "money_gate_value": gate,
                    "target": target, "money_gate": f"Money gate: {gate}",
                    "decisions": decisions, "counts": counts, "scorer_counts": sk,
                    "note": c.get("note", "")})
    return out, blocks


def jobs(scr: Screen) -> list[dict]:
    snap = scr.snap
    out = []
    lc = snap.launchctl
    newest_close = None
    for p in PROJECTS:
        r = snap.closes.get(p)
        for row in (r.data[1] if r is not None and r.data else []):
            t = words.parse_utc(row.get("capture_utc", ""))
            if t is not None and (newest_close is None or t > newest_close):
                newest_close = t
    for job in JOBS:
        lbl = job["label"]
        listed = None if lc.listed is None else lc.listed.get(lbl)
        printed = lc.printed.get(lbl, {})
        status = listed.get("status") if listed else None
        loaded = None if lc.listed is None else listed is not None
        level = "ok"
        if loaded is False:
            level, exit_words = "warn", "Not loaded in launchd"
        elif loaded is None:
            level, exit_words = "warn", "Could not ask launchd"
        elif status is None:
            exit_words = "No exit recorded yet" if "never" in printed.get("last exit code", "never") else "Fine"
        elif status == 0:
            exit_words = "Last exit 0 (fine)"
        else:
            level, exit_words = "fail", f"Last exit {status} (an error)"
        running = bool(listed and listed.get("pid"))
        last_run, result = None, exit_words
        if "project" in job:
            rr = snap.runs.get(job["project"])
            t, row = health_mod.last_run(rr.data[1] if rr is not None and rr.data else [])
            last_run = t
            if row is not None:
                if (row.get("status") or "").lower() == "failed":
                    result, level = f"Failed ({health_mod.step_of(row.get('error', ''))})", "fail"
                else:
                    result = (f"OK: {row.get('games', '?')} games, {row.get('signals', '?')} signals"
                              + ("" if level == "ok" else f"; {exit_words.lower()}"))
                if words.working_hours_between(t, scr.now, scr.tz) > health_mod.STALE_HOURS:
                    level = "fail"
                    result += "; no run for more than 5 hours of the working day"
            else:
                level = "warn" if level == "ok" else level
                result = "No run recorded"
        else:
            lg = snap.logs.get(lbl) or {}
            mt = lg.get("mtime")
            last_run = datetime.fromtimestamp(mt, UTC) if mt else None
            line = (lg.get("last_line") or "").strip().lower()
            if lbl.endswith("closecapture"):
                result = (f"Last close captured {scr.when(newest_close)}" if newest_close else "No close captured yet")
            elif line.endswith("ledgers pushed"):
                result = "Copied the records to the ledgers branch"
            elif line.endswith("ledgers unchanged"):
                result = "Nothing new to copy"
            if level != "ok":
                result = f"{exit_words}. {result}"
        if job.get("collector"):
            stamp = snap.operations.get("collector_outputs", {}).get(lbl)
            output_at = datetime.fromtimestamp(stamp, UTC) if stamp else None
            output_words = scr.when(output_at) if output_at else "Not verified"
            start = snap.operations.get("nba_start") if lbl.endswith("nbacollector") else None
            future_start = bool(start and scr.now.astimezone(scr.tz).date().isoformat() < start)
            process = "Running" if running else "Loaded; idle" if loaded else "Not loaded" if loaded is False else "Unknown"
            result = process + ". " + (exit_words + ". " if loaded else "")
            if future_start:
                result += "Collection starts " + start + "; no collections expected yet. "
            result += "Last output file update: " + output_words + ". Collection success is unverified; process status alone does not prove data arrived."
            # Output can be legitimately quiet without a trigger/slot. Do not invent freshness deadlines.
            if level == "ok" and not future_start:
                level = "warn"  # no successful-collection receipt contract exists for these jobs yet
            if future_start and loaded is True and status in (None, 0):
                level = "ok"
        out.append({"label": lbl, "name": job["name"], "schedule": schedule_words(snap.plists.get(lbl)),
                    "loaded": loaded, "running": running, "state": printed.get("state", ""),
                    "runs_since_load": printed.get("runs", ""), "exit_status": status,
                    "exit_words": exit_words, "last_run": scr.when(last_run) if last_run else "Not recorded",
                    "last_run_label": "Last run" if "project" in job else "Last wrote to its log",
                    "last_run_note": ("from its run record" if "project" in job else
                                      "when it last wrote to its log" if last_run else ""),
                    "result": result, "level": level,
                    "log_line": (snap.logs.get(lbl) or {}).get("last_line", "")})
    return out


def bar_sentence(clears: bool, bar) -> str:
    """Whether a result clears the bar it was measured against, and that bar, as one plain sentence. The bar is
    written as it was when measured (it may have parentheses of its own, so it follows a colon)."""
    b = " ".join(str(bar or "").split()).rstrip(".")
    if not b or b.lower().startswith("not stated"):
        return ("No multiple-testing bar was stated in the source, so it is "
                + ("counted as clearing one." if clears else "not counted as clearing one."))
    if b.lower().startswith("not a betting test"):
        return words.cap(b) + "."
    return (f"{'Clears' if clears else 'Does not clear'} the multiple-testing bar in force when it was measured: "
            f"{b}.")


def evidence_stamp(entries: list[dict]) -> str:
    """The Research screen's stamp: the date of the newest entry (the file's own time is only when git wrote it)."""
    dates = []
    for e in entries:
        try:
            dates.append(date.fromisoformat(e["date"]))
        except (TypeError, ValueError):
            continue
    if not dates:
        return "No entry in the evidence list is dated"
    d = max(dates)
    return f"Newest entry dated {d:%a} {d:%b} {d.day}, {d.year}"


def evidence(scr: Screen) -> tuple[list[dict], int | None, str | None]:
    raw = scr.snap.evidence.data
    entries = []
    if isinstance(raw, dict):
        raw = raw.get("entries", [])
    if not isinstance(raw, list):
        raw = []
    skipped = 0
    for e in raw:
        if not isinstance(e, dict) or not e.get("title") or not e.get("result"):
            skipped += 1
            continue
        n = e.get("n")
        clears = e.get("clears_bar") is True
        entries.append({
            "id": str(e.get("id", "")), "title": str(e["title"]), "sport": str(e.get("sport", "")),
            "result": str(e["result"]), "record": str(e.get("record") or ""),
            "win_rate": (f"{e['win_rate']:.1f}%" if isinstance(e.get("win_rate"), (int, float))
                         else str(e.get("win_rate") or "")),
            "n": (f"{n:,}" if isinstance(n, int) else str(n) if n else ""),
            "n_words": (f"n = {n:,}" if isinstance(n, int) else str(n) if n else "Sample size not given in the source"),
            "p_value": ("" if e.get("p_value") in (None, "") else f"p = {e['p_value']}" if isinstance(
                e.get("p_value"), (int, float)) else f"p {e['p_value']}" if str(e["p_value"])[:1] in "<>=≈"
                else f"p = {e['p_value']}"),
            "clears_bar": clears,
            "bar_words": ("Clears the multiple-testing bar" if clears else "Does not clear the multiple-testing bar"),
            "bar_sentence": bar_sentence(clears, e.get("bar")),
            "bar": str(e.get("bar") or ""), "kind": str(e.get("kind") or ""), "note": str(e.get("note") or ""),
            "source": str(e.get("source") or ""), "date": str(e.get("date") or ""),
        })
    if skipped:
        scr.notes.append(f"{skipped} entr{'ies' if skipped != 1 else 'y'} in the evidence list could not be read "
                         "(each needs at least a title and a result).")
    n = status_md.variants(scr.snap.status_text or "") if scr.snap.status_text else None
    if n is None:
        scr.notes.append("The running count of variants could not be read from STATUS.md's “Variants” "
                         "bullet.")
    return entries, n, status_md.bar(n)


LIVE_RULE_WORDS = {"rule_b": "Wind rule (Rule B)", "rule_ht": "High-total rule (Rule HT)"}


def better_number(r) -> str:
    """The best number any book offers, when it is better for the under than the rule's own quote: a higher total,
    or the same total at a better price. "" when it isn't better, or wasn't logged."""
    line, price = words.num(get(r, "total")), words.num(get(r, "under"))
    bl, bp, bb = words.num(get(r, "best_line")), words.num(get(r, "best_line_under")), get(r, "best_line_book")
    if line is not None and bl is not None and (bl > line or (bl == line and bp is not None and price is not None
                                                              and bp > price)):
        return f"Better at {words.book(bb) or 'another book'}: under {bl:.1f} at {words.odds(bp)}"
    bu, bub = words.num(get(r, "best_under")), get(r, "best_under_book")
    if line is not None and bu is not None and price is not None and bu > price:
        return f"Better at {words.book(bub) or 'another book'}: under {line:.1f} at {words.odds(bu)}"
    return ""


def live_signals(scr: Screen) -> list[dict]:
    """Each signal live on the board (a game still to kick off whose newest row is a signal), one per rule: what to
    take, the better number if a book offers one, and how long until kickoff. The same games the light counts."""
    out = []
    for sport, L, r, listed in on_board(scr.store, scr.snap, scr.now):
        for rule in RULES[sport]:
            if not words.is_signal(rule, get(r, rule)):
                continue
            k, timed = L.kickoff(r), L.time_set(r)
            src = words.book(get(r, "line_src")) if get(r, "line_src") else ""
            take = (f"Under {words.total(get(r, 'total'))} at {words.odds(get(r, 'under'))}" + (f", {src}" if src else "")
                    if words.num(get(r, "total")) is not None else "No number logged")
            out.append({"badge": words.badge(rule, get(r, rule)), "sport": SPORT_OF[L.project], "sport_key": sport,
                        "game_id": get(r, "game_id"), "matchup": f"{get(r, 'away_team')} at {get(r, 'home_team')}",
                        "kickoff": words.kickoff_et(k) if timed or k is None
                        else f"{words.day_label(k, words.EASTERN)}, time not set",
                        "rule": LIVE_RULE_WORDS[rule], "take": take, "better": better_number(r),
                        "until": words.until(k, scr.now) if timed else "Kickoff time not set",
                        "_sort": (L.until(r) or scr.now, get(r, "game_id"), rule)})
    out.sort(key=lambda x: x.pop("_sort"))
    return out


# ---------------------------------------------------------------- the screens

def source_freshness(scr):
    op = scr.snap.operations
    out = [x for x in (op.get("freshness"), op.get("plan_freshness"), op.get("action_freshness")) if x]
    for project in PROJECTS:
        r = scr.snap.runs.get(project)
        at, _ = health_mod.last_run(r.data[1] if r and r.data else [])
        out.append(operations.freshness(("NFL" if project == "nfl-weather" else "College football") + " alert records", at, scr.now, scr.tz, 24))
    q = scr.snap.quota or {}
    out.append(operations.freshness("Credit balance", words.parse_utc(q.get("utc", "")), scr.now, scr.tz, 24))
    ev = scr.snap.evidence.data
    dates = [words.parse_utc(str(x.get("date", "")) + "T00:00:00Z") for x in ev if isinstance(x, dict)] if isinstance(ev, list) else []
    out.append(operations.freshness("Research evidence", max((x for x in dates if x), default=None), scr.now, scr.tz, 168, "Newest evidence date"))
    return out


def home(store: Store) -> dict:
    scr = Screen(store)
    s = summary(store, scr.snap, scr.now)                 # the same snapshot, minute and games as the rest
    at = latest_alert_run(scr.snap)
    tests, _ = scr.part("forward tests", lambda: forward_tests(scr, wait=False), ([], {}))
    job_list = scr.part("scheduled jobs", lambda: jobs(scr), [])
    op = scr.snap.operations
    waiting = op.get("actions", [])
    if op.get("unclassified_actions"):
        scr.notes.append("Unclassified owner items remain visible with “Status needs review”; the hub should confirm their current disposition.")
    ev, n, bar = scr.part("evidence list", lambda: evidence(scr), ([], None, None))
    ev_sorted = sorted((e for e in ev if e["kind"] != "pending"), key=lambda e: e["date"], reverse=True)
    q = scr.snap.quota or {}
    nxt = words.next_run(run_times(scr.snap), scr.now, scr.tz)
    live = scr.part("live signals", lambda: live_signals(scr), [])
    return scr.done({
        "header": scr.header("Last run", at),
        "live": live,
        "live_note": "A signal is the rule firing on a pre-registered paper test. It is not a proven edge.",
        "live_none": "No signal is live." + (
            f" The next run is at {words.clock(nxt, scr.tz)}"
            f"{' today' if nxt.astimezone(scr.tz).date() == scr.now.astimezone(scr.tz).date() else ' tomorrow'}."
            if nxt else ""),
        "numbers": {
            "signals_live": s["signals_live"], "games_on_board": s["games_on_board"],
            "leans_live": scr.part("model leans", lambda: leans_live(on_board(store, scr.snap, scr.now)), 0),
            "next_run": words.clock(nxt, scr.tz) if nxt else "Not known",
            "next_run_day": ("today" if nxt and nxt.astimezone(scr.tz).date() == scr.now.astimezone(scr.tz).date()
                             else "tomorrow" if nxt else ""),
            "credits": s["credits_remaining"],
            "credits_read": scr.when(words.parse_utc(q.get("utc", ""))) if q.get("utc") else None,
        },
        "tests": tests, "jobs": job_list, "waiting": waiting, "evidence": ev_sorted[:3],
        "operations": op, "sources": source_freshness(scr),
        "evidence_total": len(ev), "variants": n, "bar": bar,
    })


def board_rows(scr: Screen) -> tuple[list[dict], list[str]]:
    """The board's rows (the games of on_board, the set the light counts), signals first, and what couldn't be
    shown."""
    rows, before = [], len(scr.notes)
    for sport, L, r, listed in on_board(scr.store, scr.snap, scr.now):
        g = scr.part("a game row", lambda sport=sport, L=L, r=r, listed=listed: game_row(scr, sport, L, r, listed))
        if g:
            rows.append((L.until(r), g))              # a game with no time set comes after its date's timed games
    rows.sort(key=lambda x: (not x[1]["signal"], x[0], x[1]["matchup"]))
    return [g for _, g in rows], scr.notes[before:]


def board(store: Store) -> dict:
    scr = Screen(store)
    for L in scr.snap.ledgers.values():
        if not L.readable:
            scr.notes.append(words.cap(L.note) or f"{words.cap(L.csv.label)} could not be read.")
    # worked out once a minute from each snapshot: a refresh, a second tab or the light reuses it
    minute = scr.now.replace(second=0, microsecond=0)
    rows, row_notes = store.derived(("board", scr.snap.built, minute), lambda: board_rows(scr))
    scr.notes.extend(n for n in row_notes if n not in scr.notes)
    runs = {}
    for sport, L in scr.snap.ledgers.items():
        t = words.parse_utc(L.latest_snapshot)
        runs[sport] = {"sport": SPORT_WORDS[sport], "latest_run": scr.when(t) if t else "No run logged",
                       "games": sum(1 for g in rows if g["sport_key"] == sport)}
    newest = max((words.parse_utc(L.latest_snapshot) for L in scr.snap.ledgers.values()
                  if words.parse_utc(L.latest_snapshot)), default=None)
    return scr.done({"header": scr.header("Last run", newest), "games": rows, "runs": runs,
                     "signals": sum(1 for g in rows if g["signal"]), "wind_rule_bar": wind_rule_bar(scr.snap)})


def game(store: Store, game_id: str) -> tuple[int, dict]:
    scr = Screen(store)
    if not isinstance(game_id, str) or not GAME_ID.match(game_id):
        return 400, scr.done({"error": "That isn't a game id the dashboard can look up. Open a game from the board.",
                              "header": scr.header("Last run", latest_alert_run(scr.snap))})
    found = None
    for sport, L in scr.snap.ledgers.items():
        if game_id in L.by_game:
            found = (sport, L)
            break
    if found is None:
        return 404, scr.done({"error": "No game with that id is in either ledger.",
                              "header": scr.header("Last run", latest_alert_run(scr.snap))})
    sport, L = found
    project = L.project
    rows = [game_row(scr, sport, L, r) for r in L.game_rows(game_id)]
    last = rows[-1]
    charts = {"total": [[g["logged_utc"], g["total_num"], g["logged"]] for g in rows if g["total_num"] is not None],
              "wind": [[g["logged_utc"], g["wind"], g["logged"]] for g in rows if g["wind"] is not None]}
    closes = scr.part("closing lines", lambda: game_closes(scr, project, game_id), [])
    alerts = scr.part("alerts", lambda: game_alerts(scr, project, L, game_id, last), {})
    fills = scr.part("paper fills", lambda: game_fills(scr, project, game_id), [])
    head = {k: last[k] for k in ("game_id", "kickoff", "matchup", "venue")}
    head["sport"] = SPORT_WORDS[sport]                    # in the header line, in words: "College football"
    newest = L.game_rows(game_id)[-1]
    head["badge"] = last["badge"]                         # the newest row's: a signal, a backup-price signal, a watch
    head["badge_words"] = ("" if not last["badge"] else
                           "The newest row is a watch, not a bet." if last["badge"] == "watch" else
                           "The newest row is a signal." + ("" if to_play(L, newest, scr.now) else
                                                           " The game has kicked off."))
    return 200, scr.done({"header": scr.header("Last logged", words.parse_utc(last["logged_utc"])), "game": head,
                          "rows": rows, "charts": charts, "closes": closes, "alerts": alerts, "fills": fills,
                          "wind_rule_bar": wind_rule_bar(scr.snap)})


def game_closes(scr: Screen, project: str, game_id: str) -> list[dict]:
    r = scr.snap.closes.get(project)
    out = []
    for row in (r.data[1] if r is not None and r.data else []):
        if (row.get("game_id") or "").strip() == game_id:
            t = words.parse_utc(row.get("capture_utc", ""))
            out.append({"captured": scr.when(t), "book": words.book(row.get("book") or row.get("line_src") or ""),
                        "total": words.total(row.get("close_total")), "under": words.odds(row.get("close_under")),
                        "over": words.odds(row.get("close_over"))})
    return out


def game_fills(scr: Screen, project: str, game_id: str) -> list[dict]:
    r = scr.snap.fills.get(project)
    out = []
    for row in (r.data[1] if r is not None and r.data else []):
        if (row.get("game_id") or "").strip() == game_id:
            t = words.parse_utc(row.get("fill_utc", ""))
            out.append({"when": scr.when(t), "rule": RULE_NAMES.get(row.get("rule", ""), row.get("rule", "")),
                        "line": words.total(row.get("line")), "price": words.odds(row.get("price")),
                        "book": words.book(row.get("book", ""))})
    return out


FIRST_SEEN = {"ruleb": ("rule_b", "SIGNAL"), "ruleb_secondary": ("rule_b", "SIGNAL_SECONDARY"),
              "leanUNDER": ("lean", "UNDER lean"), "leanOVER": ("lean", "OVER lean"), "ht": ("rule_ht", "SIGNAL")}


def game_alerts(scr: Screen, project: str, L, game_id: str, last: dict) -> dict:
    st = scr.snap.alert_state.get(project)
    state = st.data.get(game_id) if st is not None and isinstance(st.data, dict) else None
    sent = state.get("sent", []) if isinstance(state, dict) and isinstance(state.get("sent", []), list) else []
    rows = L.game_rows(game_id)
    items = []
    for key in sent:
        key = str(key)
        col_val = FIRST_SEEN.get(key)
        if col_val is None and (key.startswith("ruleb_") or key.startswith("watch_")):
            col_val = ("rule_b", key.split("_", 1)[1])
        first = next((L.logged(r) for r in rows if col_val and r[I[col_val[0]]] == col_val[1]), None)
        items.append({"words": words.alert_words(key),
                      "first_seen": (f"First logged on the run of {words.when_full(first, scr.tz)}" if first
                                     else "")})
    log = scr.snap.alerts_log.get(project)
    lines = []
    if log is not None and log.data:
        needle = last["matchup"].replace(" at ", " @ ") + " "
        text = log.data.splitlines()
        for i, ln in enumerate(text):
            if ln.startswith("ALERT") and needle in ln:
                lines.append(words.scrub(ln))
                if i + 1 < len(text) and text[i + 1].startswith("       "):
                    lines.append(words.scrub(text[i + 1]))
    return {"sent": items, "log_lines": lines[-40:],
            "none": not items and not lines,
            "note": ("" if st is not None and st.data is not None else
                     "The alert record could not be read, so the alerts sent are not known.")}


def tests_screen(store: Store) -> dict:
    scr = Screen(store)
    tests, blocks = scr.part("forward tests", lambda: forward_tests(scr, wait=True), ([], {}))
    _, n, bar = scr.part("variant count", lambda: evidence(scr), ([], None, None))
    groups = []
    for p in PROJECTS:
        groups.append({"project": p, "sport": "NFL" if p == "nfl-weather" else "College football",
                       "tests": [t for t in tests if t["project"] == p], "scorer": blocks.get(p)})
    newest = max((words.parse_utc(L.latest_snapshot) for L in scr.snap.ledgers.values()
                  if words.parse_utc(L.latest_snapshot)), default=None)
    return scr.done({"header": scr.header("Last run", newest), "groups": groups, "variants": n, "bar": bar})


def signals_screen(store: Store) -> dict:
    """The Signals screen: every bet the scorers count (signals.py). The server runs both scorers first, outside its
    lock; here they are only read (a preview is kept for 10 minutes)."""
    scr = Screen(store)
    scored = {p: store.scorer(p, wait=True) for p in PROJECTS}
    docs = {p: s.doc if s.status == "ok" else None for p, s in scored.items()}
    then = signals_mod.LISTED                             # or NONE_LISTED, when that ledger has none (signals.build)
    trouble = {p: scorer_trouble(p, s, then) for p, s in scored.items()}
    content = tests_content(scr)
    if not content:
        scr.notes.append("The descriptions of the forward tests (dashboard/content/forward_tests.json) could not be "
                         "read, so the dates the tests start are not shown.")
    games = scr.part("board", lambda: on_board(store, scr.snap, scr.now), [])
    payload = scr.part("log of signals", lambda: signals_mod.build(scr, docs, trouble, content, games), None) or {
        "rules": [], "together": {}, "bets": [], "fallback": [], "empty": None, "paper": signals_mod.PAPER,
        "trouble": [w for w in trouble.values() if w]}
    ran = [s.ran_at for s in scored.values() if s.ran_at and s.status != "skipped"]
    header = scr.header("Scored", max(ran) if ran else None)
    header["last_written"] = (f"Scored as a preview at {scr.when(max(ran))}" if ran else "Not scored yet")
    return scr.done({"header": header, **payload})


def jobs_screen(store: Store) -> dict:
    scr = Screen(store)
    runs = {}
    for p in PROJECTS:
        r = scr.snap.runs.get(p)
        rows = r.data[1] if r is not None and r.data else []
        out = []
        for row in rows[-50:][::-1]:
            t = words.parse_utc(row.get("run_utc", ""))
            failed = (row.get("status") or "").strip().lower() == "failed"
            err = words.scrub(row.get("error", "") or "")
            out.append({"when": words.when_full(t, scr.tz), "result": "Failed" if failed else
                        ("OK" if (row.get("status") or "").strip().lower() == "ok" else row.get("status") or "?"),
                        "failed": failed, "games": row.get("games", ""), "signals": row.get("signals", ""),
                        "priced": row.get("priced", ""), "rule_priced": row.get("rule_priced", ""),
                        "unmapped": row.get("unmapped", ""), "rules_version": row.get("rules_version", ""),
                        "error": err[:300]})
        runs[p] = {"sport": "NFL" if p == "nfl-weather" else "College football", "rows": out,
                   "total": len(rows), "note": "" if r is not None and r.data else words.cap(r.note if r else "")}
    q = scr.snap.quota
    credits = None
    if q is not None:
        t = words.parse_utc(q.get("utc", "") or "")
        rem, used = q.get("remaining"), q.get("used")
        plan = rem + used if isinstance(rem, int) and isinstance(used, int) else None
        old = t is not None and (t.year, t.month) != (scr.now.year, scr.now.month)
        credits = {"remaining": rem, "used": used, "plan": plan, "read": words.when_full(t, scr.tz),
                   "text": (f"{rem:,} credits left" if isinstance(rem, int) else "Balance not known")
                   + (f" of {plan:,} this month" if plan else "") + (f", as the Odds API reported it on "
                                                                     f"{words.when_full(t, scr.tz)}" if t else ""),
                   "stale": ("That reading is from an earlier month; the allowance has reset since." if old else ""),
                   "plan_words": ("Free plan" if isinstance(rem, int) and rem < health_mod.FREE_PLAN_BELOW and
                                  (plan or 0) <= 1000 else "Paid plan" if plan else "")}
    closes = scr.part("closing lines", lambda: recent_closes(scr), [])
    return scr.done({"header": scr.header("Last run", latest_alert_run(scr.snap)), "runs": runs,
                     "jobs": scr.part("scheduled jobs", lambda: jobs(scr), []), "credits": credits,
                     "credits_note": scr.snap.quota_note, "closes": closes,
                     "launchctl_note": scr.snap.launchctl.note})


def recent_closes(scr: Screen) -> list[dict]:
    since = scr.now - timedelta(days=7)
    games: dict = {}
    for p in PROJECTS:
        r = scr.snap.closes.get(p)
        for row in (r.data[1] if r is not None and r.data else []):
            t = words.parse_utc(row.get("capture_utc", ""))
            if t is None or t < since:
                continue
            key = (p, row.get("game_id", ""), row.get("kick_utc") or row.get("start_utc") or "")
            g = games.setdefault(key, {"sport": SPORT_OF[p], "game_id": row.get("game_id", ""),
                                       "matchup": f"{row.get('away_team', '?')} at {row.get('home_team', '?')}",
                                       "kickoff": words.kickoff_et(words.parse_utc(key[2])), "captured_utc": t,
                                       "books": 0, "lines": []})
            g["captured_utc"] = max(g["captured_utc"], t)
            if words.num(row.get("close_total")) is not None:
                g["books"] += 1
                bk = row.get("book") or row.get("line_src") or ""
                g["lines"].append({"book": words.book(bk), "rule_book": bk in ("pinnacle", "draftkings"),
                                   "text": f"{words.total(row.get('close_total'))}, under "
                                           f"{words.odds(row.get('close_under'))}"})
    out = []
    for g in sorted(games.values(), key=lambda g: g["captured_utc"], reverse=True):
        main = next((ln for ln in g["lines"] if ln["book"] == "Pinnacle"), None) or next(
            (ln for ln in g["lines"] if ln["rule_book"]), None) or (g["lines"][0] if g["lines"] else None)
        out.append({"sport": g["sport"], "matchup": g["matchup"], "kickoff": g["kickoff"],
                    "captured": scr.when(g["captured_utc"]), "books": g["books"],
                    "line": f"{main['text']} ({main['book']})" if main else "No price captured"})
    return out


def run_records(store: Store) -> dict:
    from .readers import read_text
    scr = Screen(store)
    r = read_text(store.cfg.root / "ops" / "RUN_RECORDS.md", "the guide to the run records (ops/RUN_RECORDS.md)")
    if r.data is None:
        scr.notes.append(words.cap(r.note))
    return scr.done({"header": scr.header("Last run", latest_alert_run(scr.snap)),
                     "text": words.scrub(r.data or "")})


def pull(store: Store) -> dict:
    scr = Screen(store)
    recorded = words.parse_utc(scr.snap.operations.get("freshness", {}).get("utc", ""))
    m = scr.snap.manifest
    if scr.snap.manifest_note:
        scr.notes.append(scr.snap.manifest_note)
    if not m or not m["pulls"]:
        return scr.done({"header": scr.header("Last acquisition record", recorded), "started": False,
                         "text": "No entries in the legacy request log. This does not mean downloads have not started.", "pulls": [],
                         "operations": scr.snap.operations, "sources": source_freshness(scr),
                         "total": None})
    pulls = sorted(m["pulls"], key=lambda p: (p["pull"] == "account", p["pull"]))
    for p in pulls:
        p["name"] = "Key checks (free)" if p["pull"] == "account" else p["pull"]
    total = {"requests": sum(p["requests"] for p in pulls), "billed": sum(p["billed"] for p in pulls),
             "upper": sum(p["upper"] for p in pulls), "unreadable": sum(p["unreadable"] for p in pulls),
             "lowest": min((p["lowest"] for p in pulls if p["lowest"] is not None), default=None)}
    return scr.done({"header": scr.header("Last acquisition record", recorded or words.parse_utc(m["last_logged"])), "started": True,
                     "text": "", "pulls": pulls, "total": total,
                     "operations": scr.snap.operations, "sources": source_freshness(scr)})


def research(store: Store) -> dict:
    scr = Screen(store)
    ev, n, bar = scr.part("evidence list", lambda: evidence(scr), ([], None, None))
    if scr.snap.evidence.data is None:
        scr.notes.append(words.cap(scr.snap.evidence.note))
    header = scr.header("Newest entry", None)
    header["last_written"], header["last_written_utc"] = evidence_stamp(ev), None
    return scr.done({"header": header, "entries": ev, "variants": n, "bar": bar})


def backtests(store: Store) -> dict:
    """The Backtests screen: the research as charts, from the prepared chart files (vfdash/backtests.py)."""
    scr = Screen(store)
    payload = scr.part("charts", lambda: backtests_mod.build(scr), None) or {
        "intro": [], "groups": [], "variants": None, "bar": None, "newest": None}
    header = scr.header("Newest table", None)
    header["last_written"] = (f"Charts from tables dated up to {payload['newest']}" if payload.get("newest")
                              else "No chart file could be read")
    header["last_written_utc"] = None
    return scr.done({"header": header, **payload})
