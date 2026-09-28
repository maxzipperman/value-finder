# H4a — Kalshi NFL totals vs wind, 2025 season

- Study games (played): 285; Kalshi total ladders matched: 285; with a valid T-5m Kalshi implied total: 281; unmatched in-season Kalshi events: 0
- Skipped Kalshi events (logged, not errors): {'preseason (not in study data)': 16, 'other season': 111}; matched with a ticker-date shift (flexed games): 1
- Terms dropped (no variation in this sample): none
- n_variants_tested: 16 (5 buckets x 2 trade sides + 2 specs x 3 outcomes)
- Weather = observed kickoff weather (study caveat). Kalshi prices = last 1-min candle at or before the snapshot.

## Regression: points vs weather terms (HC1 SEs, one season, no fixed effects)
| spec | term | actual − book close | actual − Kalshi T-5m | Kalshi − book |
|---|---|---|---|---|
| bins | wind_10_14 | -4.92 (2.75), p=0.074 | -4.75 (2.76), p=0.085 | -0.17 (0.09), p=0.053 |
| bins | wind_15p | -2.25 (3.52), p=0.522 | -2.11 (3.53), p=0.550 | -0.14 (0.11), p=0.206 |
| bins | temp_le32 | -3.52 (2.83), p=0.214 | -3.51 (2.84), p=0.216 | -0.01 (0.10), p=0.918 |
| bins | rain | -2.58 (3.52), p=0.463 | -2.55 (3.48), p=0.465 | -0.04 (0.13), p=0.777 |
| bins | snow | +9.61 (5.66), p=0.089 | +9.78 (5.62), p=0.082 | -0.17 (0.18), p=0.360 |
| bins | indoor | -0.40 (1.76), p=0.822 | -0.44 (1.76), p=0.800 | +0.05 (0.07), p=0.461 |
| linear | wind_mph | -0.26 (0.22), p=0.230 | -0.25 (0.22), p=0.247 | -0.01 (0.01), p=0.267 |
| linear | cold_deg | -0.26 (0.11), p=0.018 | -0.26 (0.11), p=0.022 | -0.01 (0.00), p=0.143 |
| linear | rain | -3.19 (3.58), p=0.373 | -3.13 (3.53), p=0.376 | -0.06 (0.14), p=0.649 |
| linear | snow | +11.35 (5.46), p=0.038 | +11.45 (5.42), p=0.035 | -0.10 (0.19), p=0.610 |
| linear | indoor | -2.26 (2.32), p=0.331 | -2.25 (2.32), p=0.332 | -0.00 (0.09), p=0.985 |

## By wind bucket (means ± SE)
| bucket | games | actual − book | actual − Kalshi | Kalshi − book | Kalshi move T-24h→T-5m | Kalshi P(over @ book line) | under EV/contract (n) | under win % | over EV/contract |
|---|---|---|---|---|---|---|---|---|---|
| wind 0-4 | 43 | +4.29 ± 1.87 | +4.35 ± 1.85 | -0.06 ± 0.08 | +0.19 ± 0.12 | 0.498 | -0.172 ± 0.073 (43) | 0.349 | +0.124 ± 0.073 |
| wind 5-9 | 95 | +1.10 ± 1.41 | +1.12 ± 1.42 | -0.02 ± 0.05 | -0.01 ± 0.08 | 0.500 | -0.055 ± 0.052 (95) | 0.474 | +0.006 ± 0.052 |
| wind 10-14 | 33 | -2.71 ± 2.53 | -2.50 ± 2.53 | -0.21 ± 0.08 | -0.22 ± 0.15 | 0.493 | +0.047 ± 0.087 (33) | 0.576 | -0.096 ± 0.088 |
| wind 15+ | 20 | -0.45 ± 3.36 | -0.28 ± 3.37 | -0.17 ± 0.10 | -0.86 ± 0.15 | 0.493 | +0.022 ± 0.114 (20) | 0.550 | -0.071 ± 0.113 |
| dome/closed | 90 | +1.89 ± 1.25 | +1.86 ± 1.26 | +0.03 ± 0.05 | +0.17 ± 0.08 | 0.501 | -0.018 ± 0.053 (90) | 0.500 | -0.032 ± 0.054 |
