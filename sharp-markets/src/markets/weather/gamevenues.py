"""Game-level venues, fetched on the Mac (both APIs are free and keyless, and blocked from the cloud).
GET only, cache-first under data/raw/_venues/.

MLB    statsapi.mlb.com schedule with hydrate=venue(location): the park and its coordinates for every game,
       so neutral-site and relocated games (London, Mexico City, Tokyo, Seoul, Field of Dreams, Rickwood,
       Bristol, the Blue Jays in 2020-21) are placed exactly.
Soccer ESPN's public scoreboard: the venue name for every match. It is needed for Copa America 2024,
       Club World Cup 2025 and Gold Cup 2025, which have no fixture table, and it checks the leagues'
       dated home venues match by match.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..cache import Fetched, RawCache, body_json, read_record
from ..http import RateLimiter, http_get, new_session
from ..settings import parse_ts
from .venues import venue_by_name

STATSAPI = "https://statsapi.mlb.com/api/v1/schedule"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
ESPN_SLUGS = {"soccer_usa_mls": "usa.1", "soccer_mexico_ligamx": "mex.1", "soccer_brazil_campeonato": "bra.1",
              "soccer_japan_j_league": "jpn.1", "soccer_korea_kleague1": "kor.1",
              "soccer_conmebol_copa_america": "conmebol.america", "soccer_fifa_club_world_cup": "fifa.cwc",
              "soccer_concacaf_gold_cup": "concacaf.gold", "soccer_concacaf_leagues_cup": "concacaf.leagues.cup",
              "soccer_fifa_world_cup": "fifa.world", "soccer_uefa_european_championship": "uefa.euro"}
SPORT = "_venues"


def month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Whole calendar months covering [start, end], so cache keys don't depend on the range asked for."""
    out, lo = [], start.replace(day=1)
    while lo <= end:
        nxt = (lo.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((lo, nxt - timedelta(days=1)))
        lo = nxt
    return out


class GameVenues:
    def __init__(self, cache: RawCache, *, session=None, rate_per_sec: float = 2):
        self.cache = cache
        self.session = session or new_session(user_agent=None)      # ESPN rejects custom agents
        self.limiter = RateLimiter(rate_per_sec)

    def _get(self, source: str, url: str, params: dict, day: date, fetch: bool) -> dict | None:
        from ..cache import cache_key
        p = self.cache.lookup(SPORT, source, cache_key(source, url, params))
        if p is not None:
            rec = read_record(p)
        elif not fetch:
            return None
        else:
            def f() -> Fetched:
                r = http_get(self.session, url, params, self.limiter, max_retries=3)
                return Fetched(r.status_code, dict(r.headers), r.text)
            rec = self.cache.get_or_fetch(sport=SPORT, source=source, data_date=day.isoformat(), url=url,
                                          params=params, fetch=f, cache_statuses=(200,))
        return body_json(rec) if rec["http_status"] == 200 else None

    def mlb(self, start: date, end: date, *, fetch: bool = False) -> list[dict]:
        rows = []
        for lo, hi in month_chunks(start, end):
            body = self._get("mlb_statsapi", STATSAPI, {"sportId": 1, "startDate": lo.isoformat(),
                                                        "endDate": hi.isoformat(), "hydrate": "venue(location)"},
                             lo, fetch)
            for d in (body or {}).get("dates", []):
                for g in d.get("games", []):
                    v = g.get("venue") or {}
                    loc = ((v.get("location") or {}).get("defaultCoordinates") or {})
                    rows.append({"game_pk": g.get("gamePk"), "kickoff": parse_ts(g.get("gameDate")),
                                 "home": g["teams"]["home"]["team"]["name"], "away": g["teams"]["away"]["team"]["name"],
                                 "venue_name": v.get("name"), "venue_id": venue_by_name(v.get("name")),
                                 "lat": loc.get("latitude"), "lon": loc.get("longitude")})
        return rows

    def espn(self, sport_key: str, start: date, end: date, *, fetch: bool = False) -> list[dict]:
        slug = ESPN_SLUGS[sport_key]
        rows = []
        for lo, hi in month_chunks(start, end):
            body = self._get("espn_soccer", ESPN.format(slug=slug),
                             {"dates": f"{lo:%Y%m%d}-{hi:%Y%m%d}", "limit": 1000}, lo, fetch)
            for ev in (body or {}).get("events", []):
                comp = (ev.get("competitions") or [{}])[0]
                teams = {c.get("homeAway"): (c.get("team") or {}).get("displayName") for c in comp.get("competitors", [])}
                v = comp.get("venue") or {}
                rows.append({"kickoff": parse_ts(ev.get("date")), "home": teams.get("home"), "away": teams.get("away"),
                             "venue_name": v.get("fullName"), "venue_city": (v.get("address") or {}).get("city"),
                             "venue_id": venue_by_name(v.get("fullName"))})
        return rows


def nearest(rows: list[dict], home: str, away: str, kickoff: datetime, key) -> dict | None:
    """The row for the same pairing (either order) with the closest kickoff within 12 hours.
    `key` maps a team name to a comparable key (venues.canonical for a sport)."""
    pair = {key(home), key(away)}
    cands = [r for r in rows if {key(r["home"]), key(r["away"])} == pair and r["kickoff"]
             and abs(r["kickoff"] - kickoff) <= timedelta(hours=12)]
    return min(cands, key=lambda r: abs(r["kickoff"] - kickoff)) if cands else None
