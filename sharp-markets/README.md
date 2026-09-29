# sharp-markets

Paper-only research pipeline: do Kalshi game-winner markets misprice relative to sharp sportsbooks (Pinnacle, LowVig, BetOnline via The Odds API), and does Kalshi lag after sharp line moves? NBA first; sport-agnostic by config. See `CLAUDE.md` for the working rules.

## Setup
```bash
uv sync
cp .env.example .env   # add ODDS_API_KEY (and KAGGLE_* for the H3 dataset)
uv run pytest
```

## Pipeline (sample week)
```bash
uv run markets discover                                        # Kalshi events/markets, cutoff, fees
uv run markets cup-calendar --season 2025-26                   # one-time ESPN NBA Cup pull -> CSV for review
uv run markets kalshi --start 2026-01-05 --end 2026-01-11      # candles + trades + event fee overrides
uv run markets odds-plan --start 2026-01-05 --end 2026-01-11   # snapshot schedule + credit estimate (free)
uv run markets odds-pull --start 2026-01-05 --end 2026-01-11 --confirm --max-credits 8000
uv run markets build                                           # raw -> DuckDB tables, matching, analysis grid
uv run markets backtest --start 2026-01-05 --end 2026-01-11    # H1, H2, lead-lag -> reports/
uv run markets h3-kaggle                                       # early H3 test on MGM splits
uv run markets odds5m plan                                     # 5M month: bulk multi-sport pulls (docs/ODDS5M_DAY_ONE.md)
uv run markets odds5m full --pull F1 --confirm --max-credits 170000        # one pull at a time, as docs/ODDS5M_DAY_ONE.md lists them
                                                               # (`--pull day_one` is refused: F3, in it, needs --seasons)
uv run markets weather qualifying                              # heat triggers -> data/weather/heat_qualifying.csv (docs/HEAT_HYPOTHESES.md)
```

## Module map
| Module | Role |
|---|---|
| `markets/cache.py` | cache-first raw store, `data/raw/{sport}/{source}/{date}/*.parquet` |
| `markets/http.py` | GET-only HTTP, rate limit, backoff |
| `markets/sport.py` | sport config + team alias resolution |
| `markets/games.py` | Kalshi events -> games, exclusions, anomalies |
| `markets/kalshi/` | GET-only client, discovery, candles (chunked), trades |
| `markets/oddsapi/` | historical/live odds client with credit budget, snapshot scheduler; `bulk.py` is the 5M-month puller (config `config/odds5m.yaml`: /events schedules, featured and event-odds pulls, manifest, circuit breaker, sealed holdout) |
| `markets/fees.py`, `markets/devig.py` | Kalshi fee model, de-vig + multi-book blend |
| `markets/build/` | DuckDB loaders, matching, SQL views |
| `markets/analysis/` | fills, CLV, H1, H2, lead-lag, reports |
| `markets/research/` | Kaggle H3 study; H4a (Kalshi NFL totals vs wind); `price_engine/`, the F1 price-engine backtest |

Data lands in `data/` (gitignored); DuckDB at `data/markets.duckdb`.

## Price-engine backtest on F1 (issues #8 and #53, added September 29, 2026)

`uv run markets price-engine` runs the whole backtest in one line once F1 is cached. Before F1 exists it prints that there is nothing to backtest and stops. `--fixture` runs it end to end on a synthetic fixture (not data).

| Module (`markets/research/price_engine/`) | Role |
|---|---|
| `quotes.py` | F1 rows from `bulk.load_rows` (sealed seasons out) → one row per game, snapshot, book and market with both sides' prices, and both the kickoff listed at that snapshot and the latest-listed one. It drops, and counts, anything at or after kickoff or more than 7 days out. |
| `model.py` | Shin de-vig and the registered totals model (`p_under_at` plus the frozen cohorts), **imported** from `nfl-weather` and `cfb-weather`, with the cohort hashes checked. Also the spread margin table (`spread_cohort.json`, games before 2020, hashed) that converts a spread close at another number for grading. |
| `engine.py` | Pinnacle and blend fair prices (blend weights fixed in code), the flags (H1: EV ≥ 1/2/3%; H2: a retail total ≥ 1 point off Pinnacle's at −115 or better), one entry per game-side, closes, CLV in cents and points, the result, and the draft decision rule. |
| `outcomes.py` | Final scores from `nfl-weather` and `cfb-weather` processed tables, 2020–25 only. |
| `run.py` | Writes `reports/price_engine/{report.md, results.csv, dropped.csv, bets.parquet}`. The printed variant count is the number of rows in `results.csv` (38). |

- **Rules and thresholds.** These are in [`docs/PRICE_ENGINE_PREREGISTRATION.md`](docs/PRICE_ENGINE_PREREGISTRATION.md), registered September 29, 2026, before the first run on F1 (it began as a draft in `strategy-research/`).
- **Tests.** `tests/test_price_engine.py`, all on synthetic rows. It checks:
  - no entry at or after kickoff or inside its last hour, including a kickoff that moved earlier or later;
  - sealed rows and 2026 scores never load;
  - the de-vig sums to 1;
  - the EV arithmetic of a flag, and the registered conversion for totals;
  - spread closes at another number are converted, not dropped, and the margin table is frozen and rebuildable;
  - the sign conventions for CLV;
  - that the variant count equals the rows in the results table, and the draft states the same count and bar as the code.
- **New dependencies.** The package imports the weather projects' pricing module, so `sharp-markets` now depends on pandas, scipy and statsmodels. The first `uv run` after pulling installs them.
- **F1's resolution.** F1 sees each game at 16:00 UTC daily and, on busy days, at other games' closes. Gaps that last minutes are mostly missed, and every run says so.
