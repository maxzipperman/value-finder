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

## Consensus home spread (issue #36, Sep 28)

`build.home_spreads()` used to drop any (game, book) whose spread rows it couldn't pair up, and it didn't count them. A third of them were dropped:

| Why a (game, book) was dropped | Pairs |
|---|---|
| No team ids on the line rows (2014, 2022–25) | 2,710 |
| Not exactly two rows, mostly byte-identical duplicates (2013–19) | 23,068 |
| Neither row matched a team name: sportsbook codes such as NIL, OHI, BGN | 27,661 |
| **Total, of 163,075 pairs for scheduled games** | **53,439 (32.8%)** |

**The fix.** Team ids now come from the schedule. Each row is matched to its team on its own, so duplicates, one-sided pairs and stray rows no longer matter. 117 sportsbook codes were added in [`cfbweather/spread_aliases.csv`](cfbweather/spread_aliases.csv), built by [`scripts/spread_aliases.py`](scripts/spread_aliases.py) from which games each code appears in. Every build prints the remaining drops by reason and season. What's left is 419 pairs whose rows disagree, and 287 of those 291 games still get a spread from other books.

**Checked against CFBD** ([`scripts/spread_audit.py`](scripts/spread_audit.py), log in [`output/spread_audit.log`](output/spread_audit.log)). The comparison covers played games from 2014 to 2025 that have a closing total and a CFBD spread.

| | Before | After |
|---|---|---|
| Games with a consensus home spread | 7,821 of 12,053 (64.9%) | 12,051 (99.98%) |
| Within 1 point of CFBD | 97.7% | 97.2% |
| Within 3 points | 99.5% | 99.3% |
| Opposite favorites, 1+ point each | 12 | 12, all pick'em games (both spreads within 2.5) |

**`data/processed/games.parquet` still holds the old column.** A rebuild adds 5,491 spreads, changes 40, and touches no other column. It also moves Rule HT's 2016–25 history, the record that `STRATEGY.md` cites:

| Rule HT, 2016–25 | Record |
|---|---|
| Before (the cited evidence) | 373–273 (57.7%) |
| After, all games | 502–393 (56.1%) |
| After, FBS-involved games only (the forward test's population) | 434–326 (57.1%) |
| Only the games the old code dropped, old thresholds | 113–99 (53.3%) |

**Rebuilt on Sep 28 (owner decision).** `games.parquet` now holds the corrected column. Rule HT and its frozen 2026 threshold of 62.6175 are unchanged; on the rebuilt data the 2025 mean recomputes to 52.53 (62.53 + 10), 0.08 below the frozen value, and `test_ht_2026_threshold_matches_the_screen` now pins the frozen constant and that recompute. The 109-row screen is unchanged by the rebuild (it uses the spread only as a has-a-line filter). The pre-checks that use the spread itself moved: Rule HT by spread size 179–114 (61.1%) → 249–169 (59.6%) at 14+ and 194–159 (55.0%) → 253–224 (53.0%) under 14; Rule HT at the consensus close 220–158 (58.2%) → 230–171 (57.4%), at the best book 223–156 → 234–168 (58.2%); CFB Rule B 131–102 → 135–102 (57.0%) and 133–100 → 137–100 (57.8%); the Rule HT open-to-close rise +0.83 → +0.85. **2027 threshold:** the owner chose the FBS-involved population for 2027 (the games the rule can fire on); a dated amendment to `PREREGISTRATION.md` will register it before 2027 Week 0. On 2025 data the two means differ by 0.01.

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
