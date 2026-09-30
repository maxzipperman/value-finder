"""Resolve Odds API team names with the price engine's OWN functions (outcomes.norm, cfb_names, _school, and the
NFL alias table through load_teams + EXTRA_NFL), twice for college football:
  thursday: raw cfbfastR team files available (the live checkout's cfb-weather/data/raw/cfbfastr)
  cloud:    raw files absent (a path that does not exist), so only the prefix rule works

Input: names.csv with columns sport, name, source (feed-2026 | memory-current | memory-historical | probe).
Output: resolved.csv. No prices, no scores are printed or written (cfb_games is called only for its school list).
"""
import csv
import sys
from pathlib import Path

import pandas as pd

from markets.research.price_engine import outcomes as o
from markets.sport import load_teams

HERE = Path(__file__).resolve().parents[1]
RAW = Path("/Users/maxzipperman/code/value-finder/cfb-weather/data/raw/cfbfastr")
NONE = HERE / "no-such-dir"

g = o.cfb_games()                       # engine's own read: seasons 2020-25 only
schools = sorted(set(g.home_team) | set(g.away_team))
del g
by_len = sorted(((o.norm(s), s) for s in schools), key=lambda x: -len(x[0]))
look = {"thursday": o.cfb_names(schools, RAW), "cloud": o.cfb_names(schools, NONE)}
print("score-table schools 2020-25:", len(schools), "| raw alias keys:", len(look["thursday"]),
      "| cloud alias keys:", len(look["cloud"]))

teams = load_teams("nfl")


def how_cfb(name, lookup):
    n = o.norm(name)
    got = o._school(name, lookup, by_len)
    if n in lookup:
        how = "exact alias"
    elif got is None:
        how = "unresolved"
    elif n == o.norm(got):
        how = "exact school name"
    else:
        how = f"prefix '{o.norm(got)}'"
    others = [s for ns, s in by_len if (n == ns or n.startswith(ns + " ")) and s != got]
    return got, how, "; ".join(others)


def how_nfl(name):
    a = teams.from_name(name)
    if a:
        return a, "alias table", ""
    b = o.EXTRA_NFL.get(o.norm(name))
    if b:
        return b, "EXTRA_NFL", ""
    return None, "unresolved", ""


rows = list(csv.DictReader(open(HERE / (sys.argv[1] if len(sys.argv) > 1 else "names.csv"))))
out = []
for r in rows:
    if r["sport"] == "NFL":
        s, h, oth = how_nfl(r["name"])
        out.append({**r, "norm": o.norm(r["name"]), "thursday": s, "thursday_how": h, "cloud": s, "cloud_how": h,
                    "other_prefixes": oth})
    else:
        s1, h1, oth = how_cfb(r["name"], look["thursday"])
        s2, h2, _ = how_cfb(r["name"], look["cloud"])
        out.append({**r, "norm": o.norm(r["name"]), "thursday": s1, "thursday_how": h1, "cloud": s2, "cloud_how": h2,
                    "other_prefixes": oth})
res = pd.DataFrame(out)
if "expect" in res:
    for c in ("thursday", "cloud"):
        res[f"{c}_verdict"] = [("unresolved" if pd.isna(s) or s is None else "right" if s == e else "WRONG")
                               for s, e in zip(res[c], res.expect)]
res.to_csv(HERE / (sys.argv[2] if len(sys.argv) > 2 else "resolved.csv"), index=False)
with pd.option_context("display.width", 250, "display.max_rows", 1000, "display.max_colwidth", 60):
    cols = ["sport", "source", "name", "thursday", "thursday_how", "cloud", "cloud_how", "other_prefixes"]
    if "expect" in res:
        cols = ["sport", "source", "name", "expect", "thursday", "thursday_how", "thursday_verdict", "cloud",
                "cloud_how", "cloud_verdict"]
    print(res[cols].to_string(index=False))
