# H4a — Kalshi NFL totals vs wind, 2025 season

- Study games (played): 285; Kalshi total ladders matched: 285; with a valid T-5m Kalshi implied total: 281; unmatched in-season Kalshi events: 0
- Skipped Kalshi events (logged, not errors): {'preseason (not in study data)': 16, 'other season': 111}; matched with a ticker-date shift (flexed games): 1
- Terms dropped (no variation in this sample): ['rain', 'snow'] — the study's 2023+ games use gamebook weather, which has wind and temperature but no precipitation.
- n_variants_tested: 16 (5 buckets x 2 trade sides + 2 specs x 3 outcomes)
- Weather = observed kickoff weather (study caveat). Kalshi prices = last 1-min candle at or before the snapshot.

## Regression: points vs weather terms (HC1 SEs, one season, no fixed effects)
| spec | term | actual − book close | actual − Kalshi T-5m | Kalshi − book |
|---|---|---|---|---|
| bins | wind_10_14 | -5.04 (2.83), p=0.075 | -4.84 (2.84), p=0.088 | -0.20 (0.09), p=0.027 |
| bins | wind_15p | -2.87 (3.49), p=0.412 | -2.73 (3.51), p=0.437 | -0.14 (0.11), p=0.196 |
| bins | temp_le32 | -1.61 (3.03), p=0.594 | -1.55 (3.02), p=0.607 | -0.06 (0.10), p=0.542 |
| bins | indoor | -1.23 (1.73), p=0.476 | -1.27 (1.73), p=0.463 | +0.04 (0.06), p=0.557 |
| linear | wind_mph | -0.34 (0.22), p=0.119 | -0.34 (0.22), p=0.130 | -0.01 (0.01), p=0.240 |
| linear | cold_deg | -0.18 (0.11), p=0.117 | -0.17 (0.12), p=0.138 | -0.01 (0.00), p=0.043 |
| linear | indoor | -3.47 (2.30), p=0.131 | -3.45 (2.30), p=0.133 | -0.02 (0.09), p=0.847 |

## By wind bucket (means ± SE)
| bucket | games | actual − book | actual − Kalshi | Kalshi − book | Kalshi move T-24h→T-5m | Kalshi P(over @ book line) | under EV/contract (n) | under win % | over EV/contract |
|---|---|---|---|---|---|---|---|---|---|
| wind 0-4 | 40 | +5.58 ± 1.84 | +5.62 ± 1.82 | -0.04 ± 0.08 | +0.20 ± 0.13 | 0.498 | -0.220 ± 0.073 (40) | 0.300 | +0.172 ± 0.073 |
| wind 5-9 | 95 | +1.10 ± 1.41 | +1.12 ± 1.42 | -0.02 ± 0.05 | -0.01 ± 0.08 | 0.500 | -0.055 ± 0.052 (95) | 0.474 | +0.006 ± 0.052 |
| wind 10-14 | 32 | -2.66 ± 2.61 | -2.43 ± 2.61 | -0.23 ± 0.08 | -0.28 ± 0.15 | 0.492 | +0.033 ± 0.089 (32) | 0.562 | -0.081 ± 0.089 |
| wind 15+ | 20 | -0.45 ± 3.36 | -0.28 ± 3.37 | -0.17 ± 0.10 | -0.86 ± 0.15 | 0.493 | +0.022 ± 0.114 (20) | 0.550 | -0.071 ± 0.113 |
| dome/closed | 94 | +1.35 ± 1.23 | +1.33 ± 1.24 | +0.02 ± 0.05 | +0.18 ± 0.08 | 0.501 | +0.003 ± 0.052 (94) | 0.521 | -0.053 ± 0.052 |
