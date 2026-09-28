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

[`prechecks.py`](prechecks.py) ran 20 more tests on free data ([`output/prechecks.csv`](output/prechecks.csv), [`output/prechecks.log`](output/prechecks.log)). **The running count is now 129 variants, so the Bonferroni bar is p < 0.00039. Nothing passes.**

| Issue | Test | Result | Verdict |
|---|---|---|---|
| [#17](https://github.com/maxzipperman/value-finder/issues/17) favorite-longshot bias | NFL closing moneylines 2006–25, ROI backing each band of no-vig probability at the consensus price | Every band loses except short underdogs (35–50%): +1.6% ROI, p = 0.24 (n = 2,575). Longshots under 20%: −15% ROI, bias −1.4 points (se 1.4). Favorites: −3.5% ROI, which is the vig; bias −0.5 (se 0.6). | **No tradeable bias** at the consensus close, in either era. The best-price version comes off the data-use plan. |
| [#6](https://github.com/maxzipperman/value-finder/issues/6) part 1, crosswind vs along-field | Stadium headings from [greerreNFL/stadiums](https://github.com/greerreNFL/stadiums), checked against [ThompsonJamesBliss/WeatherData](https://github.com/ThompsonJamesBliss/WeatherData) (median gap 1°; 5 stadiums where the sources disagree are left out), plus ERA5 kickoff wind direction | Unders at 15+ mph: **58.97% (194–135) mostly across** vs 54.5% (169–141) mostly along. Final total minus close per mph: −0.19 across, −0.10 along (difference p = 0.18). Yards per attempt per mph: −0.030 vs −0.021 (p = 0.12). | **Consistent but not significant.** Crosswinds look like they do more damage in all three tests. Worth a pre-registered Rule B refinement for 2027 at most; Rule B stays unchanged for 2026. |
| #6 part 2 pre-check, derivative markets | nflverse play-by-play halftime scores, outdoor 2006–25 | First-half share of points: 0.515 at 15+ mph vs 0.502 calm, per mph p = 0.31. Favorite's margin minus the spread: −0.39 at 15+ mph vs +0.23 calm, per mph p = 0.27. | **Gate not met.** Wind doesn't measurably change how points split between halves or teams, so lines derived from the main total have little to lag. The first-half and team-totals pull (M4) is dropped. |
| [#4](https://github.com/maxzipperman/value-finder/issues/4) Rule HT by spread size | Run *after* Rule HT was pre-registered; descriptive only | Spread ≥ 14: **61.1% (179–114)**. Spread < 14: 55.0% (194–159). | Fits the garbage-time / running-clock mechanism. Rule HT stays as registered; this is context for its 2027 review. |

### What to expect this season (added September 28, 2026)

Before the forward tests start, two free exercises. Neither is evidence for any rule, and neither adds variants.

**Dress rehearsal.** `scripts/rehearse_2025.py` in each weather project replays 2025 through this season's code, ledger format and unmodified scorer. Outputs: `*/output/rehearsal_2025.log`.

| Rule | Replay | Signals | Result |
|---|---|---|---|
| NFL Rule B | Archived 1- and 3-day forecasts; nflverse closes, so CLV is 0 | 17 in Weeks 5–18, 0 to 5 a week, clustered in windy weeks. 2 more were blocked by price. | 11–6 at the close |
| CFB Rule B | Observed wind as a *perfect* forecast; cfbfastR open then close, at −110 | 32 from Week 5, 1 to 8 a week | 21–10–1; open-to-close CLV +1.81 (95% CI +1.09 to +2.54). Optimistic. |
| CFB Rule HT | Last quote, the close | 34 from Week 6, about 3 to 5 a week | 19–15 (55.9%) |

Everything ran end to end: statuses, ledger rows, the 53-week date shift into the 2026 windows, and both scorers.

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

### 7. Prop structure: the median beats the mean

- **Mechanism:** Yardage outcomes are right-skewed, so a line near the mean should go under more than 50% of the time. Unabated argues this, but I found no published hit-rate study. Your data could produce the first clean number.
- **Data and cost:** Odds API historical props at one pregame snapshot per game for 4 markets. That's 40 credits a game, about 34,000 for 2023–25, which fits the 100K plan.
- **Scoring and fit:** Join to nflverse player stats and score against the prop close. It also completes step 2 of the weather-props work.

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
