"""Price-engine backtest on F1 (issues #8 and #53): retail prices that beat the sharp no-vig fair line.

  quotes.py    F1 rows (bulk.load_rows, sealed seasons out) -> one row per game, snapshot, book and market
  model.py     Shin de-vig and the registered totals model, imported from nfl-weather and cfb-weather
  engine.py    fair prices, flags, entries, closes, CLV, the realized result, the results table, the registered rule
  outcomes.py  final scores from the repo's processed game tables (2020-25 only), and the college alias table
  names_preflight.py  the names-only check the hub runs before any F1 price is opened (amendment 1, item 8)
  fixture.py   a synthetic F1 fixture for tests and `--fixture`
  run.py       `uv run markets price-engine`

The rules, thresholds and decision criteria: sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md.
Paper only: nothing here places, sizes or routes a bet.
"""
