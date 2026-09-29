# Odds API credits: which plan to buy, and what more credits unlock

*Strategy research · September 28, 2026 · The 5M-month section was rewritten on September 29 to the reviewed day-one design the owner adopted ([#38](https://github.com/maxzipperman/value-finder/issues/38)), with the research sweep's two corrections folded in ([#41](https://github.com/maxzipperman/value-finder/issues/41), [#42](https://github.com/maxzipperman/value-finder/issues/42)).*

Which Odds API plan this repo should pay for, month by month, and what each extra tier of credits would let us backtest. No Odds API call was made. The cost rules come from the official docs, and every credit figure comes from [`odds_budget.py`](odds_budget.py), which counts snapshots from the kickoff times in `*/data/processed/games.parquet`. Its output is in [`output/odds_budget.log`](output/odds_budget.log) and `output/odds_api_*.csv`. Two independent reviews tried to refute the arithmetic and the value case; [what they changed](#what-the-review-changed) is at the end. A third review, of the 5M month itself, is [`plan-review-2026-09-28.md`](plan-review-2026-09-28.md).

---

## The 5M month (owner decisions, September 28, 2026; rewritten September 29)

The owner buys **one 5M month ($119) on Thursday, October 1, 2026**, and on the evening of September 28 adopted the [plan review](plan-review-2026-09-28.md): a small day-one pull, pulls gated on results inside the month, and the rest in a March 2027 month that the 2026 holdout needs anyway. The props pull runs in two slices, a research-sweep finding the hub asked to fold in on September 29: its pre-registration ([#41](https://github.com/maxzipperman/value-finder/issues/41)) was written that day, so the 2025 slice is on day one and the rest waits on that slice's result. [`odds_5m.py`](odds_5m.py) makes the plan; its outputs are [`output/odds_5m_plan.csv`](output/odds_5m_plan.csv) (one row per pull with its tier, credits, 2026 share and gate), [`odds_5m_seasons.csv`](output/odds_5m_seasons.csv) and [`odds_5m_live.csv`](output/odds_5m_live.csv). The hub runs [`sharp-markets/docs/ODDS5M_DAY_ONE.md`](../sharp-markets/docs/ODDS5M_DAY_ONE.md) on the Mac on day one.

**Every credit figure here is an upper bound.** Football counts a full 2026 season as 2025's stand-in. On October 1 about a third of it exists (48 NFL and 331 CFB games played), so each football pull has a 2026 remainder that only a March month can complete. The table gives both numbers.

### Owner decisions (September 28)

1. **Holdout: the recommended split.** Sealed seasons:
   - the 2026 NFL and CFB seasons;
   - games played in calendar 2026 for MLB, every soccer league and the 2026 World Cup;
   - the 2026-27 NBA and NHL seasons.

   NBA research uses 2025-26, the study season in `sharp-markets/docs/PLAN.md`. `sharp-markets/config/odds5m.yaml` matches this exactly.
2. **Day one stays under 400K.** The probe, with three extra 30-credit coverage checks; F1; F2 at T−24h and the close, without team totals; the NBA sample week at schedule A through `markets odds-pull --schedule A`, not the bulk puller's `week` stage; heat as trigger-first, close-only pulls. This reverses the same day's earlier decision to pull F4 (hourly football) at once: F4 is now gated on F1's daily result. The review's reasons: the daily test comes first in the repo's own sequencing, the history doesn't expire, and F4 was 38% of the plan sitting in the first tier, where a billing surprise costs the most.
3. **Three pulls are gated inside the month, decided by about October 20:** F3b on the 2025 props slice, N1 on the NBA sample week, F4 on F1's day-to-day reversal test. The exact rules are in the gated table below and in `odds_5m.py`.
4. **The heat hypotheses become descriptive, closes only** ([`HEAT_HYPOTHESES.md`](../sharp-markets/docs/HEAT_HYPOTHESES.md) amendment 4). The full MLB and soccer histories, B1 and S1 (850K), are out of October and not scheduled for March.
5. **Drop X3, the exchange group (232K).** The same data is free from Kalshi and Polymarket at better resolution. Its credits go to the reserve, not to new pulls. X2, the 5-minute windows, stays deferred.
6. **Terms of use.** The hub checked [the-odds-api.com/terms-and-conditions](https://the-odds-api.com/terms-and-conditions) from the Mac:
   - Storing data indefinitely is allowed.
   - Research, dashboards and model training are allowed.
   - "Calculating and displaying values you derive from our data" is allowed.
   - Reselling or redistributing the raw data as a standalone data product is not allowed.
   - The terms don't say whether billing cycles follow the calendar month (see C6 below).

   So compact derived tables may go into this private repo, and raw responses stay out of git.
7. **After October: the owner decides around October 25, from real usage.** The estimates to decide with are [below](#after-the-month-live-uses): the 20K plan ($30) covers the low case (about 14,100 credits a month, with the NBA collector as shipped). The high case (about 20,000, with the collector's one-minute final-2h ticks turned on) needs the 100K plan ($59), or the collector's 56-hour window cut to game windows.
8. **"Get as much NCAA as possible."** What that means inside this design is [below](#ncaa-what-get-as-much-as-possible-buys-here): F1 already carries every FBS game's close and daily line, and nothing CFB-specific is added on day one.

### Day one: 272,790 credits at most, of which about 244K exists on October 1

Everything here has its outcomes on disk already, so analysis starts the same week. The run order is the table order.

| ID | Pull | Credits (upper bound) | 2026 share, and the part of it that exists on Oct 1 | Backtest ready on disk? |
|---|---|---|---|---|
| P0 | Probe: key check (free), historical `/events` sweeps for all 16 sport keys (exact schedules), then seven single-call probes: the four NFL billing checks, plus featured closes for NCAAF 2020, MLB 2024 and MLS 2024 | ~10,700 | — | n/a |
| F1 | NFL+CFB featured markets, 10 books, daily for 7 days before kickoff plus every close, 2020–26 | 162,210 | 24,540; 5,670 | Yes: 653 Rule HT games, 128 NFL and 237 CFB windy games (2020–25), every closing outcome |
| F2 | NFL alternate spreads and alternate totals at T−24h and the close, 2023–26. No T−2h snapshot (no hypothesis) and no team totals (their line, M4, was dropped after the free pre-check) | 45,600 | 11,400; 1,920 | Yes: nflverse margins |
| F3a | NFL props (pass, rush and receiving yards, receptions, kicking points, field goals made) at T−24h and the close, the 2025 season. The first slice of F3: #10's pre-registration draft was written on September 29 ([README idea 7](README.md#7-prop-structure-the-line-against-the-median)), and posted lines aren't on disk, so its line-vs-median test runs on this slice before the rest is bought | 34,200 | — | Yes: `player_week.parquet`, `kicks.parquet` |
| N0 | NBA sample week, Jan 5–11, 2026, at schedule A (754 snapshots), as PLAN.md §8 requires before any full season. `markets odds-pull --schedule A`; the snapshots are on N1's 5-minute grid and land in its cache | 7,540 | — | Yes: the week's Kalshi candles and trades are cached |
| HB1 | MLB heat closes: 10 books at the close of each 2024–25 game whose day-1 forecast temperature at first pitch is ≥ 90 °F at an open park | ≤ 4,380 | — | After the free weather join and `markets weather qualifying` |
| HS1 | Soccer heat closes: 10 books at the close of each 2024–25 league or tournament match whose day-1 forecast heat index at kickoff is ≥ 90 °F at an open venue | ≤ 8,160 | — | Same |
| **Total** | | **272,790** | **35,940; 7,590** | |

- **Why the heat pulls are small.** The trigger comes first, from free Open-Meteo data, and only qualifying games' closes are bought: the pulls read the game list that `markets weather qualifying` writes. The figures assume one close slot per qualifying game (146 MLB games and about 272 soccer matches, the review's free counts on observed weather), which is an upper bound. The day-1 forecast counts replace those numbers on the Mac; a different count changes the credits, never the design.
- **How the soccer leagues were chosen.** They're the summer and heat leagues with Odds API history from mid-2020. (There's no international-friendlies key.)

  | League or tournament | Why it's in |
  |---|---|
  | MLS | US summer heat |
  | Liga MX | Monterrey and Guadalajara heat, with altitude as a contrast |
  | Brasileirão | Tropical heat for most of the season |
  | J1 League | Japanese summer heat and humidity |
  | K League 1 | Korean summer heat and humidity |
  | Club World Cup 2025 | US summer; widely reported extreme heat |
  | Copa América 2024, Gold Cup 2025, Leagues Cup 2025 | US summer venues |
  | Euro 2024 | A cooler European control |
  | World Cup 2022 | A cooled-stadium control |
  | World Cup 2026 | The prime heat test; sealed |

### Gated inside the month: 2,031,260 at most, decided by about October 20

| ID | Pull | Credits (upper bound) | 2026 share; on Oct 1 | Gate (act-or-drop) |
|---|---|---|---|---|
| F3b | NFL props, the same markets and snapshots as F3a, 2023–24 and the 2026 games played | 102,600 | 34,200; 5,760 | Only if, on the 2025 slice (F3a), graded exactly as #10's pre-registration draft says (the excess under rate over the power-method de-vigged close price, receiving and rushing yards pooled, passing yards and receptions as controls): the pooled excess is positive, and the posted line sits above the player's same-season median in both primary markets. Before that read, the draft goes into a pre-registration file unchanged or by dated amendment. If the lines sit at the median or the excess is at or below zero, F3b moves to March and only the kicking markets (#21) stay in play. |
| N1 | NBA 2025-26 at 5-minute resolution, moneyline, 3 sharp books (PLAN.md schedule D), less the sample week | 486,440 | — | Only if the sample week shows an H1 edge (net-of-fee edge flags with fills and positive CLV to Pinnacle's close) or an H2 lag (median catch-up lag of 10 minutes or more), exactly as PLAN.md §8 step 3 and §9 decision 2 require. |
| F4 | NFL+CFB featured markets, 10 books, **hourly** for 7 days before kickoff, 2020–26, net of F1 | 1,442,220 | 207,090; 40,650 | Only if H16b passes on F1's daily grid ([#42](https://github.com/maxzipperman/value-finder/issues/42); the full gate is [below](#f4s-gate-h16b-reversal-before-the-close-added-september-29-2026-42)): Pinnacle's spread or total moved a point or more since the previous daily snapshot, bet against it, CLV to Pinnacle's close; act if mean CLV is at least 0.25 points with the 95% interval (clustered by game) above zero in both sports, and the season's interval above zero in at least 4 of the 6 seasons in each sport. H16a (fade the move *at* the close) was dropped on September 29: no edge on the free SBR pre-check. |

- **Day one plus every gate is 2,304,050**, against the hard ceiling of **4,440,000** (5,000,000 less the 531,630 floor, the probe and October's live use, rounded down; the arithmetic is in the day-one doc). Even if every gate passes, 2,164,320 stays unallocated. Nothing else is bought in October.
- **F3 runs in two slices (September 29).** The Sep 28 decision had all 136,800 on day one. The research sweep found that a yardage line set at the median hits about 50% by construction, so the skew argument needs the line to sit above the median. The free pre-check and the pre-registration draft landed the same day (#41), so the first slice is on day one; posted lines aren't free, so the line-vs-median test runs on that slice and the rest follows only if it passes. The total is unchanged if it does.
- **F4's incremental cost is 1,442,220, not 1,604,430.** Every F1 snapshot (the 16:00 UTC points and every close) lies on F4's hourly grid, and `bulk.py` caches by the same key; `tests/test_bulk.py` checks it.
- **N1 is 486,440 = 10 × (49,398 − 754).** The Sep 28 figure of 478,530 also netted 791 "closes" that nothing in the month pulls (review C12). Honouring the gate costs nothing: the sample week's snapshots are the first 754 of N1's grid.

### March 2027: the completions, and whatever the gates earned

| What | Credits (upper bound) | Gate |
|---|---|---|
| The 2026 completions of F1, F2 and F3b (the games after October 1) | 56,790 | None: the sealed 2026 seasons are pulled so they exist when a hypothesis about them is registered |
| F4's 2026 completion, if F4 was earned | 166,440 | H16b, as above |
| H1: NHL featured, daily plus every close, 2020–26 (estimate) | 163,860 | Only if the price engine worked on football (F1's rule) and a data-use line has been written |
| N2: NBA featured, daily plus every close, seasons other than 2025-26 (estimate) | 170,460 | Same |
| F5: CFB alternate lines and team totals at T−24h and the close, 2023–26 | 221,880 (the team-totals slice at the close alone is 36,980) | Only if Rule HT's re-grade at Pinnacle's close (F1, 2020–25) keeps its win rate above the break-even of the prices; the team-totals slice is the part worth having |
| F6: CFB props at the close, 2023–26 (upper bound; coverage is thin) | 147,920 | Only if #10 passes on NFL (F3) and a 30-credit probe finds CFB props at the close |

The plan size for March follows from the gates: 100K ($59) covers the completions and F5's team-totals slice; anything with H1, N2 or F4 needs 5M ($119).

### Not pulled

| ID | Pull | Credits | Why |
|---|---|---|---|
| B1, S1 | The full MLB and soccer daily histories, 2020–26 (estimates) | 358,470 + 491,970 | Replaced by HB1 and HS1 on September 29 (#38): the heat hypotheses are descriptive and closes-only, and the trigger exists only from 2024, so 2020–23 serves nothing registered |
| X3 | Exchange book group (Kalshi, Polymarket, Novig, ProphetX), hourly, 2025 | 231,630 | Dropped by the owner; its credits are in the reserve |
| X2 | 5-minute NFL+CFB totals for 72 hours before windy kickoffs, 2024–25 | 705,580 | Deferred until a forecast-run archive exists; the MOS archive in [#40](https://github.com/maxzipperman/value-finder/issues/40) may supply the run times |

### NCAA: what "get as much as possible" buys here

The owner asked for as much college football as the design allows. Inside the reviewed design:

- **F1 already carries it.** 3,381 of F1's 5,407 snapshots are CFB (101,430 of the 162,210 credits): every FBS-involved game's close and daily line at 10 books, 2020–26. That re-grades Rule HT (653 games) and CFB Rule B (237 windy games, 2020–25) at Pinnacle's close, and runs the price engine, H16a and H16b on CFB as well as the NFL.
- **The NCAAF 2020 probe** (30 credits) checks whether Pinnacle prices college football in the earliest history; `pin_total` in the CFBD data stops in 2019, so this is the open question for the CFB sharp close.
- **Free, in parallel:** the alerts log 10 books four times a day and close capture records every kickoff slot, which builds the 2026 CFB archive at no cost. Switching the alert book list to `us10` would make that archive continue F1 exactly (see [hygiene](#free-before-october-1-hygiene) below).

What could be added, with the credits and the hypothesis served, and the recommendation:

| Candidate | Credits | Hypothesis | Recommendation |
|---|---|---|---|
| F5, CFB alternates and team totals at T−24h and the close, 2023–26 | 221,880; 147,920 without team totals; 36,980 for team totals at the close only | Rule HT-style shrinkage shows up in team totals and alternates | **Not now.** Dropped once for thin coverage and weak CFB key numbers, and nothing has changed; Bovada, the book named for CFB derivatives, isn't in `us10`. March, behind the Rule HT re-grade, and only the team-totals slice. |
| A CFB-only hourly pull, 2020–26 | 796,380 gross; 694,950 net of F1's CFB snapshots | Hour-to-hour reversal (#16), the same as F4 | **Not separately.** F4 already includes CFB and has the same gate. A CFB-only version would only make sense if H16b held in CFB and failed in the NFL, which the F1 test will show before any hourly credit is spent. |
| F6, CFB props at the close, 2023–26 | 147,920 | Median-vs-mean props in CFB | **March**, behind #10 passing on the NFL and a 30-credit coverage probe. |
| Heat in NCAA football | Free (cfb-weather's data) | Whether the close mis-sets hot early-season games | **2027 material.** Testable free, but the ceiling is low, the sign is contested, and no CFB slot opens before 2027 (review section 7). |

**Recommendation: add nothing CFB-specific on day one.** The one NCAA item worth a decision in October is F5's team-totals slice (36,980), and its gate can only be read after F1 lands.

### Data-use plan

**Sealed holdout.** Every 2026-season game that exists is pulled with its pull, but it isn't examined until a hypothesis about it is pre-registered. Owner decision 1 defines the seasons; for NBA and NHL that's 2026-27. All exploration uses 2020–25 (NBA through 2025-26). The sharp-markets puller enforces this: the manifest flags sealed calls, and `bulk.load_rows()` leaves sealed rows out by default (PR B, #28).

The act-or-drop rules below are written before the data lands (review section 4, item 1). "Act" means the hypothesis becomes a 2027 pre-registration candidate, or unlocks the pull it gates; "drop" means it is written up and closed.

| Pull | Primary hypothesis | Metric | Act if | Drop if | Games needed | Variants |
|---|---|---|---|---|---|---|
| F1 | **Price engine** (#8): soft-book prices beyond the sharp fair line are bets | Realized ROI at the flagged price, and CLV to the soft book's own close (CLV to Pinnacle is tautological when Pinnacle defines the flag) | ROI positive with a 95% interval above zero, positive in at least 5 of 6 seasons, and it survives excluding flags where Pinnacle's market `last_update` is older than the soft book's | ROI at or below zero, or driven by one book or one season | A few hundred flags per market; stability across books and seasons is the binding constraint, not power | 9 |
| F1 | Rule HT and CFB Rule B history re-graded at Pinnacle's close; value of line shopping | Win rate, ROI | Descriptive: no act-or-drop. Rule HT above break-even at the sharp close is F5's gate | — | — | 4 |
| F1 | **H16b** ([#42](https://github.com/maxzipperman/value-finder/issues/42)): a move of a point or more on day *t* reverses by the close | CLV of fading the move, on the daily grid | At least 0.25 points of CLV with the interval above zero, in both sports, in 4 of 6 seasons: F4 unlocks | Anything else: F4 stays unpulled | Thousands of game-days | 2 |
| F1 | **H16a** (#42): fade the open-to-close move at the close | Win rate and ROI at the close, after vig | **Dropped on September 29**, on the free SBR pre-check: 49.6–50.8% at −110 on NFL 2007–21, ROI −3% to −5% ([README](README.md#fade-the-move-at-the-close-h16a-added-september-29-2026-42)). Not tested again on F1; a descriptive line at most | — | — | 6 (the pre-check's, in the 198) |
| F2 | Alternate lines misprice key-number crossings against recent-era margins | EV at the alternate price | Best-book alternate EV of at least +2% against the recent-era margin table, in each of 2023, 2024 and 2025 | EV at or below zero after vig. The Wong teaser leg rate was 73.3% in 2022–25 against a 73.9% break-even, so expect this dead at −120 | 1,140 games times many lines | 4 |
| F3a, F3b | **#10 as pre-registered on September 29** ([README idea 7](README.md#7-prop-structure-the-line-against-the-median), #41): posted lines sit above the empirical median, so the under wins more often than its price implies. Primary markets receiving and rushing yards, pooled (the two the free pre-check found skewed); passing yards and receptions as controls | Excess under rate over the power-method de-vigged close price, Σ(winᵢ − pᵢ)/n; ROI at the under price; the line minus the same-season median as a descriptive readout | F3b: the gate above. On 2023–25, per the draft: pooled p below the bar in force (0.05 / 198), *and* a positive excess with p < 0.01 in each of 2023, 2024 and 2025 and in each primary market | The pooled excess at or below zero, or one market or one season carries it | Tens of thousands of lines; the one close-is-wrong rule in the plan that is decidable | 4 (+1 for the draft, in the 198) |
| F3a, F3b | **Kicker props** (#21): kicking-points unders in wind or cold | Mean CLV from T−24h to the prop close; kicking points in trigger games | Mean CLV above zero with the interval clear on at least 100 lines, and kicking points actually fall in trigger games | Otherwise | About 89 windy or cold outdoor games in 2023–25, roughly 180 lines: a 2027 forward-test candidate at best | 2 |
| F3 | Prop moves across snapshots | — | Retired: the T−48h and T−2h snapshots are gone and it had no metric. The count is not lowered | — | — | 2 |
| N0, N1 | H1 (Kalshi static edge) and H2 (lag) as in PLAN.md | Per PLAN.md | Per PLAN.md; N1 only through the gate | Per PLAN.md | Train and validate as written | 12 |
| F4 | Hour-to-hour moves reverse before the close (#16) | CLV of fading the move | Only pulled through H16b; the same criteria at hourly resolution | — | — | 2 |
| HB1, HS1 | B-H1 and S-H1, **descriptive** (amendment 4) | The registered side's record at Pinnacle's close, its excess over the de-vigged probability with an interval, ROI; reported as a split | No decision rule: reported only, with the void and no-close counts | — | 146 and about 272: below any useful power | 3 (unchanged; includes the deferred B-H2) |
| H1, N2 (March) | Soft-price flags at the best price | ROI | Only through their gate; a data-use line is written before March | | | 4 + 4 |
| F5, F6 (March) | CFB shrinkage in team totals and alternates; CFB median-vs-mean props | Win rate, ROI | Only through their gates | | | 2 + 2 |

**Variant count:** the plan committed 56 variants on September 28 (191 in all). The retired prop-move variants stay counted. The free pre-checks of September 29 added 7: the #10 pre-registration draft (1) and the H16a fade-the-move variants (6), so the running count is **198** and the bar is **p < 0.00025** (0.05 / 198; [README](README.md#pre-checks-on-the-backlog-added-september-28-2026)). Nothing without a line in this table gets analysed.

#### F4's gate: H16b, reversal before the close (added September 29, 2026, [#42](https://github.com/maxzipperman/value-finder/issues/42))

F4 (hourly football) is pulled only if F1's daily grid shows that moves reverse *before* the close. The free H16a pre-check found that fading the move *at* the close has no edge: 49.6–50.8% at −110 on NFL 2007–21 ([README](README.md#fade-the-move-at-the-close-h16a-added-september-29-2026-42)). So an outcome edge can't justify F4; only CLV can. H16b is one of F1's committed variants and adds none.

| | |
|---|---|
| **Signal** | On a daily F1 snapshot (16:00 UTC, 7 to 1 days before kickoff), Pinnacle's spread or total has moved **1 point or more** since the previous daily snapshot. |
| **Bet** | Against that move, at that snapshot's Pinnacle number. |
| **Metric** | CLV in points: from the snapshot's number to Pinnacle's close (the last F1 snapshot at least 5 minutes before kickoff), positive when the line comes back. A game with no Pinnacle quote at either end is left out and counted. |
| **Sample** | F1, 2020–25, NFL and CFB, regular season and postseason; spreads and totals pooled, each also reported. The 2026 seasons are sealed. |
| **Act (pull F4)** | Mean CLV of at least **0.25 points**, with the 95% interval (clustered by game) above zero, **in both sports**, and the season's interval above zero in **at least 4 of the 6 seasons** in each sport. |
| **Drop** | Anything else. F4 is not pulled, and hourly history stays deferred. |
| **When** | Computed from F1 before any F4 credit is spent. |

### Free before October 1: hygiene

From the review's section 4, item 6:

- **The cut line and the reserve no longer collide.** The old 4.5M cut line plus the 531,630 floor summed to 5,031,630. The month now has a day-one cap of 400K and one hard ceiling, 4,440,000, which the floor can actually reach; `odds_5m.py` checks both.
- **STATUS.md** no longer describes the 20K pilot or the March month as the plan.
- **The paid key goes in all three `.env` files.** `LIVE_USES.md` and `ODDS5M_DAY_ONE.md` agree ([#33](https://github.com/maxzipperman/value-finder/issues/33)).
- **The alert book list: not switched (hub decision, Sep 28).** The alerts keep their 10 books; see the reasoning below, which stands as the record. The alerts log `pinnacle, lowvig, betonlineag, draftkings, fanduel, betmgm, betrivers, bovada, espnbet, hardrockbet`; F1's `us10` has `williamhill_us` and `fanatics` in place of `bovada` and `hardrockbet`, and the alerts log totals only. Switching the alert list to `us10` makes the free 2026 archive continue F1 exactly for totals, but it touches live alert behaviour, so it is the hub's call. One caveat: `williamhill_us` and `fanatics` are paid-only books, so on a free month after October the switched list would silently return eight books, not ten. Either switch for paid months only, or accept the eight-of-ten overlap.

### After the month: live uses

These are live calls, so they cost 1 credit per market per book group per call, not 10.

| Live use | Credits a month |
|---|---|
| Alerts, NFL + CFB, with the best under across 10 books (already on `main` since #20) | 248 |
| Close capture, one call per kickoff slot | ~137 |
| Trigger poller: every 10 minutes while a Rule B wind trigger is active | ~2,600 |
| NFL props, alternates and team totals log (9 markets at 4 snapshots a game) | ~2,520 |
| NBA collector from PLAN.md §7, from the Oct 20 opener | 8,640–14,460 |
| **Total** | **about 14,100–20,000** |

The NBA collector as shipped acts every 5 minutes while any game is inside its 56-hour window before tip (`sharp-markets/config/sports/nba.yaml`). In season some game always is, so it acts all day: 288 credits a day, or 8,640–8,928 a month. One-minute ticks in the final 2 hours, if turned on, add up to about 205 per game day (about 5,500 a month). The earlier figure of 3,888 assumed ticks only on game days' windows (corrected September 29, 2026, [#33](https://github.com/maxzipperman/value-finder/issues/33)).

**The owner decides around October 25, from real usage** (decision 5). The low case (about 14,100) fits the 20K plan ($30 a month) with about 5,900 to spare. The high case (about 20,000) is just over the 20K plan, so either leave the one-minute ticks off, cut the collector's window to game windows, or take the 100K plan ($59) during the NBA season.

---

## Earlier recommendation (superseded by the 5M month above)

**Pay for two months: a 20K pilot in October ($30), then one 5M month on March 1, 2027 ($119). Run the live alerts on the free tier the rest of the time.** The total is $149, plus $119 more only if the NBA sample week shows an edge.

*Update, September 28: the free pre-checks dropped two items. The first-half and team-totals pull (M4) is gone, and so is the best-price longshot test. The main month is now 292,960 credits, and it still needs the 5M plan.*

| When | Plan | Cost | What runs | Credits |
|---|---|---|---|---|
| **Now, before Oct 1** | Free (500/mo) | $0 | Put the key in all three `.env` files. The NFL and CFB alerts start using prices (L1, L2). If you approve the amendment (see [before you buy](#before-you-buy)), add a close-capture call at each kickoff (L3). | 248 a month; 385 with close capture (October has five Saturdays) |
| **October 2026** | 20K | $30 | Pilot: probe the unverified billing and coverage facts (P0), run the NFL forecast-time Pinnacle backfill (B1) and the NBA sample week (B12), and test each new puller on one week of real data. | 16,800 + 385 live = 17,185 (86%) |
| **Nov 2026 to Feb 2027** | Free | $0 | Alerts and close capture only. | 33–378 a month |
| **March 1, 2027** (after the Feb 14 Super Bowl) | 5M | $119 | Main backfill, NFL and CFB 2020–26: multi-book lines daily plus every close (M1), NFL alternates (M2), and NFL props at the close (M3). Also M5 if H3 proceeds. (M4 was dropped: its play-by-play pre-check failed.) Subscribe on the 1st, since credits reset on the 1st, and cancel the same day so the plan lapses at the end of the cycle. | 253,410 core; 292,960 with M5 |
| **April to August 2027** | Free | $0 | The alerts cost nothing off-season (the boards skip the API when no game is within 8 days). | 0–130 |
| **NBA branch**, only if B12's review supports H1/H2 | 5M on Nov 1 or Dec 1, then 20K a month | $119, then $30 a month | Full 2025-26 NBA season at 5-minute resolution (N1), then the forward collector (L4) for the rest of the season. If the new pullers have passed their tests, pull football 2020–25 in the same month. March then needs only the 2026 season (about 47K), which fits the 100K plan ($59). | 478,530; the collector uses 3,888–14,175 a month |

### Why this plan

- **5M is the only single month that fits the main backfill.** M1 alone is 162,210 credits, more than the 100K plan. Splitting M1–M3 across 100K months takes three months ($177). The cost per 1,000 credits is $1.50 on the 20K plan, $0.59 on 100K, $0.024 on 5M and $0.017 on 15M.
- **15M is never needed.** The main month plus the NBA season plus the deferred hourly history (X1) comes to 2,375,920 credits, which fits in 5M. If hourly were replaced by 15-minute snapshots, two 5M months ($238) would still cost less than 15M ($249).
- **Pilot first, because most of the pullers don't exist yet.**
  - No code calls historical events or historical event odds.
  - The sharp-markets normalizer drops the `point` field, so it can't store spreads or totals.
  - There's no NCAAF config.
  - Historical endpoints return `HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN` on the free tier, so these can only be tested in a paid month.
  - The pilot also settles six facts the plan depends on (see [unverified facts](#unverified-facts)) for under 1,000 credits.
- **Main month after the season, not in November.** Rules can't change mid-season, so anything found in November could only feed 2027 rules, and a March pull feeds the same rules. March also includes all of 2026, which removes the need for a second month, and it keeps the big pull off the Mac while the alerts are running.
- **Free is enough for live, with a guard.** The busiest month is 385 credits against a 500 limit. Running out breaks things, though. An exhausted quota returns 429 `OUT_OF_USAGE_CREDITS` (secondary source). `nflweather/oddsapi._get` turns only 401 and 422 into `SystemExit`, and `board._pinnacle_live` catches only `SystemExit`, so a 429 crashes the NFL alert run. CFB falls back to ESPN, which returned 403, so its signals arrive with no price. Also, `alerts.py --dry-run` still spends a credit.

---

## Before you buy

These are things you need to do or decide. This pull request doesn't change any alert, puller, rule or pre-registration.

1. **Guard the free tier (before Oct 1).**
   - Catch non-401 errors in the NFL client.
   - Add a floor on `x-requests-remaining` that skips manual runs and close capture below about 60.
   - Write each CFB live response to disk (`cfbweather/fetch.py:195` caches nothing, which breaks the cache-first rule).
   - On the first run, check that `x-requests-last` is 1 and that `pinnacle` appears in the NCAAF response. The free tier's coverage of Pinnacle and NCAAF comes from secondary sources only.
2. **Log up to 10 books on every alert call, at no extra cost.** Up to 10 bookmakers bill as one region, so `bookmakers=pinnacle,lowvig,betonlineag,draftkings,fanduel,...` costs the same 1 credit.
   - This is logging only; each rule keeps its registered price source.
   - It gives every signal a best-available price (line shopping: −105 breaks even at 51.2%, −110 at 52.4%).
   - It builds a free 2026 multi-book archive.
3. **Decide on close capture (L3). This needs a dated amendment before Oct 1 (CFB), Oct 7 (#4) and Oct 8 (NFL).**
   - The CFB scorer grades against the last logged quote, which is 0.5–4 hours before kickoff, because the alerts run at about 14:30, 18:30, 22:30 and 02:30 UTC.
   - The NFL scorer grades Pinnacle entries against the nflverse consensus close.
   - One totals call per kickoff slot fixes both. It would also be #4's entry price, since that rule bets "at the latest number available".
   - The least contentious form is a *secondary* CLV measure that leaves the primary one unchanged. It's your call, and it isn't made here.
4. **Fix the B1 puller before the pilot.**
   - `oddsapi.historical()` stamps each snapshot with the requested time instead of the API's `timestamp` (`nflweather/oddsapi.py:115`). The real quote can be up to 5 minutes earlier, which can overstate CLV.
   - `backfill()` defaults to `max_credits=6000`, but the plan needs 8,260.
5. **Commit a data-use plan before March.** Give one primary hypothesis, metric and holdout per dataset, and keep a running variant count that starts at the screen's 109. There's a draft [below](#draft-data-use-plan). Nothing without a line in it gets pulled, even though 5M leaves about 4.7M credits spare.
6. **Back up what you buy.** Paid data can't be re-created without paying again.
   - Keep `*/data/raw/oddsapi*` in an encrypted backup outside git.
   - Commit a pull manifest (requested and returned timestamps, `x-requests-last`, file hashes).
   - Commit compact derived tables to `data/processed/` only after checking the Odds API terms of use. (Since checked by the hub: derived tables are allowed, and raw responses stay out of git. See the 5M-month decisions above.)
7. **Keep M1 at 10 books or fewer.** At 11 books it bills as two regions, which doubles M1. Pilot one week first.

---

## What more credits unlock

| Credits | What it buys |
|---|---|
| **Free (500/mo)** | Live featured odds only: the alerts, close capture, and free multi-book logging. No history. |
| **20K** | The first history: the Rule B replay at real Pinnacle quotes for 2024–25 (B1) and the NBA sample week (B12). Or a live NBA collector. |
| **100K** | Multi-book closes for NFL and CFB 2020–25 (2,819 kickoff slots × 30 = 84,570).<br>CFB has no Pinnacle close after 2019 (`pin_total` stops then). This would re-grade #4's 57.7% and CFB Rule B's history against a sharp close. Or NFL props and alternates for 2023–26 (91,200). |
| **5M** | Everything below, with about 2.6M credits to spare even with the NBA season and the hourly history. |

How the newly possible ideas fared:

| Idea | Credits as first sized | Verdict |
|---|---|---|
| **5-minute line histories around forecast updates** for windy games (#6) | X2: 705,580 for NFL and CFB 2024–25, after removing snapshots M1 already has | **Deferred.** The repo has no record of when each forecast run was issued, CFB games would be picked on observed wind, and alerts that run 4 times a day can't act on a lag measured in minutes. First build a run-level forecast archive on the Mac, then pilot hourly (about 1/12 the cost). |
| **Props at several snapshots**, NFL and CFB (#10) | X6: 136,800 (NFL, 4 snapshots); X5: 442,240 (CFB) | **NFL at the close only (M3, 45,600).** That's #10's own design, and the median-vs-mean test needs only the close. CFB dropped: props come mostly from FanDuel, BetRivers and Bovada, and `player_games` has only QB, RB1 and WR1. |
| **Alternate lines** for teaser and key-number pricing (#8) | 45,600 (NFL 2023–26) | **Keep (M2), after the pilot checks whether Pinnacle carries alternates.** Teasers are fixed-payout book rules, so there are no teaser prices to pull. The key-number table comes free from nflverse margins. CFB dropped (X4, 110,560). |
| **First-half and team totals** for the derivative-market lag (#6) | X7: 580,160 (every 2 hours over 72 hours) | **Dropped after the free pre-check** ([results](README.md#pre-checks-on-the-backlog-added-september-28-2026)): wind doesn't measurably change the first-half or team split. The redesign it would have needed (M4, 11,440) is kept below for reference. A 2-hour grid can't see a lag shorter than 2 hours, and books derive these lines from the main total. The testable version checks level instead: does the book's first-half or team-total split ignore wind? Run it at T−24h and the close, and only if a free nflverse play-by-play pre-check shows wind changes the first-half or team split beyond a proportional shift. |
| **Multi-book close** for the price engine (#8) | M1: 162,210 (daily and close, 2020–26) | **Keep; this is the core.** It also serves #4 (Pinnacle closes, best price), #5 (NFL openers for 2022–25, which the SBR archive lacks), and the three hypotheses from outside feedback [below](#hypotheses-m1-can-test-at-no-extra-cost). Hourly (X1, 1,604,430) is deferred to a named question. |
| **A full NBA season** for H1/H2 | N1: 478,530 (schedule D, net of cached snapshots) | **Only if B12 passes.** PLAN.md says no full-season pull until the sample week has been reviewed, and H4a found no Kalshi lag in NFL totals. |

### Hypotheses M1 can test at no extra cost

Each of these reuses M1's snapshots (h2h, spreads and totals from 10 books) and counts toward the variant budget.

- **Line shopping.** What does the best of 10 books add to ROI over the consensus or Pinnacle price? Test it on #4 and on Rule B's history. This is descriptive and doesn't create a new bet rule. *A free first pass for CFB is done:* CollegeFootballData's retail books (about 2.4 per game) add about 0.3 points and about half a point of win rate ([pre-checks](README.md#pre-checks-on-the-backlog-added-september-28-2026)). M1 adds prices and more books, including sharp ones.
- **Line-move reversal.** [Simon (2024)](https://pubsonline.informs.org/doi/10.1287/mnsc.2022.00456) finds negatively autocorrelated line changes across 3,681 MLB games. A [2025 follow-up](https://sage.cnpereading.com/doi/10.1177/15586235251394815) reports the same in NFL, NBA and NHL moneylines.
  - **What the screen already found:** the open-to-close move doesn't predict the *result* (slope −0.05 ± 0.10).
  - **The different question:** does a day-to-day move reverse before the close? That would show up as CLV, not as a better result.
  - **Test and holdout:** fade the prior day's move and grade on CLV to the close, with 2026 as the holdout.
  - **Follow-up if daily data shows reversal:** hourly NFL (808,050 credits) becomes the named question that justifies part of X1, and it fits in the same 5M month.
- **Favorite-longshot bias by odds band.** *Pre-check done: no band shows a tradeable bias at the consensus close ([#17](https://github.com/maxzipperman/value-finder/issues/17), [results](README.md#pre-checks-on-the-backlog-added-september-28-2026)), so this comes off the data-use plan.* The original idea was to test at the best available moneyline, not the consensus.
  - A free pre-check on NFL is possible now, using the nflverse moneylines already in `games.parquet`. It needs no Odds API data.
  - CFB moneylines need M1.
  - Don't read it as "always bet favorites"; the screen's CFB big-underdog result already flips between eras.

Two ideas from the same feedback stay out:
- **Cross-book arbitrage.** At daily or close resolution, the arbitrage M1 finds is mostly stale quotes (the docs say Pinnacle's feed "may incur a delay"). Execution and limits decide whether it's real, and a paper-only repo can't test that. M1 will count it as a data-quality flag only.
- **Hedging promotional bets.** This is real-money bonus extraction, worth about 61¢ per dollar of free bet at best according to [Whelan's *The Economics of Free Bets*](https://www.karlwhelan.com/Papers/FreeBets.pdf). It isn't a market mispricing, and it needs live accounts.

The Kaunitz outlier-price method is idea 1 itself. Its real-money test ran for five months before the books limited the account. The feedback also reports that the live sample was 265 bets with p = 0.089, and that the stated $957.50 profit on 265 × $50 bets is a 7.2% return, not the 8.5% quoted. I couldn't open the paper from here to check those figures. Either way, a sample that small is one more reason to grade on CLV. The paper's historical test also used minute-by-minute odds, which is a reminder that M1's daily snapshots will only find the stale prices that persist.

### Draft data-use plan

| Dataset | Primary hypothesis | Metric | Holdout | New variants |
|---|---|---|---|---|
| B1 | Rule B's replay at real Pinnacle quotes matches the nflverse-based replay | CLV at entry | None (descriptive, 2024–25) | 1 |
| M1 | Soft-book prices beyond the 3-book sharp fair by ≥ X earn CLV (idea 1) | Mean CLV per flag | 2026 | 9 (3 thresholds × 3 markets) |
| M1 | #4 and CFB Rule B history re-graded at the Pinnacle close; value of line shopping | Win rate, ROI | None (descriptive) | 4 |
| M1 | Day-to-day line moves reverse before the close | CLV of fading the move | 2026 | 4 (2 markets × 2 sports) |
| ~~M1~~ | ~~Longshots lose more per dollar at the best price~~ (dropped: the free pre-check found no bias) | | | 0 |
| M2 | Alternate lines misprice key-number crossings versus recent-era margins | EV at the alternate price | 2026 | 4 |
| M3 | Yardage-prop unders hit more than 50% (median below mean) | Under rate, ROI at the close | 2026 | 4 (one per market) |
| M6 | Kicking-points unders in 15+ mph or ≤ 32°F outdoor games ([#21](https://github.com/maxzipperman/value-finder/issues/21)) | Win rate, ROI at the prop price | 2026 | 2 |
| ~~M4~~ | ~~Windy-game first-half and team totals don't reflect the wind~~ (dropped: pre-check failed) | | | 0 |
| B12, N1 | H1/H2 as specified in PLAN.md | Per PLAN.md | Per PLAN.md | Per PLAN.md |

That's about 26 new football variants. The free pre-checks already raised the running count to 134 ([`prechecks.py`](prechecks.py)), so it would reach 134 + 26 = 160 and the Bonferroni bar would fall to p < 0.00031. Cap new forward tests at one per sport per season.

---

## Use cases

Credits are per month for live rows (L) and one-time for backfills. Value runs from 1 to 5 and reflects [`README.md`](README.md)'s ranking: idea 1, the price engine, is the most proven; ideas 5, 7 and 8 are untested; the "Skip" list is out. It also reflects what the running forward tests need. These scores are ordinal, so they are never summed.

| ID | Stage | Use | Serves | Arithmetic | Credits | Value | Why |
|---|---|---|---|---|---|---|---|
| L1 | Live | NFL alerts: live Pinnacle totals | Rule B | 1 market × 1 book group × 4 runs × 31 days | 124/mo | 5 | The NFL forward test's price |
| L2 | Live | CFB alerts: Pinnacle/DraftKings totals | Rule B | 1 × 1 × 4 × 31 | 124/mo | 5 | CFB's only price source |
| L3 | Live | Close capture: one totals call per kickoff slot | Rule B, #4 | 1 × (29 NFL + ~108 CFB slots, Oct 2026) | 137/mo | 5 | The CLV reference for both tests and #4's entry price; deadline-bound |
| L4 | If B12 passes | NBA forward collector (PLAN.md §7) | H1/H2 | 1 × (144–288 five-minute ticks + 0–205 one-minute) × 27 game days | 3,888–14,175/mo | 2 | H4a found no lag; waits on B12 |
| L5 | Optional | Live logger: hourly multi-book lines, both sports, plus NFL props, alternates, first-half and team totals | #8, #10, #6 | 3 × 24 × 30 × 2 + 70 NFL games × (4 + 4 × 2) | 5,160/mo | 3 | Live costs a tenth of history, but March holds the same history at no extra cost |
| P0 | Oct pilot | Probes: billing multiplier, Pinnacle props, alternates and periods, LowVig and exchange history start, one test week per puller | All | Capped | 1,000 | 4 | Settles facts that swing the plan tenfold |
| B1 | Oct pilot | NFL Pinnacle totals at forecast decision times, 2024–25 (`backfill_plan`) | Rule B replay, #6 | 10 × 1 × 1 × 826 snapshots | 8,260 | 3 | End-to-end pipeline test; about 38 games at 15+ mph, and it can't change Rule B |
| B12 | Oct pilot | NBA sample week, schedule A | H1/H2 gate | 10 × 1 × 1 × 754 | 7,540 | 4 | PLAN.md's gate for the whole NBA path |
| M1 | Main month | Multi-book featured lines, daily 16:00 UTC for 7 days before kickoff plus every close, NFL+CFB 2020–26 | #8, #4, #5 | 10 × 3 markets × 1 group (10 books) × 5,407 snapshots | 162,210 | 4 | Price-engine data; CFB Pinnacle closes; NFL openers 2022–25 |
| M2 | Main month | Alternate spreads and totals, NFL 2023–26, T−24h and close | #8 | 10 × 2 × 1 × 2 × 1,140 games | 45,600 | 3 | Needs Pinnacle alternates for a sharp reference |
| M3 | Main month | Player props (4 markets), NFL 2023–26, close | #10 | 10 × 4 × 1 × 1 × 1,140 | 45,600 | 3 | Idea 7; graded on outcomes at US-book prices |
| M4 | Dropped (pre-check failed) | First-half and team totals, windy NFL games (≥ 12 mph observed) plus as many calm games, 2023–26, T−24h and close | #6 | 10 × 2 × 1 × 2 × (143 + 143) | 11,440 | 1 | The free play-by-play check found no wind effect on the first-half or team split |
| M6 | If #21 is in the data-use plan | Kicker props (kicking points, field goals made), NFL 2023–26, close | #21 | 10 × 2 × 1 × 1 × 1,140 | 22,800 | 3 | Wind and cold cut team kicking points from 7.2 to 6.5 a game; the prices are untested |
| M5 | If H3 proceeds | NBA Pinnacle closes 2021–26 | H3 | 10 × 1 × 1 × ~3,955 tips | 39,550 | 2 | Waits on licensed data |
| N1 | If B12 passes | NBA 2025-26 season, 5-minute, market open to tip (schedule D) | H1/H2 | 10 × 1 × 1 × (49,398 − 754 − 791 cached) | 478,530 | 2 | Worth it only after B12 |
| X1 | Deferred | Hourly multi-book featured lines, 7 days before kickoff, NFL+CFB 2020–26 | #8 | 10 × 3 × 1 × 53,481 | 1,604,430 | 3 | Hourly misses minute-long stale lines, and daily already catches persistent ones |
| X2 | Deferred | 5-minute totals for 72 hours before windy kickoffs, 2024–25, net of X1 | #6 | 10 × 1 × 1 × 70,558 (77,378 before netting) | 705,580 | 1 | No forecast-run timestamps yet |
| X3 | Dropped | Exchange book group (Kalshi, Polymarket, Novig, ProphetX), hourly, 2025 | #8, #9 | 10 × 3 × 1 × 7,721 | 231,630 | 1 | Kalshi and Polymarket are free at 1-minute resolution |
| X4 | Dropped | Alternate spreads and totals, CFB 2023–25 | #8 | 10 × 2 × 1 × 2 × 2,764 | 110,560 | 1 | Thin coverage, weak key numbers |
| X5 | Dropped | Player props, CFB 2023–25, 4 markets × 4 snapshots (upper bound) | #10 | 10 × 4 × 1 × 4 × 2,764 | 442,240 | 1 | Thin coverage; outcomes only for QB/RB1/WR1 |
| X6 | Replaced by M3 | Player props, NFL 2023–25, 4 snapshots | #10 | 10 × 4 × 1 × 4 × 855 | 136,800 | 2 | The extra snapshots have no hypothesis |
| X7 | Replaced by M4 | First-half and team totals every 2 hours over 72 hours, windy plus calm, NFL and CFB 2023–25 | #6 | 10 × 2 × 1 × 37 × 2 × (108 + 284) | 580,160 | 1 | Can't detect a lag shorter than 2 hours |

Event-odds rows (M2–M4, X4–X7) are upper bounds, because only markets that come back are billed and empty responses are free. Featured rows bill the markets requested. M1's responses carry the event IDs that M2–M4 need, so no separate `/events` calls are required.

**Inputs from the data** ([`output/odds_api_counts.csv`](output/odds_api_counts.csv)):
- **NFL:** 285 games and 136–139 kickoff slots a season from 2021 on.
- **CFB (FBS-involved):** 895–934 games and 325–381 slots a season from 2021 on.
- **Missing postseasons:** 2020–22 CFB bowls are missing from the file, so 2025's postseason count is added to those seasons.
- **2026:** both sports' 2026 schedules are incomplete, so 2026 uses 2025's counts.
- **Windy NFL games** (outdoor, ≥ 12 mph observed): 35, 38 and 35 in 2023–25.

**Live credits by month** ([`output/odds_api_live_months.csv`](output/odds_api_live_months.csv), using the 2025-26 schedule):

| | Aug | Sep | Oct | Nov | Dec | Jan | Feb |
|---|---|---|---|---|---|---|---|
| Alerts | 88 | 240 | 248 | 240 | 248 | 176 | 32 |
| Plus close capture | 128 | 359 | 372 (385 in Oct 2026) | 378 | 320 | 202 | 33 |

---

## Credit estimates already in the repo

| Where | Estimate | Check |
|---|---|---|
| `nfl-weather/README.md:39` | NFL 2024–25 backfill, about 8,300 | OK: 826 snapshots × 10 = 8,260 |
| `nfl-weather/nflweather/oddsapi.py:171`, `scripts/odds_api.py:4` | `--max-credits 6000` | **Too low.** The run would stop at about 600 of 826 snapshots. The argparse default and the README say 9000. |
| `nfl-weather/scripts/odds_api.py:5`, `this_week.py:5`, `cfbweather/fetch.py:187` | Live calls cost 1 or 2 credits | OK |
| `sharp-markets/docs/PLAN.md` §3 | Schedules A–D: 7,540 for the sample week, up to 493,980 for the season; H3 closes about 40K | OK: 10 × snapshots |
| `sharp-markets/docs/PLAN.md` §3 | 1-minute polling in the final 2 hours adds "about +100 credits/day" | **Low.** NBA tips are spread out, so it's about 150–260 a day. |
| `strategy-research/README.md` (idea 7), issue #10, `STATUS.md` | Props: 40 credits a game, about 34,000 for 2023–25 | OK: 855 NFL games × 40 = 34,200. M3 extends it to 2026. |
| `strategy-research/README.md` (data table) | "10 credits × markets × regions per historical snapshot" | **Incomplete.** Props, alternates and period markets are charged *per game* per snapshot. |
| Issues #6, #8, #9 | No figure | Sized here: M1, M2 and M4. |

---

## Cost rules

| Endpoint | Cost | Notes |
|---|---|---|
| `/v4/sports`, `/v4/sports/{sport}/events` | Free | |
| `/v4/sports/{sport}/scores` | 1; 2 with `daysFrom` | |
| Live `/odds` | Markets × regions | Featured markets only: h2h, spreads, totals, outrights. Empty responses are free. |
| Live `/events/{id}/odds` | Markets **returned** × regions | Any market; one game per call |
| `/events/{id}/markets`, `/participants` | 1 | |
| Historical `/odds` | 10 × markets × regions | Featured only. **One call returns every game of the sport** at the snapshot at or before `date`. |
| Historical `/events` | 1 (0 if empty) | |
| Historical `/events/{id}/odds` | 10 × markets returned × regions | **Per game, per snapshot.** Props, alternates, period markets and team totals. |

- **Books and regions.** A `bookmakers=` list of up to 10 books bills as 1 region, 11–20 books as 2, and it overrides `regions`. Every response carries `x-requests-remaining`, `x-requests-used` and `x-requests-last`.
- **History.** Featured markets from 2020-06-06 for NFL and NCAAF (2020-06-27 for NBA), in 10-minute snapshots, then 5-minute from September 2022. Additional markets from 2023-05-03T05:30Z, 5-minute. A book or market has history only from when it was added to the API. Odds before 2022-09-18 were stored in decimal.
- **NCAAF.** `americanfootball_ncaaf` has live and historical odds, with the same prop keys as the NFL ("NFL, NCAAF, CFL Player Props"). Props come mainly from US books.
- **Keys.**

  | Book | Key | Region |
  |---|---|---|
  | Pinnacle | `pinnacle` | `eu` only ("may incur a delay") |
  | LowVig | `lowvig` | `us` |
  | BetOnline | `betonlineag` | `us` and `eu` |

  Exchanges are in `us_ex`: `kalshi`, `polymarket`, `novig`, `prophetx`. Paid-only books: `williamhill_us`, `fanatics`, `rebet`.
- **Market keys.**
  - Props: `player_pass_yds`, `player_rush_yds`, `player_reception_yds`, `player_receptions`
  - Alternates: `alternate_spreads`, `alternate_totals`
  - Team totals: `team_totals`
  - Periods: `totals_h1`, `spreads_h1`, `h2h_q1`, and so on.
- **Plans.**
  - Free: 500 credits.
  - Paid: 20K $30, 100K $59, 5M $119, 15M $249 a month. Every paid plan includes all books, all markets and history.
  - Credits reset on the 1st.
  - Plans are monthly and can be cancelled any time; the plan runs to the end of the cycle with no refund, and upgrades are prorated.
  - The rate limit is 30 requests a second (429 `EXCEEDED_FREQ_LIMIT`).

### Unverified facts

The pilot settles each of these for under 1,000 credits.

1. **C1: event-odds history billed at 10×?** One R package says historical event odds are billed without the 10× multiplier. The official docs and code samples say 10×. The plan assumes 10×; check `x-requests-last`.
2. **C2: featured calls billed on markets requested or returned?** The plan assumes requested.
3. **C4: does Pinnacle carry props, alternates or period markets through the API?** It's unverified. A historical probe is free if the answer is none.
4. **C5: when does LowVig history start?** Possibly after 2021; it's missing from the official November 2021 sample. Exchange history probably starts recently.
5. **C6: does a mid-month subscription interact with the reset on the 1st?** It's undocumented; subscribe on the 1st.
6. **Does a cancelled key fall back to free, and does the free tier serve Pinnacle and NCAAF?** Both come from secondary sources only. Check `x-requests-remaining` on the first day after a paid plan lapses.

---

## What the review changed

Two independent reviews tried to refute this plan: one on the arithmetic, one on whether the value justifies the cost.

**Corrections applied:**
- **Timing.** A 20K pilot was added before any big month, and the big month moved from November to March 2027. The March month now includes 2026, which replaced a separate 2026 add-on of about 283K credits.
- **Hourly history.** The hourly multi-book pull (value 5 in the first draft, 1.28M) became daily plus close (M1, 162K). Hourly misses short-lived stale lines and adds little over daily for persistent ones.
- **5-minute forecast windows** dropped from 3 to 1 and were deferred.
- **Exchanges, CFB props and CFB alternates** were dropped.
- **NFL props** went from 4 snapshots to 1.
- **Derivative markets** were redesigned as a two-snapshot level test with a free pre-check.
- **Double counting** was removed: B1 and the 5-minute windows overlapped the other pulls, and the NBA sample week and closes sit inside the full season.
- **Missing postseasons.** The 2020–22 CFB bowls were added.
- **Separate event-ID lookups** were dropped, because M1 returns the IDs.
- **October's live figure** rose from 371 to 385, because October 2026 has five Saturdays.
- **The NBA collector** became a range, 3,888–14,175, instead of a point estimate.
- **"15-minute hourly ≈ 5.1M"** was corrected to about 4.97M for 2020–25.
- **Plan scoring** no longer sums value scores.
- **Prerequisites added:** the free-tier guard, backup, manifest, data-use plan and the 10-book limit on M1.

**Not applied:**
- **A 20K live logger from November to January** ($90). March's 5M month buys the same 2026 history at no extra cost, so it's listed as optional (L5).
- **Scoring B1 below the pilot.** It stays in the pilot as the end-to-end test of an existing puller.

---

## Sources

- **The Odds API docs** (official pages; read through a verbatim mirror dated Aug 31, 2026, because the site is blocked from the cloud sandbox):
  - [v4 guide](https://the-odds-api.com/liveapi/guides/v4/), including the usage-quota cost sections
  - [historical odds data](https://the-odds-api.com/historical-odds-data/)
  - [bookmakers](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html)
  - [betting markets](https://the-odds-api.com/sports-odds-data/betting-markets.html)
  - [sports](https://the-odds-api.com/sports-odds-data/sports-apis.html)
  - [error codes](https://the-odds-api.com/liveapi/guides/v4/api-error-codes.html)
  - [plans](https://the-odds-api.com/#get-access)
  - The mirror: [kieranaston/bet-bot `api-docs/docs_markdown`](https://github.com/kieranaston/bet-bot/tree/main/api-docs/docs_markdown)
- **Official code and samples:** [the-odds-api/samples-python](https://github.com/the-odds-api/samples-python) (historical odds and event odds) and the official S3 sample responses (a 2021-11-25 NFL snapshot covering all 15 Week 12 games).
- **Conflicting secondary source:** [sportsdataverse/oddsapiR](https://github.com/sportsdataverse/oddsapiR) (C1).
- **Repo:**
  - `nfl-weather/nflweather/oddsapi.py`, `cfb-weather/cfbweather/fetch.py`
  - `sharp-markets/src/markets/oddsapi/`, [`sharp-markets/docs/PLAN.md`](../sharp-markets/docs/PLAN.md) §3 and §7
  - `*/scripts/install_alerts.sh`
  - Issues #4–#11
- **Research cited for the M1 hypotheses:**
  - Simon (2024), [Inefficient Forecasts at the Sportsbook: An Analysis of Real-Time Betting Line Movement](https://pubsonline.informs.org/doi/10.1287/mnsc.2022.00456), *Management Science*
  - [Inefficiencies in Moneyline Movement for Three Major Sports](https://sage.cnpereading.com/doi/10.1177/15586235251394815) (2025)
  - Whelan (2026), [The Economics of Free Bets](https://www.karlwhelan.com/Papers/FreeBets.pdf)
  - Kaunitz, Zhong & Kreiner (2017), [Beating the bookies with their own numbers](https://arxiv.org/abs/1710.02824)
