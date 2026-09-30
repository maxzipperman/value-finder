# A prediction-model layer: think-through of outside advice

## The hub's reading (September 29, 2026)

The hub read this memo and decided the following on the owner's standing instruction of September 29, 2026 (the hub settles research questions itself and reports afterwards; money and purchases stay the owner's).

- **"Do nothing now" is accepted.** Issue #71 stays open and parked until #10's gate is read, by about October 20, 2026.
- **D1 and D2 go as the memo advises.** No pull is added to October for a model layer, and F3b's gate stays the only way to the 2023–24 props, with no second reason written for buying them.
- **D3:** when the hub writes #10's registration, it puts in this sentence: "the sealed 2026 props are opened once, for every hypothesis registered by then".
- **D4 becomes a small job:** [#76](https://github.com/maxzipperman/value-finder/issues/76), a column in the fill log for how much a book will take.
- **D5, a backup of the paid data, is being written as its own pull request today.** A second disk, if one is bought, is the owner's purchase, and it is on his list in `STATUS.md`.
- **The hub's first opinion was wrong on the points in [section 8](#8-where-the-hub-is-wrong), and the hub accepts them,** except that it has not yet formed a view on the bar ([question 3](#9-questions-for-the-owner)), which goes to the owner.

---

*Strategy research · September 29, 2026 · Issue [#71](https://github.com/maxzipperman/value-finder/issues/71) · A memo for the hub and the owner. It recommends; it decides nothing.*

**Why the owner asked.** "Just being comprehensive." He isn't set on building a model layer. He wants to be sure nothing worth having is being missed. So this memo leans on the inventory and the gaps, and "do nothing" is a full answer throughout.

**What was done, and what wasn't.**

- **No model was fitted and no test on results was run.** Nothing here compares a predictor with an outcome, so the variant count stays at 273 (bar p < 0.000183).
- **No API was called** (odds, weather or markets), nothing was bought, and no 2026 game was read. Every count below is filtered to seasons through 2025 before anything is counted.
- **What was run:** two row counts on committed tables and one sheet of power arithmetic ([Appendix B](#appendix-b-the-counts-and-the-arithmetic)).
- **What was read:** the repo's own documents and output tables, and the papers in [Appendix A](#appendix-a-sources-and-how-each-was-checked). Each paper is marked as read in full, read as an abstract, or recalled and not verified.
- **No rule, registered document or code was changed.** This file is the only new file. `STATUS.md` was updated only at merge, with the hub's reading above.

**The advice, quoted as data.**

> Your core prediction layer should be things like XGBoost/LightGBM/CatBoost, logistic models, Bayesian hierarchical models, Elo-style systems, time-series models, Monte Carlo simulation, calibration, and ensembles. Those should output probabilities. Then compare those probabilities against the market-implied probabilities after removing vig.
>
> Sportsbooks -> odds snapshots -> database -> feature generation -> predictions -> edge calculation -> monitoring -> LLM analysis.
>
> For each market, you might be storing: book x game x market x selection x timestamp x price. That explodes into a lot of observations very quickly. Then you're doing things like: P(model) vs P(market); line movement; cross-book dispersion; closing-line-value analysis; injury adjustments; player projections; correlated markets; historical analogues; simulation.

---

## The short answer

- **Is anything worth having being missed? From the advice's list, nothing that is worth having today.** Of its 24 distinct items, 17 exist in whole or in part, or arrive in October. Seven are missing, and six of those aren't worth building at this project's size. One, player projections for props, may be worth having later, behind a gate.
- **Three gaps are worth closing, and the advice names none of them.** None is a model:
  - a measurement of how much a book will actually take;
  - a decision on the multiple-testing bar;
  - a backup of the data the month buys.
- **Your instinct is mostly right.** It isn't too early to think about it. It is too early to build it, and most of it points away from what this project is good at.
- **A model layer already exists here, and it has been tested.** The NFL "model lean" is a logistic model on a registered paper test. In `nfl-weather/scripts/model_compare.py`, a gradient-boosted model of the under did worse than quoting the league's average under rate (5,352 games, 2006–25, each season predicted from earlier ones). The logistic model beat the average by less than half of one percent of log loss, which is a score of how good a probability forecast is.
- **The published record mostly says the same, in all three sports.** Where a study scores models against the betting line, the line is the more accurate forecast (college football: Fair and Oster 2007; NBA: Manner 2016; NFL: Boulier and Stekler 2003), except one NFL test of 110 games (Glickman and Stern 1998), whose authors decline to generalize it. The samples are old (1998–2001, 2006–14 and 1994–2000), and Manner compares against the opening line, not the close. A few papers report backtest profits; none reports a pre-registered test, as far as their abstracts show, and one of them bets a single season.
- **The deeper problem is proof, not software.** Graded on results, a model that truly wins 54% needs about 18,400 bets to clear this project's bar (about 11,100 at the family bar of [question 3](#9-questions-for-the-owner)). The NFL plays 285 games a season. Only a rule that bets early and is graded on closing-line value can be decided here, in about 700 bets for 1 cent.
- **This project already works the better way round.** It starts from the market's price and tests one small thing the market might miss. The advice starts from a model and asks where it disagrees with the market. With a noisy model, most of that disagreement is the model's own error.
- **Nothing a model layer needs has to be bought before October 20.** The Odds API's history doesn't expire, a March month is already planned, and about 2.1 million credits are unallocated even if every gate passes.
- **Compute was never the constraint.** The new Mac Studio helps in two ways that matter, and neither is speed: it can stay awake for the scheduled jobs, and it has the disk. It doesn't add a single game.
- **Recommendation: do nothing now.** One option can be kept behind a gate, and dropping it is an equally good answer. The details are in [section 7](#7-the-recommendation).

---

## 1. Inventory

What the repo has, what arrives in October, and what is missing, for each part of the advice. "Thursday" is October 1, 2026, day one of the 5M month.

### The core prediction layer

| Part of the advice | Already in the repo | Arrives in October | Missing |
|---|---|---|---|
| Gradient boosting (XGBoost, LightGBM, CatBoost) | One try: a gradient-boosted P(under) on weather, the posted total and the spread, in [`nfl-weather/scripts/model_compare.py`](../nfl-weather/scripts/model_compare.py). Result in [`model_compare.csv`](../nfl-weather/output/tables/model_compare.csv): worse than the base rate on all games and much worse on the 466 windy games. It was one hand-set configuration on weather inputs, so it is evidence about that kind of model, not about every model. | Nothing | Nothing worth adding for game markets |
| Logistic models | The NFL model lean: a logistic model of P(under) on weather bins, `fit_under_model` in [`nfl-weather/nflweather/market.py`](../nfl-weather/nflweather/market.py), pre-registered and on paper ([`nfl-weather/STRATEGY.md`](../nfl-weather/STRATEGY.md), "Watch"). The college version isn't used (52.8% at P ≥ 53% in [`walkforward.csv`](../cfb-weather/output/tables/walkforward.csv)). A kicking logit is in `kicking_logit.csv`. | The model lean's forward test is scored from Week 5 (October 8) | Nothing |
| Bayesian hierarchical models | None. The nearest things: the landing-mass table pulls its multipliers toward 1 when counts are small ([`landing_mass.py`](landing_mass.py)), and the money-gate study fits a day and season random-effects model ([`simulate_decisions.py`](simulate_decisions.py), section 4). | Nothing | **A hierarchical model of anything** |
| Elo-style ratings | None built. CollegeFootballData's own pregame Elo is a column in `cfb-weather/data/processed/games.parquet` (`home_pregame_elo`, `away_pregame_elo`); no rule or test reads it. | Nothing | **A rating built here,** and any rating for the NFL or the NBA |
| Time-series models | Line moves only: fade the move at the close ([`fade_move_sbr.py`](fade_move_sbr.py), dropped), reversal before the close (H16b, registered in [`odds-api-credits.md`](odds-api-credits.md)), and Kalshi lead-lag (`sharp-markets/src/markets/analysis/leadlag.py`). | H16b runs on F1 | **A model of team strength over time** |
| Monte Carlo simulation | Simulation of the decisions, not of games: 20,000 seasons in [`simulate_decisions.py`](simulate_decisions.py), 40,000 paths in [`keep_test_check.py`](keep_test_check.py). For totals, the frozen residual cohort does the job a game simulation would do (`p_under_at` in `market.py`). | Nothing | **A simulation of games or of players** |
| Calibration | The calibration slope of results on closing totals ([`output/calibration_slopes.csv`](output/calibration_slopes.csv)), which is where Rule HT came from; the Kalshi ladder ([`output/kalshi_ladder.csv`](output/kalshi_ladder.csv)); the favorite-longshot check (#17); the frozen forecast-to-station wind calibration. | The price engine's report prints how well Pinnacle's no-vig close matched results on every game it priced (descriptive, no variant) | Nothing |
| Ensembles | The three-book sharp blend, weights 0.55, 0.30 and 0.15 (`blend` in `sharp-markets/src/markets/devig.py`, fixed in the price engine). | The blend is the price engine's second fair price | Nothing worth adding |
| Output probabilities, compared with the no-vig market | [`bet_model_vs_market.csv`](../nfl-weather/output/tables/bet_model_vs_market.csv): the NFL model's P(under) against the de-vigged close, 8 variants already counted. The price engine: [`PRICE_ENGINE_PREREGISTRATION.md`](../sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md). | The price-engine run, 38 variants, the day F1 lands | Nothing |

### The pipeline

| Box | Already in the repo | Arrives in October | Missing |
|---|---|---|---|
| Sportsbooks to odds snapshots | The alerts log 10 books four times a day; close capture every kickoff slot ([`ops/capture_closes.sh`](../ops/capture_closes.sh)); the bulk puller ([`sharp-markets/docs/ODDS5M_DAY_ONE.md`](../sharp-markets/docs/ODDS5M_DAY_ONE.md)). | F1 (10 books, daily and every close, 2020–26), F2, F3a, the NBA sample week; the trigger poller, the props log and the NBA collector ([`ops/LIVE_USES.md`](../ops/LIVE_USES.md)) | Nothing |
| Database | Three stores: DuckDB for the Kalshi pipeline (`markets.duckdb`, Mac only, schema in [`PLAN.md`](../sharp-markets/docs/PLAN.md) section 5); parquet tables in `*/data/processed/`; F1 as cached responses with a manifest, read by `bulk.load_rows`. | The manifest and caches fill | One database across sports. Not needed yet. |
| Feature generation | Weather features (`features.py`); team box scores with EPA (`team_games.parquet`); CFBD returning production, talent and team box scores (`cfbd_*.parquet`). | Nothing | Team strength, injuries, player projections (counted below) |
| Predictions | The model lean and the registered pricing model. | Pinnacle's no-vig price for every college game, four times a day, if the live log in the price-engine file is built | Nothing beyond the rows above |
| Edge calculation | `ev_under` in `market.py`; the price engine's expected value against the Shin no-vig price; the Kalshi edge net of fees (`v_analysis`). | The price-engine report | Nothing |
| Monitoring | Alerts, `runs.csv`, the scorers, the dashboard and the menu-bar light. | The forward tests start: October 1, 7 and 8 | Nothing |
| LLM analysis | None in code. The hub and its workers are language models doing the research. The hub's review of a decision model on September 28 found no use for one at any of 96 decision points (a hub memory note, not a repo file), and left one opening: a hand-labelled log of college availability news ([section 8](#8-where-the-hub-is-wrong), point 3c). | Nothing | **A language model inside the pipeline** |

### The per-market list

| Item | Already in the repo | Arrives in October | Missing |
|---|---|---|---|
| Book × game × market × selection × time × price | The `sharp_odds` table (PLAN.md section 5); the ledgers; `closes.csv`. | F1's rows | Nothing |
| P(model) against P(market) | As above. | The price engine, where the model is Pinnacle | Nothing |
| Line movement | SBR opens and closes, NFL 2007–21; cfbfastR opens and closes; [`output/line_moves.csv`](output/line_moves.csv). | F1's daily grid; the 10-minute trigger poller | Hourly history (F4, gated) |
| Cross-book dispersion | `total_sd` and `n_books` in the college games table; `blend_std` in the `sharp_fair` view; the best line on every alert row. | The price engine's table of how often each book sits a point or more off Pinnacle | Nothing |
| Closing-line value | Both scorers; close capture; PLAN.md section 6. | The price engine grades every flag on it | Nothing |
| Injury adjustments | None. Sources are named in the backlog (#11). | Nothing | **All of it** |
| Player projections | None. The outcomes are on disk: `player_week.parquet` (476,159 player-weeks, 1999–2025, counted with the season filter). [`props_median_check.py`](props_median_check.py) measured the skew a line-setter faces. | F3a: the first prop prices the project has ever held | **A projection** |
| Correlated markets | The same-day correlation of closing-line moves is measured (0.09 to 0.11 in college football) and the keep test allows for it. The first-half and team-totals pre-check failed. | Nothing | Same-game combinations. Out of scope: no venue the owner named prices them fairly. |
| Historical analogues | The pricing cohort is exactly this: 656 NFL and 855 college games with 15+ mph wind. The spread table takes the 1,000 games priced nearest a spread. | Nothing | Nothing |
| Simulation | As above. | Nothing | As above |

**Reading the tables.** The 26 rows hold 24 distinct items, because simulation and the comparison of model with market each appear twice. 17 exist in whole or in part, or arrive in October (most on Thursday; the forward tests on October 7 and 8, and the NBA collector's Kalshi depth log on October 20). Seven are missing, in bold above: three wholly (a hierarchical model, injury adjustments, player projections) and four in the form the advice means (team ratings, a team-strength time series, a simulation of games, a language model in the pipeline).

A hierarchical model is one that estimates many small groups at once and pulls each toward the average of all of them. It is the usual tool when each group has few observations.

### The gaps, and whether each is worth having

The first eight come from the advice: the seven missing items, and one database across sports, which the inventory counts as present (three stores) and which is listed here as a design choice. The last four are gaps the inventory turned up that the advice doesn't mention.

| Gap | Worth having? | Why | If so: when, and at what cost |
|---|---|---|---|
| Player projections | **Perhaps, later** | Props are the one market with no sharp price and a large sample. Whether anything is left over there is what #10 tests on Thursday's data. | January, about 4 worker-days, behind a gate ([section 6](#6-the-smallest-useful-version)) |
| A hierarchical model | Only as the player median above | It is the right tool when each unit has few observations, as a player has 8 to 16 games. For the wind pricing model it changes no bet ([section 8](#8-where-the-hub-is-wrong)). | The same |
| Injury adjustments | No | The project's rules start from the market's price, which already holds the injury news. Only a model built from scratch needs its own. | — |
| Team ratings | No, not now | Nine rating systems added nothing to the college line (Fair and Oster 2007). CFBD's Elo is already on disk if it is ever wanted. The one open use, early-season college games (#11), can't be tested before August 2027. | — |
| A team-strength time series | No | The same evidence as ratings | — |
| A simulation of games | No | For totals and spreads the frozen cohort and the landing-mass table already do it, and the richer table was no better (#52). | — |
| A language model in the pipeline | No | News is a race the project can't run, and there is no labelled text yet to check a model against. The one opening the hub's September 28 review left, a hand-labelled log of college availability news, would create that text; it is a log, not a model in the pipeline ([section 8](#8-where-the-hub-is-wrong), point 3c). | — |
| One database across sports | Not yet | Three stores work at today's size. Look again only if F4 or N1 is pulled. | — |
| **How much a book will take** | **Yes** | Every idea that survives ends at a retail book or on Kalshi, and nothing in the repo measures size. The price-engine file records it as unknown for every flag. It also says the stake is recorded in the paper fill log where it's known ([`PRICE_ENGINE_PREREGISTRATION.md`](../sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md), section 11 and the live form), but the fill log (`scripts/log_fill.py`) has no column for it: it writes the time, game, rule, line, price and book. The registration and the code disagree. | Free, forward only. A small job for the hub. Both scorers read `fills.csv` for their cost-of-waiting report, so a size field must leave `score_forward.py`'s grading unchanged; whether it needs a dated note is the hub's call. |
| **A decision on the bar** | **Yes** | The plan review called one bar over every variant "unclearable by any sports edge" at these sample sizes and proposed families of tests with their own bars. It is still undecided. It matters more than any model class. | An owner decision ([question 3](#9-questions-for-the-owner)). No work. |
| **A backup of the paid data** | **Yes** | "Paid data can't be re-created without paying again" ([`odds-api-credits.md`](odds-api-credits.md), "Before you buy", item 6), and the same item goes on: "Keep `*/data/raw/oddsapi*` in an encrypted backup outside git." The rule exists; the gap is that no step carries it out. I found none in the day-one checklist or in `ops/`, and no Time Machine destination is set on the laptop (checked September 29). | A second disk, ready before Thursday's pull: an external drive (the owner's purchase, roughly $60 to $150 for 1 to 2 TB; a typical retail range, not a quote), or the Mac Studio over the network at no extra cost |
| How much a prop line moves in its last day | Already planned | No power statement about props is possible without it. It is #10's secondary readout. | Free, inside #10 |

---

## 2. Model by model

### The facts every class shares

**The samples** (counted from committed tables, seasons through 2025):

| Market | Games a season | Seasons with prices | Games in all |
|---|---|---|---|
| NFL sides and totals | 285 since 2021 (267 in 2002–19) | 27 with a closing spread and total (1999–2025); 20 with over and under prices (2006–25) | 7,276; 5,292 with prices |
| NFL at several books with timestamps | 285 | 6 (2020–25), from F1 on Thursday | 1,693 |
| College football totals, FBS-involved | 849 to 934 in 2021–25 (FBS-involved with a consensus close, the same filter as the 14,383) | 20 with a consensus close (2006–25) | 14,383 |
| College football at several books with timestamps | about 900 | 6 (2020–25), from F1 | 5,147 |
| NBA | about 1,320 with playoffs (the plan's estimate) | 6 full seasons that The Odds API sells (2020-21 to 2025-26), plus the 2019-20 restart (171 games; history from June 27, 2020); only the sample week is cached | about 7,770 in the six full seasons, plus 171 in the restart; none on disk |
| NFL player props | 285 games | 3 (2023–25); prop history starts May 3, 2023 | 855 games. As a rough proxy for the two skewed markets: 2,342 rushers with 8+ carries and 6,041 receivers with 4+ targets, about 8,400 player-games. Posted lines aren't on disk, so the real count is unknown until F3a lands. |
| Windy games (the pricing cohort) | about 25 NFL, about 50 college | 25 and 18 | 656 and 855 |

**The bar and what it takes to clear it** (80% power; [Appendix B](#appendix-b-the-counts-and-the-arithmetic)):

| Graded on | True effect | Bets needed at p < 0.05 | Bets needed at the project's bar (0.05 / 273) | Bets needed at a family bar (0.05 / 10, [question 3](#9-questions-for-the-owner)) |
|---|---|---|---|---|
| Results at −110 | wins 53% | 40,200 | 126,000 | 75,900 |
| Results at −110 | wins 54% | 5,900 | 18,400 | 11,100 |
| Results at −110 | wins 55% | 2,240 | 7,000 | 4,240 |
| Profit | a 2% edge | 15,500 | 48,500 | 29,200 |
| Closing-line value, 6 cents of noise per bet | 0.5 cents | 890 | 2,800 | 1,680 |
| Closing-line value | 1 cent | 220 | 700 | 420 |
| Closing-line value | 2 cents | 56 | 175 | 105 |

**What follows from the two tables.**

- **A model that bet every NFL game with prices since 2006** (5,292) at a true 54% would clear the bar on results about 1 time in 9. At a true 55%, 6 times in 10.
- **One that bet every college total since 2006** (14,383) would clear it about 6 times in 10 at a true 54%, and nearly always at 55%.
- **No model bets every game.** One that flags a quarter of them has a quarter of the sample: 1,300 NFL bets and 3,600 college bets in twenty seasons, against the 7,000 that a true 55% needs. And it has to do this on seasons it has never seen.
- **At a family bar the history looks less hopeless.** 5,292 NFL bets would clear it about 4 times in 10 at a true 54% and 9 in 10 at 55%; a quarter of college games (3,600 bets) about 7 times in 10 at 55%. But under the protocol in [section 4](#4-the-protocol) those seasons are for building and rehearsal and can't confirm anything, and a forward test at about 300 football bets a season would still need about 14 seasons to show a true 55%.
- **So, at the project's bar, a model graded on results can't be decided here in any useful time, whatever its class.** At a family bar the conclusion is weaker but holds for anything that has to be confirmed going forward. It depends on the bar, which is the owner's question 3. Only a model that bets before the close and is graded on closing-line value can be, and that is a claim about where the line will move, not about who wins.

### Class by class

"Variants if done honestly" counts every configuration that is compared with results, as the project's rule requires. The lower figure assumes every setting is fixed blind before any run.

| Class | The question it could answer better than what exists | Data it needs | Variants if done honestly | Could a plausible effect clear the bar? | Published evidence, model against line |
|---|---|---|---|---|---|
| **Gradient boosting** | For sides and totals: none. The repo's one try lost to the base rate. For props: possibly, how a player's yards depend on usage, opponent and game script together. | Game markets: on disk. Props: `player_week.parquet` and F3. | 4 if one configuration is fixed blind (2 sports × 2 markets). A small honest search is 36 configurations (3 depths × 3 learning rates × 2 sizes × 2 feature sets) per sport and market: 144. | On results, no. On closing-line value, only as an early-entry rule. | None I can name and verify for this class in the NFL, college football or the NBA. The two NBA machine-learning papers (Hubáček, Šourek and Železný 2019; Walsh and Joshi 2024) report backtest profits; see the evidence table. |
| **Logistic models** | The right size of model for these samples, and the one the project already uses. With the market's probability as the starting point, each added term is one rule. | On disk | 1 per term, market and sport: 2 to 8 | The model lean's registered cut (P ≥ 55%) went 56.4% on 629 bets, p = 0.023, walk-forward 2006–25 at −110 ([`bet_walkforward.csv`](../nfl-weather/output/tables/bet_walkforward.csv)), far from the bar. On closing-line value, yes in principle. | Boulier and Stekler 2003 (NFL): probit forecasts from power scores were second to the betting market. Gray and Gray 1997 (NFL): probit rules profitable in sample, confirmed out of sample only in part. |
| **Bayesian hierarchical** | Two honest uses. (a) How large is the wind edge now, shrunk across eras, to set expectations for January. (b) A player's median yards, shrunk toward his position, against a posted prop line. The hub's use, a hierarchical pricing model, is discussed in [section 8](#8-where-the-hub-is-wrong). | (a) on disk. (b) `player_week.parquet` and F3. | About 10: 3 pooling structures × 2 priors, plus 2 to 4 graded cells | (a) is descriptive and clears nothing. (b) on closing-line value, perhaps. | Glickman and Stern 1998 (NFL): a Bayesian state-space model was "comparable" to the line on 110 games, by the authors' own word not enough to generalize. Lopez, Matthews and Baumer 2018 build their state-space model *from* betting prices. Egidi, Pauli and Torelli 2018 (soccer) feed bookmaker odds into the model. |
| **Elo-style ratings** | Early-season college football, where last year's results and roster turnover are all anyone has (#11). Not the NFL or NBA. | CFBD returning production and talent (on disk); openers (CFBD from 2021, cfbfastR totals 2012–19); F1's daily grid. | 2 to 4 with published settings taken blind. A tuned rating has 4 knobs (update speed, home edge, margin weight, carry-over): 54 settings at 3 × 3 × 2 × 3. | On results, no. From the opener to the close, perhaps; this is next August's question, not October's. | Fair and Oster 2007 (college football): nine rating systems and their best combination hold nothing that the final line doesn't. FiveThirtyEight's NFL Elo reportedly won 51% against the spread (secondhand; not verified). |
| **Time-series models** | Line moves: H16b already asks the first question on F1. A richer model waits for that result. | F1; F4 only through its gate | 2 are registered. A richer model adds 12 or more (lags × thresholds). | On closing-line value, yes: that is H16b's design. | Moskowitz 2021: moves partly reverse, too little to beat costs. Simon 2024 (MLB): line changes are negatively autocorrelated. Both are in the repo's sources; neither was opened again here. |
| **Monte Carlo simulation** | Sizing decision rules, which the project already does well. Pricing derivative markets from a simulated game: the empirical cohort and the landing-mass table already do this for totals and spreads. | On disk | 0 when it sizes a decision rule. 4 to 10 when each simulated price is graded against a market. | Not applicable: simulation is a tool, not a hypothesis. | None needed |
| **Calibration** | Whether the market's own price is off in a systematic way. This is the project's most productive tool: Rule HT is a calibration finding (slope 0.89, standard error 0.025, [`calibration_slopes.csv`](output/calibration_slopes.csv)). | On disk; F1 for Pinnacle's close | 0 while descriptive (the price-engine file's own reasoning). 1 per market once a recalibrated price drives a bet. | Rule HT: p = 0.0035, not near the bar, and graded on results over two seasons. | Walsh and Joshi 2024 (NBA): choosing a model on calibration beat choosing on accuracy, in one season of betting. A 2025 corrigendum revised the paper's results and, by a search summary of it, kept this conclusion; its text couldn't be opened here (see the evidence table). |
| **Ensembles** | None beyond the sharp blend. Averaging home-built models averages their noise, not the market's information. | None | 0 for the fixed blend. 5 to 10 once weights are fitted. | No | Manner 2016 (NBA): model plus spread is "statistically not worse" than the spread alone. Fair and Oster 2007: the best combination of rating systems adds nothing to the line. |

### The evidence, and how far it goes

| Study | Sport and sample | What it found | How I checked it |
|---|---|---|---|
| Fair and Oster (2007), *College Football Rankings and Market Efficiency*, Journal of Sports Economics 8(1) | College football, 1,582 games, 1998–2001, nine computer ranking systems | The best combination of systems picks 72.9% of winners; the final Las Vegas spread picks 74.7%. With the spread in the regression, no system's coefficient is significant (F = 0.96 against a critical value of 2.10) and the spread's coefficient is 1.03. | Read in full |
| Manner (2016), *Modeling and forecasting the outcomes of NBA basketball games*, Journal of Quantitative Analysis in Sports 12(1) | NBA, eight seasons, 2006–14, the second half of each season predicted | Squared error 137.5 for the *opening* spread against 142.2 to 143.1 for three models; the models are significantly worse; model plus spread is not significantly different from the spread. | Read: the author's working-paper version of November 2015 |
| Glickman and Stern (1998), *A State-Space Model for National Football League Scores*, Journal of the American Statistical Association 93 | NFL, data from 1988–93, tested on the last 110 games of 1993 | Model squared error 165.0 against 170.5 for the line; 64 winners against 63. The authors: "the difference is not large enough to generalize". | Read: the results section |
| Boulier and Stekler (2003), *Predicting the outcomes of National Football League games*, International Journal of Forecasting 19 | NFL, 1994–2000 | The betting market was the best predictor, then probit forecasts from power scores. | Abstract only |
| Štrumbelj and Vračar (2012), *Simulating a basketball match with a homogeneous Markov model and forecasting the outcome*, International Journal of Forecasting 28(2) | NBA | The model matches other statistical approaches; bookmaker odds were the best probabilistic forecasts. | Abstract only |
| Hubáček, Šourek and Železný (2019), *Exploiting sports-betting market using machine learning*, International Journal of Forecasting 35(2) | NBA, 2007–14 | Positive cumulative profits, from a model trained to be *less* correlated with the bookmaker, with bets sized as a portfolio. The size of the profit and the prices used were not verified. | Abstract only |
| Walsh and Joshi (2024), *Machine learning for sports betting: should model selection be based on accuracy or calibration?*, Machine Learning with Applications 16 | NBA, several seasons of training, one season of betting | Choosing models on calibration beat choosing them on accuracy, in one season of betting. The paper as first published reported returns of +34.69% against −35.17%; those are the original figures, revised by a 2025 corrigendum (*Machine Learning with Applications* 19, doi 10.1016/j.mlwa.2025.100627) that corrects errors in the authors' code. By a search engine's summary of it, the errors were in the feature-engineering steps, affected all later results, and left the conclusion unchanged. **The corrected figures, and that summary, are not independently confirmed.** | Abstract only. The corrigendum's existence, date and subject were checked in its Crossref record and in the authors' GitHub notice; its text couldn't be opened (the publisher refused access). |
| Gray and Gray (1997), *Testing Market Efficiency: Evidence from the NFL Sports Betting Market*, Journal of Finance 52(4) | NFL | Probit betting rules profit in sample; out of sample some are confirmed and the rest are inconsistent. | Abstract only |
| Zuber, Gandar and Bowers (1985), *Beating the spread*, and Sauer, Brajer, Ferris and Marr (1988), *Hold your bets*, both Journal of Political Economy | NFL | The first reports profitable rules from a model. The second is a comment on it; I recall that it shows the result did not hold on other seasons. | Citations verified; the content of the second is recalled, **not verified** |
| FiveThirtyEight, *Introducing NFL Elo Ratings* (2014) | NFL | Elo reportedly picked 51% against the spread in its own backtest. | **Not verified.** Secondhand; the original page now redirects elsewhere. |

**What the evidence supports, stated carefully.**

- **On accuracy, it is consistent.** Every study above that scores a model against the line finds the line at least as accurate, except one test of 110 games whose authors decline to generalize it.
- **On profit, it is mixed and weak.** Four papers report backtest profits (Zuber, Gandar and Bowers; Gray and Gray; Hubáček, Šourek and Železný; Walsh and Joshi). One bets a single season, and published results lean toward the ones that worked.
- **What it doesn't cover.** None of these is about player props. The college football study's games are 25 years old. Manner compares with the opening line, which is a weaker benchmark than the close, and the models still lost.
- **A gap I couldn't fill.** I know of no verified study of gradient boosting against closing lines in these three sports. The case against it here rests on the repo's own try and on the power table, not on a paper.

---

## 3. From scratch, or from the market's price?

### The two designs

| | From scratch | From the market's price |
|---|---|---|
| What is predicted | The result, from features | The part of the result the no-vig price doesn't explain |
| What it must get right first | Everything the market already knows: injuries, matchups, rest, weather, who is betting | Nothing. It starts with all of that for free. |
| What a finding looks like | "The model says 56%, the market says 52%" | "In games like these, the market's 50% has been 56%" |
| How variants are counted | Hard. Every setting of a flexible model is a look. | Easy. One added term is one rule. |
| Examples here | The gradient-boosted model in `model_compare.py` | Rule B, Rule HT, the model lean against the de-vigged close, the price engine |

### Why the second design wins at this scale

- **Most of a noisy model's disagreement with the market is the model's own error.** A worked example, under assumptions and not an estimate: suppose the model's error and the market's error are independent. The best guess at the truth is then a weighted average of the two, and the model's weight is the market's error variance divided by the sum of both.
  - If the model is twice as noisy as the market, its weight is 1/5. A model at 56% against a market at 52% is then worth 52.8%, where −110 needs 52.4%.
  - If it is three times as noisy, its weight is 1/10 and the same gap is worth 52.4%: nothing.
  - So betting the model's biggest disagreements selects its biggest mistakes.
- **One of the papers that reports a profit agrees.** Hubáček, Šourek and Železný (2019) say in their abstract that they trained the model to be less correlated with the bookmaker's own view, and that this allowed better profits than accuracy alone.
- **The repo agrees too.** The de-vigged market price and the base rate score the same on totals (log loss 0.69336 and 0.69338 on 5,216 games), as they should when every total is set near 50%. The only model that adds anything is the small one built on a mechanism, and it adds 0.4% to 0.5%.
- **A published model of team strength starts from prices.** Lopez, Matthews and Baumer (2018) estimate team strength in four leagues from betting prices, not from scores.

### Which markets have no sharp price to start from

| Market | Is there a sharp price? | Sample | What the repo knows about size |
|---|---|---|---|
| NFL, college and NBA sides, totals and moneylines | Yes. Pinnacle priced 56 of 58 college games in the September 28 live check. | The largest | Nothing measured. The Odds API shows quotes, not limits. |
| Small-conference college totals | Mostly yes, by the same check | Inside F1 | Nothing measured |
| Kalshi game markets | Yes: Pinnacle's moneyline, which is what H1 tests | 1,233 NBA regular-season events in 2025-26; 285 NFL games in 2025 | The trades tape shows real traded size. The NFL tape isn't pulled yet. |
| Kalshi totals near the line | Yes, the book total. They were calibrated within 3.2 cents (2,915 contracts). | 2025 only | As above |
| Kalshi deep strikes and props | No | Not cached | Not measured |
| Alternate spreads and totals | Derived from the main line. Whether Pinnacle posts alternates through the API is probe question C4. | 1,140 NFL games, many lines each (F2) | Nothing measured |
| Team totals and first halves | Derived. The pre-check found nothing for wind to move; dropped. | — | — |
| NFL player props | Probably not. Whether Pinnacle quotes them through the API is one of Thursday's probes. | About 2,800 player-games a season in the two skewed markets (a proxy) | Nothing measured |
| College player props | No | Thin coverage; outcomes on disk for the QB, RB1 and WR1 only | Nothing measured |

**So the hub's list is shorter than it looks.** Kalshi's game markets and small-conference totals do have a sharp price. The markets without one are player props and the far ends of Kalshi's ladders.

**Can a bet of a useful size be placed?** The repo can't say for any market. No feed carries limits, and the price-engine file records the stake a book would accept as unknown for every flag. Two things are known:

- **Books limit accounts that take soft prices.** Kaunitz, Zhong and Kreiner (2017) were limited within months, as the repo already cites.
- **Prop limits are widely said to be the lowest of any market.** I have no source I can name for a figure, so treat it as unverified.

Whether that matters depends on the stake. At 0.5% of bankroll, a bet is $25 on $5,000 and $500 on $100,000. That is [question 1](#9-questions-for-the-owner).

---

## 4. The protocol

If anything were built, this is how. It follows the price-engine file, which is the best template in the repo.

**1. Registered before it is fitted.** One file, merged before any price is joined to any result. It states:

- the hypothesis, and one sentence on who is wrong and why;
- the data, the seasons and every exclusion;
- the model class, the exact list of inputs, and every setting that will be tried;
- the entry rule and the price taken;
- the grading, the decision rule and the kill rule;
- a power statement: "with n bets we have X% power to see Y".

The fitted model is then frozen as a committed file with a registered hash, as the pricing cohorts are. Every run checks the hash.

**2. The holdout, given the sealed seasons.**

| Layer | Seasons | What may be done |
|---|---|---|
| Development | Through 2022 | Fit and tune, on a target that involves no price (yards, points). Every setting tried is counted. |
| Rehearsal | 2023–25 | Prices joined once, reported, decides nothing. For sides and totals the screen, the pre-checks and the replays have all used these seasons, so they can't confirm anything. For props the prices are unseen until #10 opens them. |
| Confirmation | The sealed 2026 season | Opened once, after registration. This decides whether a forward test is earned. |
| Forward test | 2027 | Paper, registered before its first eligible game. This decides whether money is ever considered. |

**3. A budget of variants, fixed in advance.** At most 10 for the whole experiment: tuning settings, graded cells and controls together. Spending the budget ends the experiment. Two ways to set the bar, and the owner chooses ([question 3](#9-questions-for-the-owner)):

- **The single count:** 0.05 / 283 = 0.000177.
- **A family bar,** as the plan review proposed; with this experiment's budget of 10, 0.05 / 10 = 0.005 for the rehearsal, with the sealed season and the forward test as the confirmation.

**4. Grading.** Closing-line value at the price taken, in cents of no-vig probability, against the entry book's own close and against a sharp close where one exists. Results at the price taken are reported beside it and can veto, as in the price engine (K2).

**5. The decision rule and the kill rule,** taken from the price engine:

- **Kill** if mean closing-line value is at or below zero, if the return's 95% interval lies wholly below zero, or if one book or one season carries the result.
- **Act** (earn a paper forward test) only if closing-line value is above zero at the bar, positive in all but at most one of the seasons with 20 or more bets, and positive without the bets of 10% expected value or more.
- **Everything else is inconclusive,** and inconclusive means no forward test.
- **One more kill rule, for the model itself:** if its forecasts are no better calibrated than the market's price on the rehearsal seasons, stop before any bet is graded.

**6. How long a forward test would take.** At the bar, from the power table:

| The model flags | Bets a season | 2 cents of closing-line value (175 bets) | 1 cent (700 bets) | 2% profit on results (48,500 bets) |
|---|---|---|---|---|
| 10% of football games | about 120 | 1.5 seasons | 6 seasons | 400 seasons |
| 25% of football games | about 300 | under 1 season | 2.3 seasons | 160 seasons |
| 20% of prop lines in two markets | about 560 (a proxy) | unknown | unknown | 87 seasons |

The prop columns are unknown because nobody here has measured how much a prop line moves in its last day. F3a has the two snapshots to measure it. Bets on the same game move together, so the real numbers are larger than these.

---

## 5. Data and the paid month

### What a model layer would need, and where it comes from

Credit figures are from [`output/odds_5m_plan.csv`](output/odds_5m_plan.csv) unless marked "my arithmetic", which applies the project's own cost rule (10 credits × markets × regions, per game and snapshot for props).

| Data | What for | Held or planned | Not held | Cost |
|---|---|---|---|---|
| Sides and totals at 10 books, NFL and college, 2020–26 | Any football model's comparison price | F1, day one | Before 2020: The Odds API sells none (history starts June 6, 2020). On disk instead: nflverse closes from 1999 and prices from 2006, SBR opens and closes 2007–21, the cfbfastR consensus, CFBD lines by book from 2014. | 162,210 |
| The same, hourly | Line-move models | F4, gated on H16b | — | 1,442,220 |
| NFL props, six markets, T−24h and the close | A props model | F3a (2025) on day one; F3b (2023–24 and 2026 to date) gated on #10 | More markets: attempts, completions, touchdowns | F3a 34,200; F3b 102,600. Four more markets, 2023–25: 68,400 (my arithmetic) |
| College props | The same, in college | F6, March, gated | — | 147,920 |
| NFL alternates | Pricing off the main line | F2, day one | — | 45,600 |
| College alternates and team totals | The same | F5, March, gated | — | 221,880 |
| NBA sides and totals, other seasons | Any NBA model's comparison price | N2, March, gated | — | 170,460 |
| NBA moneyline every 5 minutes, 2025-26 | Kalshi H1 and H2 | N1, gated on the sample week | — | 486,440 |
| NBA props | An NBA props model | Not in any plan | All of it | About 158,400 for four markets at the close, 2023-24 to 2025-26 (my arithmetic) |
| NHL; MLB and soccer histories | More sports | H1, March, gated; B1 and S1 dropped | — | 163,860; 850,440 |
| NFL player outcomes | Player projections | `player_week.parquet`, on disk | — | Free (nflverse) |
| College player outcomes | The same | `player_games.parquet`: QB, RB1 and WR1 only | Every other player | Free (CFBD, within 1,000 calls a month) |
| NBA player and team data | Any NBA model | Nothing | All of it | Free from the league's statistics site; terms not checked |
| Injuries | Injury adjustments | Nothing | NFL: nflverse's injury reports, 2009 on, free. College: conference availability reports (Big Ten 2023, SEC 2024, ACC and Big 12 2025), forward only, terms not checked. NBA: no archive I can verify. | Free. The Odds API doesn't sell injuries. |
| Play-by-play | Team strength | NFL raw cache on the Mac; `team_games.parquet` on disk | College and NBA | Free (nflverse, cfbfastR) |
| Team-strength inputs | Ratings, priors | CFBD Elo, returning production and talent, on disk | NFL, NBA | Free |
| Limits and fillable size | Whether a thin market can take a bet | Nothing. The hand fill log records a line, a price and a book, not a size. | All of it. Nobody sells it. | Free, forward only |
| Order-book depth on Kalshi | The same, for Kalshi | The NBA collector logs top-of-book size from October 20 | NFL and college markets | Free, forward only |

**What this table says about the month.** Everything a model layer could want from The Odds API is either bought on day one, already behind a gate, or buyable in March. What The Odds API can't sell at any price is history before June 2020, prop prices before May 2023, and any record of limits.

### What must be decided before about October 20

**Nothing has to be bought.** Three facts from the plan make the purchase deadline soft:

- **The history doesn't expire.** A gate not read by October 25 is a "no" for the month, and March buys the same data.
- **A March month is already planned,** for the 2026 completions.
- **About 2.1 million credits are unallocated** even if every gate passes. Buying in October costs no cash. Waiting costs at most $60: March's 56,790 of completions fit the 100K plan ($59), and with the rest of F3b they come to 130,950, which needs the 5M plan ($119).

The decisions with a real deadline are about order, logging and safekeeping:

| # | Decision | By when | Why it has a deadline | My view |
|---|---|---|---|---|
| D1 | Add no pull to October for a model layer | Thursday, and again at the gate reads | "The credits lapse anyway" will be said on October 25. The plan review already answered it: pulled data invites analysis, and every analysis is a counted variant. | Add nothing |
| D2 | F3b's gate stays the only route to the 2023–24 props | Before #10's gate is read, by about October 20 | A second reason to buy F3b (a props model) would have to be written before the read. After it, that is widening a gate. | Keep the gate. Write no second reason. |
| D3 | #10's registration says whether the sealed 2026 props may also confirm one later hypothesis | Before F3a's rows are first joined to outcomes, days after Thursday | Once #10 opens the 2026 props to confirm itself, they can't confirm anything registered later. | One sentence when #10's draft goes into its file: "the sealed 2026 props are opened once, for every hypothesis registered by then". It costs nothing and keeps "do nothing" open. The sentence interprets the owner's September 28 sealed-holdout decision (`STATUS.md`, "Sealed holdout"; [`ops/LIVE_USES.md`](../ops/LIVE_USES.md)). The hub can settle it under the owner's standing instruction of September 29 on research questions, and the owner can overrule it. |
| D4 | Whether to record size: a largest-stake figure on each hand-checked fill, and Kalshi top-of-book size for NFL and college markets | Each week not logged is lost | Size can't be bought later | Worth doing for the fills whatever happens to the model question (the price-engine file already says the fill log records the stake; the code doesn't yet). Kalshi depth only if Kalshi stays in play after October 20. Log only; every 2026 row is sealed. |
| D5 | A backup of the raw responses | The disk ready before Thursday's pull; the copy made the same day | The month's data can't be re-created without paying again | A second disk: an external drive (the owner's purchase, roughly $60 to $150) or the Mac Studio over the network. The rule already exists (`odds-api-credits.md`, "Before you buy", item 6); what is missing is a step that carries it out. See the next section. |
| D6 | The plan after October (20K or 100K) | About October 25 | Already on the owner's list | A model layer doesn't change it |

---

## What the new computer changes, and what it does not

From Wednesday, September 30, the project has a Mac Studio: M5 Max, 18 CPU cores, 40 GPU cores, 64 GB of memory, 1 TB of storage. That specification is in neither the repo nor the issue and is not independently confirmed. Today the project runs on an M4 laptop with 32 GB of memory (both confirmed on the machine). The laptop's free disk moves: figures on September 29 ranged from about 14 GB to 74 GB, so none is relied on here.

**Compute was never the constraint.** The heaviest analyses in the repo finish in about a minute, by their own write-ups: the screen in about 40 seconds, the landing-mass study in about 30, the 40,000-path keep-test check in about a minute. The slow jobs were slow because a server set the pace. The forecast archive took five to six hours at one request every 7 to 8 seconds, and F1 takes about 12 minutes at 8 requests a second. A faster computer changes neither.

| What becomes practical | Does it matter here? |
|---|---|
| A machine that is always on for the scheduled jobs | **Yes, most of all.** A slot missed while the Mac sleeps "is reported as missing, never filled in" (STATUS.md). Missed closes weaken Rule B's closing-line value, and fewer than 20 primary closes make a decision inconclusive. |
| Disk: 1 TB | **Yes.** Day one needs about 3 GB. The day-one file says about 16 GB if F4 is earned; it calls that an extrapolation from two live responses, it is unverified, and the file doesn't say whether it includes day one's 3 GB. Whether that fits on the laptop depends on the day; 1 TB removes the question. |
| The month's odds tables held in memory | A convenience. Day one's 3 GB fits in the laptop's memory too. F4 and N1 are the ones that get easier. |
| Chains of a Bayesian model in parallel | Practical, not needed. A hierarchical model on 1,500 windy games or 8,400 player-games is small; I would expect minutes on the laptop, though nothing was timed here. |
| Larger simulations | Practical, not needed. The keep-test check (40,000 paths) is already precise to about 0.1 point, and the 20,000-season shares in `simulate_decisions.py` to about 0.3 point. Their weak part is their inputs, about 400 games a sport. |
| A wide search over a model's settings | Practical, and the one to fear. Compute makes a search cheap. It doesn't make it honest: every setting tried is still a counted variant. |
| A language model run locally to read news | Practical on 64 GB. It doesn't touch the reasons against it: news is a race, and there is no labelled text to check a model against. |

**What it does not change.**

- **The number of games.** The NFL plays 285 a season, and wind reaches 15 mph in about 25 of them. Every test here is limited by that, and no computer adds a game.
- **The bar, the sealed seasons and the count of variants.**
- **The pace of the servers** the data comes from.
- **The need for a second copy.** 1 TB inside the same machine is not a backup.

**One caution about the move itself** (the hub's call). The Mac arrives on Wednesday, the month is bought and pulled on Thursday, and the college test is scored from Thursday.

- **Run the scheduled jobs on one machine only.** Two would log every run twice and spend credits twice.
- **Decide before Thursday which machine makes the pull,** and make it there. The cache must end up where the jobs and the backup are.
- **Move the jobs on a quiet day,** between two alert runs, with no kickoff and no pull. What has to move together: the three `.env` keys, the quota file and forecast cache under `~/.cache/value-finder/`, the ledgers and decision records in `data/forward/`, and the raw caches. The alert jobs are reinstalled from the new location (CLAUDE.md), and the boards read the Mac's own clock and time zone, so check both.

---

## 6. The smallest useful version

**In October: none.** Every candidate either repeats something already counted, waits on a result that lands this month, or can't be decided at these sample sizes.

**In January, if #10 passes its gate and the owner wants it: one.** "None" stays a full answer then too.

| | |
|---|---|
| **The question** | When a posted NFL prop line for receiving or rushing yards sits well above a player's shrunken median, does the under beat its price, and does the line come down by the close? |
| **Who is wrong, in one sentence** | Retail books set yardage lines near a player's average, which sits above his median, and no sharp book corrects them. |
| **Why this one** | It has no sharp anchor. Its mechanism is already measured (the mean is 7.6% above the median for receiving yards and 3.2% for rushing, #41). Its prices have never been seen. It extends #10 and opens no new front. |
| **The data** | `player_week.parquet` (on disk); F3a; F3b only through its gate; the sealed 2026 props (the live props log and the March completion). |
| **The model** | The smallest member of the hierarchical family. A player's predicted median is a weighted average of his own median over his last 8 to 16 games and the median for players of his position and usage. One weight, chosen on 2015–22 outcomes, where no price exists. It must pass one check before any price is joined: out of sample, half of outcomes fall below the predicted median. The #41 pre-check found that 56 to 57% fall below a raw trailing median, so an unshrunk projection fails this check. |
| **The flag** | The T−24h line is at least 10% above the predicted median: under. At least 10% below: over. One threshold, fixed at registration. |
| **The variants** | 8: five settings of the weight, two graded cells (unders, overs, the two markets pooled), one control (passing yards, where the mechanism predicts nothing). |
| **The grading** | Closing-line value from the T−24h price to the close at the same book, and against Pinnacle's close if Thursday's probe finds that Pinnacle quotes props. The excess win rate over the de-vigged price is reported beside it. |
| **The decision** | 2023–25 is a rehearsal and decides nothing. The sealed 2026 props decide whether a 2027 paper test is earned. |
| **What it can't show** | An edge on results. One season of about 560 flags can see a true win rate of about 59% and nothing smaller. Inactives are posted after a T−24h entry, so part of its closing-line value will be injury news, in both directions. |
| **The work** | About 4 worker-days: half a day for the registration, a day and a half for the model and its tests, half a day for an independent review, a day and a half for the run and the write-up. |
| **What it displaces** | #11's priors model, which is the same kind of work with a weaker mechanism, and one of the two or three places in the 2027 family of rules. |

**If #10 fails its gate: none.** Lines that sit at the median leave a small model nothing to find.

**Considered and not chosen.**

| Candidate | Why not |
|---|---|
| A hierarchical version of the wind pricing model (the hub's idea) | It can't change a bet this season: inside the −115 cap the gate can't reject a bet at the rule's own number, and the model is frozen. The landing-mass study already tried a richer table against the registered method: no difference on 8 declared comparisons, 32 variants spent. |
| A hierarchical estimate of the wind edge by era | Useful for reading January's results. But it re-reads outcomes the project has looked at many times, and it would set an expectation, not a rule. At most a descriptive note in the winter. |
| A team rating for early-season college football (#11) | The right season to test it starts in August 2027. Its mechanism is weaker: the screen found 50.6% for early-season underdogs. |
| A model of sides or totals in any sport | Sections 2 and 3 |
| A language model reading availability news | [Section 8](#8-where-the-hub-is-wrong), point 3 |

---

## 7. The recommendation

**Do nothing now.** One option can be kept behind a gate, and dropping it is an equally good answer.

1. **October: build no model and buy nothing for one.** Keep every pull and gate as adopted on September 28 and 29.
2. **Nothing on the advice's list is being missed that is worth having today.**
3. **Close three gaps the advice doesn't name:** record size on hand-checked fills, decide the bar, and back up the paid data the day it lands.
4. **Read Thursday's price-engine run as the project's test of "P(model) against P(market)" on the main markets.** Nothing in the evidence suggests a home-built model would price a game better than Pinnacle, so on the main markets, and for edges measured against Pinnacle's close, I expect its result to bound what a home-built model could show. It doesn't bound a model aimed at errors in the close itself, which is what Rule B and Rule HT claim: the price-engine file names that limit, that it cannot catch Pinnacle's close itself being wrong.
5. **Don't build a model of sides or totals from scratch, in any sport.** The repo's own try, the published record and the power table all say no.
6. **The option:** the props experiment of section 6, considered only if #10 passes its F3b gate (read by about October 20), registered in January, decided on the sealed 2026 props.
7. **If #10 fails, or the owner drops the option:** close this issue until the 2027 rules are written, and park #11's priors model with it.
8. **This week, the hub's call:** the sentence in D3 (it interprets the owner's September 28 sealed-holdout decision, so the hub settles it under his standing instruction on research questions and he can overrule it), and the move to the new Mac on a quiet day.

### The strongest argument against it

Written as its best advocate would.

> You are protecting a method that has produced nothing. 273 variants, and by your own count not one passes your own bar; your own plan review calls that bar unclearable. A screen tests one feature at a time, so it can never find an edge that lives in a combination, and combinations are where any edge left in a mature market must live. You say the project can't prove a model's edge, but the same table says it can't prove a rule's edge either, and you run three of those.
>
> Your evidence is thin where it matters. One paper on 110 games from 1993, one on college rankings from 1998 to 2001, one on the NBA that stops in 2014. Nothing on props, nothing on modern methods against a closing line, and you say so yourself. The repo's own try was one hand-set model on weather inputs. That is not a test of the idea; it is a test of one afternoon.
>
> The owner asked in order to be comprehensive. Reasoning your way to "no" from old papers is the opposite. A capped experiment, registered first, 8 variants, graded on closing-line value, costs four days, and within a month you would know whether there is anything to pursue. If it fails you have lost four days. If you wait for a gate, the question isn't even asked until January.

**What I make of it.** The first paragraph is half right: the single bar is a real problem, and [question 3](#9-questions-for-the-owner) puts it to the owner. But a flexible model makes that problem worse, not better. The second is fair, and it is why the case here rests on the power table more than on the papers: the table holds whatever the papers say, at the project's bar; at a family bar its numbers are smaller, and the case against results still holds for anything that has to be confirmed going forward ([section 2](#2-model-by-model)). The third is right that four days is cheap, which is why the option is kept and not closed. It is also right that acting now could answer sooner in one direction: the protocol's own kill rule ([section 4](#4-the-protocol), step 5) stops the experiment if its forecasts are no better calibrated than the market's price on the rehearsal seasons, and with only 2025's props available until F3b's gate, that could give a "no" within weeks. I still prefer to wait. #10 reads the same 2025 slice by about October 20 and answers the prior question, whether lines sit above the median at all, without this experiment's 8 variants; if #10 fails, the experiment has little to find, and if it passes, the experiment is registered with that result in hand. An early run can only say "no" or "the rehearsal passed"; a "yes" still needs the sealed 2026 season, which can't be opened before March either way. And waiting loses no data: the alert log records 2026 now and the props log will from its install on day one; props for games before then can still be bought (F3b's 2026 slice, or in March). What would move me to run it sooner is #10 passing clearly. What would close the question today is the owner's answer to [question 2](#9-questions-for-the-owner).

---

## 8. Where the hub is wrong

| The hub's point | Where I agree | Where I disagree |
|---|---|---|
| **1. Much of the pipeline exists or arrives Thursday.** | The list is right as far as it goes. | It leaves out the most useful fact: a model layer exists too. The repo has a logistic model on a registered paper test, an interaction model and a gradient-boosted model, all scored season by season from 2006 to 2025, and a table of the model against the de-vigged market. Two smaller points: the simulations size decisions, which is not what the advice means by simulation; and the database is three separate stores, which is fine for now. |
| **2. A home-built model is the hardest and most crowded road.** | Yes, on the main markets, and the literature backs it. | "The new part is a home-built model" isn't quite right: a home-built model of the under has been tried, and the gradient-boosted version lost to the base rate. And the variant count is not the binding problem. A protocol can cap a model at 10 variants by tuning it on a target with no price in it. The binding problem is power: even one variant can't be expected to clear the bar on results at 285 games a season. |
| **3a. A hierarchical version of the wind pricing model.** | The cohort is small, and the price-engine file says its point value carries a sampling error of 0.4 to 0.5 cents. | It isn't worth doing. The pricing model selects no bet inside the −115 cap, it is frozen for the season, and the landing-mass study already found that a richer table doesn't beat it (8 declared comparisons, all null). Shrinking the windy cohort toward all games also assumes the answer to the open question, which is whether windy games are shaped differently. |
| **3b. Markets with no sharp price: props, alternates, Kalshi, small-conference totals.** | Props, yes. | Kalshi's game markets and small-conference totals do have a sharp price; Pinnacle priced 56 of 58 college games on September 28. The list is really props and the far ends of Kalshi's ladders. And these are the markets where the repo knows least about whether a bet can be placed. |
| **3c. A language model reading availability news, forward only.** | As a log, perhaps. The hub's own review of September 28 left exactly one opening: "a forward-collected, fetch-stamped, hand-labeled stream of availability news for CFB games without mandatory reports", counted as a variant under #11. That log would create the labelled text that doesn't exist today. | As a bet, no. News is a race. Inactives post 90 minutes before kickoff, and I would expect books to reprice within minutes (not measured here); the alerts run four times a day and the poller every ten minutes. The same review found no use for a decision model at any of 96 decision points, and nothing could be checked against a hand-labelled log for at least a season. For the NFL, nflverse's structured injury feed is the right source, and it needs no language model. |
| **4. The reason to think now is the paid month.** | Thinking now is right. | The purchase deadline is soft, for the three reasons in section 5. What has a deadline is the order of registration (D2 and D3), the size log (D4) and the backup (D5). The risk on October 25 is the opposite of the one the hub names: not failing to buy, but buying because the credits are there. |
| **5. Thursday's result is the cheapest version of "P(model) against P(market)".** | Yes, and on the main markets I expect it to be more than that: a bound on what a home-built model could show, for edges measured against Pinnacle's close. If prices that beat Pinnacle's no-vig price don't hold their value to the close, I see no reason a home-built model would do better through the same books. It is no bound for a model aimed at errors in the close itself, which the price-engine test says it cannot catch. | It is lopsided. The price-engine file says a pass is close to automatic if Pinnacle is right, so a pass says little about a home-built model, whose flags would carry less value than Pinnacle's. A fail is the informative result. And it says nothing about props, where no Pinnacle price may exist. |

---

## 9. Questions for the owner

Each answer would change the recommendation.

1. **At 0.5% of bankroll, is one bet nearer $25 or nearer $500?** If it is small, the low-limit markets can take it and the props option is worth keeping. If it is large, only the main markets can take it, a model has the least chance there, and the option should be dropped.
2. **Do you want the January option kept at all?** If being comprehensive was the whole reason for asking, "do nothing" can be final today and this issue closed. Keeping the option costs one sentence in #10's file now and nothing else until January.
3. **Would you accept a separate bar for a small registered family of tests, confirmed on the sealed season and a forward test, as the plan review proposed?** If no, the single bar stands at 0.05 / 273 and rising, only closing-line value can ever pass it, and the list of ideas worth testing gets shorter, for rules as well as for models.
4. **How many seasons will you wait for one answer?** If one, only a rule that bets early and earns 2 cents or more qualifies. If three, 1 cent does.
5. **Do you want the 2023–24 props held unopened this month at no cash cost, or bought only through the gate, as adopted?** Holding them saves at most $60 in March and keeps an option. It also reverses a decision made two days ago and puts unopened data within reach. My view is to leave it, but the purchase is yours.

---

## Appendix A: sources, and how each was checked

**Read in full or in the relevant part.**

- Fair, R. C. and Oster, J. F. (2007). College Football Rankings and Market Efficiency. *Journal of Sports Economics* 8(1), 3–18.
- Glickman, M. E. and Stern, H. S. (1998). A State-Space Model for National Football League Scores. *Journal of the American Statistical Association* 93, 25–35. Section 4.5 and the conclusion.
- Manner, H. (2016). Modeling and forecasting the outcomes of NBA basketball games. *Journal of Quantitative Analysis in Sports* 12(1), 31–41. The author's working-paper version, dated November 26, 2015.

**Abstract only.**

- Boulier, B. L. and Stekler, H. O. (2003). Predicting the outcomes of National Football League games. *International Journal of Forecasting* 19, 257–270.
- Egidi, L., Pauli, F. and Torelli, N. (2018). Combining historical data and bookmakers' odds in modelling football scores. *Statistical Modelling* 18(5–6), 436–459.
- Gray, P. K. and Gray, S. F. (1997). Testing Market Efficiency: Evidence from the NFL Sports Betting Market. *Journal of Finance* 52(4), 1725–1737.
- Hubáček, O., Šourek, G. and Železný, F. (2019). Exploiting sports-betting market using machine learning. *International Journal of Forecasting* 35(2), 783–796.
- Lopez, M. J., Matthews, G. J. and Baumer, B. S. (2018). How often does the best team win? A unified approach to understanding randomness in North American sport. *The Annals of Applied Statistics* 12(4), 2483–2516, doi 10.1214/18-AOAS1165 (journal, volume, issue and pages checked on Project Euclid and in Crossref). Preprint: arXiv 1701.05976.
- Štrumbelj, E. and Vračar, P. (2012). Simulating a basketball match with a homogeneous Markov model and forecasting the outcome. *International Journal of Forecasting* 28(2), 532–542.
- Walsh, C. and Joshi, A. (2024). Machine learning for sports betting: should model selection be based on accuracy or calibration? *Machine Learning with Applications* 16, 100539. Corrigendum: *Machine Learning with Applications* 19 (March 2025), doi 10.1016/j.mlwa.2025.100627, checked in Crossref and in the authors' GitHub notice. Its text couldn't be opened (the publisher refused access), so its corrected figures are not independently confirmed, and the original paper's return figures are not quoted as findings.

**Citation verified, content recalled and not verified.**

- Zuber, R. A., Gandar, J. M. and Bowers, B. D. (1985). Beating the spread: testing the efficiency of the gambling market for National Football League games. *Journal of Political Economy* 93, 800–806.
- Sauer, R. D., Brajer, V., Ferris, S. P. and Marr, M. W. (1988). Hold your bets: another look at the efficiency of the gambling market for National Football League games. *Journal of Political Economy* 96, 206–213.

**Not verified.**

- FiveThirtyEight's statement that NFL Elo picked 51% against the spread. Secondhand; the original page now redirects elsewhere.
- That prop limits are the lowest of any market. No source I can name.
- The Mac Studio's specification. It is in neither the repo nor the issue.
- The 16 GB disk estimate for F4. The day-one file and the plan review both call it an unverified extrapolation from two live responses.

**Checked on the machine, September 29:** the laptop is an M4 with 32 GB of memory, and no Time Machine destination is set on it.

**Already in the repo's sources, and taken from there:** Kaunitz, Zhong and Kreiner (2017); Moskowitz (2021); Simon (2024); Sinkey and Logan (2009); Buchdahl on closing-line value. None was opened again for this memo.

**The repo's own tables:** [`model_compare.csv`](../nfl-weather/output/tables/model_compare.csv), [`model_compare_bets.csv`](../nfl-weather/output/tables/model_compare_bets.csv), [`bet_model_vs_market.csv`](../nfl-weather/output/tables/bet_model_vs_market.csv), [`bet_walkforward.csv`](../nfl-weather/output/tables/bet_walkforward.csv), [`calibration_slopes.csv`](output/calibration_slopes.csv), [`bet_summary.json`](../nfl-weather/output/tables/bet_summary.json), [`walkforward.csv`](../cfb-weather/output/tables/walkforward.csv), [`output/odds_5m_plan.csv`](output/odds_5m_plan.csv), [`output/odds_5m_seasons.csv`](output/odds_5m_seasons.csv), [`output/odds_api_counts.csv`](output/odds_api_counts.csv).

---

## Appendix B: the counts and the arithmetic

Nothing here compares a predictor with a result.

**Row counts,** read with a filter on seasons through 2025 and on columns that carry no result:

| Table | Count |
|---|---|
| `nfl-weather/data/processed/games.parquet` | 7,276 games, 1999–2025, all with a closing spread and total; 5,292 with over and under prices (2006–25); 285 a season from 2021 |
| `cfb-weather/data/processed/games.parquet` | 33,361 rows, 2006–25; 16,740 with a consensus closing total; 14,383 of those FBS-involved |
| `nfl-weather/data/processed/player_week.parquet` | 476,159 player-weeks, 1999–2025 |
| `nfl-weather/data/processed/player_week.parquet`, 2023–25 | 855 games; 1,709 quarterback games with 15+ attempts; 2,342 rusher games with 8+ carries; 6,041 receiver games with 4+ targets; 1,513 kicker games with a field-goal attempt |
| [`output/odds_api_counts.csv`](output/odds_api_counts.csv), 2020–25 | 1,693 NFL games and 5,147 college games |
| [`output/odds_5m_seasons.csv`](output/odds_5m_seasons.csv), NBA 2020-21 to 2025-26 | 1,171 + 5 × 1,320 = 7,771 games (the plan's estimates); the 2019-20 restart adds 171 |

The player counts are a proxy chosen by usage. They are not counts of posted prop lines, which don't exist on disk.

**Power.** One-sided tests, 80% power. The bar is p < 0.05 / 273 = 0.000183, z = 3.56.

- **Closing-line value:** bets = ((z + 0.84) × 6 / effect in cents)². At the bar: 2,800 for 0.5 cents, 700 for 1 cent, 175 for 2 cents. At p < 0.05: 890, 220 and 56. The 6 cents is the price-engine file's figure for sides and totals. It is not known for props.
- **Results at −110** (break-even 52.38%): at the bar, 126,000 bets for a true 53%, 18,400 for 54%, 7,000 for 55%, 3,700 for 56%. At p < 0.05: 40,200, 5,900, 2,240 and 1,170. These match the plan review's figures at its earlier bar.
- **The chance of clearing the bar on results with a fixed number of bets:** 5,292 bets give 11% at a true 54% and 60% at 55%. 14,383 bets give 63% and over 99%.
- **Profit,** with one bet's result varying by about 1 unit: a 2% edge needs 15,500 bets at p < 0.05 (the price-engine file rounds to 15,000) and 48,500 at the bar, as that file says.
- **A family of 10:** p < 0.005, z = 2.58. With 8 it is z = 2.50.
- **The same arithmetic at the family bar of 10:** results at −110 need 75,900 bets for a true 53%, 11,100 for 54%, 4,240 for 55% and 2,220 for 56%; closing-line value needs 1,680, 420 and 105 bets for 0.5, 1 and 2 cents; a 2% profit edge needs 29,200. 5,292 bets clear it 41% of the time at a true 54% and 89% at 55%; 14,383 bets 91% and over 99%; 3,600 bets 26% and 72%.
- **The simulations' precision:** at 40,000 paths a rate near 3% has a standard error of about 0.09 percentage points; at 20,000 seasons a share between 25% and 60% has one of about 0.3 to 0.35 points.
- **What one season of 560 prop flags can see on results:** 52.38% + (2.50 + 0.84) × 0.5 / √560 = 59.4% at a family bar of 8, and 61.7% at the project's bar.

**Credits.** Day one plus every gate is 2,304,050, against the hard ceiling of 4,440,000, which leaves 2,135,950. The plan's text gives 2,164,320, counted against 5,000,000 less the 531,630 floor. Both are "about 2.1 million".

- Four more NFL prop markets at two snapshots, 2023–25: 10 × 4 × 2 × 855 = 68,400.
- NBA props, four markets at the close, three seasons: 10 × 4 × 3,960 = 158,400.
- March's completions: 18,870 for F1, 9,480 for F2 and 28,440 for F3b's 2026 games, 56,790 in all, inside the 100K plan ($59). If the rest of F3b waits for March too, add 68,400 for 2023–24 and 5,760 for the 2026 games played by October 1: 130,950, which needs the 5M plan ($119).

---

## Corrections (September 29, 2026)

An independent fact-check found the points below, and each was reproduced before it was changed. None changes the recommendation or any of the decisions D1 to D6.

- **Player-weeks:** 479,433 was the whole file's row count, which includes rows after 2025; filtered to 1999–2025 it is 476,159. Only a row count was read, no 2026 price or result.
- **Walsh and Joshi:** the returns quoted (+34.69% and −35.17%) are the original paper's, revised by a 2025 corrigendum (doi 10.1016/j.mlwa.2025.100627). Only the direction is now stated as the finding; the corrected figures are not independently confirmed.
- **The props log:** it doesn't record 2026 yet; it starts when it is installed on day one. Waiting still loses no data, because earlier props can be bought later.
- **The short answer** now gives the one NFL exception (Glickman and Stern 1998), the ages of the samples, and that Manner compares against the opening line.
- **The price engine is no longer called a "ceiling".** It is expected to bound a home-built model on the main markets, for edges measured against Pinnacle's close, and not for a model aimed at errors in the close itself.
- **The power table** gains a column for a family bar of 10, and section 2's conclusion is now stated as depending on the bar (at 0.005: 4,240 bets for a true 55%, 11,100 for 54%, 420 for 1 cent of closing-line value).
- **The answer to the strongest argument** now concedes that the protocol's own kill rule could give an early "no" on the 2025 props, and says why waiting is still preferred.
- **The backup gap:** the repo already has the rule (an encrypted backup outside git); the gap is that no step carries it out. The disk is marked as the owner's purchase, with a rough cost, and no Time Machine destination is set on the laptop.
- **The size gap:** the price-engine file says the fill log records the stake, but the fill log has no column for it. A size field must leave the scorers' grading unchanged.
- **The computer:** the 16 GB estimate for F4 is marked as an unverified extrapolation, the laptop's free disk is no longer given as a fixed figure, and the Mac Studio's specification is marked as not independently confirmed.
- **Counts that disagreed:** seven missing items plus the database as a design choice; 17 items exist or arrive in October, not all on Thursday; four papers report backtest profits, not three; the college games a season are 849 to 934 on the same filter as the 14,383 (not 895 to 934); the NBA has six full seasons plus the 2019-20 restart (171 games).
- **The model lean's 56.4% on 629 bets** is its registered cut (P ≥ 55%), not its best, and comes from `bet_walkforward.csv`.
- **The hub's September 28 review of a decision model** is now quoted with its one opening, a hand-labelled log of college availability news.
- **Rule HT's calibration slope:** 0.89 with a standard error of 0.025, from `calibration_slopes.csv` (the repo's documents round it to ± 0.03).
- **Attributions:** the price-engine file rounds the 2% profit figure to 15,000; the family bar's 10 is this memo's budget, not the plan review's.
- **D3** now says that its sentence interprets the owner's September 28 sealed-holdout decision, and who settles it.
- **Simulation precision:** about 0.1 point for the keep-test check, about 0.3 point for the 20,000-season shares.
- **Lopez, Matthews and Baumer (2018)** now has its verified journal citation.
