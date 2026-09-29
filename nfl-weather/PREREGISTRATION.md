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
this one applies.

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

* The first time a decision is final, the scorer appends it to `data/forward/decisions.csv`: the rule,
  the horizon, the time it was decided (UTC), the number of bets, every number the decision used, the
  verdict, and a fingerprint (sha256) of the ledger rows that entered it (the entry rows; the closes
  come from the schedule).
* Every later run prints the recorded decision. If a fresh computation on the same horizon would now
  come out differently (a corrected score, say), the scorer prints both and says the recorded one
  stands.
* **Only a real run writes the record.** That is a run of the scorer on the live ledger
  (`data/forward/ledger.csv`), on the real clock, reading the default schedule (`data/raw/games.csv`)
  when that file was refreshed in the last 2 days. Every alert run refreshes it. The hub's daily
  check-in runs the scorer this way, so the first check-in after a decision becomes final records it.
  In every other case the scorer prints the decision and says why it wasn't recorded:
  * a run with `--now` (a preview as of another time, for tests and rehearsals) records nothing;
  * a schedule last refreshed more than 2 days ago records nothing, because played games would look
    unscored and could be voided; refresh it and run the scorer again;
  * a run on another ledger kept in `data/forward/` (the rewrite's backup copy) neither reads nor
    writes the record;
  * a copy of the scorer in another folder (a worker's worktree) run on the live ledger reads the record
    but never writes it.
* A run on a test ledger kept anywhere else (`--ledger`) writes `decisions.csv` beside that ledger,
  never into `data/forward/`.

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
* Rule B's entry is its earliest `SIGNAL` row before kickoff. The 24-hour rule is the model lean's
  only; amendment 5, section 3 already gives Rule B's window as about 11 to 82 hours before kickoff.

### 6. After the 2026 decision

* A keep or a drop at the 2026 horizon (40 in the 2026 regular season) is the decision. Later bets are
  still logged and reported, and decide nothing.
* An inconclusive result at the 2026 horizon carries the rule into 2027 unchanged, as the original
  file says. It is decided once more after the 2027 regular season, on both seasons pooled, with mean
  CLV positive in each season.
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

Rule variants under forward test: still **2**. This amendment tests nothing, so the historical count
stays 200.
