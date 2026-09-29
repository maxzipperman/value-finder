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
in the slot has no Pinnacle total, the slot is tried once more on the next run, for a second credit. Since
Sep 29 each game takes at most one feed listing: one with its two teams that starts within 6 hours of its
scheduled kickoff, preferring a listing Pinnacle prices (as the board does), then the one nearest the kickoff.
Before, it matched on the teams alone, so when the feed listed the same teams twice with Pinnacle prices on
both, it wrote both and the scorer took whichever the feed gave last. A tie between two equally good listings,
or no listing within 6 hours, leaves the game's close missing, and the log says why. Tests:
`tests/test_close_capture.py`.

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

Count at merge (Sep 29, 2026): 272; bar p < 0.000184.

The replay described above, unchanged, on 22 seasons. **Provisional: 221 games still lack a forecast.** Those are all 187 Baltimore home games and 34 Washington games from 2004–09. Their next-nearest station was never downloaded (Step 1 says why). 28 more requests would fetch it. The result below may move a little when they are added.

**Short answer**

- **On the forecasts as they were issued, NFL Rule B went 323–253–8 (56.1%) on 584 signals.** That is 4,030 games over 22 seasons.
- **At an assumed −110 the ROI is +7.1%.** The 95% interval runs from 52.0% to 60.1% for the win rate, or −0.7% to +14.7% for the ROI.
- **It is consistent with the observed-wind evidence** the rule rests on (57.2% on 682 games since 1999).
- **It is only weakly distinguishable from break-even**: one-sided p = 0.041, and 0.034 with standard errors grouped by game day.
- **It is far from this project's bar** (p < 0.000184, 272 variants).
- **The declared eras** (descriptive, no variant):
  - 2004–14: 158–129–4 (55.1%, 291 signals, p = 0.20);
  - 2015–25: 165–124–4 (57.1%, 293, p = 0.061);
  - 2021–25: 86–56–2 (60.6%, 144, p = 0.030).
- **Where SBR lines exist (2007–21, 386 signals) the rule is weaker**:
  - 217–162–7 (57.3%) at the SBR opener;
  - 205–179–2 (53.4%) at the SBR close;
  - 203–178–5 (53.3%) at the nflverse close on the same games.
  - The two closes agree, so those seasons are simply weaker. The pooled 56.1% owes most to 2004–06 and 2021–23.
- **The forecast rule fires about 27 times a season** (19–37), about 23 of them on or after Oct 1.

| | **2004–25, all** | 2004–14 | 2015–25 | 2021–25 |
|---|---|---|---|---|
| Games with a forecast | **4,030** | 2,042 | 1,988 | 884 |
| Signals (forecast ≥ 15 mph at kickoff, 1–3 days out) | **584** | 291 | 293 | 144 |
| Under at the close (nflverse), −110 | **323–253–8 (56.1%)** | 158–129–4 (55.1%) | 165–124–4 (57.1%) | 86–56–2 (60.6%) |
| 95% interval for the win rate | **52.0–60.1%** | 49.3–60.7% | 51.3–62.7% | 52.3–68.2% |
| The same, grouped by game day | 52.1–60.0% | 49.8–60.3% | 51.2–63.0% | 52.0–69.1% |
| ROI at −110 | **+7.1%** (−0.7% to +14.7%) | +5.1% | +9.0% | +15.6% |
| One-sided p against 52.4% (grouped by game day) | **0.041** (0.034) | 0.20 (0.16) | 0.061 (0.060) | 0.030 (0.031) |
| At the SBR opener, 2007–21 | 217–162–7 (57.3%), 386 | 111–92–2 (54.7%), 205 | 106–70–5 (60.2%), 181 | 23–9–1 (71.9%), 33 |
| At the SBR close, 2007–21 | 205–179–2 (53.4%), 386 | 105–99–1 (51.5%), 205 | 100–80–1 (55.6%), 181 | 22–11 (66.7%), 33 |
| The same games on *observed* (game-book) wind | 283–221–7 (56.2%), 511 | 159–126–5 (55.8%), 290 | 124–95–2 (56.6%), 221 | 58–34–1 (63.0%), 93 |

- **At nflverse's own under price**, where it is −115 or better (the board's cap), the rule went 266–225–7 on 498 signals, +5.6% at the prices quoted.
- **By season**, from 10–18–1 (35.7%, 2010) to 18–6–1 (75.0%, 2023). 8 of the 22 seasons finished below break-even, which is normal at 27 signals a season. The per-season table is [`output/tables/mos_replay_seasons.csv`](output/tables/mos_replay_seasons.csv), and every number is in [`output/mos_replay.log`](output/mos_replay.log).

**Step 1: what the download returned.** The NFL asked the nearest MOS station for 487 station-seasons.
- 459 came back with forecasts. None was unreadable.
- **22 came back with runs but no wind**: every season of Baltimore Inner Harbor (KDMH), the station 1.1 km from the Ravens' stadium.
  - MOS doesn't forecast wind there, so IEM leaves the wind column out of the answer.
  - That missing column is what crashed the end of the download (`read_file` expected it). One request to IEM's JSON API confirmed it: every step of a KDMH run has a temperature and no wind.
  - The fix (both copies of `mos.py`, with tests) reads such an answer as a missing forecast. The download scripts now treat it as empty, so the next-nearest station is tried, as PR 61 specified.
- **6 came back with no runs**: College Park (KCGS), Washington's nearest station, has no runs before the 2010 season.
- **The next-nearest stations for those 28 station-seasons were never asked for**, because the crash came just before that step: Baltimore-Washington International (KBWI) for 2004–25 and Andrews (KADW) for 2004–09.
  - That is 28 requests, about four minutes at the site's pace, and more than the handful of re-fetches this run was allowed. So those games are counted as missing, and listed.
  - `scripts/mos_fetch.py --report` lists every station-season and what it returned ([`output/mos_cache_report.log`](output/mos_cache_report.log)).

**Step 2: coverage.** 4,300 outdoor games in 2004–25 have a closing total and a score.

| Why a game has no forecast at any lead | Games |
|---|---|
| No MOS station within 40 km (the international games) | 49 |
| Baltimore: KDMH has no wind; KBWI and KMTN not downloaded | 187 |
| Washington 2004–09: KCGS has no runs; KADW and KDCA not downloaded for those dates | 34 |
| **With a forecast** | **4,030** |

- **The station behind each forecast.**
  - 4,016 of the 4,030 games use the nearest station.
  - 14 Washington games from 2006–09 use Reagan National (KDCA, 15.7 km, the third-nearest). College Park had no runs, Andrews wasn't downloaded, and Reagan National's runs happened to be on disk from the college football download. One of the 14 is a signal (Kansas City at Washington, Oct 18, 2009; the under won).
  - Once Andrews is fetched, those 14 games move to it, as PR 61's nearest-first rule says.
- **Leads.** Lead 1 has a forecast for 4,028 games and lead 2 for 4,030.
  - Lead 1 is missing for 2 Washington games whose borrowed college download window ends a day early.
  - Lead 3 covers 2,080 games. A run from three days out reaches 72 hours, which covers a 1 PM Eastern Sunday kickoff but not a later one (1,950 games).
- **Per season.** Every season has 168–197 games with a forecast, and 8–16 without, other than the international games. See [`output/tables/mos_coverage.csv`](output/tables/mos_coverage.csv); each game without a forecast is in [`output/tables/mos_no_forecast.csv`](output/tables/mos_no_forecast.csv).

**Step 3: how good the forecast is.** MOS at the kickoff instant against the game book's wind at kickoff (calibrated ERA5 where the game book has none), on every game with both:

| | Lead 1 (4,028 games) | Lead 2 (4,030) | Lead 3 (2,080) |
|---|---|---|---|
| MOS minus game book, average | +0.87 mph | +0.93 mph | +0.97 mph |
| Typical miss (mean absolute error) | 2.89 mph | 2.99 mph | 3.08 mph |
| Correlation | 0.69 | 0.68 | 0.70 |
| Games where MOS reaches 15 mph | 11.1% | 11.0% | 12.9% |
| Games where the game book reaches 15 mph | 12.7% | 12.7% | 15.3% |
| Game-book wind reached as often as MOS reaches 15 | 15 mph | 15 mph | 15 mph |

- **The two measures differ.** MOS forecasts the airport; the game book records the stadium, in whole miles per hour. On average MOS runs about 0.9 mph higher.
- **But the game book's readings spread wider, so MOS reaches 15 mph slightly less often.** By frequency, 15 mph on MOS corresponds to 15 mph in the game book at each lead.
  - The rule fires if any of its three leads reaches 15. Taken together that is 14.5% of games, as often as the game book reaches 14 mph.
- **The gap has grown lately.** At lead 1 it ran from −0.06 mph (2010) to +1.98 mph (2025), and 2023–25 are the three largest (+1.09, +1.82, +1.98).
  - In 2023–25 the game book reached 15 mph on only 5.8–10.3% of games, against 12–20% in 2004–08.
  - Whether that is the weather or a change in how the wind is recorded isn't known.
- **Details.** The season-by-season table is [`output/tables/mos_bias_by_season.csv`](output/tables/mos_bias_by_season.csv).
- **Against the live board's forecast** (Open-Meteo on the frozen calibration), on the 360 games of 2023–25 with both:
  - MOS runs about 1 mph higher.
  - MOS misses the game-book wind by more: 2.84 against 2.34 mph at lead 1.
  - MOS fired on 59 of those games (30–29), Open-Meteo on 41 (21–20), and 34 were both.

**Step 4: where the result sits** (descriptive; it uses the observed wind, which no one knows at bet time):

| Group | Games | Record |
|---|---|---|
| Forecast and game-book wind both reached 15 | 319 | 180–135–4 (57.1%) |
| Forecast only | 265 | 143–118–4 (54.8%) |
| Game book only (the forecast missed it) | 192 | 103–86–3 (54.5%) |

- **The first two groups don't differ** beyond chance (Fisher exact test, p = 0.61).
- **When each signal first appeared.** 269 of the 584 signals first appeared three days out, 235 two days out and 80 only the day before.

**What it means**

- **Consistent with the observed-wind history?** Yes. 56.1% on 584 forecast signals against 57.2% on 682 observed-wind games; the interval (52.0–60.1%) contains 57.2%.
- **Distinguishable from break-even?** Barely, by ordinary standards.
  - One-sided p is 0.041, 0.034 grouped by game day (321 game days, 1.8 signals a day), and 0.048 if same-day results correlated at 0.1.
  - By this project's bar, no.
  - The seasons where a second source of lines exists (2007–21) are close to break-even at the close.
- **The NFL signal count** is about 27 a season, about 23 of them from Oct 1 on.
- **What it does not show.**
  - The 221 games still missing: 187 Baltimore home games and 34 Washington games.
  - The price actually available 1–3 days early.
  - The stadium's own wind at kickoff: MOS forecasts the airport.
  - Independence from the observed-wind evidence: 319 of the 584 signals are games that evidence counts.

**Variants.** 1 for the NFL. With the college football replay already counted in main's 271, the total is **272**, bar p < 0.000184. The era cuts, the SBR opener and close grades, the bias tables and the split above describe the one rule and add none. `scripts/mos_replay.py` prints this count (`VARIANTS_BEFORE = 270`).

**No lookahead, checked by hand.** [`scripts/mos_hand_check.py`](scripts/mos_hand_check.py) prints the run selection for 11 real games, with every run, publication time and interpolation ([`output/mos_hand_check.log`](output/mos_hand_check.log)):
- a 1 PM Sunday kickoff that lead 3 reaches, and a 4:25 PM one it doesn't;
- Sunday-night, Monday-night and Thursday-night games;
- Christmas 2004 and 2021, and New Year's Day 2017;
- the Sunday summer time ended in 2019;
- 13 kt = 14.96 mph (no signal);
- the Washington game on the third-nearest station;
- a Baltimore game with runs but no wind.

Every value was worked by hand, and `tests/test_mos.py` pins them using the MOS rows in `tests/fixtures/`.

**What's left.**
1. Fetch the 28 next-nearest station-seasons. From `nfl-weather`, with `data/raw/mos` linked, run `.venv/bin/python scripts/mos_fetch.py`. It is cache-first, asks only for the 28 missing windows, and takes about four minutes.
2. Rerun `scripts/mos_replay.py` and `scripts/mos_hand_check.py`.
3. Update the two hand-checked games the new stations change in `tests/test_mos.py`: the Baltimore game will then have a forecast, and the Washington 2009 game moves to Andrews.
4. Replace the numbers above.

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
