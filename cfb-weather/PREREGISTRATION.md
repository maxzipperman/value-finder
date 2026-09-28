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
