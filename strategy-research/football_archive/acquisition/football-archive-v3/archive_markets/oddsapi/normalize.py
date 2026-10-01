"""Normalize Odds API odds bodies into long rows (one per snapshot x event x bookmaker x market x outcome).

Handles featured /odds bodies (`data` is a list of events) and event-odds bodies (`data` is one event).
`point` is the line (spread, total, prop line); `description` names the player on prop outcomes.
Both are kept as strings, like the price, so nothing is lost to float rounding.
"""
from __future__ import annotations

from ..sport import Teams


def _events(body: dict) -> list[dict]:
    data = body.get("data")
    return [data] if isinstance(data, dict) else (data or [])


def _str(v):
    return None if v is None else str(v)


def outcome_rows(body: dict, requested_ts: str, origin: str = "historical") -> list[dict]:
    """Team-agnostic rows for any sport and market (no team-name resolution)."""
    rows = []
    snapshot_ts = body.get("timestamp")
    for ev in _events(body):
        for bm in ev.get("bookmakers") or []:
            for mk in bm.get("markets") or []:
                for oc in mk.get("outcomes") or []:
                    rows.append({
                        "snapshot_ts": snapshot_ts, "requested_ts": requested_ts, "odds_event_id": ev["id"],
                        "commence_time": ev.get("commence_time"), "home_team": ev.get("home_team"),
                        "away_team": ev.get("away_team"),
                        "bookmaker": bm["key"], "book_last_update": bm.get("last_update"),
                        "market_key": mk["key"], "market_last_update": mk.get("last_update"),
                        "outcome_name": oc.get("name"), "description": oc.get("description"),
                        "point": _str(oc.get("point")), "price_decimal": _str(oc.get("price")),
                        "origin": origin,
                    })
    return rows


def snapshot_rows(body: dict, requested_ts: str, teams: Teams, origin: str = "historical") -> tuple[list[dict], list[str]]:
    unknown = [name for ev in _events(body) for name in (ev.get("home_team"), ev.get("away_team"))
               if teams.from_name(name) is None]
    rows = [{**r, "home_code": teams.from_name(r["home_team"]), "away_code": teams.from_name(r["away_team"]),
             "team_code": teams.from_name(r["outcome_name"])}
            for r in outcome_rows(body, requested_ts, origin)]
    return rows, unknown
