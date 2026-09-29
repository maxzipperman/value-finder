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

## Forecast replay on NWS MOS, back to 2006 (issue #40, Sep 29)

Every long-run CFB Rule B number used the wind *observed* at the airport after the game. The live rule bets on a *forecast* made 1–3 days before. The Open-Meteo replay above only reaches back to 2024, because that archive starts there. The National Weather Service's own station forecasts (MOS) are archived, with the time each was issued, back to 2000. [`scripts/mos_replay.py`](scripts/mos_replay.py) replays the rule on those forecasts, using only what had been issued by the day of the bet.

**Status: validated on 2023–25; the 2006–25 download is still running.** The site allows about one request every 7–8 seconds, so the full pull (about 2,100 requests for college football, then about 490 for the NFL) takes roughly five hours. It runs detached on the Mac and is resumable; the numbers below are the FBS 2023–25 sample only. The 20-season result, the one that matters, comes from rerunning `scripts/mos_replay.py` once the pull finishes.

**Results, FBS 2023–25 (2,483 games, every one with a forecast)**

| | 2023 | 2024 | 2025 | Pooled |
|---|---|---|---|---|
| MOS signals (forecast ≥ 15 mph, 1–2 days out) | 65 | 69 | 66 | 200 |
| Under at the close, −110 | 39–26–0 (60.0%) | 32–35–2 (47.8%) | 41–25–0 (62.1%) | **112–86–2 (56.6%)** |
| 95% interval for the win rate | 48–71% | 36–60% | 50–73% | **49.6–63.3%** |
| ROI at −110 | +14.5% | −8.8% | +18.6% | **+8.0%** (−5.3% to +20.8%) |
| Under at the opener (where one exists) | 36–26 (58.1%) | 35–33 (51.5%) | 42–24 (63.6%) | 113–83 (57.7%), 196 games |
| The same games on *observed* wind, at the close | 17–15 | 16–20–1 | 23–12 | 56–47–1 (54.4%), 104 signals |

Pooled, the forecast version wins 56.6% against a break-even of 52.4%. One-sided p = 0.13. The bar for this project is p < 0.00025 (0.05 split over 202 variants), so this is **not evidence of an edge on its own**; three seasons are too few. On these games the total fell 1.6 points on average from the opener to the close, so the market does move toward the under before kickoff.

**What it means**

- **The forecast version does about as well as the observed-wind history, so far.** 56.6% on 200 forecast signals equals the 56.6% the rule's evidence cites. It is in line with the Open-Meteo replay too: on the same 1,670 games of 2024–25, MOS fired 135 times and went 73–60–2 (54.9%); Open-Meteo fired 110 times and went 61–46–3 (57.0%). They agreed on 65 games.
- **Forecasts fire about twice as often as the observed wind would have.** 200 signals against 104. MOS runs about 1 mph windier than the airport later records, so it crosses 15 mph on 6.5% of games against 4.2% observed. Only 38% of MOS signals saw 15 mph actually arrive.
- **The edge sits where the wind arrives.** When both MOS and the observed wind reached 15 mph, the under went 46–29–1 (61.3%, 76 games). When MOS fired and the wind didn't come, 66–57–1 (53.7%, 124 games), about break-even. When the wind came but MOS missed it, 10–18 (28 games). That is the same pattern the Open-Meteo replay found, and it isn't something a bettor can act on in advance: these splits use the result.
- **One bad year in three.** 2024 was a losing year on MOS (47.8%), though Open-Meteo went 59.3% in 2024. The two forecasts flagged different games that year and got different results. Swings like this are normal at 65 signals a season.

**Is 15 mph on MOS the same as 15 mph observed?** Not quite. MOS reads about 1 mph above what is later observed: 1.0 mph at the same airport, and 1.03, 1.08 and 1.04 mph in the three seasons. Its typical miss one day out is 2.2 mph, and its correlation with the observed wind is 0.75. So 15 mph on MOS behaves like roughly 14 mph observed. The live rule's own forecast behaves the same way: on 2024–25, MOS sits 0.5 mph above Open-Meteo on the station scale at lead 1 and level with it at lead 2. MOS is also slightly more accurate than Open-Meteo against the observed wind (typical miss 2.15 against 2.34 mph at lead 1). The threshold was not changed to compensate; this replay tests the rule as registered.

**What it does not show**

- **That the edge is real.** Three seasons, p = 0.13, one variant. The 20-season run is the test; with roughly 1,000 signals it clears the multiple-testing bar only if it wins about 58% or more.
- **The price you would actually get.** Every entry is the consensus total at an assumed −110. The rule bets 1–3 days early, so a real entry sits between the opener (57.7% here, which flatters it) and the close (56.6%, which understates it).
- **Lead 3.** GFS MOS doesn't reach far enough to cover a kickoff three days out, so this replays leads 1 and 2 only (one game of 2,483 had a lead-3 forecast).
- **Stadium wind.** MOS forecasts the airport, like the observed wind the evidence uses; neither is the wind in the stadium.
- **Anything about Rule HT**, which doesn't use weather.

**Variants:** 1 for college football (and 1 for the NFL replay, when it runs). The hub adds them to the running total (200 on Sep 29, so 202).

**What's left.** When the download finishes (`~/.cache/value-finder/mos/fetch_full.log` ends with `mos_pull_all: finished`), run `scripts/mos_replay.py` with no arguments here and in `../nfl-weather`, commit the outputs, and replace the 2023–25 table above with the 2006–25 one. The code needs no change.

**How it works**

- **Forecasts:** the National Weather Service's GFS MOS ("Model Output Statistics"), the station forecast NWS forecasters start from. It is the GFS model corrected, airport by airport, to what that airport's instruments report, so it is already on the station scale; no calibration is applied. The Iowa Environmental Mesonet (IEM) keeps every run since 2000, each stamped with its run time. Runs come out four times a day (00, 06, 12, 18 UTC) with a step every 3 hours out to 60 hours, then at 66 and 72 hours. Wind is in knots; 1 knot = 1.1508 mph.
- **Stations:** each venue gets the nearest airport on the NWS MOS station list within 40 km ([`data/processed/mos_station_map.csv`](data/processed/mos_station_map.csv), built by [`scripts/mos_stations.py`](scripts/mos_stations.py)). 136 of the 139 venues with eligible games have one (median 8.2 km); for 115 of them it's the same airport the observed-wind backtests used. Three venues have none within 40 km and are left out, not guessed: Ole Miss (Vaught-Hemingway), Ohio (Peden) and Louisiana Tech (Joe Aillet), 322 eligible games in 2006–25 between them. If the nearest station has no forecast for a game, the next-nearest within 40 km is used; in 2023–25 that was 39 games, because Chapel Hill's airport (UNC and Duke) has no MOS runs in those seasons.
- **Timing, no lookahead:** lead time is counted the way the live rule counts it (amendment 3): the kickoff's Eastern date minus the date of the run. For lead 1, 2 and 3 the replay takes the **last** run on that date. A run is published about 4 hours after its run time (the code assumes 5), which is before that day's 7:30 PM Pacific alert run for all four daily runs, so a bet on that day could have used it; the code checks this for every game ([`cfbweather/mos.py`](cfbweather/mos.py), tests in [`tests/test_mos.py`](tests/test_mos.py)). Nothing from the game day itself is used.
- **The kickoff window:** the rule averages wind over the kickoff hour and the next three hours. MOS gives a value every 3 hours, so each of those four hours is read off a straight line between the two MOS steps around it (an hour that falls on a step takes that step's value), and the four are averaged. If any of the four hours falls outside the run's steps, that lead is missing for that game.
- **Lead 3 is almost never available.** A run from three days before reaches only 72 hours ahead, which ends before a typical kickoff window closes. So in practice this replays leads 1 and 2. In the Open-Meteo replay above, 19 of the 110 signals fired only at lead 3; they went 9–10.
- **Trigger (the one variant):** MOS wind at or above **15 mph** at lead 1, 2 or 3. The threshold isn't tuned; the bias table shows how MOS's 15 mph compares with observed 15 mph.
- **Games:** FBS-involved, outdoor, with venue coordinates, a known kickoff, a closing total and a final score, the same filter as the Open-Meteo replay.
- **Prices:** the consensus closing total (cfbfastR) at an assumed −110, as the primary; also the opening total where one exists (cfbfastR's consensus opener, else the median CFBD opener). The rule bets 1–3 days before kickoff, so the real entry sits between the two: the opener is usually posted before the forecast that fires, so it flatters the result, and the close understates it.

**Run it.** The download is free and needs no key, but it is slow: IEM answers "too many requests" to more than about one request every 7 seconds, so it makes one request per (MOS station, season), and the whole 2006–25 pull is about 2,100 requests. The cache lives outside any checkout, at `~/.cache/value-finder/mos/`; link it into a checkout with

```bash
mkdir -p ~/.cache/value-finder/mos
ln -s ~/.cache/value-finder/mos cfb-weather/data/raw/mos
ln -s ~/.cache/value-finder/mos nfl-weather/data/raw/mos
```

(without the link the code uses `~/.cache/value-finder/mos` directly). Then:

```bash
.venv/bin/python scripts/mos_stations.py                 # the station map (needs data/raw/meteostat)
.venv/bin/python scripts/mos_fetch.py --plan             # how many requests are left
nohup scripts/mos_pull_all.sh > ~/.cache/value-finder/mos/fetch_full.log 2>&1 &   # CFB, then NFL; resumable
.venv/bin/python scripts/mos_replay.py                   # 2006-25 (or --seasons 2023-2025)
```

Outputs: per-game rows in `data/processed/mos_replay*.parquet`, tables in `output/tables/mos_replay_seasons*.csv` and `output/tables/mos_bias*.csv`, and the log in `output/mos_replay*.log`.

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
- **Decisions are made on dates, once.** Rule B: after 40 signals or Army–Navy (Dec 12, 2026), whichever is later, on the signals that kicked off by then. Rule HT: after the 2027 season's title game. A cancelled game can't hold a decision open, and a game is graded only once the schedule marks it completed. Before the horizon the scorer prints the numbers and no verdict.
- **Rule HT drops when it made no money** at the prices taken, so the verdict can't contradict the ROI beside it.
- **The best line is logged for every game the feed lists**, including games neither Pinnacle nor DraftKings quotes.
- **Every run checks the pricing cohort** against its registered hash and stops if it differs.
- **A run that fails at any stage is recorded and notified.** One game's alert failing doesn't stop the others. Keys are blanked from error text.
- **The one-time ledger rewrite keeps old rows character for character** and leaves a copy of the ledger as it stood.

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
