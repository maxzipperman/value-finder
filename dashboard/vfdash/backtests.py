"""The Backtests screen: the research the project has done, as charts drawn from tables already committed in the repo.

The charts are prepared by dashboard/tools/build_charts.py (run by hand with a weather project's Python, since the
server uses the standard library and can't read parquet) as small JSON files in dashboard/content/charts/. The server
only reads them. As the page loads it adds whether each result clears the project's multiple-testing bar (read from
STATUS.md's "Variants" bullet, as the other screens do), and it draws one chart itself: every result in the evidence
list that has a p-value, against the bar, since both of those change whenever research merges.

A chart file that is missing, empty, cut off or not in the form the tool writes is shown as one plain sentence in its
place; the rest of the screen is drawn."""
from __future__ import annotations

import os
import re
from datetime import date

from . import words
from .data import scrub_all
from .readers import Refused, read_json, refuse
from .signals import Bar

# The screen's order: (group heading, [chart ids]); dashboard/tools/build_charts.py holds the same list (a test
# checks). "evidence-vs-bar" is drawn here, from the evidence list and STATUS.md, as the page loads.
GROUPS = [
    ("Why wind, and the wind rule replayed on forecasts",
     ["wind-and-scoring", "wind-rule-cfb-seasons", "wind-rule-nfl-seasons", "wind-rule-units",
      "wind-rule-opener-vs-close"]),
    ("How good are the forecasts", ["forecast-error-cfb", "forecast-error-nfl"]),
    ("How hard it is to prove anything", ["evidence-vs-bar", "money-gate", "keep-test"]),
    ("Other ideas tested", ["key-numbers", "line-moves", "high-total-seasons"]),
]
LIVE = {"evidence-vs-bar"}
# Asked for, and not charted: no committed table holds it. Said on the screen, in its place.
NOT_CHARTED = {
    "high-total-seasons": ("College football's high-total rule (Rule HT), season by season, is not charted: "
                           "strategy-research/README.md gives its win rate by season without counts, from a superseded "
                           "record of the rule (373–273, before #48 rebuilt the college football games table on the "
                           "#36 spread fix), and no committed table holds its record by season. Its pooled records are "
                           "on the Research screen."),
}
# What each chart is, for the sentence shown when its file can't be read.
NAMES = {
    "wind-and-scoring": "Scoring and the closing total against wind, NFL",
    "wind-rule-cfb-seasons": "College football's wind rule on forecasts as issued, season by season",
    "wind-rule-nfl-seasons": "The NFL wind rule on forecasts as issued, season by season",
    "wind-rule-units": "Units won in each sport's forecast replay",
    "wind-rule-opener-vs-close": "The forecast replays at the opener and at the close",
    "forecast-error-cfb": "College football forecasts against the observed wind",
    "forecast-error-nfl": "NFL forecasts against the observed wind",
    "money-gate": "The paper-to-money gate",
    "keep-test": "The keep test",
    "key-numbers": "Key numbers",
    "line-moves": "How totals move from the opener to the close",
}
FORMAT = 1
MAX_BYTES = 5_000_000                   # the largest chart is about 200 KB
REPO_URL = "https://github.com/maxzipperman/value-finder/blob/"
SAFE_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,200}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SAFE_ANCHOR = re.compile(r"^[a-z0-9-]{0,120}$")
P_NUMBER = re.compile(r"(?<![\d.])(\d*\.?\d+(?:[eE]-?\d+)?)")
# The evidence list's Rule HT entry is the screen's first row, 373–273 on 646 games (p = 0.0035). The screen rerun on
# the corrected spread data (#36) restates it; while the list still holds the older row, chart 6 says so. The figures
# are the committed log's (strategy-research/output/screen.log, the "PRIOR-season mean + 10" row), checked by a test.
HT_ENTRY = ("cfb-rule-ht-2016-25", 646)
HT_RESTATED = ("The evidence list's Rule HT entry (373–273, p = 0.0035) predates the restatement on the corrected "
               "spread data (#36): the screen's log, strategy-research/output/screen.log, gives the rule 502–393 "
               "(56.1% of 895 bets), p = 0.0142 against break-even, which does not clear the bar either.")


# ---------------------------------------------------------------- reading a chart file

def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def _points_ok(points, width: int) -> bool:
    if not isinstance(points, list):
        return False
    for p in points:
        if not (isinstance(p, list) and len(p) >= width and isinstance(p[0], (str, int, float))
                and not isinstance(p[0], bool)):
            return False
        if not all(v is None or _is_num(v) for v in p[1:width]):
            return False
    return True


def shape_problem(doc, cid: str) -> str | None:
    """Why a chart file is not in the form build_charts.py writes, or None when it is."""
    if not isinstance(doc, dict):
        return "it is not a chart"
    if doc.get("format") != FORMAT:
        return "it was written in a form this dashboard doesn't know"
    if doc.get("id") != cid:
        return "it names a different chart"
    for k in ("title", "name", "shows", "not_shows", "sample", "date"):
        if not isinstance(doc.get(k), str) or not doc[k].strip():
            return f"it has no {k.replace('_', ' ')}"
    bar = doc.get("bar")
    if not isinstance(bar, dict) or not isinstance(bar.get("tests"), list):
        return "it doesn't say how its result stands against the bar"
    for t in bar["tests"]:
        if not (isinstance(t, dict) and isinstance(t.get("label"), str) and _is_num(t.get("p")) and 0 < t["p"] <= 1
                and isinstance(t.get("p_words"), str)):
            return "one of its p-values can't be read"
    if not bar["tests"] and not isinstance(bar.get("none"), str):
        return "it doesn't say how its result stands against the bar"
    src = doc.get("sources")
    if not (isinstance(src, list) and src and all(isinstance(s, dict) and isinstance(s.get("path"), str)
                                                    and isinstance(s.get("blob"), str) for s in src)):
        return "it doesn't name its sources"
    plot = doc.get("plot")
    if not isinstance(plot, dict) or plot.get("layout") not in ("columns", "rows"):
        return "its chart can't be read"
    panels = plot.get("panels")
    if not (isinstance(panels, list) and 1 <= len(panels) <= 6):
        return "its chart can't be read"
    for pn in panels:
        if not isinstance(pn, dict) or not isinstance(pn.get("series"), list) or not pn["series"]:
            return "its chart can't be read"
        axis = pn.get("x") if plot["layout"] == "rows" else pn.get("y")
        if not isinstance(axis, dict):
            return "its chart can't be read"
        if plot["layout"] == "rows" and not (isinstance(pn.get("rows"), list)
                                             and all(isinstance(r, str) for r in pn["rows"])):
            return "its chart can't be read"
        for s in pn["series"]:
            if not (isinstance(s, dict) and isinstance(s.get("name"), str) and s.get("mark") in ("dot", "line", "bar")
                    and _points_ok(s.get("points"), 2)):
                return "its chart can't be read"
        for r in pn.get("refs") or []:
            if not (isinstance(r, dict) and _is_num(r.get("value")) and isinstance(r.get("label"), str)):
                return "its chart can't be read"
    tab = doc.get("table")
    if not (isinstance(tab, dict) and isinstance(tab.get("columns"), list) and isinstance(tab.get("rows"), list)
            and all(isinstance(r, list) for r in tab["rows"])):
        return "its table can't be read"
    return None


def read_chart(folder, cid: str) -> tuple[dict | None, str]:
    """(the chart, "") or (None, a plain sentence saying why it can't be shown)."""
    name = NAMES.get(cid, cid)
    rel = f"dashboard/content/charts/{cid}.json"
    path = folder / f"{cid}.json"
    label = f"the chart file ({rel})"
    try:
        size = os.stat(refuse(path)).st_size
    except FileNotFoundError:
        return None, (f"The chart “{name}” is not shown: its file ({rel}) is missing. The hub makes it with "
                      "dashboard/tools/build_charts.py.")
    except (OSError, Refused):
        return None, f"The chart “{name}” is not shown: its file ({rel}) could not be opened."
    if size > MAX_BYTES:
        return None, f"The chart “{name}” is not shown: its file ({rel}) is far larger than a chart, so it is not read."
    try:
        r = read_json(path, label)
    except RecursionError:
        return None, f"The chart “{name}” is not shown: its file ({rel}) is nested too deeply to be a chart."
    if r.data is None:
        why = r.note.replace(label, "its file").rstrip(".") if r.note else "its file could not be read"
        return None, f"The chart “{name}” is not shown: {why} ({rel})."
    try:
        problem = shape_problem(r.data, cid)
    except (RecursionError, TypeError, ValueError):
        problem = "its chart can't be read"
    if problem:
        return None, f"The chart “{name}” is not shown: {problem} ({rel})."
    return scrub_all(r.data), ""


# ---------------------------------------------------------------- words

def link(path: str, anchor: str = "", at: str = "main") -> str:
    """The file's page on GitHub as it is at `at`: a source at the commit the chart was built from (the file as the
    chart read it), a write-up on main. The repo is private: it opens for the owner, signed in, in his browser, when
    he clicks it; the page never fetches it."""
    if not isinstance(path, str) or not SAFE_PATH.match(path) or ".." in path:
        return ""
    if at != "main" and not (isinstance(at, str) and COMMIT.match(at)):
        return ""
    return (REPO_URL + at + "/" + path
            + (f"#{anchor}" if isinstance(anchor, str) and anchor and SAFE_ANCHOR.match(anchor) else ""))


def day_words(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso or "")
    return f"{d:%a} {d:%b} {d.day}, {d.year}"


def bar_lines(bar: Bar, spec: dict) -> tuple[list[str], bool | None]:
    """Whether each result clears the bar in force now, in plain sentences, and whether any does (None: no test)."""
    tests = spec.get("tests") or []
    if not tests:
        return [str(spec.get("none") or "")], None
    lines, clears = [], False
    for t in tests:
        head = f"{t['label']}: {t['p_words']}."
        if bar.value is None:
            lines.append(head + " The multiple-testing bar could not be read from STATUS.md, so it is not counted as "
                                "clearing it.")
            continue
        ok = t["p"] < bar.value
        clears = clears or ok
        lines.append(head + f" {'Clears' if ok else 'Does not clear'} the multiple-testing bar, p < {bar.text} "
                            f"(0.05 / {bar.variants:,} variants).")
    if spec.get("note"):
        lines.append(str(spec["note"]))
    return lines, clears


def chart_payload(doc: dict, group: str, bar: Bar) -> dict:
    lines, clears = bar_lines(bar, doc["bar"])
    return {"id": doc["id"], "group": group, "title": doc["title"], "name": doc["name"], "shows": doc["shows"],
            "not_shows": doc["not_shows"], "sample": doc["sample"], "n": doc.get("n"), "bar_lines": lines,
            "clears": clears, "date": day_words(doc["date"]),
            "sources": [{"path": s["path"], "url": link(s["path"], at=s.get("commit")), "blob": s["blob"][:10],
                         "changed": day_words(s.get("changed", ""))} for s in doc["sources"]],
            "writeups": [{"path": w.get("path", ""), "section": w.get("section", ""),
                          "url": link(w.get("path", ""), w.get("anchor", ""))}
                         for w in doc.get("writeups") or [] if isinstance(w, dict)],
            "plot": doc["plot"], "table": doc["table"], "missing": ""}


# ---------------------------------------------------------------- the one chart drawn live: every result against the bar

def p_of(v) -> float | None:
    """The p-value an evidence entry writes, as a number: the first number in it ("0.028 (one-sided; ...)" is 0.028,
    "≈ 0.007" is 0.007). None when there is none, or it isn't between 0 and 1."""
    if isinstance(v, bool):
        return None
    if _is_num(v):
        p = float(v)
    elif isinstance(v, str):
        m = P_NUMBER.search(v)
        p = float(m.group(1)) if m else None
    else:
        p = None
    return p if p is not None and 0 < p <= 1 else None


def evidence_chart(entries: list, bar: Bar, readable: bool) -> dict:
    marks, without = [], []
    for e in entries:
        if not isinstance(e, dict) or not e.get("title"):
            continue
        p = p_of(e.get("p_value"))
        if p is None:
            without.append(str(e["title"]))
            continue
        n = e.get("n")
        n_words = f"n = {n:,}" if isinstance(n, int) and not isinstance(n, bool) else str(n or "n not given")
        marks.append({"title": str(e["title"]), "sport": str(e.get("sport") or ""), "p": p,
                      "written": str(e["p_value"]), "n": n_words, "source": str(e.get("source") or "")})
    total = sum(1 for e in entries if isinstance(e, dict))
    if bar.value is not None:
        clear = [m for m in marks if m["p"] < bar.value]
        closest = min((m["p"] for m in marks), default=None)
        if not marks:
            title = "No result in the evidence list has a p-value to place against the bar"
        elif not clear:
            title = (f"None of the {len(marks)} results with a p-value clears the project's bar of p < {bar.text}; "
                     f"the closest is p = {words.p_value(closest)}")
        else:
            verb = "clears" if len(clear) == 1 else "clear"
            title = f"{len(clear)} of the {len(marks)} results with a p-value {verb} the project's bar of p < {bar.text}"
        lines = [(f"{'None' if not clear else len(clear)} of {'them' if marks else 'the results'} "
                  f"{'clears' if not clear or len(clear) == 1 else 'clear'} the multiple-testing bar in force now, "
                  f"p < {bar.text} (0.05 / {bar.variants:,} variants).")]
    else:
        clear = []
        title = (f"The {len(marks)} results with a p-value, against the ordinary 0.05: the project's bar could not "
                 "be read from STATUS.md")
        lines = ["The multiple-testing bar could not be read from STATUS.md's “Variants” bullet, so no result is "
                 "counted as clearing it."]
    if any(isinstance(e, dict) and (e.get("id"), e.get("n")) == HT_ENTRY and p_of(e.get("p_value")) is not None
           for e in entries):
        lines.append(HT_RESTATED)
    rows = [m["title"] for m in marks]
    refs = [{"value": 0.05, "label": "0.05, the ordinary standard", "role": "line"}]
    if bar.value is not None:
        refs.append({"value": bar.value, "label": f"The project's bar, p < {bar.text}", "role": "bar"})
    tab_rows = [[m["title"], m["sport"], m["n"], m["written"], words.p_value(m["p"]),
                 ("Yes" if m["p"] < bar.value else "No") if bar.value is not None else "Not known"] for m in marks]
    return {
        "id": "evidence-vs-bar", "title": title,
        "name": "Every result in the evidence list that has a p-value, against the project's bar",
        "shows": ("Each dot is one result from the evidence list, placed at its p-value on a scale where each step "
                  "to the right is ten times smaller; a result must reach past the bar's line to clear it."),
        "not_shows": ((f"The {len(without)} result{'s' if len(without) != 1 else ''} in the evidence list with no "
                       f"written p-value {'are' if len(without) != 1 else 'is'} not on it: " + "; ".join(without) + ". "
                       if without else "") + "A result past the line would still need its forward test."),
        "sample": (f"{len(marks)} results with a p-value, of {total} in the evidence list" if readable else
                   "The evidence list could not be read"),
        "n": len(marks), "bar_lines": lines, "clears": bool(clear) if bar.value is not None else None,
        "date": "Read as the page loads",
        # read from this Mac as the page loads, at no recorded version: named, not linked
        "sources": [{"path": "dashboard/content/evidence.json", "url": "", "blob": "",
                     "changed": "read from this Mac as the page loads"},
                    {"path": "STATUS.md", "url": "", "blob": "",
                     "changed": "its “Variants” bullet, read from this Mac as the page loads"}],
        "writeups": [], "missing": "",
        "plot": {"layout": "rows", "panels": [{
            "name": "", "rows": rows,
            "x": {"kind": "p", "label": "p-value (to the right is stronger)", "log": True, "reverse": True},
            "series": [{"id": "p", "name": "p-value", "mark": "dot", "color": "c1",
                        "points": [[m["title"], m["p"]] for m in marks]}],
            "refs": refs, "notes": {m["title"]: m["n"] for m in marks}}]},
        "table": {"columns": ["Result", "Sport", "Sample", "p-value as written", "Placed at",
                              "Clears the bar in force now"],
                  "num": [False, False, False, False, True, False], "rows": tab_rows,
                  "note": "Each result's own entry, with the bar in force when it was measured, is on the Research "
                          "screen."},
    }


# ---------------------------------------------------------------- the screen

def intro(entries: list | None, bar: Bar) -> list[str]:
    first = ("These charts show the research behind the forward tests, drawn from tables committed in the repo: why "
             "the wind rule exists and how it did on forecasts as they were issued, how good those forecasts are, how "
             "hard it is to prove an edge, and other ideas tested.")
    second = ("Every chart is a backtest or a simulation on past data, not a forward result: the forward tests' own "
              "bets are on the Signals screen.")
    if entries is None:
        return [first, second, "The evidence list could not be read, so this screen can't say which results have "
                               "cleared the project's multiple-testing bar."]
    listed = [e for e in entries if isinstance(e, dict) and e.get("title")]
    # judged as the chart of every result against the bar judges it: each written p-value against today's bar
    if bar.value is None:
        return [first, second, "The multiple-testing bar could not be read from STATUS.md, so no result in the "
                               "evidence list is counted as clearing it."]
    cleared = [str(e["title"]) for e in listed if (p := p_of(e.get("p_value"))) is not None and p < bar.value]
    where = f" (p < {bar.text}, 0.05 / {bar.variants:,} variants)"
    if not cleared:
        third = (f"None of the {len(listed)} results in the evidence list clears the project's multiple-testing "
                 f"bar{where}.")
    else:
        which = "only this one clears" if len(cleared) == 1 else "only these clear"
        third = (f"Of the {len(listed)} results in the evidence list, {which} the project's multiple-testing "
                 f"bar{where}: " + "; ".join(cleared) + ".")
    return [first, second, third]


def build(scr) -> dict:
    """The Backtests screen's payload (api.backtests)."""
    store = scr.store
    folder = store.cfg.content / "charts"
    bar = Bar(scr.snap.status_text)
    raw = scr.snap.evidence.data
    if isinstance(raw, dict):
        raw = raw.get("entries")
    entries = raw if isinstance(raw, list) else None
    read = store.derived("backtest-charts", lambda: {cid: read_chart(folder, cid) for _, ids in GROUPS for cid in ids
                                                     if cid not in LIVE and cid not in NOT_CHARTED})
    groups, dates = [], []
    for heading, ids in GROUPS:
        items = []
        for cid in ids:
            if cid in NOT_CHARTED:
                items.append({"id": cid, "group": heading, "not_charted": NOT_CHARTED[cid]})
            elif cid in LIVE:
                items.append(dict(evidence_chart(entries or [], bar, entries is not None), group=heading))
            else:
                doc, why = read[cid]
                if doc is None:
                    items.append({"id": cid, "group": heading, "name": NAMES.get(cid, cid), "missing": why})
                else:
                    items.append(chart_payload(doc, heading, bar))
                    dates.append(doc["date"])
        groups.append({"heading": heading, "charts": items})
    if entries is None:
        scr.notes.append(words.cap(scr.snap.evidence.note or "The evidence list could not be read."))
    if bar.value is None:
        scr.notes.append("The running count of variants could not be read from STATUS.md's “Variants” bullet.")
    newest = max(dates) if dates else None
    return {"intro": intro(entries, bar), "groups": groups, "variants": bar.variants, "bar": bar.text,
            "newest": day_words(newest) if newest else None}
