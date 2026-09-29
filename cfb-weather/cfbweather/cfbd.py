"""CollegeFootballData API (https://api.collegefootballdata.com, v2), GET only.

* Key: CFBD_API_KEY in .env (Bearer token). The free tier allows 1,000 calls a month.
* Cache first: every response is written to data/raw/cfbd/ before it is parsed; reruns read the
  cache and never re-fetch (past seasons don't change).
* Budget: pull() refuses to start when the uncached calls exceed max_calls.

What it adds to cfbfastR (schemas: github.com/CFBD/cfb-api-v2, src/app/*/types.ts):
  lines       every sportsbook's spread and total, with openers, per game (1 call per season type)
  team box    team stats per game (1 call per week; the API needs a week, team or conference)
  player box  every player's stat line per game, for CFB props (optional; 1 call per week)
  returning   returning production by team-season (1 call per season)
  talent      247 talent composite by team-season (1 call per season)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

from .config import RAW
from .fetch import session

BASE = "https://api.collegefootballdata.com"
CACHE = RAW / "cfbd"
REGULAR_WEEKS = range(1, 17)   # CFBD folds week 0 into week 1; late weeks are empty in short seasons


def api_key():
    from .notify import _env
    key = _env("CFBD_API_KEY")
    if not key:
        raise SystemExit("CFBD_API_KEY is not set: add it to .env in cfb-weather (see .env.example)")
    return key


def _path(endpoint, params):
    tag = "_".join(f"{k}-{params[k]}" for k in sorted(params))
    return CACHE / endpoint.strip("/").replace("/", "_") / f"{tag}.json"


def calls(seasons, players=False):
    """Every (endpoint, params) the pull needs, in order."""
    out = []
    for y in seasons:
        out += [("/lines", dict(year=y, seasonType=t)) for t in ("regular", "postseason")]
        out += [("/player/returning", dict(year=y)), ("/talent", dict(year=y))]
        weeks = [("regular", w) for w in REGULAR_WEEKS] + [("postseason", 1)]
        out += [("/games/teams", dict(year=y, week=w, seasonType=t)) for t, w in weeks]
        if players:
            out += [("/games/players", dict(year=y, week=w, seasonType=t)) for t, w in weeks]
    return out


def plan(seasons, players=False):
    todo = [c for c in calls(seasons, players) if not _path(*c).exists()]
    return len(calls(seasons, players)), todo


def get(endpoint, params):
    """One cached GET. Returns the parsed JSON."""
    dest = _path(endpoint, params)
    if dest.exists():
        return json.loads(dest.read_text())
    try:
        r = session.get(BASE + endpoint, params=params, timeout=120,
                        headers={"Authorization": f"Bearer {api_key()}", "Accept": "application/json"})
    except requests.RequestException as e:
        raise SystemExit(f"CFBD is unreachable ({type(e).__name__})") from e
    if r.status_code == 401:
        raise SystemExit("CFBD rejected the key (401)")
    if r.status_code == 429:
        raise SystemExit("CFBD rate limit or monthly quota reached (429)")
    if not r.ok:
        raise SystemExit(f"CFBD returned {r.status_code} for {endpoint} {params}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(r.text)
    return r.json()


def pull(seasons, players=False, max_calls=300, confirm=False, sleep=0.5):
    total, todo = plan(seasons, players)
    print(f"  CFBD plan: {total} calls, {len(todo)} not cached (budget {max_calls})")
    if not confirm:
        print("  dry run: add --confirm to call the API")
        return 0
    if len(todo) > max_calls:
        raise SystemExit(f"{len(todo)} uncached calls exceed --max-calls {max_calls}; narrow --seasons")
    for i, (endpoint, params) in enumerate(todo):
        get(endpoint, params)
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} {endpoint} {params}", flush=True)
        time.sleep(sleep)
    return len(todo)


# ---------------------------------------------------------------- parsers (cache -> tables)
def _cached(endpoint):
    d = CACHE / endpoint.strip("/").replace("/", "_")
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.exists() else []


def lines_table(payloads=None) -> pd.DataFrame:
    """One row per game x sportsbook: spread and total, open and close, moneylines."""
    rows = []
    for games in payloads if payloads is not None else _cached("/lines"):
        for g in games:
            for ln in g.get("lines", []):
                rows.append(dict(game_id=g["id"], season=g["season"], season_type=g["seasonType"], week=g["week"],
                                 start_utc=g.get("startDate"), home_team=g["homeTeam"], away_team=g["awayTeam"],
                                 home_points=g.get("homeScore"), away_points=g.get("awayScore"),
                                 provider=ln["provider"], spread=ln.get("spread"), spread_open=ln.get("spreadOpen"),
                                 total=ln.get("overUnder"), total_open=ln.get("overUnderOpen"),
                                 home_ml=ln.get("homeMoneyline"), away_ml=ln.get("awayMoneyline")))
    t = pd.DataFrame(rows)
    if len(t):
        t["start_utc"] = pd.to_datetime(t.start_utc, utc=True)
        t = t.drop_duplicates(["game_id", "provider"])
    return t


def team_box_table(payloads=None) -> pd.DataFrame:
    """One row per team-game, one column per stat category (values as CFBD reports them)."""
    rows = []
    for games in payloads if payloads is not None else _cached("/games/teams"):
        for g in games:
            for t in g.get("teams", []):
                rec = dict(game_id=g["id"], team=t["team"], home_away=t["homeAway"], points=t.get("points"))
                rec.update({s["category"]: s["stat"] for s in t.get("stats", [])})
                rows.append(rec)
    return pd.DataFrame(rows).drop_duplicates(["game_id", "team"]) if rows else pd.DataFrame()


def player_box_table(payloads=None) -> pd.DataFrame:
    """Long format: one row per game x player x stat (passing/rushing/receiving/kicking)."""
    keep = {"passing", "rushing", "receiving", "kicking"}
    rows = []
    for games in payloads if payloads is not None else _cached("/games/players"):
        for g in games:
            for t in g.get("teams", []):
                for cat in t.get("categories", []):
                    if cat["name"] not in keep:
                        continue
                    for typ in cat.get("types", []):
                        for a in typ.get("athletes", []):
                            rows.append(dict(game_id=g["id"], team=t["team"], player_id=a["id"], player=a["name"],
                                             category=cat["name"], stat=typ["name"], value=a["stat"]))
    return pd.DataFrame(rows)


def season_table(endpoint) -> pd.DataFrame:
    """Returning production or talent: the per-season lists stacked."""
    frames = [pd.DataFrame(p) for p in _cached(endpoint) if p]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
