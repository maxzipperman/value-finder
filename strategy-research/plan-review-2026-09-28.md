# Review of the 5M-month plan

*Strategy research · September 28, 2026 (evening) · A research review of [`odds-api-credits.md`](odds-api-credits.md), "The 5M month". No Odds API call was made. No outcome statistic was computed: every number here is an eligible-game count, a credit figure, a power calculation, a price-move standard deviation, or a literature effect size. Two independent skeptic passes re-derived every count, credit and power figure and reproduced them; where they weakened a conclusion, it says so.*

**Owner answers that shaped this review (Sep 28):** money would go to any of Kalshi, US regulated sportsbooks or Pinnacle, so the price engine is a betting hypothesis, not a measurement; a second 5M month is acceptable if October justifies it; football comes first, but MLB, soccer, NBA or NHL would be bet if an edge showed.

**Reproduce the numbers:** scripts in [`review_2026_09_28/`](review_2026_09_28/), outputs in [`output/review_2026_09_28/`](output/review_2026_09_28/). See [Appendix B](#appendix-b-what-was-counted-and-how).

---

## The verdict

The top of the plan's order is right and the middle is wrong. The pull everyone agrees is most valuable, F1, is 4% of the credits. Hourly football (F4) and the four non-football sports are 78% of the credits, and none of them can produce a result that changes a decision this season. About 2.9M of the 4.18M credits either have no written act-or-drop rule, or fund a hypothesis whose best outcome is already known from a free count.

**Recommendation.** Buy the 5M month on Oct 1, because F1 alone (162K) needs that tier. Spend under 400K on day one. Gate two more pulls on results inside the month. Leave the rest for a March 2027 month that is needed regardless: the 2026 football season cannot be completed in October, so 240K to 330K of the planned 2026 credits are unpullable before Nov 1 in any version of the plan.

---

## 1. Order: what to buy in October

### Day one, about 380K credits

Everything here has its outcomes on disk already, so analysis starts the same week.

| Pull | Credits | Backtest ready on disk? |
|---|---|---|
| Probe, plus three 30-credit checks the current probe skips: NCAAF 2020 Pinnacle, MLB and MLS totals history | ~10.7K | n/a |
| **F1**: 10 books, daily plus every close, NFL and CFB 2020–25 | 162,210 | Yes: 653 Rule HT games, 128 NFL and 237 CFB windy games (2020–25), every closing outcome |
| **F2**: NFL alternate spreads and totals at T−24h and the close. Drop the T−2h snapshot (no hypothesis) and team totals (their line, M4, was dropped after the free pre-check) | 45,600 | Yes: nflverse margins |
| **F3**: NFL props at T−24h and the close only | 136,800 | Yes: `player_week.parquet`, `kicks.parquet` |
| **NBA sample week** (Jan 5–11, 2026) at schedule A, as PLAN.md §8 requires before any full season | 7,540 | Yes: that week's Kalshi candles and trades are cached |
| **Heat**, trigger-first and close-only: compute the day-1 forecast trigger from Open-Meteo (free), then pull one featured close per qualifying MLB and soccer game, 2024–25 | ~10–15K | Needs the free weather and results joins first |

The bulk puller's `week` stage cannot produce schedule A; use `markets odds-pull --schedule A`. If N1 is left in the `week` stage it spends about 24K on a D-schedule week instead. Either is a superset the full season would reuse, but review before pulling the season.

### Gated inside the month, decided by about Oct 20

- **N1, the full 2025-26 NBA season at 5-minute resolution (478,530):** only if the sample week shows an H1 edge or an H2 lag. PLAN.md §8 step 3 and §9 decision 2 make this a hard stop, and the day-one order in `ODDS5M_DAY_ONE.md` skips it. The week's snapshots are a subset of N1 and the cache is shared, so honouring the gate costs nothing.
- **F4, hourly football:** only if F1's day-to-day reversal test shows positive CLV (section 3). F4's true incremental cost is **1,442,220**, not 1,604,430: every F1 snapshot lies on F4's hourly grid and `bulk.py` caches by the same key. F4 was a dated owner decision on Sep 28; this review asks to reverse it, for three reasons. The daily test comes first in the repo's own earlier sequencing (`odds-api-credits.md` lines 185 and 197). The history does not expire, so a March month buys the same data with the complete 2026 season. And F4 is 38% of the plan sitting in the first tier, where a billing surprise costs more than every value-1 and value-2 item combined.

### March 2027 month

The 2026 completion for every football pull (F1's remainder is about 18K; F2 and F3 about 50K; F4's about 178K, which alone exceeds the 100K plan). F4 in full if F1 earned it. N2 and H1 if the price engine worked on football and a data-use line has been written for them.

### The "credits lapse anyway, so pull everything" objection

Half right. The cash cost of an extra pull inside the month is zero. The real costs are a six-hour run on the Mac during the alert season; roughly 16 GB of raw responses to back up (an extrapolation from two live responses, unverified); the reserve exposed to a wrong billing multiplier on the first event-odds pull; and the fact that pulled data invites analysis and every analysis is a counted variant. October should start with a small pile of data and a decision rule for each piece.

---

## 2. Data nobody will study

| Pull | Credits | Why | What is lost by cutting |
|---|---|---|---|
| F4 hourly football, before F1 | 1,442,220 net | Its two variants are the hourly version of a test F1 runs first | Five months on the hour-to-hour question |
| B1 and S1, 2020–23 | 455,400 | The heat trigger (Open-Meteo previous-runs) exists only from 2024. These years serve a descriptive check the pre-registration says "decides nothing" | An observed-weather mechanism check the literature already settles |
| B1 and S1, pre-close grid for 2024–25 | ~250K | Both rules bet at the close. Trigger-first close-only gives the identical registered test for under 15K | An unregistered early-entry CLV variant. Heat is forecast accurately days out, so there is little late move to capture |
| N2 and H1, NBA and NHL daily | 334,320 | Their only data-use line is the favorite-longshot test that the #17 pre-check removed | Nothing registered. The natural month-two extension if the price engine works |
| F5 and F6, CFB alternates and props | 369,800 | Dropped once for thin coverage; nothing changed. Bovada, the book the review named for CFB props, is not in `us10` | CFB team-totals shrinkage (36,980 keeps team totals at the close if one CFB derivative check is wanted) |
| F3's T−48h and T−2h snapshots | 136,800 | "Prop moves across the snapshots" has no metric | A descriptive |
| 2026 football in October | 240K–330K | Cannot be spent; the season is a third played | Nothing |

Two housekeeping items the audit found: the 4.5M cut line plus the 531,630 floor sums to 5,031,630, so the floor stops the run before the cut line does; and STATUS.md still describes the October 20K pilot and the March month in four backlog rows. N1's arithmetic also nets 1,545 "cached" snapshots that nothing in the 5M month caches (+15,450).

---

## 3. What each result should mean

### The structural fact

A rule graded on CLV needs about **33 NFL or 45 CFB signals** to detect one point of line value, and about **130 or 177** for half a point (one-sided 95%, 80% power, using the repo's own windy-cohort move SDs of 2.285 and 2.675). A rule graded on win rate at the close needs **542 games at a true 57.7%** just to reach p < 0.05 against the −110 break-even, and **2,243 at 55%**. The repo bar of p < 0.00026 needs **1,633 and 6,751**. So "beat the close" rules are decidable at small n and "the close is wrong" rules are not, unless thousands of lines exist. The plan's weather pulls are the second kind at n of 150 to 300. [Appendix A](#appendix-a-why-clv-rules-need-fewer-games) explains why.

### Decision rules

| Hypothesis | Act if | Drop if | Games needed |
|---|---|---|---|
| **Price engine** (F1, #8) | Realized ROI at the flagged price is positive with a 95% interval above zero, positive in at least 5 of 6 seasons, and survives excluding flags where Pinnacle's market `last_update` is older than the soft book's. Grade on ROI and on CLV to the soft book's own close. CLV to Pinnacle is tautological when Pinnacle defines the flag | ROI at or below zero, or driven by one book or one season | A few hundred flags per market. Stability across books and seasons is the binding constraint, not power |
| **Day-to-day reversal** (#16, inside F1) | Fading a move of a point or more earns at least 0.25 points of CLV with the interval above zero, in both sports, in 4 of 6 seasons. Only then does F4 earn its place | Anything else | Thousands of game-days |
| **Alternates and key numbers** (F2) | Best-book alternate EV at least +2% against the recent-era margin table, in each of 2023, 2024 and 2025 | EV at or below zero after vig. The Wong teaser leg rate was 73.3% in 2022–25 against a 73.9% break-even, so expect this dead at −120 | 1,140 games times many lines |
| **Props, median vs mean** (F3, #10) | Under rate above the price's break-even with p < 0.01 in each year and each market | At or below break-even, or one market carries it | Tens of thousands of prop lines. A close-is-wrong rule that is actually decidable |
| **Kicker props in wind and cold** (F3, #21) | Mean CLV from T−24h to the prop close above zero with the interval clear, on at least 100 lines, and kicking points actually fall in trigger games | Otherwise | About 89 windy or cold outdoor NFL games in 2023–25, roughly 180 lines. A 2027 forward-test candidate at best |
| **NBA H1 and H2** (week, then N1) | Per PLAN.md: net-of-fee edge flags with fills and positive CLV to Pinnacle's close in the week; median catch-up lag of 10 minutes or more for H2 | Per PLAN.md | Train and validate as written |
| **MLB heat** (B-H1) | Registered. The free count finds **146** qualifying open-park regular-season games in 2024–25, below the 150-game floor | "No decision" is the pre-written outcome. With the market fully blind to temperature the ceiling is about 54%; clearing the bar at n = 150 needs 64% | Run it cheaply to close it out. Do not widen to retractable roofs after the fact: that adds 210 games and needs an amendment dated before any odds are joined |
| **Soccer heat** (S-H1) | Registered. About **250 to 320** qualifying matches | The published effect on goals is zero, so the ceiling is 51% to 52%. "Promising" needs 54.7% at n = 300 | Expected outcome is Rejected. Run cheaply, write it up |

### One deadline this week: the NFL Rule B horizon

NFL Rule B produced 18 forecast triggers in 2024 and 25 in 2025 before its price gates (8 and 16 at lead 1). The 40-signal decision path cannot be reached in 2026, and the interval path at about 17 signals needs mean CLV near 1.1 points, which is the full historical open-to-close move. **Amend the NFL decision horizon to two seasons pooled before Oct 8.** That is a dated amendment before any scored outcome, which the rules allow. CFB Rule B, at about 55 triggers a season, is fine as written.

### The 2026 forward-test slots

- **CFB** is full (Rule B, Rule HT).
- **NFL** has one slot left. Give it to the **price engine** as a paper CLV log, pre-registered by about Oct 20 once F1 fixes the threshold, fed by an hourly 10-book live poll costing 2K to 3K credits a month. It is the best-supported idea in the literature, bettable at the venues named, and decidable on 150 flags. Caveat: soft books limit winners, so the real-money ceiling is small even if it works.
- **NBA** gets **Kalshi H1 static edge** on 2026-27, pre-registered after the sample week sets the threshold. Keep H2 lag descriptive; H4a found none in NFL.
- Nothing else deserves a 2026 slot. MLB and soccer 2026 are sealed and nearly over. None of the new candidates in section 7 clears the bar for one.

---

## 4. Free before Oct 1

1. **Write act-or-drop rules for F1, F2 and F3 before the data lands.** Today only the heat file has one, and it covers 850K of credits while 2.9M have none.
2. **Amend the NFL Rule B horizon** as above.
3. **Run the real day-1 forecast trigger counts** for MLB and soccer 2024–25 from Open-Meteo's previous-runs archive, to confirm the 146 and 250-to-320 figures (which use observed ERA5) before any heat odds are bought. `markets weather` reads schedules only from the probe's `/events` sweep; a small change lets it take the free MLB Stats API schedule that `gamevenues.py` already fetches.
4. **Pull the free Kalshi data**: the 2025 NFL trades tape and full-lifetime candles for every `KXNFLTOTAL` strike (about 3K to 17K public GETs), and the rest of NBA 2025-26. No credits. This unlocks the maker-versus-taker paper simulation (#9) and deep-strike tests later. The cache today holds NFL candles for 285 games but no NFL trades, and NBA candles and trades for the sample week only.
5. **Audit the CFB forecast replay**: `fc_trigger` equals `fc_signal` in all 110 rows, so the −115 and EV gates either never bind or are not applied there.
6. **Hygiene**: fix the cut-line and reserve arithmetic; update STATUS.md; decide which `.env` gets the paid key (`LIVE_USES.md` and `ODDS5M_DAY_ONE.md` disagree); switch the alert book list to `us10` so the free 2026 archive continues F1 exactly (two of ten books differ today, and only totals are logged).

---

## 5. 100K or 5M this month

F1 alone is 162K, so the 100K plan ($59) cannot buy the design above. What 100K would buy: every NFL and CFB **close** for 2020–25 across 10 books (2,819 kickoff slots × 30 = 84,570), plus the NBA sample week (7,540), with about 8K left for live uses. That re-grades Rule HT and Rule B's history at Pinnacle's close, measures line shopping, and tests a close-priced price engine (soft close versus Pinnacle close, graded on ROI). It does **not** buy any pre-close snapshot, so no day-to-day reversal test, no "beat the close" version of the price engine, no alternates and no props.

**On n.** Credits do not buy more games; the history has a fixed number of games. Credits buy more snapshots per game (time resolution) and more markets per game. Props are the exception: F3's 137K multiplies the number of lines by tens of thousands, which is why #10 is the most decidable win-rate test in the plan. For the price engine, snapshots are chances to catch a stale price, so flags scale with snapshots: daily gives seven chances per game against one at the close.

**The $60 difference** between 100K and 5M buys F1's daily grid, F2, F3 and the option on N1 and F4. If a 2026 price-engine forward test matters, 5M in October is right, because the NFL slot's pre-registration deadline depends on F1 arriving in October. If waiting until 2027 is acceptable, 100K in October (closes plus the NBA week) and 5M in March costs $178 against $238 for two 5M months, and answers the narrower question first.

---

## 6. What a careful researcher would change

- **Match the design to the sample.** Anything with fewer than 500 expected signals should be a CLV rule that enters before the close. Win-rate rules belong where thousands of lines exist (props) or on multi-season horizons with the power stated up front. Rule HT and both heat rules are win-rate rules at 100 to 300 games, so their most likely outcome was written the day they were registered.
- **Attach a power statement to every pre-registration.** "At n signals we have X% power to see Y" would have flagged the heat rules and the NFL Rule B horizon before any money moved.
- **Keep the multiple-testing discipline but count better.** A single Bonferroni bar over 191 heterogeneous, mostly nested variants is unclearable by any sports edge at achievable n. The skeptic pass was right that loosening to p < 0.05 would be worse: the sealed 2026 holdouts have power of 0.14 to 0.27 for MLB heat, so they cannot filter false positives. The fix is pre-specified families with their own bars, and the sealed holdout plus forward CLV as the confirmation stage.
- **Write the "who is wrong" sentence.** Every close-priced rule should state in one sentence why Pinnacle's close would be wrong. For MLB heat there is no good sentence; temperature is in every totals model.
- **Expect decay.** `nfl-weather/output/betting.log` shows wind 15+ at 57.8% over 435 games in 1999–2013 and 56.1% over 257 in 2014–2025, with the 20+ mph bucket at 52.9% over 52. Rule B may be a shrinking edge, and the forward test should be read against that prior.
- **Log reversals.** The plan reversed its own review in about ten places between Sep 27 and Sep 28 ([Appendix C](#appendix-c-where-the-plan-contradicts-its-own-gates)). Some were owner decisions and fine, but none say why. A dated decision log would have caught the F1-inside-F4 double count and the N1 gate.

---

## 7. Other hypotheses, including heat in NCAA football

A literature pass produced ten candidates; the skeptics cut the top one down. Each is a counted variant under the one-threshold rule. None has been run.

| Idea | Ceiling if unpriced | Sample on disk | Status |
|---|---|---|---|
| Cold-climate or dome visitor in a hot game (≥ 85 °F) → home ATS | ~54% at the rule's own 15 °F gap (the first estimate of 57% used a 27 °F gap) | 181 NFL away rows, 209 CFB games | Peer-reviewed outcome effect (Roberts et al. 2026, *Temperature*); the spread question is open |
| CFB rain → home ATS | 54–59%, but the +3.7-point source is a class project without home-field controls | 653 CFB games 2016–25 | Weakly supported |
| CFB neutral-site or bowl → under | ~55% from the repo's own regression residual (−2.68, se 1.23) | 409 games; bowls only from 2023 | Post hoc; flips sign by era |
| Kalshi maker vs taker, paper simulation | Structural: +2–5% per contract before adverse selection (Bürgi, Deng & Whelan 2026) | Needs the free NFL trades pull | A microstructure fact, not a mispricing |
| CFB early-season heat ≥ 90 °F | ~52% at the repo's own +0.95-point residual; 55% only if the ≥ 90 °F effect is 2 points | 291 games since 2016, 170 FBS-vs-FBS in weeks 0–4 | Sign contested: the CFB residual says over, Borghesi (2008) says heat lowered NFL scoring |
| NFL heat | Untestable | 20 outdoor games at 90 °F+ since 2016; the 80 °F+ residual flipped sign between eras | Skip |
| Humidity or dew point → over | 53–56% (Paul 2017; magnitude unverified, paywalled) | 242 NFL, 796 CFB at dew point ≥ 70 °F | Mechanism contested |

**NCAA heat specifically.** It is testable free and it is the one weather variable not yet run, but the ceiling is low, the sign is ambiguous, and no CFB slot opens before 2027. If run, pre-register it two-sided as a descriptive question about whether the close mis-sets hot games, count one variant, and treat it as 2027 material.

**Broader advice.** Wait until F1 lands. F1 gives Pinnacle closes for 2020–25, which makes every one of these gradeable against a sharp number instead of a consensus, and the slot calendar means nothing found before Oct 20 can be acted on this year. Then pre-register a small 2027 family over the winter: two or three rules, one threshold each.

---

## Appendix A: why CLV rules need fewer games

There are two ways to grade a bet. Did the line move toward you after you bet (closing-line value)? Or did the bet win?

The difference is noise. In the NFL the final score lands about **13.5 points** either side of the closing total; that is the standard deviation of the outcome. The line itself moves about **2.3 points** either side of zero between an early bet and the close in windy games. A true one-point edge is therefore about 0.07 standard deviations of *outcome* but about 0.43 standard deviations of *line move*. The number of games needed to see an effect scales with (noise ÷ effect)², so the ratio is roughly (13.5 ÷ 2.3)² ≈ 34. One point of CLV shows up in a few dozen games; the same edge expressed as wins takes over a thousand.

The win-rate arithmetic: at −110 a bet breaks even at 52.38%. A rule that truly wins 57.7% is 5.3 points better. Each game is a coin flip with standard deviation 0.5, so the standard error of a win rate over n games is 0.5 ÷ √n. To make a 5.3-point excess stand 1.645 standard errors clear (p < 0.05) with 80% power takes n ≈ 542. At 55% the excess halves and n quadruples to 2,243. Reaching p < 0.00026 (z = 3.47) needs about three times more again: 1,633 and 6,751.

Why a "beat the close" rule can use CLV at all: you bet early, and the close is a second, sharper opinion about the same game formed after you acted. If the close moves toward your side on average, the market agreed with you, independently of how the game's dice landed. Because the close is the best available predictor of outcomes, consistent CLV is consistent edge. A "the close is wrong" rule bets *at* the close, so no later, sharper number exists to compare against; CLV is zero by construction and only outcomes remain.

Consequences. The heat rules at Pinnacle's close with 146 to 320 games have a standard error of 3 to 4 points on their win rate; a 2- to 3-point true edge is invisible. Props at the close have tens of thousands of lines, so the standard error falls below half a point and win rate works. And the price engine's CLV is only meaningful against a close that did not define the flag, which is why section 3 grades it on realized ROI.

---

## Appendix B: what was counted, and how

Scripts in [`review_2026_09_28/`](review_2026_09_28/); outputs in [`output/review_2026_09_28/`](output/review_2026_09_28/). Run each from the repo root with the venv named in its docstring. The heat scripts cache every free API response under `strategy-research/data/heat/` (gitignored, about 100 MB) so a rerun makes no network calls.

| Script | What it produces | Key results |
|---|---|---|
| `power.py` (any venv with scipy) | The win-rate power table and the CLV constant | n = 542 / 1,099 / 1,633 at 57.7% for α = 0.05 / 0.0035 / 0.00026; 2,243 / 4,545 / 6,751 at 55%; CLV constant 6.1826 |
| `nfl_counts.py` (`nfl-weather/.venv`) | Eligible-game counts 2016–25 by season, exactly on the rule definitions in `board.py` and `features.py`; SBR move SDs | 210 windy outdoor games (128 in 2020–25); 43 forecast triggers (2024: 18, 2025: 25); 20 at ≥ 90 °F; total move sd 1.868 all games, 2.285 windy cohort (mean +0.985, n = 371) |
| `cfb_counts.py` (`cfb-weather/.venv`) | The same for CFB, plus the Rule HT population exactly as `screen.py` builds it | 470 windy games; 291 at ≥ 90 °F; Rule HT 653 eligible (398 in 2020–25), 2026 threshold 62.62; `pin_total` exists 2006–19 only; move sd 2.407 all, 2.675 windy (mean +1.495) |
| `trims.py` (`nfl-weather/.venv`) | Reproduces `odds_5m.plan()` and prices every trim; verifies F1 ⊂ F4 | Plan 4,175,930; F4 net 1,442,220; lean 482,050; 2026 pullable by Oct 4: 114,590 of 443,620 |
| `heat/mlb_heat_count.py` (`uv run` in sharp-markets) | MLB 2024–25 regular-season games by park and first-pitch temperature, MLB Stats API + ERA5 | 57 + 89 = 146 open-park games at ≥ 90 °F; 210 at the seven retractable parks; sigma of total runs 4.31 / 4.59 (`mlb_sigma.py`) |
| `heat/soccer_heat_count.py`, `tournament_heat.py`, `soccer_summary.py` | Hot venue-days and expected qualifying matches, 19:00-local heat-index proxy | ~225 league matches (MLS 72, J1 81, K League 48, Liga MX 20, Brasileirão 4) plus ~47 tournament matches |
| `heat/ceiling.py`, `heat/credits.py` | Ceiling win rates Φ(δ/σ) and the close-only credit costs | MLB 54% market-blind, 52% half-adjusted; soccer 51–52%; close-only designs under 15K credits in total |

**Verified by the skeptic passes:** every count above; the power constants; the plan arithmetic; the F1-inside-F4 overlap (by reading `bulk.py`'s cache key); the DuckDB and raw-cache inventory (NBA sample week only in DuckDB; 3,128 NFL candle files, 1,505,366 candles, no NFL trades, no `_schedules` directory).

**Unverified, stated as such:** literature effect sizes (Callahan et al. 2023, 1.96% HR per °C; Nathan 2023; Roberts et al. 2026; Schwarz et al. 2025; Nassis et al. 2015) were read from abstracts and PDFs but not independently re-derived; runs per home run assumed 1.5; soccer league membership and tournament venue allocations from memory; the 19:00-local kickoff proxy overstates for MLS and understates for Brazilian Saturday matches; the 2025 soccer windows are clipped at Sep 22 for the ERA5 lag; ERA5 runs slightly cool against ballpark sensors, so the 146 is if anything low; the trigger-first close-only credit figures (2,880 and 3,720) apply an all-games slot ratio to scattered games and are probably 35–45% low (about 4,400 and 6,750 is the right order); the 16 GB disk estimate; whether Pinnacle has history for NCAAF, MLB or the soccer leagues in the Odds API; whether one account can hold a free and a paid key.

**Skeptic corrections applied here:** the heat-acclimation ceiling is 54%, not 57% (the first estimate multiplied a per-°C slope by 15 °C); the "corrected spendable" plan total double-subtracted F1's 2026 share and is not used; power conventions differ between sources (this note uses 80% power throughout).

---

## Appendix C: where the plan contradicts its own gates

Line numbers are for `odds-api-credits.md` unless another file is named.

| # | Earlier gate or correction | What the 5M plan does | Credits |
|---|---|---|---|
| C1 | PLAN.md §8, §9 and line 186: no full-season NBA pull before the sample week is reviewed | N1 in the plan with no review stop; the sample week is gone | 478,530 |
| C2 | H4a found no Kalshi lag; N1 "waits on B12" | N1's primary hypothesis is still lag | (same) |
| C3 | Line 349: NFL props cut from 4 snapshots to 1, "the extra snapshots have no hypothesis" | F3 back at 4 snapshots | 273,600 vs 68,400 |
| C4 | Line 348: CFB props and alternates dropped for thin coverage | F5 and F6 back; Bovada not in the book list | 369,800 |
| C5 | Lines 185, 197, 346: hourly deferred to a named question after daily shows reversal | F4 hourly, both sports, before daily exists; double-counts F1 | 1,604,430 (1,442,220 net) |
| C6 | HEAT_HYPOTHESES.md: "No decision" under 150 qualifying games | No count existed; B1 and S1 pulled before the count step | 850,440 |
| C7 | Line 133: the big month in March, for three stated reasons | Oct 1; all three reasons reversed; 2026 incomplete | 240K–330K unspendable |
| C9 | Line 159: nothing without a data-use line gets pulled; line 198: the longshot test "comes off the data-use plan" | N2 and H1's only line is that removed test | 334,320 |
| C10 | Line 184: team totals dropped after the pre-check | `team_totals` inside F2 and F5 | 108,160 |
| C11 | Cut line 4.5M and floor 531,630 | Sum exceeds 5M by 31,630 | — |
| C12 | N1 nets "cached" snapshots | Nothing in the month caches them | +15,450 |
| C13 | CLAUDE.md: STATUS.md changes in the same PR | STATUS still says 20K pilot and March month | — |

C5 and C7 are dated owner decisions in STATUS.md, so they are recorded reversals rather than silent ones; the doc never says what they reverse or why. The rest are internal inconsistencies.
