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
| `markets/research/` | Kaggle H3 study |

Data lands in `data/` (gitignored); DuckDB at `data/markets.duckdb`.
