# cfb-weather

College football version of `../nfl-weather`: does the totals market under-price wind,
and a live, pre-registered forward test of the one rule that survived.
Rules and evidence: `STRATEGY.md`. Forward-test contract: `PREREGISTRATION.md`.

## Run it

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/fetch_data.py     # cfbfastR schedules/venues/lines + Meteostat station histories (~1 GB)
.venv/bin/python -c "import sys; sys.path.insert(0,'.'); from cfbweather.build import build; build()"
.venv/bin/python scripts/analyze.py        # market vs reality, rules, walk-forward, CLV
.venv/bin/python scripts/calibrate.py      # frozen forecast-to-station wind calibration (already done)
.venv/bin/python scripts/alerts.py --dry-run          # no Odds API credit
.venv/bin/python scripts/log_fill.py GAME_ID --rule rule_ht --line 64.5 --price -108 --book fanduel
.venv/bin/python scripts/score_forward.py         # Rule B, Rule HT, and the cost of waiting
.venv/bin/python -m pytest -q tests
scripts/install_alerts.sh                  # launchd: 7:30, 11:30, 15:30, 19:30 (installed)
```

Every bet alert ends with timing advice (issue #5): wind unders now, Rule HT at the close.
Log the price you actually got with `scripts/log_fill.py`, and `score_forward.py`
reports how much waiting gained or cost against the alert-time quote.

## Data

| Source | What |
|---|---|
| cfbfastR-data (mirrors CollegeFootballData) | schedules with UTC kickoffs, venues with coordinates/dome flag, betting lines 2006–2025 (consensus close = median across books; opening lines where present) |
| CollegeFootballData API v2 (`CFBD_API_KEY`) | every sportsbook's spread and total with openers, team box scores, returning production, talent; player box scores optional (`scripts/fetch_cfbd.py`, cache-first, `--max-calls` budget; about 250 of the free tier's 1,000 monthly calls for 2014–25) | Multi-book CFB line history for free (#8, #16), box scores for props, priors for #11. Writes `data/processed/cfbd_*.parquet`. |
| Meteostat bulk hourly | nearest airport station to each venue (median 9.6 km); wind, temperature, precipitation at kickoff |
| Open-Meteo | forecasts for upcoming games; an ERA5 sample for the frozen calibration |
| The Odds API / ESPN | live totals and prices (Odds API when `ODDS_API_KEY` is set: Pinnacle, else DraftKings, with 8 more books logged for line shopping at no extra cost; responses cached in `data/raw/oddsapi/live/`. ESPN refuses scripted clients at times) |

Shared code copied from nfl-weather (`market.py`, `features.py`, `models.py`,
`notify.py`) is marked in each file; keep them in sync until they move to a
common package.
