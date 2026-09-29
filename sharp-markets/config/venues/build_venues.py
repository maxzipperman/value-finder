"""Rebuild the generated venue tables: mlb_parks.csv, soccer_venues.csv, tournament_fixtures.csv.

    python config/venues/build_venues.py            # from sharp-markets/; needs GitHub access

Sources (pinned):
  cageyjames/GeoJSON-Ballparks  4a3b72ede056f0b99facd0c1af1ef4a7aeb1d8d4  (ODC Attribution License)
  openfootball/worldcup.json    516d3825c3bd23fdc298c4014e84bde78f2d4965  (CC0)
  openfootball/euro.json        7bbf6309bdda6896d6bb9ca218c1e15eaf418ce3  (CC0)
The hand-made rows (league venues, neutral MLB sites, Euro 2024 grounds) are in this file. The fixture
table keeps date, kickoff, teams and venue only: no scores (World Cup 2026 is a sealed holdout).
mlb_homes.csv and soccer_homes.csv are edited by hand, not generated.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PINS = {"gb": ("https://github.com/cageyjames/GeoJSON-Ballparks", "4a3b72ede056f0b99facd0c1af1ef4a7aeb1d8d4"),
        "of_worldcup.json": ("https://github.com/openfootball/worldcup.json", "516d3825c3bd23fdc298c4014e84bde78f2d4965"),
        "of_euro.json": ("https://github.com/openfootball/euro.json", "7bbf6309bdda6896d6bb9ca218c1e15eaf418ce3")}
HERE = Path(__file__).resolve().parent


def fetch_sources(tmp: Path) -> None:
    for name, (url, sha) in PINS.items():
        subprocess.run(["git", "clone", "-q", url, str(tmp / name)], check=True)
        subprocess.run(["git", "-C", str(tmp / name), "checkout", "-q", sha], check=True)


import csv
import json
import re
import unicodedata
from datetime import datetime, timedelta


def build_mlb(SRC, OUT):
    f = json.load(open(SRC + 'gb/ballparks.json'))['features']
    leg = json.load(open(SRC + 'gb/legacy_ballpark.geojson'))['features']
    RETRACT = {"Chase Field", "Daikin Park", "Globe Life Field", "loanDepot Park", "American Family Field", "T-Mobile Park", "Rogers Centre"}
    DOME = {"Tropicana Field", "Tokyo Dome", "Gocheok Sky Dome"}
    ALIAS = {"Daikin Park": "Minute Maid Park", "Rate Field": "Guaranteed Rate Field", "American Family Field": "Miller Park",
             "loanDepot Park": "loanDepot park;Marlins Park", "George M. Steinbrenner Field": "Steinbrenner Field",
             "Sutter Health Park": "", "Oakland Coliseum": "RingCentral Coliseum;Oakland-Alameda County Coliseum",
             "Rogers Centre": "", "Globe Life Field": "", "Oracle Park": "", "Truist Park": ""}
    CITY = {"Baltimore Orioles": "Baltimore", "Boston Red Sox": "Boston", "New York Yankees": "Bronx", "Tampa Bay Rays": "Tampa",
            "Toronto Blue Jays": "Toronto", "Chicago White Sox": "Chicago", "Cleveland Guardians": "Cleveland",
            "Detroit Tigers": "Detroit", "Kansas City Royals": "Kansas City", "Minnesota Twins": "Minneapolis",
            "Oakland Athletics": "West Sacramento", "Houston Astros": "Houston", "Los Angeles Angels": "Anaheim",
            "Seattle Mariners": "Seattle", "Texas Rangers": "Arlington", "Atlanta Braves": "Cumberland",
            "Miami Marlins": "Miami", "New York Mets": "Queens", "Philadelphia Phillies": "Philadelphia",
            "Washington Nationals": "Washington", "Chicago Cubs": "Chicago", "Cincinnati Reds": "Cincinnati",
            "Milwaukee Brewers": "Milwaukee", "Pittsburgh Pirates": "Pittsburgh", "St. Louis Cardinals": "St. Louis",
            "Arizona Diamondbacks": "Phoenix", "Colorado Rockies": "Denver", "Los Angeles Dodgers": "Los Angeles",
            "San Diego Padres": "San Diego", "San Francisco Giants": "San Francisco"}
    rows = []
    def vid(name):
        import re, unicodedata
        s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    def add(name, city, country, lat, lon, roof, src, note=""):
        rows.append(dict(venue_id=vid(name), name=name, aliases=ALIAS.get(name, ""), city=city, country=country,
                         lat=round(float(lat), 5), lon=round(float(lon), 5), roof=roof, source=src, notes=note))
    for x in f:
        p = x['properties']
        if p.get('Class') != 'MLB':
            continue
        name = p['Stadium'].replace("loanDepot park", "loanDepot Park")
        lon, lat = x['geometry']['coordinates']
        roof = "retractable" if name in RETRACT else "dome" if name in DOME else "open"
        add(name, CITY[p['Team']], "CA" if "Toronto" in p['Team'] else "US", lat, lon, roof, "GeoJSON-Ballparks")
    for x in f:
        p = x['properties']
        if p.get('Stadium') in ("Sahlen Field", "TD Ballpark") and p.get('Class') in ('AAA', 'Single-A'):
            lon, lat = x['geometry']['coordinates']
            add(p['Stadium'], "Buffalo" if "Sahlen" in p['Stadium'] else "Dunedin", "US", lat, lon, "open",
                "GeoJSON-Ballparks", "Blue Jays temporary home 2020-21")
    for x in leg:
        p = x['properties']
        b = p['Ballpark']
        if b in ("Oakland Coliseum", "Tropicana Field", "Estadio Alfredo Harp Helú", "Tokyo Dome", "Gocheok Sky Dome",
                 "BB&T Ballpark at Historic Bowman Field"):
            lon, lat = x['geometry']['coordinates']
            city, country, note = {"Oakland Coliseum": ("Oakland", "US", "Athletics through 2024"),
                                   "Tropicana Field": ("St. Petersburg", "US", "Rays through 2024; return in 2026 to verify"),
                                   "Estadio Alfredo Harp Helú": ("Mexico City", "MX", "Mexico City Series (neutral)"),
                                   "Tokyo Dome": ("Tokyo", "JP", "Tokyo Series 2025 (neutral)"),
                                   "Gocheok Sky Dome": ("Seoul", "KR", "Seoul Series 2024 (neutral)"),
                                   "BB&T Ballpark at Historic Bowman Field": ("Williamsport", "US", "Little League Classic (neutral)")}[b]
            name = "Bowman Field" if "Bowman" in b else b
            roof = "dome" if b in DOME else "open"
            add(name, city, country, lat, lon, roof, "GeoJSON-Ballparks (legacy)", note)
    for name, city, country, lat, lon, note in [
            ("London Stadium", "London", "GB", 51.5387, -0.0166, "London Series (neutral)"),
            ("Field of Dreams", "Dyersville", "US", 42.4983, -91.0553, "MLB at Field of Dreams 2021-22 (neutral)"),
            ("Rickwood Field", "Birmingham", "US", 33.5017, -86.8503, "MLB at Rickwood Field 2024 (neutral)"),
            ("Bristol Motor Speedway", "Bristol", "US", 36.5157, -82.2570, "Speedway Classic 2025 (neutral)")]:
        add(name, city, country, lat, lon, "open", "manual (verify on the Mac)", note)
    rows.sort(key=lambda r: r["venue_id"])
    with open(OUT + 'mlb_parks.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    print(len(rows))


def build_soccer(SRC, OUT):
    def vid(name):
        s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


    # (name, aliases, city, country, lat, lon, roof, used_by)
    M = [
        # ---- MLS (and US/Canada tournament venues)
        ("Mercedes-Benz Stadium", "", "Atlanta", "US", 33.7553, -84.4006, "retractable", "MLS; Copa 2024; CWC 2025; WC 2026"),
        ("Q2 Stadium", "", "Austin", "US", 30.3877, -97.7195, "open", "MLS 2021-; Copa 2024; Gold Cup 2025"),
        ("Bank of America Stadium", "", "Charlotte", "US", 35.2258, -80.8528, "open", "MLS 2022-; Copa 2024; CWC 2025"),
        ("Soldier Field", "", "Chicago", "US", 41.8623, -87.6167, "open", "MLS"),
        ("Nippert Stadium", "", "Cincinnati", "US", 39.1310, -84.5163, "open", "MLS 2020"),
        ("TQL Stadium", "", "Cincinnati", "US", 39.1110, -84.5220, "open", "MLS 2021-; CWC 2025"),
        ("Dick's Sporting Goods Park", "", "Commerce City", "US", 39.8056, -104.8919, "open", "MLS"),
        ("Historic Crew Stadium", "MAPFRE Stadium", "Columbus", "US", 40.0095, -82.9911, "open", "MLS 2020-21"),
        ("ScottsMiracle-Gro Field", "Lower.com Field", "Columbus", "US", 39.9685, -83.0171, "open", "MLS 2021-"),
        ("Audi Field", "", "Washington", "US", 38.8684, -77.0128, "open", "MLS; CWC 2025"),
        ("Toyota Stadium", "Toyota Stadium Frisco", "Frisco", "US", 33.1545, -96.8352, "open", "MLS"),
        ("Shell Energy Stadium", "BBVA Stadium", "Houston", "US", 29.7522, -95.3524, "open", "MLS; Gold Cup 2025"),
        ("Chase Stadium", "DRV PNK Stadium;Inter Miami CF Stadium", "Fort Lauderdale", "US", 26.1930, -80.1611, "open", "MLS 2020-25"),
        ("Nu Stadium", "Miami Freedom Park", "Miami", "US", 25.7900, -80.2600, "open", "MLS 2026- (approximate location)"),
        ("Dignity Health Sports Park", "", "Carson", "US", 33.8644, -118.2611, "open", "MLS; Gold Cup 2025"),
        ("BMO Stadium", "Banc of California Stadium", "Los Angeles", "US", 34.0128, -118.2845, "open", "MLS"),
        ("Allianz Field", "", "Saint Paul", "US", 44.9530, -93.1650, "open", "MLS"),
        ("Stade Saputo", "", "Montreal", "CA", 45.5627, -73.5528, "open", "MLS"),
        ("Nissan Stadium", "", "Nashville", "US", 36.1665, -86.7713, "open", "MLS 2020-21"),
        ("GEODIS Park", "", "Nashville", "US", 36.1302, -86.7658, "open", "MLS 2022-; CWC 2025"),
        ("Gillette Stadium", "Boston Stadium", "Foxborough", "US", 42.0909, -71.2643, "open", "MLS; WC 2026"),
        ("Yankee Stadium", "", "Bronx", "US", 40.8296, -73.9262, "open", "MLS (NYCFC)"),
        ("Citi Field", "", "Queens", "US", 40.7571, -73.8458, "open", "MLS (NYCFC)"),
        ("Red Bull Arena", "Sports Illustrated Stadium", "Harrison", "US", 40.7368, -74.1503, "open", "MLS"),
        ("Inter&Co Stadium", "Exploria Stadium", "Orlando", "US", 28.5411, -81.3893, "open", "MLS; Copa 2024; CWC 2025"),
        ("Subaru Park", "", "Chester", "US", 39.8328, -75.3789, "open", "MLS"),
        ("Providence Park", "", "Portland", "US", 45.5215, -122.6917, "open", "MLS"),
        ("America First Field", "Rio Tinto Stadium", "Sandy", "US", 40.5829, -111.8933, "open", "MLS"),
        ("PayPal Park", "Earthquakes Stadium", "San Jose", "US", 37.3513, -121.9251, "open", "MLS; Gold Cup 2025"),
        ("Lumen Field", "Seattle Stadium", "Seattle", "US", 47.5952, -122.3316, "open", "MLS; CWC 2025; WC 2026"),
        ("Children's Mercy Park", "", "Kansas City", "US", 39.1218, -94.8231, "open", "MLS; Copa 2024"),
        ("Energizer Park", "CITYPARK", "St. Louis", "US", 38.6312, -90.2107, "open", "MLS 2023-; Gold Cup 2025"),
        ("BMO Field", "Toronto Stadium", "Toronto", "CA", 43.6332, -79.4186, "open", "MLS; WC 2026"),
        ("BC Place", "BC Place Vancouver;Vancouver Stadium", "Vancouver", "CA", 49.2768, -123.1120, "retractable", "MLS; Gold Cup 2025; WC 2026"),
        ("Snapdragon Stadium", "", "San Diego", "US", 32.7831, -117.1196, "open", "MLS 2025-; Gold Cup 2025"),
        ("Pratt & Whitney Stadium", "Rentschler Field", "East Hartford", "US", 41.7599, -72.6190, "open", "Toronto FC home 2020 (COVID)"),
        ("ESPN Wide World of Sports Complex", "", "Bay Lake", "US", 28.3370, -81.5560, "open", "MLS is Back 2020 (bubble)"),
        # ---- NFL-type stadiums used by the tournaments
        ("MetLife Stadium", "New York New Jersey Stadium", "East Rutherford", "US", 40.8135, -74.0745, "open", "Copa 2024; CWC 2025; WC 2026"),
        ("AT&T Stadium", "Dallas Stadium", "Arlington", "US", 32.7473, -97.0945, "retractable", "Copa 2024; Gold Cup 2025; WC 2026"),
        ("NRG Stadium", "Houston Stadium", "Houston", "US", 29.6847, -95.4107, "retractable", "Copa 2024; Gold Cup 2025; WC 2026"),
        ("Hard Rock Stadium", "Miami Stadium", "Miami Gardens", "US", 25.9580, -80.2389, "open", "Copa 2024; CWC 2025; WC 2026"),
        ("SoFi Stadium", "Los Angeles Stadium", "Inglewood", "US", 33.9535, -118.3392, "covered", "Copa 2024; Gold Cup 2025; WC 2026"),
        ("State Farm Stadium", "", "Glendale", "US", 33.5276, -112.2626, "retractable", "Copa 2024; Gold Cup 2025"),
        ("Allegiant Stadium", "", "Paradise", "US", 36.0909, -115.1833, "dome", "Copa 2024; Gold Cup 2025"),
        ("Levi's Stadium", "San Francisco Bay Area Stadium", "Santa Clara", "US", 37.4030, -121.9700, "open", "Copa 2024; Gold Cup 2025; WC 2026"),
        ("GEHA Field at Arrowhead Stadium", "Arrowhead Stadium;Kansas City Stadium", "Kansas City", "US", 39.0489, -94.4839, "open", "Copa 2024; WC 2026"),
        ("Rose Bowl", "", "Pasadena", "US", 34.1613, -118.1676, "open", "CWC 2025"),
        ("Lincoln Financial Field", "Philadelphia Stadium", "Philadelphia", "US", 39.9008, -75.1675, "open", "CWC 2025; WC 2026"),
        ("Camping World Stadium", "", "Orlando", "US", 28.5392, -81.4029, "open", "CWC 2025"),
        ("U.S. Bank Stadium", "", "Minneapolis", "US", 44.9736, -93.2575, "dome", "Gold Cup 2025"),
        # ---- Liga MX
        ("Estadio Azteca", "Estadio Banorte;Estadio Ciudad de México;Mexico City Stadium", "Mexico City", "MX", 19.3029, -99.1505, "open", "Liga MX; WC 2026"),
        ("Estadio Ciudad de los Deportes", "", "Mexico City", "MX", 19.3834, -99.1782, "open", "Liga MX 2024-"),
        ("Estadio Olímpico Universitario", "", "Mexico City", "MX", 19.3319, -99.1921, "open", "Liga MX"),
        ("Estadio Akron", "Estadio Guadalajara;Guadalajara Stadium", "Zapopan", "MX", 20.6818, -103.4626, "open", "Liga MX; WC 2026"),
        ("Estadio Jalisco", "", "Guadalajara", "MX", 20.7050, -103.3280, "open", "Liga MX"),
        ("Estadio BBVA", "Estadio Monterrey;Monterrey Stadium", "Guadalupe", "MX", 25.6690, -100.2446, "open", "Liga MX; WC 2026"),
        ("Estadio Universitario", "Estadio Universitario UANL", "San Nicolás de los Garza", "MX", 25.7224, -100.3120, "open", "Liga MX"),
        ("Estadio Nemesio Díez", "", "Toluca", "MX", 19.2871, -99.6668, "open", "Liga MX (2,660 m)"),
        ("Estadio Corona", "TSM Corona", "Torreón", "MX", 25.5500, -103.4000, "open", "Liga MX (city-level location)"),
        ("Estadio Hidalgo", "", "Pachuca", "MX", 20.1050, -98.7560, "open", "Liga MX"),
        ("Estadio León", "Nou Camp", "León", "MX", 21.1130, -101.6640, "open", "Liga MX"),
        ("Estadio Victoria", "", "Aguascalientes", "MX", 21.8810, -102.2760, "open", "Liga MX"),
        ("Estadio Caliente", "", "Tijuana", "MX", 32.5070, -117.0090, "open", "Liga MX"),
        ("Estadio Cuauhtémoc", "", "Puebla", "MX", 19.0780, -98.1620, "open", "Liga MX"),
        ("Estadio Corregidora", "", "Querétaro", "MX", 20.5780, -100.3660, "open", "Liga MX"),
        ("Estadio Alfonso Lastras", "", "San Luis Potosí", "MX", 22.1400, -101.0000, "open", "Liga MX (city-level location)"),
        ("Estadio Olímpico Benito Juárez", "", "Ciudad Juárez", "MX", 31.7100, -106.4300, "open", "Liga MX (city-level location)"),
        ("Estadio El Encanto", "Estadio Kraken", "Mazatlán", "MX", 23.2600, -106.4200, "open", "Liga MX 2020-25 (city-level location)"),
        ("Estadio Morelos", "", "Morelia", "MX", 19.7200, -101.2200, "open", "Liga MX to 2020 (city-level location)"),
        # ---- Brasileirão
        ("Maracanã", "Estádio do Maracanã", "Rio de Janeiro", "BR", -22.9122, -43.2302, "open", "Série A"),
        ("São Januário", "", "Rio de Janeiro", "BR", -22.8910, -43.2280, "open", "Série A"),
        ("Estádio Nilton Santos", "Engenhão", "Rio de Janeiro", "BR", -22.8932, -43.2922, "open", "Série A"),
        ("Allianz Parque", "", "São Paulo", "BR", -23.5275, -46.6784, "open", "Série A"),
        ("Neo Química Arena", "Arena Corinthians", "São Paulo", "BR", -23.5453, -46.4742, "open", "Série A"),
        ("Morumbi", "MorumBIS;Estádio do Morumbi", "São Paulo", "BR", -23.6000, -46.7203, "open", "Série A"),
        ("Vila Belmiro", "", "Santos", "BR", -23.9510, -46.3390, "open", "Série A"),
        ("Nabi Abi Chedid", "", "Bragança Paulista", "BR", -22.9520, -46.5430, "open", "Série A"),
        ("Ligga Arena", "Arena da Baixada", "Curitiba", "BR", -25.4482, -49.2769, "retractable", "Série A"),
        ("Couto Pereira", "", "Curitiba", "BR", -25.4210, -49.2590, "open", "Série A"),
        ("Arena do Grêmio", "", "Porto Alegre", "BR", -29.9740, -51.1950, "open", "Série A"),
        ("Beira-Rio", "Estádio Beira-Rio", "Porto Alegre", "BR", -30.0655, -51.2358, "open", "Série A"),
        ("Alfredo Jaconi", "", "Caxias do Sul", "BR", -29.1600, -51.1900, "open", "Série A (city-level location)"),
        ("Mineirão", "", "Belo Horizonte", "BR", -19.8659, -43.9711, "open", "Série A"),
        ("Arena MRV", "", "Belo Horizonte", "BR", -19.9400, -44.0100, "open", "Série A 2023-"),
        ("Independência", "", "Belo Horizonte", "BR", -19.9080, -43.9180, "open", "Série A"),
        ("Arena Fonte Nova", "", "Salvador", "BR", -12.9787, -38.5043, "open", "Série A"),
        ("Barradão", "", "Salvador", "BR", -12.9200, -38.4300, "open", "Série A"),
        ("Ilha do Retiro", "", "Recife", "BR", -8.0630, -34.9030, "open", "Série A"),
        ("Castelão", "Arena Castelão", "Fortaleza", "BR", -3.8071, -38.5224, "open", "Série A"),
        ("Estádio Hailé Pinheiro", "Serrinha", "Goiânia", "BR", -16.7000, -49.2500, "open", "Série A (city-level location)"),
        ("Antônio Accioly", "", "Goiânia", "BR", -16.6700, -49.2500, "open", "Série A (city-level location)"),
        ("Arena Pantanal", "", "Cuiabá", "BR", -15.6040, -56.1210, "open", "Série A"),
        ("Arena Condá", "", "Chapecó", "BR", -27.1000, -52.6200, "open", "Série A (city-level location)"),
        ("Ressacada", "", "Florianópolis", "BR", -27.6690, -48.5460, "open", "Série A"),
        ("Heriberto Hülse", "", "Criciúma", "BR", -28.6800, -49.3700, "open", "Série A (city-level location)"),
        ("Estádio José Maria de Campos Maia", "", "Mirassol", "BR", -20.8200, -49.5200, "open", "Série A 2025- (city-level location)"),
        ("Mangueirão", "Estádio Olímpico do Pará", "Belém", "BR", -1.3900, -48.4500, "open", "Série A 2026- (city-level location)"),
        ("Baenão", "", "Belém", "BR", -1.4400, -48.4700, "open", "Série A 2026- (city-level location)"),
        # ---- J1 League
        ("Kashima Soccer Stadium", "Mercari Stadium", "Kashima", "JP", 35.9920, 140.6410, "open", "J1"),
        ("Sankyo Frontier Kashiwa Stadium", "", "Kashiwa", "JP", 35.8490, 139.9750, "open", "J1"),
        ("Saitama Stadium 2002", "", "Saitama", "JP", 35.9030, 139.7180, "open", "J1"),
        ("Ajinomoto Stadium", "", "Chofu", "JP", 35.6640, 139.5270, "open", "J1"),
        ("Todoroki Athletics Stadium", "Uvance Todoroki Stadium", "Kawasaki", "JP", 35.5860, 139.6520, "open", "J1"),
        ("Nissan Stadium Yokohama", "Nissan Stadium", "Yokohama", "JP", 35.5100, 139.6060, "open", "J1"),
        ("NHK Spring Mitsuzawa Football Stadium", "", "Yokohama", "JP", 35.4690, 139.6040, "open", "J1"),
        ("Lemon Gas Stadium Hiratsuka", "", "Hiratsuka", "JP", 35.3450, 139.3410, "open", "J1"),
        ("Machida GION Stadium", "", "Machida", "JP", 35.5930, 139.4440, "open", "J1 2024-"),
        ("IAI Stadium Nihondaira", "", "Shizuoka", "JP", 35.0140, 138.4820, "open", "J1"),
        ("Yamaha Stadium", "", "Iwata", "JP", 34.7260, 137.8480, "open", "J1"),
        ("Toyota Stadium Japan", "Toyota Stadium", "Toyota", "JP", 35.0850, 137.1700, "retractable", "J1"),
        ("Paloma Mizuho Stadium", "", "Nagoya", "JP", 35.1210, 136.9450, "open", "J1"),
        ("Panasonic Stadium Suita", "", "Suita", "JP", 34.8030, 135.5380, "open", "J1"),
        ("Yodoko Sakura Stadium", "", "Osaka", "JP", 34.6140, 135.5180, "open", "J1"),
        ("Noevir Stadium Kobe", "", "Kobe", "JP", 34.6570, 135.1690, "retractable", "J1"),
        ("Sanga Stadium by Kyocera", "", "Kameoka", "JP", 35.0100, 135.5700, "open", "J1 2022- (city-level location)"),
        ("Edion Stadium Hiroshima", "Hiroshima Big Arch", "Hiroshima", "JP", 34.4400, 132.3950, "open", "J1 to 2023"),
        ("Edion Peace Wing Hiroshima", "", "Hiroshima", "JP", 34.4010, 132.4530, "open", "J1 2024-"),
        ("Best Denki Stadium", "", "Fukuoka", "JP", 33.5860, 130.4610, "open", "J1"),
        ("Ekimae Real Estate Stadium", "", "Tosu", "JP", 33.3720, 130.5200, "open", "J1"),
        ("Resonac Dome Oita", "", "Oita", "JP", 33.2010, 131.6570, "retractable", "J1"),
        ("Yurtec Stadium Sendai", "", "Sendai", "JP", 38.3190, 140.8820, "open", "J1"),
        ("Sapporo Dome", "Daiwa House Premist Dome", "Sapporo", "JP", 43.0150, 141.4100, "dome", "J1"),
        ("Sapporo Atsubetsu Park Stadium", "", "Sapporo", "JP", 43.0410, 141.4770, "open", "J1"),
        ("Pocarisweat Stadium", "", "Naruto", "JP", 34.2100, 134.5800, "open", "J1 2021 (city-level location)"),
        ("Denka Big Swan Stadium", "", "Niigata", "JP", 37.8800, 139.0590, "open", "J1"),
        ("JFE Harenokuni Stadium", "", "Okayama", "JP", 34.6700, 133.9190, "open", "J1 2025-"),
        ("Japan National Stadium", "", "Tokyo", "JP", 35.6780, 139.7150, "open", "J1 (occasional)"),
        ("Peace Stadium Connected by SoftBank", "", "Nagasaki", "JP", 32.7500, 129.8700, "open", "J1 if promoted (city-level location)"),
        ("Ks Denki Stadium Mito", "", "Mito", "JP", 36.3700, 140.4700, "open", "J1 if promoted (city-level location)"),
        # ---- K League 1
        ("Jeonju World Cup Stadium", "", "Jeonju", "KR", 35.8680, 127.0640, "open", "K League 1"),
        ("Ulsan Munsu Football Stadium", "", "Ulsan", "KR", 35.5350, 129.2590, "open", "K League 1"),
        ("Pohang Steel Yard", "", "Pohang", "KR", 36.0000, 129.3800, "open", "K League 1 (city-level location)"),
        ("Seoul World Cup Stadium", "", "Seoul", "KR", 37.5683, 126.8972, "open", "K League 1"),
        ("Suwon World Cup Stadium", "", "Suwon", "KR", 37.2866, 127.0369, "open", "K League 1"),
        ("Suwon Sports Complex", "", "Suwon", "KR", 37.2980, 127.0110, "open", "K League 1"),
        ("DGB Daegu Bank Park", "", "Daegu", "KR", 35.8810, 128.5880, "open", "K League 1"),
        ("Incheon Football Stadium", "", "Incheon", "KR", 37.4660, 126.6430, "open", "K League 1"),
        ("Chuncheon Songam Stadium", "", "Chuncheon", "KR", 37.8500, 127.7100, "open", "K League 1 (city-level location)"),
        ("Gangneung Stadium", "", "Gangneung", "KR", 37.7700, 128.9000, "open", "K League 1 (city-level location)"),
        ("Tancheon Sports Complex", "", "Seongnam", "KR", 37.4070, 127.1210, "open", "K League 1"),
        ("Busan Asiad Main Stadium", "", "Busan", "KR", 35.1900, 129.0590, "open", "K League 1 2020"),
        ("Sangju Civic Stadium", "", "Sangju", "KR", 36.4100, 128.1600, "open", "K League 1 2020 (city-level location)"),
        ("Gimcheon Sports Complex", "", "Gimcheon", "KR", 36.1300, 128.1100, "open", "K League 1 (city-level location)"),
        ("Gwangju Football Stadium", "", "Gwangju", "KR", 35.1340, 126.8750, "open", "K League 1"),
        ("Jeju World Cup Stadium", "", "Seogwipo", "KR", 33.2460, 126.5090, "open", "K League 1"),
        ("Daejeon World Cup Stadium", "", "Daejeon", "KR", 36.3650, 127.3250, "open", "K League 1 2023-"),
        ("Anyang Sports Complex", "", "Anyang", "KR", 37.4000, 126.9500, "open", "K League 1 2025- (city-level location)"),
        # ---- Euro 2024 (openfootball has no stadium file for it)
        ("Olympiastadion Berlin", "Berlin", "Berlin", "DE", 52.5147, 13.2395, "covered", "Euro 2024"),
        ("Allianz Arena", "München;Munich", "Munich", "DE", 48.2188, 11.6247, "covered", "Euro 2024"),
        ("Signal Iduna Park", "Dortmund", "Dortmund", "DE", 51.4926, 7.4519, "covered", "Euro 2024"),
        ("MHPArena", "Stuttgart", "Stuttgart", "DE", 48.7923, 9.2320, "covered", "Euro 2024"),
        ("Volksparkstadion", "Hamburg", "Hamburg", "DE", 53.5872, 9.8986, "covered", "Euro 2024"),
        ("Merkur Spiel-Arena", "Düsseldorf", "Düsseldorf", "DE", 51.2616, 6.7331, "retractable", "Euro 2024"),
        ("Veltins-Arena", "Gelsenkirchen", "Gelsenkirchen", "DE", 51.5546, 7.0676, "retractable", "Euro 2024"),
        ("Deutsche Bank Park", "Frankfurt", "Frankfurt", "DE", 50.0686, 8.6455, "retractable", "Euro 2024"),
        ("RheinEnergieStadion", "Köln;Cologne", "Cologne", "DE", 50.9336, 6.8752, "covered", "Euro 2024"),
        ("Red Bull Arena Leipzig", "Leipzig", "Leipzig", "DE", 51.3458, 12.3483, "covered", "Euro 2024"),
    ]


    def dms(s):
        """'25°39'08"N 51°29'16"E' or '37.403°N 121.970°W' -> (lat, lon)."""
        out = []
        for part in s.split():
            m = re.match(r"(\d+(?:\.\d+)?)°(?:(\d+)'(?:(\d+(?:\.\d+)?)\")?)?([NSEW])", part)
            d, mi, se, h = m.groups()
            v = float(d) + float(mi or 0) / 60 + float(se or 0) / 3600
            out.append(-v if h in "SW" else v)
        return out[0], out[1]


    rows = {}
    for name, aliases, city, cc, lat, lon, roof, used in M:
        rows[vid(name)] = dict(venue_id=vid(name), name=name, aliases=aliases, city=city, country=cc, lat=lat, lon=lon,
                               roof=roof, used_by=used, source="manual (verify on the Mac)")

    COOLED_2022 = {"Al Bayt Stadium", "Lusail Stadium", "Ahmad bin Ali Stadium", "Education City Stadium",
                   "Khalifa International Stadium", "Al Thumama Stadium", "Al Janoub Stadium"}
    by_alias = {}
    for r in rows.values():
        for a in [r["name"], *[x for x in r["aliases"].split(";") if x]]:
            by_alias[vid(a)] = r["venue_id"]
    wc_city = {}
    for year in ("2022", "2026"):
        st = json.load(open(SRC + f"of_worldcup.json/{year}/worldcup.stadiums.json"))["stadiums"]
        for s in st:
            lat, lon = dms(s["coords"])
            key = by_alias.get(vid(s["name"]))
            if key:                       # already in the manual table: keep ours, record the openfootball name
                r = rows[key]
                if s["name"] != r["name"] and s["name"] not in r["aliases"].split(";"):
                    r["aliases"] = ";".join(x for x in (r["aliases"], s["name"]) if x)
                r["used_by"] += f"; WC {year}" if f"WC {year}" not in r["used_by"] else ""
                wc_city[(year, s["city"])] = key
                continue
            roof = "cooled" if (year == "2022" and s["name"] in COOLED_2022) else "open"
            city = re.sub(r"\s*\(\d\)$", "", s["city"])
            cc = (s.get("cc") or ("qa" if year == "2022" else "")).upper()
            r = dict(venue_id=vid(s["name"]), name=s["name"], aliases="", city=city, country=cc, lat=round(lat, 4),
                     lon=round(lon, 4), roof=roof, used_by=f"WC {year}", source="openfootball (CC0)")
            rows[r["venue_id"]] = r
            by_alias[vid(s["name"])] = r["venue_id"]
            wc_city[(year, s["city"])] = r["venue_id"]

    with open(OUT + "soccer_venues.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["venue_id", "name", "aliases", "city", "country", "lat", "lon", "roof", "used_by", "source"])
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["country"], r["venue_id"])))
    print(len(rows), "venues")

    # ---- tournament fixtures: date, kickoff UTC, teams, venue. No scores (2026 is sealed).
    fx = []


    def utc(date, time, offset_h):
        t = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M") - timedelta(hours=offset_h)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")


    st22 = {s["name"]: s for s in json.load(open(SRC + "of_worldcup.json/2022/worldcup.stadiums.json"))["stadiums"]}
    for m in json.load(open(SRC + "of_worldcup.json/2022/worldcup.json"))["matches"]:
        ground = m["ground"].split(",")[0].strip().replace("Lusail Iconic Stadium", "Lusail Stadium")
        fx.append(dict(sport_key="soccer_fifa_world_cup", date=m["date"], kickoff_utc=utc(m["date"], m["time"], 3),
                       team1=m["team1"], team2=m["team2"], venue_id=by_alias[vid(ground)], ground=m["ground"]))
    st26 = json.load(open(SRC + "of_worldcup.json/2026/worldcup.stadiums.json"))["stadiums"]
    city26 = {s["city"]: s for s in st26}
    for m in json.load(open(SRC + "of_worldcup.json/2026/worldcup.json"))["matches"]:
        tm = re.match(r"(\d+:\d+)\s*UTC([+-]\d+)", m["time"])
        g = m["ground"]
        s = city26.get(g) or next(v for k, v in city26.items() if k.startswith(g) or g in k)
        fx.append(dict(sport_key="soccer_fifa_world_cup", date=m["date"], kickoff_utc=utc(m["date"], tm.group(1), int(tm.group(2))),
                       team1=m["team1"], team2=m["team2"], venue_id=by_alias[vid(s["name"])], ground=g))
    EURO = {"München": "allianz_arena", "Berlin": "olympiastadion_berlin", "Dortmund": "signal_iduna_park",
            "Stuttgart": "mhparena", "Hamburg": "volksparkstadion", "Düsseldorf": "merkur_spiel_arena",
            "Gelsenkirchen": "veltins_arena", "Frankfurt": "deutsche_bank_park", "Köln": "rheinenergiestadion",
            "Leipzig": "red_bull_arena_leipzig"}
    for m in json.load(open(SRC + "of_euro.json/2024/euro.json"))["matches"]:
        fx.append(dict(sport_key="soccer_uefa_european_championship", date=m["date"], kickoff_utc=utc(m["date"], m["time"], 2),
                       team1=m["team1"], team2=m["team2"], venue_id=EURO[m["ground"]], ground=m["ground"]))
    with open(OUT + "tournament_fixtures.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["sport_key", "date", "kickoff_utc", "team1", "team2", "venue_id", "ground"])
        w.writeheader()
        w.writerows(fx)
    print(len(fx), "fixtures", {k: sum(f["sport_key"] == k for f in fx) for k in {f["sport_key"] for f in fx}})


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        fetch_sources(Path(tmp))
        build_mlb(tmp + "/", str(HERE) + "/")
        build_soccer(tmp + "/", str(HERE) + "/")
