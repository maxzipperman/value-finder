"""Weather joins for the 5M-month sports (MLB and the soccer heat leagues). GET-only, cache-first.

venues.py      venue tables (config/venues/) and which venue a game was played at
heat.py        NWS heat index
openmeteo.py   Open-Meteo archive (ERA5, observed) and previous-runs (day-1 forecast) client and fetch plan
gamevenues.py  game-level venues on the Mac: MLB Stats API schedule, ESPN soccer scoreboards
join.py        one row per game: venue, roof, kickoff weather, heat index (data/weather/); `qualifying` applies
               the pre-registered triggers and writes the game list the HB1/HS1 close-only pulls read

The heat hypotheses these feed are pre-registered in docs/HEAT_HYPOTHESES.md.
"""
