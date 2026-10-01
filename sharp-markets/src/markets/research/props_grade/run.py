"""`uv run markets props-grade`: the registered props test (#10) on F3, graded by nfl-weather/PREREGISTRATION_PROPS.md.

Today, before F3a exists, it prints that there is nothing to grade and stops (exit 0). `--fixture` runs the whole
grader on a small synthetic fixture instead (nothing in it is data). Once F3a is pulled (docs/ODDS5M_DAY_ONE.md,
step 5), the steps are:

  1. `uv run markets props-grade`
     Outcome-blind. Reads F3's cached answers (sealed calls never read), prints what loaded (a partial F3a is
     flagged on its own), each primary market's coverage at F3a's close and the book the rule of 2.4 picks, and the
     prop names that don't match the committed roster (names and counts; the roster and the team table are the only
     other files read). Then it stops: no outcome or schedule table is read. The hub records the book in a dated
     entry in section 8 of the registration ("the book is DraftKings", with the date and the two coverage figures)
     and commits it.
  2. `uv run markets props-grade --book-recorded draftkings` (or pinnacle)
     Refused unless the book named is the one the rule picks, a dated entry in section 8 records that same book,
     and both the registration and the roster (config/props/nfl_rosters_2023_2025.csv) are committed unchanged.
     Then it joins and prints the full report: exclusions by reason, the primary test at the close, controls, the
     readout, T-24h and the line move, the F3b gate (section 3) and, once 2023-25 are all in and every 2023-25 call
     is cached, the decision of 2.9 with the count and bar read at run time (withheld, with the counts, before that).
     `--list-excluded` also prints every excluded line. The report goes to reports/props_grade/report.md and every
     line, graded or excluded, to reports/props_grade/lines.csv (gitignored).

No API is called. Paper only: nothing here places, sizes or routes a bet.
"""
from __future__ import annotations

import hashlib
import math
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ...cache import RawCache
from ...oddsapi import bulk
from ...settings import REPORTS_DIR, utcnow
from . import grade, lines as L, outcomes, registration, roster

DATA_DAY = ("On data day: `uv run markets odds5m full --pull F3 --seasons 2025 ...` (docs/ODDS5M_DAY_ONE.md, step 5), "
            "then `uv run markets props-grade` (coverage and the book only), the dated book note in section 8 of "
            f"{registration.PREREG_REL}, then `uv run markets props-grade --book-recorded <book>`.")


@dataclass
class Paths:
    roster: Path = roster.ROSTER
    games: Path = outcomes.GAMES
    player_week: Path = outcomes.PLAYER_WEEK
    status: Path = registration.STATUS
    prereg: Path = registration.PREREG
    check_git: bool = True                 # registration and roster committed unchanged (off for the fixture)
    out: Path = field(default_factory=lambda: REPORTS_DIR / "props_grade")


# ---------------------------------------------------------------- formatting
def _f(x, nd=3) -> str:
    if x is None or x is pd.NA or (isinstance(x, (float, np.floating)) and math.isnan(x)):
        return "-"
    if isinstance(x, (bool, np.bool_)):
        return "yes" if x else "no"
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    if isinstance(x, (float, np.floating)):
        x = float(x)
        return f"{x:,.{nd}f}" if abs(x) >= 1e-4 or x == 0 else f"{x:.2e}"
    return str(x)


def text_table(df: pd.DataFrame, cols: list[str], nd: int = 3) -> list[str]:
    if df is None or df.empty:
        return ["  (none)"]
    cells = [[str(c) for c in cols]] + [[_f(v, nd) for v in r] for r in df[cols].itertuples(index=False)]
    w = [max(len(row[i]) for row in cells) for i in range(len(cols))]
    return ["  " + "  ".join(c.rjust(w[i]) if i else c.ljust(w[i]) for i, c in enumerate(row)) for row in cells]


def _commit(path: Path | None = None) -> str:
    """The repo's short HEAD, or the last commit of `path`."""
    cmd = ["git", "log", "-1", "--format=%h", "--", str(path)] if path else ["git", "rev-parse", "--short", "HEAD"]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=registration.REPO, timeout=10).stdout.strip()
    except Exception:
        return ""


def committed(path: Path) -> tuple[bool, str]:
    """(committed and unchanged at HEAD, what to print)."""
    try:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)], capture_output=True,
                                 cwd=registration.REPO, timeout=10).returncode == 0
        clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], capture_output=True,
                               cwd=registration.REPO, timeout=10).returncode == 0
    except Exception as e:                      # no git: can't show it was committed
        return False, f"git unavailable ({type(e).__name__})"
    if not tracked:
        return False, "not committed"
    return (True, f"committed in {_commit(path)}") if clean else (False, "has changes not committed")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- the command
def nothing_yet(games: dict, calls: list, cached: int) -> None:
    if not games:
        why = "no NFL schedule has been saved (`markets odds5m probe` runs first)"
    elif not calls:
        why = "the saved schedule plans no F3 call"
    else:
        why = f"0 of F3's {sum(not c.sealed for c in calls):,} planned 2023-25 calls are cached"
    print(f"No F3 data yet: {why}. Nothing to grade yet.")
    print(f"The rule, its exclusions and its decision criteria are fixed in {registration.PREREG_REL} (registered "
          "September 30, 2026); this grader implements them and adds no variant.")
    print(DATA_DAY)


def grade_command(cfg: dict, cache: RawCache, paths: Paths, *, book_recorded: str | None = None,
                  list_excluded: bool = False, fixture: bool = False, now=None) -> int:
    games = L.schedule(cfg, cache)
    calls = L.f3_calls(cfg, games, now=now)
    cached = sum(1 for c in calls if not c.sealed and cache.lookup(c.cache_sport, c.source, c.key) is not None)
    if not calls or not cached:
        nothing_yet(games, calls, cached)
        return 0
    out: list[str] = []

    def say(*xs):
        for x in xs:
            print(x)
            out.append(x)

    title = "Props grade (#10): the line against the median" + (" -- SYNTHETIC FIXTURE, NOT DATA" if fixture else "")
    say(title, "", f"Run {utcnow():%Y-%m-%d %H:%M} UTC from commit {_commit() or 'unknown'}. Rules: "
        f"{registration.PREREG_REL} (registered September 30, 2026, PR 82). Sealed 2026 rows are never read.",
        "n_variants_tested: 1, the variant already in the running count (section 4); this grader adds none.", "")
    loaded = L.load(cfg, calls, cache, games)
    say(*loaded_section(loaded, calls))
    if loaded.rows.empty:
        say("F3 is cached but no row of #10's markets survived loading. Nothing to grade.")
        return 0
    cov = L.coverage(loaded.rows)
    book = L.choose_book(cov)
    f3a_missing = uncached(loaded, roles=True).get(L.F3A, {})
    say(*book_section(cov, book, f3a_missing))
    if book is None:
        say("F3a (the 2025 season) has no close-snapshot line in either primary market, so the book can't be chosen. "
            "Nothing to grade.")
        return 0
    say(*names_section(loaded.rows, paths.roster))
    stop = refusal(book, book_recorded, registration.noted_book(paths.prereg), paths)
    if stop:
        say(*stop)
        return 0 if book_recorded is None else 1

    df, unmatched_games, pw = join(loaded.rows, book, paths)        # only after the book note
    ro = grade.readout(df, grade.season_medians(pw))
    b = registration.bar(paths.status, paths.prereg)
    state = committed(paths.roster)[1] if paths.check_git else "not checked (fixture)"
    say(f"Roster (2.7): {paths.roster.name}, SHA-256 {sha256(paths.roster)[:16]}..., {state}. Outcomes: "
        f"{paths.player_week.name}, kickoffs: {paths.games.name} (gameday and gametime, US Eastern), both read for "
        "2023-25 only.", "")
    say(*results_section(df, unmatched_games, ro, b, uncached(loaded), f3a_missing))
    if list_excluded:
        say(*excluded_listing(df))
    paths.out.mkdir(parents=True, exist_ok=True)
    (paths.out / "report.md").write_text("\n".join(out) + "\n")
    keep = ["role", "label", "season", "event_id", "game_id", "market", "description", "player_id", "book", "status",
            "detail", "line", "d_over", "d_under", "p_power", "p_add", "p_mult", "lines_listed", "y", "win", "snap"]
    df[keep].rename(columns={"status": "excluded_for"}).to_csv(paths.out / "lines.csv", index=False)
    print(f"wrote {paths.out}/report.md and lines.csv")
    return 0


def join(rows: pd.DataFrame, book: str, paths: Paths) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """The main lines at the book, joined to the nflverse schedule, the roster and player_week (2023-25 only):
    every line with its fate (grade.assign), the unmatched games by reason, and the player_week rows read."""
    pl = L.player_lines(rows, book)
    sched = outcomes.nfl_schedule(paths.games)
    events = pl[["event_id", "kick", "home_team", "away_team"]].drop_duplicates("event_id")
    matched, unmatched_games, _ = outcomes.match_events(events, sched)
    names = roster.NameMap(roster.load(paths.roster))
    pw = outcomes.player_week(paths.player_week)
    return grade.assign(pl, matched, names, pw), unmatched_games, pw


def refusal(book: str, recorded: str | None, noted: tuple[str | None, str], paths: Paths) -> list[str] | None:
    """Why the join can't run yet (nothing joined to an outcome before the section 8 note), or None. `noted` is
    registration.noted_book: (the book section 8's dated entries record, or None, and why not)."""
    name = registration.BOOK_NAMES[book]
    where = f"section 8 of {registration.PREREG_REL}"
    note, why = noted
    if recorded is None:
        state = f"it records {registration.BOOK_NAMES[note]}" if note else why
        return ["Stopped before any outcome is read: the book has to be recorded first (2.4: \"recorded after the "
                "F3a pull, and before any F3a row is joined to an outcome, in a dated note (section 8)\").",
                f"Next: add a dated entry to {where} saying \"the book is {name}\", with the two coverage figures "
                f"above (now {state}); commit it; then rerun with --book-recorded {book}."]
    if recorded != book:
        return [f"REFUSED: --book-recorded {recorded}, but the rule of 2.4 picks {name} on F3a's coverage. Nothing "
                "was joined to an outcome."]
    if note != book:
        state = f"it records {registration.BOOK_NAMES[note]}" if note else why
        return [f"REFUSED: {where} does not record {name} in a dated entry (\"the book is {name}\"): {state}. "
                "Nothing was joined to an outcome."]
    if paths.check_git:
        for what, path in (("the registration", paths.prereg), ("the roster", paths.roster)):
            ok, state = committed(path)
            if not ok:
                return [f"REFUSED: {what} ({path}): {state}. The book note and the roster must be committed before "
                        "the first join (2.4, 2.7). Nothing was joined to an outcome."]
    return None


def uncached(ld: L.Loaded, roles: bool = False) -> dict:
    """Planned, unsealed calls not in the cache, by season label (and by snapshot, with `roles`)."""
    out: dict = {}
    for (label, role, answer), n in ld.status.items():
        if answer == "not cached":
            if roles:
                out.setdefault(label, {})
                out[label][role] = out[label].get(role, 0) + n
            else:
                out[label] = out.get(label, 0) + n
    return out


def names_section(rows: pd.DataFrame, roster_path: Path) -> list[str]:
    """2.7's name match, before any join: the prop names that map to no player, or to more than one, on either team
    that season. Reads the roster and the team table only (no outcome, schedule or score), so the hub can review the
    name map, and fix the roster by a dated amendment, before the first join."""
    names = roster.NameMap(roster.load(roster_path))
    pg = rows[rows.point.notna()][["event_id", "label", "home_team", "away_team", "description"]].drop_duplicates()
    bad: dict[tuple[str, str], set] = {}
    total = 0
    for r in pg.itertuples(index=False):
        if not str(r.label).isdigit():
            continue
        total += 1
        _, why = names.match(int(r.label), (outcomes.team_code(r.home_team), outcomes.team_code(r.away_team)),
                             r.description)
        if why:
            bad.setdefault((r.description, why), set()).add(r.event_id)
    t = pd.DataFrame([(n, w, len(e)) for (n, w), e in bad.items()], columns=["name", "why", "games"])
    t = t.sort_values(["games", "name"], ascending=[False, True])
    out = ["## Names against the roster (2.7), before any join", "",
           f"(Game, player name) pairs in F3's lines: {total:,}; not matched to exactly one rostered player on either "
           f"team that season: {len(t):,} names in {int(t.games.sum()) if len(t) else 0:,} games. Names and counts "
           "only: the roster is not an outcome table. A fix to the roster is a dated amendment made before the "
           "first join (2.7)."]
    return out + (text_table(t, ["name", "why", "games"]) if len(t) else []) + [""]


def loaded_section(ld: L.Loaded, calls: list) -> list[str]:
    st = pd.DataFrame([(s, r, k, n) for (s, r, k), n in sorted(ld.status.items())],
                      columns=["season", "snapshot", "answer", "calls"])
    out = ["## What was loaded", "",
           f"F3 calls planned from the saved schedule: {len(calls):,}; sealed (2026 games), never read: "
           f"{ld.sealed_calls:,}. The rest, by season, snapshot and cached answer:", *text_table(st, list(st.columns)),
           "", f"Rows refused as sealed after loading, before any join: {sum(ld.refused.values()):,}"
           + (f" ({dict(ld.refused)})" if ld.refused else "") + f"; left out by bulk.load_rows: "
           f"{sum(ld.left_out.values()):,}" + (f" ({dict(ld.left_out)})" if ld.left_out else "") + "."]
    missing = uncached(ld)
    if missing.get(L.F3A):
        out.append(f"F3a (2025) is partial: {missing[L.F3A]:,} of its planned calls are not cached; everything below "
                   "covers only what is.")
    f3b = {s: n for s, n in sorted(missing.items()) if s != L.F3A}
    if f3b:
        out.append("2023-24 (F3b, bought only through the gate): planned calls not cached: "
                   + ", ".join(f"{s} {n:,}" for s, n in f3b.items()) + ".")
    if ld.skipped:
        out.append("Rows not read, by reason: " + "; ".join(f"{k} {v:,}" for k, v in sorted(ld.skipped.items())) + ".")
    for role, (med, mx) in sorted(ld.lag_minutes.items()):
        out.append(f"{role}: the answer's snapshot is {med:.1f} minutes (median) and at most {mx:.1f} before the "
                   "time requested.")
    rows = ld.rows
    if len(rows):
        n = rows.groupby(["label", "role", "market"]).description.nunique().rename("names").reset_index()
        out += ["", "Distinct player names listed at any us10 book, by season, snapshot and market:",
                *text_table(n, ["label", "role", "market", "names"])]
    return out + [""]


def partial_f3a(missing: dict) -> str:
    return (f"WARNING: F3a is partial: {sum(missing.values()):,} of its planned calls are not cached ("
            + ", ".join(f"{r}: {n:,}" for r, n in sorted(missing.items())) + ").")


def book_section(cov: dict, book: str | None, f3a_missing: dict | None = None) -> list[str]:
    out = ["## The book (2.4), from F3a's close-snapshot coverage", ""]
    if f3a_missing:
        out += [partial_f3a(f3a_missing) + " The book below is picked on the close snapshots cached so far; record "
                "it in section 8 only once F3a is complete.", ""]
    for m, (num, den) in cov.items():
        share = f"{num / den:.1%}" if den else "-"
        out.append(f"  {m}: Pinnacle lists {num:,} of {den:,} player-games ({share})")
    if book:
        out.append(f"Book: {registration.BOOK_NAMES[book]} (Pinnacle only if it lists at least 80% in EACH primary "
                   "market; one book for all four markets; fixed on F3a, never revisited; no fill-in from another "
                   "book).")
    return out + [""]


COLS = ["scope", "n", "games", "under_wins", "under_rate", "mean_p", "excess", "se_plain", "se_game", "p", "roi",
        "excess_additive", "excess_multiplicative"]


def results_section(df: pd.DataFrame, unmatched_games, ro: pd.DataFrame, b: registration.Bar,
                    missing: dict | None = None, f3a_missing: dict | None = None) -> list[str]:
    out = ["## Exclusions (2.7), every line counted once under the first reason that applies", ""]
    out += text_table(grade.exclusions(df), ["role", "market", "reason", "lines"])
    graded = df[df.status == ""]
    n = {(r, k): len(graded[(graded.role == r) & graded.market.isin(ms)]) for r in (L.CLOSE, L.T24)
         for k, ms in (("primary", L.PRIMARY), ("controls", L.CONTROLS))}
    out += ["", f"Graded lines: at the close {n[L.CLOSE, 'primary']:,} primary and {n[L.CLOSE, 'controls']:,} "
            f"control; at T-24h {n[L.T24, 'primary']:,} primary and {n[L.T24, 'controls']:,} control."]
    if unmatched_games:
        out.append("Games not matched to nflverse's schedule, by reason: "
                   + "; ".join(f"{k} {v}" for k, v in sorted(unmatched_games.items())) + ".")
    um = df[df.status == L.UNMATCHED].detail.value_counts()
    if len(um):
        out.append("Unmatched players, by why: " + "; ".join(f"{k} {v}" for k, v in um.items()) + ".")
    out += ["Run with --list-excluded to list every excluded line.", "",
            "## The primary test at the close (2.6): receiving and rushing yards pooled",
            "excess = under rate - mean power-method probability; p one-sided from the larger of the two SEs "
            "(plain, and clustered by game, not centred); roi at the under's price, one unit a line. The additive "
            "and multiplicative columns are the excess with those de-vig methods, reported, not graded. The rows "
            "for each season and each market are the five checks of 2.9, which decide nothing until 2.9 is read.", ""]
    close = grade.table(df, L.CLOSE, L.PRIMARY)
    cells = close.scope.str.contains(", ")
    out += text_table(close[~cells], COLS, 4)
    out += ["", "Season x market cells, descriptive (the six-cell reading of 2.9 was rejected; no p-value):"]
    out += text_table(close[cells], [c for c in COLS if c != "p"], 4)
    out += ["", f"Clustered SE over plain SE (pooled): {_f(close.se_ratio.iloc[0] if len(close) else None, 2)} "
            "(section 5: the within-game correlation, measured and reported, used for nothing).", "",
            "## Controls (2.3): passing yards and receptions, reported, never tested (no p-value)", ""]
    out += text_table(grade.controls(df), [c for c in COLS if c != "p"], 4)
    out += ["", "## Mechanism readout (2.8): the line against the player's same-season median",
            "Over the graded close lines; the median over every 2023-25 game of that season in which he has a "
            "player_week row (playoffs included; no attempt = 0). Descriptive: the median is known only after the "
            "season.", ""]
    out += text_table(ro.assign(season=ro.season.astype(str)), ["market", "season", "lines", "no_median",
                                                                 "mean_line_minus_median", "share_above"], 3)
    out += ["", "## Secondary (2.10): the same statistic at T-24h, and the line move. Reported, not a second test", ""]
    t24 = grade.table(df, L.T24, L.PRIMARY)
    out += text_table(t24[t24.scope.isin(("pooled",) + L.PRIMARY)], COLS, 4)
    out += ["", "Line move, close minus T-24h, for primary player-games with a main line at the book at both:"]
    out += text_table(grade.line_move(df), ["scope", "pairs", "mean_move", "share_up", "share_down", "share_same"], 3)
    out += ["", "## The F3b gate (section 3), on the 2025 season", ""]
    if f3a_missing:
        out += [partial_f3a(f3a_missing) + " The gate below reads only the cached calls.", ""]
    out += gate_lines(grade.gate(df, ro))
    out += ["", "## The count and the bar (2.9, section 4), read at run time", ""]
    out += ["  " + x for x in b.lines()]
    out += ["", "## Decision (2.9)", ""]
    out += decision_lines(grade.decision(df, b.alpha, missing), b)
    out += ["", "2026 is sealed: not read. It is opened once, for every hypothesis registered by then, under the "
            "criteria of 2.2.", ""]
    return out


def gate_lines(g: dict) -> list[str]:
    if not g["read"]:
        return [f"Not read: {g['why']}."]
    p = g["pooled"]
    out = [f"Pooled excess {p['excess']:+.4f} on {p['n']:,} lines in {p['games']:,} games (SE plain "
           f"{p['se_plain']:.4f}, by game {_f(p['se_game'], 4)}; p from the larger {_f(p['p'], 4)}; ROI "
           f"{p['roi']:+.4f}). Per market: " + "; ".join(f"{m} {t['excess']:+.4f} (n {t['n']:,}, ROI {_f(t['roi'], 4)})"
                                                          for m, t in g["markets"].items()) + "."]
    out += [f"  {'pass' if ok else 'FAIL'}  {k}" for k, ok in g["checks"].items()]
    out.append("Gate: PASSES (F3b may be bought in October)." if g["passes"] else
               "Gate: FAILS (F3b moves to March; only the kicking markets, #21, stay in play; #10 is set aside with no "
               "Act or Drop verdict).")
    out.append("The gate decides only the F3b purchase. None of its numbers is a test (section 3).")
    return out


def decision_lines(d: dict, b: registration.Bar) -> list[str]:
    if d.get("withheld"):
        return [f"Verdict withheld: {d['why']}."]
    if not d["read"]:
        return [f"Not read: {d['why']}. The F3a read on 2025 alone decides only the F3b purchase (section 3)."]
    p = d["pooled"]
    out = [f"Condition 1: pooled p {_f(p['p'], 6)} (larger SE) against the bar {_f(b.alpha, 6)}: "
           f"{'met' if d['condition_1'] else 'not met'}.", "Condition 2, five checks (positive excess, p < 0.01):"]
    out += [f"  {'pass' if ok else 'FAIL'}  {k}: excess {_f(e, 4)}, p {_f(pv, 4)}" for k, (e, pv, ok) in
            d["checks"].items()]
    out.append("Carries it (Drop): the pooled excess with one market or one season removed (- = nothing left, "
               "which counts as carried): " + "; ".join(f"{k} {_f(v, 4)}" for k, v in d["without"].items()) + ".")
    out.append(f"Verdict: {d['verdict']}.")
    return out


def excluded_listing(df: pd.DataFrame) -> list[str]:
    x = df[df.status != ""].sort_values(["role", "status", "market", "event_id", "description"])
    out = ["", "## Every excluded line (--list-excluded)", ""]
    out += text_table(x.assign(reason=x.status), ["role", "reason", "detail", "market", "event_id", "description",
                                                  "line"], 1)
    return out


def main(args) -> int:
    if args.fixture:
        from . import fixture
        tmp = Path(tempfile.mkdtemp(prefix="props-grade-fixture-"))
        fx = fixture.build(tmp)
        print(f"SYNTHETIC FIXTURE (not data), in {tmp}")
        paths = Paths(fx.roster, fx.games, fx.player_week, fx.status, fx.prereg, check_git=False,
                      out=Path(args.out) if args.out else tmp / "report")
        return grade_command(fx.cfg, fx.cache, paths, book_recorded=args.book_recorded or fx.book,
                             list_excluded=args.list_excluded, fixture=True, now=fixture.NOW)
    paths = Paths(out=Path(args.out)) if args.out else Paths()
    return grade_command(bulk.load_config(), RawCache(), paths, book_recorded=args.book_recorded,
                         list_excluded=args.list_excluded)
