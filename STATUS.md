# Value Finder: status

*Updated September 28, 2026*

Paper-only sports-betting research. The goal is to find prices the market gets wrong, and to prove each one on a pre-registered forward test graded on closing-line value (CLV) before any money goes in. Nothing in this repo places bets.

## Projects

| Folder | Question | Where it stands | Next step |
|---|---|---|---|
| [`nfl-weather/`](nfl-weather/) | Do NFL totals under-price wind? This extends the 2014 thesis. | Thesis replicated and audited. Rule B (forecast wind ≥ 15 mph → under) is pre-registered as playbook v2. Alerts run 4×/day. | Forward test is scored from Week 5 (Oct 8). |
| [`cfb-weather/`](cfb-weather/) | The same question for college football. | Rule B pre-registered (`cfb-v1-2026-09-28`). Rule HT (high totals → under, [#4](https://github.com/maxzipperman/value-finder/issues/4)) added as amendment 1 (`cfb-v2-2026-09-28`). Alerts run 4×/day. | Rule B is scored from Oct 1, Rule HT from Week 6 (Oct 7, 00:00 UTC). |
| [`sharp-markets/`](sharp-markets/) | Do Kalshi markets misprice relative to sharp books, or lag behind them? | Pipeline built (NBA first, sport-agnostic), 22 tests. H4a (Kalshi NFL totals vs wind, 2025): Kalshi moves with the books and doesn't lag. | NBA sample week for H1/H2 in the October 20K pilot (7,540 credits). H3 is waiting on licensed data. |
| [`strategy-research/`](strategy-research/) | Which "proven" strategies hold up in our data? | 109-variant screen plus 20 free pre-checks ([`prechecks.py`](strategy-research/prechecks.py)), 129 variants in all. Nothing passes a strict multiple-testing bar. Ranked ideas are in the backlog below. The Odds API plan and credit budget are in [`odds-api-credits.md`](strategy-research/odds-api-credits.md). | Work through the backlog. |
| [`thesis-research/`](thesis-research/) | What has been published since the thesis? | Literature review and feedback done ([page](https://claude.ai/artifact/ULdbHSkgLLcf6bzBGEppNU)). | Its crosswind idea is part of [#6](https://github.com/maxzipperman/value-finder/issues/6). |
| [`thesis/`](thesis/) | The 2014 thesis, as text. | Reference only. | None. |

## Forward tests (the scoreboard)

| Rule | Scored from | Signals so far | Decision |
|---|---|---|---|
| NFL Rule B: early wind under ([`STRATEGY.md`](nfl-weather/STRATEGY.md)) | Week 5, Oct 8, 2026 | 0 | After Week 18 or 40 signals: keep only if average CLV > 0 with a 95% interval above zero. |
| CFB Rule B: early wind under ([`STRATEGY.md`](cfb-weather/STRATEGY.md)) | Oct 1, 2026 | 0 | After 40 signals or the regular season, whichever is later, by the same test. |
| CFB Rule HT: high total → under ([`STRATEGY.md`](cfb-weather/STRATEGY.md)) | Week 6, Oct 7, 2026 (00:00 UTC) | 0 | Once, after the 2027 season: promote only if the win rate beats the break-even of the prices taken (one-sided p < 0.05) and ROI > 0. Drop at or below break-even. Otherwise keep on paper. |

Stake for Rule B: paper until 20 settled signals show positive average CLV. After that, 0.5% of bankroll at most. Rule HT stays on paper through 2027.

What to expect: in 2025 replays, NFL Rule B signalled 17 times in Weeks 5–18, CFB Rule B about 25–32 times, and Rule HT 34 times. Losing seasons are common even with a real edge. The NFL decision is unlikely to be conclusive this season. The 20-signal stake gate passes about half the time with no edge, so it isn't a reason to stake. See [what to expect](strategy-research/README.md#what-to-expect-this-season-added-september-28-2026).

## Waiting on you

1. **Odds API plan.** A free key is set in all three `.env` files (Sep 28). Live check:
   - Each alert call costs 1 credit, so the alerts use about 248 credits a month.
   - Pinnacle prices NCAAF on the free plan: 56 of 58 games.
   - [#15](https://github.com/maxzipperman/value-finder/issues/15) is done:
     - the free-tier guard (errors mean "no price" instead of a crash; manual runs stop when fewer than 60 credits are left; dry runs spend nothing);
     - 10-book logging with the best under price on each signal;
     - the B1 timestamp and budget fixes.
   - **Next purchase:** the 20K pilot for October ($30), per [`odds-api-credits.md`](strategy-research/odds-api-credits.md).
   - **Later:** one 5M month on March 1, 2027 ($119) for about 293K credits, once a data-use plan is committed. Add $119 only if the NBA sample week shows an edge.
2. **Close capture is live (Sep 28), as a secondary measure.** A launchd job (`com.valuefinder.closecapture`) runs every 15 minutes. It makes one Odds API call per kickoff slot, 2–20 minutes before kickoff, and records the close in `*/data/forward/closes.csv`.
   - Both scorers now also report CLV against that close. The registered primary CLV and the decision rules are unchanged: nfl-weather amendment 3, cfb-weather amendment 2, both dated before any signal.
   - Rule HT keeps its entry at the last logged quote; the scorer also reports the captured close for it.
   - Budget: about 385 credits in October, out of 500.
   - **Keep the Mac awake at kickoff.** A slot missed while it sleeps is reported as missing, never filled in.
3. **Phone alerts.** Subscribe to the `NTFY_TOPIC` from either `.env` in the ntfy app, if you haven't yet.

## Backlog

One issue per idea from [`strategy-research/`](strategy-research/README.md#ideas-to-add-ranked), in suggested order. Filter the [`idea` label](https://github.com/maxzipperman/value-finder/issues?q=is%3Aissue+label%3Aidea) on GitHub.

| # | Idea | Project | Needs |
|---|---|---|---|
| [#6](https://github.com/maxzipperman/value-finder/issues/6) | Crosswind vs headwind; derivative markets; forecast-run timing | nfl-weather | Crosswind: checked. It looks worse than along-field wind but isn't significant; a 2027 refinement at most. Derivative markets: the pre-check failed, so the pull is dropped. Forecast-run timing: deferred until there's an archive of when each forecast run was issued. |
| [#7](https://github.com/maxzipperman/value-finder/issues/7) | Home teams off a bye; Week 1 unders (paper) | nfl-weather | Nothing new |
| [#8](https://github.com/maxzipperman/value-finder/issues/8) | Price engine: beat the sharp fair line (most proven) | sharp-markets | Multi-book lines for 2020–26, 162K credits, plus NFL alternates, 46K credits, both in the March 5M month. Kalshi and Polymarket (free). |
| [#9](https://github.com/maxzipperman/value-finder/issues/9) | Kalshi/Polymarket microstructure | sharp-markets | Free Kalshi and Polymarket data |
| [#10](https://github.com/maxzipperman/value-finder/issues/10) | Player props: median vs mean | nfl-weather | About 46K Odds API credits (NFL 2023–26 at the close), in the March 5M month |
| [#11](https://github.com/maxzipperman/value-finder/issues/11) | CFB injury reports and early-season priors | cfb-weather | CFBD API |
| [#16](https://github.com/maxzipperman/value-finder/issues/16) | Line-move reversal: do day-to-day moves reverse before the close? | sharp-markets | The multi-book lines in the March 5M month |

Done: #4 (Rule HT pre-registered), #5 (timing advice and fill logging), #15 (10-book logging and the free-tier guard), #17 (no longshot bias; see below). The credit cost of every item, and the extra hypotheses the March data can test at no extra cost (line shopping, line-move reversal), are in [`odds-api-credits.md`](strategy-research/odds-api-credits.md).

Tested and skipped: primetime unders, the holdover bias, West Coast night games, fading big covers, turnover luck, road teams, CFB big underdogs, service-academy unders, the NFL moneyline favorite-longshot bias, and wind effects on the first-half and team split. See [what the screen found](strategy-research/README.md#faded-or-never-there) and [the pre-checks](strategy-research/README.md#pre-checks-on-the-backlog-added-september-28-2026).

## Keeping this current

Any change that moves a project, a forward test or a backlog item updates this file in the same pull request. See [`CLAUDE.md`](CLAUDE.md).
