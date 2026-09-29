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

## Forecast replay (2024–25)

Every earlier CFB Rule B number used the wind *observed* at the nearest airport. Live, the rule fires on a *forecast* 1–3 days out. [`scripts/forecast_replay.py`](scripts/forecast_replay.py) replays 2024 and 2025 using only the forecasts that existed at bet time.

**How it works**

- **Forecasts:** Open-Meteo's previous-runs archive (`data/raw/openmeteo_prev/`, cached), for all 1,709 eligible games. None is missing.
- **Scale:** each forecast is put on the station scale with the frozen calibration. It isn't refit.
- **Gates:** the wind trigger (15+ mph at lead 1, 2 or 3) is the only gate that can bind here. cfbfastR has no prices, so every entry is at −110, which passes the −115 gate by construction, and the EV gate is evaluated at the closing total as both line and market reference, so it takes the same value (+0.081) for every game and never rejects one. *Correction, Sep 28:* the first version of this section said the gates were applied "exactly" as on the live board; they were computed, but two of the three could not bind. A replay with real prices needs the Pinnacle history (F1 in the Odds API plan).
- **Entry:** the closing total at −110. It exists after every lead's forecast was public, and `tests/test_forecast_replay.py` checks that no quote predates its forecast.
- **Output:** per-game rows in [`data/processed/forecast_replay.parquet`](data/processed/forecast_replay.parquet); the log is [`output/forecast_replay.log`](output/forecast_replay.log).

**Results**

| | 2024 | 2025 | Pooled |
|---|---|---|---|
| Forecast signals | 57 | 53 | 110 |
| Record at the close | 32–22–3 (59.3%) | 29–24–0 (54.7%) | **61–46–3 (57.0%)**, one-sided p = 0.19 |
| ROI at −110 | +13.1% | +4.5% | +8.8% |
| Same rule on observed wind | 16–20–1 | 23–12–0 | 39–32–1 (54.9%, 72 signals) |

**Forecast and observed wind agree on 94.7% of games**, but mostly because neither fires. Only 46 games fired on both. Where they agree, the under went **28–17–1 (62%)**. It went 33–29–2 (53%) when only the forecast fired, and 11–15–0 (42%) when only the observed wind did.

**What it means**

- **The edge survives the switch to forecasts.** 57% matches the 56.6% observed-wind history, but two seasons can't confirm it (p = 0.19).
- **It is strongest when the forecast wind actually arrives.** False alarms thin it out.
- **Forecasts run 0.6–1.1 mph above the station wind,** with a mean absolute error of 2.4–2.7 mph and a correlation of 0.64–0.71. Most signals fire first at lead 3 (71 of 110).
- **Rule B stays as registered.** Nothing here argues for an amendment before Oct 1.

**Also reported, with a caveat:** entering at the opener instead gives +1.19 points of CLV (95% CI +0.79 to +1.59), and 26–19–2 in the dress-rehearsal window, against 21–10–1 with a perfect forecast. The opener predates the forecast, so both numbers overstate what was achievable.

This adds **1 variant**, for a running total of 135.

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
