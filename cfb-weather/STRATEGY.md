# College football weather playbook (v2: Rule B + Rule HT)

Same rule and gates as the NFL playbook v2 (`../nfl-weather/STRATEGY.md`), on its
own evidence and its own forward test.

## Rule B: early wind under (forward test)

| | |
|---|---|
| **Trigger** | FBS game at an outdoor venue with known coordinates and kickoff time; kickoff wind forecast **≥ 15 mph** on the station scale (frozen calibration: station = 1.01 + 0.92 × model wind, fit 2016–23), **1–3 days out**. |
| **Price gate** | Posted total, under at **−115 or better**, positive expected value at that line and price (from the 2006–23 cohort of windy outdoor games). |
| **Stake** | Paper until 20 settled signals show positive average CLV; if betting, flat 0.5% of bankroll. No size-ups. |
| **Evidence for** | 56.6% under vs the close in 990 observed-wind games 2006–25 (+8% at −110); 57.4% in 2016–25 and 56.4% in 2021–25; 60.9% vs the opener (614 games) with totals falling 1.4 points by kickoff. The closing total moves about 0.9 points for wind that costs 3.7 points of scoring (15–19 mph). |
| **Evidence against** | All of it uses observed airport-station weather, not forecasts; no CFB forecast replay exists yet. Station wind is not stadium wind. Rain unders faded to 51% in 2021–25. |
| **Decision** | Scored from Oct 1, 2026 by `scripts/score_forward.py` at entry line and price, CLV against the last quote before kickoff. Keep only if average CLV > 0 with a 95% interval above zero after 40 signals or the end of the regular season, whichever is later. |

## Rule HT: high-total under (forward test, amendment 1)

From [issue #4](https://github.com/maxzipperman/value-finder/issues/4) and strategy-research idea 2. It doesn't use weather.

| | |
|---|---|
| **Trigger** | FBS game on the board, kicking off from 2026 Week 6 (first kickoff 2026-10-07 00:00 UTC) through the 2027 national title game. The posted total is **at least the prior season's mean closing total + 10**. |
| **Threshold** | **2026: 62.6** (the 2025 mean of 52.62 over 955 games, + 10). **2027:** the 2026 mean + 10, from the same data and filters, known before 2027 Week 0 (`board.ht_threshold`). The mean uses cfbfastR consensus closing totals for games with a result and a nonzero closing spread, the set `strategy-research/screen.py` used. |
| **Entry** | The game's **last logged quote before kickoff**, which is the latest number available, at that total and under price. The under must be **−115 or better**. The alert fires on the last scheduled run before kickoff. A game can also be a Rule B signal; the two rules are graded separately. |
| **Price source** | The Odds API: Pinnacle, else DraftKings. With no key and no ESPN price, a game can't signal. |
| **Stake** | Paper for both seasons. |
| **Evidence for** | **373–273 (57.7%) in 2016–25**, above 50% in 9 of 10 seasons (screen). The calibration slope of result on closing total fell from 1.01 (2006–15) to 0.89 ± 0.03 (2016–25). It holds with windy and dome games excluded (57.5%). About 65 bets a season, 63% of them from Week 6 on. |
| **Evidence against** | p = 0.0035 against a Bonferroni bar of 0.00046 for 109 variants. The era split was chosen after looking (2006–15 was 48.2%). The mirror rule (low totals → over) fails (52.0%). The evidence uses consensus closes, while the forward test uses one book's last quote. |
| **Grading** | Win rate and ROI at the entry price; pushes return the stake. CLV isn't the metric, because the rule bets at the close on the claim that the close is wrong. Graded by `scripts/score_forward.py` (RULE_HT). |
| **Decision** | Made once, after the 2027 season, on 2026 Weeks 6+ and 2027 pooled. **Promote** to the 0.5% stake only if the record beats the break-even of the prices taken with a one-sided binomial p < 0.05 and ROI > 0. **Drop** if the win rate is at or below that break-even. **Otherwise** keep it on paper for 2028 under the same rule. There are no interim decisions. |
| **Power** | About 105 bets are expected. At −110 that needs about 62% to pass. If the true rate is the screen's 57.7%, the chance of passing is only about 22–27%, so the most likely outcome is "keep on paper". |

## Watch / avoid

* Rain, snow and cold-only plays: watch only (rain faded; snow n = 47).
* The weather-only model lean: not used for CFB (walk-forward 52.8% at P ≥ 53%).
* Indoor venues and neutral sites without venue coordinates.

Lines: The Odds API (Pinnacle, else DraftKings) when `ODDS_API_KEY` is set;
otherwise ESPN's DraftKings feed when it responds. With neither, triggers arrive
as WATCH / no price.
