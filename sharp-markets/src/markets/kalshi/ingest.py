"""Kalshi ingestion: discovery, candles (chunked under the 5,000 cap), trades. All cache-first."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..games import Game
from ..settings import parse_ts
from ..sport import SportConfig
from .client import MAX_CANDLES_PER_REQUEST, KalshiClient

log = logging.getLogger(__name__)
CHUNK_PERIODS = MAX_CANDLES_PER_REQUEST - 100   # safety margin under the cap


@dataclass
class Discovery:
    events: list[dict]
    markets: list[dict]          # each has "_endpoint": historical|live
    cutoff: dict
    series: dict
    series_fee_changes: list[dict]


def discover(client: KalshiClient, cfg: SportConfig, as_of: str) -> Discovery:
    cutoff = client.historical_cutoff(as_of)
    series = client.series(cfg.series_ticker, as_of)
    fee_changes = client.series_fee_changes(cfg.series_ticker, as_of)
    events = client.events(cfg.series_ticker, as_of)
    hist = client.markets(cfg.series_ticker, historical=True, as_of=as_of)
    live = client.markets(cfg.series_ticker, historical=False, as_of=as_of)
    markets: dict[str, dict] = {}
    for m in live:
        markets[m["ticker"]] = {**m, "_endpoint": "live"}
    for m in hist:   # a market listed in both places is routed to /historical
        markets[m["ticker"]] = {**m, "_endpoint": "historical"}
    return Discovery(events, list(markets.values()), cutoff, series, fee_changes)


def floor_minute(ts: datetime) -> int:
    return int(ts.timestamp()) // 60 * 60


def ceil_minute(ts: datetime) -> int:
    return -(-int(ts.timestamp()) // 60) * 60


def candle_windows(start_ts: int, end_ts: int, period_min: int, max_periods: int = CHUNK_PERIODS) -> list[tuple[int, int]]:
    """Contiguous, non-overlapping [start, end] windows, each spanning fewer than max_periods candles."""
    if end_ts < start_ts:
        return []
    span = max_periods * period_min * 60
    out, s = [], start_ts
    while s <= end_ts:
        e = min(s + span - 1, end_ts)
        out.append((s, e))
        s = e + 1
    return out


def market_window(cfg: SportConfig, game: Game, market) -> tuple[int, int]:
    """Pre-game window: market open -> est tip + fetch_after_tip_min (never past close)."""
    end = min(market.close_time, game.kalshi_est_tip + timedelta(minutes=cfg.fetch_after_tip_min))
    return floor_minute(market.open_time), ceil_minute(end)


def fetch_candles(client: KalshiClient, cfg: SportConfig, games: list[Game]) -> int:
    n = 0
    for g in games:
        for m in g.markets:
            start, end = market_window(cfg, g, m)
            for s, e in candle_windows(start, end, cfg.candle_period_min):
                n += len(client.candles(market_ticker=m.market_ticker, series_ticker=cfg.series_ticker,
                                        start_ts=s, end_ts=e, period_min=cfg.candle_period_min,
                                        historical=m.endpoint == "historical", data_date=str(g.game_date_et)))
    return n


def fetch_trades(client: KalshiClient, cfg: SportConfig, games: list[Game], cutoff: dict) -> int:
    """Trades before `trades_created_ts` live under /historical/trades; later ones under /markets/trades."""
    trades_cutoff = int(parse_ts(cutoff["trades_created_ts"]).timestamp())
    n = 0
    for g in games:
        for m in g.markets:
            start, end = market_window(cfg, g, m)
            spans = []
            if start < trades_cutoff:
                spans.append((True, start, min(end, trades_cutoff - 1)))
            if end >= trades_cutoff:
                spans.append((False, max(start, trades_cutoff), end))
            for historical, s, e in spans:
                n += len(client.trades(market_ticker=m.market_ticker, min_ts=s, max_ts=e,
                                       historical=historical, data_date=str(g.game_date_et)))
    return n


def fetch_event_fees(client: KalshiClient, games: list[Game], as_of: str) -> int:
    return sum(len(client.event_fee_changes(g.game_id, str(g.game_date_et), as_of)) for g in games)
