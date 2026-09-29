"""Live uses on a paid Odds API plan (the 5M month and after): the wind-trigger price poller and the
props/alternates log. LOGGING ONLY: nothing here sends an alert, places a bet or changes Rule B,
its gates or its scoring. GET only.

Both are background loggers. Their launchd jobs set ODDS_QUOTA_KIND=background, so quota.check()
refuses them on the free plan and stops them at the background floor (quota.py). The alerts and
close capture keep their credits.

Trigger poller (scripts/poll_triggers.py, every 10 minutes): for games whose latest ledger row
has a Rule B wind trigger (board.rule_b_status past "no_trigger") and a kickoff within
POLL_HORIZON, one live totals call (1 credit, 10 books) logs every book's total and prices to
data/forward/trigger_polls.csv. It shows how the price moves between the four daily alert runs.

Props log (scripts/log_props.py, every 15 minutes): for every NFL game, event odds for PROP_MARKETS
at PROP_BOOKS at T-48h, T-24h, T-2h and the close (2-20 minutes before kickoff, as close capture
does). That continues the historical F2/F3 series live, in the same decimal odds. Each call costs
1 credit per market returned (up to 9). Rows go to data/forward/props_log.csv; raw response text to
data/raw/oddsapi/props/ (under "body"), written before it is parsed.

Both logs are holdout data. The 2026 NFL season is sealed (owner decision, Sep 28; the window in
sharp-markets/config/odds5m.yaml), so every row for a 2026-season game carries sealed=True, and nothing
analyses those rows until a hypothesis about them is pre-registered.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

SEALED_SEASON = (pd.Timestamp("2026-09-01", tz="UTC"), pd.Timestamp("2027-02-21", tz="UTC"))  # odds5m.yaml NFL "2026"
TRIGGERED = {"outside_horizon", "no_price", "price_too_high", "negative_ev", "SIGNAL"}
POLL_HORIZON = pd.Timedelta(days=4)
MATCH_TOLERANCE = pd.Timedelta(hours=12)

# The historical F2 + F3 pulls (sharp-markets/config/odds5m.yaml), so the live log continues them.
PROP_MARKETS = ("alternate_spreads", "alternate_totals", "team_totals", "player_pass_yds", "player_rush_yds",
                "player_reception_yds", "player_receptions", "player_kicking_points", "player_field_goals")
PROP_BOOKS = ("pinnacle", "lowvig", "betonlineag", "draftkings", "fanduel", "betmgm", "williamhill_us", "fanatics",
              "betrivers", "espnbet")                     # 10 books = 1 region
PROP_ODDS_FORMAT = "decimal"                              # as the historical F2/F3 pulls
PROP_OFFSETS_H = (48, 24, 2, 0)
OFFSET_WINDOW = pd.Timedelta(minutes=30)                  # a slot is due for 30 minutes after its target
CLOSE_WINDOW = (pd.Timedelta(minutes=2), pd.Timedelta(minutes=20))


def sealed(kick_utc) -> bool:
    """True for a game in the sealed 2026 season (holdout data)."""
    k = pd.Timestamp(kick_utc)
    k = k.tz_localize("UTC") if k.tzinfo is None else k.tz_convert("UTC")
    return bool(SEALED_SEASON[0] <= k < SEALED_SEASON[1])


def ledger_kick_utc(ledger: pd.DataFrame) -> pd.Series:
    return (pd.to_datetime(ledger.gameday + " " + ledger.gametime)
            .dt.tz_localize("America/New_York").dt.tz_convert("UTC"))


def active_triggers(ledger: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """Games whose latest ledger row carries a Rule B wind trigger and that kick off within POLL_HORIZON."""
    if ledger.empty or "rule_b" not in ledger:
        return ledger.iloc[0:0]
    L = ledger.dropna(subset=["gameday", "gametime"]).copy()
    L["kick_utc"] = ledger_kick_utc(L)
    L = L.sort_values("snapshot_utc").drop_duplicates("game_id", keep="last")
    return L[L.rule_b.isin(TRIGGERED) & (L.kick_utc > now) & (L.kick_utc - now <= POLL_HORIZON)]


def trigger_rows(active: pd.DataFrame, lines: pd.DataFrame, poll_utc: str) -> pd.DataFrame:
    """One row per triggered game x book: the book's total and prices at this poll."""
    cols = ["poll_utc", "game_id", "kick_utc", "ledger_snapshot_utc", "rule_b", "wx_wind", "lead_days", "book",
            "total", "under_price", "over_price", "book_update", "quote_utc", "sealed"]
    if active.empty or lines is None or lines.empty:
        return pd.DataFrame(columns=cols)
    tot = lines[lines.market == "totals"].copy()
    tot["commence"] = pd.to_datetime(tot.commence_utc, utc=True)
    m = active.merge(tot, left_on=["home_team", "away_team"], right_on=["home", "away"], how="inner")
    m = m[(m.commence - m.kick_utc).abs() <= MATCH_TOLERANCE]
    m = m.assign(poll_utc=poll_utc, ledger_snapshot_utc=m.snapshot_utc_x, quote_utc=m.snapshot_utc_y,
                 sealed=m.kick_utc.map(sealed), kick_utc=m.kick_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return m[cols].reset_index(drop=True)


def props_due(events: list[dict], captured: set[str], now: pd.Timestamp) -> list[tuple[dict, int]]:
    """(event, offset hours) pairs whose snapshot is due now and not yet captured."""
    due = []
    for ev in events:
        kick = pd.Timestamp(ev["commence_time"])
        for h in PROP_OFFSETS_H:
            if f"{ev['id']}:{h}" in captured:
                continue
            if h == 0:
                ok = CLOSE_WINDOW[0] <= kick - now <= CLOSE_WINDOW[1]
            else:
                target = kick - pd.Timedelta(hours=h)
                ok = target <= now < target + OFFSET_WINDOW
            if ok:
                due.append((ev, h))
    return due


def props_rows(body: dict, snapshot_utc: str, offset_h: int) -> pd.DataFrame:
    """Long rows: one per book x market x outcome (player in `description`, line in `point`)."""
    rows = []
    for bk in body.get("bookmakers", []):
        for mk in bk.get("markets", []):
            for o in mk.get("outcomes", []):
                rows.append(dict(snapshot_utc=snapshot_utc, offset_h=offset_h, event_id=body.get("id"),
                                 commence_utc=body.get("commence_time"), home_team=body.get("home_team"),
                                 away_team=body.get("away_team"), book=bk["key"], market=mk["key"],
                                 market_update=mk.get("last_update"), outcome=o.get("name"),
                                 player=o.get("description"), point=o.get("point"), price=o.get("price"),
                                 sealed=sealed(body["commence_time"]) if body.get("commence_time") else None))
    return pd.DataFrame(rows)


def save_state(path: Path, state: dict) -> None:
    """Write the props log's state atomically (temp file, then rename), so a crash never leaves it half-written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, path)
