"""Stadium coordinates (keyed by the PFR stadium_id used in nflverse schedules)
and the NOAA GHCN-Daily station used as each home city's "practice climate".

Coordinates only need to be good to ~1 km: the ERA5 reanalysis grid behind
Open-Meteo's archive is ~9-25 km.
"""

# stadium_id: (name, lat, lon, ghcnd_station for home-city climate or None)
STADIUMS = {
    "ATL00": ("Georgia Dome", 33.7577, -84.4008, "USW00013874"),
    "ATL97": ("Mercedes-Benz Stadium", 33.7554, -84.4008, "USW00013874"),
    "BAL00": ("M&T Bank Stadium", 39.2780, -76.6227, "USW00093721"),
    "BOS00": ("Gillette Stadium", 42.0909, -71.2643, "USW00014739"),
    "BOS99": ("Foxboro Stadium", 42.0909, -71.2643, "USW00014739"),
    "BRG00": ("Tiger Stadium (LSU)", 30.4120, -91.1838, None),
    "BUF00": ("Highmark Stadium", 42.7738, -78.7870, "USW00014733"),
    "BUF01": ("Rogers Centre", 43.6414, -79.3894, None),
    "CAR00": ("Bank of America Stadium", 35.2258, -80.8528, "USW00013881"),
    "CHI98": ("Soldier Field", 41.8623, -87.6167, "USW00094846"),
    "CHI99": ("Memorial Stadium (Champaign)", 40.0992, -88.2360, "USW00094846"),
    "CIN00": ("Paycor Stadium", 39.0955, -84.5161, "USW00093814"),
    "CIN99": ("Cinergy Field", 39.0975, -84.5076, "USW00093814"),
    "CLE00": ("Huntington Bank Field", 41.5061, -81.6995, "USW00014820"),
    "DAL00": ("AT&T Stadium", 32.7473, -97.0945, "USW00003927"),
    "DAL99": ("Texas Stadium", 32.8401, -96.9117, "USW00003927"),
    "DEN00": ("Empower Field at Mile High", 39.7439, -105.0201, "USW00003017"),
    "DEN99": ("Mile High Stadium", 39.7458, -105.0215, "USW00003017"),
    "DET00": ("Ford Field", 42.3400, -83.0456, "USW00094847"),
    "DET99": ("Pontiac Silverdome", 42.6457, -83.2553, "USW00094847"),
    "FRA00": ("Deutsche Bank Park", 50.0686, 8.6455, None),
    "GER00": ("Allianz Arena", 48.2188, 11.6247, None),
    "GNB00": ("Lambeau Field", 44.5013, -88.0622, "USW00014898"),
    "HOU00": ("NRG Stadium", 29.6847, -95.4107, "USW00012960"),
    "IND00": ("Lucas Oil Stadium", 39.7601, -86.1639, "USW00093819"),
    "IND99": ("RCA Dome", 39.7635, -86.1636, "USW00093819"),
    "JAX00": ("EverBank Stadium", 30.3239, -81.6373, "USW00013889"),
    "KAN00": ("Arrowhead Stadium", 39.0489, -94.4839, "USW00003947"),
    "LAX01": ("SoFi Stadium", 33.9535, -118.3392, "USW00023174"),
    "LAX97": ("StubHub Center", 33.8644, -118.2611, "USW00023174"),
    "LAX99": ("LA Memorial Coliseum", 34.0141, -118.2879, "USW00023174"),
    "LON00": ("Wembley Stadium", 51.5560, -0.2796, None),
    "LON01": ("Twickenham Stadium", 51.4560, -0.3415, None),
    "LON02": ("Tottenham Hotspur Stadium", 51.6043, -0.0664, None),
    "MAD01": ("Santiago Bernabeu", 40.4531, -3.6883, None),
    "MEL00": ("Melbourne Cricket Ground", -37.8200, 144.9834, None),
    "MEX00": ("Estadio Azteca", 19.3029, -99.1505, None),
    "MIA00": ("Hard Rock Stadium", 25.9580, -80.2389, "USW00012839"),
    "MIN00": ("Metrodome", 44.9738, -93.2581, "USW00014922"),
    "MIN01": ("U.S. Bank Stadium", 44.9737, -93.2575, "USW00014922"),
    "MIN98": ("TCF Bank Stadium", 44.9765, -93.2246, "USW00014922"),
    "MUN01": ("Allianz Arena", 48.2188, 11.6247, None),
    "NAS00": ("Nissan Stadium", 36.1665, -86.7713, "USW00013897"),
    "NOR00": ("Caesars Superdome", 29.9511, -90.0812, "USW00012916"),
    "NYC00": ("Giants Stadium", 40.8135, -74.0745, "USW00014734"),
    "NYC01": ("MetLife Stadium", 40.8128, -74.0742, "USW00014734"),
    "OAK00": ("Oakland Coliseum", 37.7516, -122.2005, "USW00023230"),
    "PAR00": ("Stade de France", 48.9245, 2.3602, None),
    "PHI00": ("Lincoln Financial Field", 39.9008, -75.1675, "USW00013739"),
    "PHI99": ("Veterans Stadium", 39.9067, -75.1714, "USW00013739"),
    "PHO00": ("State Farm Stadium", 33.5276, -112.2626, "USW00023183"),
    "PHO99": ("Sun Devil Stadium", 33.4264, -111.9325, "USW00023183"),
    "PIT00": ("Acrisure Stadium", 40.4468, -80.0158, "USW00094823"),
    "PIT99": ("Three Rivers Stadium", 40.4467, -80.0128, "USW00094823"),
    "RIO00": ("Maracana Stadium", -22.9121, -43.2302, None),
    "SAN00": ("Alamodome", 29.4169, -98.4789, None),
    "SAO00": ("Arena Corinthians", -23.5453, -46.4742, None),
    "SDG00": ("Qualcomm Stadium", 32.7831, -117.1196, "USW00023188"),
    "SEA00": ("Lumen Field", 47.5952, -122.3316, "USW00024233"),
    "SEA98": ("Kingdome", 47.5952, -122.3316, "USW00024233"),
    "SEA99": ("Husky Stadium", 47.6503, -122.3016, "USW00024233"),
    "SFO00": ("Candlestick Park", 37.7136, -122.3861, "USW00023234"),
    "SFO01": ("Levi's Stadium", 37.4030, -121.9700, "USW00023293"),
    "STL00": ("Edward Jones Dome", 38.6328, -90.1885, "USW00013994"),
    "TAM00": ("Raymond James Stadium", 27.9759, -82.5033, "USW00012842"),
    "VEG00": ("Allegiant Stadium", 36.0909, -115.1833, "USW00023169"),
    "WAS00": ("Northwest Stadium", 38.9078, -76.8645, "USW00013743"),
}

# nflverse occasionally tags a neutral-site game with the home team's stadium_id;
# the stadium name is reliable, so these names override the id.
NAME_OVERRIDES = {
    "Tottenham Hotspur Stadium": "LON02",
    "Tottenham Stadium": "LON02",
    "Wembley Stadium": "LON00",
    "Twickenham Stadium": "LON01",
}


def resolve_stadium(stadium_id, stadium_name):
    """Return the stadium key to use for coordinates."""
    if isinstance(stadium_name, str) and stadium_name in NAME_OVERRIDES:
        return NAME_OVERRIDES[stadium_name]
    return stadium_id


def coords(stadium_key):
    s = STADIUMS.get(stadium_key)
    return (s[1], s[2]) if s else (None, None)


def home_stations():
    return sorted({s[3] for s in STADIUMS.values() if s[3]})
