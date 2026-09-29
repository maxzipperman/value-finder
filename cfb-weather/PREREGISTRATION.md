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
  line break) or does not start with the same header line, it keeps the published copy as it is, prints one line
  saying which project's record it did not publish and why, and syncs every other file as usual; it never fails the
  sync and never removes the published copy. A file that holds every published line, plus new ones, is published as
  before. So a decision that was ever published is never decided again: if the file loses it, the copy still holds
  it, and the next real run restores it. The one case left is a decision recorded and lost on the same day, before
  that night's copy: neither the file nor the copy holds it, and the next real run decides it again, as amendment 4
  says. A line that the file still holds under the same decision id but has changed is not restored by the scorer
  (the file holds a decision under that id): the nightly copy keeps the published line, says so every night, and the
  hub puts the published line back by hand.
* **A copy that can't be read.** Because the copy is now read on every run, amendment 4's rule for a damaged copy
  applies whether or not the file is there: while the copy can't be read, nothing is recorded, and the scorer says
  so on every run. Each decision on a line of the copy that can still be read (the same test as for a damaged file)
  is held: if the file doesn't hold it, it is printed from the copy as recorded, never decided again, and it is not
  restored from a damaged copy (the hub can restore it by hand). Recording resumes once the copy can be read again.
  The nightly copy replaces a damaged copy only with a file that holds every line of it (an empty copy, say); a copy
  with a damaged line the repaired file no longer holds is replaced by the hub by hand, with a commit to the ledgers
  branch. When the file is missing, it is first restored by hand from a readable earlier copy in the branch's
  history (`git log origin/ledgers -- cfb-weather/decisions.csv`), as amendment 4 says.

### What this amendment replaces

Each earlier sentence below is quoted as registered; the section of this amendment named beside it applies
instead.

* `STRATEGY.md`, Rule B, "Decision": "Keep only if average CLV > 0 with a 95% interval above zero". The 95%
  interval is the wider of the plain one and the one grouped by game day, and with fewer than 2 game days (or 2
  signals) there is none and the result is inconclusive (section 1).
* `STRATEGY.md`, Rule B, "Decision", the dated note of amendment 4: "a lost record is restored from its nightly copy
  on the ledgers branch, never decided again unless it is lost before that night's copy is made". This holds, and
  now also for a decision lost from a file that still exists: the nightly copy never publishes a file that has lost
  a published line (section 3). A new dated note in `STRATEGY.md` says so.
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
  `decisions.csv` only when it holds every line of the copy already published; otherwise it keeps the published
  copy and says so (section 3).
* Amendment 4, section 3: "A lost record is restored from that copy; it is never decided again." This holds, and now
  also for a line lost from a file that still exists: the published copy never loses a line, so a decision that
  was ever published is never decided again; the one case left is a decision recorded and lost on the same day,
  before that night's copy (section 3).
* Amendment 4, section 3: "A copy that is there but can't be read (a damaged file was copied before the damage was
  repaired) stops recording, as a damaged file does, until the file is restored from a readable earlier copy in the
  branch's history (`git log origin/ledgers -- cfb-weather/decisions.csv`)." This now applies whether or not the file
  is there; the decisions on the copy's readable lines are printed from it as recorded; recording resumes once the
  copy can be read again; and the nightly copy replaces a damaged copy only with a file that holds every line of
  it, so otherwise the hub replaces it by hand (section 3).

Variants under forward test: still **2**. This amendment tests nothing and leaves the running variant count
unchanged: on the day of registration it is **271**, so the multiple-testing bar is p < 0.000185
(`strategy-research/README.md`, `STATUS.md`).
