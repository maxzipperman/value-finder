"""Match Kalshi games to Odds API events: unordered team pair + nearest commence_time, one-to-one."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class OddsEvent:
    odds_event_id: str
    home_code: str | None
    away_code: str | None
    commence_time: datetime              # as of the latest snapshot that listed the event
    commence_min: datetime
    commence_max: datetime


@dataclass
class Match:
    game_id: str
    odds_event_id: str
    commence_time: datetime
    tip_diff_min: float
    home_away_swapped: bool
    commence_changed: bool


def match_games(games: list[tuple[str, str, str, datetime]], events: list[OddsEvent],
                window: timedelta = timedelta(hours=18)) -> tuple[dict[str, Match], list[tuple[str, str]]]:
    """games: (game_id, away_code, home_code, kalshi_est_tip). Returns ({game_id: Match}, conflicts)."""
    cands = []
    for gid, away, home, est in games:
        pair = frozenset((away, home))
        for ev in events:
            if frozenset((ev.away_code, ev.home_code)) != pair:
                continue
            diff = ev.commence_time - est
            if abs(diff) <= window:
                cands.append((abs(diff), gid, away, ev, diff))
    cands.sort(key=lambda c: (c[0], c[1], c[3].odds_event_id))
    matched: dict[str, Match] = {}
    used: dict[str, str] = {}
    conflicts = []
    for _, gid, away, ev, diff in cands:
        if gid in matched:
            continue
        if ev.odds_event_id in used:
            conflicts.append((gid, f"odds event {ev.odds_event_id} already matched to {used[ev.odds_event_id]}"))
            continue
        matched[gid] = Match(gid, ev.odds_event_id, ev.commence_time, diff.total_seconds() / 60,
                             home_away_swapped=ev.away_code != away,
                             commence_changed=ev.commence_min != ev.commence_max)
        used[ev.odds_event_id] = gid
    conflicts = [c for c in conflicts if c[0] not in matched]
    return matched, conflicts
