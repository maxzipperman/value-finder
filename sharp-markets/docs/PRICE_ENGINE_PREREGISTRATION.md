# Price engine: pre-registration (issues [#8](https://github.com/maxzipperman/value-finder/issues/8) and [#53](https://github.com/maxzipperman/value-finder/issues/53))

**Status: registered September 29, 2026 (Pacific), by the hub on the owner's standing instruction, before any F1 data exists.** Nobody has seen a single F1 price. The F1 pull is planned for October 1, 2026. From this commit on, changing any threshold, flag, grading rule or decision rule is a dated amendment, made before the affected result is seen. It was written as a draft the same day (`strategy-research/price-engine-preregistration-draft.md`) and revised after an independent review (below).

The registering commit is the merge of pull request 56 ([#56](https://github.com/maxzipperman/value-finder/pull/56)).

The code that runs it is already written and tested: [`sharp-markets/src/markets/research/price_engine/`](../src/markets/research/price_engine/). Every threshold below is a constant in `engine.py` or `model.py` (the blend weights included), and the tests check the variant count and that this file states the same count and bar as the code. Changing any of them after F1 lands is an amendment. It is not an edit.

### Revised after the independent review (September 29, 2026)

No headline number changed: still 38 variants. As registered, the running count is 271 and the bar p < 0.000185 (see section 8). Still no F1 data, so there are no results to change. What did change:

- **A lookahead hole is closed.** A kickoff that was later moved *later* could turn a snapshot taken inside the last hour before the original kickoff into a bet. An entry now needs both the kickoff listed at that moment and the latest-listed kickoff to be more than 60 minutes away (section 4). A test checks it.
- **Spread bets whose close moved are now graded, not dropped.** Before, a spread bet counted toward the main CLV only if Pinnacle closed on the same number. That left out most spread bets, and exactly the ones where Pinnacle moved to the retail book's side, which is the failure this test is meant to catch. A close at another number is now converted with a margin table fixed from the seasons before 2020 (section 6). The report shows how many bets were graded, and the result split by same-number and moved closes.
- **H2 must also beat the lagging book's own close** (condition A6, as issue #53 asks).
- **Plainer about what the main test can and cannot show.** If Pinnacle is right, a 2% flag is expected to show about 1 cent of CLV, which 420 to 650 bets would detect almost automatically (section 7). The owner decides whether that is the right main test (decision 6).
- **Plainer about H2's weakest flags.** At exactly 1 point and −115, an H2 bet is about 2% *negative* EV at Pinnacle's own price (section 4, decision 7).
- **Corrections.** Every snapshot lists every game, so entries also come from other games' closes, not only the daily snapshot. The "next snapshot" in the lag table is often hours later on game days, not a day. The totals conversion rests on a small windy cohort that overlaps the backtest (section 3). The blend weights are now fixed in code.
- **Not done yet:** issue #53's first task, the live-log lag measurement (see the end of this file).

## The short version

- **What gets tested.** When a regular US sportsbook offers a price that beats Pinnacle's no-vig price for the same game at the same moment, is that price worth betting? The price engine flags those prices. This draft fixes, before the data exists, exactly which prices count and how they are graded.
- **Where the probabilities come from.** The sharp market's own no-vig price. That is the most defensible probability for any game, and it is what a college football signal this season would be built on.
- **The decision.** It rests on closing-line value (CLV): did the price you took beat Pinnacle's closing price? Profit and loss is reported too, but six seasons are far too few bets for profit to prove anything (section 9). A pass earns a **paper** forward test on the rest of the 2026 season. It does not earn money.
- **Count.** 38 variants, which takes the running count from 233 to **271**. The bar becomes **p < 0.05 / 271 = 0.000185**.
- **What it cannot see.** F1 looks at each game once a day at 16:00 UTC and, on busy days, also at every other game's close. A gap shows up only if it is open at one of those moments, so the fast gaps described in #53 are mostly missed, and nothing says how long a gap lasted.

## 1. The two hypotheses

- **H1, the price engine (#8).** A retail price whose expected value against the sharp no-vig fair price at the same snapshot is at least X beats Pinnacle's close on average.
- **H2, soft-book lag (#53).** A retail total at least 1 point on the good side of Pinnacle's total at the same snapshot, at −115 or better, beats Pinnacle's close on average. The good side is a higher number for an under and a lower number for an over.

Both are "beat the close" rules: the bet is placed hours or days before kickoff, and the close is a later, sharper price. The repo grades that kind of rule on CLV.

## 2. Data

| | |
|---|---|
| Pull | F1 (`sharp-markets/config/odds5m.yaml`): featured markets, a snapshot at 16:00 UTC on each of the 7 days before each kickoff, plus each game's close (the last 5-minute grid point at least 5 minutes before kickoff). Every snapshot lists every game of that sport, so a game is also seen at every other game's close: on a college Saturday that is every half hour to few hours. |
| Sports | NFL and college football, **analysed separately**. |
| Markets | Full-game moneyline (h2h), spread and total. |
| Seasons | 2020–2025, regular season and postseason (see amendment 1). **2026 is sealed**: `bulk.load_rows` leaves it out, the backtest never asks for it, and it never loads 2026 scores (a test checks all three). |
| Sharp books (the fair price) | Pinnacle; LowVig and BetOnline for the blend. |
| Retail books (the flags) | DraftKings, FanDuel, BetMGM, Caesars (`williamhill_us`), Fanatics, BetRivers, ESPN BET: F1's ten books minus the three sharp ones. LowVig and BetOnline are never treated as retail. |
| Window | Snapshots from 7 days before kickoff up to kickoff. Featured snapshots also list games further out; F1 wasn't built to cover them, so those quotes are dropped and counted (see amendment 1). |
| Final scores | The repo's processed game tables (nflverse and cfbfastR), 2020–25 only. A game with no matched score still counts for CLV and is left out of profit and loss, with its reason logged (see amendment 1). |

## 3. The fair price

- **Primary: Pinnacle.** At each snapshot, Pinnacle's two prices for a market are de-vigged with the Shin method. That gives a fair probability for each side at **Pinnacle's own line**. The Shin code is the repo's registered one: `devig_shin`, imported from `nfl-weather` and `cfb-weather`, never copied.
- **Second, pre-declared: the blend.** Pinnacle, LowVig and BetOnline are each de-vigged, wherever they quote Pinnacle's line at that snapshot, and averaged with weights 0.55 / 0.30 / 0.15, renormalized over the books present. The weights are the ones `sharp-markets/config/backtest.yaml` held on September 29, fixed in `engine.py` so that an edit to that shared file can't change this test. The blend also needs Pinnacle, so both versions cover the same games.
- **Comparing a retail quote with the fair price:**
  - **Moneylines:** always.
  - **Spreads:** only when the retail book is at Pinnacle's own spread. A different spread is left out of the primary analysis and counted.
  - **Totals:** at any total. A total different from Pinnacle's is converted with the repo's registered pricing model (`p_under_at` and each sport's frozen residual cohort, checked against its registered hash; imported, not copied). The rule is:

    > P(under wins at L) = q × (1 − P(push at L0)) + [w(L) − w(L0)], and P(push at L) = the model's push chance at L,
    >
    > where q is Pinnacle's no-vig under probability at its own total L0, and w(·) is the model's chance the under wins, with the reference total set to L0.

    Only the probability mass the model puts **between** the two lines is used, not its level. The registered cohort is windy games, whose unders win more often than the market expects, and that tilt must not leak into a price engine that treats Pinnacle as the truth. NFL uses the NFL cohort; college football uses the CFB cohort.

    **A weakness to know about.** The registered cohort is small and overlaps the backtest. It is 656 NFL games (1999–2023) and 855 CFB games (2006–2023), and 92 and 236 of them are from 2020–23, inside the backtest seasons. It values one point near the middle of a total at 2.44 cents (NFL) and 2.22 cents (CFB). All games in 2014–25 say 2.76 cents (3,295 NFL games) and 2.57 cents (12,115 CFB games). The windy figures have a sampling error of about 0.4–0.5 cents. Every CLV in cents for a total at another number goes through this conversion, and the test is sized to find about 1 cent. So the report puts CLV in points, which needs no conversion, next to CLV in cents for every total and spread cell.
- **Expected value.** Every probability is taken conditional on no push, as a two-way price is. The expected value (EV) of a bet at decimal price d is p × d − 1 per unit staked on bets that are decided. A push returns the stake.

## 4. The flags

| Flag | Rule | Versions |
|---|---|---|
| H1 | The retail side's EV against the fair price is **at least 1%, 2% or 3%**. These are the only three thresholds, and **2% is primary**. | Pinnacle (primary) and blend, for totals, spreads and moneylines, for NFL and CFB. |
| H2 | A retail total **at least 1.0 point** on the good side of Pinnacle's total at the same snapshot, at **−115 or better** (decimal 1.87 or more) (see amendment 1). | Totals only, NFL and CFB. |

**H2's weakest flags are negative EV at Pinnacle's own price.** Take Pinnacle at 44.5, 1.95 / 1.95 (a fair 50%), and a retail under at 45.5 for −115. Under the registered conversion the under at 45.5 wins 52.4% of decided NFL bets and 52.2% of CFB bets. At −115 that is an EV of **−1.9% (NFL) and −2.3% (CFB)**; at −110 it is about even (+0.1% and −0.3%). A bigger gap or a better price turns it positive. So if Pinnacle is right, H2's minimum flags should show *negative* CLV against Pinnacle's close, about −1 cent, and H2 passes only if the average flag had value or the lagging books really do trail Pinnacle. Whether H2 should also require a non-negative EV at Pinnacle's price is owner decision 7.

**No snapshot at or after kickoff is ever an entry.** A snapshot is dropped if it is at or after the kickoff it lists itself, or the kickoff listed in the game's latest snapshot, in-play snapshots included (kickoffs move). Tests check this, including a kickoff that moved earlier and one that moved later.

## 5. Entries: one bet per game, market and side

For each variant, the bet on a game, market and side is the **first snapshot at which that side is flagged**, at the flagged retail book with the best EV. For H2 it goes to the biggest gap, then the best price (see amendment 1). The price taken is that book's posted price at that snapshot. Later flags on the same side of the same game are not extra bets.

**Only snapshots more than 60 minutes before kickoff can be entries.** The close is what every bet is graded against. A flag first seen at the close would have a CLV equal to its own EV by construction, which is the circularity the plan review warned about, so the close is never an entry.

- **Both kickoffs must be more than 60 minutes away:** the one listed in that snapshot, which is what a bettor saw at the time, and the latest-listed one. The latest one is known only later, so it may only remove an entry. On its own it could add one: a game listed for 16:30 at the 16:00 snapshot and later moved to 20:00 would make 16:00 look four hours early when it was 30 minutes early.
- **Entries are not only the daily snapshots.** Every F1 snapshot lists every game, so another game's close is an entry snapshot too if it is more than an hour before this game's kickoff. On game days, and on college Saturdays especially, that gives several entry snapshots a few hours or less apart.

## 6. Grading

| Measure | Definition |
|---|---|
| **CLV against Pinnacle's close, in cents (primary)** | 100 × (Pinnacle's no-vig closing probability of the bet's side **at the bet's line**, minus the break-even probability of the price taken, 1/d). Positive means the price beat Pinnacle's close. A close at another number is converted to the bet's number: totals with the registered model (section 3), spreads with the margin table below. Every bet with a Pinnacle close counts. |
| CLV against the entry book's own close, in cents | The same arithmetic against that book's own no-vig closing price. This is #53's check: did the lagging book move to where Pinnacle already was? It is condition A6 for H2 and reported for H1. |
| CLV in points (spreads and totals) | Against Pinnacle's close and against the book's own close. Positive when the close moved toward the bet: a lower total for an under, a higher total for an over, a bigger number for the side taken on a spread. It needs no conversion, so the report prints it next to CLV in cents. |
| What an efficient Pinnacle implies | For each bet, its EV at Pinnacle's price divided by the decimal price taken, in cents (about 1 cent for a 2% flag). The report prints the cell's average (`clv_pin_expected`) next to its CLV; section 7 explains why. |
| Realized result at the price taken | Flat one-unit bets: win rate, ROI (pushes left out) and a 95% interval (see amendment 1). |
| The close | A book's quote in its last snapshot before kickoff, only if that snapshot is within 60 minutes of kickoff. F1's close is 5 to 10 minutes before. A bet whose book, or Pinnacle, has no close is left out of that CLV column and counted: the report prints how many bets each cell graded (`clv_pin_n`) next to its bet count. |

Standard errors are clustered by game throughout (see amendment 1).

**Spread closes at another number.** Spread lines move often: in the repo's SBR NFL data, only 18.4% of spreads close on their opening number (740 of 4,020 games, 2007–21). The first draft graded a spread bet only when Pinnacle closed on the bet's number. That left out most spread bets, and it left out exactly the ones where Pinnacle later moved to the retail book's side, the failure section 7 says this test catches. So a moved close is converted, with the same "only the mass between the numbers" rule as totals:

> P(side covers at L) = q × (1 − P(push at L0)) + [P(margin + L > 0) − P(margin + L0 > 0)], and P(push at L) = P(margin + L = 0),
>
> where q is Pinnacle's no-vig chance the side covers at its closing spread L0, and the margin chances come from the table below.

- **The table** (`sharp-markets/src/markets/research/price_engine/spread_cohort.json`, hashed in `model.py`). It holds every game in the repo's processed tables with a closing spread and a final score, from the seasons before the backtest: NFL 1999–2019 (5,583 games, nflverse) and CFB 2006–2019 (9,396 games, the cfb-weather table). Each game counts from both sides. For a closing spread L0, the margins used are those of the 1,000 entries whose closing spread is nearest L0, ties included. That way the key numbers come from games priced near L0.
- **Example.** An NFL bet on −3 whose Pinnacle close is −2.5 at even odds is worth 45.3%, not 50%. Among games priced near −2.5, 8.7% ended on exactly 3, which turns a win at −2.5 into a push at −3. If Pinnacle closes at −3.5 instead, the same bet is worth 55.4%.
- **Its weak points.** It is a model, and it is only as good as its landing rates. In 2020–25, NFL margins of exactly 7 near a −7 spread came up 4.9% of the time, against 6.3% in the table, so crossing 7 is slightly overvalued (about 0.6 to 0.8 cents per crossing). Margins of 3 near −3 barely changed (9.0% in 2020–25, 9.0% in the table). Landing rates for 1999–2014, 2015–19 and 2020–25 were looked at before the seasons were chosen, and that is disclosed here. The table uses every season before 2020 so that nothing from the backtest seasons enters it; 2015–19 alone (1,335 NFL games) was too small. It is used only to grade closes, never to flag a bet, so it adds no variant.
- **In the report.** Each primary spread and total cell shows its CLV on same-number closes and on converted ones separately, and in points. If the converted bets are well below the same-number ones, Pinnacle's later moves went against the flags.

## 7. Decision rules

Each **primary cell** is judged on its own: H1 at the 2% threshold against Pinnacle, for each of NFL and CFB × totals, spreads and moneylines (6 cells), and H2 for each of NFL and CFB (2 cells). The other 30 cells are reported and never decide anything, except that the blend's 2% cell enters condition A5 below. The script computes these verdicts itself (`engine.decide`), and a test checks the rules.

**Too few bets.** Fewer than 100 bets in the cell, or fewer than 100 with a Pinnacle close. The cell is reported, and nothing goes forward from it.

**Kill: the idea is dropped for that cell** if any one of these holds:

- K1. Mean CLV against Pinnacle's close is at or below zero.
- K2. Realized ROI's 95% interval lies entirely below zero (see amendment 1).
- K3. With the book that has the most bets removed, mean CLV is at or below zero, or no bets are left (see amendment 1). One book carries it.
- K4. With the season that has the highest mean CLV removed, mean CLV is at or below zero, or no bets are left. One season carries it.

**Act: this justifies a pre-registered paper forward test on the 2026 season** only if nothing kills the cell and all of these hold:

- A1. Mean CLV against Pinnacle's close is above zero with **one-sided p < 0.05 / 271 = 0.000185** (see amendment 1).
- A2. At least 3 seasons have 20 or more bets, and CLV is above zero in all of those seasons but at most one (see amendment 1).
- A3. CLV is above zero on the bets where Pinnacle's market was updated at least as recently as the retail book's. Where Pinnacle's quote is older than the book's, the gap may be Pinnacle being stale; either timestamp missing counts as stale.
- A4. CLV is above zero on the bets with EV below 10% (see amendment 1). The fattest prices are the ones a book is likeliest to void as obvious errors.
- A5. H1 only: the blend version's 2% cell also has CLV above zero.
- A6. H2 only: mean CLV against the lagging book's **own** close is above zero. Issue #53 asks that H2 be graded on exactly this: did the book that held the old number move to where Pinnacle already was? For H1 it is reported and decides nothing (owner decision 6).

**Inconclusive: everything else.** Typically CLV is positive but not below the bar. No forward test comes from this backtest. The idea can still be logged on paper descriptively.

**What an "act" does not mean.** It means the price engine's premise held up at F1's resolution (a daily snapshot plus other games' closes) in 2020–25, and nothing more. The forward test's own registration fixes its metric and horizon before its first eligible game. The suggested version is mean CLV against Pinnacle's close with its 95% interval above zero, after at least 150 bets. That is a separate pre-registration.

**What CLV against Pinnacle's close tests, and where it stops.** The flag uses Pinnacle's price at an earlier snapshot, up to seven days out, and the close is a later, sharper price.

- **What it catches.** If a gap exists because Pinnacle was slow (the retail book moved first on news), Pinnacle's close moves to the retail book's side and the CLV disappears or turns negative. That is the main way "beat the sharp line" fails in practice. For totals and, since the revision, for spreads, those bets are in the main number: a close at another number is converted, not dropped (section 6).
- **Why a pass is close to automatic if Pinnacle is right.** If Pinnacle's price is right and moves only on new information, a flag at EV e and decimal price d is expected to show CLV of e / d against Pinnacle's close. That is **1.03 cents** for a 2% flag at 1.95, and 1.28 cents at 2.5%. With a spread of about 6 cents per bet, a cell whose flags average 2.5% EV clears the bar (p < 0.000185) with 80% power at about **425 bets**; at exactly 2%, about 660. (The draft worked these out at its bar of 0.00021: about 420 and 650.) So an H1 cell with several hundred bets passes A1 almost automatically if Pinnacle is efficient. The report prints this expected figure (`clv_pin_expected`) next to each cell's CLV. A cell near it means the flags kept their value to the close; well below it means Pinnacle moved toward the retail prices.
- **What it cannot catch.** Pinnacle's close itself being wrong. A pass says Pinnacle was not the slow side and the flagged prices beat the sharpest price available; it does not show that Pinnacle's close is right. The plan review raised exactly this ([`plan-review-2026-09-28.md`](../../strategy-research/plan-review-2026-09-28.md), section 3), and the data-use plan ([`odds-api-credits.md`](../../strategy-research/odds-api-credits.md), row F1) called CLV to Pinnacle "tautological when Pinnacle defines the flag" and asked for ROI and CLV to the book's own close instead. This draft keeps Pinnacle's close as the main test for the reasons in section 9, requires the book's own close for H2 (A6), and leaves the choice for H1 to the owner (decision 6). Only results can test the close itself, and section 9 shows they need far more bets than F1 has. So the report adds a descriptive check of how well Pinnacle's no-vig close matched results on every game it priced, and a pass leads to paper, not money.

## 8. Variants and the multiple-testing bar

| Family | Count |
|---|---|
| H1: 2 sports × 3 markets × 2 fair versions × 3 thresholds | 36 |
| H2: 2 sports | 2 |
| **This draft** | **38** |
| Running count before it | 233 |
| **Running count after it** | **271, so the bar is p < 0.05 / 271 = 0.000185** |

- **Not counted: the descriptive tables.** These are the calibration of Pinnacle's close, how often each book sits a point or more off Pinnacle, and the per-book splits. They can't select a rule, so they add no false-positive risk.
- **Counted in full, conservatively.** The data-use plan already counted 9 price-engine variants (3 thresholds × 3 markets) in the 200. Netting those out would give 262 and a bar of 0.000191. The difference doesn't matter; decision 2 counts all 38.
- **The revision adds none.** The spread margin table only grades closes, and A6 is a decision condition on the same 2 H2 cells, so the count stays 38.
- **The count before this draft was set at registration, September 29, 2026: 233.** That is 200 (STATUS.md on September 28), plus 32 for the landing-mass table (PR #55, issue #52) and 1 for the CFB forecast replay (PR #61, issue #40), both merged first. The count after it is **271**, and the bar **0.05 / 271 = 0.000185**. `PRIOR_COUNT` in `engine.py` and this table state the same count. A test fails if the two disagree.

## 9. How many bets it takes, and why the decision is on CLV

This is back-of-envelope arithmetic from the repo's own numbers. It is not from F1.

- **CLV.** The plan review measured line moves from an early bet to the close at about 2.3 points (NFL) and 2.7 points (CFB) either side. Near the middle of a total, one point is worth about 2.5 cents of probability. So a bet's CLV varies by roughly ±6 cents.
  - To detect a true average CLV of **1 cent** at the bar (p < 0.000185, one-sided z = 3.56, 80% power) takes about **700 bets**.
  - **2 cents** takes about **175 bets**.
  - **0.5 cents** takes about **2,800 bets**.
  - (The draft worked these out at its bar of 0.00021, z = 3.53: about 690, 170 and 2,700 bets, and 48,000 for profit below. The registered bar raises each by about 1.6%.)
- **Profit.** One bet's result varies by about ±1 unit.
  - A true 2% edge needs about **15,000 bets** to show at the ordinary 5% level.
  - At the bar it needs about **48,500**.
  - With 1,000 bets, the ROI's 95% interval is about ±6 points wide. A real +2% edge would read as something like "+2% ± 6%".
- **What this means for the plan's earlier rule.** The data-use plan ([`odds-api-credits.md`](../../strategy-research/odds-api-credits.md#data-use-plan), row F1) asked for "realized ROI positive with a 95% interval above zero". At 1,000 bets, that rule rejects a true 2% edge about 9 times in 10 and a true 3% edge about 8 times in 10. That is why this draft decides on CLV and keeps ROI as a veto (K2). The change is the owner's to accept (decision 1).
- **Unknown until F1 lands.** How many flags each cell will have. It could be a few hundred or a few thousand, depending on how often retail prices stray. A cell under 100 bets decides nothing.

## 10. What daily data cannot show

- **Gaps that last minutes.** F1 sees each game at 16:00 UTC (late morning in the US) on each of the 7 days before it, at every other game's close, and at its own close. A soft book that lags Pinnacle by 20 minutes after a wind forecast, which is #53's example, is seen only if one of those moments falls inside the 20 minutes. So short gaps are mostly missed and long ones are over-represented. The output says so on every run.
- **How long a gap lasted.** The report shows only whether the same book still had the gap at its next snapshot of that game. Early in the week that is a day later; on game days it is often another game's close, minutes to a few hours later. So that share mixes very different time gaps and is not a duration. The 10-minute trigger poller (#53, task 1) is the tool for duration.
- **Whether a quote was fillable, or for how much.** The Odds API shows posted quotes, not limits. The stake a book would have accepted is unknown for every F1 flag, and the output records it as unknown.
- **Whether the feed was current.** A book's quote in the feed can itself lag the book. `last_update` is used only for the staleness check (A3), never to time a bet.
- **Mostly one time of day.** Away from game days, a gap that opens in the evening and closes overnight never appears. Late morning may also be when books are at their stalest after overnight moves, which could make gaps look more common than they are at other hours.
- **Other lines.** Alternate lines, team totals, exchanges and props are outside F1. Alternates are F2's separate question.

## 11. Cautions written into the rule (from #53)

- **Books void obvious errors.** A price far off the market can be cancelled after the fact. A4 requires the result to survive without the flags at 10% EV or more, and `bets_ev_10plus` counts them.
- **Books limit accounts that take stale numbers.** Kaunitz, Zhong and Kreiner made money betting soft prices against the consensus until the books limited them within months. Even if this works, the real-money ceiling is small and shrinks as it's used.
- **A posted quote is not always a fillable one.** The stake a book would accept is recorded where it's known (the paper fill log, `scripts/log_fill.py`, when the owner checks a live price) and marked unknown everywhere else.
- **Paper only.** Nothing in this code places, sizes or routes a bet.

## 12. Decisions, as registered

Decided September 29, 2026, at registration, on the owner's standing instruction. Changing any of them is a dated amendment, made before the affected result is seen.

1. **Decide on CLV, with ROI as a veto, as in section 7.** This replaces the data-use plan's "ROI with a 95% interval above zero". The ROI rule would reject a true 2% edge about 9 times in 10 (section 9).
2. **All 38 variants are counted; the running count is 271 and the bar is p < 0.000185.** Netting out the 9 price-engine variants the data-use plan already counted would give 262 and 0.000191. Counting all 38 is the conservative choice, and the two bars barely differ.
3. **If a college football totals cell reaches "act", a paper forward test of that cell is registered for the 2026 season before its first eligible kickoff; otherwise the live log is descriptive only in 2026 (see amendment 1).** The plan review says both CFB 2026 slots are already taken (Rule B and Rule HT), but the live log costs no credits and no money, and a CLV test is decidable in a few hundred bets.
4. **No money goes on this rule until a paper forward test of it has been decided.** This is the project's standing rule (CLAUDE.md). Only the owner can change it, by a dated amendment. A backtest pass earns a paper test, and under the repo's own rules real money waits for that test's decision. The earliest honest path to a real CFB bet is a pass on Oct 1–2, a paper test from mid-October, and a decision when its bet count is reached, which is likely late 2026 at the earliest and more likely 2027.
5. **Books F1 never saw (Bovada, Hard Rock Bet) are logged and left out of every decision.** Bovada is also offshore, which is not one of the venues the owner named (US regulated books, Kalshi, Pinnacle).
6. **Option (a): Pinnacle's close decides H1; the book's own close is reported for H1 and required for H2 (A6).** The data-use plan asked for CLV to the soft book's own close, because CLV to Pinnacle is "tautological when Pinnacle defines the flag"; this switches the main test to Pinnacle's close. The cost of that switch in numbers: if Pinnacle is right, a 2% flag is expected to show about 1.03 cents of CLV against Pinnacle's close (1.28 cents at 2.5%), and a cell of about 425 to 660 bets would pass A1 almost automatically (section 7). Option (a) catches the main failure, Pinnacle being the slow side. But a pass under (a) means less than it sounds: it says Pinnacle wasn't the slow side, not that Pinnacle's close is right. Not chosen:
   - **(b) The plan's version:** also require CLV to the book's own close above zero for H1. That tests a different thing, whether the retail book later corrected its price. A book that shades one kind of price on purpose and never corrects would fail it even if the bets were good, and a consistently soft book is the most usable kind.
   - **(c) Test against what an efficient Pinnacle implies:** pass only if CLV is not clearly below `clv_pin_expected`, meaning the flags kept their value to the close. With a few hundred bets this has little power.
7. **No expected-value floor on H2; the trigger stays as issue #53 wrote it.** At its minimum trigger (exactly 1 point, at −115), an H2 bet is about 2% negative EV at Pinnacle's own price (section 4). Adding the EV floor would make H2 mostly a copy of the H1 totals cells, and the cell's CLV already shows whether the average flag had value.
8. **The spread margin table of section 6 (every game before 2020, the 1,000 nearest-spread entries) is used to grade a spread close at another number; CLV in points is printed beside CLV in cents.** Points ignore the price: a spread flag is a better price at Pinnacle's own number, and if Pinnacle is right its line doesn't move on average, so points CLV would be about zero even for a real edge.

---

## The live form for this season: a CFB price-engine paper log from the call the alerts already make

This section describes what the log would record. It changes no alert code, spends no extra credits, and places no bet. The hub decides whether and where to build it.

**What already arrives, for free.**
- **The alert runs.** The CFB alert job runs four times a day (07:30, 11:30, 15:30 and 19:30, Mac time). Each run makes **one** Odds API call:
  - `americanfootball_ncaaf/odds`, `markets=totals`, at 1 credit;
  - for **10 books**: Pinnacle, LowVig and BetOnline (sharp), and DraftKings, FanDuel, BetMGM, BetRivers, Bovada, ESPN BET and Hard Rock Bet.
- **Saved first.** The whole response is saved to `cfb-weather/data/raw/oddsapi/live/<time>.json` before it's parsed.
- **Close capture.** The same kind of call runs 2–20 minutes before each kickoff slot and saves the same kind of file.
- **The trigger poller.** On a paid plan, it saves a file every 10 minutes for games with a wind trigger (`*_poll.json`).
- **So a price-engine log needs no new call.** A small script that reads each new saved file after the run has everything. Pinnacle priced 56 of 58 college games in the Sep 28 live check.

**What the log would record, one row per saved file × game × retail book × side:**

| Field | What it holds |
|---|---|
| `snapshot_utc`, `source` | The file's time, and whether it came from an alert run, close capture or the poller. |
| `event_id`, `kickoff_utc`, `home`, `away`, `sealed` | The game. Every 2026 row is `sealed=True`; see below. |
| `pin_total`, `pin_over`, `pin_under`, `pin_update` | Pinnacle's quote and its `last_update`. |
| `fair_under_pin`, `fair_under_blend` | Pinnacle's Shin no-vig P(under) at its total, and the three-book blend. These are **the probabilities**: one for every game Pinnacle prices, four times a day. |
| `book`, `total`, `over`, `under`, `book_update` | The retail quote. |
| `p_side`, `ev_pin`, `ev_blend` | The fair probability at the book's own total (the registered conversion, same as the backtest) and the EV of each side. |
| `flag_1`, `flag_2`, `flag_3`, `flag_lag` | The H1 flags at 1/2/3% and the H2 lag flag, exactly as in section 4. |
| `entry` | True on the first flagged row per game and side, at the best book: the paper bet. |

**Grading.** Each entry is graded, as in the backtest:
- CLV against Pinnacle's close and against the entry book's own close, both from the close-capture file for that kickoff slot;
- then the final score.

**What it can't do, stated plainly.**
- **Totals only.** Spreads and moneylines aren't in the call. Adding them makes each call 3 credits: about +240 a month for the alerts' ~120 calls. That changes the alert call, so it is the hub's decision.
- **Four snapshots a day.** Like F1, it only sees gaps that last hours. The poller's 10-minute grid covers windy games only.
- **A different book list from F1.** F1 has Caesars and Fanatics, which the alerts don't. The alerts have Bovada and Hard Rock Bet, which F1 doesn't. Only DraftKings, FanDuel, BetMGM, BetRivers and ESPN BET are in both, and only those five should count toward a decision (owner decision 5).
- **The sealed season.** Every 2026 CFB row is sealed holdout data. The log may record it from the start, but nothing analyses it until a forward test is registered before its first eligible game (owner decision 3).
- **Stake limits are unknown.** The row says so. A manual check can go into the fill log.

**The order of events.**
1. **Done, September 29, 2026.** The hub registered this draft, with decisions 1–8 as in section 12 and `PRIOR_COUNT` set to that day's running count, 233 (section 8).
2. F1 is pulled on Oct 1, and `uv run markets price-engine` runs the same day.
3. If a CFB totals cell reaches "act" and you choose the 2026 test (decision 3), the forward test is registered before the next Saturday's first kickoff.
4. The hub adds the logging script as a separate launchd job, or as a step after each alert run, touching no alert code.
5. The paper log starts.

If nothing reaches "act", the same log can still run descriptively. It supplies the probabilities, but it produces no signal to act on.

---

## Not done yet

- **Issue #53, task 1: measure the lag from the live logs** (how often a book sits a point off Pinnacle, how long the gap lasts on the poller's 10-minute grid, which books lag, and whether the lagging number beats the book's own close and Pinnacle's). **Blocked, for two reasons.** The live logs don't carry the fields yet: on September 29 neither live `data/forward/` folder has a `trigger_polls.csv`, and neither `ledger.csv` has the `ref_total`, `best_line` or `ev_best_line` columns that PR #50 added. And every one of those rows is 2026 data, which is sealed until a forward test is registered before its first eligible game. It can start once the alert jobs run the #50 code and a forward test (decision 3) is registered.
- **Issue #53, task 2 (the F1 version)** waits for F1 (October 1). The code is ready.

---

## Amendment 1 (2026-09-30 Pacific, before any F1 data exists; nobody has seen an F1 price)

**Who registers it.** The hub, on the owner's standing instruction of September 29, 2026. It is registered when the hub merges it, before the F1 pull on October 1, 2026.

**Why.** On September 29, 2026 an outside audit looked at this engine (Gemini audit 3, as the owner pasted it: `notes/gemini-audit-3-as-pasted.md` on the `hub-briefs` branch), and the hub ran three checks of its own the same day, all under `handoff/price-engine/` on that branch:

- **The claims check** (`the-audits-claims.json`): 55 tests on made-up data, from `claims/test_pe_mine.py`, each shown to fail on deliberately broken code. (The brief's count of 74 also counts the weather scorers' 19 tests, which are outside this amendment.) It found twelve defects, D1 to D12. The audit's own scripts mostly printed rather than tested (D12), so this amendment rests on the checker's tests, not on the audit's list of what held up.
- **The names check** (`team-names.json`, with `names/alias_proposal.csv`): how the engine turns The Odds API's college team names into the schools in the score table.
- **The full-size run** (`full-size-run.json`): the engine on a made-up cache the size and shape of F1.

No F1 data exists and nobody has seen an F1 price, so nothing here was chosen by looking at a result.

**What stays the same.** Still 38 variants, 8 of them deciding. The running count stays 271 and the bar p < 0.05 / 271 = 0.000185. (The higher counts in STATUS.md come from tests added after this registration. They don't move this test's bar.) No threshold, flag, entry rule or grading rule changes. What each item can do to a verdict:

- **Items 1, 3 and 4** can only make a verdict harder to reach.
- **Items 5, 6 and 7** change no result. Item 5 leaves the 2026 rows out as the file is read instead of just after, which changes no number. Items 6 and 7 write down readings and numbers already in force.
- **Items 2 and 8** repair loading and matching. They add quotes and final scores that were wrongly lost, so a verdict can move in either direction, toward "act" as well as toward "kill". An adversarial review of this amendment built made-up cells where each repair turns "kill" into "act". Both repairs were made before any F1 data exists, so nobody can know which way they will move a verdict.
- **Item 9** is a record, with no code.

The hub's decision text of September 29 says that every decision "either states what the code already does, repairs loading, or makes a verdict HARDER to reach. None makes one easier." That last sentence is corrected here for items 2 and 8, and the hub confirms the correction when it registers this amendment.

The tests for this amendment are `sharp-markets/tests/test_price_engine_amendment1.py`, plus the checker's tests, brought in as `sharp-markets/tests/test_price_engine_checks.py`. The checker's tests that asserted a defect are turned round to assert the repair.

### Item 1. Which seasons count for A2 (defect D2). Code changed.

A2 reads: "At least 3 seasons have 20 or more bets, and CLV is above zero in all of those seasons but at most one." That sentence counts every bet. The code counted only the bets that have a Pinnacle close. The checker built two made-up cells to show the two readings disagree. In one, the sentence passes a cell the code fails. In the other, the code passes a cell the sentence fails. From now on A2 uses the reading that satisfies both:

- **A season is counted** when it has 20 or more bets.
- **A counted season is above zero** only when 20 or more of its bets have a Pinnacle close and the mean CLV of those bets is above zero.
- **A2 holds** when three things are true: at least 3 seasons are counted, at least 3 seasons have 20 or more bets with a Pinnacle close, and every counted season but at most one is above zero.

A cell that passes this A2 passes both earlier readings. So nothing can pass now that either reading would have failed. The tests show this on the checker's two cells, on two cells of our own and on 400 random made-up cells.

*Example.* 2020, 2021 and 2022 each have 50 bets, all with a Pinnacle close, at +2 cents. 2023 has 22 bets, and only 18 of them have a Pinnacle close. 2023 is counted, because it has 22 bets. It can't be above zero, because only 18 of its bets have a close. It is the one season A2 lets miss, so A2 holds. If 2024 looked like 2023 as well, that would be two misses, and A2 would fail. The checker's cell of 50, 50 and 22 bets (18 with a close) fails, because only 2 seasons have 20 or more closes.

`results.csv` now prints `seasons_counted` (20 or more bets), `seasons_20_closes` (20 or more bets with a Pinnacle close) and `seasons_positive` (counted seasons above zero).

### Item 2. Reading F1 (defect D1). Code changed.

F1 is now read **one call at a time**. Before about September 18, 2022, The Odds API kept one snapshot every 10 minutes and answered each request with the latest snapshot at or before the requested time. So two F1 calls 5 minutes apart can get back the same snapshot. The code read 50 calls at a time and grouped each book's prices by game, snapshot, book and market. Two copies of one snapshot made a group of four prices instead of two, and the whole group was thrown away (logged as `*_not_two_outcomes`, the wrong reason). Whether that happened depended on where the batch of 50 happened to end.

Now a snapshot that two calls returned is read once, wherever the two calls fall. The first call that returns a snapshot of a sport is read. Every quote of a later call that returns the same snapshot is counted once, as `duplicate_snapshot`, before any other reason. So no quote is counted twice: a second copy of a quote listed after its kickoff is not also counted as `at_or_after_kickoff`. The count `duplicate_snapshot_conflicting_price` is part of `duplicate_snapshot`, not a further drop: it counts the repeated quotes whose price differs from the copy kept.

*Example.* On a college Saturday in 2021, the 16:00 UTC daily call and the 15:55 close call for the noon Eastern games can both get back the 15:55 snapshot (if the 10-minute grid sat at :x5; nobody knows which minute it sat on). Before, every game's prices in that snapshot were dropped: the noon games lost their close, and every other game lost that morning's entry snapshot. Now one copy is kept.

*Proof that nothing else moves.* On input with no repeated snapshot, the loading repair alone (the registered code with only `quotes.py` replaced) gives `results.csv`, `dropped.csv` and `bets.parquet` byte for byte as the registered code does. That was checked on the engine's `--fixture`, on a made-up cache of 568 F1 calls from 2021 and 2024, and on the 242 calls after September 1, 2022 of the reviewer's made-up cache. With the whole amendment, `dropped.csv` and `bets.parquet` are still byte for byte the same on that input (with the alias table emptied for the reviewer's cache, whose made-up names need it: item 8 adds scores there). `results.csv` differs only in the columns items 1 and 3 change (`seasons_counted`, `top_book` and `clv_pin_wo_top_book`, plus the new `seasons_20_closes`), and no decision moved.

On the reviewer's made-up cache of 380 calls, where 16 snapshots were each returned to two calls, the registered code dropped 22,406 groups as `*_not_two_outcomes` (each group held two copies of one quote). The repaired code keeps one copy and counts 27,827 quotes as `duplicate_snapshot`. That is every quote of every second copy, including the ones that would otherwise have been counted as listed after kickoff or as more than 7 days before it. Quotes read, counted call by call, equal quotes kept plus every drop reason (431,910 = 251,400 + 180,510), so no quote is counted twice. Time is about the same and memory goes down (item 9).

### Item 3. K3 when books tie (defect D4). Code changed.

K3 removes "the book that has the most bets". When two or more books tie for the most bets, each tied book is removed in turn. K3 kills if any one of those removals leaves the mean CLV at or below zero, or leaves no bets. As coded, "no bets" means no bet with a Pinnacle close, the same as for a single top book. `top_book` in `results.csv` lists every tied book, joined by "+". Before, the order of the rows decided which tied book was removed, so the verdict could depend on row order.

*Example.* 60 DraftKings bets average +3 cents and 60 FanDuel bets average −1 cent. Removing DraftKings leaves −1, so K3 kills, whatever the row order. Before, one order killed the cell and the other did not.

### Item 4. K2 needs results (defect D3). Code changed.

K2 kills a cell when the 95% interval of its realized return lies entirely below zero. That needs final scores, and a cell with few or none could never be killed by K2. From now on, **a primary cell with fewer than 100 bets that have a final score cannot reach "act"**. Its verdict is "inconclusive: too few results to check the return". A bet counts toward the 100 only if it has a final score and won or lost. A push returns the stake and is left out, as it is in the return itself. `results.csv` already calls this count `graded`. **This is stricter than the hub's decision text**, which speaks of "bets with a final score": a push has a final score but is not counted here. Leaving pushes out can only make "act" harder to reach, and the hub confirms this reading when it registers the amendment. The kill rules K1 to K4 are checked first and still kill such a cell; this rule only stops it from acting. The report's main table now shows `graded` for every cell, with `pushes` beside it.

*Example.* A cell has 150 bets, all with a Pinnacle close, but final scores were matched for only 40 of them. Before, K2 could fire on only those 40 results, and if it didn't, the cell could "act". Now it is "inconclusive: too few results to check the return".

### Item 5. No 2026 row reaches the engine (defect D7). Code changed.

Section 2 says the backtest "never loads 2026 scores". Before, three readers of the game tables read every row, 2026 included: the two score readers, which dropped the 2026 rows afterwards, and the reader of the spread margin table (`model.spread_pairs_from_tables`), which keeps only 1999 to 2019 (2006 to 2019 for college) and runs only when that frozen table is rebuilt. Now all three filter on the season as the file is read, so no 2026 row reaches the engine. (The file reader, pyarrow, may still decode a block of the file before it applies the filter; what it hands over holds no 2026 row.) The checks after the read stay as a second layer. Nothing from 2026 ever reached an output, before or now, and the frozen spread table's hashes are unchanged for both sports (a test).

*Example.* A table with a 2024 row and a 2026 row: the reader receives only the 2024 row. The tests check all three readers, for the NFL and college football.

### Item 6. What "act" means for a cell other than college football totals (the audit's finding 1). No code.

Decision 3 names a college football totals cell because totals are the only market the live alert jobs log. For any other primary cell that reaches "act" (NFL totals, spreads or moneylines, NFL H2, or college spreads or moneylines), section 7 applies as written. The result justifies a paper forward test. That test must be registered before its first eligible game, and it needs a live log of that market. Starting such a log changes the alert jobs' Odds API call and what it costs in credits, and that is the owner's decision. Until a test is registered, nothing is logged toward a decision for that cell. No money goes on it in any case (decision 4).

*Example.* NFL spreads reaches "act" on October 1. Nothing is bet. The hub may propose a paper forward test of NFL spreads, and the owner decides whether the alert job's call adds spreads to feed it.

### Item 7. Numbers and rules the registration did not state (defects D5 and D8, the audit's finding 4). No code, except tests that pin them.

Each row below was checked against the source code and `config/odds5m.yaml` for this amendment. These values are now fixed. Changing any of them is an amendment.

| What | The rule, as coded |
|---|---|
| **Final scores, NFL** | The feed's team names become team codes through `config/teams/nfl.csv` and three older names: Washington Football Team and Washington Redskins are WAS, and Oakland Raiders is LV. The two teams must match, in either order. The score table's game day must be within 1 day of the kickoff's date in New York time, using the latest-listed kickoff. There must be exactly one such game; with none the game is logged as `nfl_no_game`, and with two or more as `nfl_ambiguous`. *Example:* a Sunday 8:20 PM Eastern game (01:20 UTC Monday) is matched to Sunday's game. |
| **Final scores, college** | The two schools (item 8) must match, in either order, and the score table's start time must be within 36 hours of the latest-listed kickoff, 36 hours included. If more than one game qualifies, the nearest is used, and an exact tie goes to the one listed first in the table. *Example:* a game listed 30 hours from the table's start time is matched; one listed 40 hours away is not (`cfb_no_game`). Both sports: the scores are put on the feed's home and away sides. |
| **The early cut at 9 days** | As each call is read, a quote is dropped if the kickoff listed in its own snapshot is more than 9 days after the snapshot (the 7-day window plus a 2-day margin, `COARSE_MARGIN`). This keeps memory small. After that, the exact rule applies: a quote more than 7 days before the latest-listed kickoff is dropped, and exactly 7 days is kept. *What the cut can drop:* a quote the exact rule would keep, when the game is later moved more than 2 days earlier. *Example:* a day-0 snapshot lists the kickoff on day 10, so it is cut. On day 1 the game moves to day 5, which makes the day-0 quote 5 days out, a quote the exact rule would keep. It is counted as `more_than_7_days_before_kickoff`. The cut only ever removes quotes, so it can't add lookahead. |
| **Standard errors** | Game-clustered: SE = √(k/(k−1) × Σ over games of (the sum of that game's deviations from the mean)²) / n, for n bets in k games. The factor k/(k−1) is a small-sample correction. With fewer than 2 games there is no SE and no p, and an SE of exactly zero gives no p. |
| **The one-sided p** | From the normal curve: p = 1 − Φ(mean / SE). A t distribution is not used. |
| **The 95% return interval** | The mean return ± 1.96 game-clustered SEs of the per-bet profit. It needs at least 2 graded bets (and 2 games); otherwise it is empty and K2 can't fire. |
| **Thresholds** | The flags are inclusive, with a tolerance of 1e-9: EV ≥ threshold − 1e-9, gap ≥ 1 point − 1e-9, and price ≥ 1 + 100/115 − 1e-9. The decision rules compare strictly: "above zero" means > 0, the bar means p < 0.000185, and K2 kills when the interval's upper end is < 0. A4's cut has no tolerance: its mean CLV is over the bets with an EV at entry below 10%, strictly (`ev_entry < 0.10`), and `bets_ev_10plus` counts the rest (`ev_entry ≥ 0.10`). With no bet below 10%, A4's mean is empty and A4 fails. |
| **"−115 or better"** | A decimal price of 1 + 100/115 = 1.869565… or more. Section 4's "decimal 1.87" is rounded: 1.8696 counts and 1.8695 doesn't. |
| **H2's order, and ties** | At the first flagged snapshot, the bet goes to the flagged book with the biggest gap, then the best price, then the book whose key comes first in alphabetical order. The code ranks by one score, gap × 1000 + price. Totals move in half points, so two gaps differ by 0.5 or more, which is 500 in the score. So the score gives the same order as "gap, then price" as long as the smaller gap's decimal price is less than 500 above the other's. Above a decimal price of about 500 (500 more than the other book's price) it fails, and the smaller gap goes first: a book 1 point off at a decimal price of 1002 (the auditor's case D8) ranks ahead of a book 1.5 points off at 1.95, because 1,000 + 1,002 = 2,002 is more than 1,500 + 1.95 = 1,501.95. The order stays as coded (a test pins it); a price that high is almost certainly an error. For H1, a tie on EV also goes to the book whose key comes first alphabetically. *Example:* FanDuel 1.5 points off at 1.87 beats DraftKings 1 point off at 2.10. |
| **Batch size** | None. F1 is read one call at a time (item 2). |
| **Minimums** | `MIN_BETS` = 100: bets, bets with a Pinnacle close, and (item 4) graded bets. `MIN_SEASON_BETS` = 20 (item 1). |
| **Season windows** | Each game's season is the window below that contains the UTC date of its latest-listed kickoff, both end dates included. A game outside every window is left out and counted as `outside_season_windows`. The 2026 windows are sealed. The windows live in `config/odds5m.yaml`, and a test fails if they change there. |

| Season | NFL window | College football window |
|---|---|---|
| 2020 | 2020-09-01 to 2021-02-15 | 2020-08-25 to 2021-01-15 |
| 2021 | 2021-09-01 to 2022-02-20 | 2021-08-20 to 2022-01-15 |
| 2022 | 2022-09-01 to 2023-02-20 | 2022-08-20 to 2023-01-15 |
| 2023 | 2023-09-01 to 2024-02-15 | 2023-08-20 to 2024-01-15 |
| 2024 | 2024-09-01 to 2025-02-15 | 2024-08-20 to 2025-01-25 |
| 2025 | 2025-09-01 to 2026-02-15 | 2025-08-20 to 2026-01-25 |
| 2026 (sealed) | 2026-09-01 to 2027-02-20 | 2026-08-20 to 2027-01-25 |

### Item 8. College team names (the audit's finding 3, the names check). Code changed.

The Odds API calls a college team "School Mascot", and the score table uses the school alone. Before, the engine found the school through cfbfastR's team files, which exist only in the Mac's live checkout. Failing that, it took the longest school name the feed's name starts with (the prefix rule). The prefix rule can pick the wrong school: "Miami RedHawks" went to Miami (Florida), not Miami (Ohio). And a game lost that way was logged as "no game", not as a name problem. Three changes:

- **An alias table is consulted first**, before the team files and the prefix rule. Each row gives a feed spelling, written the way the engine normalizes it (lower case, with accents and punctuation removed, so "Miami (Ohio) RedHawks" becomes "miami ohio redhawks" and "Louisiana-Monroe" becomes "louisianamonroe"), and the school it means. It holds all 40 rows of the names check's proposal. Each school was checked by eye against the score table's spelling (`cfb-weather/data/processed/games.parquet`, 2020–25), and a test checks that every school is spelled as the table spells it. None was rejected.

| Feed name (normalized) | School |
|---|---|
| umass minutemen | Massachusetts |
| miami redhawks · miami ohio redhawks · miamiohio redhawks | Miami (OH) |
| louisiana monroe warhawks · louisianamonroe warhawks · ulmonroe warhawks | UL Monroe |
| louisianalafayette ragin cajuns | Louisiana |
| north carolina state wolfpack | NC State |
| southern california trojans | USC |
| mississippi rebels | Ole Miss |
| texas el paso miners | UTEP |
| ut san antonio roadrunners | UTSA |
| nevada las vegas rebels | UNLV |
| alabama birmingham blazers | UAB |
| southeastern louisiana lions | SE Louisiana |
| tennesseemartin skyhawks · tennessee martin skyhawks | UT Martin |
| albany great danes | UAlbany |
| citadel bulldogs | The Citadel |
| saint francis pa red flash · saint francis red flash | St. Francis (PA) |
| tarleton texans | Tarleton State |
| se missouri state redhawks | Southeast Missouri State |
| appalachian state mountaineers | App State |
| southern mississippi golden eagles | Southern Miss |
| connecticut huskies | UConn |
| houston baptist huskies | Houston Christian |
| texas amcommerce lions | East Texas A&M |
| dixie state trailblazers | Utah Tech |
| central florida knights | UCF |
| southern methodist mustangs | SMU |
| texas christian horned frogs | TCU |
| louisiana state tigers | LSU |
| brigham young cougars | BYU |
| arkansas pine bluff golden lions | Arkansas-Pine Bluff |
| san diego st aztecs | San Diego State |
| ohio st buckeyes | Ohio State |
| iowa st cyclones | Iowa State |
| utah st aggies | Utah State |

- **Name problems are logged as name problems.** A college game for which no game is found, when a name was resolved by the prefix rule, is logged as `cfb_prefix_name_no_game`, not `cfb_no_game`. The reason mixes causes: the prefix rule may have picked the wrong school, or the name is right and the score table has no such game. Read it as "no game found; a name was resolved by the prefix rule". A name that resolves to nothing stays `cfb_team_name_unknown` (`nfl_team_name_unknown` for the NFL). The report now prints, for each sport and season, the share of games matched to a final score, with a line on its first page if any season is below 95%. It also says whether the college team files were present, and it lists every name resolved only by the prefix rule or not at all (names only). A game with no score still counts for CLV, as section 2 says. It is only left out of the realized return, K2, the count item 4 needs, and the calibration table.
- **The names-only preflight is part of the engine**: `uv run python -m markets.research.price_engine.names_preflight --out <folder>`, run from `sharp-markets/`. It reads the schedules the probe saves (team names and kickoffs only), drops the 2026 and out-of-window games as it reads them, and runs the engine's own name and matching code with every score replaced by a row number. So it reads no price and prints no score. It writes the names and how each resolved (prefix and unresolved rows first), the games it can't match and why, the top-division schools no name reaches, and the games that appear under two event ids. For every row of the alias table it also writes (`aliases.csv`) and, when cfbfastR's team files are present, prints the school the team files would give for the same name, so any disagreement with the alias table is seen on Thursday. The alias table is what the engine uses. It is tested on a made-up schedule and made-up team files.

**The protocol, registered now.** On Thursday, after the probe has saved its schedules (team names and kickoffs only) and **before any F1 price is opened**, the hub runs the preflight. Any further alias comes only from its list of names, judged on names and schedules and never on a price or a result, and it is recorded in a dated note together with the list. The preflight also counts games that appear under two event ids. If they are more than 1 in 100 games, the hub decides what to do before any price is opened, and says so in the note.

**A known limit.** Until then, a game listed under two event ids can give two bets, one under each id.

*Example.* The feed lists "Miami RedHawks" at Cincinnati. Before, the prefix rule sent it to Miami (Florida), found no Miami (Florida) against Cincinnati game, and logged "no game", so the game lost its score. Now the alias table sends it to Miami (OH), and the score is found.

### Item 9. Size (defect D9). No code.

For the record: on September 29, 2026, a full-size run on a made-up cache of F1's shape (4,841 calls) took about 3 minutes and 7.6 GB on the Mac. A heavier version that also lists every FCS game took about 6 minutes and 12.3 GB. Both were before the loading repair. After the repair, the measurement was repeated in proportion on the cloud machine, taking the median of 3 runs each:

- On the builder's made-up cache of 568 calls (about an eighth of F1), the registered code took 62.4 seconds and 1.66 GB of peak memory. The repaired code took 57.5 seconds and 1.30 GB: 8% less time and 22% less memory.
- On the reviewer's made-up cache of 380 calls, with 16 repeated snapshots, the registered code took 17.6 seconds and 0.79 GB. The repaired code took 17.7 seconds and 0.70 GB: 1% more time and 12% less memory.

So time is roughly unchanged, and memory goes down because the code holds one call's rows at a time instead of fifty. (Measured before the September 30 counting fix of item 2, the time changes were −12% and +5%.) The September 29 figures are therefore an upper bound for that made-up cache. They are not a forecast for Thursday: F1's real size is known only once it is pulled.

### Known limits, stated and not repaired

- **A game under two event ids** can give two bets, one under each id, until the hub decides (item 8).
- **Home and away swapped between snapshots.** Nothing guards against the feed listing a game's teams one way at one snapshot and the other way at another. A bet's CLV would then be graded against the other side's close. And the final score goes on the game's first listing, so a swap before the entry would flip the bet's result. The report prints, for information only, how many games are listed with more than one (home, away) pair across their quotes (a swap, or a name spelled two ways). Nothing is excluded for it. Whether to exclude such games is the hub's decision. No code changed except that count.

### What this amendment does not change

- The count (38 variants, 8 deciding), the running count (271) and the bar (p < 0.000185).
- The flags and their thresholds: EV of 1%, 2% or 3% with 2% primary; 1 point at −115 or better for H2.
- The fair prices and the blend weights (0.55 / 0.30 / 0.15), the Shin de-vig, and the totals and spread conversions.
- The entry rule (the first flagged snapshot, more than 60 minutes before both kickoffs), one bet per game, market and side, and the close (the last quote within 60 minutes of kickoff).
- The CLV and return definitions, K1, K2's definition, K4, A1 and A3 to A6, and the 100-bet minimums for bets and for bets with a Pinnacle close.
- The sealed 2026 seasons, and decision 4: no money until a paper forward test has been decided.
- The weather projects and the alert jobs. The college Rule B alert's wording (defect D10) and the nightly publication (defect D11) are for the hub, outside this amendment.

---

## The one-line command

From `sharp-markets/`, after F1 is pulled ([`docs/ODDS5M_DAY_ONE.md`](ODDS5M_DAY_ONE.md), step 5):

```bash
uv run markets price-engine
```

- **Output.** It writes `reports/price_engine/report.md` and `results.csv` (one row per variant, 38 rows), plus `bets.parquet` and `dropped.csv`.
- **Before F1 exists,** it prints that there is nothing to backtest and stops.
- **`--fixture`** runs the whole pipeline on a small synthetic fixture (not data), to check it works.
- **No API calls.** It reads only what is cached, and it never touches the sealed seasons.
