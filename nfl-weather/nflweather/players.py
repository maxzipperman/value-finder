"""Player-game stat lines for prop research, from nflverse play-by-play.

Roles are chosen WITHOUT looking at the game's outcome, which is what a prop bettor
faces (a backup who replaces an injured starter must not flatter the results):

  QB   the passer on the team's first pass attempt of the game (the starter)
  RB1  the non-QB with the most designed-run carries in the team's previous game
  WR1  the player with the most targets in the team's previous game

Stat definitions follow sportsbook prop conventions: gross passing yards,
completions, attempts (spikes count, sacks don't); rush attempts include
scrambles and kneels; receiving yards on catches.
"""
from __future__ import annotations

import pandas as pd

from .config import PROC, RAW

COLS = ["game_id", "season", "week", "play_id", "posteam", "posteam_type", "play_type", "two_point_attempt", "sack",
        "pass_attempt", "complete_pass", "passing_yards", "passer_player_id", "passer_player_name", "rush_attempt",
        "rushing_yards", "rusher_player_id", "rusher_player_name", "qb_scramble", "receiver_player_id",
        "receiver_player_name", "receiving_yards"]


def _season(season: int) -> pd.DataFrame:
    p = pd.read_parquet(RAW / "pbp" / f"play_by_play_{season}.parquet", columns=COLS)
    p = p[p.play_type.isin(["pass", "run", "qb_spike", "qb_kneel"]) & (p.two_point_attempt != 1)].copy()
    p["side"] = p.posteam_type
    att = p[(p.pass_attempt == 1) & (p.sack != 1) & p.passer_player_id.notna()]
    passing = att.groupby(["game_id", "side", "passer_player_id"]).agg(
        name=("passer_player_name", "first"), pass_att=("pass_attempt", "size"), cmp=("complete_pass", "sum"),
        pass_yds=("passing_yards", lambda x: x.fillna(0).sum())).reset_index().rename(columns={"passer_player_id": "player_id"})
    rush = p[(p.rush_attempt == 1) & p.rusher_player_id.notna()]
    rushing = rush.groupby(["game_id", "side", "rusher_player_id"]).agg(
        name=("rusher_player_name", "first"), rush_att=("rush_attempt", "size"),
        rush_yds=("rushing_yards", lambda x: x.fillna(0).sum()),
        designed=("qb_scramble", lambda x: int((x != 1).sum()))).reset_index().rename(columns={"rusher_player_id": "player_id"})
    tgt = att[att.receiver_player_id.notna()]
    receiving = tgt.groupby(["game_id", "side", "receiver_player_id"]).agg(
        name=("receiver_player_name", "first"), targets=("pass_attempt", "size"), rec=("complete_pass", "sum"),
        rec_yds=("receiving_yards", lambda x: x.fillna(0).sum())).reset_index().rename(columns={"receiver_player_id": "player_id"})

    # starting QB: passer on the team's first pass attempt
    first = att.sort_values("play_id").drop_duplicates(["game_id", "side"])[["game_id", "side", "passer_player_id"]]
    qb = first.rename(columns={"passer_player_id": "player_id"}).merge(passing, on=["game_id", "side", "player_id"], how="left")
    qb = qb.fillna({"pass_att": 0, "cmp": 0, "pass_yds": 0})
    qb["role"] = "QB"

    # previous-game leaders (same season), matched to this game by team order
    order = p[["game_id", "season", "week", "posteam", "side"]].drop_duplicates().sort_values(["posteam", "week"])
    order["prev_game"] = order.groupby("posteam").game_id.shift(1)
    order["prev_side"] = order.groupby("posteam").side.shift(1)
    qbs = set(passing[passing.pass_att >= 5].player_id)

    def ex_ante(stats, key, role, cols):
        s = stats if role != "RB1" else stats[~stats.player_id.isin(qbs)]
        lead = s.sort_values(key, ascending=False).drop_duplicates(["game_id", "side"])[["game_id", "side", "player_id"]]
        lead = lead.rename(columns={"game_id": "prev_game", "side": "prev_side"})
        cur = order.merge(lead, on=["prev_game", "prev_side"])[["game_id", "side", "player_id"]]
        cur = cur.merge(stats, on=["game_id", "side", "player_id"], how="left").fillna({c: 0 for c in cols})
        cur["role"] = role
        return cur

    rb = ex_ante(rushing, "designed", "RB1", ["rush_att", "rush_yds"])
    wr = ex_ante(receiving, "targets", "WR1", ["targets", "rec", "rec_yds"])
    out = pd.concat([qb, rb, wr], ignore_index=True)
    out["season"] = season
    return out


def build(seasons=range(1999, 2026)) -> pd.DataFrame:
    pg = pd.concat([_season(s) for s in seasons], ignore_index=True)
    pg.to_parquet(PROC / "player_games.parquet", index=False)
    return pg
