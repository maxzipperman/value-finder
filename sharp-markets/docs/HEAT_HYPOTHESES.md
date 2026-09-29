# Heat hypotheses: soccer and MLB (pre-registered)

*Registered September 29, 2026.* No soccer or MLB odds had been pulled, and no weather had been joined to any soccer or MLB outcome. The pulls (S1, B1) start with the 5M month on October 1. This file is the pre-registration the 5M data-use plan promised ([`odds-api-credits.md`](../../strategy-research/odds-api-credits.md#data-use-plan): "S1: kickoff heat index at or above the threshold (defined in PR D) → under at the close"; "B1: heat → over").

**Changes to this file:**
- Before any S1 or B1 odds are joined to weather, changes are dated amendments at the bottom.
- After that, nothing here changes.

## Common to both

| | |
|---|---|
| **Data** | Odds: S1 (soccer, featured markets) and B1 (MLB, featured markets), pulled by `markets odds5m`. Venues and weather: `markets weather` (`src/markets/weather/`, venue tables in `config/venues/`). |
| **Exposure (the trigger)** | The day-1 forecast at the venue for the kickoff hour: Open-Meteo previous-runs, `*_previous_day1`, rounded to the nearest hour. It was issued at least 24 hours before kickoff, so the bet never uses anything unknown at the time. It is available from 2024. |
| **Price** | Pinnacle's total at the close: the last S1/B1 snapshot at least 5 minutes before kickoff (`bulk.close_time`). The rule side is taken at Pinnacle's price on that line. A game with no Pinnacle close is left out, and the count is reported. |
| **Grading** | These rules bet *at* the close, so they are graded on win rate and ROI at that price (the repo's rule for close-priced bets; CLV is zero by construction). |
| **Statistic** | Excess win rate over the de-vigged Pinnacle close: Σ(winᵢ − pᵢ) / n, where pᵢ is the rule side's probability after removing the vig (multiplicative). One-sided z test with variance Σpᵢ(1 − pᵢ). ROI at the actual price is reported next to it. Pushes, and the pushed halves of quarter lines, are left out of n and counted. |
| **Test sample** | 2024 and 2025 (unsealed). |
| **Holdout** | The sealed 2026 season (owner decision, Sep 28) is opened only to confirm, after the test-sample result is written up. |
| **Descriptive only** | The same split using *observed* weather (ERA5, 2020–25) shows whether the mechanism exists at all. It can't be bet, since observed weather isn't known before kickoff, and it decides nothing. |
| **Roofs** | Only venues whose roof is `open` in `config/venues/` count. Retractable roofs (status unknown), domes, covered stadiums and the cooled 2022 World Cup stadiums are left out. |
| **No threshold search** | Each hypothesis has exactly one threshold, set below. No other threshold, lead time, book or market is reported until the primary result is written up. |

**Multiple testing.** These are 3 of the 191 variants in the 5M data-use plan:
- soccer, 1 (S1);
- MLB, 2 (B1: the heat variant below, plus the deferred wind variant).

The repo-wide bar stays **p < 0.00026** (0.05 / 191).

**Decision rules (both hypotheses):**
- **Confirmed:** the test sample clears p < 0.00026, *and* the sealed 2026 sample shows a positive excess win rate with one-sided p < 0.05.
- **Promising:** the test sample has p < 0.05 but misses the bar. The rule gets a paper forward test only (never staked), and the result is re-read after 2026 is unsealed.
- **Rejected:** anything else, including a wrong-signed result.
- **No decision:** fewer than 150 qualifying games with a Pinnacle close in the test sample. The count is reported and nothing else is.

## S-H1: soccer heat → under

| | |
|---|---|
| **Games** | Every S1 match at an `open` venue: MLS, Liga MX, Brasileirão, J1, K League 1, Copa América 2024, Club World Cup 2025, Gold Cup 2025, Leagues Cup 2025 and Euro 2024. World Cup 2022 is left out as cooled; World Cup 2026 is sealed. |
| **Trigger** | Day-1 forecast **NWS heat index at kickoff ≥ 90 °F (32.2 °C)**. That's where the NWS "extreme caution" band begins. The heat index is computed from temperature and relative humidity (`weather/heat.py`, the NWS Rothfusz equation). |
| **Bet** | **Under** the full-time total at Pinnacle's close. |
| **Why** | Players cover less high-intensity distance in heat, and teams slow the game down. If the closing total under-adjusts, unders win more often than the price implies. |

## B-H1: MLB heat → over

| | |
|---|---|
| **Games** | Every B1 game (regular season and postseason) at an `open` park. The venue is placed game by game from the MLB Stats API when cached, otherwise from the dated home-park table. |
| **Trigger** | Day-1 forecast **air temperature at first pitch ≥ 90 °F (32.2 °C)**. This uses temperature, not the heat index: ball carry depends on air density, which falls as temperature rises. Humidity has a small effect on density in the opposite direction to what "feels hotter" suggests, so it's left out. |
| **Bet** | **Over** the full-game total at Pinnacle's close. Whole-number totals that push are refunded and counted. |
| **Why** | Fly balls carry farther in hot, thin air, and published work finds more home runs on hotter days. If the closing total under-adjusts, overs win more often than the price implies. |

**B-H2, wind blowing in → under (registered, deferred).** It needs each park's orientation (the bearing from home plate to center field), which `config/venues/mlb_parks.csv` doesn't have yet. The orientation, the wind-speed threshold and the "blowing in" angle will be added as a dated amendment here before any B1 odds are joined to weather. Until then it is untested and still counted.

## Amendments

None yet.
