"""Amendment 8 (draft, Sep 30): Astra's audit 3, blockers 1 and 2 (issue 88), checked in this scorer. A captured
Pinnacle close is used only for the listing it was captured for, 2 to 20 minutes before that listing's kickoff; and
the test's end already follows the schedule (a test holds it). The audit's first case, as an NFL game, fails on the
scorer as it was on main on Sep 29 (commit 30444ec) and passes here. Every input is synthetic, or the committed 2025
rehearsal; no 2026 price or result is read, and every run is a preview (--now) on a test ledger (--ledger)."""
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RB = ("RULE_B (wind under)", "RULE_B, secondary")
REFUSED = "close captured outside the window for this listing (2 to 20 minutes before its kickoff)"


def wk_day(year, wk):
    """The Sunday of `wk` in `year`'s season (Week 1's Sunday is Sep 13 in 2026)."""
    return (pd.Timestamp(f"{year}-09-10") + pd.Timedelta(weeks=wk - 1, days=3)).strftime("%Y-%m-%d")


def row(gid, day, time="13:00", snap=None, **kw):
    base = dict(rules_version="v3-2026-09-28", game_id=gid, gameday=day, gametime=time, away_team="A",
                home_team="B", lead_days=2, wx_src="era5", wx_wind=16, line_src="pinnacle", total_line=44.0,
                under_odds=-110, over_odds=-110, p_under=0.5, p_market=0.5, lean="", ev_under=0.08, rule_b="SIGNAL")
    base["snapshot_utc"] = snap or (pd.Timestamp(day) - pd.Timedelta(days=2)).strftime("%Y-%m-%dT15:00:00Z")
    return base | kw


def game(gid, day, time="13:00", season=None, week=None, game_type="REG", total=40, close=42, result=3):
    d = pd.Timestamp(day)
    season = season if season is not None else (d.year if d.month >= 8 else d.year - 1)
    return dict(game_id=gid, season=season, week=week, game_type=game_type, gameday=day, gametime=time,
                total=total, total_line=close, result=result)


def eastern(day, time):
    return pd.Timestamp(f"{day} {time}").tz_localize("America/New_York").tz_convert("UTC")


def cap(gid, day, time, minutes, total, book="pinnacle"):
    """A row of closes.csv as scripts/capture_close.py writes it: captured `minutes` before the kickoff `day time`
    (Eastern), with the capture time as oddsapi.live stamps it (to the minute)."""
    k = eastern(day, time)
    return dict(game_id=gid, kick_utc=k.strftime("%Y-%m-%dT%H:%M:%SZ"), home_team="B", away_team="A",
                capture_utc=(k - pd.Timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H%MZ"), book=book,
                close_total=total, close_under=-110, close_over=-110, book_update="")


def score(folder, rows, games, now, *extra, closes=None):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "ledger.csv", index=False)
    pd.DataFrame(games).to_csv(folder / "games.csv", index=False)
    if closes is not None:
        pd.DataFrame(closes).to_csv(folder / "closes.csv", index=False)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(folder / "ledger.csv"), "--games", str(folder / "games.csv"), "--now", now, *extra],
                          capture_output=True, text=True, check=True).stdout


def part(out, start, end):
    return out.split(start, 1)[1].split(end, 1)[0] if start in out else ""


# ------------------------------------------------------------------ blocker 1: the audit's case, as an NFL game
def test_blocker_1_a_new_listing_never_inherits_the_close_captured_for_an_earlier_one(tmp_path):
    """Listed Oct 11 1:00 PM Eastern, Pinnacle close 40 captured at 12:50 that day; postponed to Nov 1 and signalled
    again at 50. Main's secondary CLV for the Nov 1 listing was +10.00, against the Oct 11 close."""
    rows = [row("PPD", "2026-10-11", total_line=44.0), row("PPD", "2026-11-01", total_line=50.0)]
    games = [game("PPD", "2026-11-01", week=9, close=49)]
    closes = [cap("PPD", "2026-10-11", "13:00", 10, 40.0)]
    out = part(score(tmp_path, rows, games, "2026-11-20", closes=closes), *RB)
    assert "2 signals, 1 settled, 0 pending, 1 void (not graded)" in out
    assert "+10.00" not in out and "secondary (amendment 3): no captured closes for these 1 bets" in out
    assert f"captured Pinnacle close refused for 1 of these 1 bets: {REFUSED}; counted as missing (PPD)" in out
    assert "mean CLV +1.00 pts; 1 of 1 bets have a primary close" in out            # the primary close is unchanged
    listed = part(score(tmp_path, rows, games, "2026-11-20", "--list-excluded", closes=closes), *RB)
    line = next(ln for ln in listed.splitlines() if ln.strip().startswith("PPD ") and REFUSED in ln)
    assert "2026-10-11T1650Z" in line and "2026-10-11T17:00:00Z" in line and "2026-11-01 18:00:00+00:00" in line


# ------------------------------------------------------------------ blocker 2: checked, already on the schedule
def test_blocker_2_a_game_moved_past_the_pooled_horizon_is_left_out_of_that_decision(tmp_path):
    """The audit's second case, checked here: an entry row whose kickoff is before the horizon (the last 2027
    regular-season kickoff) while the schedule moves the game 21 hours past it (not void). The scorer takes kickoffs
    and seasons from the schedule, so the game is left out of the pooled decision, on main and now."""
    rows, games = [], []
    for year in (2026, 2027):
        for wk in (6, 8, 10):
            gid = f"{year}_{wk:02d}_X"
            rows.append(row(gid, wk_day(year, wk)))
            games.append(game(gid, wk_day(year, wk), season=year, week=wk))
    games += [game(f"{y}_{wk:02d}_FILL", wk_day(y, wk), season=y, week=wk) for y in (2026, 2027) for wk in range(1, 19)]
    last = wk_day(2027, 18)                                                    # the horizon: 1:00 PM that day
    rows.append(row("WC27", last, time="10:00"))                              # logged against a kickoff before it
    moved = (pd.Timestamp(last) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    games.append(game("WC27", moved, time="07:00", season=2027, week=19, game_type="WC"))    # 21 hours later
    out = part(score(tmp_path, rows, games, "2028-02-20"), *RB)
    assert "7 signals, 7 settled, 0 pending, 0 void" in out and "WC27" in out
    assert re.search(r"after the 2027 regular season, both seasons pooled\), FINAL: INCONCLUSIVE \(only 6 of the 6 "
                     r"bets have a primary close", out)


# ------------------------------------------------------------------ the window
def test_a_close_captured_inside_the_window_is_used_at_both_ends(tmp_path):
    """10 minutes before kickoff, and exactly 2 and exactly 20; a DraftKings row is never the captured close."""
    days = ["2026-10-11", "2026-10-18", "2026-10-25"]
    rows = [row(f"G{i}", d) for i, d in enumerate(days)]
    closes = [cap(f"G{i}", d, "13:00", m, 44.0 - c) for i, (d, m, c) in enumerate(zip(days, (10, 2, 20), (1, 2, 3)))]
    closes.append(cap("G0", days[0], "13:00", 5, 30.0, book="draftkings"))
    out = part(score(tmp_path, rows, [game(f"G{i}", d) for i, d in enumerate(days)], "2026-11-20", closes=closes), *RB)
    assert "mean CLV vs captured Pinnacle close +2.00 pts" in out and "0 of 3 without a captured close" in out
    assert "refused" not in out


def test_a_close_captured_21_minutes_or_1_minute_before_kickoff_or_after_it_is_not_used(tmp_path):
    days = ["2026-10-11", "2026-10-18", "2026-10-25", "2026-11-01"]
    rows = [row(f"G{i}", d) for i, d in enumerate(days)]
    closes = [cap(f"G{i}", d, "13:00", m, 43.0) for i, (d, m) in enumerate(zip(days, (21, 1, -5, 10)))]
    out = part(score(tmp_path, rows, [game(f"G{i}", d) for i, d in enumerate(days)], "2026-11-20", closes=closes), *RB)
    assert "mean CLV vs captured Pinnacle close +1.00 pts" in out and "3 of 4 without a captured close" in out
    assert f"captured Pinnacle close refused for 3 of these 4 bets: {REFUSED}; counted as missing (G0, G1, G2)" in out


def test_a_close_captured_for_the_earlier_listing_of_a_postponed_game_is_not_used_for_the_later_one(tmp_path):
    """The later listing's own capture (48) is its close, even when the earlier listing's capture (40) comes after it
    in the file; main took the file's last Pinnacle row, 40."""
    rows = [row("PPD", "2026-10-11", total_line=44.0), row("PPD", "2026-11-01", total_line=50.0)]
    closes = [cap("PPD", "2026-11-01", "13:00", 10, 48.0), cap("PPD", "2026-10-11", "13:00", 10, 40.0)]
    out = part(score(tmp_path, rows, [game("PPD", "2026-11-01", week=9)], "2026-11-20", closes=closes), *RB)
    assert "1 settled, 0 pending, 1 void" in out and "mean CLV vs captured Pinnacle close +2.00 pts" in out
    assert "refused" not in out


def test_the_window_is_before_the_earlier_of_the_rows_kickoff_and_the_schedules(tmp_path):
    """A game moved earlier, 1:00 PM on the row to 10:00 AM in the schedule (not void): a close captured at 12:50 was
    in play and is refused; one captured at 9:50 is used. Two retries in the window: the last in the file is taken."""
    rows = [row("E1", "2026-10-11"), row("E2", "2026-10-18")]
    games = [game("E1", "2026-10-11", time="10:00"), game("E2", "2026-10-18", time="10:00")]
    closes = [cap("E1", "2026-10-11", "13:00", 10, 40.0),
              cap("E2", "2026-10-18", "10:00", 15, 43.0), cap("E2", "2026-10-18", "10:00", 10, 42.0)]
    out = part(score(tmp_path, rows, games, "2026-11-20", closes=closes), *RB)
    assert "2 signals, 2 settled" in out and "mean CLV vs captured Pinnacle close +2.00 pts" in out
    assert f"captured Pinnacle close refused for 1 of these 2 bets: {REFUSED}; counted as missing (E1)" in out


# ------------------------------------------------------------------ a game moved later on game day (review, finding 1)
ASIDE = "outside the window for the listing, while another inside it is used"


def moved_later(tmp_path, later_row, *extra):
    """Game MV's entry row gives 1:00 PM Eastern on Oct 11; the game is moved to 4:25 PM (under 24 hours: not void).
    The capture job caught both slots: 46.0 ten minutes before 1:00, and the true close, 41.0, ten minutes before
    4:25. With `later_row`, the board logged the game again at noon Eastern with the new kickoff (no signal on it)."""
    rows = [row("MV", "2026-10-11", total_line=44.0)]
    if later_row:
        rows.append(row("MV", "2026-10-11", time="16:25", snap="2026-10-11T16:00:00Z", rule_b="no_trigger"))
    closes = [cap("MV", "2026-10-11", "13:00", 10, 46.0), cap("MV", "2026-10-11", "16:25", 10, 41.0)]
    return score(tmp_path, rows, [game("MV", "2026-10-11", time="16:25", week=6)], "2026-11-20", *extra,
                 closes=closes)


def test_a_game_moved_later_is_graded_on_its_true_close_once_a_row_shows_the_new_kickoff(tmp_path):
    """The listing's kickoff is the earlier of its last row's and the schedule's: 4:25 PM, so the close captured at
    4:15 is used (secondary CLV +3.00, as on main), and the 12:50 capture is set aside, counted and named. On the entry
    row's kickoff alone (the first draft) the stale 12:50 capture was taken (-2.00)."""
    out = part(moved_later(tmp_path, later_row=True), *RB)
    assert "1 signals, 1 settled, 0 pending, 0 void" in out
    assert "mean CLV vs captured Pinnacle close +3.00 pts" in out and "refused" not in out
    assert f"Pinnacle captures set aside for 1 of these 1 bets: 1 {ASIDE} (MV)" in out
    listed = part(moved_later(tmp_path, True, "--list-excluded"), *RB)
    line = next(ln for ln in listed.splitlines() if ln.strip().startswith("MV ") and "set aside" in ln)
    assert "2026-10-11T1650Z" in line and "2026-10-11 20:25:00+00:00" in line


def test_a_game_moved_later_with_no_row_after_the_move_is_the_declared_limit_and_is_reported(tmp_path):
    """No row logged after the move: the listing's kickoff is still the entry row's 1:00 PM, so the 12:50 capture (a
    pre-kickoff price for this listing, never in play) is used, and the 4:15 capture is set aside, counted and named."""
    out = part(moved_later(tmp_path, later_row=False), *RB)
    assert "mean CLV vs captured Pinnacle close -2.00 pts" in out
    assert f"Pinnacle captures set aside for 1 of these 1 bets: 1 {ASIDE} (MV)" in out


def test_a_row_logged_after_the_real_kickoff_never_sets_the_listing_s_kickoff(tmp_path):
    """Kickoff 1:00 PM on the entry row and in the schedule. A row logged at 1:30 PM that shows 4:25 PM is excluded
    as logged at or after kickoff, so the listing's kickoff stays 1:00 PM: a capture at 4:15 (in play) is refused;
    with the 12:50 capture beside it, the 12:50 one is used and the 4:15 one is set aside."""
    rows = [row("IP", "2026-10-11"), row("IP", "2026-10-11", time="16:25", snap="2026-10-11T17:30:00Z",
                                         rule_b="no_trigger")]
    games = [game("IP", "2026-10-11", week=6)]
    inplay = cap("IP", "2026-10-11", "16:25", 10, 30.0)
    out = score(tmp_path / "a", rows, games, "2026-11-20", closes=[inplay])
    assert "excluded, logged at or after kickoff: 1" in out
    assert f"captured Pinnacle close refused for 1 of these 1 bets: {REFUSED}; counted as missing (IP)" in part(out, *RB)
    out = part(score(tmp_path / "b", rows, games, "2026-11-20", closes=[cap("IP", "2026-10-11", "13:00", 10, 43.0),
                                                                          inplay]), *RB)
    assert "mean CLV vs captured Pinnacle close +1.00 pts" in out
    assert f"Pinnacle captures set aside for 1 of these 1 bets: 1 {ASIDE} (IP)" in out


def test_a_postponed_game_s_earlier_capture_is_still_refused_after_rows_on_the_new_date(tmp_path):
    """The audit's case with the board logging the new listing twice: the Oct 11 capture is still not the Nov 1
    listing's close."""
    rows = [row("PPD", "2026-10-11", total_line=44.0), row("PPD", "2026-11-01", total_line=50.0),
            row("PPD", "2026-11-01", time="13:30", snap="2026-11-01T15:00:00Z", rule_b="no_trigger")]
    closes = [cap("PPD", "2026-10-11", "13:00", 10, 40.0)]
    out = part(score(tmp_path, rows, [game("PPD", "2026-11-01", time="13:30", week=9)], "2026-11-20", closes=closes),
               *RB)
    assert "2 signals, 1 settled, 0 pending, 1 void" in out
    assert f"captured Pinnacle close refused for 1 of these 1 bets: {REFUSED}; counted as missing (PPD)" in out


# ------------------------------------------------------------------ the amendment's text
def norm(text):
    return " ".join(text.replace("**", "").replace("`", "").split())


def test_amendment_8_is_a_dated_draft_that_repairs_a_registered_rule_and_quotes_what_it_replaces():
    whole = (ROOT / "PREREGISTRATION.md").read_text()
    head, text = whole.split("## Amendment 8 ")[0], whole.split("## Amendment 8 ")[1].split("\n## ")[0]
    assert text.startswith("(registered 2026-09-30 Pacific, before ")        # registered by the hub, Sep 30
    t = norm(text)
    assert "This amendment repairs a registered rule and changes no threshold, gate or decision rule" in t
    assert "0 variants" in t and "on the day it was written it is 288, so the multiple-testing bar is p < 0.000174" in t
    assert "Cfb-weather amendment 6" in t and "already follows the schedule" in t
    assert "2 to 20 minutes" in t and "both ends included" in t
    assert "earlier of the kickoff on the listing's last row logged before kickoff" in t and "set aside" in t
    bullets = text.split("### What this amendment replaces")[1].split("\n* ")[1:]
    assert len(bullets) == 3
    for bullet in bullets:
        label, rest = bullet.split(': "', 1)
        m = re.match(r"Amendment (\d+)(?:, section (\d+))?", label)
        src = head.split(f"## Amendment {m[1]} ")[1].split("\n## ")[0]
        src = src.split(f"### {m[2]}.")[1].split("\n### ")[0] if m[2] else src
        quotes = re.findall(r'"([^"]+)"', '"' + rest)
        assert quotes, label
        for q in quotes:
            assert norm(q) in norm(src), (label, q)
    assert "*Amendment 8 (draft, Sep 30, awaiting the hub):*" in (ROOT.parent / "STATUS.md").read_text()


# ------------------------------------------------------------------ the committed rehearsal ledger
SHIFT = pd.Timedelta(weeks=53)
OFFSETS = [10, 2, 20, 21, 1, 10, 15, 30, 5, 10]       # minutes before kickoff, cycled over the games


def rehearsal(tmp_path, closes):
    """The committed 2025 rehearsal ledger, with the schedule scripts/rehearse_2025.py builds from the committed
    processed games, scored as a preview. With `closes`, one made-up Pinnacle capture per game at the cycled OFFSETS,
    its total a little off the ledger's last quote."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = ROOT / "output" / "tables" / "rehearsal_2025.csv"
    (tmp_path / "ledger.csv").write_bytes(src.read_bytes())
    g = pd.read_parquet(ROOT / "data" / "processed" / "games.parquet")
    g = g[(g.season == 2025) & (g.game_type == "REG") & g.week.between(5, 18) & g.result.notna()]
    g.assign(gameday=(pd.to_datetime(g.gameday) + SHIFT).dt.strftime("%Y-%m-%d"))[
        ["game_id", "total", "total_line", "gameday", "gametime", "result"]].to_csv(tmp_path / "games.csv", index=False)
    led = pd.read_csv(src)
    last = led.sort_values("snapshot_utc", kind="stable").drop_duplicates("game_id", keep="last")
    off = dict(zip(last.game_id, [OFFSETS[i % len(OFFSETS)] for i in range(len(last))]))
    shift = dict(zip(last.game_id, [0.5 * (i % 5 - 2) for i in range(len(last))]))
    if closes:
        pd.DataFrame([cap(r.game_id, r.gameday, r.gametime, off[r.game_id], r.total_line + shift[r.game_id])
                      for r in last.itertuples()]).to_csv(tmp_path / "closes.csv", index=False)
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                          str(tmp_path / "ledger.csv"), "--games", str(tmp_path / "games.csv"), "--now", "2027-03-01"],
                         capture_output=True, text=True, check=True).stdout
    return out, led, off, shift


def test_the_rehearsal_report_is_unchanged_byte_for_byte(tmp_path):
    """No captured closes: the report is the committed rehearsal log's, byte for byte, except its record line (the
    log was a real run on a test ledger; this is a --now preview)."""
    out, _, _, _ = rehearsal(tmp_path, closes=False)
    log = (ROOT / "output" / "rehearsal_2025.log").read_text()
    logged = log.split("Scorer output (entry = close here, so CLV is 0 by construction):\n")[1]
    logged = logged.split("Variants under forward test: 2 (MODEL_LEAN, RULE_B).\n")[0]
    logged = logged.replace("Decision record: the first final decision is written to decisions.csv beside this test "
                            "ledger.", "Decision record: none written by this run: a run with --now is a preview.")
    assert out == logged + "Variants under forward test: 2 (MODEL_LEAN, RULE_B).\n"


def test_the_rehearsal_report_changes_only_where_a_captured_close_is_refused(tmp_path):
    """A made-up capture for every game: only the secondary line changes, and a line is added naming every refused
    game, exactly the settled bets whose capture is outside 2 to 20 minutes (21, 1 and 30 minutes before kickoff; 2
    and 20 are used). The secondary mean is recomputed here."""
    out, led, off, shift = rehearsal(tmp_path, closes=True)
    base, _, _, _ = rehearsal(tmp_path / "none", closes=False)
    kept = [ln for ln in out.splitlines() if "captured Pinnacle close refused" not in ln]
    a = base.splitlines()
    assert len(kept) == len(a)
    changed = [(x, y) for x, y in zip(a, kept) if x != y]
    assert changed and all(x.startswith("  secondary (amendment 3):") and y.startswith("  secondary (amendment 3):")
                           for x, y in changed)
    rb = part(out, *RB)
    named = [s.strip() for m in re.findall(r"counted as missing \(([^)]*)\)", rb) for s in m.split(",")]
    settled = set(re.findall(r"^\s*(20\d\d_\d\d_[A-Z]+_[A-Z]+)\s", rb, re.M))
    outside = {g for g in settled if not 2 <= off[g] <= 20}
    assert outside and sorted(named) == sorted(outside)
    entries = led[led.rule_b == "SIGNAL"].sort_values("snapshot_utc", kind="stable").drop_duplicates("game_id")
    last = led.sort_values("snapshot_utc", kind="stable").drop_duplicates("game_id", keep="last").set_index("game_id")
    inside = entries[[2 <= off[g] <= 20 for g in entries.game_id]]
    clv = inside.total_line.to_numpy() - (last.total_line.reindex(inside.game_id).to_numpy()
                                          + np.array([shift[g] for g in inside.game_id]))
    assert (f"mean CLV vs captured Pinnacle close {np.mean(clv):+.2f} pts" in rb
            and f"{len(entries) - len(inside)} of {len(entries)} without a captured close" in rb)
