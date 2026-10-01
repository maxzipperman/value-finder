# Eligibility and close selection

Three statuses are distinct: scheduled-pregame eligible, actual-play certified, and conflicted/ineligible. Missing independent first-play evidence prevents certification, but does not alone reject an otherwise eligible scheduled close proxy. Known first play overrides scheduled timing for decisions and executions.

Every quote binds its immutable response hash, exact provider ID, canonical game, market and canonical side to its schedule observation. Independent final schedule is a retrospective safety guard unless its publication vintage is verified. Conflicting simultaneous observations for the exact quoted listing are quarantined; ID sorting cannot resolve them.

Close selection partitions by canonical game, book, market and side. Among eligible candidates, choose the latest returned snapshot, then freshest update timestamp, then smallest immutable quote ID. Prices, lines, CLV and results never enter ranking. If none qualifies, retain missing primary close and all diagnostics. When first play is verified, the close lead window is 5–20 minutes relative to it; otherwise use the provider kickoff with the independent safety guard.

Sides join by canonical team key (moneyline/spreads) or Over/Under (totals), never provider home/away position. Freshness remains 15 minutes at snapshot and 25 at decision; snapshot lag up to 10 minutes with gaps over five reported explicitly.

Paper listing voids, including postponement over 24 hours, remain attempted decisions. They do not erase historical opportunities or prove a sportsbook settlement. Multiple listings, cancellation and settlement mapping must be registered for the specific later study.

All 665 original MOS slots remain three-market fixed-time diagnostics. This is not a full live trigger or execution-delay replay. The 2026 season stays sealed; no outcome joins before recent coverage. Historical grades and significance rules are unchanged.

Execution acceptance: no send outside the authorized allowlist or without a durable reservation; no automatic resend of unresolved attempts; conservative accounting and halt when billing cannot be reconciled. Provider billing and unrelated shared-key activity are not guaranteed by the wrapper.
