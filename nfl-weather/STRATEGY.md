# NFL weather betting playbook (v2)

The research is real; the edge is not yet proven. Wind reliably lowers NFL
passing, and closing totals historically under-adjusted for it, but every
profitable backtest used the weather observed at kickoff. The forecast-based
record so far is 12–12. So this is a small, pre-registered forward test graded on
closing-line value (CLV) at the price you actually got, not a system to scale.
Version 2 follows an independent audit; see `PREREGISTRATION.md` amendment 2.

## Rule B: early wind under (forward test)

| | |
|---|---|
| **Trigger** | Outdoor stadium, kickoff wind forecast **≥ 15 mph** (game-book scale), **1–3 days before kickoff**. *Amendment 5:* days are calendar days (the kickoff's Eastern date minus the run's date), so a signal can be logged about 11 to 82 hours out. |
| **Price gate** | A posted total, an under price of **−115 or better**, and **positive expected value at that line and price**. The alert computes EV from what actually happened after comparable windy lines (1999–2023), so a worse number or price can fail even when the wind trigger fires. *Amendment 5:* the pricing model is registered in full in `PREREGISTRATION.md`. At the rule's own number the value only reaches zero at about −136, so inside the −115 cap this gate can't reject a bet: in practice the gates are the wind, the window and the price. **Pinnacle's price is the registered test.** When Pinnacle has no quote, a signal at the backup consensus line is labelled *secondary price*, reported separately, and left out of the decision. |
| **Alert** | `RULE B WIND UNDER 42.5 at −110: …`. A wind trigger without a usable price arrives as `WATCH … no bet (no price / price too high / negative EV)`. *Amendment 5:* the alert also names the best number any logged book offers, with its value (`Best number: under 43.5 at −108 (FanDuel), expected value +12.1%`). A point of total is worth about 2.4 points of win probability. |
| **Action** | Take that number or better, right away. Rain or snow in the forecast does not change the stake. |
| **Stake** | Paper-trade it until 20 settled signals show positive average CLV. If you bet before then, flat 0.5% of bankroll per signal, never more. |
| **Line lag** | Same gates, plus the wind forecast rose 5+ mph since the last check while a posted total barely moved (`RULE B LINE LAG`). |
| **Evidence for** | 57.2% under vs the close in 682 observed-wind games since 1999 (+9% at −110); 59.7% vs the opener 2007–21; totals fell about 1 point by kickoff; walk-forward bets beat the close 63% of the time. |
| **Evidence against** | 18–18 on observed wind in 2024–26; 12–12 on 1-day forecasts; 108 variants were examined, and the long result (p ≈ 0.007) doesn't clear a strict multiple-testing bar (p < 0.0005). |
| **Decision** | Scored from Week 5 (Oct 8, 2026) by `scripts/score_forward.py` at entry line and price. Keep only if average CLV > 0 with a 95% interval above zero, decided once after the 2027 season on 2026 Weeks 5+ and 2027 pooled, or at 40 signals if sooner (amendment 4; the 2026 result after Week 18 is an interim read only). Amendment 3 adds a secondary CLV against Pinnacle's close captured 2–20 minutes before kickoff. |

## Watch: log, don't bet

| Signal | Why it's watch-only |
|---|---|
| **Model lean** (P(under) ≥ 55%) | Pre-registered, but its probability is relative to the *closing* total and ignores the offered price; it also leans on a rain term fit to observed rain. |
| **Forecast rain** | The historical 62% rain edge comes mostly from rain nobody forecast. Forecast rain went 8–9 against a close that had already priced it. |
| **Cold visitor**: dome or warm-climate team in a ≤ 32°F game | Home covered 58.6% of 113; cold-climate visitors 47%. Right shape, small sample, never forward-tested. |
| **Props** | Passing yards fall ~11% at 20+ mph and ~7% in rain; a 50-yard FG drops from 78% to 67% in freezing wind. No historical prop prices, so untested. |

## Avoid

* Snow unders (45%), cold-only totals (freezing overs 59% before 2014, 50% since), 10–14 mph wind at the close (54%), indoor games.
* Laying more than −115 on any weather under.

## Execution

* Shop the number: half a point of total is worth roughly 1–2.5 points of win probability; −105 instead of −110 drops break-even from 52.4% to 51.2%.
* On Kalshi, match the exact strike and settlement (an under 44 and an under 43.5 differ when the score is 44). A 50¢ contract plus the taker fee breaks even at 51.75%.
* Log the price you actually got. The ledger records the posted price at signal time; your fill is what counts.
* Nothing in this project places bets.
