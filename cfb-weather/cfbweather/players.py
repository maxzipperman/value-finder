"""CFB player-game stat lines for prop research, from cfbfastR's play-level player
records (one row per play with the passer, rusher, receiver and yards), 2014-2025.

Roles chosen without looking at the game's outcome (as in nfl-weather):
  QB   the passer on the team's first pass attempt of the game
  RB1  the non-QB with the most carries in the team's previous game
  WR1  the player with the most targets in the team's previous game
"""
from __future__ import annotations

import pandas as pd

from .config import PROC, RAW


def _season(season: int) -> pd.DataFrame:
    p = pd.read_parquet(RAW / "cfbfastr" / "player_stats" / f"player_stats_{season}.parquet")
    p = p.sort_values(["game_id", "play_id"])
    passer = p.completion_player_id.fillna(p.incompletion_player_id).fillna(p.interception_thrown_player_id)
    pname = p.completion_player.fillna(p.incompletion_player).fillna(p.interception_thrown_player)
    att = p.assign(player_id=passer, name=pname, cmp=p.completion_player_id.notna().astype(int),
                   yds=p.completion_yds.fillna(0))[passer.notna()]
    passing = att.groupby(["game_id", "team", "player_id"]).agg(name=("name", "first"), pass_att=("play_id", "size"),
                                                               cmp=("cmp", "sum"), pass_yds=("yds", "sum")).reset_index()
    ru = p[p.rush_player_id.notna()]
    rushing = ru.groupby(["game_id", "team", "rush_player_id"]).agg(name=("rush_player", "first"), rush_att=("play_id", "size"),
                                                                   rush_yds=("rush_yds", "sum")).reset_index()
    rushing = rushing.rename(columns={"rush_player_id": "player_id"})
    tg = p[p.target_player_id.notna()]
    targets = tg.groupby(["game_id", "team", "target_player_id"]).size().rename("targets").reset_index().rename(
        columns={"target_player_id": "player_id"})
    rc = p[p.reception_player_id.notna()]
    rec = rc.groupby(["game_id", "team", "reception_player_id"]).agg(name=("reception_player", "first"), rec=("play_id", "size"),
                                                                    rec_yds=("reception_yds", "sum")).reset_index()
    receiving = targets.merge(rec.rename(columns={"reception_player_id": "player_id"}), on=["game_id", "team", "player_id"], how="outer")
    # cfbfastR's target field records incomplete targets only; total targets = catches + incompletions
    receiving["targets"] = receiving.targets.fillna(0) + receiving.rec.fillna(0)

    first = att.drop_duplicates(["game_id", "team"])[["game_id", "team", "player_id"]]
    qb = first.merge(passing, on=["game_id", "team", "player_id"], how="left").assign(role="QB")

    order = p[["game_id", "team", "week", "season"]].drop_duplicates(["game_id", "team"]).sort_values(["team", "week", "game_id"])
    order["prev_game"] = order.groupby("team").game_id.shift(1)
    qbs = set(passing[passing.pass_att >= 5].player_id)

    def ex_ante(stats, key, role, cols):
        s = stats if role != "RB1" else stats[~stats.player_id.isin(qbs)]
        lead = s.sort_values(key, ascending=False).drop_duplicates(["game_id", "team"])[["game_id", "team", "player_id"]]
        cur = order.merge(lead.rename(columns={"game_id": "prev_game"}), on=["prev_game", "team"])[["game_id", "team", "player_id"]]
        cur = cur.merge(stats, on=["game_id", "team", "player_id"], how="left").fillna({c: 0 for c in cols})
        return cur.assign(role=role)

    rb = ex_ante(rushing, "rush_att", "RB1", ["rush_att", "rush_yds"])
    wr = ex_ante(receiving.fillna({"targets": 0, "rec": 0, "rec_yds": 0}), "targets", "WR1", ["targets", "rec", "rec_yds"])
    out = pd.concat([qb, rb, wr], ignore_index=True)
    out["season"] = season
    return out


def build(seasons=range(2014, 2026)) -> pd.DataFrame:
    pg = pd.concat([_season(s) for s in seasons], ignore_index=True)
    pg["game_id"] = pg.game_id.astype("int64")
    pg.to_parquet(PROC / "player_games.parquet", index=False)
    return pg
