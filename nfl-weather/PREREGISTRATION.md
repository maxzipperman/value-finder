# Pre-registered forward test: weather unders, 2026 season

Locked 2026-09-27, before any Week 4+ results existed. Modeled on the
decision-criteria discipline in `sharp-markets`: write the contract first so a
mixed result can't be talked into a win.

## The rule (no changes mid-season)

* **Signal.** `P(under)` from the weather-only logistic model
  (`nflweather.market.fit_under_model`, bins: wind 10–14 / 15–19 / 20+ mph,
  air temp ≤32 / 33–45 / 80+ °F, rain ≥0.06 in and snow ≥0.10 in over the four
  game hours, dome, open roof), fit on every
  1999–2025 game with observed kickoff weather.
* **Inputs.** Open-Meteo forecast for the kickoff hour, wind put on the
  game-book scale with the saved calibration (`data/processed/calibration.json`).
* **Lean.** `P(under) >= 0.55` → under; `P(under) <= 0.45` → over. Leans on
  indoor games are impossible by construction.
* **Snapshots.** `scripts/this_week.py` appends *every* upcoming game (not
  just leans) to `data/forward/ledger.csv` with a UTC timestamp, the posted
  total, the forecast, and the model probability. Paper only.

## What counts

* **Primary metric: closing-line value.** For each lean, the snapshot total
  minus the closing total (sign-adjusted so beating the close is positive),
  using the earliest snapshot taken at least 24 hours before kickoff.
* **Secondary:** win rate against the closing total, ROI at -110.
* Everything is reported with the count of leans and the number of rule
  variants examined (this file fixes it at **1**).

## Decision (after Week 18, or at 40 leans, whichever is later)

**Keep using it** only if all of these hold:
1. Mean CLV > 0 and its 95% CI lower bound > 0.
2. Win rate vs the close ≥ 52.4% (break-even at -110).
3. Mean CLV is positive in both halves of the season (Weeks 4–11, 12–18).

**Drop it** if mean CLV ≤ 0 or its 95% CI upper bound is below +0.25 points.

**Anything else is inconclusive.** Carry it into 2027 unchanged; do not
retune thresholds on 2026 data.

## Known limits, stated up front

* The historical backtest used *observed* kickoff weather, an upper bound on
  what a forecast-driven bettor could capture.
* Lines in the ledger come from nflverse's schedule feed, not a specific book.
  Swapping in Pinnacle via The Odds API (the `sharp-markets` client) would make
  the CLV measurement sharper.

## Amendment 1 (2026-09-28, before any Week 4 kickoff): the betting rule

The playbook in `STRATEGY.md` bets one rule; it is graded here on the same terms.

* **Rule B, early wind under.** Outdoor game, kickoff wind forecast ≥ 15 mph on
  the game-book scale, 1–3 days before kickoff → under (1.5 units when rain
  ≥ 0.06 in or snow ≥ 0.10 in is also forecast). Logged by `scripts/alerts.py` as
  `BET ... WIND UNDER` / `STORM UNDER` / `LINE LAG`.
* **Metric and decision:** the same CLV criteria as above, applied to Rule B's
  bets alone, after Week 18 or 40 bets, whichever is later.
* **Why the model lean stays paper-only:** its rain term is estimated on observed
  rain, and in 2024–26 forecast rain was already priced (8–9 against the total)
  while unforecast rain produced most of the historical rain edge.
* Rule variants now under forward test: **2** (the model lean and Rule B).

## Amendment 2 (2026-09-28, after an independent audit; no forward outcomes observed)

An independent review (Codex, Sept 28) reproduced the historical numbers and found
defects in how signals were generated and scored. Changes, with reasons:

1. **Rule B is only actionable with a real price.** A signal now requires a posted
   total, an under price of −115 or better, 1–3 days to kickoff (same-day excluded),
   and positive expected value at that line and price. EV comes from the empirical
   distribution of (final total − market total) in the frozen 1999–2023 cohort of
   outdoor games with 15+ mph wind, so it depends on the offered number (the old
   P(under) was the same at a total of 30 or 60). Triggers without a usable price are
   logged as `no_price` / `price_too_high` / `negative_ev`, never as bets.
2. **Flat, small stakes; no storm size-up.** The 1.5-unit storm stake is withdrawn:
   the storm subset is small and was selected on observed precipitation.
3. **Scoring at the entry number.** `score_forward.py` grades MODEL_LEAN and RULE_B
   separately, at the entry line and entry price, with CLV against the close. (The v1
   scorer silently dropped wind-only signals.)
4. **Frozen calibration.** The ERA5-to-game-book calibration is fit once on 1999–2023
   and reused (`calibration.json`, `frozen: true`); the v1 all-season fit is kept as
   `calibration_v1_all_seasons.json`.
5. **Forecast replay timing.** Planned Pinnacle quotes are taken at each forecast
   lead's decision time (last game hour − lead + 7 h publication latency), so no quote
   predates the forecast it is paired with.
6. **Evaluation window.** Week 4 boards were viewed while these fixes were made, so
   both rules are evaluated on games from **Week 5 (Oct 8, 2026) onward**; ledger rows
   before this amendment (blank `rules_version`) are excluded.
7. **Multiple testing.** 108 historical betting variants were examined. A strict
   Bonferroni bar (p < 0.00046) is not met by the long wind result (p ≈ 0.007); the
   forward test, not the backtest, decides.

Decision criteria are unchanged (CLV-based, per rule). Entry-price ROI is reported as
a secondary measure. Rule variants under forward test: still **2**.

## Amendment 3 (2026-09-28, before any Week 5 game; no Rule B signal logged and no forward outcome observed)

**A secondary CLV measure against Pinnacle's close.** Nothing about the primary
measure or the decision changes.

* **Why.** Rule B's entry prices come from Pinnacle (The Odds API, live since
  Sept 28). The primary CLV compares them with the nflverse closing total, a
  consensus of other books. That comparison mixes a change of book into the change
  of price.
* **What is recorded.** `scripts/capture_close.py` runs every 15 minutes
  (`ops/capture_closes.sh`, launchd). It makes one Odds API call per kickoff slot,
  2–20 minutes before kickoff, and records the totals and prices of every logged
  book for every game in the slot in `data/forward/closes.csv`. The secondary CLV
  uses Pinnacle's.
* **What is reported.** `score_forward.py` reports, for each rule, CLV against that
  captured close, next to the primary measure. It also reports how many bets have no
  captured close (the Mac was asleep, the quota was low, or Pinnacle had no line).
  Missing closes are reported, never imputed.
* **What it can't change.** This measure is descriptive. It doesn't change which bets
  count, the primary CLV, or the keep/drop decision (after Week 18 or 40 bets,
  whichever is later).
* Rule variants under forward test: still **2**.

## Amendment 4 (2026-09-28, before any Week 5 game; no Rule B signal logged and no forward outcome observed)

**The decision horizon pools the 2026 and 2027 seasons.** Nothing about Rule B's
trigger, gates, entry, CLV metric or stakes changes.

* **Why.** The rule produced 18 forecast triggers in 2024 and 25 in 2025 before its
  price gates (review of Sep 28, `strategy-research/plan-review-2026-09-28.md`,
  section 3), so "40 bets" cannot be reached in one season. The original horizon
  ("after Week 18 or 40 bets, whichever is later") would leave the test undecided
  until 2028 whatever the result. A CLV rule needs about 33 NFL signals to detect one
  point of line value and about 130 for half a point (same review, appendix A).
* **New horizon.** The keep/drop decision is made **once, after the 2027 regular
  season (Week 18 of the 2027 season), on 2026 Weeks 5+ and 2027 pooled**, or
  earlier at 40 signals if that comes first. The criteria are unchanged: keep only if
  mean CLV > 0 with a 95% CI lower bound above zero, win rate vs the close ≥ 52.4%,
  and mean CLV positive in both seasons (replacing "both halves of the season" as the
  split); drop if mean CLV ≤ 0 or the 95% CI upper bound is below +0.25 points;
  anything else is inconclusive and carries forward unchanged.
* **Interim read.** `score_forward.py` reports the 2026 result after Week 18 as an
  interim read, labelled as such. It decides nothing and changes nothing; the 2027
  rule is Rule B as registered here.
* **What this can't do.** It doesn't lower the bar, add a variant, or let 2026
  results retune thresholds for 2027.
* Rule variants under forward test: still **2**.

## Amendment 5 (2026-09-28 Pacific, before any Week 5 game; no Rule B signal logged and no forward outcome observed)

An independent audit ([`reviews/2026-09-29-astra-audit.md`](../reviews/2026-09-29-astra-audit.md)) traced
each rule from trigger to scored result and found six places where this file and the code disagreed.
This amendment settles each one. (The audit file is dated in UTC: it was run at 9:02 PM Pacific on
Sep 28. This amendment was written that night and merged on Sep 29, after a second review of the fixes.) **Rule B's trigger, lead window, price cap, stakes and CLV metric are
unchanged, and every game that would have signalled before still signals now.**

### 1. The pricing model (replaces the description in amendment 2, item 1)

Amendment 2 said the expected value "depends on the offered number". The code didn't do that. It
compared the offered line with itself, so the value was the same at a total of 30 or 60, and it gave a
half-point line a chance of pushing.

* **What the data say about the size of the total.** Before building a gate that varies with it, the
  frozen cohort was tested: the under's chance in windy games does not depend on the size of the
  total. The logistic slope is −0.06 per 10 points (p = 0.72). In leave-one-season-out
  cross-validation the flat model has the lowest log loss (0.68442, against 0.68466 to 0.68845 for
  kernels of 12 down to 2 points). None of them rejects a single 2024–25 game at −115.
  [`strategy-research/gate_level_check.py`](../strategy-research/gate_level_check.py) reproduces this.
  The model is therefore flat in the size of the total, by registration.
* **The model.** The final total is a reference total plus a residual drawn from the frozen cohort:
  final total minus closing total in the 656 outdoor games with 15+ mph observed wind, 1999–2023. With
  *x* = offered line − reference, and *G*(t) = P(residual < t) + ½ P(residual = t):
  * a half-point line can't push: P(win) = *G*(x);
  * a whole-number line wins below it, pushes on it and loses above it: P(win) = *G*(x − ½) and
    P(push) = *G*(x + ½) − *G*(x − ½).

  Expected value per unit staked is P(win) × the payout − P(loss).
* **The cohort is a committed file**, `data/processed/pricing_cohort.json`. Rebuilding the games table
  can't move the model, and changing the file needs a dated amendment. Two fingerprints are registered:
  * the residuals: `897a61b6846b077b71c324dc0c2f4b2e28bda963aa69d0cc4a89f181eb039556`
    (`board.PRICING_COHORT_SHA256`). This is the sha256 of the 656 residuals, sorted, rounded to 4
    places, as 64-bit floats (`market.cohort_hash`). It identifies the numbers, whatever the file's
    layout. **Every run checks it**: a file whose residuals hash to anything else stops the run, and
    the run is recorded as failed.
  * the file as committed: `shasum -a 256` gives
    `ba71e29929f2b4f75e29c73601f0b672f45768b6366f70c3a6c0cb9984efb8bc`.
* **Quarter-point lines.** A line such as 43.75 is half a bet at 43.5 and half at 44, so it is priced
  as the average of the two. A higher line is never worth less.
* **A price must be a price.** American odds are at or beyond 100 either side of zero. A feed value
  between −100 and +100 is treated as no price (`no_price`).
* **The reference is the rule's own total**, Pinnacle's when it quotes. So the rule's entry is priced
  at *x* = 0: on a half-point line the under wins 57.5%, worth +7.4% at −115 and +9.7% at −110.
* **What this means for the gate.** The value only reaches zero at about −136, and the price cap is
  −115. **So inside the price cap the expected-value gate cannot reject a bet at the rule's own
  number.** Rule B in practice is: forecast wind of 15+ mph, 1 to 3 days out, under at −115 or better.
  That is also exactly what the historical evidence measured. The gate stays in the code, and
  `negative_ev` stays a status, because the model does reject an under offered well below the
  reference (3 points below, at −115).
* **What the model is for.** It prices a better number at another book. For every game the odds feed
  lists, whether or not Pinnacle quotes it, every run logs the highest total any of the 10 logged
  books offers the under at, at −115 or better (`best_line`, `best_line_under`, `best_line_book`), and
  its value against the reference (`ev_best_line`). A point of total is worth about 2.4 points of win
  probability. This is logging only: the rule's entry and its grading don't change.
* **The highest number isn't always the best value.** A half point more at a worse price can be worth
  less than the rule's own quote. The alert names the best number only when the model prices it above
  the rule's quote.

### 2. Primary and secondary prices (owner decision, Sep 28)

* **Primary: Pinnacle.** A signal priced at Pinnacle has the status `SIGNAL`. These are the registered
  test, and the keep/drop decision uses them alone.
* **Secondary: the backup price.** When Pinnacle has no complete quote (a total and an under price),
  the nflverse consensus line and prices are used. A game that passes every gate at that price has the status `SIGNAL_SECONDARY`. It is
  logged, alerted with the label "secondary price", and reported in its own table. It is not part of
  the decision. A consensus line isn't a price any one book offered.
* A game with both kinds of signal counts once, as primary, at its earliest Pinnacle-priced signal.
* This settles the conflict between the original file ("lines come from nflverse") and amendment 3
  ("entry prices come from Pinnacle").
* The ledger records when the odds feed was read (`quote_utc`) and when Pinnacle last updated its
  market (`quote_update`). On a secondary-price row `quote_utc` dates the best-line columns, since the
  consensus line carries no time of its own, and `quote_update` is empty. Freshness is logged, not
  gated.

### 3. Definitions the earlier text left open

* **Lead time is counted in calendar days:** the kickoff's Eastern date minus the date of the run on
  the Mac's clock (Pacific), 1 to 3 inclusive. The four scheduled runs (7:30 AM, 11:30 AM, 3:30 PM
  and 7:30 PM Pacific) fall on the same date in both zones. In hours, a signal can be logged from
  about 11 to 82 hours before kickoff, depending on the kickoff time. A run on the day of the game
  never qualifies.
* **The model lean's entry** is unchanged: the earliest snapshot at least 24 hours before kickoff.
* **Wind** is the Open-Meteo forecast at the kickoff time, interpolated between the two surrounding
  hours, put on the game-book scale with the frozen calibration.
* **Outdoor** excludes domes, closed roofs, and retractable roofs reported open. An open retractable
  roof is its own category in training and has no weather terms. **With no roof state reported,** a
  game is outdoor unless the stadium has a retractable roof, in which case it is treated as closed.
  The retractable roofs are Atlanta, Dallas, Houston, Indianapolis, Arizona, and the Bernabéu in
  Madrid (Bengals at Falcons, Nov 8, 2026).

### 4. The decision horizon (completes amendment 4, and replaces its "or earlier at 40 signals")

Amendment 4 said the decision comes after the 2027 season "or earlier at 40 signals if that comes
first". That left open when, on which bets, and with which split. There are now exactly two decision
times, and the scorer computes both:

* **If 40 Rule B signals settle in the 2026 regular season,** the decision is made after Week 18 of
  2026 on those bets. "Positive in both seasons" is then read as positive in both halves of the
  season (Weeks 5–11 and 12–18), as in the original file.
* **Otherwise** the decision is made once, after the 2027 regular season, on every bet that kicked
  off by then (2026 Weeks 5+, the 2026 playoffs and the 2027 regular season), and mean CLV must be
  positive in each season. A 40th signal that arrives during 2027 does not bring the decision
  forward.
* **The decision is made once.** It uses the bets that kicked off by its horizon. Bets after the
  horizon never enter it, so a later run of the scorer prints the same result.
* **Before the horizon** the scorer prints an interim read: the numbers and which criteria they meet,
  and no verdict.
* **The model lean** follows the same two horizons, counted in leans: with 40 leans in the 2026
  regular season it is decided after Week 18 of 2026 on those leans, by half; otherwise it is carried
  into 2027 unchanged, as the original file says, and decided after the 2027 regular season on both
  seasons, by season. With fewer than 40 leans by then, the result is inconclusive.
* **If the keep test and the drop test are both met, the result is drop.** That can only happen when
  the whole 95% interval sits between 0 and +0.25 points: a real edge, and too small to keep.
* **Win rate against the close** is counted over the bets that have a primary close. A bet with no
  close is not a loss.
* **The regular season is over** when every game in the schedule has a result, or kicked off more
  than a week ago (a cancelled game never gets a result).
* **The test ends with the 2027 season.** Later games don't count.

### 5. What the scorer now enforces

`scripts/score_forward.py` used to accept any rules version and had no end date. It now:

* counts only rows written under a registered version (`v2-2026-09-28`, `v3-2026-09-28`), logged
  before kickoff, for games from Oct 8, 2026 through the 2027 season;
* counts every excluded row by its first failing reason, so nothing is dropped silently, and prints
  each one with `--list-excluded`;
* computes the keep/drop decision from the criteria above and labels it **interim** or **final**;
* computes the CLV interval over the bets that have a primary close, and says how many don't;
* reports ROI as units won per bet placed. A push counts as a bet. (It used to leave pushes out.)

### 6. Records

* **Ledger.** Rows carry `rules_version = v3-2026-09-28` and these new columns: `ref_total`,
  `best_line`, `best_line_under`, `best_line_book`, `ev_best_line`, `quote_utc`, `quote_update`,
  `wx_hash`, `wx_fetched_utc`, and `wx_wind_dir`, `wx_cross` and `wx_along` (the forecast wind direction and
  its crosswind and along-field parts, from each stadium's orientation; logged for a later study, and
  no rule uses them).
* **Forecasts.** Each forecast a logged run used is kept in `data/forward/forecasts/` under the hash of
  its contents, and the row carries that hash and the time the file was fetched. Before this
  amendment, forecast files were overwritten on every run, so older rows can't be traced to their
  forecast.
* **The one-time ledger rewrite.** The first run under this amendment adds the new columns. The old
  rows are written back as text, character for character, and the ledger as it stood is kept beside
  it (`ledger.before-v3-2026-09-28.csv`).
* **Runs.** Every alert run, finished or failed, leaves a row in `data/forward/runs.csv`, written at
  the end of the run. A run that fails at any stage (building the board, saving the ledger, building
  or sending the alerts) is recorded as failed with the stage, and sends a notification. One game's
  alert failing doesn't stop the other games' alerts. Any key in an error message is blanked before
  it is recorded or sent. Before this, one failed forecast download lost the whole run without a
  record.
* **Odds-feed names that match no team** are printed and written to the run record.
* **Close capture** retries a kickoff slot that came back without Pinnacle's total for some game (two
  calls per slot at most), and it shares the scheduled jobs' credit floor.

### 7. Known limits, stated up front

* **Amendment 2's first rows came before its commit.** The first `v2-2026-09-28` rows were logged at
  10:44 AM Pacific on Sep 28, 29 minutes before amendment 2 was committed. All of those games are
  before Oct 8 and are outside the test.
* **The original file and amendment 1** first appear in the repository's first commit (Sep 28, 9:57
  AM), after the earliest ledger rows (Sep 27, 10:15 PM). Those rows have no rules version and are
  excluded.
* **Timestamps.** A commit time is the author's clock. Every amendment since amendment 1 was merged
  through a GitHub pull request, which carries GitHub's own time. From this amendment on, a rules
  version changes only in the same commit as the amendment that defines it.
* **The size of the edge inside the model is the historical one.** It was measured on observed wind
  at the close. The forecast record is still 12–12. The forward test, not the model, decides.

Rule variants under forward test: still **2**. The historical count rises by 2 for the
size-of-total check (one per sport), to 200.

## Amendment 6 (2026-09-29 Pacific, before any Week 5 game; no Rule B signal logged and no forward outcome observed)

A review of the scorer, made after amendment 5 was merged (pull request 50), found readings the earlier
text left open. Every one is settled here, before any outcome exists. **No trigger, gate, price cap,
stake or metric changes.** The rules version stays `v3-2026-09-28`, because the board behaves exactly
as before; only `scripts/score_forward.py` changes. Where this amendment and any earlier text differ,
this one applies. The last section lists every earlier sentence it changes. A final review before
registration (Sep 29) added sections 9 to 11 and that list. Registered by the hub on the owner's
standing instruction of September 29, 2026 (the hub decides questions of how the tests are graded and
reports them; money, and any rule's trigger, gate or price cap, stay the owner's). The registering
commit is the merge of pull request 59. The owner can change any reading here by a dated amendment made
before the first outcome it would affect.

### 1. A bet whose game was moved or never played is void

* A bet is **void** when its game did not kick off within 24 hours of the kickoff time on its entry
  row (the game was postponed, moved or cancelled), or when the schedule still shows no result 30 days
  after that kickoff. The entry row's kickoff is its `gameday` and `gametime` (Eastern time); the
  scorer compares it with the schedule's kickoff for the same game id.
* A void bet is counted and listed by reason. It is not graded: it is left out of the record, the
  units, the CLV and the count toward 40.
* A sportsbook voids the same bets. Wind rules meet this case more than most, because hurricanes
  postpone games.
* A result that lands after day 30 brings the bet back: it is graded like any other bet from then on.
  If a decision on its horizon is already recorded, the record stands, and the scorer prints the fresh
  computation beside it (section 3).

### 2. A bet still waiting for its result holds its decision open

* A bet whose game has no result yet, and that is not void, is **pending**. The scorer prints how many
  bets are pending.
* No decision is final while any bet that kicked off on or before the decision's horizon is pending.
* This replaces amendment 5's test that treated a game with no result a week after kickoff as not
  played. Under that test a result that arrived late could change a decision after it was made.

### 3. A decision is made once, and written down

* The first time a decision is final, the scorer appends it to `data/forward/decisions.csv`: its
  decision id, the rule, the horizon, the time it was decided (UTC), the number of bets, every number
  the decision used, the verdict, the positions in the ledger of the rows that entered it (1 is the
  first row after the header; they are the entry rows, since the closes come from the schedule), and a
  fingerprint of those rows.
* **The decision id is fixed:** `RULE_B:2026` and `MODEL_LEAN:2026` for the decisions after Week 18 of
  2026, `RULE_B:2026-27` and `MODEL_LEAN:2026-27` for the decisions after the 2027 regular season. The
  record is looked up by its decision id, never by the wording of its label.
* **The fingerprint** is the sha256 of the ledger's header line followed by each row that entered the
  decision, exactly as written in the ledger and in the order of the ledger, each line followed by a
  newline (`\n`), the whole encoded as UTF-8. (If a row was ever written across several lines, the
  rows are taken as the scorer reads them instead.) Every later run recomputes the fingerprint from the
  rows at the recorded positions and, if it differs, prints a warning that the ledger has changed since
  the decision was recorded. The recorded decision still stands.
* Every later run prints the recorded decision. If a fresh computation on the same horizon would now
  come out differently (a corrected score, say), the scorer prints both and says the recorded one
  stands. A preview with `--now` shows a recorded decision only if it was decided at or before the
  preview's date.
* **Only a real run writes the record.** That is a run of the scorer on the live ledger
  (`data/forward/ledger.csv`), on the real clock, reading the default schedule (`data/raw/games.csv`)
  when that file was refreshed in the last 2 days. Every alert run refreshes it. The hub's daily
  check-in runs the scorer this way, so the first check-in after a decision becomes final records it.
  A scorer is live only if its `data/forward` folder, with links resolved, is inside its own project
  folder. In every other case the scorer prints the decision and says why it wasn't recorded:
  * a run with `--now` (a preview as of another time, for tests and rehearsals) records nothing, except
    with `--test-record` beside a test ledger (below);
  * a schedule last refreshed more than 2 days ago records nothing, because played games would look
    unscored and could be voided; refresh it and run the scorer again;
  * a run on another ledger kept in `data/forward/` (the rewrite's backup copy) neither reads nor
    writes the record;
  * a copy of the scorer in another folder (a worker's worktree) run on the live ledger reads the record
    but never writes it;
  * a scorer whose `data/forward` folder is a link to a folder outside its own project reads that
    folder's record but never writes it.
* A run on a test ledger kept anywhere else (`--ledger`) writes `decisions.csv` beside that ledger,
  never into `data/forward/`. `--test-record` exists for tests only: with `--now`, it records decisions
  beside a test ledger as if they were made at that time, and it is refused on a live ledger or any
  other ledger in `data/forward/`.
* **One run at a time.** A run that writes takes a lock on the record and reads it again before it
  appends, so two runs at once can't record the same decision twice.
* **A damaged record.** If `decisions.csv` can't be read (a half-written line, wherever it was cut; a
  line without exactly its 10 fields; a missing header; an empty file; a decision id, verdict or
  numbers the scorer doesn't know or can't print), the scorer says so, records nothing until the file
  is repaired or restored from the ledgers branch, and still prints the scores. It never adds a line
  to a damaged file.
* **A lost record.** The record is copied to the ledgers branch every night. A lost record is restored
  from that copy; it is never decided again. When the live record is missing, a real run reads the
  copy (`origin/ledgers`, as this checkout last fetched it; the scorer never fetches), restores the
  file from it and prints what it restored, before it decides anything. Any other run on the live
  ledger (a preview, a run on a stale schedule, a worker's copy of the scorer) reads the copy too,
  prints its decisions as recorded, and leaves the file alone. It records a new decision only when
  neither the file nor the copy holds one. If git can't show a copy (there is no ledgers branch, or no
  record in it), there is no copy. A copy that is there but can't be read (a damaged file was copied
  before the damage was repaired) stops recording, as a damaged file does, until the file is restored
  from a readable earlier copy in the branch's history (`git log origin/ledgers --
  nfl-weather/decisions.csv`). A record made since the last nightly copy exists only on the Mac until
  that night: if it is lost before then, neither the file nor a copy holds it, and the next real run
  decides it again.

### 4. Horizons are dates

* "After Week 18" means after the last regular-season kickoff in the NFL schedule for that season.
  This replaces amendment 5's "every game in the schedule has a result, or kicked off more than a
  week ago"; section 2 now keeps a decision open while any of its bets waits for a result.
* A game dated after a test's end never counts, whatever season label it carries. For the NFL the
  schedule labels each game's season, and no decision uses a bet that kicked off after its horizon;
  the last horizon is the end of the 2027 regular season.

### 5. The model lean's entry

* The model lean's entry is **the earliest snapshot, at least 24 hours before kickoff, that has both a
  lean and a posted total.** This replaces the original "What counts" entry at the top of this file
  ("the earliest snapshot taken at least 24 hours before kickoff"), which amendment 5 repeated. The
  code took the earliest such row with a lean, and it could take one with no posted total and grade it
  as a loss. The live ledger already has such a row: the 7:30 PM run on Sep 28 logged an
  under lean on Rams at Eagles (Week 4, outside the test) with a blank total.
* Rule B's entry is its earliest `SIGNAL` row before kickoff (for each listing, section 9). The 24-hour
  rule is the model lean's only; amendment 5, section 3 already gives Rule B's window as about 11 to 82
  hours before kickoff.

### 6. After the 2026 decision

* A keep or a drop at the 2026 horizon (40 in the 2026 regular season) is the decision. Later bets are
  still logged and reported, and decide nothing.
* An inconclusive result at the 2026 horizon carries the rule into 2027 unchanged, as the original
  file says. It is decided once more after the 2027 regular season, on both seasons pooled, with mean
  CLV positive in each season.
* That is a second look at overlapping data: the 2026 bets enter both the 2026 decision and the pooled
  one. It replaces amendment 5, section 4's "The decision is made once." for this case only.
* A decision recorded after the 2027 regular season, with none recorded for 2026, is the decision. If a
  2026 result lands later and brings 2026 to 40 settled bets, no 2026 decision is made.
* While 2026 bets are still waiting for results that could bring 2026 to 40, the 2026 decision waits
  for them; if they end up void and 2026 has fewer than 40, the pooled decision applies.
* This applies to Rule B and to the model lean.

### 7. Ties with the close

* Ties with the close are left out of the win rate against the close: a tie neither beats the close
  nor loses to it.
* The printed count of bets "with a primary close" counts bets whose game has a closing total.

### 8. Corrections to amendment 5's quoted numbers (2026-09-29)

Amendment 5's text is left as written. Two numbers in section 1, "What this means for the gate", were
off:

* The value at the rule's own number reaches zero at **about −135** on a half-point line (−135.1), and
  **−136 on a whole number** (−136.4), not "about −136" for both. The conclusion stands: inside the
  −115 cap the gate can't reject a bet at the rule's own number.
* At −115 the model rejects an under **from 1.5 points below the reference** (reference 42.5, under
  41: −0.6%), not only "3 points below". One point below still passes (+2.3%).

### 9. A postponed game that signals again is two listings

* A game's rows are grouped into **listings** by the kickoff on each row: rows whose kickoffs are
  within 24 hours of each other are one listing. Precisely: in order of each row's kickoff, a row whose
  kickoff is more than 24 hours after the first kickoff of the current listing starts a new listing.
* A listing's entry is its earliest signal: for Rule B its earliest `SIGNAL` row, for the model lean
  its earliest snapshot that qualifies under section 5.
* A listing whose entry's kickoff is more than 24 hours from the game's actual kickoff is void
  (section 1). The listing that matches the actual kickoff is graded like any other bet. If two
  listings are each within 24 hours of the actual kickoff, the nearer one is graded (the later one if
  they are equally near) and the other is void.
* So a game is still graded once, and a game postponed by more than a day that signals again on its
  new date is graded at its new entry. Before this reading the second signal was dropped as a repeat
  of the first, which was void, so the game was never a bet.

### 10. "Before kickoff"

* "Before kickoff" means before the earlier of the kickoff on the row and the kickoff in the schedule,
  in both scorers and for every use: which rows count, the entries, the last quotes and the
  later-quote closes. Here that covers which rows count, both rules' entries, and the model lean's 24
  hours. The row's kickoff is its `gameday` and `gametime` (Eastern time).
* Why: a row carries the kickoff the schedule showed when it was logged. When a game is moved, the
  row's kickoff and the schedule's differ, and a row logged after the game really started must not
  count.

### 11. A closing-line decision needs 20 closes

* A closing-line decision needs closing lines. If fewer than 20 of the bets in a decision have a
  primary close, the result is **inconclusive**, and the scorer says why. This applies to Rule B and to
  the model lean, at both horizons. An inconclusive 2026 result then goes on to the pooled decision
  (section 6).
* Whenever some bets in a decision have no primary close, the scorer prints how many.

### What this amendment replaces

Each earlier sentence below is quoted as registered; the section of this amendment named beside it
applies instead.

* The original file, "What counts": "using the earliest snapshot taken at least 24 hours before
  kickoff". Replaced by section 5 (the entry also needs a posted total), section 9 (each listing has
  its own entry) and section 10 (the 24 hours are counted to the earlier kickoff).
* The original file, "Decision": "Keep using it only if all of these hold:", "Drop it if mean CLV ≤ 0 or
  its 95% CI upper bound is below +0.25 points." and "Anything else is inconclusive." Amendment 4: "drop
  if mean CLV ≤ 0 or the 95% CI upper bound is below +0.25 points; anything else is inconclusive and
  carries forward unchanged".
  Amendment 5, section 4: "If the keep test and the drop test are both met, the result is drop." With
  fewer than 20 bets that have a primary close, a decision is inconclusive whatever its numbers
  (section 11).
* Amendment 5, section 1: "The value only reaches zero at about −136" and "3 points below, at −115".
  Corrected by section 8.
* Amendment 5, section 2: "A game with both kinds of signal counts once, as primary, at its earliest
  Pinnacle-priced signal." A game postponed by more than a day has one entry per listing, and only the
  listing that matches the actual kickoff is graded (section 9).
* Amendment 5, section 3: "The model lean's entry is unchanged: the earliest snapshot at least 24 hours
  before kickoff." Replaced by sections 5, 9 and 10.
* Amendment 4: "The keep/drop decision is made once, after the 2027 regular season". Amendment 5,
  section 4: "The decision is made once." For an inconclusive 2026 result only, section 6 adds a
  second look, on both seasons pooled, at data that overlaps the first.
* Amendment 5, section 4: "If 40 Rule B signals settle in the 2026 regular season, the decision is made
  after Week 18 of 2026 on those bets." and, for the model lean, "with 40 leans in the 2026 regular
  season it is decided after Week 18 of 2026 on those leans, by half". A void bet doesn't settle and
  doesn't count toward 40 (section 1). And once a decision after the 2027 regular season is recorded
  with none recorded for 2026, a 2026 result that lands later and brings 2026 to 40 makes no 2026
  decision (section 6).
* Amendment 5, section 4: "It uses the bets that kicked off by its horizon." Void bets among them are
  left out (section 1), and the decision waits while any of them is pending (section 2).
* Amendment 5, section 4: "so a later run of the scorer prints the same result". A later run prints the
  recorded decision, and a fresh computation beside it when that now differs (section 3).
* Amendment 5, section 4: "Otherwise the decision is made once, after the 2027 regular season, on every
  bet that kicked off by then". Void bets are left out (section 1), and the decision waits while any of
  those bets is pending (section 2).
* Amendment 5, section 4: "Win rate against the close is counted over the bets that have a primary
  close." Ties with the close are left out as well (section 7).
* Amendment 5, section 4: "The regular season is over when every game in the schedule has a result, or
  kicked off more than a week ago (a cancelled game never gets a result)." Replaced by section 2 (a bet
  with no result holds its decision open) and section 4 ("after Week 18" is the last regular-season
  kickoff).
* Amendment 5, section 5: "logged before kickoff, for games from Oct 8, 2026 through the 2027 season".
  Before kickoff now means before the earlier of the row's kickoff and the schedule's (section 10).

Rule variants under forward test: still **2**. Nfl-weather amendment 6 and cfb-weather amendment 4
test nothing and leave the running variant count unchanged. On the day of registration it is **271**,
so the multiple-testing bar is p < 0.000185 (`strategy-research/README.md`, `STATUS.md`).

## Amendment 7 (2026-09-29 Pacific, before any Week 5 game; no Rule B signal logged and no forward outcome observed)

This amendment makes the 95% interval behind every closing-line decision the wider of two: the plain interval,
and one grouped by game day. The closing-line moves of windy games on the same day move together, so the plain
interval alone keeps a rule with no edge too often, and the grouped interval alone can come out too narrow. It
also registers which feed event gives a game's captured close, closes three small gaps in the decision record, and
registers that the nightly copy of the record never loses a line. **No trigger, gate, price cap or stake
changes.** The rules version stays `v3-2026-09-28`, because the board behaves exactly as before; only
`scripts/score_forward.py`, `scripts/capture_close.py` and `ops/sync_ledgers.sh` change. Where this amendment and
any earlier text differ, this one applies, and the last section lists every earlier sentence it changes.
Registered by the hub on the owner's standing instruction of September 29, 2026 (the hub decides questions of how
the tests are graded and reports them; money, and any rule's trigger, gate or price cap, stay the owner's). The
registering commit is the merge of pull request 64. The owner can change any reading here by a dated amendment
made before the first outcome it would affect.

### 1. The keep test's interval is the wider of two

* **Why.** The paper-to-money study (`strategy-research/README.md`, "The paper-to-money gate", and
  `strategy-research/simulate_decisions.py`) found that the closing-line moves of windy games on the same day move
  together, and that NFL seasons also swing as a whole. The plain interval treats every bet as independent, so the
  registered keep test keeps a rule with no edge more often than the 2.5% it is meant to. The first draft of this
  amendment grouped the interval by game day instead. Its second review showed that the grouped interval can come
  out narrower than the plain one, even of zero width, and the simulation showed that with fully independent
  signals in college football it keeps a rule with no edge slightly more often than the plain one, because 40
  signals fall on only 10 to 16 game days. Neither interval is safe alone, so the registered interval is the wider
  of the two. [`strategy-research/keep_test_check.py`](../strategy-research/keep_test_check.py) measures all three.
* **The reading.** Wherever a registered decision uses mean CLV with a 95% interval (Rule B and the model lean; the
  keep test and the drop test; after Week 18 of 2026 and after the 2027 regular season):
  * the mean m is the plain mean of the CLVs of the n bets in the decision that have a primary close;
  * the plain half-width is t(0.975, n - 1) x s / sqrt(n), where s is the sample standard deviation of those CLVs
    and t(0.975, n - 1) is the 97.5th percentile of Student's t with n - 1 degrees of freedom;
  * the grouped half-width is t(0.975, G - 1) x the grouped standard error. The bets are grouped by the calendar
    date of the game's actual kickoff in Eastern time (America/New_York), the kickoff in the schedule; G is the
    number of days with at least one such bet; for each day g, s_g is the sum over that day's bets of (CLV - m); the
    variance of the mean is (G / (G - 1)) x (the sum over days of s_g squared) / n squared, and the grouped
    standard error is its square root; t(0.975, G - 1) is the 97.5th percentile of Student's t with G - 1 degrees
    of freedom;
  * **the registered interval is m plus or minus the larger of the two half-widths;**
  * with fewer than 2 game days, or fewer than 2 bets, there is no interval and the result is inconclusive;
  * everything else is unchanged: the keep test's other criteria, the drop test's 0.25-point bound (which uses
    this same interval), the 20-close limit, void and pending bets, the horizons and the decision record.
* **The plain multiplier.** Until now the scorer computed the plain interval as m plus or minus 1.96 x s / sqrt(n).
  The plain half-width here uses t(0.975, n - 1) instead, which is wider (2.09 at 20 bets, 2.02 at 40), so the
  plain half of the registered test is slightly stricter than the interval the scorer printed before. The last
  section names this change.
* **What the scorer shows.** It prints the registered interval and says which of the two it is ("the wider is the
  grouped one, over G game days" or "the wider is the plain one"; "the two are equally wide" when they are, as when
  every game day has one bet), and it prints both. The decision record stores the registered bounds (`ci_low`,
  `ci_high`), both half-widths (`plain_half_width`, `grouped_half_width`) and G (`game_days`). No decision has
  been recorded, so no record has to change.
* **What it measured.** `keep_test_check.py` reuses the study's model: the open-to-close moves of 371 windy NFL
  games, the same-day and same-season dependence it estimated, and the dates of the windiest games of 2016–25
  replayed onto 2026 Weeks 5–18. Run with seed 29: 40,000 simulated paths per case, 40 bets per path, no edge
  unless stated. "Plain" below is the interval as the scorer had it (1.96); "grouped" is the grouped interval
  alone, as the first draft had it.
  * Realistic dependence (same day 0.07, same season 0.06): the registered test keeps a rule with no edge 5.8% of
    the time at 17 signals a season and 7.4% at 25 (plain 8.0% and 10.3%; grouped 6.4% and 8.1%).
  * Stress dependence (same day 0.16, same season 0.06): 6.3% and 7.4% (plain 9.0% and 11.0%; grouped 6.6% and
    7.8%).
  * Independent signals: 1.4% and 1.4% (plain 2.1% and 2.1%; grouped 2.0% and 2.0%).
  * With no model at all: whole historical days resampled, 1.2% (plain 3.7%, grouped 1.6%); whole NFL seasons
    resampled, 3.2% (plain 5.6%, grouped 3.2%).
  * The two looks of amendment 6, section 6 (after Week 18 of 2026 only with 40 bets in the 2026 regular season,
    otherwise once after the 2027 regular season on both seasons pooled), with the registered interval, the
    20-close limit, mean CLV positive in each half or season, and keep and drop both met read as a drop: a rule
    with no edge is kept 6.5% of the time at 17 signals a season and 8.4% at 25 in the realistic case (grouped
    7.1% and 8.9%), 6.7% and 8.4% in the stress case, and 1.3% and 1.4% with independent signals. The win rate
    against the close is not simulated, so these are upper bounds for that criterion. No simulated path reached 40
    bets in 2026, so the rate is the pooled look's.
  * It also keeps a real edge less often. At 17 signals a season, realistic case: 28% if the true edge is half the
    historical line move and 66% if it is the full move (plain 34% and 73%; grouped 29% and 67%); over the two
    looks, 26% and 60%.
  * In every case the registered test keeps a rule with no edge no more often than the plain or the grouped
    interval alone. For the keep test on its own this must be so: a path it keeps, both of the others keep. Over
    the two looks it need not be, because keep and drop both met is a drop, and a wider interval can turn a drop
    into a keep; there it is measured instead: every simulated path the registered test keeps, both of the others
    keep too. The script checks both, path by path. Run with seed 6 instead, the registered test's rates agree with
    these to within 0.3 points.
* **Where the grouped interval alone fell short, the registered test holds.**
  * Day totals that balance: 40 bets on 4 game days, 10 a day, whose CLVs add up to the same amount on each day
    (two of +5.5 and eight of -1.0) give a grouped interval of zero width, +0.30 to +0.30, which the first draft
    would have kept. The plain half-width is the wider there, so the registered interval is -0.54 to +1.14, which
    includes zero, and the result is inconclusive.
  * Independent signals: the grouped interval alone keeps a no-edge rule 2.0% of the time in the NFL (in college
    football 3.1 to 3.4%, more than the plain interval's 2.7 to 2.8%); the registered test keeps it 1.4% of the
    time (in college football 1.7 to 1.9%).
* **Known limit: it does not fix the NFL.** The NFL's remaining error comes from the season-wide swing, which
  grouping by day can't correct, and one or two seasons can't measure a season-wide swing. With the season share
  set to 0, the registered test keeps a no-edge rule 1.7% of the time. As registered, the NFL keep decision still
  lets a rule with no edge through 5.8 to 7.4% of the time in the realistic case (6.5 to 8.4% over the two looks)
  and 1.2 to 3.2% in the model-free checks, against the intended 2.5%.
* **The money gate is a separate question.** When real money goes in (`STRATEGY.md`, "Stake") is the owner's
  decision, and the owner has not chosen a gate. Nothing here changes it.
* **Variants.** This changes how a test is graded, not a betting rule: 0 variants.

### 2. Which feed event gives a game's captured close

Pull request 62 (merged Sep 29) made close capture take one entry of the odds feed per game. This registers the
rule it implements, with one change. A **feed event** is one event in the odds feed (The Odds API): a game as the
feed lists it, with its own event id, start time and books. It is not a listing in the sense of amendment 6,
section 9, which groups a game's ledger rows.

* **The rule.** When a kickoff slot is due, the feed can list a game's two teams more than once (a relisted
  event, or a rematch later in the season):
  * a feed event counts for a game only if it has the game's home and away teams and starts within 6 hours of the
    scheduled kickoff; a feed event with no readable start time never counts;
  * among those, a feed event with a complete Pinnacle quote (a total and a valid under price, as on the board)
    comes first, and among the feed events left, the one starting nearest the scheduled kickoff is taken;
  * every logged book's total and prices in that one feed event are written to `data/forward/closes.csv`, and the
    secondary CLV uses its Pinnacle row, as amendment 3 says.
* **The change.** When two or more feed events are equally near the kickoff and all carry the same complete
  Pinnacle quote (the same total and the same under and over prices), they are the same game listed twice, and the
  first in the feed is taken. Until now that case was a tie and the close was lost.
* **Still a tie.** Equally near feed events whose Pinnacle quotes differ, or that have no complete Pinnacle quote,
  are a tie, and none is taken.
* **A game with no usable feed event** (a tie, no feed event within 6 hours, no readable start time, or not in the
  feed at all) has no captured close for that slot. Its row is written with the book columns blank, and the slot is
  tried once more if the next run still falls 2 to 20 minutes before kickoff (at most two calls per slot,
  amendment 5, section 6). What is still missing then stays missing: it is reported, never imputed.
* **A feed with no usable feed event.** When the feed answers with no events at all, or with events that no logged
  book prices, the slot has no feed events: every due game is written with the book columns blank, the try is
  counted as for any incomplete slot, and the run ends cleanly. The printed note says which of the two happened
  ("returned no events", or "returned k events, none priced by any logged book"). Until now the script stopped with
  an error before it wrote its state file, so the try was never counted.
* **Nothing else changes:** the books recorded, the 2 to 20 minute window, at most two calls per slot, the quota
  floor, the columns of `closes.csv` and the shape of the state file. In the offline replay made for this
  amendment (scratch scripts, not kept in the repository), every cached real feed (4 responses; 62 runs over their
  kickoff slots, 1,238 rows) and 9 made-up ordinary slot sequences, run through the script as it was before this
  amendment and as it is now, gave byte-identical `closes.csv`, state file and printout, and the one real capture
  so far (Sep 28, Eagles at Bears) replayed to the live `closes.csv` byte for byte. A reviewer's separate replay,
  over other slots, also found the rows byte-identical.

### 3. Three gaps in the decision record, and a copy that never loses a line

A review after amendment 6 found three rare cases where the code did not do what section 3 of amendment 6 says,
and the reviews of this amendment found that the nightly copy itself could lose a line. Each is settled here.

* **A time with no time zone.** A recorded time with no time zone (a spreadsheet can re-save
  `2027-01-10T18:00:00Z` as `2027-01-10T18:00:00`) couldn't be compared with the scorer's times, and it stopped the
  whole run, so the day's report was lost. Now a record whose time cannot be read as a UTC time is a damaged
  record, and section 3's rule for damaged records applies: the scorer says so, records nothing until the file is
  repaired, and still prints the scores.
* **A damaged record still shows what it can.** With a damaged `decisions.csv`, any decision in it that can still
  be read is still printed as recorded, and no fresh "FINAL" that contradicts it is printed for that decision; the
  scorer says the record is damaged and records nothing until it is repaired. A decision can still be read when its
  line, taken on its own, has exactly the record's 10 fields and passes every check a recorded decision must pass.
  A decision whose line can't be read, and that the copy on the ledgers branch doesn't hold, is computed fresh and
  printed with the reason it isn't recorded, as before.
* **A decision missing from a file that still exists.** A decision that is missing from a `decisions.csv` which
  still exists, while the copy on the ledgers branch holds it, is restored from the copy, never decided again. A
  real run appends the copy's own line for it to the file, byte for byte, under the lock, and prints what it
  restored; any other run on the live ledger prints it from the copy as recorded and leaves the file alone. When the
  file is damaged, the decision is printed from the copy, and restored once the file is repaired. Until now the copy
  was read only when the whole file was missing. The scorer still never fetches: the hub's daily check-in runs
  `git fetch` in the live checkout before it runs the scorers, so the copy read is the latest one published.
* **The published copy never loses a line.** Before the nightly copy (`ops/sync_ledgers.sh`, about 11:45 PM on the
  Mac) copies `decisions.csv`, it compares the file with the copy already published on the ledgers branch. If any
  line of the published copy is missing from the file, or the file is missing, empty, cut (its last line has no
  line break) or does not start with the record's header line, it keeps the published copy as it is, prints one line
  saying which project's record it did not publish and why, and syncs every other file as usual; it never fails the
  sync and never removes the published copy. A file that holds every published line, plus new ones, is published as
  before. The first copy is checked the same way: while nothing is published, a file that is empty, cut or does not
  start with the header is not published either, and the line says that nothing has been published yet (with no
  file at all, as before the first decision, it says nothing). So a decision that was ever published is never
  decided again: if the file loses it, the copy still holds it, and the next real run restores it. The one case
  left is a decision recorded since the last nightly copy that published the file and lost before the next one:
  neither the file nor the copy holds it, and the next real run decides it again, as amendment 6 says. Normally that
  is a decision recorded and lost on the same day. But while the nightly copy holds the file back because a
  published line in it has changed (a hand edit, say, or a spreadsheet re-saving the file with other line endings,
  which the scorer still reads), the scorer goes on recording and nothing new is published, so every decision
  recorded until the hub puts that line back exists only on the Mac. A changed line is not restored by the scorer
  (the file holds a decision under that id): the nightly copy keeps the published line, says so every night, and the
  hub puts the published line back by hand.
* **A copy that can't be read.** Because the copy is now read on every run, amendment 6's rule for a damaged copy
  applies whether or not the file is there: while the copy can't be read, nothing is recorded, and the scorer says
  so on every run. Each decision on a line of the copy that can still be read (the same test as for a damaged file)
  is held: if the file doesn't hold it, it is printed from the copy as recorded, never decided again, and it is not
  restored from a damaged copy (the hub can restore it by hand). Recording resumes once the copy can be read again.
  The nightly copy never replaces a published copy that is itself cut or does not start with the record's header
  line: it keeps it, and the line it prints says that the published copy is damaged, not the file. An empty copy
  is replaced as a first copy is published. A copy with any other damaged line is replaced only by a file that
  holds every line of it. Otherwise the hub replaces a damaged copy by hand, with a commit to the ledgers branch.
  When the file is missing, it is first restored by hand from a readable earlier copy in the branch's history (`git log
  origin/ledgers -- nfl-weather/decisions.csv`), as amendment 6 says.

### What this amendment replaces

Each earlier sentence below is quoted as registered; the section of this amendment named beside it applies
instead.

* `STRATEGY.md`, Rule B, "Decision": "Keep only if average CLV > 0 with a 95% interval above zero". The 95%
  interval is the wider of the plain one and the one grouped by game day, and with fewer than 2 game days (or 2
  bets) there is none and the result is inconclusive (section 1).
* `STRATEGY.md`, Rule B, "Decision", the dated note of amendment 6: "a lost record is restored from its nightly copy
  on the ledgers branch, never decided again unless it is lost before that night's copy is made". This holds, and
  now also for a decision lost from a file that still exists: the nightly copy never publishes a file that has lost
  a published line. That night's copy now means the next nightly copy that publishes the file: while the nightly
  copy holds the file back because a published line in it has changed, the first one after the hub puts that line
  back (section 3). A new dated note in `STRATEGY.md` says so.
* The original file, "Decision": "Mean CLV > 0 and its 95% CI lower bound > 0." and "Drop it if mean CLV ≤ 0 or its
  95% CI upper bound is below +0.25 points." The 95% interval is the wider of the plain one and the one grouped by
  game day, and with fewer than 2 game days (or 2 bets) there is none and the result is inconclusive, whatever the
  mean (section 1).
* Amendment 4: "keep only if mean CLV > 0 with a 95% CI lower bound above zero" and "drop if mean CLV ≤ 0 or the
  95% CI upper bound is below +0.25 points". The same (section 1).
* Amendment 5, section 4: "If the keep test and the drop test are both met, the result is drop. That can only happen
  when the whole 95% interval sits between 0 and +0.25 points: a real edge, and too small to keep." The 95% interval
  here is the registered one, the wider of two, and this still holds; with fewer than 2 game days there is no
  interval, and the result is inconclusive (section 1).
* Amendment 5, section 5: "computes the CLV interval over the bets that have a primary close, and says how many
  don't;". The interval is the wider of the plain one and the one grouped by game day, and both are printed. Its
  plain half-width uses Student's t on n - 1 degrees of freedom; until now the scorer computed the plain interval
  with 1.96, which is narrower (section 1).
* Amendment 6, section 11: "If fewer than 20 of the bets in a decision have a primary close, the result is
  inconclusive, and the scorer says why." A decision whose bets with a primary close kicked off on fewer than 2 game
  days is inconclusive too (section 1).
* Amendment 3: "It makes one Odds API call per kickoff slot, 2–20 minutes before kickoff, and records the totals and
  prices of every logged book for every game in the slot in `data/forward/closes.csv`." Each game's rows come from
  the one feed event it takes, and a game with no usable feed event has none (section 2).
* Amendment 3: "It also reports how many bets have no captured close (the Mac was asleep, the quota was low, or
  Pinnacle had no line)." A game with no usable feed event has no captured close either (section 2).
* Amendment 6, section 3: "If `decisions.csv` can't be read (a half-written line, wherever it was cut; a line
  without exactly its 10 fields; a missing header; an empty file; a decision id, verdict or numbers the scorer
  doesn't know or can't print), the scorer says so, records nothing until the file is repaired or restored from the
  ledgers branch, and still prints the scores." A time that can't be read as a UTC time is damage too, and the
  decisions that can still be read are printed as recorded (section 3).
* Amendment 6, section 3: "When the live record is missing, a real run reads the copy (`origin/ledgers`, as this
  checkout last fetched it; the scorer never fetches), restores the file from it and prints what it restored, before
  it decides anything." A single decision missing from a file that still exists is restored from the copy too, by
  appending the copy's own line (section 3).
* Amendment 6, section 3: "The record is copied to the ledgers branch every night." The nightly copy publishes
  `decisions.csv` only when the file ends with a line break, starts with the record's header line and holds every
  line of the copy already published; otherwise it keeps the published copy (or, before the first copy, publishes
  none) and says so (section 3).
* Amendment 6, section 3: "A lost record is restored from that copy; it is never decided again." This holds, and now
  also for a line lost from a file that still exists: the published copy never loses a line, so a decision that
  was ever published is never decided again; the one case left is a decision recorded since the last nightly copy
  that published the file and lost before the next one (section 3).
* Amendment 6, section 3: "A record made since the last nightly copy exists only on the Mac until that night: if it
  is lost before then, neither the file nor a copy holds it, and the next real run decides it again." A record made
  since the last nightly copy that published the file exists only on the Mac until the next one that publishes it:
  normally that night, but while the nightly copy holds the file back because a published line in it has changed,
  not before the hub puts that line back (section 3).
* Amendment 6, section 3: "A copy that is there but can't be read (a damaged file was copied before the damage was
  repaired) stops recording, as a damaged file does, until the file is restored from a readable earlier copy in the
  branch's history (`git log origin/ledgers -- nfl-weather/decisions.csv`)." This now applies whether or not the file
  is there; the decisions on the copy's readable lines are printed from it as recorded; recording resumes once the
  copy can be read again; and the nightly copy never replaces a copy that is cut or does not start with the
  record's header line, and replaces any other damaged copy only with a file that holds every line of it, so
  otherwise the hub replaces it by hand (section 3).

Rule variants under forward test: still **2**. This amendment tests nothing and leaves the running variant
count unchanged: on the day of registration it is **273**, so the multiple-testing bar is p < 0.000183
(`strategy-research/README.md`, `STATUS.md`).
