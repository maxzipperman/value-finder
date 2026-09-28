"""Pinnacle NFL totals and spreads from The Odds API (https://the-odds-api.com).

Same rules as sharp-markets:
* GET only. Key from ODDS_API_KEY (environment, or .env in the project root).
* Cache first: every response is written to data/raw/oddsapi/ before it is
  parsed; reruns read the cache and never re-fetch.
* Credit budget: historical pulls need --confirm and stop at --max-credits.
* UTC everywhere. A line is "known" at the snapshot timestamp, never at the
  book's last_update.

Costs (per The Odds API docs): a live call costs markets x regions credits; a
historical call costs 10x that. A bookmakers= list of up to 10 books counts as one
region, so live calls log LIVE_BOOKS for the price of Pinnacle alone. The rule's
price is still Pinnacle's; the other books are logged for line shopping.

Credits: every response's x-requests-remaining is kept in data/raw/oddsapi/quota.json.
A call is refused (OddsAPIUnavailable, which the board treats like "no key") when the
month's remaining credits are at or below its floor: 0 for the scheduled alerts,
MANUAL_FLOOR for hand-run commands, so manual use can't starve the alerts.
"""
from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd

import requests

from .config import PROC, RAW, ROOT
from .fetch import session

BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"
CACHE = RAW / "oddsapi"
QUOTA = CACHE / "quota.json"
MANUAL_FLOOR = 60
# <= 10 books = 1 region = 1 credit per market. All on the free plan (williamhill_us and fanatics are paid-only).
LIVE_BOOKS = ("pinnacle", "lowvig", "betonlineag", "draftkings", "fanduel", "betmgm", "betrivers", "bovada",
              "espnbet", "hardrockbet")
RULE_BOOK = "pinnacle"

TEAM = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR", "Chicago Bears": "CHI", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL", "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV", "Oakland Raiders": "OAK", "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LA",
    "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO",
    "New York Giants": "NYG", "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS", "Washington Football Team": "WAS",
}


def api_key():
    key = os.environ.get("ODDS_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("ODDS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("ODDS_API_KEY is not set: add it to .env in the project root (see .env.example)")
    return key


class OddsAPIUnavailable(SystemExit):
    """The Odds API can't be used right now (no key, bad key, out of credits, network or
    server error). A SystemExit so callers that already catch "no key" fall back the same way."""


def has_key():
    try:
        api_key()
        return True
    except SystemExit:
        return False


class Budget:
    def __init__(self, max_credits):
        self.max, self.used, self.remaining = max_credits, 0, None

    def charge(self, r):
        last = int(r.headers.get("x-requests-last", 0) or 0)
        self.used += last
        rem = r.headers.get("x-requests-remaining")
        self.remaining = int(float(rem)) if rem is not None else self.remaining
        if last > 100:
            raise SystemExit(f"circuit breaker: one request cost {last} credits")

    def room(self, cost):
        return self.used + cost <= self.max


def _month():
    return pd.Timestamp.now(tz="UTC").strftime("%Y-%m")


def quota_left():
    """Credits left as of the last call this calendar month (UTC), or None if unknown.
    Credits reset on the 1st, so last month's figure doesn't count."""
    if not QUOTA.exists():
        return None
    q = json.loads(QUOTA.read_text())
    return q.get("remaining") if q.get("month") == _month() else None


def _record_quota(r):
    h = r.headers
    if h.get("x-requests-remaining") is None:
        return
    QUOTA.parent.mkdir(parents=True, exist_ok=True)
    num = lambda v: None if v is None else int(float(v))  # noqa: E731
    QUOTA.write_text(json.dumps(dict(utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), month=_month(),
                                     remaining=num(h.get("x-requests-remaining")), used=num(h.get("x-requests-used")),
                                     last=num(h.get("x-requests-last")))))


def _get(path, params, floor=0):
    left = quota_left()
    if left is not None and left <= floor:
        raise OddsAPIUnavailable(f"credit floor: {left} Odds API credits left this month (floor {floor})")
    try:
        r = session.get(f"{BASE}{path}", params={**params, "apiKey": api_key()}, timeout=60)
    except requests.RequestException as e:
        raise OddsAPIUnavailable(f"The Odds API is unreachable ({type(e).__name__})") from e
    _record_quota(r)
    if r.status_code == 401:
        raise OddsAPIUnavailable("The Odds API rejected the key, or the plan is out of credits (401)")
    if r.status_code == 422 and "historical" in path:
        raise OddsAPIUnavailable("Historical odds need a paid Odds API plan (422)")
    if r.status_code == 429:
        raise OddsAPIUnavailable("The Odds API refused the call: out of credits or rate-limited (429)")
    if r.status_code != 200:
        raise OddsAPIUnavailable(f"The Odds API returned {r.status_code}")
    return r


def live(markets=("totals", "spreads"), budget: Budget | None = None, floor=0):
    """Current lines at LIVE_BOOKS (Pinnacle first) for every upcoming NFL game. Costs len(markets)
    credits. `floor`: refuse when this month's remaining credits are at or below it."""
    ts = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H%MZ")
    dest = CACHE / "live" / f"{ts}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = _get(f"/sports/{SPORT}/odds", dict(bookmakers=",".join(LIVE_BOOKS), markets=",".join(markets),
                                            oddsFormat="american", dateFormat="iso"), floor=floor)
    if budget:
        budget.charge(r)
    dest.write_text(json.dumps({"snapshot_utc": ts, "data": r.json()}))
    return parse({"snapshot_utc": ts, "data": r.json()})


def historical(ts: pd.Timestamp, markets=("totals",), budget: Budget | None = None):
    """The snapshot at or before `ts`. It is labelled with the API's own `timestamp` (when the
    quotes were captured, up to 5 minutes earlier), not the requested time."""
    stamp = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    dest = CACHE / "historical" / f"{ts.strftime('%Y-%m-%dT%H%MZ')}_{'-'.join(markets)}.json"
    if dest.exists():
        return json.loads(dest.read_text())
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = _get(f"/historical/sports/{SPORT}/odds", dict(bookmakers="pinnacle", markets=",".join(markets),
                                                       oddsFormat="american", dateFormat="iso", date=stamp))
    if budget:
        budget.charge(r)
    js = r.json()
    js["requested_utc"] = stamp
    js["snapshot_utc"] = js.get("timestamp") or stamp
    dest.write_text(json.dumps(js))
    return js


def parse(payload) -> pd.DataFrame:
    snap = payload.get("timestamp") or payload.get("snapshot_utc")   # historical: the API's capture time
    rows = []
    for ev in payload.get("data", []):
        home, away = TEAM.get(ev["home_team"]), TEAM.get(ev["away_team"])
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                rec = dict(snapshot_utc=snap, event_id=ev["id"], commence_utc=ev["commence_time"],
                           home=home, away=away, book=bk["key"], market=mk["key"], book_update=mk.get("last_update"))
                if mk["key"] == "totals":
                    for o in mk["outcomes"]:
                        side = o["name"].lower()
                        rec[f"{side}_price"], rec["total"] = o["price"], o.get("point")
                elif mk["key"] == "spreads":
                    for o in mk["outcomes"]:
                        tag = "home" if TEAM.get(o["name"]) == home else "away"
                        rec[f"{tag}_spread"], rec[f"{tag}_spread_price"] = o.get("point"), o["price"]
                rows.append(rec)
    return pd.DataFrame(rows)


FORECAST_LEADS = (1, 3)       # days: Open-Meteo previous_day1 / previous_day3
FORECAST_LATENCY_H = 7        # hours from model initialization to published forecast
GAME_WINDOW_H = 4             # forecast fields used: kickoff hour through kickoff + 4h


def decision_time(kick_utc, lead_days):
    """Earliest moment every forecast field used for this game at this lead was
    public. previous_dayN at valid hour t comes from a run initialized ~N days
    before t, so the binding field is the last game hour (kickoff + 4h):
    decision = kickoff + 4h - N days + release latency, rounded up to 5 minutes."""
    t = pd.Timestamp(kick_utc) + timedelta(hours=GAME_WINDOW_H) - timedelta(days=lead_days) \
        + timedelta(hours=FORECAST_LATENCY_H)
    return t.ceil("5min")


def backfill_plan(games: pd.DataFrame, seasons=(2024, 2025), close_min=30):
    """Snapshot times per distinct kickoff: one at each forecast lead's decision time
    (so the quote never predates the forecast it is paired with) plus one near-close
    snapshot. Games sharing a kickoff share snapshots."""
    g = games[games.season.isin(seasons) & games.result.notna()].copy()
    kick = pd.to_datetime(g.gameday + " " + g.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    stamps = set()
    for k in kick.unique():
        k = pd.Timestamp(k)
        for lead in FORECAST_LEADS:
            stamps.add(decision_time(k, lead))
        stamps.add((k - timedelta(minutes=close_min)).floor("5min"))
    return sorted(stamps)


def backfill(games, seasons=(2024, 2025), markets=("totals",), confirm=False, max_credits=9000):
    plan = backfill_plan(games, seasons)
    per_call = 10 * len(markets)
    todo = [t for t in plan if not (CACHE / "historical" / f"{t.strftime('%Y-%m-%dT%H%MZ')}_{'-'.join(markets)}.json").exists()]
    print(f"  plan: {len(plan)} snapshots, {len(todo)} not cached, ~{len(todo) * per_call:,} credits "
          f"({per_call} per call, budget {max_credits:,})")
    if not confirm:
        print("  dry run: add --confirm to spend credits")
        return
    b = Budget(max_credits)
    for i, t in enumerate(todo):
        if not b.room(per_call):
            print(f"  stopping: budget reached after {b.used} credits")
            break
        historical(t, markets, b)
        if i % 50 == 0:
            print(f"  {i}/{len(todo)} {t}  used {b.used}  remaining {b.remaining}", flush=True)
        time.sleep(0.5)
    print(f"  done: {b.used} credits used, {b.remaining} remaining on the account")


def lines_table(games: pd.DataFrame) -> pd.DataFrame:
    """Every cached Pinnacle snapshot, matched to nflverse game_id, with minutes to kickoff."""
    frames = []
    for f in sorted((CACHE / "historical").glob("*.json")) + sorted((CACHE / "live").glob("*.json")):
        frames.append(parse(json.loads(f.read_text())))
    if not frames:
        return pd.DataFrame()
    L = pd.concat(frames, ignore_index=True)
    L = L[(L.market == "totals") & (L.book == RULE_BOOK)].dropna(subset=["total"])
    L["commence_utc"] = pd.to_datetime(L.commence_utc, utc=True)
    L["snapshot_utc"] = pd.to_datetime(L.snapshot_utc, utc=True, format="mixed")
    g = games[["game_id", "home_team", "away_team", "gameday"]].copy()
    L["gameday"] = L.commence_utc.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    L = L.merge(g, left_on=["home", "away", "gameday"], right_on=["home_team", "away_team", "gameday"], how="left")
    L["min_to_kick"] = (L.commence_utc - L.snapshot_utc).dt.total_seconds() / 60
    L = L[L.min_to_kick > 0].drop_duplicates(["game_id", "snapshot_utc"])
    L.to_parquet(PROC / "pinnacle_lines.parquet", index=False)
    return L
