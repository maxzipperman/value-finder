# sharp-markets

Paper-only research pipeline: do Kalshi game-winner markets misprice relative to sharp sportsbooks (Pinnacle, LowVig, BetOnline via The Odds API), and does Kalshi lag after sharp line moves? NBA first; sport-agnostic by config. See `CLAUDE.md` for the working rules.

## Setup
```bash
uv sync
cp .env.example .env   # add ODDS_API_KEY; the H3 dataset needs a Kaggle token (see .env.example)
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
uv run markets h3-kaggle                                       # H3: the registered test on BetMGM's NBA closing splits
uv run markets h3-kaggle --sport nfl --check-only              # H3, NFL: columns, team names, join; no result
uv run markets h3-kaggle --sport nfl                           # H3, NFL: the 6 registered variants (#75)
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
| `markets/research/` | Kaggle H3 study; H4a (Kalshi NFL totals vs wind); `price_engine/`, the F1 price-engine backtest; `props_grade/`, the grader for the registered props test on F3 (#10) |

Data lands in `data/` (gitignored); DuckDB at `data/markets.duckdb`.

## Betting splits, first test: H3 (issue #66, added September 29, 2026)

**A null.** On BetMGM's NBA closing figures from a free Kaggle file (`caseydurfee/mgm-grand-nba-betting-data`, 2021-22 to January 31, 2026, about 5,500 games a market), none of the 14 registered variants passes the bar of p < 0.000174 with the same sign in 4 of 5 seasons. The variants were: backing the side with more of the money than of the tickets (by 5, 10 or 15 points), the same idea as a regression, and fading the side with 30% of the tickets or fewer. Measured against BetMGM's own closing price with the margin removed, none came near the bar. The closest was p = 0.032, about 185 times too large.

- **Limits.** One retail book, not the market. Closing figures only, with no timestamps, so a line moving against the public can't be tested. The benchmark is BetMGM's own close, not Pinnacle's. The test could only detect effects of about 3 points of win chance or more in its biggest variants, so a small edge is not ruled out. NBA only. Games after January 31, 2026 (the Kalshi study's validation period) were left out, and no result after that date was computed. Three choices made after the file was downloaded are shown both ways in the report; none changes the finding.
- **Files.** The registration, pushed before the download: [`docs/H3_KAGGLE_PREREGISTRATION.md`](docs/H3_KAGGLE_PREREGISTRATION.md). The report, with the checks on the file and the football candidates on Kaggle: [`reports/h3_kaggle_mgm.md`](reports/h3_kaggle_mgm.md). The code: `markets/research/kaggle_h3.py`; tests: `tests/test_kaggle_h3.py` (fake token, no network).
- **The token.** `uv run markets h3-kaggle` reads the Kaggle token from `KAGGLE_API_TOKEN`, else `~/.kaggle/access_token` (refused unless only you can read it, mode 600), else `KAGGLE_USERNAME` and `KAGGLE_KEY` in `.env`. It goes with the first request only, to Kaggle's fixed API address on www.kaggle.com, and never on a redirect (Kaggle redirects downloads to a storage host); the download is cached under `data/raw/nba/kaggle_mgm/` with a `download.json` (time, size, sha256), and a rerun makes no request.
- **Football.** Kaggle has one free NFL source in the same format (`caseydurfee/mgm-grand-nfl-betting-data`, 2021–25 regular seasons, not downloaded) and none for college football. Any football test needs its own registration first.
- **The NFL test (issue #75, written September 30, 2026; not yet registered or run).** [`docs/H3_KAGGLE_NFL_PREREGISTRATION.md`](docs/H3_KAGGLE_NFL_PREREGISTRATION.md): 6 variants (families A at 10 points, B and C, on spreads and totals), results from the repo's own scores in `nfl-weather/data/processed/games.parquet`, bar p < 0.05 / 294 = 0.000170 with the same sign in 4 of 5 seasons (the running count goes from 288 to 294 when it runs). The hub registers it, then makes the one download and runs `uv run markets h3-kaggle --sport nfl --check-only` (columns, team names, the join, the format of lines, shares and prices, and the lines' sign against nflverse's closing lines; no score or won flag) followed by `--sport nfl`, which writes `reports/h3_kaggle_nfl.md`. The code: `markets/research/kaggle_h3_nfl.py`; tests: `tests/test_kaggle_h3_nfl.py` (a hand-built file, no network). The download is cached under `data/raw/nfl/kaggle_mgm/`.

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

## Props grader on F3 (issue #10, added October 1, 2026)

`uv run markets props-grade` grades the registered props test ([`nfl-weather/PREREGISTRATION_PROPS.md`](../nfl-weather/PREREGISTRATION_PROPS.md), registered September 30, 2026) on F3's cached event-odds answers. Before F3a exists it prints that there is nothing to grade yet and stops (exit 0). `--fixture` runs it end to end on a synthetic fixture (not data). It adds no variant: it implements the one already in the running count.

- **Two steps on data day.** Without `--book-recorded`, it reads F3 (sealed 2026 calls never read), prints the coverage of each primary market at F3a's close and the book the rule picks (Pinnacle only if it lists at least 80% of player-games in each primary market, else DraftKings), flags a partial F3a next to the book, lists the prop names the roster doesn't match (names and counts only), and stops before any outcome or schedule table is read. The hub adds a dated entry to the registration's section 8 ("YYYY-MM-DD: the book is DraftKings", with the two coverage figures) and commits it. Then `--book-recorded <book>` joins and prints the report: every exclusion by reason (`--list-excluded` lists them), the excess under rate at the power-method close with both standard errors and the p-value from the larger, the additive and multiplicative figures, ROI, the controls (no p-value), the readout against the same-season median, T-24h and the line move, the F3b gate on 2025, and the decision of 2.9 once 2023–25 are all in and every 2023–25 call is cached (withheld, with the counts, before that), with the count and bar read from `STATUS.md` and the registration's header at run time. It refuses the join if the book named isn't the rule's, if no dated entry in section 8 records it, or if the registration or the roster isn't committed unchanged.
- **Inputs.** Outcomes from `nfl-weather/data/processed/player_week.parquet` and kickoffs from `games.parquet` (`gameday`, `gametime`; no score column), both filtered to 2023–25 as they are read. Players are matched through `config/props/nfl_rosters_2023_2025.csv`: nflverse's weekly rosters for 2023–25 reduced to one row per player, team, season and spelling, with no outcome column; `uv run python -m markets.research.props_grade.roster` rebuilds it (GET only, GitHub; 2026 refused).
- **Output.** `reports/props_grade/report.md`, and every line with its grade or exclusion in `reports/props_grade/lines.csv` (gitignored).
- **Tests.** `tests/test_props_grade.py`, on mocked F3 answers: known-answer de-vigs, the clustered SE (not centred), the main-line tie rule and missing prices, pushes and voids, every exclusion reason, the book rule at 80%, the seal (sealed calls never read, a slipped 2026 row refused before the join, 2026 never read from the outcome tables), the stop before the book note, the empty-cache message, and a fixture season that reproduces a hand-computed excess of 0.155.
