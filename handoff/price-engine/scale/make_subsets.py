"""Partial copies of the made-up full cache (hard links, no extra disk): every k-th F1 call in plan order.
The saved schedules are copied whole, so `markets price-engine` plans all of F1 and finds only the subset
cached ("a partial pull"), exactly as it would on a partly pulled F1."""
import os
import shutil
import sys
from pathlib import Path

from markets.cache import RawCache
from markets.oddsapi import bulk

SCR = Path(__file__).parent
full = SCR / "data_full" / "raw"
cfg = bulk.load_config()
calls = bulk.plan_calls(cfg, "F1", bulk.load_schedules(cfg, full))
cache = RawCache(full)
for name, k in [(a.split(":")[0], int(a.split(":")[1])) for a in sys.argv[1:]]:     # e.g. p10:10 p25:4 p50:2
    dst = SCR / f"data_{name}" / "raw"
    if dst.exists():
        shutil.rmtree(dst.parent)
    shutil.copytree(full / "_schedules", dst / "_schedules")
    n = 0
    for i, c in enumerate(calls):
        if i % k:
            continue
        p = cache.lookup(c.cache_sport, c.source, c.key)
        q = dst / p.relative_to(full)
        q.parent.mkdir(parents=True, exist_ok=True)
        os.link(p, q)
        n += 1
    print(name, f"every {k}th call:", n, "of", len(calls))
