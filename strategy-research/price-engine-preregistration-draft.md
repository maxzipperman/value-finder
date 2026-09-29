# Price engine: pre-registration draft (issues [#8](https://github.com/maxzipperman/value-finder/issues/8) and [#53](https://github.com/maxzipperman/value-finder/issues/53))

**Status: DRAFT, written September 29, 2026, before any F1 data exists, and revised the same day after an independent review.** Nobody has seen a single F1 price. The owner and the hub register it (copy it into a registered file with a date, amend anything first) before `markets price-engine` first runs on F1. Until then nothing here is binding.

The code that runs it is already written and tested: [`sharp-markets/src/markets/research/price_engine/`](../sharp-markets/src/markets/research/price_engine/). Every threshold below is a constant in `engine.py` or `model.py` (the blend weights included), and the tests check the variant count and that this file states the same count and bar as the code. Changing any of them after F1 lands is an amendment. It is not an edit.

### Revised after the independent review (September 29, 2026)

No headline number changed: still 38 variants, a running count of 238 and a bar of p < 0.00021 (if open PR #55 merges first, 270 and 0.000185; see section 8). Still no F1 data, so there are no results to change. What did change:

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
- **Count.** 38 variants, which takes the running count from 200 to **238**. The bar becomes **p < 0.05 / 238 = 0.00021**.
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
| Seasons | 2020–2025, regular season and postseason. **2026 is sealed**: `bulk.load_rows` leaves it out, the backtest never asks for it, and it never loads 2026 scores (a test checks all three). |
| Sharp books (the fair price) | Pinnacle; LowVig and BetOnline for the blend. |
| Retail books (the flags) | DraftKings, FanDuel, BetMGM, Caesars (`williamhill_us`), Fanatics, BetRivers, ESPN BET: F1's ten books minus the three sharp ones. LowVig and BetOnline are never treated as retail. |
| Window | Snapshots from 7 days before kickoff up to kickoff. Featured snapshots also list games further out; F1 wasn't built to cover them, so those quotes are dropped and counted. |
| Final scores | The repo's processed game tables (nflverse and cfbfastR), 2020–25 only. A game with no matched score still counts for CLV and is left out of profit and loss, with its reason logged. |

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
| H2 | A retail total **at least 1.0 point** on the good side of Pinnacle's total at the same snapshot, at **−115 or better** (decimal 1.87 or more). | Totals only, NFL and CFB. |

**H2's weakest flags are negative EV at Pinnacle's own price.** Take Pinnacle at 44.5, 1.95 / 1.95 (a fair 50%), and a retail under at 45.5 for −115. Under the registered conversion the under at 45.5 wins 52.4% of decided NFL bets and 52.2% of CFB bets. At −115 that is an EV of **−1.9% (NFL) and −2.3% (CFB)**; at −110 it is about even (+0.1% and −0.3%). A bigger gap or a better price turns it positive. So if Pinnacle is right, H2's minimum flags should show *negative* CLV against Pinnacle's close, about −1 cent, and H2 passes only if the average flag had value or the lagging books really do trail Pinnacle. Whether H2 should also require a non-negative EV at Pinnacle's price is owner decision 7.

**No snapshot at or after kickoff is ever an entry.** A snapshot is dropped if it is at or after the kickoff it lists itself, or the kickoff listed in the game's latest snapshot, in-play snapshots included (kickoffs move). Tests check this, including a kickoff that moved earlier and one that moved later.

## 5. Entries: one bet per game, market and side

For each variant, the bet on a game, market and side is the **first snapshot at which that side is flagged**, at the flagged retail book with the best EV. For H2 it goes to the biggest gap, then the best price. The price taken is that book's posted price at that snapshot. Later flags on the same side of the same game are not extra bets.

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
| Realized result at the price taken | Flat one-unit bets: win rate, ROI (pushes left out) and a 95% interval. |
| The close | A book's quote in its last snapshot before kickoff, only if that snapshot is within 60 minutes of kickoff. F1's close is 5 to 10 minutes before. A bet whose book, or Pinnacle, has no close is left out of that CLV column and counted: the report prints how many bets each cell graded (`clv_pin_n`) next to its bet count. |

Standard errors are clustered by game throughout.

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
- K2. Realized ROI's 95% interval lies entirely below zero.
- K3. With the book that has the most bets removed, mean CLV is at or below zero, or no bets are left. One book carries it.
- K4. With the season that has the highest mean CLV removed, mean CLV is at or below zero, or no bets are left. One season carries it.

**Act: this justifies a pre-registered paper forward test on the 2026 season** only if nothing kills the cell and all of these hold:

- A1. Mean CLV against Pinnacle's close is above zero with **one-sided p < 0.05 / 238 = 0.00021**.
- A2. At least 3 seasons have 20 or more bets, and CLV is above zero in all of those seasons but at most one.
- A3. CLV is above zero on the bets where Pinnacle's market was updated at least as recently as the retail book's. Where Pinnacle's quote is older than the book's, the gap may be Pinnacle being stale; either timestamp missing counts as stale.
- A4. CLV is above zero on the bets with EV below 10%. The fattest prices are the ones a book is likeliest to void as obvious errors.
- A5. H1 only: the blend version's 2% cell also has CLV above zero.
- A6. H2 only: mean CLV against the lagging book's **own** close is above zero. Issue #53 asks that H2 be graded on exactly this: did the book that held the old number move to where Pinnacle already was? For H1 it is reported and decides nothing (owner decision 6).

**Inconclusive: everything else.** Typically CLV is positive but not below the bar. No forward test comes from this backtest. The idea can still be logged on paper descriptively.

**What an "act" does not mean.** It means the price engine's premise held up at F1's resolution (a daily snapshot plus other games' closes) in 2020–25, and nothing more. The forward test's own registration fixes its metric and horizon before its first eligible game. The suggested version is mean CLV against Pinnacle's close with its 95% interval above zero, after at least 150 bets. That is a separate pre-registration.

**What CLV against Pinnacle's close tests, and where it stops.** The flag uses Pinnacle's price at an earlier snapshot, up to seven days out, and the close is a later, sharper price.

- **What it catches.** If a gap exists because Pinnacle was slow (the retail book moved first on news), Pinnacle's close moves to the retail book's side and the CLV disappears or turns negative. That is the main way "beat the sharp line" fails in practice. For totals and, since the revision, for spreads, those bets are in the main number: a close at another number is converted, not dropped (section 6).
- **Why a pass is close to automatic if Pinnacle is right.** If Pinnacle's price is right and moves only on new information, a flag at EV e and decimal price d is expected to show CLV of e / d against Pinnacle's close. That is **1.03 cents** for a 2% flag at 1.95, and 1.28 cents at 2.5%. With a spread of about 6 cents per bet, a cell whose flags average 2.5% EV clears the bar (p < 0.00021) with 80% power at about **420 bets**; at exactly 2%, about 650. So an H1 cell with several hundred bets passes A1 almost automatically if Pinnacle is efficient. The report prints this expected figure (`clv_pin_expected`) next to each cell's CLV. A cell near it means the flags kept their value to the close; well below it means Pinnacle moved toward the retail prices.
- **What it cannot catch.** Pinnacle's close itself being wrong. A pass says Pinnacle was not the slow side and the flagged prices beat the sharpest price available; it does not show that Pinnacle's close is right. The plan review raised exactly this ([`plan-review-2026-09-28.md`](plan-review-2026-09-28.md), section 3), and the data-use plan ([`odds-api-credits.md`](odds-api-credits.md), row F1) called CLV to Pinnacle "tautological when Pinnacle defines the flag" and asked for ROI and CLV to the book's own close instead. This draft keeps Pinnacle's close as the main test for the reasons in section 9, requires the book's own close for H2 (A6), and leaves the choice for H1 to the owner (decision 6). Only results can test the close itself, and section 9 shows they need far more bets than F1 has. So the report adds a descriptive check of how well Pinnacle's no-vig close matched results on every game it priced, and a pass leads to paper, not money.

## 8. Variants and the multiple-testing bar

| Family | Count |
|---|---|
| H1: 2 sports × 3 markets × 2 fair versions × 3 thresholds | 36 |
| H2: 2 sports | 2 |
| **This draft** | **38** |
| Running count before it | 200 |
| **Running count after it** | **238, so the bar is p < 0.05 / 238 = 0.00021** |

- **Not counted: the descriptive tables.** These are the calibration of Pinnacle's close, how often each book sits a point or more off Pinnacle, and the per-book splits. They can't select a rule, so they add no false-positive risk.
- **Counted in full, conservatively.** The data-use plan already counted 9 price-engine variants (3 thresholds × 3 markets) in the 200. If the hub nets those out, the count is 229 and the bar is 0.00022. The difference doesn't matter; see owner decisions.
- **The revision adds none.** The spread margin table only grades closes, and A6 is a decision condition on the same 2 H2 cells, so the count stays 38.
- **The count before this draft is set at registration.** Open PR #55 (the landing-mass table) adds 32 variants to the same 200. If it merges first, the count before this draft is 232, the count after it **270**, and the bar **0.05 / 270 = 0.000185**. The hub sets `PRIOR_COUNT` in `engine.py` and this table to STATUS.md's running count on the day it registers the draft. A test fails if the two disagree.

## 9. How many bets it takes, and why the decision is on CLV

This is back-of-envelope arithmetic from the repo's own numbers. It is not from F1.

- **CLV.** The plan review measured line moves from an early bet to the close at about 2.3 points (NFL) and 2.7 points (CFB) either side. Near the middle of a total, one point is worth about 2.5 cents of probability. So a bet's CLV varies by roughly ±6 cents.
  - To detect a true average CLV of **1 cent** at the bar (one-sided z = 3.53, 80% power) takes about **690 bets**.
  - **2 cents** takes about **170 bets**.
  - **0.5 cents** takes about **2,700 bets**.
- **Profit.** One bet's result varies by about ±1 unit.
  - A true 2% edge needs about **15,000 bets** to show at the ordinary 5% level.
  - At the bar it needs about **48,000**.
  - With 1,000 bets, the ROI's 95% interval is about ±6 points wide. A real +2% edge would read as something like "+2% ± 6%".
- **What this means for the plan's earlier rule.** The data-use plan ([`odds-api-credits.md`](odds-api-credits.md#data-use-plan), row F1) asked for "realized ROI positive with a 95% interval above zero". At 1,000 bets, that rule rejects a true 2% edge about 9 times in 10 and a true 3% edge about 8 times in 10. That is why this draft decides on CLV and keeps ROI as a veto (K2). The change is the owner's to accept (decision 1).
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

## 12. Decisions for the owner (with recommendations)

1. **Decide on CLV, not ROI.** Replace the data-use plan's "ROI with a 95% interval above zero" with the rules in section 7, keeping ROI as a veto. *Recommend: yes.* The ROI rule would reject a true 2% edge about 9 times in 10 (section 9).
2. **Variant count: 238 (all 38 added) or 229 (net of the 9 already counted).** *Recommend 238.* It is the conservative choice, and the bars (0.00021 against 0.00022) barely differ.
3. **A CFB forward test in 2026.** The plan review says both CFB 2026 slots are taken (Rule B and Rule HT). If a CFB cell reaches "act", either run the CFB price-engine paper log as a third registered CFB test this season, or log it descriptively in 2026 and register it for 2027. *Recommend the 2026 test only for a CFB totals cell that reaches "act".* The live log costs no credits and no money, and a CLV test is decidable in a few hundred bets. Otherwise log descriptively.
4. **Money this season.** *Recommend none from this rule.* A backtest pass earns a paper test, and under the repo's own rules real money waits for that test's decision. The earliest honest path to a real CFB bet is a pass on Oct 1–2, a paper test from mid-October, and a decision when its bet count is reached, which is likely late 2026 at the earliest and more likely 2027.
5. **Books in the live log that F1 never saw** (Bovada, Hard Rock Bet). *Recommend logging them but leaving them out of any decision.* Bovada is also offshore, which is not one of the venues you named (US regulated books, Kalshi, Pinnacle).
6. **Grade on Pinnacle's close, or on the book's own close (added after the review).** The data-use plan asked for CLV to the soft book's own close, because CLV to Pinnacle is "tautological when Pinnacle defines the flag". This draft switches the main test to Pinnacle's close. The cost of that switch in numbers: if Pinnacle is right, a 2% flag is expected to show about 1.03 cents of CLV against Pinnacle's close (1.28 cents at 2.5%), and a cell of about 420 to 650 bets would pass A1 almost automatically (section 7). Three choices:
   - **(a) As drafted:** Pinnacle's close decides H1; the book's own close is reported for H1 and required for H2 (A6).
   - **(b) The plan's version:** also require CLV to the book's own close above zero for H1. That tests a different thing, whether the retail book later corrected its price. A book that shades one kind of price on purpose and never corrects would fail it even if the bets were good.
   - **(c) Test against what an efficient Pinnacle implies:** pass only if CLV is not clearly below `clv_pin_expected`, meaning the flags kept their value to the close. With a few hundred bets this has little power.

   *Recommend (a).* It catches the main failure, Pinnacle being the slow side, and (b) would reject a book that is consistently soft, which is the most usable kind of book. But a pass under (a) means less than it sounds: it says Pinnacle wasn't the slow side, not that Pinnacle's close is right.
7. **H2's weakest flags (added after the review).** At exactly 1 point and −115, an H2 bet is about 2% negative EV at Pinnacle's own price (section 4). Should H2 also require EV of zero or more at Pinnacle's price? *Recommend no:* keep the trigger issue #53 wrote. Adding the EV floor makes H2 mostly a copy of the H1 totals cells, and the cell's CLV already shows whether the average flag had value. Say so if you'd rather have the floor; it has to be decided before F1 lands.
8. **The spread margin table (added after the review).** Accept the table in section 6 (every game before 2020, the 1,000 nearest-spread entries) for grading spread closes at another number? The alternative is to make CLV in points the main measure for the two spread cells. *Recommend the table.* Points ignore the price: a spread flag is a better price at Pinnacle's own number, and if Pinnacle is right its line doesn't move on average, so points CLV would be about zero even for a real edge. The report prints points next to cents either way.

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
1. The hub registers this draft, with the owner's answers to decisions 1–8 and `PRIOR_COUNT` set to that day's running count (section 8).
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

## The one-line command

From `sharp-markets/`, after F1 is pulled ([`docs/ODDS5M_DAY_ONE.md`](../sharp-markets/docs/ODDS5M_DAY_ONE.md), step 5):

```bash
uv run markets price-engine
```

- **Output.** It writes `reports/price_engine/report.md` and `results.csv` (one row per variant, 38 rows), plus `bets.parquet` and `dropped.csv`.
- **Before F1 exists,** it prints that there is nothing to backtest and stops.
- **`--fixture`** runs the whole pipeline on a small synthetic fixture (not data), to check it works.
- **No API calls.** It reads only what is cached, and it never touches the sealed seasons.
