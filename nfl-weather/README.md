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

**Close capture** (amendment 3). Every 15 minutes `ops/capture_closes.sh` runs `scripts/capture_close.py`.
When games kick off in 2–20 minutes, it makes one Odds API call and adds each logged book's total and prices
for every game in that kickoff slot to `data/forward/closes.csv`; the scorer uses Pinnacle's row. If some game
in the slot has no Pinnacle total, the slot is tried once more on the next run, for a second credit. A feed
event is one event in the odds feed: a game as the feed lists it, with its own event id. Since Sep 29 each game
takes at most one feed event: one with its two teams that starts within 6 hours of its scheduled kickoff,
preferring a feed event Pinnacle prices (as the board does), then the one nearest the kickoff. Before, it matched
on the teams alone, so when the feed listed the same teams twice with Pinnacle prices on both, it wrote both and
the scorer took whichever the feed gave last. A tie between two equally good feed events, or no feed event within
6 hours, leaves the game's close missing, and the log says why. Tests: `tests/test_close_capture.py`.
*Note, Sep 29 (amendment 7):* this rule is now registered, with one change. Two feed events equally near the
kickoff that carry the same Pinnacle quote (the same total and prices) are the same game listed twice, so the
first in the feed is taken; a tie between different quotes still leaves the close missing. A feed with no usable
event (no events at all, or events that no logged book prices) is recorded as a slot with no feed events (each
due game with its book columns blank) and counted as a try, and the log says which of the two it was; it used to
stop the script with an error before the try was counted.

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

- **Decisions follow the registered horizons.** Rule B and the model lean are decided after Week 18 of 2026 with 40 bets in the 2026 regular season, and otherwise once, after the 2027 regular season. A decision uses only the bets that kicked off by its horizon, so it can't change later. Before the horizon the scorer prints the numbers and no verdict.
  - *Note, Sep 29 (amendment 6):* "it can't change later" now rests on the written record, not on the horizon alone. A decision waits until each bet that kicked off by its horizon has a result or is void. The first final decision is written to `data/forward/decisions.csv` by a run on the live ledger, on the real clock, with a schedule refreshed in the last 2 days (the daily check-in's run is one). Every later run prints that record; if a corrected score would now change the numbers, the scorer shows both and the recorded decision stands. An inconclusive 2026 decision is decided once more after the 2027 regular season.
- **The best line is logged for every game the feed lists**, including the ones Pinnacle doesn't quote. A Pinnacle total with no under price no longer blocks the backup price.
- **Every run checks the pricing cohort** against its registered hash and stops if it differs.
- **A run that fails at any stage is recorded and notified**, not only one that fails while building the board. Keys are blanked from error text.
- **The one-time ledger rewrite keeps old rows character for character** and leaves a copy of the ledger as it stood.
- **A number that isn't a price is no price** (anything between −100 and +100), and quarter-point lines are priced as half a bet at each neighbour.

**A review of the scorer (Sep 29) found readings the text still left open.** Amendment 6 settles each one before any outcome exists; no trigger, gate, price cap, stake or metric changes. A final review before registration, the same day, added the last four items. Each has a test in `tests/test_readings.py`:

- **Void.** A bet whose game kicked off more than 24 hours from the kickoff on its entry row (postponed, moved or cancelled), or that still has no result 30 days after that kickoff, is void: listed by reason and not graded, as a sportsbook would. A result that lands later brings the bet back; a decision already recorded still stands.
- **Pending.** A bet with no result yet holds its decision open. The old test treated a game with no result a week after kickoff as not played, so a late result could flip a final decision.
- **Decided once, and written down** in `data/forward/decisions.csv`, under a fixed decision id, with the positions and a fingerprint of the ledger rows behind it. Every later run rechecks the fingerprint and warns if those rows changed; the record still stands. Only a real run on the live ledger writes it. A preview with `--now`, a schedule more than 2 days old, a copy of the ledger in `data/forward/`, a copy of the scorer in a worker's folder, or a scorer whose `data/forward` is a link to another folder records nothing and says why. A preview shows only the decisions made by its date. A run on a test ledger writes its own `decisions.csv` beside that ledger; a preview on one records only with `--test-record`, which exists for tests. A decision recorded after 2027 with none for 2026 is never followed by a 2026 one. One run at a time writes, under a lock; a damaged record stops recording, not the scores; a lost record is restored from its nightly copy on the ledgers branch, never decided again unless it is lost before that night's copy is made.
- **"After Week 18" is a date:** the season's last regular-season kickoff.
- **The model lean enters at its first snapshot 24 hours out that has a posted total.** The live ledger already had a lean with a blank total, which the old code would have graded as a loss.
- **After 2026.** A keep or a drop in 2026 is the decision. An inconclusive 2026 result is decided once more after the 2027 regular season, on both seasons pooled.
- **Ties with the close** are left out of the win rate against the close. Two quoted numbers in amendment 5 are corrected (the gate's zero point is about −135 on a half-point line, and at −115 it rejects an under from 1.5 points below the reference).
- **Listings.** A game postponed by more than a day that signals again on its new date is two listings, each with its own entry; the one that matches the actual kickoff is graded. Before, the second signal was dropped and the game was never a bet.
- **"Before kickoff"** is before the earlier of the kickoff on the row and the kickoff in the schedule, for every use.
- **20 closes.** A decision in which fewer than 20 bets have a primary close is inconclusive, and the scorer says why and how many bets have no close.
- **What it replaces.** The amendment ends with a list of every earlier sentence it changes, quoted. It tests nothing; the running variant count stays 271 (p < 0.000185).

**Amendment 7 (Sep 29)** follows up the money-gate study and the last review of amendment 6. No trigger, gate, price cap or stake changes. Tests in `tests/test_readings.py` and `tests/test_close_capture.py`:

- **The keep test's interval is the wider of two.** Closing-line moves of windy games on the same day move together, so the plain interval kept a rule with no edge about 8 to 10% of the time instead of 2.5%. Grouping by game day alone can come out narrower than the plain interval, even of zero width, so the registered interval is the wider of the two: the plain half-width, with Student's t on one less than the number of bets (a little wider than the 1.96 the scorer used), and the grouped one, with the bets grouped by the Eastern date of their game's kickoff and Student's t on one less than the number of game days. With fewer than 2 game days there is no interval and the decision is inconclusive. The scorer prints the registered interval, says which of the two it is, and prints both; the record keeps the interval, both half-widths and the number of game days. In simulation ([`../strategy-research/keep_test_check.py`](../strategy-research/keep_test_check.py), 40,000 paths per case) it keeps a no-edge rule 5.8 to 7.4% of the time in the realistic case (the grouped interval alone 6.4 to 8.1%), and the two looks together 6.5 to 8.4%; with independent signals 1.4%. That is better, not fixed: NFL seasons swing as a whole, and grouping by day can't correct that.
- **Close capture's feed-event rule is registered** (above).
- **Three record gaps, and a copy that never loses a line.** A recorded time with no time zone is a damaged record, not a crash; a damaged record still prints each decision in it that can be read, as recorded; and a decision missing from a record file that still exists is restored from the ledgers-branch copy, never decided again, by appending the copy's own line. The nightly copy (`../ops/sync_ledgers.sh`) now never publishes a `decisions.csv` that has lost or changed a line of the published copy (or is missing, empty, cut or has the wrong header): it keeps the published copy, says so in one line, and syncs everything else. The first copy is checked the same way, and a published copy that is itself damaged is named as the damaged one. So a decision that was ever published is never decided again. The one case left is a decision recorded since the last nightly copy that published the file and lost before the next one: normally the same day, but while the nightly copy holds the file back because a published line in it has changed, every decision recorded until that line is put back. A copy that can't be read stops recording even when the file is there, and the decisions still readable in it are printed as recorded. Tests of the nightly copy: `tests/test_sync_ledgers.py`.

## Forecast replay on NWS MOS, 2004–25 (issue #40, Sep 29)

The Rule B evidence (57.2% under vs the close in 682 observed-wind games since 1999, `STRATEGY.md`) uses the wind the game book recorded at kickoff. The live rule bets on a forecast 1–3 days out. [`scripts/mos_replay.py`](scripts/mos_replay.py) replays it on the National Weather Service's GFS MOS station forecasts as they were issued, archived with their run times at the Iowa Environmental Mesonet. It is the NFL half of the college football replay; the method, the no-lookahead timing and the download are described in [`../cfb-weather/README.md`](../cfb-weather/README.md#forecast-replay-on-nws-mos-back-to-2006-issue-40-sep-29), and the shared code is `nflweather/mos.py` (an exact copy of `cfbweather/mos.py`; a test checks).

**No NFL results yet.** The scripts are written and tested, but the NFL download runs after the college one, and the whole pull takes several hours at the rate the site allows. When it finishes, `scripts/mos_replay.py` writes the tables below. Nothing in this section changes Rule B.

*Update, later on Sep 29: the download finished, and the results are in the [next section](#forecast-replay-on-nws-mos-the-full-run-200425-issue-40-sep-29).*

What differs from the college version:

- **The wind is read at the kickoff instant**, as the live rule reads its forecast (interpolated between the 3-hourly MOS steps), not averaged over four hours.
- **"Observed" is the game book's stadium wind** (else calibrated ERA5), the scale Rule B's evidence and its 15 mph threshold use. MOS forecasts the airport's wind, so the bias table matters more here: if MOS runs higher than the game book, 15 mph on MOS fires more often than 15 mph did in the evidence.
- **Lead 3 is available for early kickoffs.** A run from three days before reaches 72 hours ahead, which covers a 1:00 PM Eastern Sunday kickoff but not a late-afternoon or night one.
- **Stations:** 30 of the 37 stadiums that hosted outdoor games in 2004–25 have a MOS station within 40 km (median 7.9 km; [`data/processed/mos_station_map.csv`](data/processed/mos_station_map.csv)). The seven without one are the international venues (Wembley, Tottenham, Twickenham, Frankfurt, Munich, Mexico City, São Paulo; 49 games). 4,251 eligible games remain.
- **Prices:** the nflverse closing total at an assumed −110 (the primary); nflverse's under price where it is −115 or better, the board's cap; and the SBR opener, 2007–21.
- **Variants:** 1, the same trigger as the live rule (MOS ≥ 15 mph at lead 1, 2 or 3). No threshold is tuned.

```bash
.venv/bin/python scripts/mos_fetch.py --map-only    # the stadium map
.venv/bin/python scripts/mos_fetch.py               # the download (cache-first; ../cfb-weather/scripts/mos_pull_all.sh runs both sports)
.venv/bin/python scripts/mos_replay.py              # tables: output/tables/mos_replay_seasons.csv, mos_bias.csv; log: output/mos_replay.log
```

## Forecast replay on NWS MOS, the full run: 2004–25 (issue #40, Sep 29)

Count at merge (Sep 29, 2026): 273; bar p < 0.000183. That includes 1 for the cut looked at after the results, described under "What it means": the hub counts it, because every look is counted.

**The headline changed after review: with the last 28 downloads fetched, the rule went 337–261–9 (56.4%) on 607 signals, p = 0.028; the first draft had 323–253–8 (56.1%) on 584, p = 0.041.** The 221 games that had no forecast (every Baltimore home game, and Washington's 2004–09 games) now have one. 23 of them are signals, and those went 14–8–1. The review had pointed out that these games leaned toward the under on observed wind (the 22 of them with 15+ mph went 17–4–1), so a rise was the likelier direction.

The replay described above, unchanged, on 22 seasons. Every game at a stadium with a MOS station now has a forecast.

**Short answer**

- **On the forecasts as they were issued, NFL Rule B went 337–261–9 (56.4%) on 607 signals.** That is out of 4,251 games over 22 seasons.
- **At an assumed −110 the ROI is +7.6%.** The 95% interval runs from 52.4% to 60.3% for the win rate, or −0.1% to +15.1% for the ROI.
- **It is consistent with the observed-wind evidence** the rule rests on (57.2% on 682 games since 1999).
- **It is only weakly distinguishable from break-even**: one-sided p = 0.028, and 0.021 with standard errors grouped by game day.
- **It is far from this project's bar** (p < 0.000183, 273 variants).
- **It is not an independent test.** 333 of the 607 signals are games the observed-wind evidence already counts. The 274 only the forecast flagged went 148–122–4 (54.8%, p = 0.23), which can't be told from break-even.
- **In the 15 seasons with a second source of lines (2007–21), the rule is indistinguishable from break-even**: 214–181–5 (54.2%, 400 signals, p = 0.25) at the nflverse close, and 214–181–2 (54.2%, 397, p = 0.25) at SBR's own close.
- **The declared eras** (descriptive, no variant):
  - 2004–14: 164–133–4 (55.2%, 301 signals, p = 0.18);
  - 2015–25: 173–128–5 (57.5%, 306, p = 0.043);
  - 2021–25: 91–59–3 (60.7%, 153, p = 0.025).
- **The forecast rule fires about 28 times a season** (19–39), about 24 of them on or after Oct 1.

| | **2004–25, all** | 2004–14 | 2015–25 | 2021–25 |
|---|---|---|---|---|
| Games with a forecast | **4,251** | 2,167 | 2,084 | 930 |
| Signals (forecast ≥ 15 mph at kickoff, 1–3 days out) | **607** | 301 | 306 | 153 |
| Under at the close (nflverse), −110 | **337–261–9 (56.4%)** | 164–133–4 (55.2%) | 173–128–5 (57.5%) | 91–59–3 (60.7%) |
| 95% interval for the win rate | **52.4–60.3%** | 49.5–60.8% | 51.8–62.9% | 52.7–68.1% |
| The same, grouped by game day | 52.5–60.2% | 50.2–60.2% | 51.7–63.3% | 52.4–68.9% |
| ROI at −110 | **+7.6%** (−0.1% to +15.1%) | +5.4% | +9.7% | +15.8% |
| One-sided p against 52.4% (grouped by game day) | **0.028** (0.021) | 0.18 (0.13) | 0.043 (0.043) | 0.025 (0.024) |
| At the SBR opener, 2007–21 | 227–163–7 (58.2%), 397 | 117–92–2 (56.0%), 211 | 110–71–5 (60.8%), 186 | 24–9–1 (72.7%), 34 |
| At the nflverse close, on those same games | 212–180–5 (54.1%) | 109–100–2 (52.2%) | 103–80–3 (56.3%) | 22–11–1 (66.7%) |
| At the SBR close, 2007–21 | 214–181–2 (54.2%), 397 | 110–100–1 (52.4%), 211 | 104–81–1 (56.2%), 186 | 23–11 (67.6%), 34 |
| *Observed* (game-book) wind ≥ 15 mph, same pool of games, at the close | 300–225–8 (57.1%), 533 | 169–127–5 (57.1%), 301 | 131–98–3 (57.2%), 232 | 62–37–2 (62.6%), 101 |
| …of which also forecast signals | 333 | 173 | 160 | 77 |

- **The observed-wind row is not the forecast signals graded on the observed wind.** It is every game, among the games with a forecast, whose game-book wind reached 15 mph: the observed-wind version of the rule on the same pool of games. 333 of the 607 forecast signals are in it. (The first draft called it "the same games on observed wind", which was wrong.)
- **At nflverse's own under price**, where it is −115 or better (the board's cap), the rule went 279–230–8 on 517 signals, +6.9% at the prices quoted.
- **By season**, from 10–18–1 (35.7%, 2010) to 18–7–2 (72.0%, 2023). 7 of the 22 seasons finished below break-even, which is normal at 28 signals a season. The per-season table is [`output/tables/mos_replay_seasons.csv`](output/tables/mos_replay_seasons.csv), and every number is in [`output/mos_replay.log`](output/mos_replay.log).

**Step 1: what the download returned.** The NFL asked the nearest MOS station for 487 station-seasons.
- 459 came back with forecasts. None was unreadable.
- **22 came back with runs but no wind**: every season of Baltimore Inner Harbor (KDMH), the station 1.1 km from the Ravens' stadium.
  - MOS doesn't forecast wind there, so IEM leaves the wind column out of the answer.
  - That missing column is what crashed the end of the download (`read_file` expected it). One request to IEM's JSON API confirmed it: every step of a KDMH run has a temperature and no wind.
  - The fix (both copies of `mos.py`, with tests) reads such an answer as a missing forecast. The download scripts now treat it as empty, so the next-nearest station is tried, as PR 61 specified.
- **6 came back with no runs**: College Park (KCGS), Washington's nearest station, has no runs before the 2010 season.
- **The next-nearest stations for those 28 station-seasons** are Baltimore–Washington International (KBWI) for 2004–25 and Andrews (KADW) for 2004–09. The crash came just before the download reached them. They were fetched later on Sep 29: 28 requests, one every 8 seconds, with the project's user agent. **All 28 came back with forecasts.**
- `scripts/mos_fetch.py --report` lists every station-season and what it returned ([`output/mos_cache_report.log`](output/mos_cache_report.log)).
- **The whole cache** (shared with college football) now has 2,637 files: 2,602 with forecasts, 13 with no runs (KCGS, KIGX), 22 with no wind (KDMH), none unreadable.
- **One oddity that costs nothing:** Denver's station (Broomfield, KBJC) has no wind value in 30.5% of the rows of its 2004 answer, but every 2004 Denver game still has a forecast at leads 1 and 2.

**Step 2: coverage.** 4,300 outdoor games in 2004–25 have a closing total and a score.

| Why a game has no forecast at any lead | Games |
|---|---|
| No MOS station within 40 km (the international games) | 49 |
| **With a forecast at leads 1 and 2** | **4,251** |

- **The station behind each forecast.**
  - 4,016 games use the nearest station.
  - 235 use the next-nearest: all 187 Baltimore home games use BWI (Inner Harbor has no wind), and 48 Washington games from 2004–09 use Andrews (College Park has no runs before 2010).
  - The first draft had 14 of those Washington games on Reagan National (the third-nearest), because Andrews hadn't been downloaded. They now use Andrews, as PR 61's nearest-first rule says. One of them is a signal either way: Kansas City at Washington, Oct 18, 2009, 19.6 mph at lead 1 on Reagan National and 17.3 mph on Andrews; the under won.
- **Leads.** Leads 1 and 2 have a forecast for all 4,251 games. Lead 3 covers 2,224. A run from three days out reaches 72 hours, which covers a 1 PM Eastern Sunday kickoff but not a later one (2,027 games).
- **Per season.** Every season has 176–213 games with a forecast; the only games without one are the international games (0–5 a season). See [`output/tables/mos_coverage.csv`](output/tables/mos_coverage.csv); each game without a forecast is in [`output/tables/mos_no_forecast.csv`](output/tables/mos_no_forecast.csv).

**Step 3: how good the forecast is.** MOS at the kickoff instant against the game book's wind at kickoff (calibrated ERA5 where the game book has none), on every game with both:

| | Lead 1 (4,251 games) | Lead 2 (4,251) | Lead 3 (2,224) |
|---|---|---|---|
| MOS minus game book, average | +0.86 mph | +0.92 mph | +0.99 mph |
| Typical miss (mean absolute error) | 2.88 mph | 2.98 mph | 3.05 mph |
| Correlation | 0.69 | 0.68 | 0.70 |
| Games where MOS reaches 15 mph | 10.9% | 10.9% | 12.6% |
| Games where the game book reaches 15 mph | 12.5% | 12.5% | 14.7% |
| Game-book wind reached as often as MOS reaches 15 | 15 mph | 15 mph | 15 mph |

- **The two measures differ.** MOS forecasts the airport; the game book records the stadium, in whole miles per hour. On average MOS runs about 0.9 mph higher.
- **But the game book's readings spread wider, so MOS reaches 15 mph slightly less often.** By frequency, 15 mph on MOS corresponds to 15 mph in the game book at each lead.
  - The rule fires if any of its three leads reaches 15. Taken together that is 14.3% of games, as often as the game book reaches 14 mph.
- **The gap has grown lately.** At lead 1 it ran from −0.03 mph (2010) to +2.03 mph (2025). 2024 and 2025 are the two largest (+1.82, +2.03); 2023 is +1.14.
  - In 2023–25 the game book reached 15 mph on only 7.1–10.4% of games, against 11.5–20.1% in 2004–08.
  - Whether that is the weather or a change in how the wind is recorded isn't known.
- **Details.** The season-by-season table is [`output/tables/mos_bias_by_season.csv`](output/tables/mos_bias_by_season.csv).
- **Against the live board's forecast** (Open-Meteo on the frozen calibration), on the 380 games of 2023–25 with both:
  - MOS runs about 1 mph higher.
  - MOS misses the game-book wind by more: 2.84 against 2.33 mph at lead 1.
  - MOS fired on 63 of those games (31–31–1), Open-Meteo on 42 (22–20), and 35 were both.

**Step 4: where the result sits** (descriptive; it uses the observed wind, which no one knows at bet time):

| Group | Games | Record |
|---|---|---|
| Forecast and game-book wind both reached 15 | 333 | 189–139–5 (57.6%) |
| Forecast only | 274 | 148–122–4 (54.8%) |
| Game book only (the forecast missed it) | 200 | 111–86–3 (56.3%) |

- **The first two groups don't differ** beyond chance (Fisher exact test, p = 0.51).
- **When each signal first appeared.** 281 of the 607 signals first appeared three days out, 244 two days out and 82 only the day before.

**What it means**

- **Consistent with the observed-wind history?** Yes. 56.4% on 607 forecast signals against 57.2% on 682 observed-wind games; the interval (52.4–60.3%) contains 57.2%.
- **Distinguishable from break-even?** Weakly, by ordinary standards.
  - One-sided p is 0.028, 0.021 grouped by game day (327 game days, 1.8 signals a day), and 0.034 if same-day results correlated at 0.1.
  - By this project's bar, no.
- **In the 15 seasons with a second source of lines, it is indistinguishable from break-even.** Across 2007–21 the rule went 214–181–5 (54.2%, 400 signals, p = 0.25) at the nflverse close, and 214–181–2 (54.2%, 397, p = 0.25) at SBR's own close. The two closes agree. It did better at the SBR opener (58.2%), which, as in college football, is posted before the forecast that fires.
- **A look taken after the results, not a test.** The first draft read the per-season table and wrote that the pooled result "owes most to 2004–06 and 2021–23" and that 2007–21 "are simply weaker". Both sentences were written after seeing the results. The worker who drafted them also computed one cut in scratch: the seasons outside 2007–21 (2004–06 and 2022–25) went 123–80–4 (60.6%, 207 signals, p = 0.011; it was 118–74–3 before the 28 downloads). Because that cut was chosen after looking, its p-value means little. The hub counts it as a variant, because the project counts every look it takes: the running count is 273 (bar p < 0.000183). Nothing in this write-up rests on it.
- **The NFL signal count** is about 28 a season (19–39), about 24 of them from Oct 1 on (15–31).
- **What it does not show.**
  - The price actually available 1–3 days early, or the board's expected-value gate.
  - The stadium's own wind at kickoff: MOS forecasts the airport.
  - Independence from the observed-wind evidence: 333 of the 607 signals are games that evidence counts. The 274 only the forecast flagged went 148–122–4 (54.8%, p = 0.23).
  - That it describes the board's own signals: on the 380 games of 2023–25 with both, MOS fired 63 times and Open-Meteo 42, with 35 in both.

**Variants.** 2 for the NFL: the replay, and the cut above that was looked at after the results (counted because every look is counted). With the college football replay already counted in main's 271, the total is **273**, bar p < 0.05 / 273 = 0.000183. The era cuts, the SBR opener and close grades, the opener comparison, the bias tables and the split above describe the one rule and add none. `scripts/mos_replay.py` prints this count (`VARIANTS_BEFORE = 271`).

**No lookahead, checked by hand.** [`scripts/mos_hand_check.py`](scripts/mos_hand_check.py) prints the run selection for 11 real games, with every run, publication time and interpolation ([`output/mos_hand_check.log`](output/mos_hand_check.log)):
- a 1 PM Sunday kickoff that lead 3 reaches, and a 4:25 PM one it doesn't;
- Sunday-night, Monday-night and Thursday-night games;
- Christmas 2004 and 2021, and New Year's Day 2017;
- the Sunday summer time ended in 2019;
- 13 kt = 14.96 mph (no signal);
- both next-nearest fallbacks: Washington 2009 on Andrews, because College Park has no runs, and Baltimore 2024 on BWI, because Inner Harbor has runs but no wind (its rows are kept in the fixture to show why it is skipped).

Every value was worked by hand, and `tests/test_mos.py` pins them using the MOS rows in `tests/fixtures/`.

```bash
.venv/bin/python scripts/mos_fetch.py --report      # step 1: what every station-season returned
.venv/bin/python scripts/mos_replay.py              # steps 2-5: output/mos_replay.log and output/tables/mos_*.csv
.venv/bin/python scripts/mos_hand_check.py          # the hand-checked games and their test fixture
```

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
