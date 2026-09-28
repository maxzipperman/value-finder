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
