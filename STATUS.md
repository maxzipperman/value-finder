# Value Finder: status

*Updated September 29, 2026*

Paper-only sports-betting research. The goal is to find prices the market gets wrong, and to prove each one on a pre-registered forward test graded on closing-line value (CLV) before any money goes in. Nothing in this repo places bets.

## Projects

| Folder | Question | Where it stands | Next step |
|---|---|---|---|
| [`nfl-weather/`](nfl-weather/) | Do NFL totals under-price wind? This extends the 2014 thesis. | Thesis replicated and audited. Rule B (forecast wind ≥ 15 mph → under) is pre-registered as playbook v2. Alerts run 4×/day. | Forward test is scored from Week 5 (Oct 8). |
| [`cfb-weather/`](cfb-weather/) | The same question for college football. | Rule B pre-registered (`cfb-v1-2026-09-28`). Rule HT (high totals → under, [#4](https://github.com/maxzipperman/value-finder/issues/4)) added as amendment 1 (`cfb-v2-2026-09-28`). Alerts run 4×/day. **Forecast replay, 2024–25** (the forecasts that existed at bet time): 61–46–3 (57.0%) at the close, one-sided p = 0.19, against 56.6% on observed wind; details in [`cfb-weather/README.md`](cfb-weather/README.md#forecast-replay-202425). | Rule B is scored from Oct 1, Rule HT from Week 6 (Oct 7, 00:00 UTC). |
| [`sharp-markets/`](sharp-markets/) | Do Kalshi markets misprice relative to sharp books, or lag behind them? | Pipeline built (NBA first, sport-agnostic), 22 tests. H4a (Kalshi NFL totals vs wind, 2025): Kalshi moves with the books and doesn't lag. | NBA sample week for H1/H2 on day one of the 5M month (Oct 1, 7,540 credits, `odds-pull --schedule A`); the full season (N1) only through its gate, by about Oct 20. H3 is waiting on licensed data. |
| [`strategy-research/`](strategy-research/) | Which "proven" strategies hold up in our data? | 109-variant screen plus 25 free pre-checks ([`prechecks.py`](strategy-research/prechecks.py)), 135 variants in all, counting the CFB Rule B forecast replay. Nothing passes a strict multiple-testing bar. Ranked ideas are in the backlog below. The Odds API plan and credit budget are in [`odds-api-credits.md`](strategy-research/odds-api-credits.md). | Work through the backlog. |
| [`thesis-research/`](thesis-research/) | What has been published since the thesis? | Literature review and feedback done ([page](https://claude.ai/artifact/ULdbHSkgLLcf6bzBGEppNU)). | Its crosswind idea is part of [#6](https://github.com/maxzipperman/value-finder/issues/6). |
| [`thesis/`](thesis/) | The 2014 thesis, as text. | Reference only. | None. |

## Forward tests (the scoreboard)

| Rule | Scored from | Signals so far | Decision |
|---|---|---|---|
| NFL Rule B: early wind under ([`STRATEGY.md`](nfl-weather/STRATEGY.md)) | Week 5, Oct 8, 2026 | 0 | Once, after the 2027 season, on 2026 and 2027 pooled (amendment 4, Sep 28), or at 40 signals if sooner: keep only if average CLV > 0 with a 95% interval above zero. The 2026 result is an interim read. |
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
   - **Next purchase (owner decision, Sep 28):** one 5M month ($119), bought **Thu Oct 1**. The hub runs the day-one checklist on the Mac that day.
     - **The plan (rewritten Sep 29, [#38](https://github.com/maxzipperman/value-finder/issues/38), to the reviewed design the owner adopted):** day one buys at most **238,590 credits**, of which about 210K exists on Oct 1: the probe with three extra coverage checks; F1 (10 books, daily plus every close, NFL and CFB 2020–26, 162,210); F2 (NFL alternates at T−24h and the close, no team totals, 45,600); the NBA sample week at schedule A (7,540); and heat closes for qualifying games only (about 12,500). Then it stops. The reserve floor stays 531,630 and the hard ceiling 4,440,000. Tables and gates: [`odds-api-credits.md`](strategy-research/odds-api-credits.md#the-5m-month-owner-decisions-september-28-2026-rewritten-september-29); the run order: [`ODDS5M_DAY_ONE.md`](sharp-markets/docs/ODDS5M_DAY_ONE.md).
     - **Gated inside the month, decided by about Oct 20:** F3, the NFL props (behind [#41](https://github.com/maxzipperman/value-finder/issues/41)'s pre-registration, in two slices: 34,200, then 102,600 if the posted lines sit above the empirical median); N1, the full NBA season (486,440), on the sample week's H1/H2 result; F4, hourly football (1,442,220 net of F1), on H16b, the daily reversal test on F1 ([#42](https://github.com/maxzipperman/value-finder/issues/42)). Day one plus every gate is 2,304,050.
     - **March 2027:** the 2026 completions (56,790, plus 166,440 for F4 if it was earned) and H1, N2, F5 and F6, each behind its gate.
     - **Review (Sep 28, evening):** [`plan-review-2026-09-28.md`](strategy-research/plan-review-2026-09-28.md). Adopted the same evening.
     - **Owner answers (Sep 28):**
       - the recommended holdout;
       - day one under 400K, with the hourly football pull (F4) gated on F1's daily result, reversing the same day's earlier decision to pull it at once; the 5-minute windows (X2) deferred;
       - drop the exchange group (X3);
       - the heat hypotheses descriptive and closes-only;
       - "get as much NCAA as possible": F1 already carries every FBS game's close and daily line (101K of its 162K); nothing CFB-specific is added on day one, and the [plan](strategy-research/odds-api-credits.md#ncaa-what-get-as-much-as-possible-buys-here) says what each option would cost and serve.
     - **Terms of use:** checked. Derived tables may go into git; raw responses stay out.
     - **Sealed holdout:** these stay unexamined until a hypothesis about them is pre-registered:
       - the 2026 NFL and CFB seasons;
       - calendar-2026 MLB, soccer and World Cup games;
       - the 2026-27 NBA and NHL seasons.
     - **Variants:** the plan committed 56 on Sep 28 (191); splitting #16 adds H16a, so the count is **192** and new analyses use p < 0.00026 (0.05 / 192).
     - **Pullers (PR B):** `sharp-markets` now has the bulk puller (`uv run markets odds5m`). It is tested against mocked responses; the hub runs it on day one by [`sharp-markets/docs/ODDS5M_DAY_ONE.md`](sharp-markets/docs/ODDS5M_DAY_ONE.md). The first step is a probe of about 10.7K credits that builds exact schedules and checks the billing, plus three coverage probes (NCAAF 2020, MLB 2024, MLS 2024). Pulls are grouped `day_one`, `gated` and `march`; `full --pull all` is refused; the heat closes read the game list that `markets weather qualifying` writes from the registered triggers, and `--seasons` pulls one slice of F3 at a time.
     - **Live uses (PR C):** three logging-only launchd jobs, described in [`ops/LIVE_USES.md`](ops/LIVE_USES.md). The hub installs them with `ops/install_live_uses.sh` once the paid key is in the `.env` files:
       - the wind-trigger price poller (NFL + CFB);
       - the NFL props, alternates and team-totals log;
       - the NBA collector (from Oct 20).

       They run only on a paid plan and stop at a background floor, so the alerts and close capture keep their credits.
       - **The paid key goes in all three `.env` files** (sharp-markets, nfl-weather, cfb-weather). The shared quota file now records which key made each call and ignores other keys' records, and the installer refuses to run unless the three keys match ([#33](https://github.com/maxzipperman/value-finder/issues/33)).
     - **Weather joins and heat hypotheses (PR D):**
       - venue tables for every MLB park and every soccer venue in the chosen leagues and tournaments (`sharp-markets/config/venues/`);
       - a free Open-Meteo fetch the hub runs on the Mac after the probe (`markets weather`);
       - two heat hypotheses pre-registered before any of their odds exist, in [`sharp-markets/docs/HEAT_HYPOTHESES.md`](sharp-markets/docs/HEAT_HYPOTHESES.md):
         - soccer: day-1 forecast heat index ≥ 90 °F → under at Pinnacle's close;
         - MLB: day-1 forecast temperature ≥ 90 °F at an open-air park → over.
       - **Amendments 1–3 (Sep 29, [#33](https://github.com/maxzipperman/value-finder/issues/33)), before any odds or outcome was joined:** consistent roof labels (Euro 2024 now counts; World Cup 2022 is out as a competition); result sources and settlement rules; World Cup 2026 is in the sealed confirmation sample. The file freezes at the first join of any outcome or odds to weather.
       - **Amendment 4 (Sep 29, [#38](https://github.com/maxzipperman/value-finder/issues/38), owner-approved):** both hypotheses are descriptive only, closes only: no decision rule, no forward test, no 2026 confirmation; results reported as a split. The full MLB and soccer histories are out; only qualifying games' closes are bought. It resolves [#35](https://github.com/maxzipperman/value-finder/issues/35): outcomes from the MLB Stats API and ESPN, and every void, unmatched or no-close game logged with a reason in `data/weather/heat_excluded.csv`. The MLB roof-status field stays unverified (hub, on the Mac).
     - **Review fixes (Sep 29, [#33](https://github.com/maxzipperman/value-finder/issues/33)):** a 3-lens review of PRs B–D found no blockers. All 19 findings are fixed, including stable Open-Meteo cache keys, weighted Open-Meteo budgets, `--now` as a dry run everywhere, a crash-safe props log in decimal odds, and a drop-pulls line of 4,440,000 in the day-one doc.
     - **Waiting on you: the plan after October. Decide around Oct 25, from real usage.** Live uses are estimated at about 14,100–20,000 credits a month (corrected Sep 29, [#33](https://github.com/maxzipperman/value-finder/issues/33): the NBA collector as shipped polls all day, 8,640–8,930 a month). 20K ($30) covers the low case with about 5,900 to spare; the high case (one-minute final-2h ticks on) needs 100K ($59), or the collector's window cut to game windows.
2. **The Oct 20 gate decisions.** By about Oct 20 the hub brings you three reads from day-one data, each against a rule written before the data landed ([gated table](strategy-research/odds-api-credits.md#gated-inside-the-month-2065460-at-most-decided-by-about-october-20)): the NBA sample week's H1/H2 tables (unlocks N1, 486,440); F1's H16b test, the daily reversal (unlocks F4, 1,442,220); and #41's line-vs-median check on the 2025 props slice (unlocks F3b, 102,600). A gate not read by Oct 25 is a no for the month; the history doesn't expire and March buys the same data. Before that, F3a (34,200) needs #41's free pre-registration written, and the H16a pre-check on the SBR lines ([#42](https://github.com/maxzipperman/value-finder/issues/42)) is free and unowned.
3. **Close capture is live (Sep 28), as a secondary measure.** A launchd job (`com.valuefinder.closecapture`) runs every 15 minutes. It makes one Odds API call per kickoff slot, 2–20 minutes before kickoff, and records the close in `*/data/forward/closes.csv`.
   - Both scorers now also report CLV against that close. The registered primary CLV and the decision rules are unchanged: nfl-weather amendment 3, cfb-weather amendment 2, both dated before any signal.
   - Rule HT keeps its entry at the last logged quote; the scorer also reports the captured close for it.
   - Budget: about 385 credits in October, out of 500.
   - **Keep the Mac awake at kickoff.** A slot missed while it sleeps is reported as missing, never filled in.
4. **Phone alerts.** Subscribe to the `NTFY_TOPIC` from either `.env` in the ntfy app, if you haven't yet.
5. **The alert book list (hub's call).** The review asks to switch the alerts' 10 books to F1's `us10` so the free 2026 archive continues F1 exactly. It touches live alert behaviour, and two of the `us10` books are paid-only, so it is described in the [plan's hygiene section](strategy-research/odds-api-credits.md#free-before-october-1-hygiene) and left for the hub.

## Research sweep (Sep 28)

A literature and code search for all eight hypotheses is in [`reviews/2026-09-28-research-sweep.md`](reviews/2026-09-28-research-sweep.md). Three findings became issues: a forecast archive back to 2004 that allows a true as-issued replay of both wind rules ([#40](https://github.com/maxzipperman/value-finder/issues/40)); props should be tested as line-vs-median before the props pull is spent ([#41](https://github.com/maxzipperman/value-finder/issues/41)); line-move reversal splits into two hypotheses, one of which gates the hourly pull ([#42](https://github.com/maxzipperman/value-finder/issues/42)). #41 and #42 are folded into the 5M plan's act-or-drop rules (Sep 29, [#38](https://github.com/maxzipperman/value-finder/issues/38)); their free pre-checks are still to run.

## Backlog

One issue per idea from [`strategy-research/`](strategy-research/README.md#ideas-to-add-ranked), in suggested order. Filter the [`idea` label](https://github.com/maxzipperman/value-finder/issues?q=is%3Aissue+label%3Aidea) on GitHub.

| # | Idea | Project | Needs |
|---|---|---|---|
| [#6](https://github.com/maxzipperman/value-finder/issues/6) | Crosswind vs headwind; derivative markets; forecast-run timing | nfl-weather | Crosswind: checked. It looks worse than along-field wind but isn't significant; a 2027 refinement at most. Derivative markets: the pre-check failed, so the pull is dropped. Forecast-run timing: deferred until there's an archive of when each forecast run was issued. |
| [#7](https://github.com/maxzipperman/value-finder/issues/7) | Home teams off a bye; Week 1 unders (paper) | nfl-weather | Nothing new |
| [#8](https://github.com/maxzipperman/value-finder/issues/8) | Price engine: beat the sharp fair line (most proven) | sharp-markets | F1 (multi-book lines 2020–26, 162K) and F2 (NFL alternates, 46K), both on day one of the 5M month, Oct 1. Kalshi and Polymarket (free). |
| [#9](https://github.com/maxzipperman/value-finder/issues/9) | Kalshi/Polymarket microstructure | sharp-markets | Free Kalshi and Polymarket data |
| [#10](https://github.com/maxzipperman/value-finder/issues/10) | Player props: median vs mean | nfl-weather | F3, gated behind [#41](https://github.com/maxzipperman/value-finder/issues/41)'s pre-registration (line vs median): the 2025 slice first (34,200), the rest (102,600) only if the lines sit above the median |
| [#11](https://github.com/maxzipperman/value-finder/issues/11) | CFB injury reports and early-season priors | cfb-weather | CFBD data pulled (2014–25, 252 calls): `cfb-weather/data/processed/cfbd_{lines,team_box,returning,talent}.parquet`. Next: the priors model. |
| [#21](https://github.com/maxzipperman/value-finder/issues/21) | Kicker props: kicking-points unders in wind and cold | nfl-weather | Outcomes are in (`player_week.parquet`). Prices: the kicking markets are inside F3 (gated, see #10). |
| [#16](https://github.com/maxzipperman/value-finder/issues/16) | Line-move reversal: do day-to-day moves reverse before the close? | sharp-markets | Split into H16a and H16b ([#42](https://github.com/maxzipperman/value-finder/issues/42)). Both run on F1's daily grid from day one; H16b gates the hourly pull (F4). H16a's free SBR pre-check (2007–21) is still to run. |

Done: #4 (Rule HT pre-registered), #5 (timing advice and fill logging), #15 (10-book logging and the free-tier guard), #17 (no longshot bias; see below), #35 (heat outcomes source and void-game logging, amendment 4), #38 (the 5M plan rewritten to the reviewed design). The credit cost of every item, and the extra hypotheses F1 tests at no extra cost (line shopping, H16a and H16b), are in [`odds-api-credits.md`](strategy-research/odds-api-credits.md).

Tested and skipped: primetime unders, the holdover bias, West Coast night games, fading big covers, turnover luck, road teams, CFB big underdogs, service-academy unders, the NFL moneyline favorite-longshot bias, and wind effects on the first-half and team split. See [what the screen found](strategy-research/README.md#faded-or-never-there) and [the pre-checks](strategy-research/README.md#pre-checks-on-the-backlog-added-september-28-2026).

## Keeping this current

Any change that moves a project, a forward test or a backlog item updates this file in the same pull request. See [`CLAUDE.md`](CLAUDE.md).
