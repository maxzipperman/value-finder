"""The Signals screen: every bet the scorers count, newest first, with its entry, its close and its result, from each
scorer's --json document (run as a preview, with --now; see commands.py). Above the table, per rule and for the
signal rules together: the record, the units and the return per bet placed, the mean closing-line value with the
registered interval, the count toward the decision, each with its sample size and whether it clears the project's
multiple-testing bar. Two small charts: cumulative units by date, and closing-line value per bet with its running
mean.

The per-rule numbers are the scorer's own (its document holds the numbers its printed report shows). The totals for
rules together, the p-values and the charts are worked out here from the scorer's bets, with the same arithmetic the
scorers use. Nothing here grades or decides anything.

When a scorer fails, takes too long or prints something that is not its document, the screen says so and lists what
the ledgers show: the games whose logged rows include a signal, without results."""
from __future__ import annotations

import math
import re
from datetime import date

from . import status_md, words
from .data import PROJECTS, SPORT_OF
from .ledger import RULES, get

PAPER = "Paper bets. No money was placed."
# What the screen adds when a scorer's document can't be read: the ledgers' games that signalled, or that there are none
LISTED = "The games that signalled are listed below from the ledgers, without results."
NONE_LISTED = "Its ledger shows no game that has signalled since its rule started."
# The rules the log shows, in this order. "kind" is the badge the rule's bets carry when their game is live: a
# signal, a signal at the NFL's backup price, or a watch (the model lean, which is logged and graded but never a bet).
LOG_RULES = [
    {"id": "nfl_rule_b", "project": "nfl-weather", "sport_key": "nfl", "test": "RULE_B", "name": "NFL wind rule",
     "kind": "signal", "column": "rule_b", "content": "nfl_rule_b", "target": 40,
     "toward": "Toward the decision: {settled} of the 40 settled bets it needs."},
    {"id": "nfl_rule_b_backup", "project": "nfl-weather", "sport_key": "nfl", "test": "RULE_B_SECONDARY",
     "name": "NFL wind rule, backup price", "kind": "backup", "column": "rule_b", "content": "nfl_rule_b",
     "target": None, "toward": "Not part of any decision: a signal at the backup price is reported apart."},
    {"id": "nfl_lean", "project": "nfl-weather", "sport_key": "nfl", "test": "MODEL_LEAN", "name": "NFL model lean",
     "kind": "watch", "column": "lean", "content": "nfl_lean", "target": 40,
     "toward": "Toward its decision: {settled} of the 40 settled leans it needs. A lean is a watch: logged and "
               "graded, never a bet."},
    {"id": "cfb_rule_b", "project": "cfb-weather", "sport_key": "cfb", "test": "RULE_B",
     "name": "College football wind rule", "kind": "signal", "column": "rule_b", "content": "cfb_rule_b",
     "target": 40, "toward": "Toward the decision: {settled} of the 40 settled bets it needs."},
    {"id": "cfb_rule_ht", "project": "cfb-weather", "sport_key": "cfb", "test": "RULE_HT",
     "name": "College football high-total rule", "kind": "signal", "column": "rule_ht", "content": "cfb_rule_ht",
     "target": None, "toward": "Toward the decision: {settled} settled. It is decided once, after the 2027 season's "
                               "title game; about 105 bets are expected."},
]
BY_ID = {r["id"]: r for r in LOG_RULES}
TOGETHER = {"all": "All signal rules together", "nfl": "NFL signal rules together",
            "cfb": "College football signal rules together"}
RESULT_WORDS = {"won": "Won", "lost": "Lost", "push": "Push", "pending": "Pending", "void": "Void"}
# The rules the empty screen names, with when each starts (from dashboard/content/forward_tests.json)
STARTS = {"cfb_rule_b": "college football's wind rule", "cfb_rule_ht": "the high-total rule",
          "nfl_rule_b": "the NFL's wind rule"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], start=1)}
START_DAY = re.compile(r"\b(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|"
                       r"dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", re.IGNORECASE)


# ---------------------------------------------------------------- a bet, as read from a document

NUMBERS = ("entry_line", "entry_price", "close_line", "clv", "captured_close", "clv_captured", "final_total", "units")
TEXTS = ("game_id", "away_team", "home_team", "kickoff_utc", "logged_utc", "side", "price_source", "close_source",
         "close_from", "outcome", "void_reason")


def number(v) -> float | None:
    """A finite number, or None (a document's null, or anything that isn't a number)."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def clean(b: dict) -> dict:
    """A bet with every number a number or None and every text a string or None, whatever the document held."""
    out = {k: number(b.get(k)) for k in NUMBERS} | {k: None if b.get(k) is None else str(b.get(k)) for k in TEXTS}
    out["price_assumed"] = b.get("price_assumed") is True
    return out


# ---------------------------------------------------------------- the arithmetic

def profit_if_won(price) -> float:
    """Units won per unit staked at American odds; an assumed −110 when no price was logged (as the NFL scorer
    grades such a bet)."""
    p = words.num(price)
    if p is None or abs(p) < 100:
        p = -110.0
    return 100 / abs(p) if p < 0 else p / 100


def p_beat_break_even(bets: list[dict]) -> float | None:
    """One-sided p that the bets that won or lost did at least this well by chance: exact, each bet winning with the
    break-even chance of its own price, pushes left out (the test the college football scorer registers for Rule HT,
    and the one the page uses for every rule's win rate). None when no bet has won or lost."""
    decided = [b for b in bets if b.get("outcome") in ("won", "lost")]
    if not decided:
        return None
    dist = [1.0]
    for b in decided:
        q = 1 / (1 + profit_if_won(b.get("entry_price")))
        nxt = [0.0] * (len(dist) + 1)
        for k, v in enumerate(dist):
            nxt[k] += v * (1 - q)
            nxt[k + 1] += v * q
        dist = nxt
    wins = sum(1 for b in decided if b["outcome"] == "won")
    return min(1.0, max(0.0, sum(dist[wins:])))


def _betacf(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta function (Lentz's method)."""
    tiny, qab, qap, qam = 1e-300, a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1 + aa * d
            d = 1 / (d if abs(d) > tiny else tiny)
            c = 1 + aa / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """The regularized incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b


def t_sf(t: float, df: float) -> float:
    """P(T > t) for Student's t with df degrees of freedom."""
    tail = 0.5 * _betai(df / 2, 0.5, df / (df + t * t))
    return tail if t >= 0 else 1 - tail


def game_day(b: dict) -> str:
    """A bet's game day: the Eastern date of its game's kickoff (the scorers group the CLV interval by it)."""
    t = words.parse_utc(b.get("kickoff_utc"))
    return t.astimezone(words.EASTERN).date().isoformat() if t else "?"


def clv_test(bets: list[dict]) -> dict:
    """Mean closing-line value over the bets that have one, and a one-sided p that it is above zero: the larger of
    the plain t-test's and the one grouped by game day, the two the registered interval is the wider of. p is None
    with fewer than 2 bets or 2 game days, or when every bet has the same value (then `why` says so)."""
    xs = [(b["clv"], game_day(b)) for b in bets if isinstance(b.get("clv"), (int, float))]
    n = len(xs)
    out = {"n": n, "G": len({d for _, d in xs}), "mean": None, "p": None, "why": ""}
    if not n:
        out["why"] = "no settled bet has a closing line yet"
        return out
    m = sum(x for x, _ in xs) / n
    out["mean"] = m
    if n < 2 or out["G"] < 2:
        out["why"] = ("a test needs at least 2 bets with a close" if n < 2 else
                      "a test needs bets on at least 2 game days")
        return out
    by_day: dict[str, float] = {}
    for x, d in xs:
        by_day[d] = by_day.get(d, 0.0) + (x - m)
    G = out["G"]
    se_plain = math.sqrt(sum((x - m) ** 2 for x, _ in xs) / (n - 1) / n)
    se_grouped = math.sqrt(G / (G - 1) * sum(v * v for v in by_day.values()) / n ** 2)
    if se_plain < 1e-12 or se_grouped < 1e-12:
        out["why"] = "every bet has the same closing-line value, so there is nothing to test"
        return out
    out["p"] = max(t_sf(m / se_plain, n - 1), t_sf(m / se_grouped, G - 1))
    return out


class Bar:
    """The project's multiple-testing bar, read from STATUS.md's "Variants" bullet."""

    def __init__(self, status_text: str | None):
        self.variants = status_md.variants(status_text or "") if status_text else None
        self.text = status_md.bar(self.variants)
        self.value = 0.05 / self.variants if self.variants else None

    def sentence(self, p: float | None, what: str, untested: str) -> str:
        """Whether a result clears the bar, in one or two plain sentences."""
        if p is None:
            return f"Not tested against the multiple-testing bar yet: {untested}."
        head = f"One-sided p = {words.p_value(p)} ({what})."
        if self.value is None:
            return (head + " The multiple-testing bar could not be read from STATUS.md, so it is not counted as "
                           "clearing it.")
        return (head + f" {'Clears' if p < self.value else 'Does not clear'} the multiple-testing bar, p < "
                       f"{self.text} (0.05 / {self.variants:,} variants).")

    def finding(self, p: float | None, against: str) -> str:
        """What a chart found, in plain words, for its title."""
        if p is None:
            return "too few to test"
        if self.value is not None and p < self.value:
            return f"better than {against}, and it clears the multiple-testing bar"
        if p < 0.05:
            return f"better than {against} at p = {words.p_value(p)}, short of the multiple-testing bar"
        return f"not distinguishable from {against}"


# ---------------------------------------------------------------- one rule, or rules together

def _count(n: int, one: str) -> str:
    return words.count(n, one)


def sample_words(settled: int, pending: int, void: int) -> str:
    return (f"{_count(settled, 'settled bet')}" + (f", {pending:,} waiting for a result" if pending else "")
            + (f", {void:,} void (not graded)" if void else ""))


def summarize(bets: list[dict], bar: Bar, numbers: dict | None = None, clv_graded: bool = True) -> dict:
    """The card above the table. `numbers` are the scorer's own for one rule (its document: record, units, return per
    bet placed, mean CLV and the registered interval); without them (rules together) they are worked out from the
    bets here. The p-values are always worked out here, from the bets."""
    settled = [b for b in bets if b.get("outcome") in ("won", "lost", "push")]
    pending = sum(1 for b in bets if b.get("outcome") == "pending")
    void = sum(1 for b in bets if b.get("outcome") == "void")
    won = sum(1 for b in settled if b["outcome"] == "won")
    lost = sum(1 for b in settled if b["outcome"] == "lost")
    pushed = len(settled) - won - lost
    units = sum(b.get("units") or 0.0 for b in settled)
    roi = 100 * units / len(settled) if settled else None
    clv = clv_test(settled) if clv_graded else {"n": 0, "mean": None, "p": None, "G": 0, "why": ""}
    interval = None
    if numbers:                                            # the scorer's own numbers for this rule
        rec = numbers.get("record") if isinstance(numbers.get("record"), dict) else {}
        if all(isinstance(rec.get(k), int) for k in ("won", "lost", "pushed")):
            won, lost, pushed = rec["won"], rec["lost"], rec["pushed"]
        units = number(numbers.get("units")) if number(numbers.get("units")) is not None else units
        roi = number(numbers.get("roi_percent")) if number(numbers.get("roi_percent")) is not None else roi
        if clv_graded and number(numbers.get("mean_clv")) is not None:
            clv["mean"] = number(numbers["mean_clv"])
        interval = numbers.get("interval") if isinstance(numbers.get("interval"), dict) else None
    p_win = p_beat_break_even(settled)
    decided = won + lost
    out = {"settled": len(settled), "pending": pending, "void": void, "bets": len(bets),
           "sample": sample_words(len(settled), pending, void), "paper": PAPER,
           "record": f"{won}-{lost}-{pushed}" if settled else "",
           "record_words": f"{won:,} won, {lost:,} lost, {pushed:,} pushed" if settled else "No bet has settled yet",
           "win_rate": (f"{100 * won / decided:.1f}% of the {decided:,} that won or lost" if decided else ""),
           "units": words.signed(units) if settled else "", "units_num": units if settled else None,
           "roi": (words.signed(roi, 1) + "% per bet placed") if roi is not None and settled else "",
           "clv": "", "clv_num": clv["mean"], "clv_n": clv["n"], "interval": "",
           "bar_win": bar.sentence(p_win, "the win rate, exact, against the break-even of each price taken",
                                   "no bet has won or lost yet"),
           "p_win": p_win, "p_clv": clv["p"]}
    if not clv_graded:
        out["clv"] = "Not graded on closing-line value: this rule is graded on its results at the price taken."
        out["bar_clv"] = ""
        return out
    if clv["mean"] is not None:
        out["clv"] = (f"Closing-line value: {words.signed(clv['mean'])} points on average, over "
                      f"{_count(clv['n'], 'bet')} with a close.")
    elif settled:
        out["clv"] = "No settled bet has a closing line yet."
    if interval and isinstance(interval.get("low"), (int, float)) and isinstance(interval.get("high"), (int, float)):
        out["interval"] = (f"Registered 95% interval {words.signed(interval['low'])} to {words.signed(interval['high'])}"
                           f", over {interval.get('game_days', '?')} game days"
                           + ("; it includes zero." if interval["low"] <= 0 <= interval["high"] else
                              "; it is above zero." if interval["low"] > 0 else "; it is below zero."))
    elif numbers is not None and clv["n"]:
        out["interval"] = ("No registered interval yet: it needs at least 2 bets with a close, on at least 2 game "
                           "days.")
    elif numbers is None and clv["n"]:
        out["interval"] = "No registered interval for rules together: each rule's interval is its own."
    out["bar_clv"] = (bar.sentence(clv["p"], "mean closing-line value above zero, the larger of the plain and the "
                                             "game-day tests", clv["why"]) if clv["n"] else "")
    return out


def chart_units(bets: list[dict], bar: Bar, p_win: float | None, tz) -> dict:
    """Cumulative units by date (the Eastern date of each settled bet's kickoff), from zero."""
    settled = sorted((b for b in bets if b.get("outcome") in ("won", "lost", "push")),
                     key=lambda b: (b.get("kickoff_utc") or "", b.get("logged_utc") or ""))
    n = len(settled)
    if n < 2:
        return {"n": n, "empty": ("Fewer than 2 settled bets, so there is nothing to chart yet."
                                  if n == 0 else "Only 1 settled bet, so there is nothing to chart yet."),
                "points": [], "title": "", "caption": ""}
    points, total, by_day = [], 0.0, {}
    for b in settled:
        total += b.get("units") or 0.0
        by_day[game_day(b)] = (b.get("kickoff_utc"), total, by_day.get(game_day(b), (None, 0, 0))[2] + 1)
    first = words.parse_utc(settled[0]["kickoff_utc"])
    start = first.astimezone(words.EASTERN).replace(hour=0, minute=0, second=0) if first else None   # that morning
    points.append([words.iso_z(start) if start else settled[0]["kickoff_utc"], 0.0, "Before the first result"])
    count = 0
    for day, (kick, cum, k) in by_day.items():
        count += k
        t = words.parse_utc(kick)
        points.append([kick, round(cum, 4), f"{words.day_label(t, words.EASTERN) if t else day}: "
                                            f"{words.signed(cum)} units after {_count(count, 'bet')}"])
    lead = ("Up" if total > 0 else "Down" if total < 0 else "Even")
    title = (f"{lead} {abs(total):.2f} units after {n:,} settled bets: {bar.finding(p_win, 'break-even')}"
             if lead != "Even" else f"Even after {n:,} settled bets: {bar.finding(p_win, 'break-even')}")
    caption = f"Sample: {_count(n, 'settled bet')}. " + bar.sentence(
        p_win, "the win rate, exact, against the break-even of each price taken", "no bet has won or lost yet")
    return {"n": n, "empty": "", "points": points, "title": title, "caption": caption}


def chart_clv(bets: list[dict], bar: Bar, clv_graded: bool = True) -> dict:
    """Closing-line value per bet in kickoff order, with its running mean."""
    if not clv_graded:
        return {"n": 0, "points": [], "title": "", "caption": "",
                "empty": "Rule HT is graded on its results at the price taken, not on closing-line value."}
    xs = sorted((b for b in bets if b.get("outcome") in ("won", "lost", "push") and isinstance(b.get("clv"),
                                                                                                 (int, float))),
                key=lambda b: (b.get("kickoff_utc") or "", b.get("logged_utc") or ""))
    n = len(xs)
    if n < 2:
        return {"n": n, "points": [], "title": "", "caption": "",
                "empty": ("Fewer than 2 settled bets with a closing line, so there is nothing to chart yet." if n == 0
                          else "Only 1 settled bet with a closing line, so there is nothing to chart yet.")}
    test = clv_test(xs)
    points, run = [], 0.0
    for i, b in enumerate(xs, start=1):
        run += b["clv"]
        t = words.parse_utc(b.get("kickoff_utc"))
        points.append([b.get("kickoff_utc"), b["clv"], f"{matchup(b)}, {words.day_label(t, words.EASTERN) if t else ''}",
                       round(run / i, 4)])
    title = (f"Closing-line value averages {words.signed(test['mean'])} points over {n:,} bets: "
             f"{bar.finding(test['p'], 'zero')}")
    return {"n": n, "empty": "", "points": points, "title": title,
            "caption": f"Sample: {_count(n, 'bet')} with a close, over {_count(test['G'], 'game day')}. "
                       + bar.sentence(test["p"], "mean closing-line value above zero, the larger of the plain and the "
                                                 "game-day tests", test["why"])}


# ---------------------------------------------------------------- the rows

def matchup(b: dict) -> str:
    a, h = b.get("away_team"), b.get("home_team")
    return f"{a} at {h}" if a and h else f"Game {b.get('game_id') or '?'}"


def close_words(b: dict) -> tuple[str, str]:
    """(the close, where it came from) as the table shows them."""
    if isinstance(b.get("close_line"), (int, float)):
        src = b.get("close_source") or ""
        if src == "nflverse schedule":
            where = "Closing total, nflverse schedule"
        elif b.get("close_from") == "later quote":
            where = f"Last quote before kickoff ({words.book(src)})" if src else "Last quote before kickoff"
        elif b.get("close_from") == "captured close" or src.startswith("captured close"):
            inner = src[src.find("(") + 1:src.rfind(")")] if "(" in src else ""
            where = f"Captured close ({words.book(inner)})" if inner else "Captured close"
        else:
            where = words.book(src)
        return f"{b['close_line']:.1f}", where
    if isinstance(b.get("captured_close"), (int, float)):
        return f"{b['captured_close']:.1f}", "Captured close (secondary)"
    return "", ""


def bet_row(rule: dict, b: dict, live: dict, tz) -> dict:
    kick = words.parse_utc(b.get("kickoff_utc"))
    logged = words.parse_utc(b.get("logged_utc"))
    side = "Over" if b.get("side") == "OVER" else "Under"
    line = b.get("entry_line")
    price = "an assumed −110" if b.get("price_assumed") else words.odds(b.get("entry_price")) or "no price"
    close, close_from = close_words(b)
    outcome = b.get("outcome") if b.get("outcome") in RESULT_WORDS else "pending"
    # tinted only when this rule's own status on the game's newest row is a signal: a model lean (a watch) is never
    # tinted, and a Rule HT bet isn't tinted for a game on which only Rule B is live
    badge = live.get((rule["sport_key"], str(b.get("game_id")), rule["column"]), "")
    return {"rule": rule["id"], "rule_name": rule["name"], "rule_kind": rule["kind"], "sport": SPORT_OF[rule["project"]],
            "sport_key": rule["sport_key"], "game_id": str(b.get("game_id") or ""), "matchup": matchup(b),
            "kickoff": words.kickoff_et(kick), "kick_utc": b.get("kickoff_utc"),
            "entry": f"{side} {line:.1f} at {price}" if isinstance(line, (int, float)) else "No number logged",
            "entry_source": words.book(b.get("price_source") or "") or "Source not logged",
            "logged": f"Logged {words.when_full(logged, tz)}" if logged else "", "logged_utc": b.get("logged_utc"),
            "close": close, "close_source": close_from,
            "clv": words.signed(b.get("clv"), 1) if isinstance(b.get("clv"), (int, float)) else "",
            "clv_num": b.get("clv") if isinstance(b.get("clv"), (int, float)) else None,
            "final_total": f"{b['final_total']:g}" if isinstance(b.get("final_total"), (int, float)) else "",
            "result": outcome, "result_words": RESULT_WORDS[outcome],
            "void_reason": words.cap(b.get("void_reason") or "") if outcome == "void" else "",
            "units": words.signed(b.get("units")) if isinstance(b.get("units"), (int, float)) else "",
            "units_num": b.get("units") if isinstance(b.get("units"), (int, float)) else None,
            "live": bool(badge), "badge": badge}


def live_badges(games: list[tuple]) -> dict:
    """{(sport, game id, rule column): badge} for each game on the board whose newest row is a signal, under each rule
    that signals on that row ("signal" or "backup"): the rows of the log that are tinted. Only Rule B and Rule HT can
    signal (words.is_signal); the NFL model lean is a watch, so a lean's row is never tinted. Both of the NFL's Rule B
    rows (Pinnacle's price and the backup price) read the rule_b column: the scorer puts a game in one or the other."""
    out = {}
    for sport, L, r, _listed in games:
        for c in RULES[sport]:
            if words.is_signal(c, get(r, c)):
                out[(sport, get(r, "game_id"), c)] = words.badge(c, get(r, c))
    return out


# ---------------------------------------------------------------- when the scorer can't be read

def fallback_rows(snap, project: str, content: dict, tz) -> list[dict]:
    """From the ledger as logged: each game whose rows include a signal under a rule, on or after the rule's start,
    with its first such row. No result: only the scorer grades, and it decides which of these count."""
    sport = "nfl" if project == "nfl-weather" else "cfb"
    L = snap.ledgers.get(sport)
    if L is None or not L.readable:
        return []
    out = []
    for gid, idx in L.by_game.items():
        seen = set()
        for n in idx:
            r = L.rows[n]
            for rule in LOG_RULES:
                if rule["project"] != project or rule["id"] in seen:
                    continue
                v = get(r, rule["column"]).strip()
                if rule["id"] == "nfl_rule_b":
                    hit = v == "SIGNAL" and get(r, "line_src").strip() == "pinnacle"
                elif rule["id"] == "nfl_rule_b_backup":
                    hit = v == "SIGNAL_SECONDARY" or (v == "SIGNAL" and get(r, "line_src").strip() != "pinnacle")
                elif rule["id"] == "nfl_lean":
                    hit = v in ("UNDER lean", "OVER lean")
                else:
                    hit = v == "SIGNAL"
                start = words.parse_utc((content.get(rule["content"]) or {}).get("starts_utc", ""))
                k = L.kickoff(r)
                if not hit or (start is not None and (k is None or k < start)):
                    continue
                seen.add(rule["id"])
                side = "Over" if v == "OVER lean" else "Under"
                out.append({"rule": rule["id"], "rule_name": rule["name"], "rule_kind": rule["kind"],
                            "sport": SPORT_OF[project], "sport_key": sport, "game_id": gid,
                            "matchup": f"{get(r, 'away_team')} at {get(r, 'home_team')}",
                            "kickoff": words.kickoff_et(k), "kick_utc": words.iso_z(k),
                            "entry": (f"{side} {words.total(get(r, 'total'))} at {words.odds(get(r, 'under') if side == 'Under' else get(r, 'over'))}"
                                      if words.num(get(r, "total")) is not None else "No number logged"),
                            "entry_source": words.book(get(r, "line_src")) or "Source not logged",
                            "logged": f"First logged {words.when_full(L.logged(r), tz)}"})
    out.sort(key=lambda x: (x["kick_utc"] or "", x["game_id"]), reverse=True)
    return out


# ---------------------------------------------------------------- the empty screen

def first_day(c: dict) -> date | None:
    """The day a forward test starts, from its words in the content file ("Thu Oct 1, 2026"); else the Eastern date
    of its start time."""
    m = START_DAY.search(str(c.get("starts_text") or ""))
    if m:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1).lower()[:3]], int(m.group(2)))
        except ValueError:
            pass
    t = words.parse_utc(c.get("starts_utc", ""))
    return t.astimezone(words.EASTERN).date() if t else None


def starts_sentence(content: dict, today: date) -> str:
    """"College football's wind rule starts Thursday, October 1; the high-total rule on October 6; the NFL's wind rule
    on October 8." Worked out from the content file every time; "started" once a date has passed."""
    items = sorted((d, name) for cid, name in STARTS.items() if (d := first_day(content.get(cid) or {})) is not None)
    parts, prev = [], None
    for i, (d, name) in enumerate(items):
        verb = "started" if d < today else "starts today," if d == today else "starts"
        day = f"{d:%B} {d.day}"
        if i == 0:
            parts.append(f"{words.cap(name)} {verb} {d:%A}, {day}")
        elif verb == prev:
            parts.append(f"{name} on {day}")
        else:
            parts.append(f"{name} {verb} on {day}")
        prev = verb
    return "; ".join(parts) + "." if parts else ""


# ---------------------------------------------------------------- the screen

def build(scr, docs: dict, trouble: dict, content: dict, games: list[tuple]) -> dict:
    """The Signals screen's payload. `docs` maps each project to its scorer's document (None when it couldn't be
    read), `trouble` to what went wrong with it in plain words ("" when nothing did), `content` is forward_tests.json
    by test id, and `games` the board's games (api.on_board), for the rows to tint."""
    bar = Bar(scr.snap.status_text)
    live = live_badges(games)
    rules, bets_by_rule, rows = [], {}, []
    for rule in LOG_RULES:
        doc = docs.get(rule["project"])
        t = next((t for t in (doc or {}).get("tests", []) if t.get("id") == rule["test"]), None)
        bets = [clean(b) for b in (t or {}).get("bets", []) if isinstance(b, dict)]
        bets_by_rule[rule["id"]] = bets
        rows.extend(bet_row(rule, b, live, scr.tz) for b in bets)
        graded_on_clv = rule["id"] != "cfb_rule_ht"
        s = summarize(bets, bar, t or {}, clv_graded=graded_on_clv) if t is not None else None
        if s is not None:
            s["toward"] = rule["toward"].format(settled=f"{s['settled']:,}")
            decisions = [d for d in t.get("decisions", []) if isinstance(d, dict)]
            # the backup price decides nothing (its "toward" line says so): no line about a decision to come
            s["decision"] = "" if rule["kind"] == "backup" or t.get("decides") is False else decision_words(decisions)
        rules.append({"id": rule["id"], "name": rule["name"], "kind": rule["kind"], "sport_key": rule["sport_key"],
                      "sport": SPORT_OF[rule["project"]], "read": t is not None, "summary": s,
                      "charts": {"units": chart_units(bets, bar, s["p_win"] if s else None, scr.tz),
                                 "clv": chart_clv(bets, bar, graded_on_clv)} if s else None})
    together = {}
    for key, name in TOGETHER.items():
        ids = [r["id"] for r in LOG_RULES if r["kind"] != "watch" and (key == "all" or r["sport_key"] == key)]
        bets = [b for i in ids for b in bets_by_rule[i]]
        s = summarize(bets, bar)
        s["toward"] = "Each rule is decided on its own, by its own registered test; these totals decide nothing."
        s["rules"] = [BY_ID[i]["name"] for i in ids]
        clv_bets = [b for i in ids if i != "cfb_rule_ht" for b in bets_by_rule[i]]
        together[key] = {"name": name, "summary": s, "charts": {
            "units": chart_units(bets, bar, s["p_win"], scr.tz),
            "clv": chart_clv(clv_bets, bar)},
            "note": " ".join(s for s in (
                "The NFL model lean is a watch: its bets are listed and totalled on their own, not here."
                if key in ("all", "nfl") else "",
                "Rule HT is graded on its results, not on closing-line value, so its bets are not in the "
                "closing-line value chart." if key in ("all", "cfb") else "") if s)}
    rows.sort(key=lambda x: (x["kick_utc"] or "", x["logged_utc"] or ""), reverse=True)
    by_project = {p: fallback_rows(scr.snap, p, content, scr.tz) if docs.get(p) is None else [] for p in PROJECTS}
    fallback = [r for p in PROJECTS for r in by_project[p]]
    fallback.sort(key=lambda x: (x["kick_utc"] or "", x["game_id"]), reverse=True)
    trouble = {p: (w.replace(LISTED, NONE_LISTED) if w and not by_project[p] else w) for p, w in trouble.items()}
    today = scr.now.astimezone(words.EASTERN).date()
    empty = None
    if not rows and not fallback:
        starts = starts_sentence(content, today)
        empty = {"text": "No rule has signalled yet." + (
            f" {starts}" if starts else " When each rule starts could not be read from the forward-test "
                                        "descriptions (dashboard/content/forward_tests.json)."),
                 "next": ("When a rule signals, each bet appears here with its entry, its close and its result, newest "
                          "first, and the totals and the two charts fill in as results come in.")}
    return {"rules": rules, "together": together, "bets": rows, "fallback": fallback,
            "fallback_note": ("From the ledgers as logged: each game whose rows include a signal, with the first such "
                              "row. There are no results here; only the scorer grades, and it decides which of these "
                              "count.") if fallback else "",
            "trouble": [w for p in PROJECTS if (w := trouble.get(p))], "empty": empty, "variants": bar.variants,
            "bar": bar.text, "paper": PAPER,
            "legend_live": ("a tinted row is a bet on a game still to kick off whose newest row is a signal under that "
                            "rule"),
            "totals_note": ("The totals and charts count every settled bet of the rules shown, whatever result is "
                            "picked below."),
            "filters": {"rules": [{"id": r["id"], "name": r["name"], "sport_key": r["sport_key"]} for r in LOG_RULES]}}


def decision_words(decisions: list[dict]) -> str:
    """The rule's decision as the scorer printed it, in one plain sentence."""
    if not decisions:
        return "No decision read yet: it comes at the rule's horizon."
    d = decisions[-1]
    status = d.get("status")
    if status == "recorded":
        rec = d.get("recorded") or {}
        return f"Decision recorded: {words.strip_markdown(str(rec.get('verdict') or d.get('verdict') or ''))}."
    if status == "final":
        return f"Final at this preview's date: {d.get('verdict')}. A preview never records a decision."
    return "Interim read, which decides nothing."
