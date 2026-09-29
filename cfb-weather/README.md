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

## The Sep 29 audit and what changed

An independent audit ([`../reviews/2026-09-29-astra-audit.md`](../reviews/2026-09-29-astra-audit.md)) traced each rule from trigger to scored result. Amendment 3 settles every gap it found. In short:

- **The pricing model is registered in full**, with a frozen cohort file and hash. A half-point line can't push. The size of the total doesn't move the price, because the data showed no dependence ([`../strategy-research/gate_level_check.py`](../strategy-research/gate_level_check.py)).
- **Inside the −115 cap the expected-value gate can't reject a bet at the rule's own number.** The model's real use is pricing a better number at another book, which every run now logs.
- **Rule HT alerts on the true last scheduled run** before kickoff, so the alert and the scored entry are the same row.
- **The scorer enforces the test:** registered versions only, pre-kickoff rows only, inside the test window, with each decision computed and labelled interim or final.
- **Log, don't drop:** every run leaves a row in `data/forward/runs.csv`; every forecast behind a logged row is kept under its content hash in `data/forward/forecasts/`.

**A second review of those fixes (Sep 29, before they went live)** found one crash and several places where the new code still fell short of the amendment. All are fixed, each with a test in `tests/test_review.py`:

- **The crash:** the first Rule HT signal on the board would have stopped every CFB alert on that run. The last-run check now reads the Mac's own time zone correctly, and it stays right across a clock change.
- **Decisions are made on dates.** Rule B: after 40 signals or Army–Navy (Dec 12, 2026), whichever is later, on the signals that kicked off by then. Rule HT: after the 2027 season's title game. A game is graded only once the schedule marks it completed. Since amendment 4, a decision waits until every bet that kicked off by its horizon has a result or is void (its game moved more than 24 hours, or had no result 30 days after kickoff), so a cancelled game holds a decision open for 30 days at most. The first final decision is written to `data/forward/decisions.csv` by a run on the live ledger, on the real clock, with a schedule refreshed in the last 2 days (the daily check-in's run is one). Every later run prints that record; if a corrected score would now change the numbers, the scorer shows both and the recorded decision stands. Before the horizon the scorer prints the numbers and no verdict.
- **Rule HT drops when it made no money** at the prices taken, so the verdict can't contradict the ROI beside it.
- **The best line is logged for every game the feed lists**, including games neither Pinnacle nor DraftKings quotes.
- **Every run checks the pricing cohort** against its registered hash and stops if it differs.
- **A run that fails at any stage is recorded and notified.** One game's alert failing doesn't stop the others. Keys are blanked from error text.
- **The one-time ledger rewrite keeps old rows character for character** and leaves a copy of the ledger as it stood.

**A review of the scorer (Sep 29) found readings the text still left open.** Amendment 4 settles each one before any outcome exists; no trigger, gate, price cap, stake or metric changes. Each has a test in `tests/test_readings.py`:

- **Void.** A bet whose game kicked off more than 24 hours from the kickoff on its entry row (postponed, moved or cancelled), or that still has no result 30 days after that kickoff, is void: listed by reason and not graded, as a sportsbook would. The review's example was a hurricane-postponed game graded at the old line. A result that lands later brings the bet back; a decision already recorded still stands.
- **Pending.** A bet with no result yet holds its decision open. The old test treated a game with no score a week after kickoff as never played, so a late score could flip a final decision.
- **Decided once, and written down** in `data/forward/decisions.csv`, with a fingerprint of the ledger rows behind it (the entries, and Rule B's later quotes used as closes). Only a real run on the live ledger writes it. A preview with `--now`, a schedule more than 2 days old, a copy of the ledger in `data/forward/`, or a copy of the scorer in a worker's folder records nothing and says why. A run on a test ledger writes its own `decisions.csv` beside that ledger.
- **Dates:** Dec 12, 2026 and Feb 1, 2028, as registered. A game dated after Feb 1, 2028 never counts, whatever its season label.
- **A quote is a total with a valid under price.** Rule HT enters at the last such quote, so a later row with no usable price can't make a bet vanish. Pushes are left out of Rule HT's exact test and count as bets in ROI.
- **Rule B's primary close is the last quote logged after the entry row,** else the captured close, else none (the bet is counted and left out of the CLV). The entry is never its own close. This replaces amendment 2's promise that the captured close could never change the primary CLV or the decision. The scorer prints the book behind each entry and each close. This settles amendment 3's open owner decision.
- **"Not kept"** means no money goes on Rule B; it stays on paper for 2027 only by a dated amendment before 2027 Week 0.
- **Rule HT is reported by price source.** Two quoted numbers in amendment 3 are corrected (the gate's zero point is about −130, and at −115 it rejects an under from 1.5 points below the reference).

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
