"""Team box scores (official-stat conventions) and advanced metrics from
nflverse play-by-play. Validated against official box scores, e.g. Houston
vs Jacksonville 2012-11-18: 43/55, 527 yds, 5 TD, 2 INT.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RAW

COLS = [
    "game_id", "season", "posteam", "defteam", "posteam_type", "play_type", "desc",
    "down", "two_point_attempt", "pass_attempt", "rush_attempt", "complete_pass", "sack",
    "interception", "passing_yards", "rushing_yards", "yards_gained", "pass_touchdown",
    "rush_touchdown", "air_yards", "qb_dropback", "qb_scramble", "qb_kneel", "qb_spike",
    "epa", "success", "cpoe", "xpass", "pass_oe", "fumbled_1_team", "fumbled_2_team",
    "fumble_lost", "penalty", "penalty_team", "field_goal_attempt", "field_goal_result",
    "kick_distance", "extra_point_attempt", "extra_point_result", "punt_attempt",
    "kicker_player_id", "kicker_player_name", "weather", "qtr", "score_differential",
    "home_team", "away_team",
]


def passer_rating(cmp, att, yds, td, ints):
    att = np.where(att > 0, att, np.nan)
    clip = lambda x: np.clip(x, 0, 2.375)
    a = clip((cmp / att - 0.3) * 5)
    b = clip((yds / att - 3) * 0.25)
    c = clip(td / att * 20)
    d = clip(2.375 - ints / att * 25)
    return (a + b + c + d) / 6 * 100


def load_pbp(season):
    p = pd.read_parquet(RAW / "pbp" / f"play_by_play_{season}.parquet",
                        columns=[c for c in COLS if c != "season"] + ["season"])
    return p


def team_game_stats(p: pd.DataFrame) -> pd.DataFrame:
    scrim = p.play_type.isin(["pass", "run", "qb_spike", "qb_kneel"]) & (p.two_point_attempt != 1)
    s = p[scrim].copy()
    s["att"] = ((s.pass_attempt == 1) & (s.sack != 1)).astype(int)
    s["cmp"] = (s.complete_pass == 1).astype(int)
    s["pyds"] = s.passing_yards.fillna(0).where(s.cmp == 1, 0)
    s["sk"] = (s.sack == 1).astype(int)
    s["sk_yds"] = s.yards_gained.fillna(0).where(s.sk == 1, 0)
    s["ryds"] = s.rushing_yards.fillna(0).where(s.rush_attempt == 1, 0)
    s["deep"] = (s.air_yards >= 20).astype(float).where((s.att == 1) & s.air_yards.notna())
    # dropbacks and designed runs for EPA / success
    s["db"] = ((s.qb_dropback == 1) & s.play_type.isin(["pass", "run"])).astype(int)
    s["designed_run"] = ((s.play_type == "run") & (s.qb_scramble != 1)).astype(int)
    s["epa_db"] = s.epa.where(s.db == 1)
    s["epa_run"] = s.epa.where(s.designed_run == 1)
    s["succ_db"] = s.success.where(s.db == 1)
    s["succ_run"] = s.success.where(s.designed_run == 1)
    s["epa_play"] = s.epa.where(s.play_type.isin(["pass", "run"]))
    s["aya"] = s.air_yards.where(s.att == 1)
    s["cpoe_"] = s.cpoe.where(s.att == 1)
    s["pass_oe_"] = s.pass_oe.where(s.play_type.isin(["pass", "run"]))
    s["xpass_"] = s.xpass.where(s.pass_oe_.notna())
    s["pass_"] = s.qb_dropback.where(s.pass_oe_.notna())

    g = s.groupby(["game_id", "posteam_type"])
    out = g.agg(
        team=("posteam", "first"), pass_att=("att", "sum"), cmp=("cmp", "sum"),
        pass_yds=("pyds", "sum"), pass_td=("pass_touchdown", "sum"), ints=("interception", "sum"),
        sacks=("sk", "sum"), sack_yds=("sk_yds", "sum"), rush_att=("rush_attempt", "sum"),
        rush_yds=("ryds", "sum"), rush_td=("rush_touchdown", "sum"), dropbacks=("db", "sum"),
        epa_db=("epa_db", "mean"), epa_run=("epa_run", "mean"), epa_play=("epa_play", "mean"),
        succ_db=("succ_db", "mean"), succ_run=("succ_run", "mean"), adot=("aya", "mean"),
        deep_rate=("deep", "mean"), cpoe=("cpoe_", "mean"), proe=("pass_oe_", "mean"),
        xpass=("xpass_", "mean"), pass_rate_sit=("pass_", "mean"),
    ).reset_index()

    # fumbles (any play, credited to the fumbling team), penalties (accepted, on the team)
    f1 = p[p.fumbled_1_team.notna()][["game_id", "fumbled_1_team", "fumble_lost"]].rename(columns={"fumbled_1_team": "team"})
    f2 = p[p.fumbled_2_team.notna()][["game_id", "fumbled_2_team"]].rename(columns={"fumbled_2_team": "team"}).assign(fumble_lost=0)
    fum = pd.concat([f1, f2]).groupby(["game_id", "team"]).agg(fumbles=("team", "size"), fumbles_lost=("fumble_lost", "sum")).reset_index()
    pen = p[(p.penalty == 1) & p.penalty_team.notna() & ~p.desc.fillna("").str.contains("declined", case=False)]
    pen = pen.groupby(["game_id", "penalty_team"]).size().rename("penalties").reset_index().rename(columns={"penalty_team": "team"})

    out = out.merge(fum, on=["game_id", "team"], how="left").merge(pen, on=["game_id", "team"], how="left")
    for c in ["fumbles", "fumbles_lost", "penalties"]:
        out[c] = out[c].fillna(0)
    out["turnovers"] = out.ints + out.fumbles_lost
    out["net_pass_yds"] = out.pass_yds + out.sack_yds
    out["total_yds"] = out.net_pass_yds + out.rush_yds
    out["qbr"] = passer_rating(out.cmp, out.pass_att, out.pass_yds, out.pass_td, out.ints)
    out["cmp_pct"] = out.cmp / out.pass_att.replace(0, np.nan)
    out["yds_per_cmp"] = out.pass_yds / out.cmp.replace(0, np.nan)
    out["ypa"] = out.pass_yds / out.pass_att.replace(0, np.nan)
    out["rush_pct"] = out.rush_att / (out.rush_att + out.pass_att).replace(0, np.nan)
    out["rush_ypa"] = out.rush_yds / out.rush_att.replace(0, np.nan)
    out["int_rate"] = out.ints / out.pass_att.replace(0, np.nan)
    out["sack_rate"] = out.sacks / (out.pass_att + out.sacks).replace(0, np.nan)
    out["plays"] = out.pass_att + out.sacks + out.rush_att
    out = out.rename(columns={"posteam_type": "side"})
    return out


def kicks(p: pd.DataFrame) -> pd.DataFrame:
    fg = p[p.field_goal_attempt == 1][["game_id", "season", "posteam", "posteam_type", "qtr", "score_differential",
                                       "kick_distance", "field_goal_result", "kicker_player_id", "kicker_player_name"]].copy()
    fg["kind"] = "fg"
    fg["made"] = (fg.field_goal_result == "made").astype(int)
    xp = p[p.extra_point_attempt == 1][["game_id", "season", "posteam", "posteam_type", "qtr", "score_differential",
                                        "kick_distance", "extra_point_result", "kicker_player_id", "kicker_player_name"]].copy()
    xp["kind"] = "xp"
    xp["made"] = (xp.extra_point_result == "good").astype(int)
    k = pd.concat([fg.drop(columns="field_goal_result"), xp.drop(columns="extra_point_result")], ignore_index=True)
    return k.rename(columns={"posteam_type": "side"})


def gamebook_weather(p: pd.DataFrame) -> pd.DataFrame:
    return p.groupby("game_id").weather.first().reset_index()
