# Value Finder research lab

Historical discovery through 2025. 2026 remains sealed. No strategy is approved by this report.
Target: actual points minus the closing total. This tests scoring information relative to the close; it does not test available entry prices, CLV, or profit.

Status: completed. Twenty new specifications recorded locally; six existing controls/models reused.
Project-count floor for adjustment: 314. Reconcile the 20 new trials with the hub before promotion.

| Comparison | Games | Seasons | MSE improvement | Positive seasons | Adjusted p |
|---|---:|---:|---:|---:|---:|
| CFB_REV_PERSISTENCE | 10490 | 15 | 0.0649 | 8 | 1 |
| CFB_REV_PREVIOUS | 10490 | 15 | 0.0382 | 8 | 1 |
| CFB_REV_COMBINED | 10490 | 15 | 0.0122 | 8 | 1 |
| CFB_REV_CURVE | 10490 | 15 | -0.0091 | 8 | 1 |
| CFB_REVISION | 10490 | 15 | -0.0326 | 8 | 1 |
| CFB_REV_REV_CURVE | 10490 | 15 | -0.0405 | 6 | 1 |
| NFL_REVISION | 3230 | 17 | -0.0497 | 9 | 1 |
| NFL_OFFENSIVE_STYLE | 2342 | 15 | -0.0607 | 6 | 1 |
| CFB_REV_ASYMMETRY | 10490 | 15 | -0.0613 | 7 | 1 |
| CFB_REV_CROSSINGS | 10490 | 15 | -0.1195 | 6 | 1 |
| NFL_REV_PERSISTENCE | 3230 | 17 | -0.1254 | 7 | 1 |
| NFL_STYLE_REVISION | 2342 | 15 | -0.1324 | 6 | 1 |
| NFL_STYLE_PERSISTENCE | 2342 | 15 | -0.1393 | 8 | 1 |
| NFL_REV_PREVIOUS | 3230 | 17 | -0.1910 | 6 | 1 |
| NFL_STYLE_REV_STYLE | 2342 | 15 | -0.1934 | 5 | 1 |
| NFL_REV_CROSSINGS | 3230 | 17 | -0.2103 | 6 | 1 |
| NFL_REV_CURVE | 3230 | 17 | -0.2185 | 7 | 1 |
| NFL_REV_ASYMMETRY | 3230 | 17 | -0.2526 | 5 | 1 |
| NFL_STYLE_CURVE | 2342 | 15 | -0.4111 | 6 | 1 |
| NFL_REV_REV_CURVE | 3230 | 17 | -0.4326 | 7 | 1 |
| NFL_REV_COMBINED | 3230 | 17 | -0.6577 | 4 | 1 |
| NFL_REV_REV_INTERACTION | 3230 | 17 | -1.3022 | 7 | 1 |
| CFB_REV_REV_INTERACTION | 10490 | 15 | -8.3007 | 7 | 1 |

Positive improvement means lower prediction error than the paired baseline. Every validation season has equal weight.
Previously explored historical seasons are not untouched confirmation. Bootstrap intervals and leave-one-season-out results are diagnostics, not extra selection gates.

Next stages: timestamped-price evaluation, college input-availability audit, and price-engine robustness each need their own frozen specification list.
