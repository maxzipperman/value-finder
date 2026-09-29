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

## Amendment 3 (2026-09-28, before the first eligible game on Oct 1; no Rule B or Rule HT signal logged)

An independent audit ([`reviews/2026-09-29-astra-audit.md`](../reviews/2026-09-29-astra-audit.md)) traced
each rule from trigger to scored result and found places where this file, `STRATEGY.md` and the code
disagreed. This amendment settles each one. **Both rules' triggers, price caps and grading are
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
* **The cohort is a committed file**, `data/processed/pricing_cohort.json`, with sha256
  `c49a6649c3f86ac1280ed488f675c14859b23073c1aa8e18aab63060b38bff67` (`board.PRICING_COHORT_SHA256`).
* **The reference is the rule's own total.** The entry is priced at *x* = 0: on a half-point line the
  under wins 56.6%, worth +5.8% at −115 and +8.1% at −110. The value reaches zero at about −131, so
  **inside the −115 cap the expected-value gate cannot reject a bet at the rule's own number.** The
  gate stays, because the model does reject an under offered 2 points below the reference.
* **What the model is for.** Each run logs the highest total any logged book offers the under at, at
  −115 or better (`best_line`, `best_line_under`, `best_line_book`), and its value against the
  reference (`ev_best_line`). Logging only.

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
* **Rule HT** is decided once, after the 2027 season, as registered. The test against "the break-even
  of the prices taken" is exact when prices differ: the chance of at least that many wins when each
  bet wins with its own break-even probability. With one price for every bet it is the ordinary
  binomial test. (The code used the average break-even.)
* **ROI** is units won per bet placed, for both rules. A push counts as a bet.

### 5. What the scorer now enforces

`scripts/score_forward.py` had no version filter and no end date; the audit got it to count a 2028
game. It now counts only rows written under a registered version (`cfb-v1-2026-09-28`,
`cfb-v2-2026-09-28`, `cfb-v3-2026-09-28`), logged before kickoff, inside the test window. It lists
every excluded row by reason, and it computes each decision and labels it **interim** or **final**.

### 6. Records

The same as nfl-weather's amendment 5, section 6: `rules_version = cfb-v3-2026-09-28`; the new ledger
columns `ref_total`, `best_line`, `best_line_under`, `best_line_book`, `ev_best_line`, `quote_utc`,
`quote_update`, `wx_hash`, `wx_fetched_utc` and `wx_wind_dir` (logged for a later crosswind study; no
rule uses it); every forecast kept under its content hash; a row in
`data/forward/runs.csv` for every run, finished or failed; unmatched team names recorded; close
capture retried when a slot comes back incomplete.

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
