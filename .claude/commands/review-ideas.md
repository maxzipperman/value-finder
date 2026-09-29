---
description: Review the whole Value Finder repo, then propose consolidations and new ideas (read-only; writes one report)
---

Review the Value Finder repo efficiently, then propose ways to consolidate and improve it. **Don't change code, call paid APIs, re-download data, or open issues.** The output is one report, described at the end. $ARGUMENTS

## What this project is

Paper-only sports-betting research. Each thesis becomes a pre-registered forward test graded on closing-line value (CLV) before any money goes in. The owner wrote a 2014 undergraduate thesis on weather and NFL passing. Everything started from that.

## Read in this order (stop reading a file once you have what you need)

1. `STATUS.md`: current state, the forward-test scoreboard, the backlog (GitHub issues #4–#11, label `idea`).
2. `CLAUDE.md`: the rules every project follows. Also `sharp-markets/CLAUDE.md`, which is stricter.
3. `strategy-research/README.md`: the 109-variant screen, what faded, and the eight ranked ideas.
4. Each project's docs, then its code only where a check needs it.

## File map

**Root**
- `STATUS.md`, `CLAUDE.md`: hub docs. `.gitignore` keeps `.env`, `data/`, `.venv/`, parquet, DuckDB and PDFs out of git.
- `thesis/*.txt`: the 2014 thesis as text. `nfl-weather/nflweather/thesis.py` transcribes its coefficients.
- `thesis-research/`: literature review and referee-style feedback on the thesis (`nfl-weather-thesis-review.md`; the HTML is the same content).

**`nfl-weather/`**: the NFL weather study and live forward test.
- `README.md`, `STRATEGY.md` (playbook v2: Rule B wind unders, watch list, avoid list), `PREREGISTRATION.md` (the rule, the decision criteria, amendments 1 and 2).
- `nflweather/`:
  - `fetch.py`, `weather.py`, `stadiums.py`, `boxscore.py`, `odds.py` (SBR open/close archive 2007–21), `oddsapi.py` (Pinnacle via The Odds API), `players.py`.
  - `build.py` builds the processed datasets.
  - `features.py` defines weather features and thresholds (`RAIN_IN = 0.06`).
  - `market.py` has de-vig, EV, and line- and price-aware pricing.
  - `models.py` wraps pyfixest.
  - `board.py` builds the weekly board.
  - `notify.py` sends macOS and ntfy alerts.
- `scripts/`:
  - The study pipeline: `replicate.py` → `audit_thesis.py` → `extend.py` → `betting.py` → `model_compare.py`, plus `strategies.py`.
  - The live loop: `this_week.py`, `alerts.py` (launchd, 4×/day), `score_forward.py`.
  - Pinnacle tools: `odds_api.py`, `pinnacle_check.py`.
  - Other: `props_research.py`, `build_player_week.py` (every player-week, kickers included → `player_week.parquet`), `report_data.py` (renders `report/nfl_weather_report.html`), `run_all.sh`, `install_alerts.sh`.
- `tests/test_core.py`, `tests/test_rules.py`: pinned facts and the audit's alert and pricing probes.
- `output/tables/*.csv` and `output/*.log`: every published number should trace to one of these.

**`cfb-weather/`**: the college football version, with its own Rule B forward test from Oct 1, 2026.
- `cfbweather/`: `features.py`, `market.py`, `models.py` and `notify.py` are *copies* of the nfl-weather files and are supposed to stay in sync. Also `fetch.py` (cfbfastR, Meteostat, Open-Meteo), `build.py`, `board.py`, `players.py`, `weather.py`.
- `scripts/`: `analyze.py`, `calibrate.py` (a frozen forecast-to-station wind calibration fit on seasons ≤ 2023), `alerts.py`, `score_forward.py`, `props_research.py`.
- `tests/test_rules.py`.

**`sharp-markets/`**: Kalshi vs sharp sportsbooks (Pinnacle, LowVig, BetOnline). uv, DuckDB, NBA first, sport-agnostic.
- `docs/PLAN.md`: hypotheses H1 (static edge), H2 (lag after sharp moves), H3 (fade the public), H4a (Kalshi NFL totals vs wind).
- `src/markets/`:
  - GET-only clients: `kalshi/`, `oddsapi/` (with a credit budget), `http.py`.
  - `cache.py` is a cache-first raw store.
  - `devig.py`, `fees.py` (Kalshi taker fee).
  - `build/` loads DuckDB and matches games.
  - `analysis/`: `backtest.py`, `leadlag.py`.
  - `research/`: `nfl_weather.py` is H4a, `kaggle_h3.py`.
- `config/`: per-sport YAML and team aliases. `reports/h4a_nfl_weather_2025.md`.
- `tests/`: `test_no_order_code.py` enforces paper-only.

**`strategy-research/`**
- `screen.py` screens candidate theses on data already in the repo (109 variants).
- `prechecks.py` runs free pre-checks for backlog issues (#17 longshot bias, #6 crosswind and halftime split, #4 by spread size). It adds 20 variants, for a running total of 129.
- `odds-api-credits.md`: which Odds API plan to buy and when, the credit cost and research value of every use, and the cost rules. `odds_budget.py` recomputes its numbers (no API calls).
- `output/*.csv` holds the results: screens, key numbers, line moves, the Kalshi ladder, calibration slopes, and the Odds API budget (`odds_api_*.csv`).

**On the owner's Mac only (gitignored; missing in a cloud checkout)**
- `*/data/raw/`: 2 GB of play-by-play, weather, odds and Kalshi caches.
- `*/data/processed/*.parquet`: about 8 MB of analysis datasets.
- `*/data/forward/ledger.csv`: the forward-test ledgers.
- `sharp-markets/data/markets.duckdb`.
- `*/.env`: `ODDS_API_KEY` (empty so far) and `NTFY_TOPIC`.
- The launchd jobs `com.nflweather.alerts` and `com.cfbweather.alerts`.

If a check needs one of these and it's missing, say so. Don't rebuild it.

## Review checklist

Only report problems you can verify. For each one, give the file and line, the evidence, and a severity: **blocks the forward test**, **wrong number**, **risk**, or **cleanup**.

1. **Numbers trace to outputs.** Take the ~10 headline numbers in `STATUS.md`, both `STRATEGY.md` files and `strategy-research/README.md` (for example 57.2% of 682, 373–273, 74.7%, the 0.89 slope). Find each one in `output/`. Flag any that don't match or can't be found.
2. **The code matches the pre-registration.** Check that `alerts.py`, `board.py` and `score_forward.py` in both weather projects implement exactly what `STRATEGY.md` / `PREREGISTRATION.md` say: wind ≥ 15 mph, 1–3 days out, under at −115 or better, positive EV at the offered line and price, `rules_version`, and the decision rule. Any gap invalidates the test.
3. **No lookahead.** Check the calibrations (≤ 2023), the walk-forward refits, the "prior-season mean" thresholds, and the snapshot-time rules in sharp-markets.
4. **Duplication and drift.** Diff the shared weather copies (`features`, `market`, `models`, `notify`). Count the Odds API clients and de-vig implementations across projects. Find constants duplicated across projects (the H4a rain threshold drifted once already).
5. **Money-critical math is tested.** American-odds conversion, de-vig (proportional and Shin), EV at a price, break-evens (−110, −115, Kalshi at 50¢ plus fee), teaser break-evens, CLV sign conventions.
6. **Operational risks.** Ledgers that exist only on one laptop, alert jobs that fail silently, empty API keys, an alert with no price, and what breaks in a cloud session.

## Odds API plan check

`strategy-research/odds-api-credits.md` holds the recommended Odds API plan and the credit cost of every use. Re-check it on every review:

1. **Numbers.** Rerun `nfl-weather/.venv/bin/python strategy-research/odds_budget.py --no-save` from the repo root (free, no API calls, writes nothing) and compare it with the file's use-case table. Flag any use whose credits moved by more than 10%, and any Odds API call site (grep `api.the-odds-api.com`, `oddsapi`) that isn't in the table.
2. **Plan vs calendar.** Compare the month-by-month plan with `STATUS.md` ("Waiting on you") and today's date. Flag a big month that is due, a paid month that lapsed with pulls still undone, and a live tier too small for the alerts plus any running collector.
3. **Data worth buying.** For any backlog issue or new idea that needs Odds API data not in the table, give its credits (using the file's cost rules), a 1–5 research value grounded in `strategy-research/README.md`, and the plan and month it fits. Also flag data the file plans to buy that the latest results make worthless.
4. **Facts.** Where you can, check that plan prices, cost rules and history start dates in the file are still current. List what you couldn't verify.

## Ideas

Then propose **new ideas and combinations of existing ones**. Combinations should work across projects, for example:
- The weather triggers routed through a price engine across books and exchanges.
- CFB high totals combined with wind.
- The timing overlay combined with line lag.
- The Kalshi ladder combined with the weather rules.
- Props combined with key numbers.

Also propose **consolidations**, such as a shared package for odds math, features, notifications and ledger scoring, or one alert runner for both sports.

For each idea, give:
- What it is, and why the market would get it wrong (the mechanism).
- The evidence already in the repo, or the cheapest test that would produce some.
- The data it needs, with its source and cost (Odds API credits, CFBD tier, free).
- Where it lives (which folder), and what it reuses.
- How many new variants it adds, and how it would be pre-registered and graded.
- Effort (S/M/L) and expected value to the project.

Don't re-propose anything the screen already rejected (the "Faded or never there" and "Skip" sections) unless you have a new reason.

## Output

Write one report to `reviews/<YYYY-MM-DD>-review.md` with these sections:
1. Verdict: three sentences.
2. Verified problems, most severe first.
3. Consolidation plan.
4. Ranked ideas.
5. Odds API plan: is the plan in `strategy-research/odds-api-credits.md` still right, and what data is worth buying next?
6. Proposed GitHub issues: a title, labels and a two-line body for each. Don't create them.
7. Anything you couldn't check, and why.

Keep it under about 400 lines. If subagents are available, review the three projects in parallel and then merge the results. Report back in chat with the verdict and the top five items.
