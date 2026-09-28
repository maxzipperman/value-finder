"""Turn Kalshi events + markets into canonical games, with rule-based exclusions and anomaly flags.

Pure functions (no I/O) so they are easy to test. Nothing is dropped: every market ends up either
in the analysis universe or in `exclusions` with a reason.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .settings import parse_ts
from .sport import SportConfig, Teams

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
EVENT_RE = re.compile(
    r"^(?P<series>[A-Z0-9]+)-(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<dd>\d{2})(?P<hhmm>\d{4})?(?P<tail>[A-Z]+?)(?P<gnum>G\d|\d)?$")


@dataclass
class Market:
    market_ticker: str
    game_id: str
    kalshi_suffix: str
    team_code: str | None
    yes_sub_title: str
    open_time: datetime
    close_time: datetime
    expected_expiration_time: datetime
    settlement_ts: datetime | None
    status: str
    result: str
    settlement_value: str | None
    volume: str | None
    endpoint: str


@dataclass
class Game:
    sport: str
    game_id: str
    series_ticker: str
    title: str
    game_date_et: date | None
    game_number: str | None
    away_kalshi: str | None
    home_kalshi: str | None
    away_code: str | None
    home_code: str | None
    kalshi_est_tip: datetime | None
    open_time: datetime | None
    close_time: datetime | None
    phase: str
    season: str | None
    split: str | None
    markets: list[Market] = field(default_factory=list)
    exclusions: list[tuple[str, str | None, str]] = field(default_factory=list)   # (reason, market_ticker|None=all, detail)
    anomalies: list[tuple[str, str | None, str]] = field(default_factory=list)    # (kind, market_ticker|None, detail)

    @property
    def excluded(self) -> bool:
        return any(m is None for _, m, _ in self.exclusions)


def build_games(cfg: SportConfig, teams: Teams, events: list[dict], markets: list[dict]) -> list[Game]:
    ev_by_ticker = {e["event_ticker"]: e for e in events}
    by_event: dict[str, list[dict]] = defaultdict(list)
    for m in markets:
        by_event[m["event_ticker"]].append(m)

    games = []
    for event_ticker, mks in sorted(by_event.items()):
        mks = sorted(mks, key=lambda m: m["ticker"])
        ev = ev_by_ticker.get(event_ticker, {})
        title = ev.get("title") or re.sub(r"\s*Winner\?$", "", mks[0].get("title") or "")
        g = Game(sport=cfg.sport, game_id=event_ticker, series_ticker=cfg.series_ticker, title=title,
                 game_date_et=None, game_number=None, away_kalshi=None, home_kalshi=None, away_code=None,
                 home_code=None, kalshi_est_tip=None, open_time=None, close_time=None,
                 phase="unknown", season=None, split=None)
        parsed = EVENT_RE.match(event_ticker)
        suffixes = [m["ticker"].rsplit("-", 1)[1] for m in mks]
        if parsed:
            g.game_date_et = date(2000 + int(parsed["yy"]), MONTHS[parsed["mon"]], int(parsed["dd"]))
            g.game_number = parsed["gnum"]
            tail = parsed["tail"]
            if len(suffixes) == 2:
                a, b = suffixes
                if tail == a + b:
                    g.away_kalshi, g.home_kalshi = a, b
                elif tail == b + a:
                    g.away_kalshi, g.home_kalshi = b, a
        if g.away_kalshi is None:
            g.exclusions.append(("malformed_event", None,
                                 f"cannot derive away/home from ticker tail and suffixes {suffixes}"))
        else:
            g.away_code, g.home_code = teams.from_kalshi(g.away_kalshi), teams.from_kalshi(g.home_kalshi)
            for raw, code in ((g.away_kalshi, g.away_code), (g.home_kalshi, g.home_code)):
                if code is None:
                    g.exclusions.append(("unknown_team_code", None, f"Kalshi code {raw!r} not in teams table"))

        exp = {m["expected_expiration_time"] for m in mks}
        if exp:
            g.kalshi_est_tip = parse_ts(min(exp)) - timedelta(hours=cfg.tip_offset_hours)
            if len(exp) > 1:
                g.anomalies.append(("est_tip_mismatch", None, f"markets disagree on expected_expiration_time: {sorted(exp)}"))
        g.open_time = min(parse_ts(m["open_time"]) for m in mks)
        g.close_time = max(parse_ts(m["close_time"]) for m in mks)

        if g.game_date_et is not None:
            g.phase = cfg.phase_for(title, g.game_date_et)
            season = cfg.season_for(g.game_date_et)
            if season:
                g.season, g.split = season.label, season.split_for(g.game_date_et)
        if g.phase != "regular":
            g.exclusions.append((g.phase, None, f"title={title!r} date={g.game_date_et}"))

        for m in mks:
            suffix = m["ticker"].rsplit("-", 1)[1]
            mk = Market(
                market_ticker=m["ticker"], game_id=event_ticker, kalshi_suffix=suffix,
                team_code=teams.from_kalshi(suffix), yes_sub_title=m.get("yes_sub_title") or "",
                open_time=parse_ts(m["open_time"]), close_time=parse_ts(m["close_time"]),
                expected_expiration_time=parse_ts(m["expected_expiration_time"]),
                settlement_ts=parse_ts(m.get("settlement_ts")), status=m.get("status") or "",
                result=m.get("result") or "", settlement_value=m.get("settlement_value_dollars"),
                volume=m.get("volume_fp"), endpoint=m["_endpoint"])
            g.markets.append(mk)
            lifetime_days = (mk.close_time - mk.open_time).total_seconds() / 86400
            if lifetime_days > cfg.lifetime_flag_days:
                g.anomalies.append(("lifetime_gt_flag", mk.market_ticker, f"{lifetime_days:.1f} days open"))
            if mk.result == "scalar":
                g.exclusions.append(("scalar_settlement", mk.market_ticker,
                                     f"settled at {mk.settlement_value} (postponed/cancelled game)"))
                g.anomalies.append(("scalar_settlement", mk.market_ticker, f"settlement_value={mk.settlement_value}"))
        if len(mks) != 2:
            g.exclusions.append(("malformed_event", None, f"{len(mks)} markets (expected 2)"))
        games.append(g)
    return games


def apply_cup_calendar(games: list[Game], cup_rows: list[dict]) -> None:
    """Flag NBA Cup games; the Cup final is not a regular-season game and is excluded."""
    # Unordered team pair: knockout games are at neutral sites, so home/away can differ between sources.
    index = {(r["game_date_et"], frozenset((r["away_code"], r["home_code"]))): r for r in cup_rows}
    for g in games:
        r = index.get((str(g.game_date_et), frozenset((g.away_code, g.home_code))))
        if r is None:
            continue
        g.anomalies.append(("nba_cup_game", None, r.get("cup_round", "")))
        if r.get("cup_round") == "final":
            g.exclusions.append(("cup_final", None, "NBA Cup championship (not a regular-season game)"))


def select_games(games: list[Game], start: date, end: date, *, include_excluded: bool = False) -> list[Game]:
    return [g for g in games
            if g.game_date_et is not None and start <= g.game_date_et <= end
            and (include_excluded or not g.excluded)]
