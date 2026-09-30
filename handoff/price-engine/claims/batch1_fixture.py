"""Is the proposed fix (read one call at a time) neutral on the registered fixture? Compares results.csv and the
drop counts from run.run with load_quotes at batch=50 (today) and batch=1."""
import functools
import tempfile
from pathlib import Path

from markets.research.price_engine import fixture, quotes
from markets.research.price_engine import run as pe_run

out = {}
for batch in (50, 1):
    tmp = Path(tempfile.mkdtemp())
    cfg, calls, cache, scores = fixture.build(tmp)
    real = quotes.load_quotes
    pe_run.load_quotes = functools.partial(real, batch=batch)
    res = pe_run.run(cfg, calls, cache, scores=scores)
    pe_run.load_quotes = real
    out[batch] = (res["results"].to_csv(index=False), dict(res["drops"]))
print("results.csv identical:", out[50][0] == out[1][0])
print("drops identical:", out[50][1] == out[1][1])
