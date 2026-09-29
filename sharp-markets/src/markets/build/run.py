"""Rebuild data/markets.duckdb from the raw cache. Deterministic and idempotent (CREATE OR REPLACE)."""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import timedelta

import duckdb
import pyarrow as pa

from ..context import Context
from ..fees import fee_schedule_at
from ..games import Game
from ..oddsapi.normalize import snapshot_rows
from ..settings import DB_PATH, RAW_DIR, parse_ts, utcnow
from ..sport import load_backtest_config
from . import sql
from .match import OddsEvent, match_games

log = logging.getLogger(__name__)
RULE_VERSION = "2026-09-27.1"
# The build's sport names and their Odds API sport keys in config/odds5m.yaml, whose sealed seasons the
# build leaves out. Written out on purpose: a sport missing here can't build odds until it is added.
ODDS5M_SPORT_KEY = {"nba": "basketball_nba", "nfl": "americanfootball_nfl"}


def connect(db_path=DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("SET TimeZone = 'UTC'")
    con.execute("SET asof_loop_join_threshold = 0")
    return con


def _raw_glob(sport: str, source: str) -> str | None:
    base = RAW_DIR / sport / source
    return str(base / "*" / "*.parquet") if any(base.glob("*/*.parquet")) else None


def _load(con, name: str, rows: list[dict], schema: pa.Schema) -> None:
    """Load rows into a staging table; string columns get str() values (DuckDB casts them to typed columns)."""
    def conv(v, f):
        return None if v is None else (str(v) if pa.types.is_string(f.type) else v)
    table = pa.Table.from_pylist([{f.name: conv(r.get(f.name), f) for f in schema} for r in rows], schema=schema)
    con.register("_tmp", table)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp")
    con.unregister("_tmp")


def _b2b(games: list[Game]) -> dict[tuple[str, str], bool]:
    """(game_id, team_code) -> played the previous calendar day (ET), over all regular-phase games."""
    by_team = defaultdict(set)
    for g in games:
        if g.phase == "regular" and g.game_date_et:
            by_team[g.away_code].add(g.game_date_et)
            by_team[g.home_code].add(g.game_date_et)
    return {(g.game_id, t): (g.game_date_et - timedelta(days=1)) in by_team[t]
            for g in games if g.game_date_et for t in (g.away_code, g.home_code)}


def sharp_odds_rows(con, sport: str, teams, *, include_sealed: bool = False) -> tuple[list[dict], Counter, Counter, int]:
    """Snapshot rows from data/raw/{sport}/oddsapi_hist (`odds-pull`, and N1 through cache_as), the team-name
    misses, the rows left out by sealed season label, and the rows left out because their game time can't be
    read. A row whose game falls in a sealed season of config/odds5m.yaml is left out unless
    include_sealed=True (only a pre-registered test may pass it), the same rule as bulk.load_rows. A row with no
    readable commence_time is always left out (and counted): its season can't be told, and no game can be
    matched to it."""
    rows_out, unknown_names, sealed_out, no_kick = [], Counter(), Counter(), 0
    glob = _raw_glob(sport, "oddsapi_hist")
    if not glob:
        return rows_out, unknown_names, sealed_out, no_kick
    from ..oddsapi.bulk import game_time, load_config, window_for
    odds5m = load_config()
    key = ODDS5M_SPORT_KEY.get(sport)
    if key not in odds5m["sports"]:
        raise SystemExit(f"markets build: sport {sport!r} has no Odds API key in ODDS5M_SPORT_KEY (build/run.py) that "
                         "config/odds5m.yaml knows, so its sealed seasons can't be left out. Add it before building.")
    for params_json, body in con.execute(
            f"SELECT params_json, body FROM read_parquet('{glob}') WHERE http_status = 200").fetchall():
        rows, unknown = snapshot_rows(json.loads(body), json.loads(params_json)["date"], teams)
        for r in rows:
            k = game_time(r["commence_time"])
            if k is None:
                no_kick += 1
                continue
            w = window_for(odds5m, key, k)
            if w and w["sealed"] and not include_sealed:
                sealed_out[w["label"]] += 1
                continue
            rows_out.append({**r, "sport": sport})
        unknown_names.update(unknown)
    return rows_out, unknown_names, sealed_out, no_kick


def build(ctx: Context, *, include_sealed: bool = False) -> dict:
    sport, cfg, teams, bt = ctx.sport, ctx.cfg, ctx.teams, load_backtest_config()
    games, disc = ctx.games, ctx.discovery
    con = connect()
    summary: dict = {}

    # -- Kalshi time series (SQL over the raw cache) ----------------------------------------------
    for source, make in (("kalshi_candles", sql.candles_sql), ("kalshi_trades", sql.trades_sql)):
        glob = _raw_glob(sport, source)
        if glob:
            con.execute(make(sport, glob))
    if _raw_glob(sport, "kalshi_trades"):
        con.execute(sql.YES_TAKER_1M)

    # -- Sharp odds (Python: team-name resolution; sealed seasons left out) -------------------------
    odds_rows, unknown_names, sealed_out, no_kick = sharp_odds_rows(con, sport, teams, include_sealed=include_sealed)
    summary["sealed_odds_rows_left_out"] = dict(sealed_out)
    summary["odds_rows_without_commence_time"] = no_kick
    odds_schema = pa.schema([(c, pa.string()) for c in (
        "sport", "snapshot_ts", "requested_ts", "odds_event_id", "commence_time", "home_team", "away_team",
        "home_code", "away_code", "bookmaker", "book_last_update", "market_key", "market_last_update",
        "outcome_name", "team_code", "price_decimal", "origin")])
    _load(con, "stg_sharp_odds", odds_rows, odds_schema)
    con.execute(sql.SHARP_ODDS)
    con.execute(sql.sharp_fair_sql(bt["fair"]["blend_weights"]))

    # -- Matching Kalshi games to Odds API events ----------------------------------------------------
    events = [OddsEvent(eid, hc, ac, parse_ts(last), parse_ts(cmin), parse_ts(cmax))
              for eid, hc, ac, last, cmin, cmax in con.execute("""
                  SELECT odds_event_id, any_value(home_code), any_value(away_code),
                         strftime(arg_max(commence_time, snapshot_ts), '%Y-%m-%dT%H:%M:%SZ'),
                         strftime(min(commence_time), '%Y-%m-%dT%H:%M:%SZ'), strftime(max(commence_time), '%Y-%m-%dT%H:%M:%SZ')
                  FROM sharp_odds GROUP BY odds_event_id""").fetchall()]
    snap_times = [parse_ts(t) for (t,) in con.execute(
        "SELECT DISTINCT strftime(snapshot_ts, '%Y-%m-%dT%H:%M:%SZ') FROM sharp_odds ORDER BY 1").fetchall()]
    candidates = [g for g in games if g.away_code and g.home_code and g.kalshi_est_tip]
    matches, conflicts = match_games([(g.game_id, g.away_code, g.home_code, g.kalshi_est_tip) for g in candidates], events)

    def odds_covered(g: Game) -> bool:     # any snapshot in the 6h before the estimated tip?
        lo, hi = g.kalshi_est_tip - timedelta(hours=6), g.kalshi_est_tip
        return any(lo <= t <= hi for t in snap_times)

    # -- Games, markets, exclusions, anomalies ----------------------------------------------------
    b2b = _b2b(games)
    event_fees = _event_fee_overrides(con, sport)
    now = utcnow().isoformat()
    game_rows, market_rows, excl_rows, anom_rows = [], [], [], []
    for g in games:
        mt = matches.get(g.game_id)
        status = "matched" if mt else ("unmatched" if g.kalshi_est_tip and odds_covered(g) else "odds_not_pulled")
        tip = mt.commence_time if mt else g.kalshi_est_tip
        fee_type, mult, assumed = fee_schedule_at(
            (tip or utcnow()) - timedelta(minutes=1), series_fee_type=disc.series.get("fee_type"),
            series_multiplier=disc.series.get("fee_multiplier"), series_changes=disc.series_fee_changes,
            event_changes=event_fees.get(g.game_id))
        game_rows.append({
            "sport": sport, "game_id": g.game_id, "season": g.season, "game_date_et": str(g.game_date_et) if g.game_date_et else None,
            "title": g.title, "phase": g.phase, "split": g.split, "away_code": g.away_code, "home_code": g.home_code,
            "kalshi_est_tip": g.kalshi_est_tip.isoformat() if g.kalshi_est_tip else None,
            "open_time": g.open_time.isoformat() if g.open_time else None,
            "odds_event_id": mt.odds_event_id if mt else None,
            "commence_time": mt.commence_time.isoformat() if mt else None,
            "tip_diff_min": mt.tip_diff_min if mt else None,
            "tip_diff_flag": bool(mt and abs(mt.tip_diff_min) > cfg.tip_diff_flag_min),
            "home_away_swapped": bool(mt and mt.home_away_swapped), "commence_changed": bool(mt and mt.commence_changed),
            "is_nba_cup": any(k == "nba_cup_game" for k, _, _ in g.anomalies),
            "away_b2b": b2b.get((g.game_id, g.away_code)), "home_b2b": b2b.get((g.game_id, g.home_code)),
            "match_status": status, "fee_type": fee_type, "fee_multiplier": str(mult), "fee_assumed": assumed,
        })
        for m in g.markets:
            market_rows.append({"sport": sport, "market_ticker": m.market_ticker, "game_id": g.game_id,
                                "team_code": m.team_code, "kalshi_suffix": m.kalshi_suffix, "yes_sub_title": m.yes_sub_title,
                                "open_time": m.open_time.isoformat(), "close_time": m.close_time.isoformat(),
                                "expected_expiration_time": m.expected_expiration_time.isoformat(),
                                "settlement_ts": m.settlement_ts.isoformat() if m.settlement_ts else None,
                                "status": m.status, "result": m.result, "settlement_value": m.settlement_value,
                                "volume": m.volume, "endpoint": m.endpoint})
        for reason, market, detail in g.exclusions:
            for m in g.markets if market is None else [x for x in g.markets if x.market_ticker == market]:
                excl_rows.append({"sport": sport, "market_ticker": m.market_ticker, "game_id": g.game_id,
                                  "reason": reason, "detail": detail, "rule_version": RULE_VERSION, "logged_at": now})
        for kind, market, detail in g.anomalies:
            anom_rows.append({"sport": sport, "kind": kind, "game_id": g.game_id, "market_ticker": market, "ts": None, "detail": detail})
        if mt and abs(mt.tip_diff_min) > cfg.tip_diff_flag_min:
            anom_rows.append({"sport": sport, "kind": "tip_diff_gt_flag", "game_id": g.game_id, "market_ticker": None,
                              "ts": mt.commence_time.isoformat(), "detail": f"commence - kalshi est = {mt.tip_diff_min:.0f} min"})
        if mt and mt.home_away_swapped:
            anom_rows.append({"sport": sport, "kind": "home_away_swapped", "game_id": g.game_id, "market_ticker": None,
                              "ts": None, "detail": f"odds event {mt.odds_event_id}"})
        if mt and mt.commence_changed:
            anom_rows.append({"sport": sport, "kind": "commence_changed", "game_id": g.game_id, "market_ticker": None,
                              "ts": None, "detail": f"odds event {mt.odds_event_id}"})
        if status == "unmatched" and not g.excluded:
            anom_rows.append({"sport": sport, "kind": "unmatched_kalshi", "game_id": g.game_id, "market_ticker": None,
                              "ts": None, "detail": f"{g.away_code}@{g.home_code} est tip {g.kalshi_est_tip}"})
            for m in g.markets:
                excl_rows.append({"sport": sport, "market_ticker": m.market_ticker, "game_id": g.game_id,
                                  "reason": "unmatched_odds", "detail": "no Odds API event within 18h with this team pair",
                                  "rule_version": RULE_VERSION, "logged_at": now})
        if assumed:
            anom_rows.append({"sport": sport, "kind": "fee_schedule_assumed", "game_id": g.game_id, "market_ticker": None,
                              "ts": None, "detail": "tip precedes first recorded series fee change"})
    for gid, detail in conflicts:
        anom_rows.append({"sport": sport, "kind": "match_conflict", "game_id": gid, "market_ticker": None, "ts": None, "detail": detail})
    matched_events = {m.odds_event_id for m in matches.values()}
    for ev in events:
        if ev.odds_event_id not in matched_events:
            anom_rows.append({"sport": sport, "kind": "unmatched_odds", "game_id": None, "market_ticker": None,
                              "ts": ev.commence_time.isoformat(), "detail": f"{ev.away_code}@{ev.home_code} {ev.odds_event_id}"})
    for name, n in unknown_names.items():
        anom_rows.append({"sport": sport, "kind": "unknown_team_name", "game_id": None, "market_ticker": None,
                          "ts": None, "detail": f"{name!r} x{n}"})
    for label, n in sealed_out.items():
        anom_rows.append({"sport": sport, "kind": "sealed_odds_left_out", "game_id": None, "market_ticker": None,
                          "ts": None, "detail": f"{n} odds rows for games in sealed season {label} "
                                                "(config/odds5m.yaml) left out of sharp_odds"})
    if no_kick:
        anom_rows.append({"sport": sport, "kind": "odds_row_without_commence_time", "game_id": None,
                          "market_ticker": None, "ts": None,
                          "detail": f"{no_kick} odds rows with no readable commence_time left out of sharp_odds "
                                    "(their season, sealed or not, can't be told)"})

    s = pa.string()
    _load(con, "stg_games", game_rows, pa.schema([(k, s) for k in game_rows[0]] if game_rows else []))
    con.execute("""
        CREATE OR REPLACE TABLE games AS
        SELECT sport, game_id, season, CAST(game_date_et AS DATE) AS game_date_et, title, phase, split,
               away_code, home_code, CAST(kalshi_est_tip AS TIMESTAMPTZ) AS kalshi_est_tip,
               CAST(open_time AS TIMESTAMPTZ) AS open_time, odds_event_id,
               CAST(commence_time AS TIMESTAMPTZ) AS commence_time, CAST(tip_diff_min AS DOUBLE) AS tip_diff_min,
               CAST(tip_diff_flag AS BOOLEAN) AS tip_diff_flag, CAST(home_away_swapped AS BOOLEAN) AS home_away_swapped,
               CAST(commence_changed AS BOOLEAN) AS commence_changed, CAST(is_nba_cup AS BOOLEAN) AS is_nba_cup,
               CAST(away_b2b AS BOOLEAN) AS away_b2b, CAST(home_b2b AS BOOLEAN) AS home_b2b, match_status,
               fee_type, CAST(fee_multiplier AS DECIMAL(6,4)) AS fee_multiplier, CAST(fee_assumed AS BOOLEAN) AS fee_assumed
        FROM stg_games""")
    _load(con, "stg_markets", market_rows, pa.schema([(k, s) for k in market_rows[0]]))
    con.execute("""
        CREATE OR REPLACE TABLE kalshi_markets AS
        SELECT sport, market_ticker, game_id, team_code, kalshi_suffix, yes_sub_title,
               CAST(open_time AS TIMESTAMPTZ) AS open_time, CAST(close_time AS TIMESTAMPTZ) AS close_time,
               CAST(expected_expiration_time AS TIMESTAMPTZ) AS expected_expiration_time,
               CAST(settlement_ts AS TIMESTAMPTZ) AS settlement_ts, status, result,
               CAST(settlement_value AS DECIMAL(6,4)) AS settlement_value, CAST(volume AS DECIMAL(18,2)) AS volume, endpoint
        FROM stg_markets""")
    con.execute("""
        CREATE OR REPLACE TABLE results AS
        SELECT sport, game_id, market_ticker, result,
               CASE WHEN result IN ('yes', 'no') THEN 'binary' ELSE result END AS settlement_type,
               settlement_value, settlement_ts AS settled_ts
        FROM kalshi_markets""")
    excl_schema = pa.schema([(k, s) for k in ("sport", "market_ticker", "game_id", "reason", "detail", "rule_version", "logged_at")])
    _load(con, "stg_excluded", excl_rows, excl_schema)
    con.execute("""CREATE OR REPLACE TABLE excluded_markets AS
                   SELECT DISTINCT ON (sport, market_ticker, reason) sport, market_ticker, game_id, reason, detail,
                          rule_version, CAST(logged_at AS TIMESTAMPTZ) AS logged_at FROM stg_excluded""")

    # -- Analysis grid ----------------------------------------------------------------------------------
    have_candles = bool(_raw_glob(sport, "kalshi_candles"))
    if have_candles and con.execute("SELECT count(*) FROM games WHERE match_status = 'matched'").fetchone()[0]:
        con.execute(sql.analysis_sql(fair_source=bt["fair"]["default_source"], ffill_max_min=bt["kalshi"]["ffill_max_age_min"],
                                     sharp_max_min=bt["fair"]["max_sharp_age_min"], taker_rate=bt["fees"]["taker_rate"]))
        con.execute("CREATE OR REPLACE VIEW v_analysis AS SELECT * FROM analysis_1m")
        for sp, gid, minutes, pre, first, last, min_sum, fresh, fee_pos in con.execute(sql.ASK_SUM_LT_1).fetchall():
            anom_rows.append({"sport": sp, "kind": "ask_sum_lt_1", "game_id": gid, "market_ticker": None,
                              "ts": first.isoformat(),
                              "detail": f"{minutes} min ({pre} pre-game; {fresh} with both legs freshly quoted; "
                                        f"{fee_pos} still < $1 after taker fees) with yes_ask_A + yes_ask_B < 1; "
                                        f"min sum {min_sum}; {first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M} UTC"})
    anom_schema = pa.schema([(k, s) for k in ("sport", "kind", "game_id", "market_ticker", "ts", "detail")])
    _load(con, "stg_anomalies", anom_rows, anom_schema)
    con.execute("""CREATE OR REPLACE TABLE anomalies AS
                   SELECT sport, kind, game_id, market_ticker, CAST(ts AS TIMESTAMPTZ) AS ts, detail FROM stg_anomalies""")
    for t in ("stg_games", "stg_markets", "stg_excluded", "stg_anomalies", "stg_sharp_odds"):
        con.execute(f"DROP TABLE IF EXISTS {t}")

    summary["tables"] = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for (t,) in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' AND table_type = 'BASE TABLE' ORDER BY 1").fetchall()}
    summary["match_status"] = dict(con.execute("SELECT match_status, count(*) FROM games GROUP BY 1").fetchall())
    summary["anomalies"] = dict(con.execute("SELECT kind, count(*) FROM anomalies GROUP BY 1 ORDER BY 1").fetchall())
    summary["exclusions"] = dict(con.execute("SELECT reason, count(*) FROM excluded_markets GROUP BY 1 ORDER BY 1").fetchall())
    con.close()
    return summary


def _event_fee_overrides(con, sport: str) -> dict[str, list[dict]]:
    glob = _raw_glob(sport, "kalshi_event_fees")
    out: dict[str, list[dict]] = defaultdict(list)
    if glob:
        for (body,) in con.execute(f"SELECT body FROM read_parquet('{glob}') WHERE http_status = 200").fetchall():
            for ch in json.loads(body).get("event_fee_changes") or []:
                out[ch["event_ticker"]].append(ch)
    return out
