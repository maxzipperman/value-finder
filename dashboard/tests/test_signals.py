"""Signals made unmistakable, and the log of every signal: the live-signal panel on Home, the tab title, the badges
and legend, the Signals screen's totals (against arithmetic done by hand here), its charts, its empty screen and
what it shows when a scorer fails. Screens are drawn in Node as test_page_render.py does."""
from __future__ import annotations

import itertools
import json
import math
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import (CFB_DOC, LATER, NFL_DOC, RICH_CFB_DOC, RICH_NFL_DOC, Clock, FakeRunner, bet, cfb_row,
                      copy_content, make_store, nfl_row, rich_store, scorer_doc, doc_test)

from vfdash import api, data, signals, words

HERE = Path(__file__).resolve().parent
APP_JS = HERE.parent / "vfdash" / "static" / "app.js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node is not installed")
UTC = timezone.utc
MINUS = "−"


def draw(tmp_path, hash_: str, answer: dict) -> dict:
    f = tmp_path / "answer.json"
    f.write_text(json.dumps(answer, ensure_ascii=False))
    out = subprocess.run([NODE, str(HERE / "render_page.mjs"), str(APP_JS), hash_, str(f)], capture_output=True,
                         text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def text(n) -> str:
    return n["text"] if "text" in n else "".join(text(k) for k in n["kids"])


def find(n, tag=None, cls=None):
    if "tag" in n:
        if (tag is None or n["tag"] == tag) and (cls is None or cls in (n.get("cls") or n.get("attrs", {}).get("class")
                                                                        or "").split()):
            yield n
        for k in n["kids"]:
            yield from find(k, tag, cls)


def table_rows(page, first_head):
    for t in find(page, "table"):
        heads = [text(th) for th in find(t, "th")]
        if heads and heads[0] == first_head:
            return heads, [tr for tr in find(next(find(t, "tbody")), "tr")]
    raise AssertionError(f"no table headed {first_head!r}")


# ------------------------------------------------------------------ Home: the live-signal panel
def test_home_lists_each_live_signal(store):
    """Three signals live at the fixtures' time: Rule B at Pinnacle's price, Rule B at the backup price, Rule HT."""
    d = api.home(store)
    live = d["live"]
    assert [(s["matchup"], s["badge"], s["rule"]) for s in live] == [
        ("BUF at NE", "signal", "Wind rule (Rule B)"), ("TEN at BAL", "backup", "Wind rule (Rule B)"),
        ("Ohio State at Michigan", "signal", "High-total rule (Rule HT)")]
    buf = live[0]
    assert buf["take"] == f"Under 44.5 at {MINUS}108, Pinnacle"
    assert buf["better"] == f"Better at FanDuel: under 45.0 at {MINUS}110"      # a higher number, as logged
    assert buf["kickoff"] == "Sun Oct 4, 1:00 PM ET" and buf["until"] == "in 2 days"
    assert live[1]["take"] == f"Under 44.5 at {MINUS}108, the consensus line (nflverse)"
    assert live[2]["until"] == "in 8 days, 2 hours"
    assert d["live_note"] == "A signal is the rule firing on a pre-registered paper test. It is not a proven edge."
    assert d["numbers"]["signals_live"] == len(live) == d["header"]["signals_live"] == 3


def test_home_with_one_signal_and_with_none(root, home):
    clock = Clock(datetime(2026, 10, 4, 18, 0, tzinfo=UTC))       # both NFL signals have kicked off
    d = api.home(make_store(root, home, clock=clock))
    assert [s["matchup"] for s in d["live"]] == ["Ohio State at Michigan"] and d["header"]["signals_live"] == 1
    clock.t = datetime(2026, 10, 10, 20, 0, tzinfo=UTC)          # and that one too
    d = api.home(make_store(root, home, clock=clock))
    assert d["live"] == [] and d["header"]["signals_live"] == 0
    assert d["live_none"] == "No signal is live. The next run is at 3:30 PM today."


@needs_node
@pytest.mark.parametrize("when, n, title", [(datetime(2026, 10, 2, 17, 0, tzinfo=UTC), 3, "(3) Value Finder"),
                                            (datetime(2026, 10, 4, 18, 0, tzinfo=UTC), 1, "(1) Value Finder"),
                                            (datetime(2026, 10, 10, 20, 0, tzinfo=UTC), 0, "Value Finder")])
def test_the_panel_and_the_tab_title_as_drawn(root, home, tmp_path, when, n, title):
    store = make_store(root, home, clock=Clock(when))
    page = draw(tmp_path, "#home", api.home(store))
    assert page["doc_title"] == title
    panel = next(find(page, "section", "live"))
    drawn = text(panel)
    tiles = next(find(page, "div", "tiles"))
    assert text(page).index(drawn) < text(page).index("Signals on the board")   # above signal tiles
    if n:
        items = list(find(panel, "li"))
        assert len(items) == n
        assert drawn.startswith(f"{n} signal{'s are' if n > 1 else ' is'} live")
        assert drawn.endswith("A signal is the rule firing on a pre-registered paper test. It is not a proven edge.")
        first = items[0]
        assert list(find(first, "span", "badge"))[0]["kids"] == [{"text": "Signal"}]
    else:
        assert drawn == "No signal is live. The next run is at 3:30 PM today." and "none" in panel["cls"]
    # every screen's answer carries the count, so the tab says it wherever the owner is
    assert draw(tmp_path, "#board", api.board(store))["doc_title"] == title


def test_each_rules_count_toward_its_decision_is_what_it_registers(root, home):
    """No "of the 40 it needs" for the NFL, whose rules are decided after the 2027 season on both seasons pooled when
    2026 has fewer than 40; college football's wind rule needs 40 (or the end of the 2026 regular season, if later)."""
    by = {r["id"]: r["summary"] for r in api.signals_screen(rich_store(root, home))["rules"]}
    lean = by["nfl_lean"]["toward"]
    assert lean.startswith("Toward its decision: ") and lean.endswith(
        " settled so far. It is decided after Week 18 of 2026 if 40 settle in the 2026 regular season, and otherwise "
        "after the 2027 regular season, on both seasons, where fewer than 40 is inconclusive. A lean is a watch: "
        "logged and graded, never a bet.")
    assert by["cfb_rule_b"]["toward"] == (f"Toward the decision: {by['cfb_rule_b']['settled']} of the 40 settled "
                                          "signals it needs. It is decided after the 40th signal's kickoff or the end "
                                          "of the 2026 regular season (Dec 12), whichever is later.")
    assert by["cfb_rule_ht"]["toward"].endswith("It is decided once, after the 2027 season's title game; about 105 "
                                                "bets are expected.")
    assert not [r for r in by.values() if r and "of the 40 settled bets" in r["toward"]]


def test_a_game_that_signals_under_two_rules(root, home, tmp_path):
    """Ohio State at Michigan signals under Rule B and Rule HT on its newest row: the panel has a row for each rule
    (4 signals), while the tab, the tile and the menu-bar light count games (3), and the heading says both."""
    with (root / "cfb-weather" / "data" / "forward" / "ledger.csv").open("a") as f:
        f.write(cfb_row("2026-10-02T14:30:14Z", "401000002", "Sat 10-10 15:30", "Ohio State", "Michigan", "SIGNAL",
                        "SIGNAL", "2026-10-10 19:30:00+00:00", total="64.5") + "\n")
    store = make_store(root, home, clock=Clock(datetime(2026, 10, 2, 17, 0, tzinfo=UTC)))
    d = api.home(store)
    assert len(d["live"]) == 4 and [s["rule"] for s in d["live"] if s["game_id"] == "401000002"] == [
        "Wind rule (Rule B)", "High-total rule (Rule HT)"]
    assert d["header"]["signals_live"] == d["numbers"]["signals_live"] == api.summary(store)["signals_live"] == 3
    if NODE:
        page = draw(tmp_path, "#home", d)
        assert text(next(find(next(find(page, "section", "live")), "h2"))) == "4 signals are live, on 3 games"
        assert page["doc_title"] == "(3) Value Finder"
        tile = next(x for x in find(page, "div", "tile") if text(x).startswith("Signals on the board"))
        assert text(tile).startswith("Signals on the board3Games not yet kicked off with a Rule B or Rule HT signal, "
                                     "each counted once.")


# ------------------------------------------------------------------ the board: signals first, a legend, badges
@needs_node
def test_the_board_groups_signals_and_shows_the_legend(store, tmp_path):
    with (store.cfg.root / "nfl-weather" / "data" / "forward" / "ledger.csv").open("a") as f:
        f.write(nfl_row("2026-10-02T14:30:07Z", "2026_05_LV_LAC", "2026-10-04", "16:05", "LV", "LAC",
                        "price_too_high", wind="17.0") + "\n")
    page = draw(tmp_path, "#board", api.board(store))
    groups = [text(h2) for h2 in find(page, "h2", "group")]
    assert groups == ["Signals3", "Everything else6"]
    legend = text(next(find(page, "div", "legend")))
    for said in ("Signalthe rule fired at its registered price", "Signal, backup price", "Watcha model lean",
                 "a tinted row is a game whose newest row is a signal"):
        assert said in legend
    tables = list(find(page, "table"))
    assert len(tables) == 2
    sig_rows = list(find(next(find(tables[0], "tbody")), "tr"))
    assert all("signal" in tr["cls"].split() for tr in sig_rows) and len(sig_rows) == 3
    rest_rows = list(find(next(find(tables[1], "tbody")), "tr"))
    assert not any("signal" in tr["cls"].split() for tr in rest_rows)
    badges = {text(b) for tr in sig_rows for b in find(tr, "span", "badge")}
    assert badges == {"Signal", "Signal, backup price"}
    lv = next(tr for tr in rest_rows if "LV at LAC" in text(tr))
    assert [text(b) for b in find(lv, "span", "badge")] == ["Watch"]          # a watch, never a signal
    assert "Rule B: Watch Wind trigger, price too high" in text(lv)
    ari = next(tr for tr in rest_rows if "ARI at NYG" in text(tr))
    assert "Model lean: Watch Leans under" in text(ari)


# ------------------------------------------------------------------ the log: totals by hand
W108, W109, W110, W112 = 100 / 108, 100 / 109, 100 / 110, 100 / 112


def test_the_log_s_totals_against_hand_arithmetic(root, home):
    d = api.signals_screen(rich_store(root, home))
    assert d["empty"] is None and d["trouble"] == [] and d["fallback"] == []
    by = {r["id"]: r for r in d["rules"]}
    # each rule, as its scorer printed it
    rb = by["nfl_rule_b"]["summary"]
    assert (rb["record"], rb["units"], rb["roi"]) == ("1-1-1", f"{MINUS}0.07", f"{MINUS}2.5% per bet placed")
    assert rb["units_num"] == pytest.approx(W108 - 1)
    assert rb["clv"] == "Closing-line value: +0.50 points on average, over 3 bets with a close."
    assert rb["interval"] == (f"Registered 95% interval {MINUS}1.65 to +2.65, over 2 game days; it includes zero.")
    assert rb["sample"] == "3 settled bets, 1 waiting for a result, 1 void (not graded)"
    assert rb["toward"] == ("Toward the decision: 3 settled so far. It is decided after Week 18 of 2026 if 40 settle "
                            "in the 2026 regular season, and otherwise after the 2027 regular season, on both seasons "
                            "pooled.")                       # nfl-weather amendments 4 to 6: not "40 it needs"
    assert by["nfl_rule_b_backup"]["summary"]["units"] == "+0.91"
    assert by["nfl_rule_b_backup"]["summary"]["toward"].startswith("Not part of any decision")
    assert by["nfl_rule_b_backup"]["summary"]["decision"] == ""              # it never has one to come
    assert rb["decision"] == "Interim read, which decides nothing."
    assert by["nfl_lean"]["summary"]["units"] == "+0.91" and by["nfl_lean"]["kind"] == "watch"
    cb = by["cfb_rule_b"]["summary"]
    assert (cb["record"], cb["units"], cb["roi"]) == ("1-1-0", f"{MINUS}0.08", f"{MINUS}4.1% per bet placed")
    ht = by["cfb_rule_ht"]["summary"]
    assert (ht["record"], ht["units"], ht["roi"]) == ("1-1-0", f"{MINUS}0.09", f"{MINUS}4.5% per bet placed")
    assert ht["clv"].startswith("Not graded on closing-line value") and ht["bar_clv"] == ""
    # the signal rules together: the model lean is a watch and is left out
    t = d["together"]
    all_units = (W108 - 1 + 0) + W110 + (W109 - 1) + (W110 - 1)
    a = t["all"]["summary"]
    assert (a["settled"], a["pending"], a["void"]) == (8, 4, 2)
    assert a["record"] == "4-3-1" and a["units_num"] == pytest.approx(all_units)
    assert a["units"] == f"+{all_units:.2f}" == "+0.66"
    assert a["roi"] == f"+{100 * all_units / 8:.1f}% per bet placed" == "+8.3% per bet placed"
    assert a["win_rate"] == "57.1% of the 7 that won or lost"
    assert a["clv_num"] == pytest.approx((1.0 - 0.5 + 1.0 + 0.5 + 1.0 - 0.5) / 6)
    assert a["clv"] == "Closing-line value: +0.42 points on average, over 6 bets with a close."
    assert a["interval"] == "No registered interval for rules together: each rule's interval is its own."
    assert a["paper"] == "Paper bets. No money was placed."
    n = t["nfl"]["summary"]
    assert (n["record"], n["units_num"], n["pending"], n["void"]) == ("2-1-1", pytest.approx(W108 - 1 + W110), 2, 1)
    assert n["roi"] == f"+{100 * (W108 - 1 + W110) / 4:.1f}% per bet placed" == "+20.9% per bet placed"
    c = t["cfb"]["summary"]
    assert (c["record"], c["units"], c["roi"]) == ("2-2-0", f"{MINUS}0.17", f"{MINUS}4.3% per bet placed")
    assert c["clv_num"] == pytest.approx(0.25)                   # Rule HT has no closing-line value
    assert "model lean is a watch" in t["all"]["note"] and "model lean" not in t["cfb"]["note"]
    # each total says whether it clears the project's bar (0.05 / 271 variants in the fixtures' STATUS.md)
    assert d["variants"] == 271 and d["bar"] == "0.000185"
    for s in [r["summary"] for r in d["rules"]] + [x["summary"] for x in t.values()]:
        assert "multiple-testing bar" in s["bar_win"] and s["sample"]


def exact_tail(prices_won_lost):
    """P(at least this many wins) by brute force over every way the decided bets could have gone."""
    probs = [1 / (1 + (100 / abs(p) if p < 0 else p / 100)) for p, _ in prices_won_lost]
    wins = sum(w for _, w in prices_won_lost)
    total = 0.0
    for outcome in itertools.product((0, 1), repeat=len(probs)):
        if sum(outcome) >= wins:
            total += math.prod(q if o else 1 - q for q, o in zip(probs, outcome))
    return total


def test_the_p_values_are_the_registered_arithmetic(root, home):
    d = api.signals_screen(rich_store(root, home))
    a = d["together"]["all"]["summary"]
    expect = exact_tail([(-108, 1), (-112, 0), (-110, 1), (-109, 1), (-110, 0), (-110, 1), (-112, 0)])
    assert a["p_win"] == pytest.approx(expect)
    assert f"One-sided p = {expect:.2f}" in a["bar_win"] and "Does not clear the multiple-testing bar" in a["bar_win"]
    # with one price for every bet it is the ordinary binomial test (60 of 100 at -110: scipy's binom.sf(59, 100, p))
    bets = [{"outcome": "won" if i < 60 else "lost", "entry_price": -110} for i in range(100)]
    assert signals.p_beat_break_even(bets) == pytest.approx(0.0765999141954799)
    assert signals.p_beat_break_even([{"outcome": "push"}]) is None
    # Student's t, against scipy's stats.t.sf
    for t, df, sf in [(2.0, 10, 0.03669401738537018), (1.0, 1, 0.25), (0.0, 5, 0.5), (-2.0, 10, 0.9633059826146299),
                      (2.5, 3, 0.04385332350403278), (4.0, 40, 0.00013295619783334903),
                      (1.3, 2, 0.16162351590802018), (0.7, 100, 0.24277630322718666)]:
        assert signals.t_sf(t, df) == pytest.approx(sf, rel=1e-9, abs=1e-13)
    same = [{"outcome": "won", "clv": 0.5, "kickoff_utc": f"2026-10-{d:02d}T17:00:00Z"} for d in (4, 11)]
    assert signals.clv_test(same)["p"] is None and "same closing-line value" in signals.clv_test(same)["why"]


def test_a_result_that_clears_the_bar_is_said_so():
    bar = signals.Bar("- **Variants:** **100**\n")
    assert bar.value == pytest.approx(0.0005)
    assert bar.sentence(0.0001, "x", "") == ("One-sided p = 0.0001 (x). Clears the multiple-testing bar, p < 0.0005 "
                                             "(0.05 / 100 variants).")
    assert bar.finding(0.0001, "break-even") == "better than break-even, and it clears the multiple-testing bar"
    assert bar.finding(0.01, "break-even") == ("better than break-even at p = 0.01, short of the multiple-testing "
                                               "bar")
    assert bar.finding(0.4, "zero") == "not distinguishable from zero"
    assert signals.Bar(None).sentence(0.0001, "x", "").endswith("so it is not counted as clearing it.")


def test_the_rows_of_the_log(root, home):
    d = api.signals_screen(rich_store(root, home))
    rows = d["bets"]
    assert len(rows) == 15
    kicks = [r["kick_utc"] for r in rows]
    assert kicks == sorted(kicks, reverse=True)                               # newest first
    by = {(r["rule"], r["game_id"]): r for r in rows}
    buf = by[("nfl_rule_b", "2026_06_BUF_NYJ")]
    assert (buf["kickoff"], buf["matchup"], buf["entry"], buf["entry_source"]) == (
        "Sun Oct 11, 1:00 PM ET", "BUF at NYJ", f"Under 41.5 at {MINUS}108", "Pinnacle")
    assert buf["logged"] == "Logged Fri Oct 9, 7:30 AM"
    assert (buf["close"], buf["close_source"], buf["clv"], buf["final_total"]) == (
        "40.5", "Closing total, nflverse schedule", "+1.0", "37")
    assert (buf["result"], buf["result_words"], buf["units"]) == ("won", "Won", "+0.93")
    mia = by[("nfl_rule_b", "2026_06_MIA_CLE")]
    assert (mia["result_words"], mia["units"], mia["void_reason"]) == (
        "Void", "", "The game kicked off more than 24 hours from the kickoff on its entry row")
    nyg = by[("nfl_rule_b_backup", "2026_08_NYG_PHI")]
    assert nyg["entry"] == "Under 45.0 at an assumed −110" and nyg["entry_source"] == "the consensus line (nflverse)"
    assert by[("nfl_lean", "2026_06_LV_LAC")]["entry"] == f"Over 47.5 at {MINUS}110"
    army = by[("cfb_rule_b", "401000102")]
    assert (army["close"], army["close_source"], army["clv"]) == ("39.0", "Captured close (Pinnacle)", f"{MINUS}0.5")
    assert by[("cfb_rule_b", "401000101")]["close_source"] == "Last quote before kickoff (Pinnacle)"
    osu = by[("cfb_rule_ht", "401000201")]
    assert (osu["close"], osu["close_source"], osu["clv"]) == ("63.5", "Captured close (secondary)", "")
    # the one game still to kick off whose newest row is a signal: tinted, with its badge; nothing else
    live = [r for r in rows if r["live"]]
    assert [(r["game_id"], r["badge"]) for r in live] == [("401000103", "signal")]


@needs_node
def test_the_signals_screen_as_drawn(root, home, tmp_path):
    answer = api.signals_screen(rich_store(root, home))
    page = draw(tmp_path, "#signals", answer)
    drawn = text(page)
    assert page["doc_title"] == "(1) Value Finder"
    assert "Paper bets. No money was placed." in drawn and "Signalthe rule fired at its registered price" in drawn
    heads, trs = table_rows(page, "Date and kickoff (ET)")
    assert heads == ["Date and kickoff (ET)", "Game", "Rule", "Entry", "Close", "Closing-line value (points)",
                     "Final total", "Result", "Units"]
    assert len(trs) == 15
    tinted = [tr for tr in trs if "signal" in tr["cls"].split()]
    assert len(tinted) == 1 and "Utah at BYU" in text(tinted[0]) and "Signal" in text(tinted[0])
    links = [a["attrs"]["href"] for tr in trs for a in find(tr, "a")]
    assert "#game/2026_06_BUF_NYJ" in links and "#game/401000103" in links      # a row opens the game's page
    lean = next(tr for tr in trs if "LV at LAC" in text(tr))
    assert [text(b) for b in find(lean, "span", "badge")] == ["Watch", "Won"]
    results = {text(b) for tr in trs for b in find(tr, "span", "badge") if b["cls"].split()[1] in
               ("won", "lost", "push", "pending", "void")}
    assert results == {"Won", "Lost", "Push", "Pending", "Void"}
    # the cards: the signal rules together first, then each rule, each with its sample size and the bar
    cards = list(find(page, "div", "card"))
    assert text(cards[0]).startswith("All signal rules together8 settled bets, 4 waiting for a result, 2 void")
    assert [text(next(find(c, "h3"))) for c in cards] == [
        "All signal rules together", "NFL wind rule", "NFL wind rule, backup price", "NFL model lean",
        "College football wind rule", "College football high-total rule"]
    for c in cards:
        assert "Paper bets. No money was placed." in text(c) and "multiple-testing bar" in text(c)
    # the two charts: titles that say what was found, break-even drawn, the axis not cropped
    charts = list(find(page, "div", "chart"))
    assert [text(next(find(c, "h2"))).split("Cumulative")[0].split("Closing-line value per bet")[0] for c in charts] == [
        "Up 0.66 units after 8 settled bets: not distinguishable from break-even",
        "Closing-line value averages +0.42 points over 6 bets: not distinguishable from zero"]
    units_svg = next(find(charts[0], "svg"))
    labels = [text(t) for t in find(units_svg, "text")]
    assert "Break-even" in labels and "0" in labels
    ticks = [float(x.replace(MINUS, "-")) for x in labels if x.replace(MINUS, "").replace("+", "").replace(".", "").isdigit()]
    assert min(ticks) <= 0 <= max(ticks) and max(ticks) - min(ticks) >= 4
    assert "Sample: 8 settled bets." in text(charts[0]) and "Sample: 6 bets with a close, over 4 game days." in text(charts[1])
    assert "Each betRunning mean" in text(charts[1])
    dots = list(find(next(find(charts[1], "svg")), "circle", "dot"))
    assert len(dots) == 6


@needs_node
def test_the_filters_are_kept_in_the_address(root, home, tmp_path):
    answer = api.signals_screen(rich_store(root, home))
    page = draw(tmp_path, "#signals?sport=cfb&rule=cfb_rule_ht&result=won", answer)
    _, trs = table_rows(page, "Date and kickoff (ET)")
    assert [text(next(find(tr, "a"))) for tr in trs] == ["Ohio State at Michigan"]
    selected = [text(o) for o in find(page, "option") if "selected" in o["attrs"]]
    assert selected == ["College football high-total rule", "Won"]
    cards = [text(next(find(c, "h3"))) for c in find(page, "div", "card")]
    assert cards == ["College football high-total rule"]
    charts = list(find(page, "div", "chart"))
    assert "Rule HT is graded on its results at the price taken, not on closing-line value." in text(charts[1])
    assert "Down 0.09 units after 2 settled bets" in text(charts[0])
    # a rule from the other sport is not kept with a sport it isn't in
    page = draw(tmp_path, "#signals?sport=nfl&rule=cfb_rule_ht", answer)
    assert [text(next(find(c, "h3"))) for c in find(page, "div", "card")][0] == "NFL signal rules together"


@needs_node
def test_fewer_than_two_settled_bets_is_a_sentence_not_a_chart(root, home, tmp_path):
    one = scorer_doc("cfb-weather", "x\n", [doc_test("RULE_B", "Rule B", RICH_CFB_DOC["tests"][0]["bets"][:1]),
                                            doc_test("RULE_HT", "Rule HT", [])])
    empty_nfl = scorer_doc("nfl-weather", "x\n", [doc_test(t, t, []) for t in ("RULE_B", "RULE_B_SECONDARY",
                                                                               "MODEL_LEAN")])
    store = make_store(root, home, clock=Clock(LATER), runner=FakeRunner(nfl_doc=empty_nfl, cfb_doc=one))
    page = draw(tmp_path, "#signals", api.signals_screen(store))
    charts = list(find(page, "div", "chart"))
    assert not list(find(charts[0], "svg")) and "Only 1 settled bet, so there is nothing to chart yet." in text(charts[0])
    assert "Only 1 settled bet with a closing line, so there is nothing to chart yet." in text(charts[1])


# ------------------------------------------------------------------ before the first signal
def no_bets_runner():
    return FakeRunner(nfl_doc=scorer_doc("nfl-weather", "x\n", [doc_test(t, t, []) for t in (
        "RULE_B", "RULE_B_SECONDARY", "MODEL_LEAN")]), cfb_doc=scorer_doc("cfb-weather", "x\n", [
            doc_test("RULE_B", "Rule B", []), doc_test("RULE_HT", "Rule HT", [])]))


@needs_node
def test_the_empty_screen(root, home, tmp_path):
    store = make_store(root, home, clock=Clock(datetime(2026, 9, 29, 17, 0, tzinfo=UTC)), runner=no_bets_runner())
    d = api.signals_screen(store)
    assert d["empty"]["text"] == ("No rule has signalled yet. College football's wind rule starts Thursday, October 1; "
                                  "the high-total rule on October 6; the NFL's wind rule on October 8.")
    assert d["empty"]["next"].startswith("When a rule signals, each bet appears here")
    drawn = text(draw(tmp_path, "#signals", d))
    assert d["empty"]["text"] in drawn and "Signalthe rule fired at its registered price" in drawn
    # after the first start: past tense for what has started
    store = make_store(root, home, clock=Clock(datetime(2026, 10, 2, 17, 0, tzinfo=UTC)), runner=no_bets_runner())
    assert api.signals_screen(store)["empty"]["text"] == (
        "No rule has signalled yet. College football's wind rule started Thursday, October 1; the high-total rule "
        "starts on October 6; the NFL's wind rule on October 8.")


def test_the_empty_screen_reads_its_dates_from_the_content_file(root, home, tmp_path):
    content = copy_content(tmp_path / "content")
    tests = json.loads((content / "forward_tests.json").read_text())
    for t in tests:
        if t["id"] == "nfl_rule_b":
            t["starts_text"], t["starts_utc"] = "Week 6, Thu Oct 15, 2026", "2026-10-15T00:00:00Z"
    (content / "forward_tests.json").write_text(json.dumps(tests))
    store = make_store(root, home, clock=Clock(datetime(2026, 9, 29, 17, 0, tzinfo=UTC)), runner=no_bets_runner(),
                       content=content)
    assert api.signals_screen(store)["empty"]["text"].endswith("the NFL's wind rule on October 15.")


# ------------------------------------------------------------------ a scorer that fails
@pytest.mark.parametrize("mode, said", [
    ("failed", "The NFL scorer stopped with an error"), ("timeout", "The NFL scorer took more than 60 seconds"),
    ("not_document", "The NFL scorer printed something that is not the report the dashboard reads"),
    ("missing", "The NFL scorer can't be run here")])
def test_a_failing_scorer_is_said_and_the_ledgers_are_shown(root, home, mode, said):
    """Without the scorer's document the screen says so and lists the games whose logged rows include a signal,
    from the ledgers, without results."""
    store = make_store(root, home, clock=Clock(datetime(2026, 10, 12, 17, 0, tzinfo=UTC)),
                       runner=FakeRunner(scorer=mode))
    d = api.signals_screen(store)
    assert d["trouble"][0].startswith(said)
    # the NFL's ledger has no signal since its rule started; the college ledger has two, listed below
    assert d["trouble"][0].endswith("Its ledger shows no game that has signalled since its rule started.")
    assert d["trouble"][1].endswith("The games that signalled are listed below from the ledgers, without results.")
    assert d["bets"] == [] and d["empty"] is None
    games = {(f["rule"], f["game_id"]) for f in d["fallback"]}
    # college football: Army at Navy (Rule B, Oct 2) and Ohio State at Michigan (Rule HT, Oct 10) signalled after
    # their rules started; the NFL's signals were all before Week 5 (Oct 8), so none is listed
    assert games == {("cfb_rule_b", "401000001"), ("cfb_rule_ht", "401000002")}
    army = next(f for f in d["fallback"] if f["game_id"] == "401000001")
    assert army["logged"] == "First logged Fri Oct 2, 7:30 AM" and army["entry"] == f"Under 55.0 at {MINUS}109"
    assert "only the scorer grades" in d["fallback_note"]
    assert all(r["summary"] is None for r in d["rules"])


@needs_node
def test_a_failing_scorer_as_drawn(root, home, tmp_path):
    store = make_store(root, home, clock=Clock(datetime(2026, 10, 12, 17, 0, tzinfo=UTC)),
                       runner=FakeRunner(scorer="failed"))
    drawn = text(draw(tmp_path, "#signals", api.signals_screen(store)))
    assert "The NFL scorer stopped with an error" in drawn and "Games that signalled, from the ledgers" in drawn
    assert "Not known: only the scorer grades" in drawn and "Its scorer could not be read" in drawn


def test_odd_values_in_a_document_never_break_the_screen(root, home):
    bad = json.loads(json.dumps(RICH_CFB_DOC))
    t = bad["tests"][0]
    t["record"], t["units"], t["interval"], t["decisions"] = [1, 2], "lots", "wide", ["not a decision"]
    t["bets"][0]["units"], t["bets"][1]["clv"], t["bets"][2]["entry_line"] = "x", float("nan"), True
    store = make_store(root, home, clock=Clock(LATER), runner=FakeRunner(nfl_doc=RICH_NFL_DOC, cfb_doc=bad))
    d = api.signals_screen(store)
    assert "error" not in d and not any("could not be shown" in n for n in d["notes"])
    rb = {r["id"]: r for r in d["rules"]}["cfb_rule_b"]["summary"]
    assert rb["record"] == "1-1-0" and rb["units"] == f"{MINUS}1.00"          # worked out from the bets it could read
    utah = next(b for b in d["bets"] if b["game_id"] == "401000103")
    assert utah["entry"] == "No number logged"


# ------------------------------------------------------------------ the game page and the Forward tests screen
def test_the_game_page_says_the_newest_row_is_a_signal(store):
    _, g = api.game(store, "2026_05_BUF_NE")
    assert (g["game"]["badge"], g["game"]["badge_words"]) == ("signal", "The newest row is a signal.")
    _, g = api.game(store, "2026_05_TEN_BAL")
    assert g["game"]["badge"] == "backup"
    _, g = api.game(store, "2026_05_ARI_NYG")
    assert (g["game"]["badge"], g["game"]["badge_words"]) == ("watch", "The newest row is a watch, not a bet.")
    _, g = api.game(store, "2026_05_KC_DEN")                  # a signal earlier, no longer
    assert g["game"]["badge"] == "" and [r["badge"] for r in g["rows"]] == ["signal", ""]


@needs_node
def test_the_game_page_as_drawn(store, tmp_path):
    _, g = api.game(store, "2026_05_BUF_NE")
    page = draw(tmp_path, "#game/2026_05_BUF_NE", g)
    assert "Signal The newest row is a signal." in text(page)
    _, trs = table_rows(page, "Logged")
    assert all("signal" in tr["cls"].split() for tr in trs)
    assert [text(b) for tr in trs for b in find(tr, "span", "badge")] == ["Signal"]
    _, g = api.game(store, "2026_05_KC_DEN")                  # signalled on its first row, not on its newest
    page = draw(tmp_path, "#game/2026_05_KC_DEN", g)
    assert "The newest row is" not in text(page)
    _, trs = table_rows(page, "Logged")
    assert [("signal" in tr["cls"].split()) for tr in trs] == [True, False]


def test_the_forward_tests_screen_reads_the_same_document(store, runner):
    d = api.tests_screen(store)
    nfl, cfb = d["groups"]
    assert nfl["scorer"]["text"] == NFL_DOC["text"] and cfb["scorer"]["text"] == CFB_DOC["text"]
    assert cfb["tests"][0]["scorer_counts"] == {"signals": 1, "settled": 0, "pending": 1, "void": 0}
    api.signals_screen(store)                                 # the same preview, not a second run
    assert sum(1 for c, _, _ in runner.calls if "--now" in c) == 2


def test_badges_in_words():
    assert [words.badge("rule_b", v) for v in ("SIGNAL", "SIGNAL_SECONDARY", "price_too_high", "no_price",
                                               "outside_horizon", "negative_ev", "no_trigger", "not_outdoor")] == [
        "signal", "backup", "watch", "watch", "watch", "watch", "", ""]
    assert [words.badge("rule_ht", v) for v in ("SIGNAL", "price_too_high", "below_threshold")] == ["signal", "", ""]
    assert [words.badge("lean", v) for v in ("UNDER lean", "OVER lean", "")] == ["watch", "watch", ""]
    assert words.until(datetime(2026, 10, 4, 17, 0, tzinfo=UTC), datetime(2026, 10, 2, 17, 0, tzinfo=UTC)) == "in 2 days"
    assert words.until(datetime(2026, 10, 2, 20, 10, tzinfo=UTC), datetime(2026, 10, 2, 17, 0, tzinfo=UTC)) == (
        "in 3 hours, 10 minutes")


# ------------------------------------------------------------------ added after the first worker stopped
def test_a_signal_on_a_game_with_no_kickoff_time_in_the_panel(root, home, tmp_path):
    """A college game logged with cfbfastR's placeholder (midnight Eastern, wx_src time_tbd) whose Rule HT signals:
    the panel lists it with its date and "time not set", never the placeholder as a kickoff or a countdown."""
    with (root / "cfb-weather" / "data" / "forward" / "ledger.csv").open("a") as f:
        f.write(cfb_row("2026-10-02T14:30:14Z", "401000010", "Sat 10-10 00:00", "Air Force", "Army", "time_tbd",
                        "SIGNAL", "2026-10-10 04:00:00+00:00", total="64.5", src="time_tbd") + "\n")
    store = make_store(root, home, clock=Clock(datetime(2026, 10, 3, 17, 0, tzinfo=UTC)))
    d = api.home(store)
    af = next(s for s in d["live"] if s["game_id"] == "401000010")
    assert (af["badge"], af["rule"], af["kickoff"], af["until"]) == (
        "signal", "High-total rule (Rule HT)", "Sat Oct 10, time not set", "Kickoff time not set")
    assert af["take"] == f"Under 64.5 at {MINUS}109, Pinnacle" and "12:00 AM" not in str(af)
    assert d["header"]["signals_live"] == len(d["live"]) == api.summary(store)["signals_live"]
    if NODE:
        page = draw(tmp_path, "#home", d)
        row = next(li for li in find(next(find(page, "section", "live")), "li") if "Air Force at Army" in text(li))
        assert "Sat Oct 10, time not set" in text(row) and "Kickoff time not set" in text(row)
        assert [text(b) for b in find(row, "span", "badge")] == ["Signal"]
        assert page["doc_title"] == f"({len(d['live'])}) Value Finder"


def lean_on_a_live_game():
    """The NFL document with a model lean on BUF at NE, whose newest row is a Rule B signal at Pinnacle's price."""
    doc = json.loads(json.dumps(NFL_DOC))
    lean = next(t for t in doc["tests"] if t["id"] == "MODEL_LEAN")
    lean.update(doc_test("MODEL_LEAN", "Model lean", [
        bet("2026_05_BUF_NE", "BUF", "NE", "2026-10-04T17:00:00Z", "2026-10-01T14:30:07Z", 44.5, -110.0, "pinnacle",
            "pending")]))
    return doc


def test_a_lean_is_never_drawn_in_the_signal_colour(root, home, tmp_path):
    """The log tints a bet's row only when its own rule signals on the game's newest row: the Rule B bet on BUF at NE
    is tinted with its Signal badge, the model lean on the same game (a watch) is not, and the backup-price bet on
    TEN at BAL carries the outlined badge."""
    store = make_store(root, home, runner=FakeRunner(nfl_doc=lean_on_a_live_game()))
    d = api.signals_screen(store)
    by = {(r["rule"], r["game_id"]): r for r in d["bets"]}
    assert (by[("nfl_rule_b", "2026_05_BUF_NE")]["live"], by[("nfl_rule_b", "2026_05_BUF_NE")]["badge"]) == (
        True, "signal")
    assert (by[("nfl_lean", "2026_05_BUF_NE")]["live"], by[("nfl_lean", "2026_05_BUF_NE")]["badge"]) == (False, "")
    assert by[("nfl_rule_b_backup", "2026_05_TEN_BAL")]["badge"] == "backup"
    assert not any(r["live"] for r in d["bets"] if r["rule_kind"] == "watch")
    if NODE:
        _, trs = table_rows(draw(tmp_path, "#signals", d), "Date and kickoff (ET)")
        lean = next(tr for tr in trs if "NFL model lean" in text(tr))
        assert "signal" not in lean["cls"].split()
        assert [text(b) for b in find(lean, "span", "badge")] == ["Watch", "Pending"]
        rb = next(tr for tr in trs if "BUF at NE" in text(tr) and "NFL wind rule" in text(tr)
                  and "backup" not in text(tr))
        assert "signal" in rb["cls"].split() and [text(b) for b in find(rb, "span", "badge")][0] == "Signal"
        ten = next(tr for tr in trs if "TEN at BAL" in text(tr))
        assert "signal" in ten["cls"].split() and "Signal, backup price" in [text(b) for b in find(ten, "span",
                                                                                                    "badge")]


@pytest.mark.parametrize("printed", [
    "[" * 200_000 + "]" * 200_000,                                  # nested deeper than Python reads
    json.dumps({"text": "x", "tests": [{"id": "RULE_B"}]}),        # a test without its counts and bets
    json.dumps({"tests": []}),                                      # no report
    json.dumps({"text": "x", "tests": [{"id": "RULE_B", "counts": {}, "bets": ["a bet"]}]}),
    json.dumps({"text": "x" * (data.DOCUMENT_BYTES + 1), "tests": []}),   # too big to be the document
    "ledger rows: 8\n", "", "null", "{"])
def test_what_is_not_a_document_is_said_plainly(root, home, printed):
    assert data.read_document(printed) is None
    store = make_store(root, home, runner=FakeRunner(raw=printed))
    d = api.signals_screen(store)
    assert d["trouble"] == ["The NFL scorer printed something that is not the report the dashboard reads (its --json "
                            "document), so its read is not shown. Its ledger shows no game that has signalled since "
                            "its rule started."]
    assert not any("could not be shown" in n for n in d["notes"]) and "error" not in d
    t = api.tests_screen(store)
    assert t["groups"][0]["scorer"]["status"] == "not_document" and len(t["groups"][0]["scorer"]["error"]) <= 1200


NOT_THE_DOCUMENT = ("The NFL scorer printed something that is not the report the dashboard reads (its --json "
                    "document), so its read is not shown. Its ledger shows no game that has signalled since its rule "
                    "started.")
NO_BETS = {"signals": 0, "settled": 0, "pending": 0, "void": 0}


@pytest.mark.parametrize("tests", [
    [],                                                                     # no test at all
    [{"id": "SOMETHING_ELSE", "counts": NO_BETS, "bets": []}],             # only an id the dashboard doesn't know
    [{"id": "RULE_B", "counts": NO_BETS, "bets": []}]])                    # one of the scorer's three tests
def test_a_document_without_its_tests_is_said_plainly(root, home, tests):
    """A well-formed document that lacks the scorer's own tests is not read as "No rule has signalled yet" with
    nothing said: it is not the scorer's document, the screen says so in plain words, and the ledgers are listed."""
    printed = json.dumps({"text": "ledger rows: 1\n", "tests": tests})
    assert data.read_document(printed, data.TEST_IDS["nfl-weather"]) is None
    store = make_store(root, home, runner=FakeRunner(raw=printed))
    d = api.signals_screen(store)
    assert d["trouble"] == [NOT_THE_DOCUMENT]
    assert api.tests_screen(store)["groups"][0]["scorer"]["status"] == "not_document"
    for drawn in (d, api.home(store)):
        assert "error" not in drawn


def test_the_test_ids_a_document_must_hold_are_the_logs_rules():
    assert {p: set(ids) for p, ids in data.TEST_IDS.items()} == {
        p: {r["test"] for r in signals.LOG_RULES if r["project"] == p} for p in data.PROJECTS}


def test_a_document_with_odd_fields_is_still_read(root, home):
    """Missing optional fields (no record, no interval, no decisions, a bet with only its outcome) are shown as not
    known; nothing breaks."""
    doc = {"text": "ledger rows: 1\n", "tests": [{"id": "RULE_B", "counts": {"signals": 1, "settled": 1, "pending": 0,
                                                                          "void": 0},
                                                  "bets": [{"outcome": "won"}]},
                                                 {"id": "RULE_B_SECONDARY", "counts": NO_BETS, "bets": []},
                                                 {"id": "MODEL_LEAN", "counts": NO_BETS, "bets": []}]}
    store = make_store(root, home, runner=FakeRunner(raw=json.dumps(doc)))
    d = api.signals_screen(store)
    assert d["trouble"] == [] and not any("could not be shown" in n for n in d["notes"])
    row = next(r for r in d["bets"] if r["rule"] == "nfl_rule_b")
    assert (row["matchup"], row["entry"], row["result_words"], row["units"]) == ("Game ?", "No number logged", "Won", "")


def test_the_empty_screen_without_the_content_file(root, home, tmp_path):
    content = copy_content(tmp_path / "content")
    (content / "forward_tests.json").write_text("{ not json")
    store = make_store(root, home, clock=Clock(datetime(2026, 9, 29, 17, 0, tzinfo=UTC)), runner=no_bets_runner(),
                       content=content)
    d = api.signals_screen(store)
    assert d["empty"]["text"] == ("No rule has signalled yet. When each rule starts could not be read from the "
                                  "forward-test descriptions (dashboard/content/forward_tests.json).")
    assert any("forward_tests.json" in n for n in d["notes"])
