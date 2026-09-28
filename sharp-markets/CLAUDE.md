# sharp-markets — working rules

Research pipeline comparing Kalshi game-winner markets to sharp sportsbook lines (Pinnacle, LowVig, BetOnline via The Odds API).

## Non-negotiables
- **Paper-only.** Never write, import, or call order-placement code: no Kalshi `POST/PUT/DELETE`, no `/portfolio/*`, no pmxt/agenttrader trading clients. `markets.kalshi.client` is GET-only and `tests/test_no_order_code.py` enforces it.
- **No lookahead, ever.** Any signal at time `t` may only use data with timestamp ≤ `t`. Sharp lines are known at the Odds API `snapshot_ts` (never `last_update` for decisions). Candles are known at their `end_ts`. Fills happen after the signal minute. Lead-lag *measurement* may look forward because it is descriptive, not a trade rule.
- **Cache first.** Every HTTP response is written to `data/raw/{sport}/{source}/{date}/*.parquet` before use. Reruns read the cache and never re-fetch. Odds API calls require `--confirm` and a `--max-credits` budget.
- **UTC everywhere.** Store and compute in UTC (`TIMESTAMPTZ`). ET appears only as the derived `game_date_et`.
- **Log, don't drop.** Excluded markets go to `excluded_markets` with a reason, and oddities go to `anomalies`. Never silently filter. Never guess team names; unknown names are anomalies.
- **Sport-agnostic.** Sport specifics live in `config/sports/{sport}.yaml` and `config/teams/{sport}.csv`. Code takes a `sport` argument; every table has a `sport` column.
- **Money as DECIMAL.** Prices, counts and fees are DECIMAL in DuckDB. Floats are fine only for statistics.
- **Overfitting guard.** Tune thresholds on the train split only. Every result table reports `n_variants_tested`.

## Layout
- `src/markets/` — package (see README for the module map)
- `config/` — sport configs, team alias tables, backtest params
- `data/` — raw cache + `markets.duckdb` (gitignored)
- `reference/` — read-only clone of mmoore07129/mlb-kalshi-bot (gitignored; patterns only, no order code)

## Commands
- `uv run pytest`
- `uv run markets --help`
