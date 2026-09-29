# Heat hypotheses: soccer and MLB (pre-registered)

*Registered September 29, 2026.* No soccer or MLB odds had been pulled, and no weather had been joined to any soccer or MLB outcome. The pulls (S1, B1) start with the 5M month on October 1. This file is the pre-registration the 5M data-use plan promised ([`odds-api-credits.md`](../../strategy-research/odds-api-credits.md#data-use-plan): "S1: kickoff heat index at or above the threshold (defined in PR D) → under at the close"; "B1: heat → over").

**Changes to this file:**
- Before any S1 or B1 odds are joined to weather, changes are dated amendments at the bottom.
- After that, nothing here changes.
- Amendments 1–3 (September 29, 2026) are at the bottom and take precedence over the text above. Amendment 2 widens the freeze to the first join of any outcome, as well as any odds.

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

All three were made on September 29, 2026, in [#33](https://github.com/maxzipperman/value-finder/issues/33). At that point no S1 or B1 odds had been pulled, and no soccer or MLB outcome or odds had been joined to any weather.

### Amendment 1: roof labels, Euro 2024 and World Cup 2022

- **Roof labels made consistent.** A roof over the stands only, with the pitch open to the sky, is `open` in every venue table. That was already the case for Hard Rock Stadium, Lumen Field, Lincoln Financial Field and the J1 and Liga MX grounds.
  - Seven Euro 2024 grounds with that kind of roof had been labelled `covered`: Berlin, Munich, Dortmund, Stuttgart, Hamburg, Cologne and Leipzig. They are now `open`.
  - The three Euro grounds whose roof closes over the pitch (Düsseldorf, Gelsenkirchen and Frankfurt) stay `retractable`, so they stay out.
  - `covered` now means a fixed roof over the pitch as well (SoFi Stadium). The "Roofs" row above is otherwise unchanged: only `open` venues count.
- **Euro 2024 stays in S-H1.** Under the old labels it contributed no games at all. Under the consistent labels, 37 of its 51 matches are at `open` grounds.
- **World Cup 2022 is excluded as a competition, not by its roofs.** Seven of its 64 matches were at Stadium 974, which is not cooled and is labelled `open`, so the roof rule alone would let them in. The whole tournament stays out of S-H1, as registered in the Games row. That row's "left out as cooled" should read "left out as a competition": it was a November–December tournament played mostly in cooled stadiums.

### Amendment 2: result sources, settlement and the freeze

- **Result sources.** Outcomes are matched to the Odds API event by teams and kickoff within 12 hours, the same way the venue join matches games.
  - **MLB:** the MLB Stats API (`statsapi.mlb.com` schedule, the endpoint `markets weather venues` already caches, with the line score). It gives the final runs, the innings played and the game status.
  - **Soccer:** ESPN's public scoreboard and match summaries, for every S1 competition. For a match that went to extra time, the regulation score comes from ESPN's goal events in the first two periods. Where openfootball (CC0) has the match (Euro 2024 and both World Cups), its full-time score is a cross-check. If the two disagree, or no regulation score can be established, the match is left out and counted.
- **Settlement, soccer.**
  - Totals settle on the goals scored in regulation: 90 minutes plus stoppage time. Extra time and penalty shoot-outs don't count; this is the usual rule, Pinnacle's included.
  - An abandoned match, or one not played on its scheduled day, is void: left out of n and counted.
  - A delayed kickoff on the same day counts. The exposure stays the day-1 forecast for the scheduled kickoff hour, because that is what was known when the bet was placed.
- **Settlement, MLB.**
  - A game counts when it is final and went at least 9 innings, or 8½ with the home team ahead. Extra innings count toward the total.
  - A game called before that point (a shortened official game) is void.
  - A game suspended and finished on a later date is void, whatever its final score, because the weather at first pitch no longer describes the whole game.
  - A game postponed from its scheduled date is void. A delayed start on the same day counts, with the forecast for the scheduled first pitch.
  - Seven-inning doubleheader games (2020–21) settle at 7 innings. They are outside the 2024–25 test sample, so they matter only to the descriptive split.
  - Void games are left out of n and counted, as pushes are.
- **These rules decide,** even where a book graded a bet differently. They are fixed before any outcome is seen.
- **The freeze.** This file is frozen at the first join of any soccer or MLB outcome, or of any S1 or B1 odds, to the weather table, whichever comes first. Until then, changes are dated amendments here. The date of that first join goes in `STATUS.md`. This replaces the freeze rule under "Changes to this file", which named odds only.

### Amendment 3: World Cup 2026 is in the confirmatory sample

- The sealed 2026 sample that confirms S-H1 includes the 2026 World Cup (June–July, in North America). Its matches at `open` grounds count exactly like the calendar-2026 league matches: 65 of its 104 matches under the current labels. The other 39 are at retractable-roof grounds or SoFi Stadium.
- The owner sealed it with the other calendar-2026 soccer on September 28. This amendment says it is part of the confirmation, not set aside.
- The confirmation is still one test on the whole sealed S1 sample, not a separate test for each competition, so the variant count stays at 3 of 191.
