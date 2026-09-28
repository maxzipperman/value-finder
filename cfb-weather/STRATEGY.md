# College football weather playbook (v1)

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

## Watch / avoid

* Rain, snow and cold-only plays: watch only (rain faded; snow n = 47).
* The weather-only model lean: not used for CFB (walk-forward 52.8% at P ≥ 53%).
* Indoor venues and neutral sites without venue coordinates.

Lines: The Odds API (Pinnacle, else DraftKings) when `ODDS_API_KEY` is set;
otherwise ESPN's DraftKings feed when it responds. With neither, triggers arrive
as WATCH / no price.
