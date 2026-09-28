"""Normalize historical odds snapshots into long rows (one per snapshot x event x bookmaker x outcome)."""
from __future__ import annotations

from ..sport import Teams


def snapshot_rows(body: dict, requested_ts: str, teams: Teams, origin: str = "historical") -> tuple[list[dict], list[str]]:
    rows, unknown = [], []
    snapshot_ts = body.get("timestamp")
    for ev in body.get("data") or []:
        home_code, away_code = teams.from_name(ev.get("home_team")), teams.from_name(ev.get("away_team"))
        for name, code in ((ev.get("home_team"), home_code), (ev.get("away_team"), away_code)):
            if code is None:
                unknown.append(name)
        for bm in ev.get("bookmakers") or []:
            for mk in bm.get("markets") or []:
                for oc in mk.get("outcomes") or []:
                    rows.append({
                        "snapshot_ts": snapshot_ts, "requested_ts": requested_ts, "odds_event_id": ev["id"],
                        "commence_time": ev.get("commence_time"), "home_team": ev.get("home_team"),
                        "away_team": ev.get("away_team"), "home_code": home_code, "away_code": away_code,
                        "bookmaker": bm["key"], "book_last_update": bm.get("last_update"),
                        "market_key": mk["key"], "market_last_update": mk.get("last_update"),
                        "outcome_name": oc.get("name"), "team_code": teams.from_name(oc.get("name")),
                        "price_decimal": None if oc.get("price") is None else str(oc["price"]),
                        "origin": origin,
                    })
    return rows, unknown
