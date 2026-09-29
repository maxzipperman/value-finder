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
neither, the slot is tried once more on the next run, for a second credit. Since Sep 29 each game takes at most
one feed listing: one with its two teams that starts within 6 hours of its scheduled kickoff, preferring
Pinnacle, then DraftKings (as the board does), then the one nearest the kickoff. Before, it matched on the teams
alone, so a relisted event, or a rematch such as a conference title game in the same feed, added a second row,
and when both rows had a price the scorer took whichever the feed gave last. A tie between two equally good
listings, or no listing within 6 hours, leaves the game's close missing, and the log says why. Tests:
`tests/test_close_capture.py`.

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

*Update, later on Sep 29: the download finished, and the 2006–25 results are in the [next section](#forecast-replay-on-nws-mos-the-full-run-200625-issue-40-sep-29). This section is the 2023–25 method check, left as it was written.*

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

## Forecast replay on NWS MOS, the full run: 2006–25 (issue #40, Sep 29)

Count at merge (Sep 29, 2026): 273; bar p < 0.000183.

*Revised after review, Sep 29: no college football number changed. The bottom line is reworded to claim less, the observed-wind row is relabeled (it was never the same games as the signals), and the opener is now compared with the close on the same games.*

The same replay as the section above, unchanged, on all 20 seasons once the download finished. It asks one question: if you had bet Rule B on the forecasts that existed 1–2 days before each game (not on the wind measured afterwards), how would you have done?

**Short answer**

- **On the forecasts as they were issued, the rule went 715–555–14 (56.3%) on 1,284 signals over 20 seasons.** At an assumed −110 that is a return of +7.5% per bet (95% interval +2.2% to +12.6%).
- **That is the same rate as the observed-wind history** the rule was built on (56.6% on 990 games).
- **It beats break-even (52.4%) by ordinary standards**: one-sided p = 0.003. That is still 0.004 when games on the same day are treated as related (standard errors grouped by game day), and 0.013 if same-day results were as correlated as same-day line moves (about 0.1, from the paper-to-money study).
- **It does not clear this project's bar**, p < 0.000183, which splits 0.05 over 273 tested variants. Nor is it an independent test:
  - 602 of the 1,284 signals are games the observed-wind evidence already counts.
  - The 682 games only the forecast flagged went 365–311–6 (54.0%), p = 0.21. As independent evidence, that is weak.
- **It is not the forecast the live board reads.** The board reads Open-Meteo. On the 1,670 games of 2024–25 both cover, MOS fired 135 times and Open-Meteo 110, and only 65 games were flagged by both.
- **It holds across the eras declared before the run**: 57.1% in 2006–15 (586 signals), 55.7% in 2016–25 (698), 57.3% in 2021–25 (335).
- **Single seasons swing widely**, from 44.2% (2018, 78 signals) to 64.3% (2008, 28 signals). 5 of the 20 seasons finished below break-even.
- **The forecast rule fires about 64 times a season**: 67 in 2021–25, of which about 47 kick off on or after Oct 1.

**The full period beside the 2023–25 sample.** Every entry is the consensus closing total at an assumed −110. Win rates leave out pushes. "Grouped" means standard errors grouped by game day (the kickoff's Eastern date).

| | 2023–25 sample (above) | **2006–25, all** | 2006–15 | 2016–25 | 2021–25 |
|---|---|---|---|---|---|
| Games with a forecast | 2,483 | **12,501** | 5,176 | 7,325 | 4,024 |
| Signals (forecast ≥ 15 mph, 1–2 days out) | 200 | **1,284** | 586 | 698 | 335 |
| Under at the close | 112–86–2 (56.6%) | **715–555–14 (56.3%)** | 331–249–6 (57.1%) | 384–306–8 (55.7%) | 189–141–5 (57.3%) |
| 95% interval for the win rate | 49.6–63.3% | **53.6–59.0%** | 53.0–61.0% | 51.9–59.3% | 51.9–62.5% |
| The same, grouped | – | 53.4–59.2% | 52.5–61.6% | 51.9–59.4% | 52.0–62.5% |
| ROI at −110 | +8.0% | **+7.5%** (+2.2% to +12.6%) | +8.9% | +6.2% | +9.3% |
| One-sided p against 52.4% | 0.13 | **0.0028** | 0.013 | 0.046 | 0.042 |
| The same, grouped | – | 0.0039 | 0.022 | 0.043 | 0.033 |
| Under at the opener, where one exists | 113–83 (57.7%), 196 | 566–380–5 (59.8%), 951 | 188–116–2 (61.8%), 306 | 378–264–3 (58.9%), 645 | 197–129–2 (60.4%), 328 |
| Under at the close, on those same games | 109–85–2 (56.2%) | 534–406–11 (56.8%) | 177–126–3 (58.4%) | 357–280–8 (56.0%) | 186–137–5 (57.6%) |
| *Observed* wind ≥ 15 mph, same pool of games, at the close | 56–47–1 (54.4%), 104 | 469–364–11 (56.3%), 844 | 210–170–4 (55.3%), 384 | 259–194–7 (57.2%), 460 | 109–86–5 (55.9%), 200 |
| …of which also forecast signals | 76 | 602 | 287 | 315 | 131 |

The three cuts to the right were declared in the brief before the run. They are descriptions of the one replayed rule and add no variant; no other cut was made.

The observed-wind row is **not** the forecast signals graded on the observed wind. It is every game, among the games with a forecast, whose observed wind reached 15 mph: the observed-wind version of the rule on the same pool of games. The two sets overlap on 602 of the 1,284 forecast signals and 602 of the 844 observed-wind games. (The first draft of this section called it "the same games on observed wind", which was wrong.)

**By season** (at the close, −110; the opener column is blank where no opener exists):

| Season | Games with a forecast | Signals | Under at the close | 95% interval | ROI | One-sided p | At the opener | Observed ≥ 15, same pool |
|---|---|---|---|---|---|---|---|---|
| 2006 | 286 | 32 | 20–12 (62.5%) | 45–77% | +19.3% | 0.17 | – | 17–12 (58.6%) |
| 2007 | 463 | 37 | 22–14–1 (61.1%) | 45–75% | +16.7% | 0.19 | 1–0 | 16–16 (50.0%) |
| 2008 | 245 | 28 | 18–10 (64.3%) | 46–79% | +22.7% | 0.14 | – | 10–8 (55.6%) |
| 2009 | 517 | 47 | 25–22 (53.2%) | 39–67% | +1.5% | 0.51 | – | 12–12 (50.0%) |
| 2010 | 500 | 42 | 24–18 (57.1%) | 42–71% | +9.1% | 0.32 | 1–0 | 21–14 (60.0%) |
| 2011 | 596 | 96 | 48–46–2 (51.1%) | 41–61% | −2.5% | 0.64 | 1–0 | 33–25–2 (56.9%) |
| 2012 | 556 | 74 | 37–35–2 (51.4%) | 40–63% | −1.9% | 0.61 | 42–31 (57.5%) | 21–20–1 (51.2%) |
| 2013 | 651 | 64 | 34–29–1 (54.0%) | 42–66% | +3.0% | 0.45 | 33–30–1 (52.4%) | 22–18 (55.0%) |
| 2014 | 669 | 78 | 48–30 (61.5%) | 50–72% | +17.5% | 0.066 | 49–29 (62.8%) | 27–24–1 (52.9%) |
| 2015 | 693 | 88 | 55–33 (62.5%) | 52–72% | +19.3% | 0.036 | 61–26–1 (70.1%) | 31–21 (59.6%) |
| 2016 | 682 | 77 | 46–31 (59.7%) | 49–70% | +14.0% | 0.12 | 48–29 (62.3%) | 34–25–1 (57.6%) |
| 2017 | 697 | 82 | 43–38–1 (53.1%) | 42–64% | +1.3% | 0.49 | 46–36 (56.1%) | 34–26 (56.7%) |
| 2018 | 717 | 78 | 34–43–1 (44.2%) | 34–55% | −15.7% | 0.94 | 35–42–1 (45.5%) | 31–23 (57.4%) |
| 2019 | 718 | 80 | 48–31–1 (60.8%) | 50–71% | +16.0% | 0.084 | 52–28 (65.0%) | 33–17–1 (66.0%) |
| 2020 | 487 | 46 | 24–22 (52.2%) | 38–66% | −0.4% | 0.57 | – | 18–17 (51.4%) |
| 2021 | 759 | 62 | 33–26–3 (55.9%) | 43–68% | +6.8% | 0.34 | 35–25–1 (58.3%) | 22–18–3 (55.0%) |
| 2022 | 782 | 73 | 44–29 (60.3%) | 49–71% | +15.1% | 0.11 | 49–21–1 (70.0%) | 31–21–1 (59.6%) |
| 2023 | 813 | 65 | 39–26 (60.0%) | 48–71% | +14.5% | 0.13 | 36–26 (58.1%) | 17–15 (53.1%) |
| 2024 | 815 | 69 | 32–35–2 (47.8%) | 36–60% | −8.8% | 0.81 | 35–33 (51.5%) | 16–20–1 (44.4%) |
| 2025 | 855 | 66 | 41–25 (62.1%) | 50–73% | +18.6% | 0.071 | 42–24 (63.6%) | 23–12 (65.7%) |
| **All** | **12,501** | **1,284** | **715–555–14 (56.3%)** | **53.6–59.0%** | **+7.5%** | **0.0028** | 566–380–5 (59.8%) | 469–364–11 (56.3%) |

**Step 1: what the download returned.** College football asked the nearest MOS station for 2,119 station-seasons.
- 2,112 came back with forecasts. None was unreadable.
- 7 came back empty, with the header and no runs:
  - College Park (KCGS), 2006–09, Maryland's 16 games. It has runs from the 2010 season on.
  - Chapel Hill (KIGX), 2023–25, 39 UNC and Duke games. It has runs through the 2022 season and none after.
- All 7 were asked again at the next-nearest station (Reagan National, KDCA; Raleigh-Durham, KRDU), and all 7 came back with forecasts. The listing is in [`output/mos_cache_report.log`](output/mos_cache_report.log) (`scripts/mos_fetch.py --report`).

**The crash at the end of the download** was an NFL problem, but the code that crashed is shared, so it is fixed in both copies of `mos.py`.
- **The cause.** IEM leaves out any column that is empty in the whole answer. Baltimore Inner Harbor (KDMH), the NFL's station for the Ravens' stadium, has every MOS variable except wind in all 22 of its seasons. So its answers have no wind column, and the reader expected one.
  - One request to IEM's JSON API confirmed it: all 21 steps of KDMH's 18Z run on Oct 12, 2024 have a temperature, and none has a wind speed or direction.
- **The fix.** Such an answer now reads as a missing forecast instead of crashing. The download scripts treat it as empty, so the next-nearest station is tried, as PR 61 specified. For the NFL that meant 28 more requests (Baltimore–Washington International for Baltimore, Andrews for Washington 2004–09), fetched later on Sep 29 at one request every 8 seconds; all 28 came back with forecasts.
- **Tests** in [`tests/test_mos.py`](tests/test_mos.py) cover answers with no runs, with no wind column, with a missing value, a zero-byte file and an HTML error page.
- **Across the whole cache** (2,637 files, shared with the NFL): 2,602 have forecasts, 13 have no runs (KCGS, KIGX) and 22 have runs but no wind (KDMH, NFL only). None is unreadable.
- **No college game used KDMH, BWI or Andrews, so none of this changes a college number.** Rerun on the full cache with the fixed code, the 2023–25 results are identical: the per-game file and the bias table match PR 61's byte for byte, and every number in the season table is the same. The rerun's log and season table gain the new sections and columns, so they are not byte-identical; PR 61's 2023–25 files are left as committed.

**Step 2: coverage.** 12,823 games are eligible in 2006–25: FBS-involved, outdoor, with venue coordinates, a known kickoff time, a closing total and a score.
- **The venue-coordinates requirement leaves out 1,284 more FBS games that have a closing total and a score** (by coincidence the same number as the signals). Coordinates come only from the venue each team lists as its home today, so what is left out is:
  - neutral-site games (399, such as Texas–Oklahoma in Dallas every year) and postseason games (61);
  - stadiums a team has since left (Northwestern's old Ryan Field, San Diego State's Qualcomm Stadium, UNLV's Sam Boyd Stadium and Baylor's Floyd Casey Stadium, among others);
  - 209 games with no venue at all.
  - Whether they were played outdoors isn't known either; some were in domes.
  - The filter doesn't depend on the weather or the result, so it shouldn't bias the record. But the replay says nothing about these games, about 64 a season.
- **322 have no MOS station within 40 km**: Ole Miss, Ohio and Louisiana Tech, 10 to 21 games a season. They are listed in [`output/tables/mos_no_forecast.csv`](output/tables/mos_no_forecast.csv).
- **Every one of the other 12,501 games has a forecast at lead 1 and at lead 2, in every season.** No game lacks a run.
- **The replay read the 18Z run for 12,491 games at lead 1 and 12,469 at lead 2.** The rest took the same day's 12Z run, because the 18Z run is missing from the archive (10 and 32 games).
- **Lead 3 covers 17 games.** A run from three days out reaches 72 hours ahead, which ends before the kickoff window of any game that starts later than about 11 AM Eastern (12,484 games).

Per season and lead, with the reason for every missing forecast: [`output/tables/mos_coverage.csv`](output/tables/mos_coverage.csv).

| Season | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Eligible games | 296 | 476 | 255 | 530 | 515 | 612 | 572 | 670 | 685 | 711 | 699 | 715 | 734 | 736 | 498 | 778 | 800 | 832 | 833 | 876 |
| Forecast at leads 1 and 2 | 286 | 463 | 245 | 517 | 500 | 596 | 556 | 651 | 669 | 693 | 682 | 697 | 717 | 718 | 487 | 759 | 782 | 813 | 815 | 855 |
| Forecast at lead 3 | 0 | 1 | 1 | 0 | 0 | 0 | 2 | 1 | 1 | 1 | 1 | 2 | 1 | 1 | 0 | 3 | 1 | 1 | 0 | 0 |
| No station within 40 km | 10 | 13 | 10 | 13 | 15 | 16 | 16 | 19 | 16 | 18 | 17 | 18 | 17 | 18 | 11 | 19 | 18 | 19 | 18 | 21 |

**Step 3: how good the forecast is.** MOS is compared with the wind the airport recorded over the kickoff window (the observed wind every backtest used), on 12,388 games with both.

| | Lead 1 | Lead 2 |
|---|---|---|
| MOS minus observed, average | +0.80 mph | +0.87 mph |
| Typical miss (mean absolute error) | 2.33 mph | 2.47 mph |
| Correlation with the observed wind | 0.70 | 0.68 |
| Same airport as the observation (10,223 games): average, miss, correlation | +0.74, 2.14, 0.75 | +0.83, 2.31, 0.73 |
| Different airport (2,165 games) | +1.09, 3.20, 0.49 | +1.07, 3.24, 0.47 |
| Games where MOS reaches 15 mph | 8.48% | 8.75% |
| Games where the observed wind reaches 15 mph | 6.81% | 6.81% |
| Observed wind reached as often as MOS reaches 15 | **14.2 mph** | **14.1 mph** |

- **MOS runs slightly windier than the airport later records, in every season.** At lead 1 the gap ranges from +0.24 mph (2014) to +1.27 mph (2007), and 2023–25 is at the high end (+1.03 to +1.08).
- **By frequency, 15 mph on MOS at lead 1 corresponds to about 14.2 mph observed.**
  - The rule looks at two leads and fires if either reaches 15. Taken together it fires on 10.3% of games, as often as the observed wind reaches **13.5 mph**.
  - So the forecast rule is effectively a somewhat lower bar than "15 mph observed", which is why it fires more often.
  - The match varies by season. At lead 1 it runs from 13.3 mph (2023) to 15.3 mph (2006).
  - Games forecast at 14–16 mph at lead 1 averaged 13.3 mph observed (568 games).
- The season-by-season table is [`output/tables/mos_bias_by_season.csv`](output/tables/mos_bias_by_season.csv).

**Step 4: the replay, and where the result sits.** The replay is exactly the one PR 61 froze before the full data existed. It fires when the forecast is 15 mph or more at lead 1, 2 or 3, and enters at the consensus close at −110. The tables are above.

- **The opener.** It comes from cfbfastR's consensus opener, else the median opener across the CFBD books.
  - The CFBD multi-book lines (`data/processed/cfbd_lines.parquet`) have totals from 2014 but openers only from 2021.
  - cfbfastR has openers for 2012–19 and 2021–25.
  - So 951 of the 1,284 signals have an opener, and 2006–11 and 2020 have almost none.
  - The opener result (59.8%) flatters the rule. The opener is posted before the forecast that fires, and on these games the total fell 1.34 points on average between the opener and the close.
  - Like for like, on the same 951 games, the close went 534–406–11 (56.8%). So the opener adds about 3 points of win rate: 61.8% against 58.4% in 2006–15 (306 games), and 58.9% against 56.0% in 2016–25 (645).
- **Where the wins fell** (descriptive; it uses the observed wind, which no one knows at bet time):

  | Group | Games | Record |
  |---|---|---|
  | Forecast and observed wind both reached 15 | 602 | 350–244–8 (58.9%) |
  | Forecast only (the wind didn't arrive) | 682 | 365–311–6 (54.0%) |
  | Observed only (the forecast missed it) | 242 | 119–120–3 (49.8%) |

  The gap between 58.9% and 54.0% is not significant (Fisher exact test, p = 0.079).
- **How the signals fired.** Lead 1 alone fires on 1,059 games. Lead 2 adds 225 that lead 1 didn't flag. Lead 3 adds none.
- **Details.** The full log is [`output/mos_replay.log`](output/mos_replay.log), with the checks in [`output/mos_replay_checks.log`](output/mos_replay_checks.log).
- **Data notes.** Found in review; the replay uses the data as it stands, and no number above was changed for them.
  - **One kickoff time looks wrong.** Air Force at Army, Nov 3, 2018 (game 401013373), is listed at 12:00 UTC, which is 8 AM Eastern; it was probably a noon kickoff. It is the only game in the replay listed before 11 AM Eastern. At the listed time MOS forecast 12.7 mph (no signal). At noon Eastern it would have forecast 26.5 mph and fired, and the under won (31 points against a close of 41.5). Correcting it would make the record 716–555–14; it is left as listed, because the rule was fixed before the data was looked at.
  - **69 of the 1,284 signals are graded against a consensus close that no book offered**, such as 43.75 (the median of the books' lines). None of the 69 finished within half a point of that number, so no result would change at a book's own line.

**Step 5: stability over time** (declared before the run). The table's three right-hand columns are the answer.
- **Neither half of the period is far from the pooled 56.3%.**
  - The first half is 57.1% (586 signals).
  - The second half is the weaker one, at 55.7% (698).
  - The last five seasons are 57.3% (335).
- **The early seasons are small**: 28 to 47 signals a season before 2011, when fewer games had totals.

**What it means for this season**

- **Is the forecast record consistent with the observed-wind history?** Yes. 56.3% on 1,284 forecast signals, against 56.6% on 990 observed-wind games. The forecast's 95% interval (53.6–59.0%) contains 56.6%.
- **Is it distinguishable from break-even?** By ordinary standards, yes.
  - One-sided p is 0.003 (1,270 decided bets), and 0.004 grouped by game day (364 game days, 3.5 signals a day).
  - The tightest caution is the paper-to-money study's same-day correlation of about 0.1 in line moves. If results correlated that much, the interval would widen to 52.9–59.7% and p would be 0.013.
  - The outcomes themselves show less clustering than that: grouping by day widens the interval only slightly.
  - By this project's bar, no. After 273 variants the bar is p < 0.000183.
- **How many signals a season?**
  - 64 a season in 2006–25 (range 28–96), and 67 in 2021–25.
  - From Oct 1 on, the part of a season still ahead on Oct 1, it is 49 (range 26–86), and 47 in 2021–25.
  - The money-gate study assumed 25 to 55 a season. The rest of a season from Oct 1 falls inside that range; a full season is above it.
  - The live board reads Open-Meteo, not MOS. On the same 2024–25 games Open-Meteo fired 110 times against MOS's 135. So the board is likely to produce fewer signals than this replay: roughly 40 from Oct 1 on, if that ratio holds.
- **What one season looks like, if the rule as bet really wins about 56%.** This replay does not establish that for the board's own forecast and prices (see below), so this is a conditional, not a forecast: at a true 56%, a season of 50 bets still finishes below break-even about 1 time in 3 (32% at 56.3%, binomial). In this replay 5 of 20 seasons did. A losing October and November would not by itself mean the edge is gone, and a winning one would not prove it.
- **What the evidence does not show.**
  - **That it is an independent test.** Almost half of the signals (602 of 1,284) are games the observed-wind evidence already counts, and 2023–25 had already been seen. The part that is new, the 682 games only the forecast flagged, went 365–311–6 (54.0%, p = 0.21): positive, not significant. As independent evidence, that is weak.
  - **That it describes the board's own signals.** The live board reads Open-Meteo, not MOS. On the 1,670 games of 2024–25 that both replays cover, MOS fired 135 times (73–60–2, 54.9%) and Open-Meteo 110 times (61–46–3, 57.0%), and only 65 games were flagged by both. The two forecasts mostly pick different games, so 20 seasons of MOS are indirect evidence for the signals the board will send. There is no Open-Meteo archive before 2024 to check them directly.
  - **The price you would get.** Every entry is the consensus close at an assumed −110. The rule bets 1–3 days early, at one book's price, with the board's −115 cap and its expected-value gate, none of which is applied here. On the 951 signals with an opener, the real entry sits between the opener (59.8%, which flatters it) and the close on those same games (56.8%).
  - **Lead 3.** MOS reaches lead 3 for 17 of 12,501 games; the live rule's forecast does reach it. In the Open-Meteo replay 19 of 110 signals fired only at lead 3, and went 9–10.
  - **Stadium wind.** Both the forecast and the observation are for the nearest airport.
  - **That the market hasn't adapted.** The last five seasons (57.3%) show no fade, but five seasons can't rule one out.
- **Bottom line.** The forecast version of Rule B has now been replayed on 20 seasons, not 3. On NWS MOS forecasts graded at the consensus close, it wins at the same rate as the observed-wind history, about 56%. The games it adds to that history went 54.0% (p = 0.21), so it is weak independent evidence. It is also not a record of the rule as the board bets it: a different forecast (Open-Meteo, which flagged mostly different games in 2024–25), one book's price 1–3 days early, a −115 cap and an expected-value gate. It supports the rule; it does not prove it. It does not settle whether to bet real money this season; the paper-to-money gate and the forward test still decide that.

**Variants.** 1 for college football, already counted in main's 271 when PR 61 merged. The NFL replay adds 1, and one NFL cut looked at after its results (described in `nfl-weather/README.md`) adds 1, because every look is counted: **273**, bar p < 0.05 / 273 = 0.000183. The era cuts, the bias tables, the coverage counts, the opener comparison and the both/forecast-only split are descriptions of the one rule and add none. `scripts/mos_replay.py` prints this count (`VARIANTS_BEFORE = 271`). No college number is near the bar.

**No lookahead, checked by hand.** [`scripts/mos_hand_check.py`](scripts/mos_hand_check.py) prints the run selection for 12 real games that cover the edge cases:
- a noon kickoff, and an 11:59 PM Eastern kickoff that is the next day in UTC;
- a Thursday game, and 11 AM kickoffs that lead 3 reaches;
- 13 kt = 14.96 mph, which does not fire;
- both next-nearest stations;
- Thanksgiving 2020, whose 18Z run is missing, so lead 1 takes the 12Z run;
- the January title game, and the weekend summer time ends.

For each game, each lead and each hour the log ([`output/mos_hand_check.log`](output/mos_hand_check.log)) shows:
- the runs cached for each day from three days before through game day;
- the run each lead takes, and when it was published against that day's last alert run;
- the MOS steps and the interpolation.

Every value was worked by hand from the log, and `tests/test_mos.py` pins them, using the MOS rows saved in `tests/fixtures/`. A deliberately introduced one-day lookahead fails all 12.

**Run it** (from `cfb-weather`, with `data/raw/mos` linked as above):

```bash
.venv/bin/python scripts/mos_fetch.py --report      # step 1: what every station-season returned
.venv/bin/python scripts/mos_replay.py              # steps 2-5: output/mos_replay.log and output/tables/mos_*.csv
.venv/bin/python scripts/mos_replay_checks.py       # the descriptive checks
.venv/bin/python scripts/mos_hand_check.py          # the hand-checked games and their test fixture
```

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
