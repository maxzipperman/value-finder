"""Sport configuration and team alias resolution (sport-agnostic)."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

import yaml

from .settings import CONFIG_DIR, to_date


@dataclass(frozen=True)
class Season:
    label: str
    events_from: date
    events_to: date
    regular_start: date
    regular_end: date
    train_end: date | None
    cup_calendar: str | None = None
    cup_scan_from: date | None = None
    cup_scan_to: date | None = None

    def split_for(self, game_date: date) -> str:
        if self.train_end is None:
            return "forward"
        return "train" if game_date <= self.train_end else "validate"


@dataclass(frozen=True)
class SportConfig:
    sport: str
    series_ticker: str
    tip_offset_hours: float
    fetch_after_tip_min: int
    candle_period_min: int
    odds_sport_key: str
    bookmakers: tuple[str, ...]
    odds_markets: str
    phase_title_rules: tuple[tuple[re.Pattern, str], ...]
    seasons: dict[str, Season] = field(default_factory=dict)
    lifetime_flag_days: float = 14
    tip_diff_flag_min: int = 30
    totals_series: str | None = None

    def season_for(self, game_date: date) -> Season | None:
        for s in self.seasons.values():
            if s.events_from <= game_date <= s.events_to:
                return s
        return None

    def phase_for(self, title: str, game_date: date) -> str:
        """Rule-based game phase: title rules first, then the season's date window."""
        for pattern, phase in self.phase_title_rules:
            if pattern.search(title or ""):
                return phase
        season = self.season_for(game_date)
        if season is None:
            return "unknown_season"
        if game_date < season.regular_start:
            return "preseason"
        if game_date > season.regular_end:
            return "postseason_window"
        return "regular"


@lru_cache
def load_sport(sport: str) -> SportConfig:
    raw = yaml.safe_load((CONFIG_DIR / "sports" / f"{sport}.yaml").read_text())
    seasons = {
        label: Season(
            label=label,
            events_from=to_date(s["events_from"]),
            events_to=to_date(s["events_to"]),
            regular_start=to_date(s["regular_start"]),
            regular_end=to_date(s["regular_end"]),
            train_end=to_date(s.get("train_end")),
            cup_calendar=s.get("cup_calendar"),
            cup_scan_from=to_date(s.get("cup_scan_from")),
            cup_scan_to=to_date(s.get("cup_scan_to")),
        )
        for label, s in (raw.get("seasons") or {}).items()
    }
    k, o, f = raw["kalshi"], raw["odds_api"], raw.get("flags", {})
    return SportConfig(
        sport=raw["sport"],
        series_ticker=k["series_ticker"],
        tip_offset_hours=float(k["tip_offset_hours"]),
        fetch_after_tip_min=int(k["fetch_after_tip_min"]),
        candle_period_min=int(k.get("candle_period_min", 1)),
        odds_sport_key=o["sport_key"],
        bookmakers=tuple(o["bookmakers"]),
        odds_markets=o.get("markets", "h2h"),
        phase_title_rules=tuple((re.compile(r["pattern"]), r["phase"]) for r in raw.get("phase_title_rules", [])),
        seasons=seasons,
        lifetime_flag_days=float(f.get("lifetime_flag_days", 14)),
        tip_diff_flag_min=int(f.get("tip_diff_flag_min", 30)),
        totals_series=k.get("totals_series"),
    )


@dataclass(frozen=True)
class Teams:
    """Canonical team codes plus every known alias. Unknown names return None (caller logs an anomaly)."""
    rows: tuple[dict, ...]
    by_kalshi: dict[str, str]
    by_name: dict[str, str]
    by_espn: dict[str, str]

    def from_kalshi(self, code: str) -> str | None:
        return self.by_kalshi.get((code or "").upper())

    def from_name(self, name: str) -> str | None:
        return self.by_name.get(_norm(name))

    def from_espn(self, code: str) -> str | None:
        return self.by_espn.get((code or "").upper())

    def name(self, code: str) -> str | None:
        return next((r["name"] for r in self.rows if r["code"] == code), None)


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


@lru_cache
def load_teams(sport: str) -> Teams:
    with open(CONFIG_DIR / "teams" / f"{sport}.csv", newline="") as fh:
        rows = tuple(csv.DictReader(fh))
    by_kalshi, by_name, by_espn = {}, {}, {}
    for r in rows:
        code = r["code"]
        for k in filter(None, r["kalshi_codes"].split("|")):
            by_kalshi[k.upper()] = code
        for e in filter(None, r["espn_codes"].split("|")):
            by_espn[e.upper()] = code
        for n in [r["name"], code, *filter(None, (r.get("aliases") or "").split("|"))]:
            key = _norm(n)
            if key in by_name and by_name[key] != code:
                raise ValueError(f"alias {n!r} maps to both {by_name[key]} and {code}")
            by_name[key] = code
    return Teams(rows, by_kalshi, by_name, by_espn)


@lru_cache
def load_backtest_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "backtest.yaml").read_text())
