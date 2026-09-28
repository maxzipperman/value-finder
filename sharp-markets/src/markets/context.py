"""Shared run context: config + cache + clients + discovered games."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import cached_property

from .cache import RawCache
from .games import Game, apply_cup_calendar, build_games
from .kalshi.client import KalshiClient
from .kalshi.ingest import Discovery, discover
from .settings import ROOT
from .sport import SportConfig, Teams, load_sport, load_teams


@dataclass
class Context:
    sport: str
    as_of: str = "v1"
    offline: bool = False

    @cached_property
    def cfg(self) -> SportConfig:
        return load_sport(self.sport)

    @cached_property
    def teams(self) -> Teams:
        return load_teams(self.sport)

    @cached_property
    def cache(self) -> RawCache:
        return RawCache(offline=self.offline)

    @cached_property
    def kalshi(self) -> KalshiClient:
        return KalshiClient(self.sport, self.cache)

    @cached_property
    def discovery(self) -> Discovery:
        return discover(self.kalshi, self.cfg, self.as_of)

    @cached_property
    def games(self) -> list[Game]:
        games = build_games(self.cfg, self.teams, self.discovery.events, self.discovery.markets)
        apply_cup_calendar(games, self.cup_rows)
        return games

    @cached_property
    def cup_rows(self) -> list[dict]:
        rows = []
        for season in self.cfg.seasons.values():
            if season.cup_calendar and (ROOT / season.cup_calendar).exists():
                with open(ROOT / season.cup_calendar, newline="") as fh:
                    rows += [r for r in csv.DictReader(fh) if not r["game_date_et"].startswith("#")]
        return rows
