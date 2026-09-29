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
