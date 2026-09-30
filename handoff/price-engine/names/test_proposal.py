"""Simulate the alias proposal IN MEMORY ONLY (the repo is not edited): merge alias_proposal.csv into the lookup
the engine builds, re-resolve every name tested (feed, memory, probes, State->St), both with and without raw
files, and report what changes. Every proposal school must be a score-table school."""
from pathlib import Path

import pandas as pd

from markets.research.price_engine import outcomes as o

HERE = Path(__file__).resolve().parents[1]
RAW = Path("/Users/maxzipperman/code/value-finder/cfb-weather/data/raw/cfbfastr")
prop = pd.read_csv(HERE / "alias_proposal.csv")
g = o.cfb_games()
schools = sorted(set(g.home_team) | set(g.away_team))
del g
bad = sorted(set(prop.school) - set(schools))
print("proposal schools not spelled as in the score table:", bad)
keys_ok = all(k == o.norm(k) for k in prop.normalized_feed_name)
print("every proposal key is already normalized:", keys_ok)
extra = dict(zip(prop.normalized_feed_name, prop.school))
by_len = sorted(((o.norm(s), s) for s in schools), key=lambda x: -len(x[0]))
base = {"thursday": o.cfb_names(schools, RAW), "cloud": o.cfb_names(schools, HERE / "no-such-dir")}
# a proposal key must not change a name the lookup already resolves by alias
clash = {k: (base["thursday"][k], v) for k, v in extra.items() if k in base["thursday"] and base["thursday"][k] != v}
print("proposal keys that would override an existing raw alias with a different school:", clash)
frames = []
for f in ("resolved_feed.csv", "resolved_memory.csv", "resolved_st.csv"):
    d = pd.read_csv(HERE / f)
    frames.append(d[d.sport == "CFB"].assign(file=f))
d = pd.concat(frames, ignore_index=True)
d["expect"] = d.expect.fillna(d.thursday)      # feed names: judged right by eye, so expect = Thursday result
for mode in ("thursday", "cloud"):
    look = {**base[mode], **extra}             # the proposal would sit on top of the engine's lookup
    d[f"{mode}_new"] = [o._school(n, look, by_len) for n in d.name]
    before = (d[mode] == d.expect).sum()
    after = (d[f"{mode}_new"] == d.expect).sum()
    worse = d[(d[mode] == d.expect) & (d[f"{mode}_new"] != d.expect)]
    still = d[d[f"{mode}_new"] != d.expect]
    print(f"[{mode}] names right before {before} / after {after} of {len(d)}; made worse: {len(worse)}")
    print(f"   still not right after the proposal ({len(still)}):", still[["name", "expect", f"{mode}_new"]].values.tolist())
