# Pre-registered forward test: CFB weather unders, 2026 season

Locked 2026-09-28, before any CFB signal existed (the first board had no 15+ mph
forecasts). Rule, gates and decision criteria are in `STRATEGY.md` and fixed for
the season: Rule B (forecast wind ≥ 15 mph, 1–3 days out, under −115 or better,
positive EV at the offered line and price). Evaluation covers games from
Oct 1, 2026. Every board snapshot is appended to `data/forward/ledger.csv` with
`rules_version = cfb-v1-2026-09-28`. Variants under forward test: 1.

## Amendment 1 (2026-09-28, before the first eligible game on Oct 1; no Rule B signal logged)

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
* **For issue #4.** The same captured close is the "latest number available" that
  #4's rule would bet at, if #4 is registered before 2026 Week 6.
* Variants under forward test: still **1**.
