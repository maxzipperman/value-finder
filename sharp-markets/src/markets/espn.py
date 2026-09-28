"""One-time NBA Cup calendar pull from ESPN's public scoreboard -> CSV for manual review.

Kalshi and The Odds API do not mark NBA Cup games; ESPN's per-game notes do ("NBA Cup - ...").
The CSV is committed and reviewed by a human; the pipeline only reads the CSV afterwards.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import yaml

from .cache import Fetched, body_json
from .context import Context
from .http import RateLimiter, http_get, new_session
from .settings import CONFIG_DIR, ROOT, parse_ts

ET = ZoneInfo("America/New_York")
FIELDS = ["game_date_et", "away_code", "home_code", "cup_round", "note_headline", "tip_utc",
          "espn_event_id", "review_status"]


def _round(headline: str) -> str:
    h = headline.lower()
    if "quarterfinal" in h:
        return "quarterfinal"
    if "semifinal" in h:
        return "semifinal"
    if "championship" in h or "final" in h:
        return "final"
    return "group"


def pull_cup_calendar(ctx: Context, season_label: str) -> tuple[str, list[dict], list[str]]:
    season = ctx.cfg.seasons[season_label]
    league = yaml.safe_load((CONFIG_DIR / "sports" / f"{ctx.sport}.yaml").read_text())["espn"]["league_path"]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{league}/scoreboard"
    session, limiter = new_session(user_agent=None), RateLimiter(1.0)
    rows, problems = [], []
    d = season.cup_scan_from
    while d <= season.cup_scan_to:
        params = {"dates": d.strftime("%Y%m%d")}

        def fetch(params=params) -> Fetched:
            r = http_get(session, url, params, limiter)
            return Fetched(r.status_code, dict(r.headers), r.text)

        rec = ctx.cache.get_or_fetch(sport=ctx.sport, source="espn_scoreboard", data_date=str(d),
                                     url=url, params=params, fetch=fetch)
        if rec["http_status"] != 200:
            raise RuntimeError(f"ESPN scoreboard {d} -> HTTP {rec['http_status']}: {(rec['body'] or '')[:200]}")
        for ev in (body_json(rec) or {}).get("events", []):
            comp = ev["competitions"][0]
            notes = " | ".join(n.get("headline", "") for n in comp.get("notes") or [])
            if "cup" not in notes.lower():
                continue
            side = {c["homeAway"]: c["team"]["abbreviation"] for c in comp["competitors"]}
            away, home = ctx.teams.from_espn(side.get("away")), ctx.teams.from_espn(side.get("home"))
            if away is None or home is None:
                problems.append(f"{d}: unknown ESPN code(s) {side}")
            tip = parse_ts(ev["date"])
            rows.append({"game_date_et": tip.astimezone(ET).date().isoformat(), "away_code": away or side.get("away"),
                         "home_code": home or side.get("home"), "cup_round": _round(notes), "note_headline": notes,
                         "tip_utc": tip.isoformat(), "espn_event_id": ev["id"], "review_status": "unreviewed"})
        d += timedelta(days=1)

    out = ROOT / season.cup_calendar
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["tip_utc"], r["home_code"])))
    return str(out), rows, problems
