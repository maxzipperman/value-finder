"""Assemble analysis datasets:

data/processed/games.parquet       one row per game: weather, lines, results
data/processed/team_games.parquet  two rows per game (offense perspective)
data/processed/kicks.parquet       every FG / XP attempt with game weather
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import boxscore
from .config import RAW, PROC, FIRST_SEASON, DOME_TEMP, DOME_WIND
from .stadiums import STADIUMS, resolve_stadium
from .weather import game_weather, parse_gamebook_weather, previous_forecasts, wind_chill

FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


def load_schedule():
    g = pd.read_csv(RAW / "games.csv")
    g["stadium_key"] = [resolve_stadium(a, b) for a, b in zip(g.stadium_id, g.stadium)]
    g["lat"] = g.stadium_key.map(lambda k: STADIUMS.get(k, (None, np.nan))[1])
    g["lon"] = g.stadium_key.map(lambda k: STADIUMS.get(k, (None, None, np.nan))[2])
    g["neutral"] = (g.location == "Neutral").astype(int)
    g["playoff"] = (g.game_type != "REG").astype(int)
    g["date"] = pd.to_datetime(g.gameday)
    g["kick_hour"] = g.gametime.str.slice(0, 2).astype(float) + g.gametime.str.slice(3, 5).astype(float) / 60
    return g


def _practice_temps():
    """Daily GHCN-D highs/lows by station -> trailing 7-day means (days -7..-1)
    of the daily high (tmax7) and of the daily mean, (high+low)/2 (tavg7)."""
    frames = []
    for f in (RAW / "weather" / "ghcnd").glob("*.csv"):
        d = pd.read_csv(f, usecols=["DATE", "TMAX", "TMIN"])
        d["DATE"] = pd.to_datetime(d.DATE)
        d = d.set_index("DATE").asfreq("D")
        d["station"] = f.stem
        d["tmax7"] = d.TMAX.shift(1).rolling(7, min_periods=4).mean()
        d["tavg7"] = ((d.TMAX + d.TMIN) / 2).shift(1).rolling(7, min_periods=4).mean()
        frames.append(d.reset_index()[["station", "DATE", "tmax7", "tavg7"]])
    return pd.concat(frames).rename(columns={"DATE": "date"})


def team_climate(g):
    """Per team-season: primary home stadium, dome status, average home wind."""
    h = g[(g.location == "Home") & g.result.notna()]
    rows = []
    for (team, season), d in h.groupby(["home_team", "season"]):
        key = d.stadium_key.mode().iat[0]
        roof = d[d.stadium_key == key].roof.mode()
        roof = roof.iat[0] if len(roof) else "outdoors"
        outdoor = d[(d.roof == "outdoors") & d.wx_wind.notna()]
        rows.append(dict(team=team, season=season, home_stadium=key,
                         dome_team=int(roof in ("dome", "closed")),
                         # thesis definitions: only fixed domes count as "Dome"; retractable
                         # roofs are open-air with 0 mph imputed for games without weather
                         dome_fixed=int(roof == "dome"),
                         home_avg_wind=outdoor.wx_wind.mean() if len(outdoor) else np.nan,
                         home_avg_wind_th=d.th_wind.mean(),
                         station=STADIUMS.get(key, (None,) * 4)[3]))
    return pd.DataFrame(rows)


def build(seasons=None, verbose=True):
    g = load_schedule()
    cur = int(g.loc[g.result.notna(), "season"].max())
    seasons = list(seasons or range(FIRST_SEASON, cur + 1))

    # ---------------------------------------------------------------- weather
    g["gb_temp"], g["gb_wind"] = g.temp, g.wind
    om = game_weather(g)
    g = g.merge(om, on="game_id", how="left")
    fc = previous_forecasts(g)
    if len(fc):
        g = g.merge(fc, on="game_id", how="left")

    stats, kick_rows, gbw = [], [], []
    for s in seasons:
        p = boxscore.load_pbp(s)
        stats.append(boxscore.team_game_stats(p))
        kick_rows.append(boxscore.kicks(p))
        gbw.append(boxscore.gamebook_weather(p))
        if verbose:
            print(f"  pbp {s}: {p.game_id.nunique()} games", flush=True)
    stats = pd.concat(stats, ignore_index=True)
    kicks = pd.concat(kick_rows, ignore_index=True)
    gbw = pd.concat(gbw, ignore_index=True)
    gbw = pd.concat([gbw[["game_id"]], parse_gamebook_weather(gbw.weather)], axis=1)
    g = g.merge(gbw, on="game_id", how="left")

    # Calibrate ERA5 grid wind to game-book (stadium-reported) wind where both exist,
    # then use it only to fill games with no game-book reading.
    both = g[(g.roof == "outdoors") & g.gb_wind.notna() & g.om_wind.notna()]
    slope, intercept = np.polyfit(both.om_wind, both.gb_wind, 1)
    g.attrs["wind_calibration"] = (slope, intercept, np.corrcoef(both.om_wind, both.gb_wind)[0, 1], len(both))
    tb = both[["om_temp", "gb_temp"]].dropna()
    t_slope, t_int = np.polyfit(tb.om_temp, tb.gb_temp, 1)
    g["om_wind_cal"] = (intercept + slope * g.om_wind).clip(lower=0)
    g["om_temp_cal"] = t_int + t_slope * g.om_temp
    import json
    (PROC / "calibration.json").write_text(json.dumps(dict(
        wind_slope=slope, wind_intercept=intercept, temp_slope=t_slope, temp_intercept=t_int,
        wind_r=float(np.corrcoef(both.om_wind, both.gb_wind)[0, 1]), n=int(len(both)))))

    # Game-book wind typos (e.g. 2008 TEN@CIN listed at 70 mph; the game-book text
    # says 21 and ERA5 says 21). Replace a reading only when it disagrees with the
    # game-book text by >10 mph or is >=35 mph against a calm ERA5 reading, and pick
    # whichever alternative sits closer to ERA5. Every change is logged.
    ref = g.om_wind_cal
    suspect = g.gb_wind.notna() & (((g.gb_wind - g.gb_text_wind).abs() > 10) | ((g.gb_wind >= 35) & (ref < 18)))
    use_text = g.gb_text_wind.notna() & ((g.gb_text_wind - ref).abs().fillna(0) < (g.gb_wind - ref).abs().fillna(np.inf))
    fixed = np.where(use_text, g.gb_text_wind, np.where(ref.notna(), ref.round(), g.gb_wind))
    fix = suspect & (fixed != g.gb_wind)
    g.loc[fix, ["game_id", "gb_wind", "gb_text_wind", "om_wind_cal"]].assign(new_wind=fixed[fix]).to_csv(
        PROC / "wind_corrections.csv", index=False)
    g["gb_wind_raw"] = g.gb_wind
    g.loc[fix, "gb_wind"] = fixed[fix]

    outdoor = g.roof.eq("outdoors") | g.roof.isna()
    g["indoor"] = g.roof.isin(["dome", "closed"]).astype(int)
    g["roof_open"] = g.roof.eq("open").astype(int)
    g["wx_temp"] = np.where(outdoor, g.gb_temp.fillna(g.om_temp_cal), np.nan)
    g["wx_wind"] = np.where(outdoor, g.gb_wind.fillna(g.om_wind_cal), np.nan)
    g["wx_src"] = np.select([g.indoor == 1, g.roof_open == 1, g.gb_temp.notna(), g.om_temp.notna()],
                            ["indoor", "open_roof", "gamebook", "era5"], "missing")
    g["wx_precip"] = np.where(outdoor, g.om_precip, 0.0)
    g["wx_snow"] = np.where(outdoor, g.om_snow, 0.0)
    g["wx_gust"] = np.where(outdoor, g.om_gust_game, np.nan)
    g["wx_wchill"] = wind_chill(g.wx_temp, g.wx_wind)

    # thesis convention: games without weather (domes, closed/open retractables) are
    # 72F / 0 mph. Outdoor games missing a game-book reading (2022-23) use ERA5.
    g["th_temp"] = g.wx_temp.fillna(DOME_TEMP)
    g["th_wind"] = g.wx_wind.fillna(DOME_WIND)
    g["th_wchill"] = wind_chill(g.th_temp, g.th_wind)
    g["th_freezing"] = (g.th_wchill <= 32).astype(int)
    g["th_hot"] = (g.th_wchill >= 80).astype(int)

    # ---------------------------------------------------------------- climates
    tc = team_climate(g)
    pt = _practice_temps()
    g["season_key"] = g.season
    games = g

    # ---------------------------------------------------------------- long table
    sides = []
    for side, opp in (("home", "away"), ("away", "home")):
        d = games[["game_id", "season", "week", "game_type", "playoff", "date", "neutral",
                   f"{side}_team", f"{opp}_team", f"{side}_score", f"{opp}_score", f"{side}_rest", f"{opp}_rest"]].copy()
        d.columns = ["game_id", "season", "week", "game_type", "playoff", "date", "neutral",
                     "team", "opp", "pts", "pts_allowed", "rest", "opp_rest"]
        d["side"] = side
        d["home"] = int(side == "home")
        sides.append(d)
    tg = pd.concat(sides, ignore_index=True)
    tg = tg.merge(stats.drop(columns=["team"]), on=["game_id", "side"], how="inner")
    tg["franchise"] = tg.team.replace(FRANCHISE)
    tg["opp_franchise"] = tg.opp.replace(FRANCHISE)
    tg = tg.merge(tc, on=["team", "season"], how="left")

    # practice-climate temperature: trailing 7-day mean temperature at the team's
    # home station; dome teams get 72F (thesis convention). Raw city values kept.
    tg = tg.merge(pt, on=["station", "date"], how="left")
    tg["city_tavg7"], tg["city_tmax7"] = tg.tavg7, tg.tmax7
    tg["practice_temp"] = np.where(tg.dome_team == 1, DOME_TEMP, tg.tavg7)
    tg["practice_temp_th"] = np.where(tg.dome_fixed == 1, DOME_TEMP, tg.tavg7)
    tg = tg.drop(columns=["tmax7", "tavg7"])

    wx_cols = ["gb_temp", "gb_wind", "wx_temp", "wx_wind", "wx_wchill", "wx_precip", "wx_snow", "wx_gust",
               "wx_src", "indoor", "roof_open", "roof", "surface", "th_temp", "th_wind", "th_wchill",
               "th_freezing", "th_hot", "om_rh", "gb_rain", "gb_snow", "stadium_key", "div_game",
               "spread_line", "total_line"]
    tg = tg.merge(games[["game_id"] + wx_cols], on="game_id", how="left")

    kicks = kicks.merge(games[["game_id", "game_type", "week", "roof", "indoor", "roof_open", "wx_temp", "wx_wind",
                               "wx_wchill", "wx_precip", "wx_snow", "wx_gust", "wx_src", "gb_rain", "gb_snow",
                               "stadium_key", "surface"]], on="game_id", how="left")

    # opening/closing lines 2007-2021 (Sportsbook Reviews Online archive)
    sbr_path = RAW / "odds" / "sbr_open_close.parquet"
    if sbr_path.exists():
        from .odds import match_to_games
        games = games.merge(match_to_games(pd.read_parquet(sbr_path), games), on="game_id", how="left")

    games.to_parquet(PROC / "games.parquet", index=False)
    tg.to_parquet(PROC / "team_games.parquet", index=False)
    kicks.to_parquet(PROC / "kicks.parquet", index=False)
    if verbose:
        s, i, r, n = g.attrs["wind_calibration"]
        print(f"  wind calibration: gamebook = {i:.2f} + {s:.2f} * ERA5  (r={r:.2f}, n={n})")
        print(f"  games {len(games)}, team-games {len(tg)}, kicks {len(kicks)}")
    return games, tg, kicks
