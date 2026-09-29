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

**Close capture** (amendment 2). Every 15 minutes `ops/capture_closes.sh` runs `scripts/capture_close.py`.
When FBS games kick off in 2–20 minutes, it makes one Odds API call and adds one row per game in that kickoff
slot to `data/forward/closes.csv`: Pinnacle's total and prices, else DraftKings'. If some game in the slot has
neither, the slot is tried once more on the next run, for a second credit. A feed event is one event in the
odds feed: a game as the feed lists it. Since Sep 29 each game takes at most one feed event: one with its two
teams that starts within 6 hours of its scheduled kickoff, preferring Pinnacle, then DraftKings (as the board
does), then the one nearest the kickoff. Before, it matched on the teams alone, so a relisted event, or a rematch
such as a conference title game in the same feed, added a second row, and when both rows had a price the scorer
took whichever the feed gave last. A tie between two equally good feed events, or no feed event within 6 hours,
leaves the game's close missing, and the log says why. Tests: `tests/test_close_capture.py`.
*Note, Sep 29 (amendment 5):* this rule is now registered, with one change. Two feed events equally near the
kickoff that are priced at the same book with the same quote (the same total and prices) are the same game
listed twice, so the first in the feed is taken; a tie between different quotes, or between feed events priced
at neither book, still leaves the close missing.

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

Count at merge (Sep 29, 2026): 233; bar p < 0.000215.

Every long-run CFB Rule B number used the wind *observed* at the airport after the game. The live rule bets on a *forecast* made 1–3 days before. The Open-Meteo replay above only reaches back to 2024, because that archive starts there. The National Weather Service's own station forecasts (MOS) are archived, with the time each was issued, back to 2000. [`scripts/mos_replay.py`](scripts/mos_replay.py) replays the rule on those forecasts, using only what had been issued by the day of the bet.

**Status: the method is checked on 2023–25, and the result there is not significant (p = 0.13). The 2006–25 download is still running.** The site allows about one request every 7–8 seconds, so the full pull (2,119 requests for college football, then 487 for the NFL, about 2 GB in all) takes five to six hours. It runs detached on the Mac and is resumable; the numbers below are the FBS 2023–25 sample only. The larger historical check, 2006–25, comes from rerunning `scripts/mos_replay.py` once the pull finishes.

*Revised after a review, Sep 29:* no result changed. Some of the wording below claimed more than the numbers show, and it is corrected. The numbers behind the corrections come from [`scripts/mos_replay_checks.py`](scripts/mos_replay_checks.py), which reads the replay's per-game rows and changes nothing in the replay (log: [`output/mos_replay_checks_2023_2025.log`](output/mos_replay_checks_2023_2025.log)).

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

- **The forecast version does about as well as the observed-wind history, so far.** 56.6% on 200 forecast signals equals the 56.6% the rule's evidence cites. It is in line with the Open-Meteo replay too: on the same 1,670 games of 2024–25, MOS fired 135 times and went 73–60–2 (54.9%); Open-Meteo fired 110 times and went 61–46–3 (57.0%). 65 of Open-Meteo's 110 signals were also MOS signals.
- **Forecasts fire about twice as often as the observed wind would have: 200 signals against 104, for two reasons.** First, MOS runs about 1 mph windier than the airport later records, so lead 1 alone reaches 15 mph on 162 games (6.5% of 2,483) against 104 (4.2%) for the observed wind. Second, the rule gets two looks: lead 2 adds 38 games that lead 1 didn't flag, which makes 200 (8.1%). Only 76 of the 200 MOS signals (38%) saw 15 mph actually arrive.
- **Where the wins fell (descriptive; uses the result).** When both MOS and the observed wind reached 15 mph, the under went 46–29–1 (61.3%, 76 games). When MOS fired and the wind didn't come, 66–57–1 (53.7%, 124 games), about break-even. When the wind came but MOS missed it, 10–18 (28 games). The gap between 61.3% and 53.7% is well within chance (Fisher exact test, p = 0.30). The both-fired group on its own beats break-even at one-sided p = 0.075, before any allowance for the other tests, and that group is picked using the observed wind, which no one knows at bet time. The rule as a whole is at p = 0.13, so no edge has been shown for these splits to locate. The Open-Meteo replay splits the same way (28–17–1 when both fired, 33–29–2 when only the forecast did), but that isn't independent confirmation: its games are 2024–25, inside this sample, and 65 of its 110 signals are also MOS signals (39 of its 46 both-fired games and 26 of its 64 forecast-only games).
- **One bad year in three.** 2024 was a losing year on MOS (32–35–2, 47.8%, 69 signals), though Open-Meteo went 32–22–3 (59.3%, 57 signals) in 2024. The two forecasts shared only 33 signals that year and got different results. Swings like this are normal at 65 signals a season.

**Is 15 mph on MOS the same as 15 mph observed?** Not quite. At lead 1, MOS reads about 1 mph above what is later observed: +1.05 mph over 2,480 games with both (+1.00 on the 2,105 at the same airport), and +1.03, +1.08 and +1.04 mph in 2023, 2024 and 2025 (813, 814 and 853 games). On those 2,480 games its typical miss one day out is 2.2 mph, and its correlation with the observed wind is 0.75. By how often it fires, 15 mph on MOS at lead 1 matches about 13.5 mph observed: MOS reaches 15 on 6.5% of games, and the observed wind reaches 13.5 on 6.6%. Games forecast at 14–16 mph at lead 1 averaged 12.7 mph observed (101 games). The live rule's own forecast behaves the same way: on the 1,670 games of 2024–25 in both replays, MOS sits 0.5 mph above Open-Meteo on the station scale at lead 1 and level with it at lead 2. MOS is also slightly more accurate than Open-Meteo against the observed wind (typical miss 2.15 against 2.34 mph at lead 1, same 1,670 games). The threshold was not changed to compensate; this replay tests the rule as registered.

**What it does not show**

- **That the edge is real.** Three seasons, p = 0.13, one variant. The 2006–25 run is the larger historical check, not an independent test. 76 of the 200 MOS signals here also fired on the observed wind, which makes them the kind of game Rule B's 990-game observed-wind evidence is built from, so over 2006–25 the replay grades many of the same outcomes again; and it re-includes 2023–25, which has now been seen. With roughly 1,000 signals it clears the multiple-testing bar only if it wins about 58% or more. A pass would support the 2027 pre-registration; it would not replace the forward test. The replay code is frozen for that run as it stands at commit 99b3a53.
- **The price you would actually get.** Every entry is the consensus total at an assumed −110. The rule bets 1–3 days early, so a real entry sits between the opener (57.7% here, which flatters it) and the close (56.6%, which understates it).
- **Lead 3.** GFS MOS doesn't reach far enough to cover a kickoff three days out, so this replays leads 1 and 2 only (one game of 2,483 had a lead-3 forecast).
- **Stadium wind.** MOS forecasts the airport, like the observed wind the evidence uses; neither is the wind in the stadium.
- **Anything about Rule HT**, which doesn't use weather.

**Variants:** 1 for college football (and 1 for the NFL replay, when it runs). The hub adds them to the running total (200 on Sep 29, so 202).

**What's left.** When the download finishes (`~/.cache/value-finder/mos/fetch_full.log` ends with `mos_pull_all: finished`), run `scripts/mos_replay.py` with no arguments here and in `../nfl-weather`, and `scripts/mos_replay_checks.py` here; commit the outputs, and replace the 2023–25 table above with the 2006–25 one. The replay code needs no change.

**How it works**

- **Forecasts:** the National Weather Service's GFS MOS ("Model Output Statistics"), the station forecast NWS forecasters start from. It is the GFS model corrected, airport by airport, to what that airport's instruments report, so it is already on the station scale; no calibration is applied. The Iowa Environmental Mesonet (IEM) keeps every run since 2000, each stamped with its run time. Runs come out four times a day (00, 06, 12, 18 UTC) with a step every 3 hours out to 60 hours, then at 66 and 72 hours. Wind is in knots; 1 knot = 1.1508 mph.
- **Stations:** each venue gets the nearest airport on the NWS MOS station list within 40 km ([`data/processed/mos_station_map.csv`](data/processed/mos_station_map.csv), built by [`scripts/mos_stations.py`](scripts/mos_stations.py)). 136 of the 139 venues with eligible games have one (median 8.2 km); for 115 of them it's the same airport the observed-wind backtests used. Three venues have none within 40 km and are left out, not guessed: Ole Miss (Vaught-Hemingway), Ohio (Peden) and Louisiana Tech (Joe Aillet), 322 eligible games in 2006–25 between them. If the nearest station has no forecast for a game, the next-nearest within 40 km is used; in 2023–25 that was 39 games, because Chapel Hill's airport (UNC and Duke) has no MOS runs in those seasons.
- **Timing, no lookahead:** lead time is counted the way the live rule counts it (amendment 3): the kickoff's Eastern date minus the date of the run. For lead 1, 2 and 3 the replay takes the **last** run on that date. A run is published about 4 hours after its run time (the code assumes 5), which is before that day's 7:30 PM Pacific alert run for all four daily runs, so a bet on that day could have used it; the code checks this for every game ([`cfbweather/mos.py`](cfbweather/mos.py), tests in [`tests/test_mos.py`](tests/test_mos.py)). Nothing from the game day itself is used.
- **The kickoff window:** the rule averages wind over the kickoff hour and the next three hours. MOS gives a value every 3 hours, so each of those four hours is read off a straight line between the two MOS steps around it (an hour that falls on a step takes that step's value), and the four are averaged. If any of the four hours falls outside the run's steps, that lead is missing for that game.
- **Lead 3 is almost never available.** A run from three days before reaches only 72 hours ahead, which ends before a typical kickoff window closes. So in practice this replays leads 1 and 2. In the Open-Meteo replay above, 19 of the 110 signals fired only at lead 3; they went 9–10.
- **Trigger (the one variant):** MOS wind at or above **15 mph** at lead 1, 2 or 3. The threshold isn't tuned; the bias table shows how MOS's 15 mph compares with observed 15 mph.
- **Games:** FBS-involved, outdoor, with venue coordinates, a known kickoff, a closing total and a final score, the same filter as the Open-Meteo replay.
- **Prices:** the consensus closing total (cfbfastR) at an assumed −110, as the primary; also the opening total where one exists (cfbfastR's consensus opener, else the median CFBD opener). The rule bets 1–3 days before kickoff, so the real entry sits between the two: the opener is usually posted before the forecast that fires, so it flatters the result, and the close understates it.

**Run it.** The download is free and needs no key, but it is slow: IEM answers "too many requests" to more than about one request every 7 seconds, so it makes one request per (MOS station, season). The whole pull is 2,119 requests for college football 2006–25 and 487 for the NFL 2004–25, about 2,600 in all, and the cache grows to about 2 GB (about 0.7 MB a request). Most of that is never read. Each request returns every run of every day with every MOS variable, and the replay reads one run a day: the last one, which was the 18Z run for all 2,483 games at leads 1 and 2 in 2023–25. The other three runs matter only as a fallback when an 18Z run is missing, so about three quarters of the rows go unused. IEM's request script ([its source](https://github.com/akrherz/iem/blob/main/pylib/iemweb/request/mos.py)) can't filter by cycle or by variable, and asking for the 18Z runs one at a time would take far more requests, so the bulk pull stays. The cache lives outside any checkout, at `~/.cache/value-finder/mos/`; link it into a checkout with

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
.venv/bin/python scripts/mos_replay_checks.py            # the descriptive checks the write-up quotes
```

Start the pull from a checkout that will outlive it, not from a worker's worktree: a worktree is removed when its worker is archived, and the later legs of the pull run from it. `mos_pull_all.sh` waits 60 seconds before each leg, because each leg is a new process whose pacing starts fresh, and a leg that opened right after the previous one's last request drew a "too many requests" answer and a slower pace for the rest of that leg.

Outputs: per-game rows in `data/processed/mos_replay*.parquet`, tables in `output/tables/mos_replay_seasons*.csv` and `output/tables/mos_bias*.csv`, the log in `output/mos_replay*.log`, and the checks in `output/mos_replay_checks*.log`.

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
  - *Note, Sep 29 (amendment 4):* a cancelled game now holds a decision open for 30 days at most. A decision waits until every bet that kicked off by its horizon has a result or is void (its game moved more than 24 hours, or had no result 30 days after kickoff). "Once" now rests on the written record: the first final decision is written to `data/forward/decisions.csv` by a run on the live ledger, on the real clock, with the current season's schedule refreshed in the last 2 days (the daily check-in's run is one). Every later run prints that record; if a corrected score would now change the numbers, the scorer shows both and the recorded decision stands.
- **Rule HT drops when it made no money** at the prices taken, so the verdict can't contradict the ROI beside it.
- **The best line is logged for every game the feed lists**, including games neither Pinnacle nor DraftKings quotes.
- **Every run checks the pricing cohort** against its registered hash and stops if it differs.
- **A run that fails at any stage is recorded and notified.** One game's alert failing doesn't stop the others. Keys are blanked from error text.
- **The one-time ledger rewrite keeps old rows character for character** and leaves a copy of the ledger as it stood.

**A review of the scorer (Sep 29) found readings the text still left open.** Amendment 4 settles each one before any outcome exists; no trigger, gate, price cap, stake or metric changes. A final review before registration, the same day, added the last four items. Each has a test in `tests/test_readings.py`:

- **Void.** A bet whose game kicked off more than 24 hours from the kickoff on its entry row (postponed, moved or cancelled), or that still has no result 30 days after that kickoff, is void: listed by reason and not graded, as a sportsbook would. The review's example was a hurricane-postponed game graded at the old line. A result that lands later brings the bet back; a decision already recorded still stands.
- **Pending.** A bet with no result yet holds its decision open. The old test treated a game with no score a week after kickoff as never played, so a late score could flip a final decision.
- **Decided once, and written down** in `data/forward/decisions.csv`, under a fixed decision id, with the positions and a fingerprint of the ledger rows behind it (the entries, and Rule B's later quotes used as closes). Every later run rechecks the fingerprint and warns if those rows changed; the record still stands. Only a real run on the live ledger writes it. A preview with `--now`, a current-season schedule more than 2 days old, a copy of the ledger in `data/forward/`, a copy of the scorer in a worker's folder, or a scorer whose `data/forward` is a link to another folder records nothing and says why. A preview shows only the decisions made by its date. A run on a test ledger writes its own `decisions.csv` beside that ledger; a preview on one records only with `--test-record`, which exists for tests. One run at a time writes, under a lock; a damaged record stops recording, not the scores; a lost record is restored from its nightly copy on the ledgers branch, never decided again unless it is lost before that night's copy is made.
- **Dates:** Dec 12, 2026 and Feb 1, 2028, as registered. A game dated after Feb 1, 2028 never counts, whatever its season label.
- **A quote is a total with a valid under price.** Rule HT enters at the last such quote, so a later row with no usable price can't make a bet vanish. Pushes are left out of Rule HT's exact test and count as bets in ROI.
- **Rule B's primary close is the last quote logged after the entry row,** else the captured close, else none (the bet is counted and left out of the CLV). The entry is never its own close. This replaces amendment 2's promise that the captured close could never change the primary CLV or the decision. The scorer prints the book behind each entry and each close. This settles amendment 3's open owner decision.
- **"Not kept"** means no money goes on Rule B; it stays on paper for 2027 only by a dated amendment before 2027 Week 0.
- **Rule HT is reported by price source.** Two quoted numbers in amendment 3 are corrected (the gate's zero point is about −130, and at −115 it rejects an under from 1.5 points below the reference).
- **Listings.** A game postponed by more than a day that signals again on its new date is two listings, each with its own entry (and, for Rule B, its own later-quote close); the one that matches the actual kickoff is graded. Before, the second signal was dropped and the game was never a bet.
- **"Before kickoff"** is before the earlier of the kickoff on the row and the kickoff in the schedule, for every use, so an in-play quote can't become Rule HT's entry or Rule B's close.
- **20 closes.** A Rule B decision in which fewer than 20 signals have a primary close is inconclusive, and the scorer says why and how many have no close. Rule HT is graded on results, so the limit doesn't apply to it.
- **What it replaces.** The amendment ends with a list of every earlier sentence it changes, quoted. It tests nothing; the running variant count stays 271 (p < 0.000185).

**Amendment 5 (Sep 29)** follows up the money-gate study and the last review of amendment 4. No trigger, gate, price cap or stake changes. Tests in `tests/test_readings.py` and `tests/test_close_capture.py`:

- **Rule B's keep interval is the wider of two.** Closing-line moves of windy games on the same day move together, so the plain interval kept a rule with no edge about 5 to 6% of the time instead of 2.5%. Grouping by game day alone can come out narrower than the plain interval, even of zero width, and with independent signals it kept a no-edge rule slightly more often than the plain one, so the registered interval is the wider of the two: the plain half-width, with Student's t on one less than the number of signals (a little wider than the 1.96 the scorer used), and the grouped one, with the signals grouped by the Eastern date of their game's kickoff and Student's t on one less than the number of game days. With fewer than 2 game days there is no interval and the decision is inconclusive. The scorer prints the registered interval, says which of the two it is, and prints both; the record keeps the interval, both half-widths and the number of game days. In simulation ([`../strategy-research/keep_test_check.py`](../strategy-research/keep_test_check.py), 40,000 paths per case) it keeps a no-edge rule 2.8 to 3.0% of the time in the realistic case (the grouped interval alone 3.6 to 4.0%), up to 3.8% in the stress case, and 1.7 to 1.9% with independent signals. Rule HT is graded on results and doesn't change.
- **Close capture's feed-event rule is registered** (above).
- **Three record gaps, and a copy that never loses a line.** A recorded time with no time zone is a damaged record, not a crash; a damaged record still prints each decision in it that can be read, as recorded; and a decision missing from a record file that still exists is restored from the ledgers-branch copy, never decided again, by appending the copy's own line. The nightly copy (`../ops/sync_ledgers.sh`) now never publishes a `decisions.csv` that has lost or changed a line of the published copy (or is missing, empty, cut or has the wrong header): it keeps the published copy, says so in one line, and syncs everything else. So a decision that was ever published is never decided again; the one case left is a decision recorded and lost on the same day, before that night's copy. A copy that can't be read stops recording even when the file is there, and the decisions still readable in it are printed as recorded. Tests of the nightly copy: `../nfl-weather/tests/test_sync_ledgers.py`.

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
