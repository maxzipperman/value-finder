# Unsexy, quantifiable edges: what to add to the tool

*Strategy research for NFL and college football · September 28, 2026*

What the evidence says about "proven" betting strategies, how the theses already in this repo fit, and a ranked list of ideas to build. Every number marked **(screen)** comes from [`screen.py`](screen.py), run on data already in this repo. It made no downloads and no API calls, and used no 2026 games.

---

## Short answer

- **Almost nothing situational stays proven.** In the literature, the edges that last are about *price*, not prediction: bet a soft number against a sharp reference line (Kaunitz et al. 2017), do the key-number math on teasers and alternate lines, and measure everything by closing-line value (CLV). The limit on price-based edges is getting limited by sportsbooks, not the math. That's why exchanges and prediction markets (Kalshi, Polymarket, ProphetX, Novig) matter for this tool.
- **Published anomalies fade once they're published.** The screen replicates several of them in their original windows and then watches them fade:
  - Holdover bias: 62.7% in the paper's 2004–12 window, 53.3% since.
  - West Coast teams at night: 70% through 2011, 56% since.
  - Primetime unders: 52.2% over 27 seasons. The 2022–25 run was 56.3%.
- **One new lead from your own data: college high totals go under.** When a CFB closing total is 10+ points above the prior season's average, the under went **373–273 (57.7%) in 2016–25**, above 50% in 9 of 10 seasons (screen). The market's totals have become too spread out: the calibration slope of result on closing total is **0.89 ± 0.03** for 2016–25, against 1.01 for 2006–15. It survives excluding windy and dome games. It doesn't pass a strict multiple-testing bar (109 variants), so it's a forward-test candidate, not a bet.
- **Your Kalshi data answers one question already.** The 2025 NFL total-points ladder was calibrated within about 3¢ between 20¢ and 80¢ (285 games, screen). The published favorite-longshot bias lives below 10¢, and those strikes aren't in your cache yet.
- **Timing is an execution edge worth encoding.** From 2007–21, lines drifted toward favorites (moved toward the favorite in 46.8% of games, away in 34.4%). Totals drifted down, and CFB high totals drifted *up* by about a point. So bet favorites and unders early, underdogs late, and CFB high-total unders at the close (screen).

---

## What's in the folder now

| Thesis | Where | Status | Obvious next step |
|---|---|---|---|
| Wind 15+ mph → under (Rule B), NFL | `nfl-weather/STRATEGY.md` | Pre-registered forward test from Week 5 (Oct 8, 2026), graded on CLV | Derivative markets and forecast-run timing (idea 5) |
| Wind 15+ mph → under (Rule B), CFB | `cfb-weather/STRATEGY.md` | Forward test from Oct 1, 2026 | Same, plus a CFB forecast replay (none exists yet) |
| Weather-only model lean | `nfl-weather/PREREGISTRATION.md` | Paper only | Keep paper |
| Dome/warm visitor in ≤32°F game → home ATS | `nfl-weather/STRATEGY.md` | Watch (58.6% of 113) | Keep watch; similar body-clock edges faded in the screen |
| Weather props (pass yards, FG%) | `*/scripts/props_research.py` | Step 1: effects measured, no prices | Pull prop prices (idea 7) |
| H1/H2: Kalshi vs Pinnacle static edge and lag | `sharp-markets/docs/PLAN.md` | NBA sample week | Port to NFL/CFB (idea 3) |
| H3: fade-the-public splits | `sharp-markets` (Kaggle MGM) | Planned; licensed data pending | Keep; the literature supports it (below) |
| H4a: Kalshi NFL totals vs wind | `sharp-markets/reports/h4a_nfl_weather_2025.md` | 2025 run: no sign Kalshi lags books on wind | Reuse its cached ladders for the pricing-bias test (idea 3) |
| 2014 thesis follow-ups (acclimation design, crosswind, NGS) | `thesis-research/` | Review done | Crosswind feeds idea 5 |

---

## What the screen found

109 bet variants, each at closing lines, flat −110, pushes excluded, seasons through 2025. The Bonferroni bar is p < 0.00046 and **nothing passes**, so read this as a ranking. A thesis ranks higher when it holds across eras, holds out of sample after its paper's window, and has a mechanism. Full table: [`output/screens.csv`](output/screens.csv).

### Leads

| Thesis | Record | Win % | Notes |
|---|---|---|---|
| CFB total ≥ prior-season mean + 10 → under, 2016–25 | 373–273 | 57.7% | p = 0.0035 vs break-even. By season: 64, 45, 51, 61, 54, 67, 56, 60, 63, 55%. 2006–15 (same rule on season mean): 48.2%. |
| … outdoor, wind < 15 mph only | 374–276 | 57.5% | Not the weather rule in disguise: only 5% of these games had 15+ mph wind. |
| … at the opening total | 350–280 | 55.6% | These totals *rise* 0.95 points on average from open to close, so bet late. |
| Mirror: CFB low totals → over | 333–307 | 52.0% | Not symmetric, which fits over-betting on high totals (Paul & Weinbach 2002). |
| NFL Wong teaser legs, 1999–2025 | 1039–352 | 74.7% | 2014–25: 75.7%. 2022–25: 73.3%. Break-even is 73.9% for a 2-team teaser at −120. |
| NFL fade home team off a bye, 2011–25 | 95–76 | 55.6% | Replicates Lopez & Bliss (2024), who find home teams off a bye cover 44.6%. Road bye teams show nothing (47.4%). |
| NFL Week 1 unders, 1999–2025 | 232–192 | 54.7% | Steady across eras (54.5%, 55.0%, 60.4% in 2020–25). Only 16 games a year. |

### Faded or never there

| Thesis | Record | Win % | Verdict |
|---|---|---|---|
| Primetime unders, 1999–2025 | 572–524 | 52.2% | Sunday night went 64.3% in 2022–25 but 47.8% in 2014–21. A hot streak, not an edge. |
| Holdover bias: Week 1, non-playoff team vs last year's playoff team | 48–42 (2013–25) | 53.3% | 62.7% in the paper's 2004–12 window. Decayed after publication. |
| West Coast team vs East Coast team, 8pm+ ET | 42–33 (2012–25) | 56.0% | 70% in 1999–2011 (n = 30). The 1pm "control" flips sign between eras, so it's noise at these sample sizes. |
| High totals → under, NFL (prior-season mean + 5), 2001–25 | 465–428 | 52.1% | Paul & Weinbach's 1979–2000 rule. 54.1% with a full-season threshold, which uses information a bettor wouldn't have. |
| Road teams (market slow to cut home-field advantage), 2020–25 | 818–806 | 50.4% | Priced in. |
| Fade a team that covered by 14+ (Vergin 2001) | 793–772 | 50.7% | Nothing, in NFL or CFB. |
| Fade turnover luck (+3 last game, or +1/game on the season) | 581–540, 466–473 | 51.8%, 49.6% | The market doesn't overreact to turnovers. |
| CFB underdogs getting 21+, 28+, 35+ | 838–768 (21+, 2016–25) | 52.2% | Flips between eras. CFB spreads calibrate at slope 1.00 now. |
| CFB underdogs, weeks 0–4 | 1222–1195 (2016–25) | 50.6% | Sinkey & Logan's (2009) overpriced favorites are gone. |
| Service-academy games → under | 211–220 | 49.0% | Only academy vs academy works (29–13), and that's 2 games a year. |

### Structure and timing (not bets)

- **Key numbers** ([`output/key_numbers.csv`](output/key_numbers.csv)). Margins of 7 have thinned since the longer extra point: 9.3% of games in 1999–2014, 7.7% in 2020–25. Margins of 6 and 8 have grown. Margins of 3 are steady at about 15%. Teaser and alternate-line pricing should use recent-era frequencies.
- **Open → close, NFL 2007–21** ([`output/line_moves.csv`](output/line_moves.csv)). Favorites won 50.4% at the opening number and 48.7% at the close, in the same games. Totals moved down in 48.8% of games and up in 38.8%. Moves don't predict the result beyond the close (slope −0.05 ± 0.10 for spreads, 0.01 ± 0.12 for totals). That makes timing an execution rule, not a signal.
- **CFB opening vs closing totals.** The average move is 1.8 points and 22% of games move 3+. Openers are only slightly less accurate than closers (mean absolute error 13.0 vs 12.8). Group of 5 and Power 5 games look the same.
- **Kalshi NFL total-points ladder, 2025, 5 minutes before kickoff** ([`output/kalshi_ladder.csv`](output/kalshi_ladder.csv)). Across 2,915 contracts priced 20–80¢, the realized hit rate is within 3.2¢ of the mid in every 10¢ bucket, with game-clustered SEs of about 3¢. Buying YES at the ask lost 1.0¢ per contract. Buying NO lost 4.4¢, because overs hit more often in 2025.

### Pre-checks on the backlog (added September 28, 2026)

[`prechecks.py`](prechecks.py) ran 25 more tests on free data ([`output/prechecks.csv`](output/prechecks.csv), [`output/prechecks.log`](output/prechecks.log)). **The running count is now 135 variants (134, plus 1 for the CFB Rule B forecast replay in [`../cfb-weather/scripts/forecast_replay.py`](../cfb-weather/scripts/forecast_replay.py)), so the Bonferroni bar is p < 0.00037. Nothing passes.**

**The bar for new analyses is already p < 0.00026 (0.05 / 191).** The 5M data-use plan commits 56 more variants ([`odds-api-credits.md`](odds-api-credits.md#data-use-plan)), 135 + 56 = 191. They count from the moment they were committed, whether or not their analysis has run yet, so anything analysed from here on is judged against 0.05 / 191, and each new variant beyond the plan raises the count further.

**Running count: 200** (September 28, 2026, evening: 198, plus 2 for the size-of-total check in [`gate_level_check.py`](gate_level_check.py), one per sport; it found no dependence, so the registered pricing model is flat). The props pre-registration draft below ([idea 7](#7-prop-structure-the-line-against-the-median)) adds 1. It sharpens one of F3's 8 committed variants rather than adding a new question, but it is counted separately to be safe. The [fade-the-move pre-check](#fade-the-move-at-the-close-h16a-added-september-29-2026-42) adds 6 (3 thresholds × 2 markets). The bar is p < 0.05 / 200 = 0.00025. September 29, 2026: the [landing-mass table](#landing-mass-table-key-numbers-added-september-29-2026-52) ([#52](https://github.com/maxzipperman/value-finder/issues/52)) adds 32, for **232**, so the bar is p < 0.05 / 232 = 0.000216. September 29, 2026: the CFB Rule B forecast replay on NWS MOS ([#40](https://github.com/maxzipperman/value-finder/issues/40), [`../cfb-weather/scripts/mos_replay.py`](../cfb-weather/scripts/mos_replay.py)) adds 1, for **233**, so the bar is p < 0.05 / 233 = 0.000215; its NFL half adds 1 more when it runs. September 29, 2026: the [price-engine backtest](#the-price-engine-backtest-ready-before-f1-lands-added-september-29-2026-8-53) ([#8](https://github.com/maxzipperman/value-finder/issues/8), [#53](https://github.com/maxzipperman/value-finder/issues/53)), registered before any F1 data exists, adds 38, for **271**, so the bar is p < 0.05 / 271 = 0.000185. September 29, 2026: the [paper-to-money gate](#the-paper-to-money-gate-added-september-29-2026-51) ([#51](https://github.com/maxzipperman/value-finder/issues/51)) sizes a staking rule, not a betting rule, and adds none: still **271**, bar p < 0.05 / 271 = 0.000185.

| Issue | Test | Result | Verdict |
|---|---|---|---|
| [#17](https://github.com/maxzipperman/value-finder/issues/17) favorite-longshot bias | NFL closing moneylines 2006–25, ROI backing each band of no-vig probability at the consensus price | Every band loses except short underdogs (35–50%): +1.6% ROI, p = 0.24 (n = 2,575). Longshots under 20%: −15% ROI, bias −1.4 points (se 1.4). Favorites: −3.5% ROI, which is the vig; bias −0.5 (se 0.6). | **No tradeable bias** at the consensus close, in either era. The best-price version comes off the data-use plan. |
| [#6](https://github.com/maxzipperman/value-finder/issues/6) part 1, crosswind vs along-field | Stadium headings from [greerreNFL/stadiums](https://github.com/greerreNFL/stadiums), checked against [ThompsonJamesBliss/WeatherData](https://github.com/ThompsonJamesBliss/WeatherData) (median gap 1°; 5 stadiums where the sources disagree are left out), plus ERA5 kickoff wind direction | Unders at 15+ mph: **58.97% (194–135) mostly across** vs 54.5% (169–141) mostly along. Final total minus close per mph: −0.19 across, −0.10 along (difference p = 0.18). Yards per attempt per mph: −0.030 vs −0.021 (p = 0.12). | **Consistent but not significant.** Crosswinds look like they do more damage in all three tests. Worth a pre-registered Rule B refinement for 2027 at most; Rule B stays unchanged for 2026. |
| #6 part 2 pre-check, derivative markets | nflverse play-by-play halftime scores, outdoor 2006–25 | First-half share of points: 0.515 at 15+ mph vs 0.502 calm, per mph p = 0.31. Favorite's margin minus the spread: −0.39 at 15+ mph vs +0.23 calm, per mph p = 0.27. | **Gate not met.** Wind doesn't measurably change how points split between halves or teams, so lines derived from the main total have little to lag. The first-half and team-totals pull (M4) is dropped. |
| [#16](https://github.com/maxzipperman/value-finder/issues/16) line shopping, CFB | CollegeFootballData lines by sportsbook, 2016–25. About 2.4 books per game, mostly retail. There are no over/under prices, so everything is at −110. | The best book's total beats the consensus close by **0.3 points** on average, and is better in 44–48% of games. Rule HT: 58.2% at consensus vs **58.8% (223–156) at the best book**. CFB Rule B (observed wind): 56.2% vs 57.1%. Rule HT totals rise **+0.83 points** from each book's open to its close (rose in 55% of cases, fell in 29%; p < 0.0001; 450 book-games). | **Shop, and take high totals late.** Shopping is worth about half a point of win rate on these rules. The open-to-close rise supports Rule HT's "bet at the close". |
| [#4](https://github.com/maxzipperman/value-finder/issues/4) Rule HT by spread size | Run *after* Rule HT was pre-registered; descriptive only | Spread ≥ 14: **61.1% (179–114)**. Spread < 14: 55.0% (194–159). | Fits the garbage-time / running-clock mechanism. Rule HT stays as registered; this is context for its 2027 review. |

### Props: how far the mean sits above the median (added September 29, 2026, [#41](https://github.com/maxzipperman/value-finder/issues/41))

[`props_median_check.py`](props_median_check.py) ([`output/props_median_check.csv`](output/props_median_check.csv), one row per player, market and season). No prop prices exist on disk, so this measures only the skew a line-setter faces. It is descriptive and adds no variant.

- **Data:** each team's QB, RB1 and WR1 from `player_games.parquet`, picked without hindsight, 2023–25. Player-seasons with at least 8 games in the role. Games where the RB1 had no carry or the WR1 no target (83 and 88) are left out, because an inactive player's prop is void.
- **Result:**

  | Market | Player-seasons (games) | Mean − median, average | As % of the mean | Under rate if the line sat at the season mean |
  |---|---|---|---|---|
  | QB passing yards | 99 (1,439) | −0.1 | 0% | 49.7% |
  | RB1 rushing yards | 93 (1,199) | +2.1 | 3.2% | 53.0% (se 1.4) |
  | WR1 receiving yards | 59 (605) | +5.5 | 7.6% | 55.0% (se 2.0) |
  | WR1 receptions | 59 (605) | +0.2 | 2.9% | 49.9% |

  The pattern holds in each season: receiving yards 54–56%, rushing yards 51–54%, passing yards 49–50%.
- **What it means for [#10](https://github.com/maxzipperman/value-finder/issues/10):**
  - Only receiving and rushing yards are skewed enough to matter. A line at the mean would give the under about 3–5 points, but a line at the median gives nothing.
  - Passing yards are symmetric, so the mechanism predicts no edge there.
  - The question is where posted lines sit, and only F3's lines can answer it.
- **A caution, not a test.** A line-setter works from past games. Against each player's previous 6–16 games (`player_week.parquet`, every prop-sized player, no role selection), outcomes fall below the trailing median 56–57% of the time for rushing and receiving yards, and below the trailing mean 59–61% of the time. The causes are regression to the mean, injury exits and usage changes. So "the line sits above a trailing median" would be true even of efficient lines, and can't be the test. The draft below grades the under at its de-vigged price instead.

### Fade the move at the close: H16a (added September 29, 2026, [#42](https://github.com/maxzipperman/value-finder/issues/42))

[`fade_move_sbr.py`](fade_move_sbr.py) ([`output/fade_move_sbr.csv`](output/fade_move_sbr.csv)).

- **The bet:** take the side the line moved *away* from between the open and the close, at the closing number. Spreads and totals are graded separately, on win rate and ROI at −110 (break-even 52.38%), since the bet is at the close.
- **The question:** Moskowitz (2021, Table III) finds NFL open-to-close moves partly reverse by the final score, after the close, but not by enough to beat transaction costs. This asks whether that reversal pays at the price.
- **Data:** SBR open and close, NFL 2007–21, regular season and playoffs, joined to nflverse results (`games.parquet`). Pushes are counted but aren't bets.
- **Variants:** 6 (moves of ≥ 0.5, ≥ 1 and ≥ 1.5 points, × 2 markets). They bring the running count to 198.
- **Result, pooled 2007–21:**

  | Market | Move ≥ | Bets | Fade wins | ROI at −110 | One-sided p vs break-even |
  |---|---|---|---|---|---|
  | Spread | 0.5 | 3,201 | 50.8% | −3.0% | 0.97 |
  | Spread | 1 | 2,267 | 49.8% | −4.9% | 0.99 |
  | Spread | 1.5 | 1,608 | 49.6% | −5.3% | 0.99 |
  | Total | 0.5 | 3,475 | 50.5% | −3.5% | 0.99 |
  | Total | 1 | 2,621 | 50.3% | −3.9% | 0.98 |
  | Total | 1.5 | 1,851 | 50.3% | −4.0% | 0.97 |

  Only 3 to 5 of the 15 seasons are above break-even in any variant, and no variant is above it in most seasons.
- **Outlier-odds audit** (the research sweep's recommendation, after Clegg & Cartlidge 2024): the SBR close matches nflverse's own close exactly in 56–57% of games, and differs by 0.3 points on average. Only 6 rows differ by more than 3 points (4 spreads, 2 totals; listed by the script). Without them, every result is unchanged to the first decimal.
- **Verdict: no edge at the close.** Moves reverse slightly, about as Moskowitz finds: fading a half-point move wins 50.5–50.8% before the vig. That is nowhere near the 52.4% the vig needs. H16a is dropped.
- **Consequence for F4:** hourly history can't be justified by an outcome edge at the close. Only a reversal *before* the close (H16b, graded on CLV) could earn it; its gate is in [`odds-api-credits.md`](odds-api-credits.md#f4s-gate-h16b-reversal-before-the-close-added-september-29-2026-42).

### What to expect this season (added September 28, 2026)

Before the forward tests start, two free exercises. Neither is evidence for any rule, and neither adds variants.

**Dress rehearsal.** `scripts/rehearse_2025.py` in each weather project replays 2025 through this season's code, ledger format and unmodified scorer. Outputs: `*/output/rehearsal_2025.log`.

| Rule | Replay | Signals | Result |
|---|---|---|---|
| NFL Rule B | Archived 1- and 3-day forecasts; nflverse closes, so CLV is 0 | 17 in Weeks 5–18, 0 to 5 a week, clustered in windy weeks. 2 more were blocked by price. | 11–6 at the close |
| CFB Rule B | Observed wind as a *perfect* forecast; cfbfastR open then close, at −110 | 32 from Week 5, 1 to 8 a week | 21–10–1; open-to-close CLV +1.81 (95% CI +1.09 to +2.54). Optimistic. |
| CFB Rule HT | Last quote, the close | 43 from Week 6, about 3 to 6 a week (rerun Sep 29; was 34, about 3 to 5 a week) | 24–19 (55.8%), +2.82 units (was 19–15, 55.9%) |

Everything ran end to end: statuses, ledger rows, the 53-week date shift into the 2026 windows, and both scorers.

*Rerun, Sep 29:* pull request 48 rebuilt the CFB games table, so the rehearsal's 2025 Rule HT threshold is now computed from a 2024 mean over 1,552 games, not 948. It moved from 62.66 to 62.22, which is why Rule HT now has 43 rehearsal signals instead of 34. The frozen 2026 threshold (62.6175) and the forward test are unchanged. The NFL and CFB Rule B rows are unchanged. Both logs were rerun through the scorers as amended on Sep 29 (nfl-weather amendment 6, cfb-weather amendment 4), which also print pending and void counts.

**Simulations.** [`simulate_decisions.py`](simulate_decisions.py) runs 20,000 seasons at the pre-registered stake ([`output/simulations.log`](output/simulations.log)).

- **Swings are normal.** Even at the historical win rate, about **1 season in 3 loses money** for NFL and CFB Rule B, and 1 in 5 for Rule HT. A season that loses for a rule with no edge looks the same. At 0.5% stakes, the typical worst stretch is 1.5–3% of bankroll, and the bad cases reach 3–5%.
- **The NFL Rule B decision is underpowered this season.** About 17 signals reach Week 18.
  - It passes 43% of the time if the CLV equals the full historical open-to-close move (+0.99 points), and 13% if it's half that.
  - Expect "not proven yet" in January, not a verdict.
- **CFB Rule B at 40 signals** passes 94% of the time at the full move (+1.50 points) and 43% at half.
- **Rule HT after 2027:**

  | True win rate | Promote | Stay on paper | Drop |
  |---|---|---|---|
  | 57.7% (historical) | 25% | 60% | 15% |
  | 50% (no edge) | 1.5% | 30% | 68% |

- **The stake gate is weak.** "Paper until 20 settled signals show positive average CLV" passes **49–51% of the time with no edge at all**. Its false-pass rate is about 50%, so it isn't a filter. The keep/drop tests have false-pass rates of 2–3%, and they're what earns stakes. Changing the gate would take a dated amendment. The choice not to stake before the full decision is yours to make at any time.

### Landing-mass table: key numbers (added September 29, 2026, [#52](https://github.com/maxzipperman/value-finder/issues/52))

**Revised after an independent review:** three headline claims changed, though no effect size and no declared verdict did: the CFB landing p-value is about 0.0006 by a small-sample test (not 0.00004) and doesn't pass the multiple-testing bar; the NFL landing lead rests on the 2025 season; and the variant count is 32, not 28.

[`landing_mass.py`](landing_mass.py) builds the table and tests it. No downloads, no API calls, seasons through 2025. Outputs in [`output/`](output/):
- `landing_mass_loso.csv` (the test) and `landing_mass_loso_by_season.csv`;
- the tables themselves, one row per market line and one column per final total or margin: `landing_mass_table_nfl_totals.csv`, `landing_mass_table_nfl_margins.csv` and `landing_mass_table_cfb_totals.csv`;
- `landing_mass_prices.csv` (half-point ladders), `landing_mass_teasers.csv`, `landing_mass_calibration.csv`, `landing_mass_multipliers.csv`;
- the console log, `landing_mass.log`.

**Short answer**

- **The table does not beat the registered pricing method at the closing line.** All 8 comparisons declared before the run show no difference: NFL and CFB, all games and windy games, the under's chance and the push's chance. By the rule written before the run, nothing below claims the table prices better. Its prices are candidates for the alternate-line pull (F2) to test.
- **What it may predict better is where a game lands next to a half-point line.** That's the number a half-point buy crosses, so it's what alternate lines depend on. This readout was added after the first run, so it's a lead for the 2027 registration, not a result.
  - **CFB:** its log loss is 1.5% lower out of sample (95% interval 0.7% to 2.1%; better in 15 of 20 seasons). The p-value is 0.0006 by a t-test on the 20 seasons, or 0.003 by flipping each season's result at random. Neither passes the multiple-testing bar (0.05 / 232 = 0.00022). The effect is steady; the evidence isn't strong enough to call it proven.
  - **NFL:** 1.1% lower (0.2% to 1.9%; 8 of 11 seasons; p = 0.03 by t). But about a quarter of that gain comes from 2025, the season whose line source changed (see the data note below). Without 2025 it's 1.0% lower, better in 7 of 10 seasons, with an interval that just touches zero (−1.9% to 0.0%) and p = 0.08. **So in the NFL it isn't shown.**
- **CFB final totals cluster strongly.**
  - Totals of 41, 55, 37, 45, 69 and 51 happen about 40–65% more often than a smooth curve says.
  - 39, 46, 53, 60, 67 and 74 happen about half as often. Each is 4 more than a multiple of 7.
  - The registered method values every half-point the same, at about 5 cents. The table says a half-point across 41, 45, 51 or 55 is worth 7–8.5 cents, and one across 39, 46 or 60 about 2.5 cents.
  - **The 2.5-cent figure isn't supported** when the close sits on the number, which is the case those prices are for. Games that closed on one of the six weak totals landed there 2.0% of the time (17 of 865), not the table's 1.3%. The declared test of exactly this (the push) found no difference. At the six strong totals the table matches: 3.6% (40 of 1,109).
- **A lead in the NFL.** Since 2015, when the closing total is a whole number, the game lands on it only 1.9% of the time (28 of 1,456).
  - In 1999–2014 it was 3.5% (78 of 2,251; p = 0.006). SBR's closes, an independent source, show the same drop: 3.4% to 1.8% (p = 0.03). Neither p is near the bar, and this was found after the first run.
  - One explanation: books post a flat number mainly when a push is unlikely. That predicts more landings next to half-point closes. nflverse shows a small rise (2.6% to 3.2%), but SBR shows a fall (3.2% to 2.6%). So SBR backs only half of the story.
  - If it holds, a half-point bought off a whole-number NFL total is worth less than either model says.
- **Spreads.** The margin table prices pushes much better than a flat model: 6.6% lower log loss (interval 2.4% to 10.4%; p = 0.01 by t). This was declared in advance. It holds without 2025 (7.0%, 2.9% to 10.8%). 3 and 7 are real key numbers. But it under-predicts Wong teaser legs out of sample (71% predicted, 76% actual), so it can't price teasers.
- **This season, nothing changes.** The pricing model is frozen, and the table hasn't earned a pricing claim. Variants: 32. No p-value in this study passes the bar.

**How the table works.** P(final = k | market total T) is a smooth curve around T times a landing multiplier for k.
- **The curve** is the residual shape the registered model already uses, smoothed by 2 points.
- **The multiplier** is how often games actually finished on k, divided by how often the smooth curve expected. It's pulled toward 1 when the count is small (empirical Bayes).
- **Seasons.** NFL multipliers come from 2015 on, after the longer extra point. CFB multipliers come from 2006 on.
- **Windy tables** use the registered frozen windy cohort as their curve, with the same multipliers. So they're the registered model plus key numbers.
- **Margins** work the same way from the favorite's side. A favorite and an underdog winning by 3 share one multiplier.
- **Nothing is copied.** The script imports `p_under_at` and the frozen cohorts from both `market.py` files. The windy cohorts it rebuilds hash to the registered fingerprints (656 NFL games, 855 CFB games).

**The test.** It was declared in the script's docstring and committed (5b5eaa7) before the first run.
- Each season is predicted by a table and by the registered pricing method, both fitted without that season. The NFL is tested on 2015–2025 and CFB on 2006–2025.
- **What "registered" means here.** For windy games the comparison is the registered cohort definition (outdoor, observed wind 15+ mph), refit in each fold. For all games it is the registered method (`p_under_at` over a pool of residuals) applied to all games; no all-games cohort is registered. The registered frozen file itself is tested only on 2024–25 (last bullet below).
- CFB closes on a quarter point (972 games) are left out of both.
- The measure is log loss: lower is better. The difference is table minus the registered method, as a share of the registered method's loss. The interval comes from resampling seasons.
- **p-values** (added after review; the verdicts use only the interval). With 10–20 seasons, treating the result as a large sample overstates significance, so each comparison carries two small-sample p-values: a t-test on the seasons, and a sign-flip test (each season's result flipped at random, over every pattern). Both are in `landing_mass_loso.csv`, as `p_t` and `p_signflip`. The column `p_normal` is the old, overstated one.

| Sport | Cohort | Under wins: games | Difference (95% interval) | Push: whole-number closes (pushes) | Difference (95% interval) |
|---|---|---|---|---|---|
| NFL | All | 3,028 | +0.01% (−0.04% to +0.06%) | 1,456 (28) | +0.4% (−1.2% to +1.8%) |
| NFL | Windy | 234 | +0.03% (−0.13% to +0.18%) | 120 (3) | −4.1% (−17.5% to +3.9%) |
| CFB | All | 15,768 | −0.02% (−0.07% to +0.04%) | 6,781 (173) | −0.8% (−2.0% to +0.4%) |
| CFB | Windy | 951 | +0.02% (−0.15% to +0.20%) | 413 (11) | −2.5% (−8.0% to +3.1%) |

- **The under's chance** at the closing line is the same under both models, to within 0.1%. Key numbers barely move it.
- **NFL pushes** were where the table should have won, and it lost slightly. The next part says why.
- **CFB pushes** lean the table's way (better in 14 of 20 seasons), but the interval includes zero.
- **Windy games** are too few to tell (3 and 11 pushes).
- **Sensitivity** (every version is counted):
  - Smoothing of 1 or 4 points gives the same verdicts.
  - So does taking NFL multipliers from 1999 on and testing on 1999–2025.
  - Without the multipliers, the NFL push forecast is slightly worse than the registered method's (+0.3%, interval +0.1% to +0.5%). The CFB windy push forecast is slightly better (−0.8%, −1.6% to −0.3%).
  - A windy NFL table built only from 2015 on is worse on the under (+0.7%, +0.2% to +1.3%). 234 games are too few for a curve.
  - None of these passes the bar of 0.05 / 232 by either small-sample test.
- **The registered frozen file as it stands**, trained through 2023 and tested on 2024–25 windy games (36 NFL, 144 CFB), shows no difference.

**Added after the first run: landing next to a half-point line, and the NFL whole-number drop.** Both are leads, not results, because they were found by looking.

| | NFL, 2015–2025 | NFL without 2025 (added after review) | CFB, 2006–2025 |
|---|---|---|---|
| Half-point closes (chances to land on a neighbour) | 1,572 (3,144) | 1,287 (2,574) | 8,987 (17,974) |
| Landings | 101 | 83 | 433 |
| Table vs registered method, log loss (95% interval) | −1.1% (−1.9% to −0.2%) | −1.0% (−1.9% to 0.0%) | −1.5% (−2.1% to −0.7%) |
| Seasons the table was better | 8 of 11 | 7 of 10 | 15 of 20 |
| p-value: t-test on seasons / sign-flip | 0.03 / 0.04 | 0.08 / 0.09 | 0.0006 / 0.003 |
| The same table without multipliers | −0.05% | — | −0.01% |

- **The gain comes from the multipliers, not the smoothing.**
- **CFB: a steady effect that doesn't pass the bar.** The first write-up gave p = 0.00004 and said it would pass the multiple-testing bar. That p treated 20 seasons as a large sample. The small-sample p-values are 0.0006 and 0.003, and the bar is 0.00022 (0.05 / 232). It doesn't pass. The size of the effect and its interval don't depend on this and still hold.
- **NFL: not shown without 2025.** 2025 supplies 570 of the 3,144 chances, 18 of the 101 landings and about a quarter of the gain. It's also the season whose nflverse line source changed (the data note below). Without it, the interval's upper end sits at zero: −0.01% in this run, +0.01% in the reviewer's, which is resampling noise. The script's rule labels it a narrow "table beats", but with p = 0.08 the fair reading is no clear difference.
- **Windy games alone** have too few landings to tell (6 NFL, 27 CFB).

| NFL closing totals | Seasons | Whole-number closes | Landed on it | Half-point closes: landed on a neighbour |
|---|---|---|---|---|
| nflverse | 1999–2014 | 2,251 | 78 (3.5%) | 105 of 3,994 chances (2.6%) |
| nflverse | 2015–2025 | 1,456 | 28 (1.9%) | 101 of 3,144 (3.2%) |
| SBR | 2007–2014 | 1,121 | 38 (3.4%) | 65 of 2,026 (3.2%) |
| SBR | 2015–2021 | 937 | 17 (1.8%) | 50 of 1,894 (2.6%) |

- **Both models predict about 3%** at whole-number closes (table 3.1%, registered method 2.9%). That was close before 2015.
- **Since 2015, games land on a whole-number close about half as often.** Fisher test of the change: p = 0.006 in nflverse, 0.03 in SBR. Neither is near the bar of 0.00022. It's a lead.
- **SBR agrees on the drop but not on the other side.** Next to a half-point close, landings rose in nflverse (2.6% to 3.2%, p = 0.15) but fell in SBR (3.2% to 2.6%, p = 0.30). "Books post a flat number mainly when a push is unlikely" predicts a rise there, so SBR doesn't back that explanation.
- **On key totals the contrast is sharp:**
  - 41: 1 landing in 100 games that closed on 41, against 8 in 192 (4.2%) that closed at 40.5 or 41.5.
  - 44: 4 in 145 (2.8%) against 16 in 311 (5.1%).
- **CFB doesn't show this overall.** Its closes are a median across books, and games landed on 2.6% of whole-number closes, as both models predict.
- **A data note.** nflverse's 2025 closing totals are all half-points: none of 285 is a whole number, against 119–166 in each season from 2015 to 2024 (105–168 in 1999–2014). Only 71 of its 2025 spreads are whole numbers, against about 140 before. Its 2025 line source seems to have changed, so the push test covers 2015–2024.

**Prices from the table (step 3).** These are what the table says at a fair (no-vig) price when the market line sits on the key number.
- They aren't validated as better than the registered method's.
- They don't include the whole-number effect above.
- In these tables, "registered" is the registered method fitted on all games (1999–2025 NFL, 2006–2025 CFB). For windy games it is the registered frozen file itself.
- The full ladders for every total from 30 to 60 (NFL) and 35 to 80 (CFB), and every spread from 1 to 17, are in `landing_mass_prices.csv`.

*NFL totals.* The market total is on K. The half-point is K − 0.5 to K for an under, or K to K + 0.5.

| K | Table: P(final = K) | Registered method | Actual 2015–25, close on K | Actual, close a half-point away | Half-point worth, table | Registered method |
|---|---|---|---|---|---|---|
| 37 | 3.8% | 2.9% | 0 of 21 | 2 of 59 (3.4%) | 8 cents | 6 cents |
| 41 | 3.5% | 2.9% | 1 of 100 (1.0%) | 8 of 192 (4.2%) | 7 | 6 |
| 44 | 3.7% | 2.9% | 4 of 145 (2.8%) | 16 of 311 (5.1%) | 8 | 6 |
| 47 | 3.4% | 2.9% | 4 of 118 (3.4%) | 6 of 257 (2.3%) | 7 | 6 |
| 51 | 4.3% | 2.9% | 2 of 53 (3.8%) | 7 of 95 (7.4%) | 9 | 6 |

For contrast, 42 is the weakest total in the range: 2.0%, worth 4 cents. In windy games the table's half-points are worth 8–13 cents, against 6–8 from the registered model. The windy under's higher win rate stretches every price.

*NFL spreads.* The favorite is −K. The half-point is K + 0.5 to K, or K to K − 0.5.

| K | Table: favorite wins by exactly K | Flat model | Actual 2015–25, close on K | Close a half-point away | Half-point worth, table | Flat model |
|---|---|---|---|---|---|---|
| 3 | 8.2% | 4.6% | 44 of 433 (10.2%) | 54 of 619 (8.7%) | 18 cents | 10 cents |
| 6 | 4.3% | 4.6% | 6 of 142 (4.2%) | 15 of 278 (5.4%) | 9 | 10 |
| 7 | 5.7% | 4.6% | 11 of 172 (6.4%) | 21 of 302 (7.0%) | 13 | 10 |
| 10 | 4.1% | 4.6% | 6 of 80 (7.5%) | 3 of 112 (2.7%) | 9 | 10 |

- **The half-points next to a key number are cheaper.** At a spread of 3, those crossing 2 or 4 are worth 6–7.5 cents.
- **6 and 8 are noisy, as the issue warned.** A close on 6 landed there 3.3% of the time in 1999–2014, 6.2% in 2015–19 and 2.6% in 2020–25.

*Wong teaser legs.* Favorites of 7.5–8.5 teased down 6 points; underdogs of 1.5–2.5 teased up 6.

| | Legs | Win rate, pushes left out |
|---|---|---|
| Table, all seasons | — | 69.9–72.4% by spread |
| Table predicting held-out seasons, 2015–25 | 749 | 71.3% |
| Actual, 2015–2025 | 569–178, 2 pushes | 76.2% (95% 73.0–79.1%) |
| … closing total 49 or less | 473–140 | 77.2% |
| … closing total above 49 | 96–38 | 71.6% |

Break-even per leg:
- Two-team: −110 72.4%, −120 73.85%, −130 75.2%, −140 76.4%.
- Three-team: +180 70.9%, +160 72.7%, +150 73.7%, +140 74.7%.

What the teaser numbers mean:
- **The table can't price teasers.** It's too pessimistic about these legs, mostly the underdog ones: 77.6% actual, 72.0% predicted.
  - Favorites of 1.5 to 2.5 points finished 1.7 points worse than their spread in 2015–25 (493 games). A table that only knows the spread can't see that.
  - A 2015-only curve narrows the gap only a little (72.5%).
- **The raw record isn't significant either.** A −120 two-teamer was profitable in 2015–25, but not significantly (one-sided p = 0.08). The screen found 73.3% in 2022–25, below break-even. At −130 the 2015–25 rate is about break-even; at −140 it's below.
- **No book's actual teaser prices are in the repo.** Teasers are fixed-payout book rules with no Odds API feed ([`odds-api-credits.md`](odds-api-credits.md)), so they're priced on a grid only.

*CFB totals.* The market total is on K. Model figures are all games / windy games; the actual counts are all games, 2006–2025.

| K | Table: P(final = K) | Registered | Actual, close on K | Actual, close a half-point away | Half-point worth, table | Registered |
|---|---|---|---|---|---|---|
| 41 | 4.0% / 4.2% | 2.5% / 2.3% | 6 of 92 (6.5%) | 10 of 185 (5.4%) | 8.5 / 11 cents | 5 / 5.5–7 cents |
| 55 | 3.9% / 4.0% | 2.5% / 2.3% | 16 of 384 (4.2%) | 34 of 996 (3.4%) | 8.4 / 12 | 5 / 5.5–7 |
| 37 | 3.6% / 3.7% | 2.5% / 2.3% | 0 of 16 | 1 of 53 (1.9%) | 7.8 / 9 | 5 / 5.5–7 |
| 45 | 3.5% / 3.6% | 2.5% / 2.3% | 9 of 205 (4.4%) | 21 of 575 (3.7%) | 7.2 / 11 | 5 / 5.5–7 |
| 51 | 3.3% / 3.4% | 2.5% / 2.3% | 8 of 352 (2.3%) | 38 of 928 (4.1%) | 6.9 / 10 | 5 / 5.5–7 |
| 46 | 1.2% / 1.2% | 2.5% / 2.3% | 3 of 185 (1.6%) | 4 of 602 (0.7%) | 2.5 / 4 | 5 / 5.5–7 |
| 60 | 1.2% / 1.2% | 2.5% / 2.3% | 3 of 217 (1.4%) | 3 of 566 (0.5%) | 2.7 / 4 | 5 / 5.5–7 |

Pooled over the six strongest and six weakest totals (added after review):

| Totals | Close on K: landed on K | Table | Registered | Close a half-point away: landed on K |
|---|---|---|---|---|
| Strongest: 37, 41, 45, 51, 55, 69 | 40 of 1,109 (3.6%) | 3.6% | 2.5% | 109 of 2,897 (3.8%) |
| Weakest: 39, 46, 53, 60, 67, 74 | 17 of 865 (2.0%) | 1.3% | 2.5% | 27 of 2,450 (1.1%) |

- **The raw counts back the table when the close is a half-point away.** They back it less when the close sits on the number, and that is the case the half-point prices above are for.
  - At the strong totals the on-number rate matches the table (3.6%).
  - At the weak totals it's 2.0%, between the table's 1.3% and the registered method's 2.5%. So **the 2.5-cent figure at 39, 46, 53 or 60 isn't supported** when the close is on the number. The raw rate would put it nearer 4 cents, not far from the registered method's 5.
  - The declared push test measures exactly this, and it found no difference (−0.8%, −2.0% to +0.4%).
- **The clustering itself is solid.** Fitted separately on 2006–15 and 2016–25, the landing ratios for totals 35 to 80 have a correlation of 0.91, and every named total repeats: 41 lands 1.61 and 1.72 times as often as the smooth curve says, 39 0.46 and 0.45 times. (The reviewer ran this first; the script now reproduces it.)
- **For line shopping** (the CFB priority), this is a lead, not guidance. When two books differ by a half-point, the table says it matters more at 41, 45, 51 and 55 than at 39, 46, 53 or 60. But the table fails the declared pricing criterion (it didn't beat the registered method on CFB pushes), so its prices can't be claimed as better.
- **It's also untested against any market price.** Rule B doesn't change: its pricing model is frozen, and inside the −115 cap its gate can't reject a bet at the rule's own number anyway.

**What F2 (NFL alternates, day one of the 5M month) needs to test these prices.** As configured ([`odds5m.yaml`](../sharp-markets/config/odds5m.yaml)), F2 pulls `alternate_spreads` and `alternate_totals` at the us10 books, at T−24h and the close, for 2023–26. To test the table against the market it needs:
1. **The main line and both prices, from the same book at the same moment.** A half-point's value depends on where the main line sits. In the NFL it may also depend on whether the line is a whole number (the lead above). F1 carries the main lines, so F2's close has to be the same snapshot as F1's for each event, or F2 records the main line itself.
2. **The whole ladder, with both sides' prices.** At least every line within 3 points of the main line: that includes the ones crossing 37, 41, 44, 47 and 51, and 3, 6, 7 and 10. Also the alternates 6 points off the main spread, which are the market's own price for a Wong-style leg.
3. **A sharp alternate price, if one exists.** Whether Pinnacle posts NFL alternates through the API is for the day-one probe to check. Without it, the only fair price is the table's, and the test leans on the table.
4. **Teaser prices recorded by hand.** No feed has them. To test teasers, write down each book's two- and three-team 6-point prices on a few dates.
5. **A table frozen before any F2 row meets an outcome.** Build it walk-forward, from 2015 to the season before the one being graded, so 2023 is graded by a table that has never seen 2023. Use the primary spec here. The whole-number effect is a separate adjustment to register for 2027, not something to fold in quietly.
6. **Grading on results, not disagreement.** F2's act rule is "EV of at least +2% against the table". That measures how much a book disagrees with the table, not who's right. A flagged alternate should also be graded on its realized win rate and ROI at the price taken, and on CLV to the alternate's own close. That's an owner decision, and it has to be made before F2 is joined to outcomes.

The CFB version is F5 (CFB alternates and team totals, March, gated).

**Variants: 32** (28 in the first write-up).
- **Declared before the first run: 26.** 12 NFL totals (6 versions × 2 cohorts), 10 CFB totals (5 × 2), 1 NFL margins, 2 frozen-file checks and 1 teaser split by total.
- **Added after it: 3.** The landing readout (read on every model version and judged against the bar, so it counts; the first write-up left it out), the 2015-only margin table and the line-type check.
- **Added after the independent review: 3.** The NFL readouts without 2025, on totals and on margins (2), and the CFB raw landing checks (1).
- **Not counted:** the extra p-values (t-test and sign-flip) and the Fisher tests. They re-read comparisons already counted; they don't test anything new.
- **Running count.** It goes from 200 to 232, so the bar for new analyses becomes p < 0.05 / 232 = 0.00022. The hub updates the count.

**What this doesn't show.**
- It doesn't show a single mispriced bet: no alternate, teaser or juice price was tested.
- Books already know about key numbers, and the whole-number drop suggests they act on them.
- The two strongest results here, the landing readout and the whole-number drop, were found after the first run.
- Nothing passes the multiple-testing bar. The smallest small-sample p-value in the study is 0.00055, and the bar is 0.00022. With 10 to 20 seasons per comparison, the p-values in the first write-up were too small, because they treated the seasons as a large sample.

Rerun it from the repo root with `nfl-weather/.venv/bin/python strategy-research/landing_mass.py`. It takes about 30 seconds.

### The paper-to-money gate (added September 29, 2026, [#51](https://github.com/maxzipperman/value-finder/issues/51))

Count at merge (Sep 29, 2026): 271; bar p < 0.000185.

**Revised the same day after an independent review. The headline numbers changed:** the recommended CFB gate is safer than first stated (a no-edge rule gets through about 2.6% of the time, not 3.9%) but a little less likely to put money in this season (21% / 65%, not 24% / 66%), and the NFL bar rises from 2.14 to 2.96.

Section 4 of [`simulate_decisions.py`](simulate_decisions.py) ([`output/money_gate.csv`](output/money_gate.csv), [`output/money_gate.log`](output/money_gate.log)). It tests a staking rule, not a betting rule, so it adds **0 variants**; the running count stays at 200.

*Note, Sep 29, 2026:* the running count at the top of this file reads **271** (bar p < 0.000185); this study adds none, so it stays 271.

**The question.** Both `STRATEGY.md` files put real money in once "20 settled signals show positive average CLV". A rule with no edge passes that half the time. What should replace it, and how likely is each candidate to let money in on CFB this season?

**Short answer.**

- Today's gate isn't a filter: it passes a no-edge rule **50%** of the time.
- The recommended replacement is a **sequential gate**. It checks after every settled signal from the 10th to the 40th, with a bar that starts high and relaxes.
- With no edge, it passes on CFB **about 2.6%** of the time. That rises to 4–5% if signals cluster as much as the most pessimistic estimate.
- On CFB at 40 signals a season, the chance of real money before the bowls end is:
  - **about 1 in 5 (21%)** if the true edge is half the historical line move;
  - **about 2 in 3 (65%)** if it is the full move.
- When it passes, it typically does so in **mid-November**, and the first real-money bet follows a few days to a week later.
- **Signals move together, so textbook tests pass too often.** CFB windy games on the same day have correlated line moves (about 0.09–0.11). NFL games also share a season-wide swing. That raises the false-pass rate of every textbook test, including the **registered keep test**: about 5.5% instead of 2.7% on CFB, and 8–10% instead of 2% on NFL. The new gates are calibrated for it; the keep test isn't.
- **You can choose a lower CFB bar.** Calibrated to the realistic correlation rather than the pessimistic one, the bar is 2.48 instead of 2.75. That raises the chance of money this season to 28% / 72%. In exchange, a no-edge rule gets through about 4% of the time, or 6–7% at the pessimistic level.

**How it was measured.**

- **CLV.** Each simulated signal's CLV is drawn from the open-to-close moves of history's windy games:
  - CFB: 426 games, 2016–25, spread 2.67 points.
  - NFL: 371 games, 2007–21, spread 2.28 points.

  The moves are shifted to three truths: no edge (average 0), half the move (CFB +0.75, NFL +0.49) and the full move (CFB +1.50, NFL +0.99). Rule B enters 1–3 days out, later than the open, so the half case is probably the nearer one. Each case has 40,000 simulated runs of 40 signals.
- **Signals move together (new).** The line moves of windy games on the same day are correlated. The estimators disagree, so all of them are shown:

  | Estimator | CFB (426 games on 143 days) | NFL (371 games on 202 days) |
  |---|---|---|
  | Correlation over pairs of games on the same day | 0.09 (95% interval 0.02 to 0.16; p = 0.004) | 0.22 (−0.04 to 0.51; p = 0.001) |
  | Random-effects model (REML), day effect only | 0.11 | 0.12 |
  | The same with a season effect: day share / season share | 0.11 / 0.00 | 0.07 / 0.06 |
  | Season effect beyond the day (whole days permuted across seasons) | none (p = 0.69) | yes (p = 0.004) |
  | One-way ANOVA, the first draft's estimator | 0.17 (0.07 to 0.28) | 0.01 (−0.23 to 0.23) |

  - **The ANOVA figure is distorted by days with one windy game.** ANOVA counts their spread as a day effect.
    - In CFB, those days (62 of 143, about half of them weekdays) have noisier moves (variance 10.9 against 6.5), so ANOVA reads high. Dropping the 3 most extreme of those games (3 of 426) moves it from 0.17 to 0.13.
    - In NFL they're quieter (4.1 against 5.7), so ANOVA reads low.
    - On days with two or more games, ANOVA gives 0.09 for both sports.
  - **NFL seasons also differ as a whole.** Windy lines moved more in some seasons than others: 2007 and 2020 averaged about 1.3 points above the 15-season average, 2014 about 1.3 below. A swing shared by a whole season isn't averaged away by more signals from that season. CFB shows no such effect.
  - **Realistic case** (used in the tables): the random-effects estimate with a season effect. That's 0.11 same-day for CFB, and 0.07 same-day plus 0.06 same-season for NFL.
  - **Stress case:** the highest same-day estimate of any method (CFB 0.17, NFL 0.22), with the same season share.
  - **Model-free check:** paths built from whole real historical days, and for NFL whole real seasons in order, with no correlation model at all.
- **Calendar.** Signals arrive on the dates of the windiest games of each of the last ten seasons, replayed onto 2026:
  - CFB is aligned on Army–Navy (Dec 12, 2026); bowls keep their calendar dates.
  - NFL uses the 2026 schedule, Weeks 5–18.
  - The wind cut-off is set so a season averages 25, 40 or 55 CFB signals, or 17 or 25 NFL signals.
- **When real money starts.** Rule B logs a signal 1–3 days before kickoff, so a signal already logged when the gate passes stays on paper.
  - A signal counts as a real-money bet only if it kicks off more than 3 days after the game that made the gate pass.
  - A pass with no such signal left in the season doesn't count as "money this season".
- **Thresholds.** The issue's gates keep their textbook thresholds. The gates added here have thresholds set by simulation on separate draws. With no edge, they pass at most 5% (or 10%) of the time in every modelled case: either sport, independent signals, the realistic case, the stress case, any season volume, and 0–40% of signals with a CLV of exactly 0.
  - Checked on the main draws, the worst case is 5.0% for the 5% gates. That's the stress case at 55 signals a season.
  - The "realistic bar" is calibrated the same way, but without the stress case.
  - The recommended CFB bar is rounded up from the 2.72 this calibration needs to 2.75, as a margin for simulation and calendar error. An independently built calendar needed 2.78 at the stress level, where 2.75 passes about 5.2%.
  - There are two kinds of added gate:
    - a single look at a fixed signal count;
    - sequential gates, which look after every settled signal from the 10th to the 40th.
- **Precision.** With 40,000 paths per cell, the simulation's own error on a 5% rate is about 0.1 point. That's the smallest source of uncertainty. The inputs matter more:
  - The calendars come from 10 seasons of dates per sport (30 CFB season combinations with the bowls). A season near the wind cut-off can gain or lose a signal on a tie-break.
  - The size and clustering of CLV come from about 400 games per sport.
- **Terms.**
  - *t* is the average CLV divided by its standard error (the spread over √n). "t > 1.65" is the issue's "lower 95% bound above zero".
  - The **OBF** (O'Brien–Fleming-type) boundary is c × √(40 ÷ n): strict early, relaxing to c at the 40th signal.
  - The **constant** (Pocock-type) boundary is c at every look.

**CFB Rule B, realistic case** (same-day correlation 0.11, 40 signals a season, no zero-CLV signals). "Money this season" is the chance a real-money bet is placed before the bowls end. "Pass date" is the median date the gate passes under the full move.

| Gate | Looks at signal | Threshold | False pass (no edge): independent / realistic / stress | Passes by the 40th signal: half / full move | Money this season: half / full | Pass date |
|---|---|---|---|---|---|---|
| Mean CLV > 0 (today's gate) | 20 | – | 50% / 50% / 50% | 86% / 98% | 86% / 98% | Nov 7 |
| t > 1.65 | 20 | 1.65 | 5.5% / 9.4% / 11% | 39% / 78% | 39% / 78% | Nov 7 |
| t > 1.65 | 40 | 1.65 | 5.1% / 8.8% / 11% | 55% / 94% | 30% / 50% | Nov 21 |
| Bootstrap 90% lower bound > 0 | 20 | – | 11% / 16% / 18% | 52% / 86% | 52% / 86% | Nov 7 |
| Bootstrap 95% lower bound > 0 | 20 | – | 6.2% / 10% / 12% | 41% / 79% | 41% / 79% | Nov 7 |
| Bootstrap 95% lower bound > 0 | 40 | – | 5.5% / 9.3% / 11% | 56% / 95% | 30% / 50% | Nov 21 |
| t above a calibrated threshold | 20 | 2.33 | 1.4% / 3.4% / 4.7% | 21% / 58% | 21% / 58% | Oct 31 |
| t above a calibrated threshold | 40 | 2.34 | 1.1% / 2.9% / 4.0% | 33% / 85% | 18% / 44% | Nov 21 |
| Sequential, constant, 5% | 10–40 | 3.37 | 1.1% / 3.0% / 4.2% | 22% / 70% | 19% / 62% | Oct 31 |
| **Sequential, OBF, 5% (recommended)** | **10–40** | **2.75 × √(40/n)** | **0.7% / 2.6% / 3.9%** | **28% / 80%** | **21% / 65%** | **Nov 14** |
| Sequential, OBF, 5%, realistic bar | 10–40 | 2.48 × √(40/n) | 1.5% / 4.2% / 5.9% | 36% / 85% | 28% / 72% | Nov 7 |
| Sequential, constant, 10% | 10–40 | 2.77 | 3.2% / 6.8% / 9.0% | 38% / 84% | 34% / 78% | Oct 24 |
| Sequential, OBF, 10% | 10–40 | 2.22 × √(40/n) | 2.8% / 6.5% / 8.6% | 45% / 90% | 35% / 79% | Nov 7 |
| *Reference: the registered keep test* | 40 | 1.96 | 2.7% / 5.5% / 7.0% | 45% / 91% | – | – |

The CSV and the log also have the same rows at 30 signals, the bootstrap 90% bound at 40, the NFL, every volume, the stress case at each volume, the floors, and the gate calibrated to 2.72 (within a point of the 2.75 row everywhere).

- **Today's gate can't be fixed with a floor.** Requiring an average of at least 0.25 or 0.5 points still passes a no-edge rule 34% or 20% of the time (independent signals).
  - For every other gate, the floors almost never bind. Clearing a statistical bar at 20 or more signals already takes an average near a point or more.
- **Textbook thresholds are only right if signals are independent.** With CFB's realistic correlation:
  - t > 1.65 and the bootstrap 95% bound pass a no-edge rule about 9–10% of the time, not 5–6% (11–12% at the stress level).
  - The bootstrap 90% bound passes it 15–16% of the time.
  - **The registered keep test has the same problem.** Its false-keep rate is 5.5% instead of 2.7%. It's 7.0% at the stress level (8.2% with 55 signals a season), and 4.7% in the model-free check. That's a finding about the keep decision, not just the gate.
- **At the same 5% false-pass rate, looking often mostly beats looking once.**

  | Gate (5% level) | Passes: half / full | Money this season: half / full | Pass date |
  |---|---|---|---|
  | Single look at signal 20 (t > 2.33) | 21% / 58% | 21% / 58% | Oct 31 |
  | Sequential OBF (2.75) | 28% / 80% (by signal 40) | 21% / 65% | Nov 14 |
  | Sequential constant (3.37) | 22% / 70% (by signal 40) | 19% / 62% | Oct 31 |

  - Under the half move, the single look at signal 20 puts money in this season as often as the OBF gate (21%). The OBF gate wins under the full move and by the 40th signal.
  - The constant boundary passes earliest, typically Oct 29–31, but less often.
- **How long the recommended gate takes.** When it passes, it averages 29 signals under the half move and 26 under the full move. It still hasn't passed at the 40th signal 72% of the time under the half move, and 21% under the full move.

**NFL Rule B** (realistic case: same-day 0.07 plus same-season 0.06; 17 signals a season; the season ends with Week 18 on Jan 10, 2027).

| Gate | Threshold | False pass: independent / realistic / stress | Passes by the 40th signal: half / full | Money by Week 18: half / full |
|---|---|---|---|---|
| Mean CLV > 0 (today's gate) | – | 48% / 49% / 49% | 75% / 92% | 7.2% / 8.8% |
| t > 1.65 at 20 | 1.65 | 4.1% / 12% / 13% | 32% / 60% | 3.4% / 5.8% |
| Sequential, constant, 5% | 3.52 | 0.2% / 3.0% / 3.8% | 14% / 41% | 5.4% / 14% |
| **Sequential, OBF, 5% (recommended)** | **2.96 × √(40/n)** | **0.2% / 2.7% / 3.4%** | **16% / 49%** | **1.1% / 4.0%** |
| Sequential, OBF, 5%, realistic bar | 2.83 × √(40/n) | 0.3% / 3.3% / 4.1% | 19% / 53% | 1.4% / 4.9% |
| Sequential, OBF, the first draft's bar | 2.14 × √(40/n) | 2.2% / 9.8% / 11% | 36% / 72% | 5.3% / 14% |
| Sequential, OBF, 10% | 2.42 × √(40/n) | 1.0% / 6.4% / 7.6% | 28% / 65% | 3.2% / 9.3% |
| *Reference: the registered keep test at 40* | 1.96 | 2.2% / 7.9% / 8.8% | 34% / 72% | – |

- **The season effect changes NFL the most.** Every NFL test passes a no-edge rule more often than it claims: t > 1.65 at 20 about 12–14% of the time, and the registered keep test 8–10% (17 or 25 signals a season).
- **The first draft's bar (2.14) isn't established at 5%.**
  - In this model it lets a no-edge rule through 10–13% of the time.
  - The model-free check, which chains whole real NFL seasons, gives 4.5%.
  - That check has only 15 seasons, about 225 distinct paths. The data can't settle which figure is closer, so the plausible range for 2.14 is about 4–13%.
- **Holding 5% with the season effect takes 2.96,** or 2.83 without the stress case. The model-free check puts 2.96 at 0.5%.
- **At 17 signals a season, no NFL gate is likely to let money in during 2026:** 1.1% / 4.0% by Week 18 at 2.96.
  - The constant boundary (3.52) also holds 5%, and pays more often by Week 18 (5.4% / 14%). It pays less often by the 40th signal (14% / 41%, against 16% / 49%).
  - The sequential gates keep looking into 2027 and 2028 until the 40th signal.
- **The NFL bar has to be set before Oct 8.** The gate pools 2026 signals with later ones, so changing it once 2026 CLVs are known would break pre-registration.

**CLVs of exactly 0.** CFB's primary close is the last logged quote before kickoff, and it can be the entry row itself. Pass rates below are CFB, realistic case, 40 signals a season, in the order no edge / half / full.

| Gate | No zeros | 20% zeros | 40% zeros |
|---|---|---|---|
| Mean CLV > 0 at 20 (today) | 50 / 86 / 98% | 51 / 84 / 97% | 51 / 81 / 96% |
| t > 1.65 at 20 | 9.4 / 39 / 78% | 8.7 / 34 / 70% | 8.0 / 29 / 60% |
| t above a calibrated threshold at 20 | 3.4 / 21 / 58% | 2.8 / 17 / 48% | 2.2 / 12 / 34% |
| Sequential, constant, 5% | 3.0 / 22 / 70% | 1.9 / 15 / 54% | 0.9 / 7.4 / 33% |
| **Sequential, OBF, 2.75 (recommended)** | **2.6 / 28 / 80%** | **1.8 / 21 / 68%** | **1.2 / 13 / 50%** |
| Sequential, OBF, realistic bar 2.48 | 4.2 / 36 / 85% | 3.3 / 28 / 76% | 2.3 / 20 / 61% |
| Sequential, OBF, 10% | 6.5 / 45 / 90% | 5.3 / 37 / 83% | 4.2 / 28 / 71% |

- Zeros don't create false passes.
- They do hide a real edge. A signal whose "close" is its own entry carries no information, so 40% zeros cut the recommended gate's power under the full move from 80% to 50%.
- The constant boundary loses more (70% → 33%).
- Grading the gate on amendment 2's captured close would avoid this. That close is logged 2–20 minutes before kickoff and is never the entry row.

**On the calendar** (recommended gate: 2.75 for CFB, 2.96 for NFL; realistic case). The "Money by …" columns are in the order no edge / half / full.

| Rule, signals a season | Wind cut-off in 2016–25 | Seasons that reach 40 signals | Money by the regular-season end | Money by the season end | Pass date: half / full | First real-money bet: half / full | Real-money bets this season: half / full |
|---|---|---|---|---|---|---|---|
| CFB, 25 | about 16.6 mph | 3% | 0.9 / 8.0 / 27% | 1.1 / 9.5 / 33% | Nov 21 / Nov 21 | Nov 27 / Nov 27 | 0.6 / 2.3 |
| CFB, 40 | about 15.0 mph | 53% | 2.0 / 18 / 55% | 2.2 / 21 / 65% | Nov 14 / Nov 14 | Nov 21 / Nov 18 | 2.8 / 9.6 |
| CFB, 55 | about 13.8 mph | 73% | 2.7 / 23 / 66% | 3.0 / 27 / 75% | Nov 5 / Oct 31 | Nov 14 / Nov 7 | 7.0 / 20.1 |
| NFL, 17 | about 15.3 mph | 0% | 0.3 / 1.1 / 4.0% | same (Week 18) | Dec 14 / Dec 19 | Dec 19 / Dec 19 | 0.0 / 0.2 |
| NFL, 25 | about 13.1 mph | 0% | 1.2 / 5.2 / 16% | same (Week 18) | Dec 20 / Dec 14 | Dec 20 / Dec 20 | 0.3 / 0.9 |

When the fixed looks arrive (the share of seasons that reach the count, and the median date when they do):

| Rule, signals a season | Signal 20 | Signal 30 | Signal 40 |
|---|---|---|---|
| CFB, 25 (start Oct 1) | 60%, Nov 21 | 34%, Nov 21 | 3%, Dec 19 (a bowl) |
| CFB, 40 | 100%, Oct 31 | 73%, Nov 14 | 53%, Nov 21 |
| CFB, 55 | 100%, Oct 24 | 100%, Oct 31 | 73%, Nov 14 |
| NFL, 17 (start Oct 8) | 20%, Jan 3 | 0% | 0% |
| NFL, 25 | 90%, Dec 20 | 10%, Dec 27 | 0% |

- Seasons are lumpy: a calm autumn gives half the signals of a windy one.
- November is windier than October, but the season's last two Saturdays are thin: championship games are often indoors.
- A fixed look at 40 decides within the season only about half the time, even at 40 signals a season.

**What betting from the first signal risks** (arithmetic, not advice). Flat 0.5% of bankroll per bet at −110, no pushes. 1 unit = one bet = 0.5% of bankroll.

| Bets | True win rate | Average | 5th percentile | 95th percentile | Chance of being behind |
|---|---|---|---|---|---|
| 20 | 50% (no edge) | −0.9 units (−0.45% of bankroll) | −8.5 (−4.3%) | +6.7 (+3.4%) | 59% |
| 20 | 53.3% (half the edge) | +0.4 (+0.18%) | −6.6 (−3.3%) | +6.7 (+3.4%) | 47% |
| 20 | 56.6% (CFB windy unders' history) | +1.6 (+0.8%) | −4.7 (−2.4%) | +8.6 (+4.3%) | 35% |
| 40 | 50% | −1.8 (−0.9%) | −11.4 (−5.7%) | +7.7 (+3.9%) | 56% |
| 40 | 53.3% | +0.7 (+0.35%) | −9.5 (−4.7%) | +9.6 (+4.8%) | 40% |
| 40 | 56.6% | +3.2 (+1.6%) | −7.5 (−3.8%) | +13.5 (+6.7%) | 25% |

- At 0.5% stakes, the money at risk before the gate decides is small either way.
- A no-edge rule costs about 0.9% of bankroll over 40 bets on average, and 5.7% in a bad (1-in-20) run.
- Even at the historical edge, 1 run in 4 is behind after 40 bets, and 44% of no-edge runs are ahead. Profit can't tell the two apart this season; CLV is what the gate reads.

**Recommendation: the sequential OBF gate at 5%, with c = 2.75 for CFB and 2.96 for NFL.**

- **CFB Rule B.** After each settled signal from the 10th to the 40th, stake once the average CLV divided by its standard error exceeds 2.75 × √(40 ÷ n):

  | Signals settled | 10 | 20 | 30 | 40 |
  |---|---|---|---|---|
  | Bar | 5.50 | 3.89 | 3.18 | 2.75 |
  | Average CLV that needs, at a 2.67-point spread | – | about 2.3 points | 1.5 | 1.2 |
- **NFL Rule B.** The same with 2.96: a bar of 5.92 at 10 signals, 4.19 at 20, 3.42 at 30 and 2.96 at 40. The first draft proposed 2.14, which assumed no season effect.
- **Real money starts with the next signal alerted after the gate passes.** Signals already logged stay on paper.
- **If it hasn't passed by the 40th signal, it never passes this way.** The registered keep decision takes over. The gate never changes the keep decision.
- **False pass, CFB (2.75).**
  - 2.6% in the realistic case, and 3.1% at worst across season volumes and zero shares.
  - 3.9% at the stress level. It's 4.9% at 55 signals a season, and about 5.2% under an independently built calendar. So it's about 5% at the stress level, not a hard ceiling.
  - 1.8% in the model-free check.
  - 0.7% if signals are independent.
- **False pass, NFL (2.96).** 2.7% in the realistic case (4.0% at 25 signals a season), at most 4.9% at the stress level, and 0.5% in the model-free check.
- **Pass rates, CFB at 40 signals a season.**
  - By the 40th signal: 28% under half the move, 80% under the full move.
  - Real money before the bowls end: 21% and 65%. The gate typically passes around Nov 14, and the first real-money bet follows around Nov 18–21.
  - At 25 signals a season: 9.5% and 33%. At 55: 27% and 75%.
- **Why this one.**
  - Among the 5% gates, it has the best chance of real money this season under the full move at 40 or more CFB signals a season. Under the half move, the single look at signal 20 ties it (21%).
  - It keeps the most power when some CLVs are exactly 0.
  - It rarely passes a rule that then fails the keep test: 0.3–1.0% across the three truths, against 0.6–2.4% for the constant boundary.
  - A single calibrated look at the 40th signal passes a little more often by then (33% and 85%). But it decides within the season only about half the time.
- **Your choice on CFB: 2.75 or the realistic bar, 2.48.**

  | CFB bar | False pass: realistic / stress / model-free | Passes by the 40th signal: half / full | Money this season at 25 / 40 / 55 signals a season (half) | Same, full move | Real-money bets this season at 40 a season: half / full |
  |---|---|---|---|---|---|
  | 2.75 (recommended) | 2.6% / 3.9% / 1.8% | 28% / 80% | 9.5% / 21% / 27% | 33% / 65% / 75% | 2.8 / 9.6 |
  | 2.48 | 4.2% / 5.9% / 3.3% | 36% / 85% | 13% / 28% / 35% | 40% / 72% / 82% | 3.9 / 11.6 |

  - 2.75 errs on the side of caution. It holds about 5% even if CFB signals cluster as much as the pessimistic estimate, and about 2.6% if the realistic one is right.
  - 2.48 buys about 7 points of chance of money this season. A no-edge rule then gets through about 4% of the time, rising to 6–7% at the pessimistic level.
  - The lean is 2.75. The live CLV runs from a 1–3-day entry, not the open, and may cluster differently from this proxy.
- **Alternatives.**
  - **For speed:** the constant boundary at 5% (t above 3.37 at any look).
    - It passes about 2 weeks earlier (Oct 29–31).
    - It does better at 25 signals a season (13% and 43% before the bowls end).
    - It gives about one more real-money bet a season under the half move, and two more under the full move.
    - It loses twice as much to zero-CLV signals.
    - For NFL, where signals are scarce, it is the more likely to pay by Week 18 (14% against 4% under the full move) at the same 5%. It's a reasonable choice for NFL alone.
  - **Looser:** the 10% versions. Under the half move, they put money in this season more often (35% against 21%, CFB). They let a no-edge rule through about 6.5% of the time, or 8.6% at the stress level.

**What this doesn't show.**

- **Nothing here is evidence that Rule B has an edge.** It only sizes the gates.
- **The CLV proxy is the open-to-close move.** The live CLV runs from a 1–3-day entry to the last quote, so it will be smaller, and its spread may differ.
- **The dependence is measured on that proxy, and its size isn't settled.**
  - The CFB same-day correlation is 0.09–0.11 by the better estimators and 0.17 by ANOVA.
  - NFL's season effect rests on 15 seasons.
  - Live signals may cluster more or less. The stress case and the model-free check bracket what that does.
- **Signal dates come from observed station wind, not forecasts.** Bowl weather exists only for 2023–25 and about half the bowls, so bowl-season signals are undercounted.
- **All thresholds assume the gate reads every settled signal the scorer counts,** in kickoff order.

**Why 40?** It's the sample the CFB keep decision was registered with, and a power choice, not a law.

- With independent signals, a 40-signal average has a standard error of about 0.42 points, so the keep test clears when the average is above about 0.83.
- The full historical move (+1.5) clears that nearly always (94%). Half the move (+0.75) clears it only 44% of the time.
- At 20 signals the bar would be about 1.17 points, and half the move would clear it about 1 time in 4.
- So 40 is roughly the smallest count at which an edge of the historical size is very likely to show. It isn't enough to confirm a smaller one.
- With 25 CFB signals a season, the 40th signal arrives this season only 3% of the time. That's why the sequential gate matters: it can let money in before 40 when the evidence is strong, and never on weaker evidence than the keep test's.

### The keep test: plain, grouped by game day, and the wider of the two (added September 29, 2026)

Count at merge (Sep 29, 2026): 271; bar p < 0.000185. This changes how a test is graded, not a betting rule, so it adds **0 variants**, and the running count stays at 271.

[`keep_test_check.py`](keep_test_check.py) ([`output/keep_test_check.csv`](output/keep_test_check.csv), [`output/keep_test_check.log`](output/keep_test_check.log)) asks how often the registered keep test keeps a Rule B that has no edge, with its interval computed three ways. nfl-weather amendment 7 and cfb-weather amendment 5 register the third, the wider of the other two. The check reuses section 4 of `simulate_decisions.py` (the CLV proxy, the dependence estimates and the calendars above) without rewriting any of that script's outputs. Each case is 40,000 simulated paths of 40 bets, with seed 29; the run takes about a minute.

**The three intervals.** Each is the plain mean m of the n closing-line values plus or minus a half-width.

- **Plain:** 1.96 × sd / √n, as the scorers computed it before the amendments. It treats every bet as independent.
- **Grouped by game day:** the bets are grouped by the Eastern date of their game's kickoff. With G game days, the variance of the mean is (G / (G − 1)) × the sum over days of (that day's sum of CLV − m) squared, divided by n squared, and the half-width uses Student's t on G − 1 degrees of freedom. With fewer than 2 game days there is no interval. The first draft of the amendments registered this one alone.
- **The wider of the two (registered):** the larger of t(0.975, n − 1) × sd / √n and the grouped half-width. With fewer than 2 game days, or 2 bets, there is no interval and the decision is inconclusive. A path it keeps, both of the others keep, so it can never keep more often than either; the script checks this path by path, and it holds in every case below.

**No edge: how often each keeps the rule.**

| Sport, signals a season | Dependence | Plain | Grouped | Wider of the two (registered) |
|---|---|---|---|---|
| CFB, 25 / 40 / 55 | independent | 2.8 / 2.7 / 2.7% | 3.3 / 3.1 / 3.4% | 1.9 / 1.7 / 1.7% |
| CFB, 25 / 40 / 55 | realistic (same day 0.11) | 5.2 / 5.8 / 6.3% | 3.6 / 3.7 / 4.0% | 2.8 / 2.9 / 3.0% |
| CFB, 25 / 40 / 55 | stress (same day 0.17) | 6.6 / 7.3 / 8.7% | 3.8 / 3.9 / 4.4% | 3.3 / 3.4 / 3.8% |
| CFB | model-free, whole days resampled | 4.6% | 3.1% | 2.6% |
| NFL, 17 / 25 | independent | 2.1 / 2.1% | 2.0 / 2.0% | 1.4 / 1.4% |
| NFL, 17 / 25 | realistic (same day 0.07, same season 0.06) | 8.0 / 10.3% | 6.4 / 8.1% | 5.8 / 7.4% |
| NFL, 17 / 25 | stress (same day 0.16, same season 0.06) | 9.0 / 11.0% | 6.6 / 7.8% | 6.3 / 7.4% |
| NFL, 17 / 25 | the realistic day share alone (season share 0) | 2.6 / 2.7% | 2.1 / 2.3% | 1.7 / 1.7% |
| NFL | model-free, whole days resampled | 3.7% | 1.6% | 1.2% |
| NFL | model-free, whole seasons resampled | 5.6% | 3.2% | 3.2% |

The intended rate is 2.5%. For the NFL's two looks (nfl-weather amendment 6, section 6), with the 20-close limit and mean CLV positive in each half or season, a rule with no edge is kept, at 17 and 25 signals a season:

| Dependence | Plain at both looks | Grouped | Wider of the two (registered) |
|---|---|---|---|
| independent | 2.0 / 1.9% | 1.9 / 2.0% | 1.3 / 1.4% |
| realistic | 8.4 / 10.2% | 7.1 / 8.9% | 6.5 / 8.4% |
| stress | 9.0 / 11.0% | 7.0 / 8.6% | 6.7 / 8.4% |

The win rate against the close isn't simulated, so these are upper bounds for that criterion. No simulated path reached 40 bets in 2026, so this is the pooled look after 2027. Keep and drop both met is a drop, so here the wider test is not below the others by construction; it is below or equal in every case, and no single path is kept by it and not by the others.

**With an edge (realistic case): how often each keeps the rule.**

| Sport, signals a season | True edge | Plain | Grouped | Wider of the two (registered) |
|---|---|---|---|---|
| CFB, 40 | half the historical move | 45% | 32% | 30% |
| CFB, 40 | the full move | 90% | 79% | 78% |
| NFL, 17 | half the historical move | 34% | 29% | 28% |
| NFL, 17 | the full move | 73% | 67% | 66% |

**What it means.**

- **The plain interval keeps a rule with no edge 2 to 4 times as often as intended** once bets on the same day move together, as the historical moves did.
- **The grouped interval alone is not safe either.** With only 10 to 16 game days among 40 college football signals, a standard error built from so few days is itself noisy: with no dependence at all, it keeps a no-edge rule more often than the plain one (3.1 to 3.4% against 2.7 to 2.8%). And when each day's CLVs happen to balance around the mean it can come out narrower than the plain interval, even of zero width: 40 bets on 4 game days with equal day totals give +0.30 to +0.30 grouped, against −0.54 to +1.14 plain (with t on 39 degrees of freedom).
- **The wider of the two covers both.** It brings college football to 2.8 to 3.0% in the realistic case and 2.6% model-free; with independent signals it keeps a no-edge rule 1.7 to 1.9% of the time, below both of the others; the zero-width example takes the plain interval and is not kept.
- **It helps the NFL less:** 5.8 to 7.4% in the realistic case, 6.5 to 8.4% over the two looks. The NFL's extra comes from a swing shared by a whole season: with the day share alone, the registered test keeps a no-edge rule 1.7% of the time. Grouping by day can't correct a season-wide swing, and one or two seasons can't measure one. This is a known limit, stated in nfl-weather amendment 7.
- **It costs power.** It keeps a real edge less often too: 12 to 15 points below the plain interval in college football, and 6 to 7 in the NFL, in the table above; 1 to 2 points below the grouped interval alone.
- **Registered for both sports as an improvement**, with its remaining error stated in the amendments. Whether and when real money goes in (the paper-to-money gate, above) is a separate question the owner hasn't decided.
- **Checked twice.** Run with seed 6, the registered test's no-edge rates agree with seed 29's to within 0.3 points (plain within 0.6, grouped within 0.4). With seed 6 this script also reproduces the earlier exploration's plain and grouped tables exactly.

Rerun it from the repo root with `nfl-weather/.venv/bin/python strategy-research/keep_test_check.py [--seed 29]`.

---

## Ideas to add, ranked

Ranked by strength of evidence, whether the data comes from an API, and fit with code already in the repo.

### 1. A price engine: bet numbers, not opinions *(the most proven idea)*

- **What it is:** For every NFL and CFB market, take a no-vig fair price from the sharp books you already blend (Pinnacle, LowVig, BetOnline). Flag any price that beats it on:
  - US sportsbooks.
  - Kalshi, Polymarket, ProphetX and Novig.
  - Alternate spreads and totals, team totals, first halves, and teasers.

  Price the alternate lines and teasers from a push-and-landing table (P(margin = k | spread, total), recent era) built from nflverse margins.
- **Evidence:**
  - Kaunitz, Zhong & Kreiner (2017) made money, including with real stakes, just by betting soft odds against the consensus-implied probability. Then the books limited them.
  - Buchdahl's CLV work: CLV confirms an edge in far fewer bets than profit does, because its noise is about a tenth as large.
  - Wong teaser legs are 74.7% since 1999 (screen). That's +2.3% EV per 2-team teaser at −120 and +8.4% per 3-team at +160, but −1.5% at −120 on the 2022–25 rate. The edge is in pricing each teaser offer, not in blanket teasing.
- **Data:** The Odds API (featured markets back to mid-2020; props, alternate lines and periods back to May 3, 2023), Kalshi and Polymarket public APIs, nflverse margins.
- **Fit:** `sharp-markets` already has de-vig, the blend, the Kalshi fee model, CLV, GET-only clients and credit budgets. This adds a sportsbook and exchange list and a key-number module. Paper-log every flag with CLV.

#### The price-engine backtest, ready before F1 lands (added September 29, 2026, [#8](https://github.com/maxzipperman/value-finder/issues/8), [#53](https://github.com/maxzipperman/value-finder/issues/53))

Count at merge (Sep 29, 2026): 271; bar p < 0.000185.

- **Revised the same day after an independent review.** No headline number changed (still 38 variants, 238, p < 0.00021), and there are still no results. A lookahead hole for kickoffs that moved later is closed, spread bets whose close moved are now graded instead of dropped, and H2 must also beat the lagging book's own close. The draft's first section lists every change.
- **Written before any F1 price exists.** The backtest of this idea on F1 is written and tested before a single F1 price exists, so its thresholds can't be tuned to the data.
- **The rules were a draft for you and the hub to register; the hub registered them on September 29, 2026:** [`PRICE_ENGINE_PREREGISTRATION.md`](../sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md).
  - Flags at 1%, 2% (primary) or 3% expected value against Pinnacle's no-vig price, for NFL and CFB totals, spreads and moneylines, against Pinnacle alone and against the three-book blend.
  - Issue #53's soft-book-lag flag: a retail total a point or more off Pinnacle's. At exactly 1 point and −115 that bet is about 2% negative EV at Pinnacle's price, which the draft says plainly (owner decision 7).
- **Grading.** Everything is graded on CLV against Pinnacle's close and against the book's own close, plus the result at the price taken. A close at another number is converted to the bet's number (totals: the registered model; spreads: a margin table from the seasons before 2020), and CLV in points is shown beside it.
- **What a pass means.** If Pinnacle is right, a 2% flag should show about 1 cent of CLV, and a few hundred bets would pass almost automatically. A pass says Pinnacle wasn't the slow side; it doesn't show Pinnacle's close is right (owner decision 6).
- **Variant count.** 38 variants, which takes the running count to 238 (bar p < 0.00021). If open PR #55 merges first, 270 (p < 0.000185); the hub sets it at registration.
- **Resolution.** F1 sees each game at 16:00 UTC daily and, on busy days, at other games' closes, so it mostly misses gaps that last minutes.
- **Running it.** One command runs it the day F1 lands (`uv run markets price-engine` in `sharp-markets/`). Today it prints that there is nothing to backtest yet.
- **This season.** The draft's last page covers the live form: a college football paper log with a probability for every game, built from the call the alerts already make, at no extra credits.
- **Not done.** Issue #53's live-log lag measurement is blocked until the live logs carry PR #50's fields and a forward test is registered (2026 rows are sealed).

### 2. CFB high-total shrinkage *(new lead from your data)*

- **Rule:** A CFB closing total at least 10 points above the prior season's average closing total → under, at the latest number available.
- **Why it might be real:**
  - The calibration slope fell from 1.01 to 0.89 around 2016.
  - The effect holds in every sub-era, including after the 2023 running-clock rule (56.1%, 58.3%, 56.7%).
  - It isn't the wind rule, and the mirror (low totals → over) fails, which fits public over-betting on shootouts.
  - Possible mechanism: garbage time and running clocks in blowouts. Next check: split by spread size.
- **Why it might not be:** p = 0.0035 against a Bonferroni bar of 0.00046. The era split was chosen after looking. About 65 bets a year means a season can't settle it.
- **Grading:** CLV is the wrong primary metric here, because the rule bets *at* the close on the claim that the close is wrong. Pre-register win rate and ROI at the price actually taken, with a two-season horizon (2026 Weeks 6+ and 2027). Log CLV as a secondary check. It slots into `cfb-weather`'s board, ledger and scorer as a second rule.

### 3. Prediction-market microstructure *(extends sharp-markets to football)*

- **Deep-strike favorite-longshot bias.** Bürgi, Deng & Whelan (2026) find Kalshi contracts under 10¢ lose over 60% of stake, contracts above 50¢ earn small positive returns, and makers beat takers. Their sample is mostly non-sports. A Polymarket study (Cardozo & Rivero-Wildemauwe 2026) finds the bias "surprisingly absent in Sports." Your cache covers only strikes near the line, where Kalshi was calibrated. To test it:
  - Pull every strike of `KXNFLTOTAL` plus the spread and player-prop series (public GETs, no credits).
  - Rerun the bucket table in `screen.py`, which has game-clustered SEs.
- **Combos:** Kalshi cross-game parlays run about 3% over fair per leg (Moshrefi 2026, NBA/MLB/NHL; median 1.22× at 10 legs). The rule is never to take a combo. Selling them is outside this paper-only repo.
- **News-window lead-lag:**
  - NFL inactives come out 90 minutes before kickoff.
  - Power Four CFB availability reports are now mandatory for conference games: Big Ten since 2023, SEC 2024, ACC and Big 12 2025. The Big 12 posts its final report 90 minutes before kickoff.

  Run H2's lead-lag (Pinnacle-first vs Kalshi-first) around those timestamps.
- **Maker simulation (paper only):** From the trades tape, estimate how often a resting bid at Pinnacle fair − x¢ would fill, and what adverse selection it would suffer.

### 4. A timing overlay on every alert

- **What it is:** Attach an execution recommendation to each signal from the measured open→close drift:
  - Favorites: now.
  - Underdogs: wait.
  - NFL unders: now.
  - CFB high-total unders: at the close.
- **Fit:** Log the price at alert time and at execution, so the ledger measures the cost of waiting.
- **Evidence:** The open→close split above, and Levitt (2004): books shade toward bettor biases instead of balancing action.

### 5. Weather, extended *(builds on Rule B)*

- **Derivative markets.** When the full-game total drops for wind, do first-half totals, team totals, passing props and kicker props follow at the same speed? Odds API period and prop history (May 2023+) can answer this for 2023–25 windy games. Books often derive these from the main line. A lag is where a forecast edge would survive once the main total has moved.
- **Forecast-run timing.** Record when each forecast was issued (GFS every 6 hours, ECMWF every 12). Measure how many minutes pass before the total moves in the 5-minute Odds API snapshots. This makes `LINE LAG` precise.
- **Crosswind vs headwind.** `om_wind_dir` is already in `games.parquet`. Add stadium orientation and test whether crosswinds drive the passing and totals effects (Allen 2024 hints yes).

### 6. Low-volume NFL situationals *(paper only, pre-registered)*

- **Fade home teams off a bye:** 55.6% in 2011–25. Lopez & Bliss find markets price a bye at +0.97 points against a measured benefit of +0.31 since the 2011 CBA.
- **Week 1 unders:** 54.7% over 27 seasons.
- **Volume:** About 12–16 bets a year each. Log them in the existing ledger and let a few seasons accumulate.

### 7. Prop structure: the line against the median

- **Mechanism (restated September 29, 2026, after the research sweep and [#41](https://github.com/maxzipperman/value-finder/issues/41)):**
  - A bet that simply wins or loses depends only on where the line sits against the *median* of the outcome. A line at the median hits about 50% by construction.
  - Yardage outcomes are right-skewed, so the under has an edge only if posted lines sit above the median, towards the mean.
  - The [pre-check above](#props-how-far-the-mean-sits-above-the-median-added-september-29-2026-41) finds that skew for receiving yards (mean 7.6% above the median) and rushing yards (3.2%), but not for passing yards or receptions.
  - Unabated argues the mean-line case; no published hit-rate study exists.
- **Data and cost:** F3 in the 5M plan (NFL props, 10 books, 2023–25, plus 2026 sealed).
- **Pre-registration draft (1 variant; running count 192).** Written September 29, 2026, before any prop line was pulled or seen. It goes into a pre-registration file, unchanged or by dated amendment, before F3's rows are first joined to outcomes.

  | | |
  |---|---|
  | **Hypothesis** | Posted lines sit above the empirical median of the player's outcome, so the under wins more often than its price implies. |
  | **Sample** | F3, NFL 2023–25 regular season and playoffs. The 2026 season is sealed and opened only to confirm. |
  | **Markets** | Primary, pooled into one test: `player_reception_yds` and `player_rush_yds`, the two markets where the pre-check finds skew. Controls, reported but not tested: `player_pass_yds` (no skew) and `player_receptions` (little). The mechanism predicts no edge in the controls. |
  | **Line and price** | Each player's main line and both prices at the close, the last F3 snapshot at least 5 minutes before kickoff (`bulk.close_time`). Pinnacle, if the day-one probe shows it quotes the market in at least 80% of player-games; otherwise DraftKings. Alternate-ladder lines are out. |
  | **Metric** | Excess under rate: Σ(winᵢ − pᵢ) / n, where pᵢ is the under's probability after removing the vig by the **power method**. The additive and multiplicative methods are reported next to it. One-sided z test, variance Σpᵢ(1 − pᵢ), also with standard errors clustered by game. ROI at the actual under price is reported next to it. |
  | **Pushes and voids** | Whole-number lines that land exactly, and props voided because the player didn't play, are left out of n and counted. |
  | **Mechanism readout** | Descriptive, not graded: the line minus the player's same-season median (known only after the season), and the share of lines above it. |
  | **Decision** | **Act** (a paper forward test on the 2026 sealed season; never staked on this result alone): pooled p < 0.05 / 192, *and* a positive excess with p < 0.01 in each of 2023, 2024 and 2025 and in each primary market ([plan review](plan-review-2026-09-28.md), section 3). **Drop:** the pooled excess is at or below zero, or one market or one season carries it. **Otherwise:** no action; re-read once 2026 is unsealed. |
  | **Secondary** | The same statistic at T−24h, and the line move from T−24h to the close. Reported, not a second test. |

- **What F3 must contain for this:** the four markets above at **T−24h and the close**, with `point`, `description` (the player) and both prices, at the `us10` books including Pinnacle and DraftKings. F3 as configured already has them. Its T−48h and T−2h snapshots aren't needed for #10.
- **Fit:** it also completes step 2 of the weather-props work.

### 8. CFB's changing information environment

- **What changed:** Sinkey & Logan (2009) named CFB's thinner information, including the lack of injury reports, as a reason its market could be less efficient than the NFL's. Power Four conference games now have those reports. Non-conference and Group of 5 games mostly don't, so any information edge should concentrate there.
- **Early-season priors:** Returning production, talent composite and transfer-portal churn come from the CFBD API (free tier 1,000 calls a month; the $1 tier adds weather). The screen found no blanket early-season underdog edge (50.6%), so this needs a real model and CLV grading.

### Skip

- Primetime unders, the holdover bias, circadian and West Coast night angles, fading big covers, turnover luck, road teams, CFB big underdogs, and service-academy unders all fail or fade in the screen.
- Referee-crew totals: crew penalty rates persist, but I found no evidence they move totals beyond the price. It's also a popular media trend with heavy multiple-testing risk.
- Fade-the-public splits stay where they are. The literature supports them: Levitt (2004) finds two-thirds of bets land on the road team when the home team is the underdog, and Paul & Weinbach (2011) and Shank (2019) reportedly find contrarian profits at 70%+ one-sided action (secondhand; neither read in full). That's H3's job, pending licensed data.

---

## Data and APIs

| Source | What it adds | History | Cost |
|---|---|---|---|
| nflverse (`nflreadpy`) | Schedules and closing lines (updated every 5 min in season), play-by-play, injuries (daily), officials, depth charts, snap counts, Next Gen Stats, FTN charting | 1999+ (lines and play-by-play) | Free (CC-BY; FTN CC-BY-SA) |
| CollegeFootballData API | Lines by book with openers, talent, returning production, recruiting, portal, advanced stats, weather ($1 tier) | 2000s+ | Free 1,000 calls/mo; $1 5K; $5 30K |
| The Odds API | Multi-book odds, including Pinnacle | Featured markets mid-2020+ (5-min since Sep 2022); props, alternate lines and periods since 2023-05-03 | 10 credits × markets × regions per historical snapshot |
| Kalshi public API | Game, spread, total and prop markets; candles; trade tape with maker/taker side | 2025 NFL season+ | Free (GET); taker fee 0.07·P·(1−P) |
| Polymarket (Gamma/CLOB) | NFL and CFB games, spreads, totals and props | Varies by market | Free |
| Conference availability reports | Power Four player status for conference games | Big Ten 2023, SEC 2024, ACC and Big 12 2025 | Free; check each site's terms before scraping |

---

## Method and caveats

- **Lines:** nflverse closing lines and cfbfastR's median-book consensus, not a specific book. Opening lines are Sportsbook Reviews' 2007–21 archive (NFL) and cfbfastR openers (CFB totals). Outcomes include overtime.
- **Tests:** p-values are one-sided against −110 break-even (teasers against 73.9%), plus two-sided against 50%. The first pass fixed thresholds from the papers or round numbers. The follow-ups (sub-eras, the wind and dome exclusion, the opener, the prior-season threshold, the bye out-of-sample check) were added after seeing the first pass, and all of them count toward the 109 variants.
- **Lookahead:** The first-pass "season mean" thresholds use the whole season's closing totals. That's market information, not outcomes, but a bettor wouldn't have it. The tradeable version uses the prior season's mean and is the headline number.
- **Kalshi:** 2025 season only. The H4a pull cached strikes within 10.5 points of the book total, so prices run about 15–85¢. Candles are the last 1-minute bar at or before the snapshot. Taker P&L uses the unrounded fee.
- **What's untested here:** Ideas 1, 3 (beyond calibration near the line), 5, 7 and 8 need data this repo doesn't have yet. Each lists its source and cost.

Run it: `nfl-weather/.venv/bin/python strategy-research/screen.py` from the repo root. It takes about 40 seconds, and the console output is saved in [`output/screen.log`](output/screen.log).

---

## Sources

**Price and market structure**
- Kaunitz, Zhong & Kreiner (2017), [Beating the bookies with their own numbers](https://arxiv.org/abs/1710.02824)
- Levitt (2004), [Why are gambling markets organised so differently from financial markets?](https://pricetheory.uchicago.edu/levitt/Papers/LevittWhyAreGamblingMarkets2004.pdf), *Economic Journal*
- Moskowitz (2021), [Asset Pricing and Sports Betting](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13082), *Journal of Finance*: momentum in betting lines, too small to beat costs
- Buchdahl on CLV: [interview summary](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
- Dmochowski (2026), [The profit-bias identity in sports betting](https://arxiv.org/abs/2609.06739): a bettor lean is worthless unless the book shades the price, and vice versa (MLB)

**Prediction markets**
- Bürgi, Deng & Whelan (2026), [Makers and Takers: The Economics of the Kalshi Prediction Market](https://www.karlwhelan.com/Papers/Kalshi.pdf)
- Cardozo & Rivero-Wildemauwe (2026), [The Favorite-Longshot Bias in Prediction Markets: Evidence from Polymarket](https://arxiv.org/abs/2609.12878)
- Moshrefi (2026), [Prices, Probabilities, and Parlays](https://arxiv.org/abs/2607.14430)
- [Kalshi adds football spreads, totals and props](https://www.sportsbettingdime.com/news/betting/kalshi-expands-football-markets-to-include-spreads-props-and-totals/)
- [Novig wins CFTC approval (CNBC, June 2026)](https://www.cnbc.com/2026/06/16/novig-wins-cftc-approval-as-competition-intensifies-in-sports-prediction-markets.html)

**Situational and behavioral (NFL)**
- Paul & Weinbach (2002), [Market Efficiency and a Profitable Betting Rule: Evidence From Totals on Professional Football](https://journals.sagepub.com/doi/10.1177/1527002502003003003)
- Vergin (2001), [Overreaction in the NFL point spread market](https://www.tandfonline.com/doi/abs/10.1080/096031001752236780)
- Fodor, DiFilippo, Krieger & Davis (2013), [Inefficient pricing from holdover bias in NFL point spread markets](https://www.tandfonline.com/doi/abs/10.1080/09603107.2013.829201) (abstract)
- Davis, Fodor, McElfresh & Krieger (2015), [Exploiting Week 2 Bias in the NFL Betting Markets](https://www.ubplj.org/index.php/jpm/article/view/1014) (abstract)
- Lopez & Bliss (2024), [Bye-bye, bye advantage](https://www.frontiersin.org/journals/behavioral-economics/articles/10.3389/frbhe.2024.1479832/full)
- Smith, Guilleminault & Efron (1997), [Circadian rhythms and enhanced athletic performance in the NFL](https://academic.oup.com/sleep/article-abstract/20/5/362/2732132), and the [2013 update](https://www.sciencedaily.com/releases/2013/11/131127115357.htm)
- Shank (2019), [NFL Betting Biases, Profitable Strategies, and the Wisdom of the Crowd](https://journals.sagepub.com/doi/10.32731/IJSF.141.022019.01) (abstract via search; not read in full)
- Media trend pieces the screen tests: [primetime unders (SI, 2023)](https://www.si.com/betting/2023/11/14/nfl-week-10-betting-big-wins-bad-beats), [signal or noise (Juice Reel)](https://juicereel.beehiiv.com/p/nfl-betting-trends-signal-or-noise), [turnover randomness (Harvard HSAC)](https://harvardsportsanalysis.org/2014/10/how-random-are-turnovers/), [referee trends (Sharp Football)](https://www.sharpfootballanalysis.com/betting/nfl-referee-assignments-penalty-trends-betting-impact/)

**College football**
- Sinkey & Logan (2009), [Betting Markets and Market Efficiency: Evidence from College Football](https://www.aeaweb.org/conference/2010/retrieve.php?pdfid=406)
- [Service-academy unders (Action Network)](https://www.actionnetwork.com/ncaaf/army-vs-navy-betting-odds-over-under-history-service-academy-games)
- Availability reports: [Big 12 policy](https://big12sports.com/sports/2025/8/14/FBreporting.aspx), [SEC 2024](https://www.cbssports.com/college-football/news/sec-institutes-player-availability-injury-reports-for-all-teams-during-2024-college-football-season/)

**Key numbers, teasers and props**
- [Key numbers study, 1999–2025 (Doc's Sports, 2026)](https://www.docsports.com/2026/study-of-nfl-games-reveals-shifting-key-betting-numbers.html)
- [Wong teaser strategy (Covers)](https://www.covers.com/nfl/teaser-strategy), after Wong, *Sharp Sports Betting* (2001)
- [Mean vs median in player props (Unabated)](https://unabated.com/articles/the-biggest-mistake-youre-making-when-betting-nfl-player-props)

**Data**
- [The Odds API historical data](https://the-odds-api.com/historical-odds-data/)
- [CollegeFootballData API tiers](https://collegefootballdata.com/api-tiers)
- [nflverse data schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)

Weather-market papers (Borghesi 2007 and 2008, Paul 2017) are covered in [`../thesis-research/nfl-weather-thesis-review.md`](../thesis-research/nfl-weather-thesis-review.md).
