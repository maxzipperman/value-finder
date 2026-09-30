# Pre-registered forward test: CFB weather unders, 2026 season

Locked 2026-09-28, before any CFB signal existed (the first board had no 15+ mph
forecasts). Rule, gates and decision criteria are in `STRATEGY.md` and fixed for
the season: Rule B (forecast wind ≥ 15 mph, 1–3 days out, under −115 or better,
positive EV at the offered line and price). Evaluation covers games from
Oct 1, 2026. Every board snapshot is appended to `data/forward/ledger.csv` with
`rules_version = cfb-v1-2026-09-28`. Variants under forward test: 1.

## Amendment 1: Rule HT (high-total under)

Written 2026-09-28. It is locked by the commit that merges it, which must land before the first eligible game: 2026 Week 6, kickoff 2026-10-07 00:00 UTC. No Rule HT outcome existed when it was written.

- **Adds Rule HT** as defined in `STRATEGY.md`:
  - The posted total is at least the prior season's mean closing total + 10 (2026: 62.6).
  - The under must be −115 or better.
  - Entry is at each game's last logged quote before kickoff.
- **Grading:** win rate and ROI at the entry price, graded once after the 2027 season on 2026 Weeks 6+ and 2027 pooled.
  - Promote only if one-sided binomial p < 0.05 against the break-even of the prices taken, and ROI > 0.
  - Drop at or below break-even.
  - Otherwise stay on paper.
- **Rule B is unchanged.**
- **Ledger:** from this amendment on, board snapshots carry `rules_version = cfb-v2-2026-09-28` and two new columns, `ht_threshold` and `rule_ht`.
- **Variants under forward test:** 2.
- **Also logged, not graded:** the best under price any logged book offers at the rule's number (`best_under`, `best_under_book`; issue #15). Neither rule's entry price changes.

## Amendment 2 (2026-09-28, before the first eligible game on Oct 1; no Rule B or Rule HT signal logged)

**A secondary CLV measure against the close captured at kickoff.** Nothing about
the primary measure or the decision changes.

* **Why.** The primary CLV compares the entry with the last alert quote before
  kickoff. The alerts run about every 4 hours, so that quote can be 0.5–4 hours
  before kickoff.
* **What is recorded.** `scripts/capture_close.py` runs every 15 minutes
  (`ops/capture_closes.sh`, launchd). It makes one Odds API call per kickoff slot,
  2–20 minutes before kickoff, and records the total and prices for every FBS game
  in the slot in `data/forward/closes.csv`. The source is Pinnacle when it lists the
  game, else DraftKings, the same as the board.
* **What is reported.** `score_forward.py` reports CLV against that captured close,
  next to the primary measure. It also reports how many bets have no captured close.
  Missing closes are reported, never imputed.
* **What it can't change.** This measure is descriptive. It doesn't change which bets
  count, the primary CLV, or the keep/drop decision.
* **Rule HT (amendment 1)** keeps its entry at the last logged quote before kickoff.
  The scorer also reports the captured close next to it, as a descriptive reference.
* Variants under forward test: still **2**.

## Amendment 3 (2026-09-28 Pacific, before the first eligible game on Oct 1; no Rule B or Rule HT signal logged)

An independent audit ([`reviews/2026-09-29-astra-audit.md`](../reviews/2026-09-29-astra-audit.md)) traced
each rule from trigger to scored result and found places where this file, `STRATEGY.md` and the code
disagreed. This amendment settles each one. (The audit file is dated in UTC: it was run at 9:02 PM
Pacific on Sep 28. This amendment was written that night and merged on Sep 29, after a second review
of the fixes.) **Both rules' triggers, price caps and grading are
unchanged, and every game that would have signalled before still signals now.**

### 1. The pricing model behind Rule B's "positive expected value"

The code compared the offered line with itself, so the value was the same at every total, and it
gave a half-point line a chance of pushing. The model is now registered in full. It is the same model
as nfl-weather's (its amendment 5), on this sport's cohort.

* **The size of the total doesn't matter.** Tested on the frozen cohort: the logistic slope is −0.02
  per 10 points (p = 0.83), and in leave-one-season-out cross-validation the flat model has the
  lowest log loss (0.68454, against 0.68540 to 0.69110 for kernels of 12 down to 2 points). The
  narrowest kernel would have rejected 17 of 145 games in 2024–25, and those went 10–7: it fits
  noise. [`strategy-research/gate_level_check.py`](../strategy-research/gate_level_check.py)
  reproduces this.
* **The model.** The final total is a reference total plus a residual drawn from the frozen cohort:
  final total minus closing total in the 855 outdoor games with 15+ mph observed station wind,
  2006–2023. With *x* = offered line − reference, and *G*(t) = P(residual < t) + ½ P(residual = t):
  a half-point line has P(win) = *G*(x) and can't push; a whole-number line has P(win) = *G*(x − ½)
  and P(push) = *G*(x + ½) − *G*(x − ½).
* **The cohort is a committed file**, `data/processed/pricing_cohort.json`. Changing it needs a dated
  amendment. Two fingerprints are registered:
  * the residuals: `c49a6649c3f86ac1280ed488f675c14859b23073c1aa8e18aab63060b38bff67`
    (`board.PRICING_COHORT_SHA256`), the sha256 of the 855 residuals, sorted, rounded to 4 places, as
    64-bit floats (`market.cohort_hash`). **Every run checks it**: a file whose residuals hash to
    anything else stops the run, and the run is recorded as failed.
  * the file as committed: `shasum -a 256` gives
    `6f8ad2760f12e1c2bf4830e4f21d0cc6c18baea6de431262274172de85cc5ee2`.
* **Quarter-point lines** are priced as half a bet at each neighbouring line. **A price must be a
  price:** a feed value between −100 and +100 is treated as no price.
* **The reference is the rule's own total.** The entry is priced at *x* = 0: on a half-point line the
  under wins 56.6%, worth +5.8% at −115 and +8.1% at −110. The value reaches zero at about −131, so
  **inside the −115 cap the expected-value gate cannot reject a bet at the rule's own number.** The
  gate stays, because the model does reject an under offered 2 points below the reference.
* **What the model is for.** For every game the odds feed lists, each run logs the highest total any
  logged book offers the under at, at −115 or better (`best_line`, `best_line_under`,
  `best_line_book`), and its value against the reference (`ev_best_line`). A game that neither
  Pinnacle nor DraftKings quotes has no rule price and no reference; its best line is still logged.
  Logging only. The alert names the best number only when the model prices it above the rule's own
  quote, since a half point more at a worse price can be worth less.

### 2. Definitions the earlier text left open

* **The rule's price** comes from the first of Pinnacle, then DraftKings, that quotes both a total and
  an under price. (A book that lists the total without an under price used to block the fallback.)
  ESPN's feed is used only when The Odds API returns nothing. The ledger's `line_src` names the
  source, and the scorer reports signals by source.
* **Wind** is the average forecast wind over the kickoff hour and the next three hours, put on the
  station scale with the frozen calibration. `STRATEGY.md` called this "kickoff wind". The historical
  evidence used the same four-hour average.
* **Lead time is counted in calendar days:** the kickoff's Eastern date minus the date of the run on
  the Mac's clock (Pacific), 1 to 3 inclusive. A run on the day of the game never qualifies.
* **Rule HT's first eligible kickoff** is 2026-10-07 00:00 UTC, which is Tuesday, Oct 6 at 5:00 PM
  Pacific.
* **Both tests end with the 2027 season's title game** (January 2028). Later games don't count.

### 3. Rule HT: the alert and the entry are the same row

* **The entry** is unchanged: the game's last logged quote before kickoff.
* **The alert** now fires on the last scheduled run before kickoff, as `STRATEGY.md` always said. The
  code used "kickoff within 4.5 hours", which for a 4:00 PM Pacific kickoff also matched the 11:30 AM
  run; that alert then blocked the 3:30 PM one, and the scorer graded the 3:30 PM quote. It now
  alerts only when no scheduled run falls between now and kickoff.
* **Manual snapshots count.** A quote logged by hand after the last scheduled run is a logged quote,
  so it becomes the entry.
* **A missed run** (the Mac was asleep) leaves the previous logged quote as the entry.

### 4. The decisions

* **Rule B** is decided after 40 signals or the end of the 2026 regular season, whichever is later:
  keep only if mean CLV > 0 with a 95% interval above zero.
  * The 2026 regular season ends with Army–Navy on Dec 12, 2026.
  * The decision uses the signals that kicked off by that horizon (the later of Dec 12, 2026 and the
    40th signal's kickoff). Later signals never enter it, so a later run of the scorer prints the same
    result.
  * If the test ends with fewer than 40 settled signals, the result is inconclusive.
* **Rule HT** is decided once, after the 2027 season's title game; the scorer treats Feb 1, 2028 as
  that date. The test against "the break-even of the prices taken" is exact when prices differ: the
  chance of at least that many wins when each bet wins with its own break-even probability. With one
  price for every bet it is the ordinary binomial test. (The code used the average break-even.)
  * **"Drop at or below break-even"** is read at the prices taken: drop when the bets, together, won
    nothing (ROI of zero or below). Promote and drop then can't contradict the ROI printed beside
    them.
* **Before its horizon** each decision prints as an interim read: the numbers and which criteria they
  meet, and no verdict.
* **ROI** is units won per bet placed, for both rules. A push counts as a bet.
* **A game is graded once the schedule marks it completed.** The feed scores a game that was never
  played 0–0; those rows are counted and not graded. A cancelled game can't hold a decision open.

### 5. What the scorer now enforces

`scripts/score_forward.py` had no version filter and no end date; the audit got it to count a 2028
game. It now counts only rows written under a registered version (`cfb-v1-2026-09-28`,
`cfb-v2-2026-09-28`, `cfb-v3-2026-09-28`), logged before kickoff, inside the test window. It counts
every excluded row by its first failing reason and prints each one with `--list-excluded`, and it
computes each decision and labels it **interim** or **final**.

### 6. Records

The same as nfl-weather's amendment 5, section 6: `rules_version = cfb-v3-2026-09-28`; the new ledger
columns `ref_total`, `best_line`, `best_line_under`, `best_line_book`, `ev_best_line`, `quote_utc`,
`quote_update`, `wx_hash`, `wx_fetched_utc` and `wx_wind_dir` (logged for a later crosswind study; no
rule uses it); every forecast kept under its content hash; a row in
`data/forward/runs.csv` for every alert run, finished or failed at any stage, with keys blanked from
any error text; unmatched team names recorded; close capture retried when a slot comes back
incomplete. The one-time ledger rewrite writes the old rows back character for character and keeps
the ledger as it stood beside it (`ledger.before-cfb-v3-2026-09-28.csv`).

**Rule HT's alert follows the Mac's own clock.** The last scheduled run before kickoff is worked out
from the four run times as wall-clock times in the Mac's time zone, so it stays right across a clock
change.

### 7. Known limits, stated up front

* **Rule B's primary close can be the entry itself.** The primary CLV compares the entry with the
  last logged quote before kickoff. When the signal fires on the last run, those are the same row and
  the CLV is 0 by construction; when the Mac misses runs, the "close" can be hours old. The scorer now
  counts both cases. Whether to require a later quote is an open owner decision, and amendment 2's
  captured close is reported alongside either way.
* **Earlier rows.** Amendment 2 and Rule HT were committed before any signal, but after some
  snapshots of the same games had been logged. No Rule B or Rule HT signal exists in any of them.
* **Rule HT's 2027 threshold** isn't frozen yet. It will be computed over FBS-involved games (owner
  decision, Sep 28) and registered by a dated amendment before 2027 Week 0.

Variants under forward test: still **2**.

## Amendment 4 (2026-09-29 Pacific, before the first eligible game on Oct 1; no Rule B or Rule HT signal logged)

A review of the scorer, made after amendment 3 was merged (pull request 50), found readings the earlier
text left open. Every one is settled here, before any outcome exists. **No trigger, gate, price cap,
stake or metric changes.** Section 6 settles which quote is Rule B's primary close, the question
amendment 3 (section 7) left to the owner. The rules version stays `cfb-v3-2026-09-28`, because the
board behaves exactly as before; only `scripts/score_forward.py` changes. Where this amendment and
any earlier text differ, this one applies. The last section lists every earlier sentence it changes. A
final review before registration (Sep 29) added sections 10 to 12 and that list. Registered by the hub
on the owner's standing instruction of September 29, 2026 (the hub decides questions of how the tests
are graded and reports them; money, and any rule's trigger, gate or price cap, stay the owner's). The
registering commit is the merge of pull request 59. The owner can change any reading here by a dated
amendment made before the first outcome it would affect.

### 1. A bet whose game was moved or never played is void

* A bet is **void** when its game did not kick off within 24 hours of the kickoff time on its entry
  row (the game was postponed, moved or cancelled), or when the schedule still shows no result 30 days
  after that kickoff. The entry row's kickoff is its `start_utc`; the scorer compares it with the
  schedule's kickoff for the same game id.
* A void bet is counted and listed by reason. It is not graded: it is left out of the record, the
  units, the CLV and the count toward 40.
* A sportsbook voids the same bets. Wind rules meet this case more than most, because hurricanes
  postpone games. The review's example: a signal logged for Oct 10 on a game played Oct 31 under the
  same game id was graded at the Oct 10 line.
* A result that lands after day 30 brings the bet back: it is graded like any other bet from then on.
  If a decision on its horizon is already recorded, the record stands, and the scorer prints the fresh
  computation beside it (section 3).

### 2. A bet still waiting for its result holds its decision open

* A bet whose game has no result yet, and that is not void, is **pending**. The scorer prints how many
  bets are pending.
* No decision is final while any bet that kicked off on or before the decision's horizon is pending.
* This replaces amendment 3's reading of "a cancelled game can't hold a decision open", which treated
  a game with no score a week after kickoff as never played. Under that reading a score that arrived
  late could change a decision after it was made. A cancelled game now holds a decision open for at
  most 30 days, and then it is void.

### 3. A decision is made once, and written down

* The first time a decision is final, the scorer appends it to `data/forward/decisions.csv`: its
  decision id, the rule, the horizon, the time it was decided (UTC), the number of bets, every number
  the decision used, the verdict, the positions in the ledger of the rows that entered it (1 is the
  first row after the header): the entry rows, and for Rule B the later quotes used as closes (section
  6), and a fingerprint of those rows.
* **The decision id is fixed:** `CFB_RULE_B` for Rule B and `CFB_RULE_HT` for Rule HT. The record is
  looked up by its decision id, never by the wording of its label.
* **The fingerprint** is the sha256 of the ledger's header line followed by each row that entered the
  decision, exactly as written in the ledger and in the order of the ledger, each line followed by a
  newline (`\n`), the whole encoded as UTF-8. (If a row was ever written across several lines, the
  rows are taken as the scorer reads them instead.) Every later run recomputes the fingerprint from the
  rows at the recorded positions and, if it differs, prints a warning that the ledger has changed since
  the decision was recorded. The recorded decision still stands.
* Every later run prints the recorded decision, even when no bet is settled any more. If a fresh
  computation on the same horizon would now come out differently (a corrected score, say), the scorer
  prints both and says the recorded one stands. A preview with `--now` shows a recorded decision only
  if it was decided at or before the preview's date.
* **Only a real run writes the record.** That is a run of the scorer on the live ledger
  (`data/forward/ledger.csv`), on the real clock, reading the default cfbfastR schedule when the
  current season's schedule file (`schedules_<season>.parquet`) was refreshed in the last 2 days; the
  other seasons' files don't count. Every alert run refreshes the current season's schedule. The hub's
  daily check-in runs the scorer this way, so the first check-in after a decision becomes final
  records it. A scorer is live only if its `data/forward` folder, with links resolved, is inside its
  own project folder. In every other case the scorer prints the decision and says why it wasn't
  recorded:
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
  cfb-weather/decisions.csv`). A record made since the last nightly copy exists only on the Mac until
  that night: if it is lost before then, neither the file nor a copy holds it, and the next real run
  decides it again.

### 4. Horizons are dates

* The dates are as registered in amendment 3: Rule B is decided after the later of Dec 12, 2026 (the
  end of the regular season) and the 40th settled signal's kickoff; Rule HT after Feb 1, 2028.
* A game dated after a test's end (Feb 1, 2028) never counts, whatever season label it carries. The
  scorer labels a season from July to June, so a game in February 2028 used to count as 2027.

### 5. What a quote is, and Rule HT's entry

* A **quote** is a posted total with a valid under price (at or beyond 100 either side of zero,
  amendment 3, section 1).
* Rule HT's entry is the game's last logged quote before kickoff in that sense (for each listing,
  section 10). A later row with a total and no usable under price is not a quote, so it doesn't replace
  the entry. (The scorer used to take such a row as the game's last quote, and the bet vanished.)
* Pushes are left out of Rule HT's exact test, and count in the denominator of ROI (a push is a bet
  placed that won nothing).

### 6. Rule B's primary close (settles amendment 3, section 7)

* Rule B's primary close is **the last logged quote before kickoff that is later than the entry row.**
  The quote comes from the entry's own listing (section 10).
* If there is none, the close captured by amendment 2 is used. **This replaces amendment 2's "What it
  can't change" for Rule B's primary close:** when no later quote was logged, the captured close now
  enters the primary CLV, and so the keep/drop decision. Everywhere else the captured close stays
  descriptive, as amendment 2 says.
* If there is neither, the bet has no primary close: it is counted, and left out of the CLV.
* The scorer prints the book behind the entry and the book behind the close. They can differ: a
  Pinnacle entry can close at DraftKings when Pinnacle takes its line down.
* Why: when a signal fires on the last run before kickoff, the entry row was also the last logged
  quote, so its CLV was 0 by construction. The entry is never its own close now.
* Amendment 3, section 7 listed this as an open owner decision. The hub settled it on September 29,
  2026 under the owner's standing instruction; the owner can change it by a dated amendment before the
  first Rule B signal settles.

### 7. "Not kept"

* A Rule B result of **not kept** means no money goes on the rule. It can stay on paper for 2027 only
  by a dated amendment before 2027 Week 0.

### 8. Rule HT by price source

* The scorer reports Rule HT's bets by price source (Pinnacle, DraftKings, ESPN), each with its record
  and units, as amendment 3, section 2 says. This is reporting only: the decision uses every bet.

### 9. Corrections to amendment 3's quoted numbers (2026-09-29)

Amendment 3's text is left as written. Two numbers in section 1 were off:

* The value at the rule's own number reaches zero at **about −130** (−130.5 on a half-point line,
  −130.3 on a whole number), not "about −131". The conclusion stands: inside the −115 cap the gate
  can't reject a bet at the rule's own number.
* At −115 the model rejects an under **from 1.5 points below the reference** (reference 42.5, under
  41: −0.6%), not only "2 points below". One point below still passes (+1.2%).

### 10. A postponed game that signals again is two listings

* A game's rows are grouped into **listings** by the kickoff on each row (`start_utc`): rows whose
  kickoffs are within 24 hours of each other are one listing. Precisely: in order of each row's
  kickoff, a row whose kickoff is more than 24 hours after the first kickoff of the current listing
  starts a new listing.
* A listing's entry is its earliest signal: for Rule B its earliest `SIGNAL` row, whose primary close
  comes from the same listing (section 6). For Rule HT, whose entry is the last quote (section 5), it
  is the listing's last quote, when that quote is a signal.
* A listing whose entry's kickoff is more than 24 hours from the game's actual kickoff is void
  (section 1). The listing that matches the actual kickoff is graded like any other bet. If two
  listings are each within 24 hours of the actual kickoff, the nearer one is graded (the later one if
  they are equally near) and the other is void. If the schedule gives no kickoff for the game, the
  check for moved games is off, and the listing with the latest kickoff is the one graded.
* So a game is still graded once, and a game postponed by more than a day that signals again on its
  new date is graded at its new entry. Before this reading the second signal was dropped as a repeat
  of the first, which was void, so the game was never a bet.

### 11. "Before kickoff"

* "Before kickoff" means before the earlier of the kickoff on the row and the kickoff in the schedule,
  in both scorers and for every use: which rows count, the entries, the last quotes and the
  later-quote closes. Here the row's kickoff is its `start_utc`, and the uses are which rows count,
  Rule B's entry, Rule HT's last quote and Rule B's later-quote close.
* Why: a row carries the kickoff cfbfastR showed when it was logged. When a game is moved earlier
  before the schedule shows it, a quote logged after the real kickoff could otherwise enter Rule HT or
  close Rule B at an in-play price.

### 12. A closing-line decision needs 20 closes

* A closing-line decision needs closing lines. If fewer than 20 of the bets in a decision have a
  primary close, the result is **inconclusive**, and the scorer says why. This applies to Rule B. It
  does not apply to Rule HT, which is graded on results. The result is inconclusive in the same sense
  as when the test ends with fewer than 40 settled signals (amendment 3, section 4).
* Whenever some bets in a decision have no primary close, the scorer prints how many.

### What this amendment replaces

Each earlier sentence below is quoted as registered; the section of this amendment named beside it
applies instead.

* Amendment 1: "Entry is at each game's last logged quote before kickoff." Amendment 2: "Rule HT
  (amendment 1) keeps its entry at the last logged quote before kickoff." Amendment 3, section 3: "The
  entry is unchanged: the game's last logged quote before kickoff." A quote is a total with a valid
  under price (section 5), each listing has its own last quote (section 10), and before kickoff is
  before the earlier kickoff (section 11).
* Amendment 3, section 3: "A quote logged by hand after the last scheduled run is a logged quote, so it
  becomes the entry." It does so only if it is a quote (section 5), in the listing that is graded
  (section 10), logged before the earlier kickoff (section 11).
* Amendment 2: "The primary CLV compares the entry with the last alert quote before kickoff."
  Amendment 3, section 7: "The primary CLV compares the entry with the last logged quote before
  kickoff." and "Whether to require a later quote is an open owner decision". Replaced by section 6:
  the last quote of the same listing logged later than the entry row, else the captured close.
* Amendment 2: "It doesn't change which bets count, the primary CLV, or the keep/drop decision." For
  Rule B's primary close only, section 6 lets the captured close enter the primary CLV, and so the
  decision.
* Amendment 3, section 1: "The value reaches zero at about −131" and "because the model does reject an
  under offered 2 points below the reference". Corrected by section 9.
* Amendment 3, section 4: "keep only if mean CLV > 0 with a 95% interval above zero". With fewer than
  20 signals that have a primary close, the result is inconclusive whatever its numbers (section 12).
* Amendment 3, section 4: "the later of Dec 12, 2026 and the 40th signal's kickoff". It is the 40th
  settled signal's kickoff: a void signal doesn't count (sections 1 and 4).
* Amendment 3, section 4: "The decision uses the signals that kicked off by that horizon". Void signals
  among them are left out (section 1), and the decision waits while any of them is pending (section 2).
* Amendment 3, section 4: "Later signals never enter it, so a later run of the scorer prints the same
  result." A later run prints the recorded decision, and a fresh computation beside it when that now
  differs (section 3).
* Amendment 3, section 4: "A cancelled game can't hold a decision open." A game with no score holds
  its decision open for at most 30 days, and then it is void (section 2).
* Amendment 3, section 5: "logged before kickoff, inside the test window". Before kickoff now means
  before the earlier of the row's kickoff and the schedule's (section 11).

Variants under forward test: still **2**. Nfl-weather amendment 6 and cfb-weather amendment 4 test
nothing and leave the running variant count unchanged. On the day of registration it is **271**, so
the multiple-testing bar is p < 0.000185 (`strategy-research/README.md`, `STATUS.md`).

## Amendment 5 (2026-09-29 Pacific, before the first eligible game on Oct 1; no Rule B or Rule HT signal logged)

This amendment makes the 95% interval behind Rule B's keep test the wider of two: the plain interval, and one
grouped by game day. The closing-line moves of windy games on the same day move together, so the plain interval
alone keeps a rule with no edge too often, and the grouped interval alone can come out too narrow. It also
registers which feed event gives a game's captured close, closes three small gaps in the decision record, and
registers that the nightly copy of the record never loses a line. **No trigger, gate, price cap or stake
changes.** The rules version stays `cfb-v3-2026-09-28`, because the board behaves exactly as before; only
`scripts/score_forward.py`, `scripts/capture_close.py` and `ops/sync_ledgers.sh` change. Where this amendment and
any earlier text differ, this one applies, and the last section lists every earlier sentence it changes.
Registered by the hub on the owner's standing instruction of September 29, 2026 (the hub decides questions of how
the tests are graded and reports them; money, and any rule's trigger, gate or price cap, stay the owner's). The
registering commit is the merge of pull request 64. The owner can change any reading here by a dated amendment
made before the first outcome it would affect.

### 1. The keep test's interval is the wider of two

* **Why.** The paper-to-money study (`strategy-research/README.md`, "The paper-to-money gate", and
  `strategy-research/simulate_decisions.py`) found that the closing-line moves of windy games on the same day move
  together. The plain interval treats every signal as independent, so the registered keep test keeps a rule with no
  edge more often than the 2.5% it is meant to. The first draft of this amendment grouped the interval by game day
  instead. Its second review showed that the grouped interval can come out narrower than the plain one, even of zero
  width, and the simulation showed that with fully independent signals it keeps a rule with no edge slightly more
  often than the plain one, because 40 signals fall on only 10 to 16 game days. Neither interval is safe alone, so
  the registered interval is the wider of the two.
  [`strategy-research/keep_test_check.py`](../strategy-research/keep_test_check.py) measures all three.
* **The reading.** Rule B's keep test uses mean CLV with a 95% interval:
  * the mean m is the plain mean of the CLVs of the n signals in the decision that have a primary close
    (amendment 4, section 6);
  * the plain half-width is t(0.975, n - 1) x s / sqrt(n), where s is the sample standard deviation of those CLVs
    and t(0.975, n - 1) is the 97.5th percentile of Student's t with n - 1 degrees of freedom;
  * the grouped half-width is t(0.975, G - 1) x the grouped standard error. The signals are grouped by the calendar
    date of the game's actual kickoff in Eastern time (America/New_York), the kickoff in the schedule (when the
    schedule gives no kickoff for a game, as amendment 4, section 10 allows, the kickoff on its entry row); G is the
    number of days with at least one such signal; for each day g, s_g is the sum over that day's signals of
    (CLV - m); the variance of the mean is (G / (G - 1)) x (the sum over days of s_g squared) / n squared, and the
    grouped standard error is its square root; t(0.975, G - 1) is the 97.5th percentile of Student's t with G - 1
    degrees of freedom;
  * **the registered interval is m plus or minus the larger of the two half-widths;**
  * with fewer than 2 game days, or fewer than 2 signals, there is no interval and the result is inconclusive;
  * everything else is unchanged: the keep test's other criteria, the 20-close limit, void and pending bets, the
    horizon and the decision record.
  * Rule HT is graded on results, not CLV, and doesn't change.
* **The plain multiplier.** Until now the scorer computed the plain interval as m plus or minus 1.96 x s / sqrt(n).
  The plain half-width here uses t(0.975, n - 1) instead, which is wider (2.09 at 20 signals, 2.02 at 40), so the
  plain half of the registered test is slightly stricter than the interval the scorer printed before. The last
  section names this change.
* **What the scorer shows.** It prints the registered interval and says which of the two it is ("the wider is the
  grouped one, over G game days" or "the wider is the plain one"; "the two are equally wide" when they are, as when
  every game day has one signal), and it prints both. The decision record stores the registered bounds (`ci_low`,
  `ci_high`), both half-widths (`plain_half_width`, `grouped_half_width`) and G (`game_days`). No decision has been
  recorded, so no record has to change.
* **What it measured.** `keep_test_check.py` reuses the study's model: the open-to-close moves of 426 windy games
  (2016–25), the same-day dependence it estimated, and the dates of the windiest FBS games of 2016–25 replayed onto
  2026 from Oct 1, aligned on Army–Navy. Run with seed 29: 40,000 simulated paths per case, 40 signals per path, no
  edge unless stated, at 25, 40 and 55 signals a season. "Plain" below is the interval as the scorer had it (1.96);
  "grouped" is the grouped interval alone, as the first draft had it.
  * Realistic dependence (same day 0.11; no season effect was found): the registered test keeps a rule with no edge
    2.8%, 2.9% and 3.0% of the time (plain 5.2%, 5.8% and 6.3%; grouped 3.6%, 3.7% and 4.0%).
  * Stress dependence (same day 0.17): 3.3%, 3.4% and 3.8% (plain 6.6%, 7.3% and 8.7%; grouped 3.8%, 3.9% and
    4.4%).
  * With no model at all, whole historical days resampled: 2.6% (plain 4.6%, grouped 3.1%).
  * Independent signals: 1.9%, 1.7% and 1.7% (plain 2.8%, 2.7% and 2.7%; grouped 3.3%, 3.1% and 3.4%).
  * It also keeps a real edge less often. At 40 signals a season, realistic case: 30% if the true edge is half the
    historical line move and 78% if it is the full move (plain 45% and 90%; grouped 32% and 79%).
  * In every case the registered test keeps a rule with no edge no more often than the plain or the grouped
    interval alone, as it must: a path it keeps, both of the others keep. The script checks this path by
    path. Run with seed 6 instead, the registered test's rates agree with these to within 0.3 points.
* **Where the grouped interval alone fell short, the registered test holds.**
  * Day totals that balance: 40 signals on 4 game days, 10 a day, whose CLVs add up to the same amount on each day
    (two of +5.5 and eight of -1.0) give a grouped interval of zero width, +0.30 to +0.30, which the first draft
    would have kept. The plain half-width is the wider there, so the registered interval is -0.54 to +1.14, which
    includes zero, and Rule B is not kept.
  * Independent signals: the grouped interval alone keeps a no-edge rule 3.1 to 3.4% of the time, more than the
    plain interval's 2.7 to 2.8%; the registered test keeps it 1.7 to 1.9% of the time, less than either.
* **Known limit.** The registered test's remaining error is stated plainly: about 2.8 to 3.0% in the realistic
  case and up to 3.8% in the stress case, against the intended 2.5%. It does not fix the NFL, where the swing is
  season-wide and one or two seasons can't measure it (nfl-weather amendment 7); in college football the study
  found no season-wide swing.
* **The money gate is a separate question.** When real money goes in (`STRATEGY.md`, "Stake") is the owner's
  decision, and the owner has not chosen a gate. Nothing here changes it.
* **Variants.** This changes how a test is graded, not a betting rule: 0 variants.

### 2. Which feed event gives a game's captured close

Pull request 62 (merged Sep 29) made close capture take one entry of the odds feed per game. This registers the
rule it implements, with one change. A **feed event** is one event in the odds feed (The Odds API): a game as the
feed lists it, with its own start time and books. It is not a listing in the sense of amendment 4, section 10,
which groups a game's ledger rows.

* **The rule.** When a kickoff slot is due, the feed can list a game's two teams more than once (a relisted
  event, or a rematch such as a conference title game):
  * a feed event counts for a game only if it has the game's home and away teams and starts within 6 hours of the
    scheduled kickoff; a feed event with no readable start time never counts;
  * among those, a feed event priced at Pinnacle comes first, then one priced at DraftKings, then one priced at
    neither (a feed event's price is the first of Pinnacle, then DraftKings, that quotes both a total and an under
    price, as on the board, amendment 3, section 2); among the feed events left, the one starting nearest the
    scheduled kickoff is taken;
  * the game's row in `data/forward/closes.csv` carries that feed event's price: its book, total and prices.
* **The change.** When two or more feed events are equally near the kickoff and are all priced at the same book
  with the same quote (the same total and the same under and over prices), they are the same game listed twice,
  and the first in the feed is taken. Until now that case was a tie and the close was lost.
* **Still a tie.** Equally near feed events whose quotes differ, or that are priced at neither book, are a tie,
  and none is taken.
* **A game with no usable feed event** (a tie, no feed event within 6 hours, no readable start time, or not in the
  feed at all) has no captured close for that slot. Its row is written with the price columns blank, and the slot
  is tried once more if the next run still falls 2 to 20 minutes before kickoff (at most two calls per slot). What
  is still missing then stays missing: it is reported, never imputed.
* **A feed that returns nothing usable** (no key, the quota floor, an error, or no priced feed event whose two teams
  it knows) writes nothing and counts no try, as before; the next run inside the window tries again.
* **Nothing else changes:** the book recorded, the 2 to 20 minute window, at most two calls per slot, the quota
  floor, the columns of `closes.csv` and the shape of the state file. In the offline replay made for this
  amendment (scratch scripts, not kept in the repository), every cached real feed (3 responses; 184 runs over their
  kickoff slots, 633 rows) and 8 made-up ordinary slot sequences, run through the script as it was before this
  amendment and as it is now, gave byte-identical `closes.csv`, state file and printout. A reviewer's separate
  replay, over other slots, also found the rows byte-identical.

### 3. Three gaps in the decision record, and a copy that never loses a line

A review after amendment 4 found three rare cases where the code did not do what section 3 of amendment 4 says,
and the reviews of this amendment found that the nightly copy itself could lose a line. Each is settled here.

* **A time with no time zone.** A recorded time with no time zone (a spreadsheet can re-save
  `2026-12-13T08:00:00Z` as `2026-12-13 08:00:00`) couldn't be compared with the scorer's times, and it stopped the
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
  neither the file nor the copy holds it, and the next real run decides it again, as amendment 4 says. Normally that
  is a decision recorded and lost on the same day. But while the nightly copy holds the file back because a
  published line in it has changed (a hand edit, say, or a spreadsheet re-saving the file with other line endings,
  which the scorer still reads), the scorer goes on recording and nothing new is published, so every decision
  recorded until the hub puts that line back exists only on the Mac. A changed line is not restored by the scorer
  (the file holds a decision under that id): the nightly copy keeps the published line, says so every night, and the
  hub puts the published line back by hand.
* **A copy that can't be read.** Because the copy is now read on every run, amendment 4's rule for a damaged copy
  applies whether or not the file is there: while the copy can't be read, nothing is recorded, and the scorer says
  so on every run. Each decision on a line of the copy that can still be read (the same test as for a damaged file)
  is held: if the file doesn't hold it, it is printed from the copy as recorded, never decided again, and it is not
  restored from a damaged copy (the hub can restore it by hand). The nightly copy never replaces a published copy
  that is itself cut or does not start with the record's header line: it keeps it, and the line it prints says that
  the published copy is damaged, not the file. An empty copy is replaced as a first copy is published. A copy with
  any other damaged line is replaced only by a file that holds every line of it. Otherwise the hub replaces a
  damaged published copy by hand with a commit to the ledgers branch, and recording resumes once the copy can be
  read. When the file is missing, it is first restored by hand from a readable earlier copy in the branch's history
  (`git log origin/ledgers -- cfb-weather/decisions.csv`), as amendment 4 says.
* **A blank line is skipped.** A blank line, or a line of only spaces, anywhere in `decisions.csv` or in its
  published copy is not a record and is not damage: the scorer skips it when it reads the file or the copy, never
  counts it as a decision and never copies it when it restores, and the nightly copy ignores blank lines on both
  sides when it compares the file with the published copy and publishes the file without them.

### What this amendment replaces

Each earlier sentence below is quoted as registered; the section of this amendment named beside it applies
instead.

* `STRATEGY.md`, Rule B, "Decision": "Keep only if average CLV > 0 with a 95% interval above zero". The 95%
  interval is the wider of the plain one and the one grouped by game day, and with fewer than 2 game days (or 2
  signals) there is none and the result is inconclusive (section 1).
* `STRATEGY.md`, Rule B, "Decision", the dated note of amendment 4: "a lost record is restored from its nightly copy
  on the ledgers branch, never decided again unless it is lost before that night's copy is made". This holds, and
  now also for a decision lost from a file that still exists: the nightly copy never publishes a file that has lost
  a published line. That night's copy now means the next nightly copy that publishes the file: while the nightly
  copy holds the file back because a published line in it has changed, the first one after the hub puts that line
  back (section 3). A new dated note in `STRATEGY.md` says so.
* Amendment 3, section 4: "keep only if mean CLV > 0 with a 95% interval above zero." The same (section 1). Its
  plain half-width uses Student's t on n - 1 degrees of freedom; until now the scorer computed the plain interval
  with 1.96, which is narrower (section 1).
* Amendment 4, section 12: "If fewer than 20 of the bets in a decision have a primary close, the result is
  inconclusive, and the scorer says why." A decision whose signals with a primary close kicked off on fewer than 2
  game days is inconclusive too (section 1).
* Amendment 2: "It makes one Odds API call per kickoff slot, 2–20 minutes before kickoff, and records the total and
  prices for every FBS game in the slot in `data/forward/closes.csv`." Each game's row comes from the one feed event
  it takes, and a game with no usable feed event has none (section 2).
* Amendment 2: "The source is Pinnacle when it lists the game, else DraftKings, the same as the board." Where close
  capture and the board differ (a feed event more than 6 hours from the kickoff, two feed events priced at the same
  book at different times, or equally near feed events with different quotes), section 2 gives the close.
* Amendment 4, section 3: "If `decisions.csv` can't be read (a half-written line, wherever it was cut; a line
  without exactly its 10 fields; a missing header; an empty file; a decision id, verdict or numbers the scorer
  doesn't know or can't print), the scorer says so, records nothing until the file is repaired or restored from the
  ledgers branch, and still prints the scores." A time that can't be read as a UTC time is damage too, and the
  decisions that can still be read are printed as recorded (section 3).
* Amendment 4, section 3: "When the live record is missing, a real run reads the copy (`origin/ledgers`, as this
  checkout last fetched it; the scorer never fetches), restores the file from it and prints what it restored, before
  it decides anything." A single decision missing from a file that still exists is restored from the copy too, by
  appending the copy's own line (section 3).
* Amendment 4, section 3: "The record is copied to the ledgers branch every night." The nightly copy publishes
  `decisions.csv` only when the file ends with a line break, starts with the record's header line and holds every
  line of the copy already published; otherwise it keeps the published copy (or, before the first copy, publishes
  none) and says so (section 3).
* Amendment 4, section 3: "A lost record is restored from that copy; it is never decided again." This holds, and now
  also for a line lost from a file that still exists: the published copy never loses a line, so a decision that
  was ever published is never decided again; the one case left is a decision recorded since the last nightly copy
  that published the file and lost before the next one (section 3).
* Amendment 4, section 3: "A record made since the last nightly copy exists only on the Mac until that night: if it
  is lost before then, neither the file nor a copy holds it, and the next real run decides it again." A record made
  since the last nightly copy that published the file exists only on the Mac until the next one that publishes it:
  normally that night, but while the nightly copy holds the file back because a published line in it has changed,
  not before the hub puts that line back (section 3).
* Amendment 4, section 3: "A copy that is there but can't be read (a damaged file was copied before the damage was
  repaired) stops recording, as a damaged file does, until the file is restored from a readable earlier copy in the
  branch's history (`git log origin/ledgers -- cfb-weather/decisions.csv`)." This now applies whether or not the file
  is there; the decisions on the copy's readable lines are printed from it as recorded; recording resumes once the
  copy can be read again; and the nightly copy never replaces a copy that is cut or does not start with the
  record's header line, and replaces any other damaged copy only with a file that holds every line of it, so
  otherwise the hub replaces it by hand (section 3).

Variants under forward test: still **2**. This amendment tests nothing and leaves the running variant count
unchanged: on the day of registration it is **273**, so the multiple-testing bar is p < 0.000183
(`strategy-research/README.md`, `STATUS.md`).

## Amendment 6 (registered 2026-09-30 Pacific, before the first eligible game on Oct 1, 2026, 5:00 PM Pacific)

**Registered** on September 30, 2026 (Pacific) by the hub, on the owner's standing instruction of September 29, 2026, by the merge of pull request 90. State of the ledger at registration, from its counts only: one Rule B signal had been logged (Texas Tech at Colorado, Saturday, October 3, at the 7:30 AM Pacific run of September 30), pending, with no close captured and no outcome known; no Rule HT signal. This amendment does not change that signal's entry; it changes only which captured close may grade it, and none exists yet. The running variant count on this day is 288 (it adds none). Pull request 86 (the reading of Rule HT for a game whose kickoff time isn't set) becomes amendment 7 if the hub registers it.

An independent audit of the scorer (Astra's audit 3, Sep 29, late evening; issue 88) found two places where
`scripts/score_forward.py` does not do what the registered text says. **This amendment repairs two registered rules
and changes no threshold, gate or decision rule:** no trigger, price cap, stake, metric, horizon or decision
criterion changes. Section 1 enforces amendment 2's capture window and amendment 4's listings (section 10) for the
captured close; section 2 enforces amendment 4's test end (section 4). The rules version stays
`cfb-v3-2026-09-28`, because the board behaves exactly as before; only `scripts/score_forward.py` changes, and none
of the files shared with nfl-weather does. Nfl-weather amendment 8 makes the same repair of the NFL scorer. Where
this amendment and any earlier text differ, this one applies; the last section lists every earlier sentence it
changes. To be registered by the hub on the owner's standing instruction of September 29, 2026 (the hub decides
questions of how the tests are graded and reports them; money, and any rule's trigger, gate or price cap, stay the
owner's). The owner can change any reading here by a dated amendment made before the first outcome it would affect.

### 1. A captured close belongs to the listing it was captured for

* **What went wrong.** The scorer kept one captured close per game id (the last row of `data/forward/closes.csv`)
  and dropped its capture time and kickoff before it joined the close to the bets. A game that was postponed and
  signalled again (two listings, amendment 4, section 10) could then take, for its new listing, the close captured
  for the old one. The audit's case: game 999 listed for Oct 10, 19:00 UTC, whose only captured close (a total of
  40) was captured Oct 10 at 18:50 UTC; the game was postponed to Oct 31 and signalled again, at 60. The Oct 10
  listing was correctly void, but the Oct 31 listing was graded against the Oct 10 close, as its primary close
  (amendment 4, section 6): mean CLV +20.00.
* **The reading.** A bet's captured close is a row of `closes.csv` for its game whose capture time (`capture_utc`)
  is from 20 minutes to 2 minutes before the kickoff of the listing graded, both ends included. That kickoff is the
  earlier of the kickoff on the listing's last row logged before kickoff and the kickoff in the schedule: the bound
  amendment 4, section 11 gives "before kickoff". The listing's last row is the latest-logged ledger row of that
  listing (amendment 4, section 10) that counts, whatever it shows (a quote, a signal or neither); for a listing
  the board logged once, it is the entry row. Every row that counts was logged before the earlier of its own
  kickoff and the schedule's (amendment 4, section 11), so that row was logged before the game's kickoff in the
  schedule, and the kickoff it sets is never later than the schedule's; a row logged after the real kickoff never
  counts, so it can't set the listing's kickoff. The window is amendment 2's ("2–20 minutes before kickoff"), with
  both ends included as `scripts/capture_close.py` applies it: it calls the odds feed when a kickoff is from 2 to
  20 minutes away, both ends included. Among a game's rows inside the window, the last in the file is taken, as
  before (a retried slot writes its row again).
* **Otherwise the bet has no captured close,** and it is counted as missing, never imputed:
  * for Rule B's primary close, when no later quote was logged (amendment 4, section 6), the bet has no primary
    close: it is counted, and left out of the CLV;
  * for the secondary measure (amendment 2), for both rules, it is one of the bets without a captured close;
  * the scorer prints, for each rule, how many bets had a captured close refused and which games ("close captured
    outside the window for this listing"), and `--list-excluded` prints each refused capture with its capture
    time, the kickoff it was captured for and the kickoff of the listing graded.
* **A capture outside the window is set aside when another inside it is used.** A game can have several captures:
  a retry of its slot, a capture for another listing of a postponed game, or one for each kickoff of a game moved
  on game day. The ones outside the window for the listing graded are set aside, and the one inside it is used.
  For example, a slot captured at 18:50 for a 19:00 kickoff whose retry's reply landed at 18:58:30 (inside the
  last 2 minutes): the retry is set aside, even though it is last in the file, and the 18:50 capture is used. When
  any capture is set aside, the scorer prints, for each rule, how many bets had captures set aside, how many
  captures, and which games; `--list-excluded` prints each, as for a refused capture. When none is, the report is
  as it was.
* **Examples.** For a listing whose kickoff is 19:00 UTC: a close captured at 18:50 is used; one captured at 18:58
  or 18:40 (exactly 2 or 20 minutes before) is used; one captured at 18:39 (21 minutes before) is not; one captured
  at 18:59 or after kickoff is not. A game moved earlier, from 19:00 on the entry row to 16:00 in the schedule: a
  close captured at 18:50 is not used (the game was in play), and one captured at 15:50 is. A game moved later on
  game day, from 16:00 on the entry row to 21:00 in the schedule, with a row logged at 15:00 that shows 21:00: the
  listing's kickoff is 21:00, so the true close, captured at 20:50, is used, and one captured at 15:50 for the old
  kickoff is set aside. If instead the schedule gives 16:00 (the game was played then) and the row that shows
  21:00 was logged at 16:30, that row doesn't count (it was logged after the schedule's kickoff), and a capture at
  20:50 is not used. The audit's postponed game: the
  close captured on Oct 10 is not the Oct 31 listing's close, and a close captured Oct 31 at 18:50 is, wherever it
  sits in the file.
* **Known limits, stated up front.**
  * The capture time college football records is when the feed's reply arrived, a few seconds after the run's
    clock found the slot due. The runs are 15 minutes apart, so unless the Mac missed a run, a slot's first call is
    more than 5 minutes before kickoff, and only a retry can fall in the last 2 minutes; a call whose reply lands a
    few seconds inside them is refused, or set aside when the slot's earlier capture is inside the window, and
    either way counted and named.
  * A game moved later, by less than a day, with no row of its listing logged after the move: the listing's
    kickoff is still the earlier one its rows show, so a close captured for that earlier kickoff is used, and one
    captured just before the new kickoff is set aside, counted and named. That close is a price from before the
    kickoff the listing was logged for: never in play (it is at least 2 minutes before the schedule's kickoff too)
    and never another listing's. It is the last price before a kickoff that was then moved, not the price just
    before the game was played. The later-quote close (amendment 4, section 6) is unaffected, and once any row of
    the listing is logged after the move, the true close is used.
  * An alternative the hub may choose at registration instead: measure the window from the kickoff in the schedule
    whenever the schedule has one (from the listing's last row only when it has none). That grades a game moved
    later on its true close even with no row after the move. Its cost on college football: the schedule shows a
    placeholder kickoff at 00:00 Eastern for a game whose time is not yet set (draft pull request 86), and a
    placeholder that is still in the schedule would then refuse every genuine close captured for the real kickoff.
    This draft's reading takes the listing's kickoff from the same "before kickoff" bound that decides which rows
    count, so however pull request 86, once registered, reads a placeholder for that bound applies to the captured
    close too. This draft keeps the brief's reading, the earlier of the two.
* **Nothing else changes:** the entry, the later-quote close, which rows count, void and pending bets, the 20-close
  limit (a refused close is a missing one), the interval, the horizons and the decision record.

### 2. The test's end is judged on the schedule's kickoff as well as the entry row's

* **What went wrong.** The scorer judged the test's end on the kickoff on the entry row (`start_utc`) alone. The
  audit's case: a Rule HT game whose entry row gives a kickoff of Jan 31, 2028, 23:00 UTC, and whose final schedule
  gives Feb 1, 2028, 20:00 UTC. That is 21 hours later, so the bet is not void, and it was settled and printed in
  the FINAL Rule HT decision (record 1–0–0, STAY ON PAPER, with `--now 2028-02-02`). Amendment 4, section 4 says a
  game dated after the test's end never counts.
* **The reading.** A ledger row counts only if the kickoff on the row and the game's kickoff in the schedule are
  both before Feb 1, 2028, 00:00 UTC. A row either of whose kickoffs is on or after it is excluded as "after the
  2027 season", counted and listed like any other excluded row. This applies to both rules.
* **With no kickoff in the schedule** (the game has no schedule row, or the schedule has no kickoff for it), the
  row's own kickoff decides, as before. Amendment 4, section 10 allows such a schedule, and the scorer already says
  when its schedule has no kickoff times.
* **Unchanged, stated up front.** This reads only the test's end. The test's start (Oct 1, 2026, and Rule HT's
  2026 Week 6, Oct 7, 00:00 UTC) and Rule B's horizon (the later of Dec 12, 2026 and the 40th settled signal's
  kickoff) are still judged on the kickoff on the entry row, as the scorer has done since amendment 3: a game moved
  across one of them by less than a day falls on the side its entry row gives. The owner or the hub can read them
  the same way by a dated amendment before the first outcome it would affect.

### 3. Variants and records

* **Variants.** This repairs how two registered rules are applied, not a betting rule: 0 variants.
* **Tests.** `tests/test_close_listing.py` runs the audit's two cases (each fails on the scorer as it was on `main`
  on Sep 29, commit 30444ec, and passes now), a close captured inside the window (used, at both ends), one 21
  minutes before kickoff and one inside the last 2 minutes (not used), one captured for the earlier listing of a
  postponed game (not used for the later listing, also after rows on the new date), a game moved later on game day
  (its true close used once a row shows the new kickoff; without one, the declared limit, with the other capture
  set aside and named), a row logged after the real kickoff (it never sets the listing's kickoff, so an in-play
  capture is refused), a retry inside the last 2 minutes (set aside, counted and listed), and the committed 2025
  rehearsal ledger (`output/tables/rehearsal_2025.csv`), whose printed report is unchanged byte for byte: with no
  captured closes, it is the committed `output/rehearsal_2025.log` except its record line (a `--now` run is a
  preview); with a made-up capture for every game, it changes only where a capture falls outside the window, and
  every such game is named.
  All inputs are synthetic or 2025; no 2026 price or result is read.
* **The note for `STRATEGY.md`** (Rule B's and Rule HT's "Decision" rows, dated on registration): *Amendment 6:* a
  captured close counts only for the listing it was captured for, 2 to 20 minutes before that listing's kickoff,
  else it is missing; a game whose kickoff in the schedule is on or after Feb 1, 2028 never counts.

### What this amendment replaces

Each earlier sentence below is quoted as registered; the section of this amendment named beside it applies
instead.

* Amendment 2: "`score_forward.py` reports CLV against that captured close, next to the primary measure." A close
  counts only when it was captured 2 to 20 minutes before the kickoff of the listing graded (section 1).
* Amendment 2: "It also reports how many bets have no captured close." A bet whose game's captured close falls
  outside that window has none, and the scorer also says how many were refused, and which (section 1).
* Amendment 4, section 6: "If there is none, the close captured by amendment 2 is used." It is the close captured
  for the entry's own listing, inside the window; otherwise the bet has no primary close (section 1).
* Amendment 3, section 5: "logged before kickoff, inside the test window". Inside the test window now means that the
  kickoff on the row and the kickoff in the schedule are both before Feb 1, 2028 (section 2).
* Amendment 4, section 4: "A game dated after a test's end (Feb 1, 2028) never counts, whatever season label it
  carries." A game is dated after the test's end when the kickoff on its row or its kickoff in the schedule is on or
  after Feb 1, 2028; with no kickoff in the schedule, the row's alone (section 2).

Variants under forward test: still **2**. This amendment tests nothing and leaves the running variant count
unchanged: on the day it was written it is **288**, so the multiple-testing bar is p < 0.000174 (`STATUS.md`); the
hub restates the count on the day of registration.

## Amendment 7 (DRAFT, not registered: written 2026-09-30 Pacific for the hub to register, before Rule HT's first eligible game on Oct 6, 2026, 5:00 PM Pacific; no Rule HT signal logged; Rule B's forward test began Oct 1, so Rule B games may already have been played at registration)

**DRAFT.** This text is not in force. The hub registers it before Oct 6, 2026, 5:00 PM Pacific, by: replacing this
paragraph and the heading's "DRAFT, not registered" with the date of registration; re-checking the ledger counts in
section 4 on the nightly copy current that day (counts only, no price or result); stating, for Rule B, how many
signals were logged by then and that none is affected, from the scorer's count of ledger games whose schedule
kickoff is the placeholder (section 2), which must show 0 completed games; filling in the variant count at the end;
and adding the notes in section 5 to `STRATEGY.md`, dated. Until then the board, the alert and the scorer on `main`
behave as amendments 1 to 6 say. This draft was written as amendment 6; amendment 6 was then registered for
the captured close and the test's end (pull request 90), so this is amendment 7, and "amendment 6" below means the
registered one.

Issue #69, found while building the dashboard (Sep 29): cfbfastR gives a game whose kickoff time isn't set yet a
placeholder of midnight Eastern on its date, and the board took that placeholder as Rule HT's kickoff. This amendment
reads Rule HT for such a game: **it is not eligible until its kickoff time is set.** For a game logged with a set
time and without the time-not-set flag nothing changes: no trigger, threshold, price cap, stake or metric changes,
and every such game that would have signalled before still signals. Rule B's trigger doesn't change. One reading
applies to the grading of both rules: when the schedule the scorer reads shows the placeholder, "before kickoff" is
bounded by the row's own kickoff and the placeholder + 30 hours instead of by the placeholder (section 2). Amendment
6 measures a listing's captured close from that same bound, so the reading applies there too (section 2, "The
captured close"). It changes nothing for a game whose schedule shows a time. CFB Rule B's forward test began Oct 1,
2026, so by registration Rule B games may have been played; the reading affects one only if the schedule shows the
placeholder for it, which the hub checks (above). The rules version stays `cfb-v3-2026-09-28`: the ledger's columns
don't change, and a row logged under this amendment is told apart by its Rule HT status `time_tbd`, which no earlier
row carries. Only `cfbweather/board.py` (one status), `scripts/alerts.py` (one notice) and `scripts/score_forward.py`
(which rows are Rule HT quotes, and the before-kickoff bound for a placeholder in the schedule, which amendment 6
also uses for the captured close) change; none of the files shared with nfl-weather does. Where this amendment and
any earlier text differ, this one applies; the last section lists every earlier sentence it changes, and the related
ones it leaves as they are. To be registered by the hub on the owner's standing instruction of September 29, 2026
(the hub decides questions of how the tests are graded and reports them; money, and any rule's trigger, gate or price
cap, stay the owner's). The owner can change any reading here by a dated amendment made before the first outcome it
would affect.

### 1. What went wrong

* **The placeholder.** A game with no kickoff time yet is listed at 00:00 Eastern on its date, with cfbfastR's
  `start_time_tbd` flag set. For Rule B that flag already gives the status `time_tbd`: no time, no forecast, no
  signal. Rule HT prices only the posted total and the under, so it could signal on such a game.
* **The alert.** Rule HT alerts on the last scheduled run before kickoff (amendment 3, section 3). Before a midnight
  placeholder that is the 7:30 PM Pacific run the evening before the game, which told you to take that number.
* **The entry.** The board shows only games that kick off after now, so it stops logging the game once the
  placeholder has passed. The scorer's last logged quote before kickoff (before the earlier of the row's and the
  schedule's kickoff, amendment 4, section 11) was then that evening's row: a number many hours before the game,
  not the latest one, which is what the rule claims to bet.
* **The same through the schedule.** The scorer also reads each game's kickoff from the schedule as it stands when
  it scores. A schedule can still carry the placeholder after the game is played: Utah State–Robert Morris, played
  Aug 31, 2024, is still flagged, at 00:00 Eastern, in the final schedule (section 4). Read as a kickoff, that
  placeholder is "the earlier kickoff" (amendment 4, section 11), so every row logged on game day after 00:00
  Eastern, with the real time set, would be dropped as logged at or after kickoff, and the entry would fall back to
  a row from the evening before.

### 2. The reading

* **No kickoff time set.** A game has no kickoff time set when the schedule flags its start time as not set
  (`start_time_tbd`, the same flag behind Rule B's `time_tbd`) or when its kickoff is exactly 00:00 Eastern, the
  placeholder (`board.no_kickoff_time`). cfbfastR lists a real midnight-Eastern kickoff, a Hawaii night game, at
  11:59 PM; in 2016–25 no game kicked off at 00:00 Eastern without the flag, and in the 2026 schedule as built on
  Sep 28 all 320 flagged games sit at 00:00 Eastern and no other game does. That listing is a habit of the feed, not
  a guarantee (section 3, known limits).
* **Not eligible until its time is set.** A row logged while the game has no kickoff time set is never graded for Rule
  HT (it still counts as the listing's last quote when it comes last: see the entry, below). When such a game would
  otherwise signal, its Rule HT status is `time_tbd` (otherwise the status is what it was: `below_threshold`,
  `no_price` or `price_too_high`).
* **The alert.** A game with no kickoff time set gets no Rule HT alert. On the last scheduled run before its
  placeholder (the run that used to alert), if it would otherwise signal, one notice says it is not eligible because
  the schedule marks its kickoff time as not set, that there is no bet, and that if the time is set it is eligible
  from the next run. It is sent once, and it is not counted as a signal in `data/forward/runs.csv`.
* **The entry.** Rule HT's entry is the listing's last quote before kickoff (amendment 4, sections 5, 10 and 11),
  **when it was logged with a kickoff time set**, and a bet when it is a signal. The last quote is taken over every
  quote, timed or not. A listing whose last quote was logged with no kickoff time set is not a bet, even when an
  earlier quote logged with a time signalled (the time was unset again, or the flag was turned on at a real time):
  that earlier quote was not the latest number, and no alert was sent for it. When a game has more than one listing,
  the listing graded (the one nearest the actual kickoff, amendment 4, section 10) is chosen among every listing whose
  last quote signalled or would have, timed or not; a listing whose last quote has no time set is then not a bet, and
  the others stay void, as they would be without this amendment. The scorer counts every Rule HT quote logged with no
  kickoff time set, and every listing whose last quote was logged with no kickoff time set and would have signalled
  ("its last quote was logged with no kickoff time set, and would have signalled", with game ids); `--list-excluded`
  prints the rows. None is graded.
* **A placeholder in the schedule the scorer reads.** Here a placeholder is only a schedule kickoff at exactly 00:00
  Eastern, whether or not the flag is set. A flag on any other time leaves that time as the schedule's kickoff: it is
  still the best record of when the game began, and dropping it would let a row logged after a kickoff that moved
  earlier count, or let a game moved by days go unvoided. (All 320 flagged 2026 games and Utah State–Robert Morris
  sit at 00:00 Eastern.) A placeholder changes one thing, "before kickoff" (amendment 4, section 11): for that game a
  row counts only if it was logged before its own kickoff and before the placeholder + 30 hours (about 06:00 Eastern
  the day after the game's date), instead of before the placeholder. Everything else keeps the placeholder as the
  schedule's kickoff: a bet is void when its entry row's kickoff is more than 24 hours from it, the listing graded is
  the one nearest it (amendment 4, sections 1 and 10), the game day is its Eastern date (amendment 5, section 1), and
  the test's end is judged on it as well as on the row's kickoff (amendment 6, section 2; a placeholder is never
  later than a real kickoff on the same date, and the row's own kickoff is checked too). So a game postponed to a
  later date that has no time set yet, or moved to the day before, is void as before, and a row logged after the
  placeholder + 30 hours never counts. This reading is the scorer's, for both rules; for a game whose schedule shows
  a time nothing changes. The scorer always prints how many ledger games have the placeholder in the schedule, split
  into completed games and games not yet played, with their game ids, and `--list-excluded` lists them.
* **The captured close (a reading of amendment 6, section 1).** Amendment 6 counts a captured close for a listing
  only when it was captured 2 to 20 minutes before "the earlier of the kickoff on the listing's last row logged
  before kickoff and the kickoff in the schedule: the bound amendment 4, section 11 gives "before kickoff"". When
  the schedule shows the placeholder, that kickoff is the bound this section gives instead: the kickoff on the
  listing's last row logged before kickoff, and never later than the placeholder + 30 hours. Read against the
  placeholder itself, the window would be 11:40 to 11:58 PM Eastern the evening before the game's date, and every
  genuine close captured on game day would be refused; amendment 6 names that cost and says that however this
  amendment reads the placeholder for "before kickoff" applies to the captured close too. For example, a game dated
  Saturday, Oct 17, 2026, whose schedule shows the placeholder (04:00 UTC, Oct 17) and whose last row logged before
  kickoff shows 19:30 UTC: a close captured at 19:20 UTC is used; one captured at 03:50 UTC (11:50 PM Eastern the
  evening before) is refused, counted and named; so is one captured at 19:29 or later (the last 2 minutes, or in play
  by that row's kickoff). As amendment 6 says, a capture for another listing of the game is not this listing's
  close, and no row logged after the placeholder + 30 hours counts, so the listing's kickoff is never later than
  that. Nothing else in amendment 6 changes. The gap in section 3 applies here too: where the schedule shows only the
  placeholder, the row's kickoff is the only record of when the game began.
* **A time set late.** Every alert run refreshes the schedule, and each ledger row carries what the schedule said
  when the row was logged. A game whose time is set is eligible from the first run that logs it with that time,
  and its alert fires on the last scheduled run before the real kickoff, like any other game's. The placeholder
  and a kickoff later that day are less than 24 hours apart, so the rows before and after are one listing
  (amendment 4, section 10); a kickoff more than 24 hours after the placeholder (a Hawaii night game) is not
  (section 3, known limits).
* **A time never set.** A game still without a time when its placeholder passes leaves the board, so its last quote
  was logged with no time set and it is not a bet. The scorer counts it, with its game id, as "its last quote was
  logged with no kickoff time set, and would have signalled". If its time is set after the placeholder has passed (on
  game day), the game comes back on the next run and is eligible from then.
* **Rows logged before this amendment's code ran.** The board then logged such a row as `SIGNAL`. The scorer knows
  it by what the row itself carries: its weather source `time_tbd` (the schedule's flag, at an outdoor venue) or its
  kickoff at exactly 00:00 Eastern. A row logged under this amendment is also known by its status `time_tbd`. The
  scorer never uses the schedule as it is now to decide whether a row had a time: that would be information from
  after the row was logged. One such row is read as timed: a row for a game at a dome or with no venue (weather
  source `indoor` or `no_venue`, not `time_tbd`) whose schedule flag was set while it showed a real time other than
  00:00 Eastern. That takes all three at once: a flag left set on a real time (section 3, known limits), a dome or no
  venue, and a row logged before this amendment's code ran.
* **Rule B's trigger is unchanged; the schedule reading above applies to its grading.** A game with no kickoff time
  has no forecast and can't signal.

### 3. Why this reading

* **Nothing from after the real kickoff, where the schedule shows it.** Whether a row counts depends only on what that
  row carried when it was logged, and a row with a time counts only before the earlier of its kickoff and the
  schedule's (amendment 4, section 11), where the schedule's is any time but the placeholder, flagged or not. Where
  the schedule shows only the placeholder, nothing in it says when the game began, so the bound is the row's own
  kickoff, and never later than the placeholder + 30 hours. **The one gap**, where main is safer: a game whose
  schedule shows the placeholder after it was played (once in 2021–25, section 4) and that kicked off before a counted
  row's own kickoff could have a row logged after the real kickoff count, as Rule HT's entry or Rule B's close, or have
  a close captured after the real kickoff used (amendment 6 measures its window from the same bound). Main has no
  lookahead there, because it drops every row logged after 00:00 Eastern (and refuses every capture but one from the
  evening before); this reading trades main's common
  failure (a stale pre-game entry, section 1) for lookahead in this rare case. So the scorer lists every completed
  game with the placeholder in the schedule by game id (section 2), and the hub checks each one by hand, against when
  the game really kicked off, before any decision is made.
* **Noon Eastern on the game's date** (the other reading the issue named) can. If a game's time is never set, the
  schedule's kickoff stays the placeholder, so nothing tells the scorer when the game really began. A game that
  kicked off before the last scheduled run before noon Eastern (7:30 AM Pacific, 10:30 AM Eastern; an early game
  abroad, say) would be alerted and graded at an in-play number. For an evening game, noon makes the entry 7 to 10
  hours early: the midnight problem, smaller.
* **Leaving it as it is** grades a number from the evening before, and the alert tells you to bet it.
* **What it costs.** A game whose time is set only after the last scheduled run before its real kickoff, or never, is
  not a bet, and neither is a listing whose time was unset again before its last quote. Section 4 says what is known
  about how often; the ledger will measure it. Whether a quote had a time is fixed when it is logged, from what the
  row carried, so the exclusion can't select on outcomes. The eligibility reading can cost a bet, never add one: a
  listing is a bet only when its last quote, over every quote, is a signal logged with a time, and the listing graded
  is chosen among every listing that signalled or would have (section 2), so every bet under it is one the same rows
  would make without it, graded on the same listing. The schedule reading only adds rows that main dropped as logged
  after the placeholder (for Rule HT a later timed quote, which can become the entry; for Rule B a game-day signal or
  close) and, through amendment 6's window, the game-day captured close it refused, and it voids exactly what the
  placeholder voided before.
* **Known limits.**
  * A game whose flag stays set after it has a real time is not eligible either (its rows carry the flag). The
    committed tables show this once in 2016–25 (Oregon–UCLA, Nov 21, 2020, flagged with a 12:30 PM Pacific kickoff;
    closing total 61.5, below that season's threshold of 65.69). It can cost a bet, never add one. The scorer keeps
    such a schedule's time as the kickoff.
  * The midnight reading can hit a real kickoff. In 2006–14 the committed tables hold 17 games that kicked off at
    exactly 00:00 Eastern without the flag, all Hawai'i home games (12 at Aloha Stadium; the other 5 have no venue
    in the table). cfbfastR has listed such kickoffs at 11:59 PM since, but that is a habit, not a guarantee. A real
    kickoff listed at 00:00 Eastern is read as no time set, and that game is not eligible at all.
  * Hawai'i–New Mexico, Oct 17, 2026, has no time set in the 2026 schedule as read on Sep 30 (its placeholder is
    04:00 UTC, Oct 17). If its time is set at 00:00 Eastern, it is not eligible, for good. If it is set at 7:00 PM
    Hawaii time (01:00 Eastern, 05:00 UTC Oct 18, 25 hours after the placeholder), the rows logged with that time
    are a second listing (amendment 4, section 10), graded as usual once the schedule shows that time; the rows
    logged before it are a listing whose last quote was logged with no time set, and if that quote would have
    signalled the scorer counts the game as "its last quote was logged with no kickoff time set", although the game
    was logged with one. If the schedule the
    scorer reads still showed the placeholder, the timed listing's kickoff would be more than 24 hours from it and
    the bet void.
  * So either way this reading can cost a bet, never add one, and the count of listings whose last quote had no time
    set can include a game that was logged with one.

### 4. How often (issue #69, task 1)

* **What the repository can't say.** The committed tables hold each game's schedule as it stood when they were
  built, after the season (`data/processed/games.parquet`, rebuilt Sep 28, 2026), not when each kickoff time was
  set. No committed file records a schedule as it stood before a game. So the number of FBS games in 2021–25 that
  still had no time 1, 2 or 3 days before they were played, and how many of those closed at or above the season's
  threshold, can't be counted from the repository.
* **What it can say.**
  * Final schedules, 2021–25: of 4,467 FBS-involved games, 1 was still flagged as having no time after it was
    played: Utah State–Robert Morris (FCS), dated Aug 31, 2024, which has no closing total in the table. None of the
    337 games at or above their season's threshold (2021 66.79, 2022 65.68, 2023 64.19, 2024 62.02, 2025 62.22, by
    `board.ht_threshold` on the committed table) was flagged.
  * The 2026 schedule as built on Sep 28: every FBS-involved game through Friday, Oct 9 had a time; the 320 without
    one start on Saturday, Oct 10 (Week 6), 12 days ahead, where 37 of 46 had none. That fits times being set 6 to
    12 days ahead; it can't show how many are still unset 1 to 3 days out.
  * The 2026 forward-test ledger, as the `origin/ledgers` copy of 2026-09-29 06:45 UTC holds it: 238 rows on 60
    games kicking off Oct 1–6, logged 3 to 8 days ahead. None has a midnight-Eastern kickoff or the weather source
    `time_tbd`. It was read for these counts only; no price or result in it was read. The hub re-checks these counts
    at registration on the copy current that day, counts only, together with the number of Rule B signals logged and
    the scorer's count of ledger games whose schedule kickoff is the placeholder (section 2), which must show 0
    completed games, so that no known outcome is affected.
* **So the rate is not measured yet.** The scorer will measure it from Week 6: it counts every Rule HT quote logged
  with no kickoff time set, and every listing whose last quote was logged with no time set and would have
  signalled.

**Variants.** This changes how a game is read, not a betting rule: 0 variants.

**Tests.** `tests/test_amendment7.py` runs the board's gate, the notice, and the scorer on games whose time is set
late, never set, or unset again, and on a placeholder in the schedule the scorer reads. For the captured close
(section 2): a placeholder game's close captured 10 minutes before the kickoff its rows carry is used (Rule B's
primary close, Rule HT's secondary); one captured 10 minutes before the placeholder, the evening before, is refused
or set aside; one in the last 2 minutes, at or after the row's kickoff, or 21 minutes before is refused; a postponed
game's later listing never takes the close captured for the earlier one; and no capture after the placeholder + 30
hours is used. The captured-close cases fail when the window is measured from the placeholder. All inputs are
synthetic; no 2026 price or result is read.

### 5. Notes for `STRATEGY.md`

The hub adds these notes at registration, each dated with the date of registration (DATE below), at the end of the
row named, as amendments 3 to 6 did.

* Rule HT, "Trigger": "*Amendment 7 (DATE):* a game with no kickoff time set (cfbfastR's time-not-set flag, or its
  placeholder kickoff of 00:00 Eastern) is not eligible until its time is set."
* Rule HT, "Entry": "*Amendment 7 (DATE):* the entry is the listing's last quote, when it was logged with a kickoff
  time set; a listing whose last quote was logged with no time set is not a bet (the scorer counts it), and a game
  with no time set gets no alert, only a notice on the last scheduled run before its placeholder that it isn't
  eligible."
* Rule HT, "Decision": "*Amendment 7 (DATE):* the entry is the last quote with a valid under price, when it was logged
  with a kickoff time set; when the schedule shows cfbfastR's placeholder (00:00 Eastern), before kickoff is before
  the row's kickoff and the placeholder + 30 hours, and a listing's captured close is measured from that kickoff."
* Rule B, "Decision": "*Amendment 7 (DATE):* when the schedule shows cfbfastR's placeholder (00:00 Eastern), before
  kickoff (11) is before the row's kickoff and the placeholder + 30 hours, and a listing's captured close is measured
  from that kickoff (amendment 6); the check for moved games (1), the listing graded (10), the game day and the test's
  end still use the placeholder."

### What this amendment replaces

Each earlier sentence below is quoted as registered; the section of this amendment named beside it applies
instead.

* `STRATEGY.md`, Rule HT, "Trigger": "FBS game on the board, kicking off from 2026 Week 6 (first kickoff 2026-10-07
  00:00 UTC) through the 2027 national title game." A game with no kickoff time set is not eligible until its time
  is set (section 2).
* `STRATEGY.md`, Rule HT, "Entry": "The game's **last logged quote before kickoff**, which is the latest number
  available, at that total and under price." Amendment 1: "Entry is at each game's last logged quote before
  kickoff." Amendment 2: "Rule HT (amendment 1) keeps its entry at the last logged quote before kickoff." Amendment
  3, section 3: "**The entry** is unchanged: the game's last logged quote before kickoff." Amendment 4, section 5:
  "Rule HT's entry is the game's last logged quote before kickoff in that sense (for each listing, section 10)." The
  entry is the listing's last quote, when it was logged with a kickoff time set; otherwise the listing is not a bet
  (section 2).
* `STRATEGY.md`, Rule HT, "Entry", the note of amendment 4: "a quote is a posted total with a valid under price, so a
  later row with no usable under price doesn't replace the entry." Amendment 4, section 5: "A **quote** is a posted
  total with a valid under price (at or beyond 100 either side of zero, amendment 3, section 1)." Both stand: a
  quote logged with no kickoff time set is still a quote, so it replaces the entry when it comes last. It is never
  graded, and the listing is then not a bet (section 2).
* `STRATEGY.md`, Rule HT, "Decision", the note of amendment 4: "the entry is the last quote with a valid under
  price". The entry is the last quote with a valid under price, when it was logged with a kickoff time set;
  otherwise the listing is not a bet (section 2).
* Amendment 4, section 10: "For Rule HT, whose entry is the last quote (section 5), it is the listing's last quote,
  when that quote is a signal." It is the listing's last quote, when that quote is a signal logged with a kickoff
  time set; a listing whose last quote was logged with no time set is not a bet, and is counted when that quote
  would have signalled (section 2).
* `STRATEGY.md`, Rule HT, "Entry": "The alert fires on the last scheduled run before kickoff (*amendment 3* fixed the
  code to do exactly that; a quote logged by hand after it becomes the entry)." Amendment 3, section 3: "**The
  alert** now fires on the last scheduled run before kickoff, as `STRATEGY.md` always said." and "A quote logged by
  hand after the last scheduled run is a logged quote, so it becomes the entry." For a game with no kickoff time set
  there is no Rule HT alert, only the notice that it is not eligible; a quote logged by hand is the last quote as
  before, and the entry only if it was logged with a kickoff time set (section 2).
* Amendment 3, section 3: "**A missed run** (the Mac was asleep) leaves the previous logged quote as the entry." It
  leaves the previous logged quote as the last quote, and as the entry only if it was logged with a kickoff time
  set; otherwise the listing is not a bet (section 2).
* Amendment 4, section 11: "\"Before kickoff\" means before the earlier of the kickoff on the row and the kickoff in
  the schedule, in both scorers and for every use: which rows count, the entries, the last quotes and the
  later-quote closes." `STRATEGY.md`, Rule B, "Decision", the note of amendment 4: "\"before kickoff\" is before the
  earlier of the row's kickoff and the schedule's (11)". `STRATEGY.md`, Rule HT, "Decision", the note of amendment
  4: "before kickoff is before the earlier of the row's and the schedule's kickoff". In this project's scorer, when
  the schedule's kickoff is cfbfastR's placeholder (exactly 00:00 Eastern), before kickoff is before the earlier of
  the row's kickoff and the placeholder + 30 hours (section 2). A schedule kickoff at any other time, flagged or not,
  is read as before.
* Amendment 6, section 1: "That kickoff is the earlier of the kickoff on the listing's last row logged before kickoff
  and the kickoff in the schedule: the bound amendment 4, section 11 gives "before kickoff"." When the schedule's
  kickoff is the placeholder, that kickoff is the earlier of the kickoff on the listing's last row logged before
  kickoff and the placeholder + 30 hours: the bound section 2 gives "before kickoff" (section 2, "The captured
  close"). Amendment 6, section 1: "Every row that counts was logged before the earlier of its own kickoff and the
  schedule's (amendment 4, section 11), so that row was logged before the game's kickoff in the schedule, and the
  kickoff it sets is never later than the schedule's; a row logged after the real kickoff never counts, so it can't
  set the listing's kickoff." It stands where the schedule shows a time. Where it shows the placeholder, every row
  that counts was logged before its own kickoff and before the placeholder + 30 hours, and the kickoff it sets is
  never later than either; whether a row was logged after the real kickoff is then known only from the row's own
  kickoff (section 3, the one gap).

These related sentences are **unchanged**: the placeholder is still the schedule's kickoff for each of them
(section 2).

* Amendment 4, section 1: "A bet is **void** when its game did not kick off within 24 hours of the kickoff time on
  its entry row (the game was postponed, moved or cancelled), or when the schedule still shows no result 30 days
  after that kickoff." and "The entry row's kickoff is its `start_utc`; the scorer compares it with the schedule's
  kickoff for the same game id."
* `STRATEGY.md`, Rule B, "Decision", the note of amendment 4: "a bet whose game moved more than 24 hours, or has no
  result 30 days after kickoff, is void and not graded (1)" and "a postponed game that signals again is two
  listings, and the one that matches the actual kickoff is graded (10)".
* `STRATEGY.md`, Rule B, "Decision", the note of amendment 5: "the grouped one groups the signals by the Eastern date
  of their game's kickoff". Amendment 5, section 1: "the kickoff in the schedule (when the schedule gives no kickoff
  for a game, as amendment 4, section 10 allows, the kickoff on its entry row)".
* `STRATEGY.md`, Rule HT, "Decision", the note of amendment 4: "a postponed game is graded on the listing that
  matches its actual kickoff".
* Amendment 6, section 2: "A ledger row counts only if the kickoff on the row and the game's kickoff in the schedule
  are both before Feb 1, 2028, 00:00 UTC." The placeholder is the schedule's kickoff here too.
* Amendment 6, section 1: "This draft's reading takes the listing's kickoff from the same "before kickoff" bound that
  decides which rows count, so however pull request 86, once registered, reads a placeholder for that bound applies
  to the captured close too." This amendment is pull request 86, and that is how it applies (section 2).
  `STRATEGY.md`, Rule B's and Rule HT's "Decision", the note of amendment 6: "a captured close counts only for the
  listing it was captured for, 2 to 20 minutes before that listing's kickoff, else it is missing". For a game whose
  schedule shows the placeholder, that listing's kickoff is the one section 2 gives.

Variants under forward test: still **2**. This amendment tests nothing and leaves the running variant count
unchanged: on the day of registration it is **N**, so the multiple-testing bar is p < 0.05 / N (the hub fills in N
from `STATUS.md`; 288 when this draft was written, p < 0.000174; `strategy-research/README.md`, `STATUS.md`).
