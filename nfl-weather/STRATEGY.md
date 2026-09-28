# NFL weather betting playbook

The edge is real but small and uneven: 13 of 20 seasons were profitable, and the
last two were flat. Bet small, bet early, and grade yourself on closing-line
value (CLV), not wins. Numbers below are from `output/tables/strategies.csv`
(run `scripts/strategies.py`); 108 betting variants were examined in total, so
treat any single bucket with suspicion.

## 1. BET: early wind under

| | |
|---|---|
| **Trigger** | Outdoor stadium; kickoff wind forecast **≥ 15 mph** (game-book scale), **1–3 days before kickoff**. Alert: `BET 1u WIND UNDER`. |
| **Action** | Bet the under right away at the best number you can find. Don't wait for Sunday. |
| **Size** | 1 unit = 1% of bankroll. **Storm** (rain ≥ 0.06 in or snow ≥ 0.1 in also forecast in the game window): 1.5 units. |
| **Price** | −110 or better; pass if the best price is worse than −115. On Kalshi, buy NO on the strike nearest the book total only if ask + fee ≤ 52¢ (50¢ + fee breaks even at 51.75%, cheaper than −110's 52.4%). |
| **Evidence** | 57.2% vs the close, 682 games 1999–2025 (+9% ROI at −110). 59.7% vs the opener, 2007–2021. In these games the total fell 1.0 point from open to close on average; when it fell 1.5+, the opener under won 69%. Walk-forward bets beat the close 63% of the time by +0.9 points. Storm games: 68% (95 games). |
| **Caveats** | 18–18 in 2024–26, even on observed wind. The backtest uses observed kickoff wind; a 1-day-out 15+ mph forecast verified about two-thirds of the time (2024–26). |
| **Kill switch** | After 40 bets, stop if average CLV ≤ 0 (`scripts/score_forward.py`). |

## 2. BET: line lag

Wind forecast jumps **≥ 5 mph to 15+** since the last check while the total has
moved less than half a point. Same action and size as rule 1. Alert: `BET LINE LAG`.

## 3. WATCH: log it, don't bet it yet

| Rule | Why it's not a bet yet |
|---|---|
| **Model lean**: P(under) ≥ 55% | The pre-registered forward test (`PREREGISTRATION.md`). Its rain term is fit on observed rain, which overstates forecast rain (next row). |
| **Rain unders from forecasts** | Historical 62% (401 games) comes mostly from rain nobody forecast. In 2024–26, surprise rain went 9–4 under; forecast rain went 8–9, already priced into the close. |
| **Cold visitor**: dome or warm-climate visitor, game ≤ 32°F | Home team covered 58.6% (113 games) and the visitor's team total went under 58.0%. Cold-climate visitors in the same games: 47.0%. Right shape, small sample. |
| **Props** | QB passing yards fall about 11% at 20+ mph and 7% in rain; a 50-yard FG goes from 78% to 72% at ≤ 32°F and 67% if also windy. No historical prop lines, so none of this is backtested. |

## 4. AVOID

* **Snow unders**: 45% (89 games). Snow games haven't scored less than the line.
* **Cold-only totals**: freezing, calm, dry overs won 59% before 2014 and 50% since.
* **10–14 mph wind at the close**: 54%, too thin after the vig.
* **Indoor games** and retractable roofs that are likely closed.

## Rules of the road

* One bet per game, no parlays, at most 3 units on a weekend.
* Shop the number. Half a point of total is worth roughly 1–2.5 points of win probability.
* Every alert snapshot is logged to `data/forward/ledger.csv`; record the price you actually got.
* After Week 18, run `scripts/score_forward.py` and apply the decision rule in `PREREGISTRATION.md`.
* Paper research first: nothing in this project places bets.
