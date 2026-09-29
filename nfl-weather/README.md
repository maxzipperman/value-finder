# nfl-weather

A follow-up to *Quantifying the Impact of Temperature and Wind on NFL Passing
and Rushing Performance* (Zipperman, CMC Senior Thesis, 2014): rebuild the data
with a reusable pipeline, replicate the thesis, test it on the 12 seasons since,
extend it, and ask whether the betting market prices the weather.

The write-up is `report/nfl_weather_report.html`, published at https://claude.ai/artifact/D3DBN6pehV5aaC2RkDZcbP (private; republish with that URL to keep the link). The betting rules are in `STRATEGY.md`.

## Setup

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

## Run it

```bash
.venv/bin/python scripts/fetch_data.py      # pull or refresh every raw input (cached, resumable)
.venv/bin/python scripts/build_data.py      # raw -> data/processed/*.parquet
.venv/bin/python scripts/replicate.py       # thesis specs: 2002-13 replication + 2014-25 holdout
.venv/bin/python scripts/extend.py          # extended models, acclimation, field goals
.venv/bin/python scripts/audit_thesis.py    # the 2014 model, one fix at a time; how much weather explains
.venv/bin/python scripts/betting.py         # market tests, open vs close, walk-forward, CLV, de-vig
.venv/bin/python scripts/model_compare.py   # simple vs interaction vs gradient-boosted P(under) models
.venv/bin/python scripts/strategies.py      # every playbook rule scored the same way (STRATEGY.md)
.venv/bin/python scripts/this_week.py       # weather board for upcoming games + forward ledger
.venv/bin/python scripts/report_data.py     # rebuild the HTML report from output/tables
.venv/bin/python scripts/score_forward.py   # score the pre-registered 2026 test
.venv/bin/python -m pytest -q tests         # pins the box-score, wind-chill, de-vig and GET-only facts
scripts/run_all.sh                          # everything above, in order
```

## Pinnacle lines and alerts

```bash
# .env already has a random NTFY_TOPIC; add ODDS_API_KEY
.venv/bin/python scripts/odds_api.py plan   # free: 2024-25 backfill schedule + credit estimate (~8,300)
.venv/bin/python scripts/odds_api.py backfill --confirm --max-credits 9000
.venv/bin/python scripts/odds_api.py build  # cached snapshots -> data/processed/pinnacle_lines.parquet
.venv/bin/python scripts/pinnacle_check.py  # no-hindsight 2024-25 replay: forecasts vs Pinnacle, scored on CLV
.venv/bin/python scripts/alerts.py --test   # one Mac notification (+ iPhone push if NTFY_TOPIC is set)
scripts/install_alerts.sh                   # launchd job: alerts at 7:30, 11:30, 15:30, 19:30
scripts/install_alerts.sh --remove
```

Alerts follow `STRATEGY.md` (v2). Only a full Rule B signal is actionable: forecast
wind 15+ mph 1–3 days out, a posted total, an under price of −115 or better, and
positive expected value at that line and price. Wind triggers without a usable price,
model leans, big model-vs-market gaps and cold-visitor spots arrive as WATCH items.
With a key in `.env`, the board and alerts use live Pinnacle totals (1 credit per run);
without one, or when the API fails or the month's credits run out, they fall back to
nflverse lines. The same call logs nine more books at no extra cost (up to 10 books bill
as one region), so each signal also shows the best under price at Pinnacle's number;
Rule B still prices at Pinnacle. `alerts.py --dry-run` makes no Odds API call, and
hand-run commands stop when fewer than 60 credits are left this month
(the shared `~/.cache/value-finder/odds_quota.json`, see `nflweather/quota.py`).

Every bet alert ends with timing advice (issue #5): unders and favorites now, overs and
underdogs later. After you bet, log what you actually got, e.g.
`scripts/log_fill.py 2026_06_BUF_NYJ --rule rule_b --line 41.5 --price -108 --book fanduel`;
`score_forward.py` then reports the cost of waiting against the alert-time quote.

For iPhone pushes: install the free ntfy app, subscribe to the topic in
`NTFY_TOPIC` (pick something long and random; anyone who knows it can read it),
and allow notifications. macOS may ask once to allow notifications from Script Editor.

During the season, a weekly refresh is just `fetch_data.py`, `build_data.py`
and `this_week.py`. Everything is cached under `data/raw`, so only new games,
new weather and new lines are downloaded.

## Where the data comes from

| Source | What | Notes |
|---|---|---|
| nflverse `games.csv` | every game since 1999; game-book kickoff temp and wind; roof; closing spread, total, moneyline, O/U prices | The same game-book weather Pro-Football-Reference shows, which is what the thesis scraped. PFR now returns 403 to scripts. |
| nflverse play-by-play | team box scores, EPA, CPOE, air yards, expected pass rate, every FG/XP | Box scores reproduce official stats (e.g. Houston 2012-11-18: 43/55, 527 yds, 5 TD, 2 INT). |
| Open-Meteo archive (ERA5) | hourly precipitation, snowfall, gusts, humidity, temp and wind at each stadium for the game window | Fills the thesis's missing precipitation, and the 2022–23 games with no game-book reading. Free tier: ~75 requests/min. |
| nflverse weekly player stats | every player's stat line since 1999, kickers included (`scripts/build_player_week.py` → `data/processed/player_week.parquet`) | Outcomes for props and kicker props (#10, #21). `player_games.parquet` keeps the no-hindsight QB/RB1/WR1 roles. |
| Open-Meteo previous runs | what the forecast said 1–3 days before kickoff (2024+) | Measures how much of the observed-weather edge a forecast-driven bettor keeps. |
| Open-Meteo forecast | forecasts for upcoming games | Used by `this_week.py`. |
| NOAA GHCN-Daily (NCEI) | daily highs/lows at each home city's airport | The visitor's 7-day "practice climate" for the acclimation variables. |
| Sportsbook Reviews Online archive | opening and closing spread/total, 2007–2021 | Scraped from 15 season pages; typo lines are dropped and counted. |

## Layout

```
nflweather/      package: fetch, stadiums, weather, boxscore, build, features, models, market, odds, thesis
scripts/         the pipeline steps above
data/raw/        cached downloads          data/processed/  analysis tables (parquet)
output/tables/   every regression/backtest table as CSV
report/          template.html + charts.js -> nfl_weather_report.html
PREREGISTRATION.md  the locked 2026 forward-test rule and decision criteria
```

## Conventions borrowed from sharp-markets

* No look-ahead in anything called a strategy: models are refit on prior
  seasons only; results that use observed kickoff weather are labeled as an
  upper bound.
* Closing-line value is reported next to win rates, and prices are de-vigged
  two ways (proportional and Shin).
* Every betting table counts the variants examined (`output/tables/bet_summary.json`).
* The 2026 forward test is pre-registered and logs every game, not just leans.

Paper research only. Nothing here places bets.
