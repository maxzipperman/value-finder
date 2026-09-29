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

## The Sep 29 audit and what changed

An independent audit ([`../reviews/2026-09-29-astra-audit.md`](../reviews/2026-09-29-astra-audit.md)) traced each rule from trigger to scored result. Amendment 5 settles every gap it found. In short:

- **The pricing model is registered in full**, with a frozen cohort file and hash. A half-point line can't push. The size of the total doesn't move the price, because the data showed no dependence ([`../strategy-research/gate_level_check.py`](../strategy-research/gate_level_check.py)).
- **Inside the −115 cap the expected-value gate can't reject a bet at the rule's own number.** The model's real use is pricing a better number at another book, which every run now logs.
- **Pinnacle's price is the registered test.** A signal at the backup consensus line is labelled secondary and reported separately.
- **Crosswind is logged** on every row (`wx_cross`, `wx_along`), from stadium orientations in `data/processed/stadium_headings.csv` (greerreNFL/stadiums, cross-checked against ThompsonJamesBliss/WeatherData; three closed stadiums where the sources disagree are left out). No rule uses it.
- **The scorer enforces the test:** registered versions only, pre-kickoff rows only, inside the test window, with each decision computed and labelled interim or final.
- **Log, don't drop:** every run leaves a row in `data/forward/runs.csv`; every forecast behind a logged row is kept under its content hash in `data/forward/forecasts/`.

**A second review of those fixes (Sep 29, before they went live)** found one crash and eight places where the new code still fell short of the amendment. All are fixed, each with a test in `tests/test_review.py`:

- **Decisions follow the registered horizons.** Rule B and the model lean are decided after Week 18 of 2026 with 40 bets in the 2026 regular season, and otherwise once, after the 2027 regular season. A decision uses only the bets that kicked off by its horizon, and (since amendment 6) it waits until each of them has a result or is void. The first final decision is written to `data/forward/decisions.csv`, and every later run prints that record; if a corrected score would now change the numbers, the scorer shows both and the recorded decision stands. Before the horizon the scorer prints the numbers and no verdict.
- **The best line is logged for every game the feed lists**, including the ones Pinnacle doesn't quote. A Pinnacle total with no under price no longer blocks the backup price.
- **Every run checks the pricing cohort** against its registered hash and stops if it differs.
- **A run that fails at any stage is recorded and notified**, not only one that fails while building the board. Keys are blanked from error text.
- **The one-time ledger rewrite keeps old rows character for character** and leaves a copy of the ledger as it stood.
- **A number that isn't a price is no price** (anything between −100 and +100), and quarter-point lines are priced as half a bet at each neighbour.

**A review of the scorer (Sep 29) found readings the text still left open.** Amendment 6 settles each one before any outcome exists; no trigger, gate, price cap, stake or metric changes. Each has a test in `tests/test_readings.py`:

- **Void.** A bet whose game kicked off more than 24 hours from the kickoff on its entry row (postponed, moved or cancelled), or that still has no result 30 days after that kickoff, is void: listed by reason and not graded, as a sportsbook would.
- **Pending.** A bet with no result yet holds its decision open. The old test treated a game with no result a week after kickoff as not played, so a late result could flip a final decision.
- **Decided once, and written down** in `data/forward/decisions.csv`, with a fingerprint of the ledger rows behind it. A run on a test ledger writes its own `decisions.csv` beside that ledger.
- **"After Week 18" is a date:** the season's last regular-season kickoff.
- **The model lean enters at its first snapshot 24 hours out that has a posted total.** The live ledger already had a lean with a blank total, which the old code would have graded as a loss.
- **After 2026.** A keep or a drop in 2026 is the decision. An inconclusive 2026 result is decided once more after the 2027 regular season, on both seasons pooled.
- **Ties with the close** are left out of the win rate against the close. Two quoted numbers in amendment 5 are corrected (the gate's zero point is about −135 on a half-point line, and at −115 it rejects an under from 1.5 points below the reference).

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
