# Venue tables

These tables are used by `markets weather` (`src/markets/weather/`) to place each MLB and soccer game and to fetch its weather. NHL is indoor, so it has no venues here.

| File | What | Source |
|---|---|---|
| `mlb_parks.csv` | The 30 current MLB parks, plus former, temporary and neutral-site parks used since 2020: Oakland Coliseum, Tropicana Field, Steinbrenner Field, Sutter Health Park, Sahlen Field, TD Ballpark, London, Mexico City, Tokyo, Seoul, Field of Dreams, Williamsport, Rickwood and Bristol | [GeoJSON-Ballparks](https://github.com/cageyjames/GeoJSON-Ballparks) (Open Data Commons Attribution License; © its contributors). Four neutral sites were added by hand. |
| `mlb_homes.csv` | Each team's home park by date, including the A's, Rays and Blue Jays moves | Hand-made |
| `soccer_venues.csv` | Every home venue in the S1 leagues (MLS, Liga MX, Brasileirão, J1, K League 1) since 2020, the tournament venues, and the COVID-era relocation venues | Hand-made, except the World Cup 2022 and 2026 stadiums, which come from [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) (CC0) |
| `soccer_homes.csv` | Each club's home venue by date. `*` rows are league-wide windows, such as the MLS is Back bubble in 2020. Dated rows cover the Canadian clubs in 2020–21, stadium moves and the 2024 Porto Alegre floods. | Hand-made |
| `tournament_fixtures.csv` | Date, kickoff (UTC), teams and venue for every World Cup 2022, World Cup 2026 and Euro 2024 match. **No scores:** 2026 is sealed. | openfootball (CC0): `worldcup.json`, `euro.json` |

## Checks

- **Coordinates.**
  - Hand-made rows say `manual (verify on the Mac)`.
  - Rows marked "city-level location" in `used_by`/`notes` are placed at the city, not the stadium. That's within one Open-Meteo grid cell of the ground, which is fine for heat, but not for wind at a specific park.
  - On the Mac, `markets weather venues --confirm` pulls the MLB Stats API's own park coordinates and places every MLB game exactly. Once cached, the join uses the Stats API's coordinates for every game at that park, and `markets weather plan` lists any park whose row here is more than 2 km away, so the row can be corrected.
  - GeoJSON-Ballparks puts Truist Park about 7 km and TD Ballpark about 12 km from the field. Both rows were corrected by hand (September 29, 2026), and `build_venues.py` keeps the corrections.
- **Team names.** Names are matched after normalizing: no accents, no case, and no "FC"/"SC"/"Club".
  - After the day-one probe, `markets weather plan` lists every game it couldn't place and why, for example "unknown home team".
  - To fix one, add the Odds API's spelling to `aliases`. Never guess a venue.
- **Roofs:**
  - `open`: the pitch is open to the sky. A roof over the stands only still counts as open, e.g. Hard Rock Stadium, Lumen Field, most J1 grounds and the seven Euro 2024 grounds without a closing roof (relabelled from `covered` on September 29, 2026; [`HEAT_HYPOTHESES.md`](../../docs/HEAT_HYPOTHESES.md) amendment 1)
  - `retractable` (status per game unknown)
  - `dome`
  - `covered`: a fixed roof over the whole bowl, pitch included, with open sides (SoFi Stadium)
  - `cooled` (the World Cup 2022 stadiums)

  The heat hypotheses use `open` only.
- `markets weather check` validates the tables, and `tests/test_weather.py` runs the same checks.

To rebuild the generated tables, run `python config/venues/build_venues.py` from `sharp-markets/`. It needs network access to GitHub.
