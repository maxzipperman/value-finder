"""H4a — does Kalshi's NFL totals ladder underreact to wind?  (zero Odds API credits)

Inputs
- The NFL weather study's processed games (read-only): realized kickoff weather (ERA5 / gamebook),
  the sportsbook closing total (nflverse), and the final score.
- Kalshi KXNFLTOTAL ladders ("Over X.5", strikes every 3 points), cached 1-minute candles.

Outputs (DuckDB + reports/h4a_nfl_weather_{season}.md)
- Kalshi implied total (the strike where P(over) = 0.5, from the bid/ask mid ladder) at T-24h/-6h/-1h/-5m.
- Regressions of (actual - book close), (actual - Kalshi T-5m), (Kalshi - book) on the study's weather terms.
- Paper trade: buy the under (NO on the strike nearest the book line) at the ask at T-5m, net of fees.

Caveat inherited from the weather study: weather is the observed kickoff weather; bettors only have the
forecast. Kalshi at T-5m is effectively a closing price, so comparing against it is fair. No lookahead:
every Kalshi price is the last candle with end_ts <= the snapshot time.
"""
from __future__ import annotations

import bisect
import logging
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from ..context import Context
from ..fees import order_fee
from ..games import EVENT_RE, MONTHS
from ..kalshi.ingest import ceil_minute, floor_minute
from ..settings import DB_PATH, REPORTS_DIR, parse_ts
from ..stats import mean_se, ols_hc1

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
SNAPSHOTS = {"T-24h": (1440, 180), "T-6h": (360, 120), "T-1h": (60, 60), "T-5m": (5, 30)}  # offset, max staleness (min)
WINDOW_BEFORE_MIN = 30 * 60
STRIKE_RADIUS = 10.5
MAX_SPREAD = Decimal("0.10")
TRADE_LOT = 100
RAIN_IN, SNOW_IN = 0.06, 0.10          # same thresholds as the weather study (nflweather.features)


def weather_terms(g: dict) -> dict:
    """Replicates nflweather.features.add_weather_features for one game."""
    out = int(g.get("wx_src") in ("gamebook", "era5"))
    w = g.get("wx_wind") if g.get("wx_wind") is not None else 0.0
    t = g.get("wx_temp") if g.get("wx_temp") is not None else 65.0
    snow = (g.get("wx_snow") or 0) >= SNOW_IN
    return {
        "outdoor": out, "indoor": 1 - out,
        "wind_10_14": out * int(10 <= w < 15), "wind_15_19": out * int(15 <= w < 20), "wind_20p": out * int(w >= 20),
        "wind_15p": out * int(w >= 15),
        "temp_le32": out * int(t <= 32), "temp_33_45": out * int(32 < t <= 45), "temp_80p": out * int(t >= 80),
        "snow": out * int(snow), "rain": out * int(((g.get("wx_precip") or 0) >= RAIN_IN) and not snow),
        "wind_mph": out * w, "cold_deg": out * max(50 - t, 0),
    }


def wind_bucket(g: dict) -> str:
    if not g["outdoor"]:
        return "dome/closed"
    w = g.get("wx_wind") or 0
    return "wind 15+" if w >= 15 else "wind 10-14" if w >= 10 else "wind 5-9" if w >= 5 else "wind 0-4"


def pava_decreasing(ps: list[float]) -> list[float]:
    """Pool-adjacent-violators: closest non-increasing sequence (P(over) must fall as the strike rises)."""
    blocks = [[p, 1] for p in ps]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] < blocks[i + 1][0]:
            (a, na), (b, nb) = blocks[i], blocks[i + 1]
            blocks[i:i + 2] = [[(a * na + b * nb) / (na + nb), na + nb]]
            i = max(i - 1, 0)
        else:
            i += 1
    return [v for v, n in blocks for _ in range(n)]


def interp_strike_at(strikes: list[float], ps: list[float], target: float = 0.5) -> float | None:
    """Strike where the (monotone) P(over) ladder crosses `target`; None if not bracketed."""
    for (s1, p1), (s2, p2) in zip(zip(strikes, ps), zip(strikes[1:], ps[1:])):
        if p1 >= target >= p2 and p1 != p2:
            return s1 + (p1 - target) / (p1 - p2) * (s2 - s1)
        if p1 == target:
            return s1
    return None


def interp_p_at(strikes: list[float], ps: list[float], x: float) -> float | None:
    if not strikes or x < strikes[0] or x > strikes[-1]:
        return None
    j = bisect.bisect_left(strikes, x)
    if strikes[j] == x:
        return ps[j]
    s1, s2, p1, p2 = strikes[j - 1], strikes[j], ps[j - 1], ps[j]
    return p1 + (p2 - p1) * (x - s1) / (s2 - s1)


def asof(candles: list[dict], ts: int, max_age_s: int) -> dict | None:
    """Last candle with end_ts <= ts (no lookahead), if not older than max_age_s."""
    ends = [c["end_period_ts"] for c in candles]
    j = bisect.bisect_right(ends, ts) - 1
    if j < 0 or ts - ends[j] > max_age_s:
        return None
    return candles[j]


def _px(side: dict, key: str) -> Decimal | None:
    v = side.get(key, side.get(f"{key}_dollars"))
    return Decimal(str(v)) if v is not None else None


def load_study_games(nfl_dir: Path, season: int) -> list[dict]:
    path = Path(nfl_dir) / "data" / "processed" / "games.parquet"
    con = duckdb.connect()
    rel = con.sql(f"select * from read_parquet('{path}') where season = {int(season)} and result is not null")
    cols = rel.columns
    return [dict(zip(cols, r)) for r in rel.fetchall()]


def split_tail(tail: str, codes: set[str]) -> tuple[str, str] | None:
    """'NYGNE' -> ('NYG', 'NE') using known Kalshi codes; None if no split or ambiguous."""
    splits = [(tail[:i], tail[i:]) for i in range(2, len(tail) - 1) if tail[:i] in codes and tail[i:] in codes]
    return splits[0] if len(splits) == 1 else None


def match_study_game(study_by_pair: dict, away: str, home: str, ticker_date, max_shift_days: int = 3):
    """Nearest study game with the same team pair within +/- max_shift_days.

    Kalshi keeps the originally scheduled date in some tickers (e.g. Week 18 games flexed to Saturday)."""
    cands = [(abs((d - ticker_date).days), d, g) for d, g in study_by_pair.get(frozenset((away, home)), [])
             if abs((d - ticker_date).days) <= max_shift_days]
    if not cands:
        return None, None
    shift, d, g = min(cands, key=lambda c: c[0])
    return g, (d - ticker_date).days


def run_h4a(nfl_dir: Path, season: int = 2025, as_of: str = "v1") -> dict:
    ctx = Context("nfl", as_of)
    totals_series = ctx.cfg.totals_series
    season_cfg = ctx.cfg.seasons[str(season)]
    study = load_study_games(nfl_dir, season)
    study_by_pair: dict[frozenset, list] = defaultdict(list)
    for g in study:
        study_by_pair[frozenset((g["away_team"], g["home_team"]))].append((date.fromisoformat(str(g["gameday"])), g))
    kalshi_codes = set(ctx.teams.by_kalshi)

    listed: dict[str, dict] = {}
    for historical in (False, True):          # a market listed in both places is routed to /historical
        for m in ctx.kalshi.markets(totals_series, historical=historical, as_of=as_of):
            listed[m["ticker"]] = {**m, "_endpoint": "historical" if historical else "live"}
    ladders: dict[str, list[dict]] = defaultdict(list)
    for m in listed.values():
        ladders[m["event_ticker"]].append(m)

    rows, unmatched = [], []
    skipped = Counter()
    for ev, mks in sorted(ladders.items()):
        parsed = EVENT_RE.match(ev)
        if not parsed:
            unmatched.append((ev, "unparseable ticker"))
            continue
        ticker_date = date(2000 + int(parsed["yy"]), MONTHS[parsed["mon"]], int(parsed["dd"]))
        if not (season_cfg.events_from <= ticker_date <= season_cfg.events_to):
            skipped["other season"] += 1
            continue
        if ticker_date < season_cfg.regular_start:
            skipped["preseason (not in study data)"] += 1
            continue
        pair = split_tail(parsed["tail"], kalshi_codes)
        if pair is None:
            unmatched.append((ev, f"cannot split team codes from {parsed['tail']!r}"))
            continue
        away, home = (ctx.teams.from_kalshi(c) for c in pair)
        sg, date_shift = match_study_game(study_by_pair, away, home, ticker_date)
        if sg is None:
            unmatched.append((ev, f"no study game for {away}@{home} within 3 days of {ticker_date}"))
            continue
        kickoff = datetime.fromisoformat(f"{sg['gameday']}T{sg['gametime']}").replace(tzinfo=ET).astimezone(ZoneInfo("UTC"))
        est = parse_ts(min(m["expected_expiration_time"] for m in mks)) - timedelta(hours=ctx.cfg.tip_offset_hours)
        line = float(sg["total_line"])
        strikes = sorted((float(m["floor_strike"]), m) for m in mks if m.get("floor_strike") is not None)
        near = [(s, m) for s, m in strikes if abs(s - line) <= STRIKE_RADIUS]
        candles = {}
        for s, m in near:
            start = max(floor_minute(parse_ts(m["open_time"])), floor_minute(kickoff - timedelta(minutes=WINDOW_BEFORE_MIN)))
            end = ceil_minute(kickoff)
            candles[s] = ctx.kalshi.candles(market_ticker=m["ticker"], series_ticker=totals_series, start_ts=start,
                                            end_ts=end, period_min=1, historical=m["_endpoint"] == "historical",
                                            data_date=str(sg["gameday"]))
        row = {"event_ticker": ev, "game_id": sg["game_id"], "game_type": sg["game_type"], "gameday": str(sg["gameday"]),
               "away": sg["away_team"], "home": sg["home_team"], "kickoff_utc": kickoff,
               "kickoff_vs_kalshi_est_min": (kickoff - est).total_seconds() / 60, "ticker_date_shift_days": date_shift,
               "total": float(sg["total"]), "book_close": line, "wx_wind": sg.get("wx_wind"), "wx_temp": sg.get("wx_temp"),
               "n_strikes_used": len(near), **weather_terms(sg)}
        row["bucket"] = wind_bucket(row)
        for label, (offset, max_age) in SNAPSHOTS.items():
            ts = int((kickoff - timedelta(minutes=offset)).timestamp())
            pts = []
            for s, _ in near:
                c = asof(candles[s], ts, max_age * 60)
                if not c:
                    continue
                bid, ask = _px(c["yes_bid"], "close"), _px(c["yes_ask"], "close")
                if bid is None or ask is None or ask - bid > MAX_SPREAD or ask <= 0:
                    continue
                pts.append((s, float((bid + ask) / 2), bid, ask))
            strikes_ok = [p[0] for p in pts]
            mono = pava_decreasing([p[1] for p in pts]) if pts else []
            row[f"kalshi_total_{label}"] = interp_strike_at(strikes_ok, mono) if len(pts) >= 2 else None
            row[f"p_over_at_line_{label}"] = interp_p_at(strikes_ok, mono, line) if len(pts) >= 2 else None
            row[f"n_quotes_{label}"] = len(pts)
            if label == "T-5m":
                row.update(_under_trade(pts, line, row["total"]))
        rows.append(row)
    return _analyze(rows, unmatched, season, len(study), skipped)


def _under_trade(pts: list[tuple], line: float, total: float) -> dict:
    """Buy NO on the strike nearest the book line at the NO ask (= 1 - YES bid); 100-lot, per-order fee."""
    if not pts:
        return {"trade_strike": None}
    s, _, bid, ask = min(pts, key=lambda p: (abs(p[0] - line), p[0]))
    no_ask = Decimal(1) - bid
    fee = order_fee([(TRADE_LOT, no_ask)], multiplier=1, fee_type="quadratic_with_maker_fees") / TRADE_LOT
    yes_fee = order_fee([(TRADE_LOT, ask)], multiplier=1, fee_type="quadratic_with_maker_fees") / TRADE_LOT
    under_win = total < s
    return {"trade_strike": s, "no_ask": float(no_ask), "under_win": int(under_win),
            "under_pnl": float((1 if under_win else 0) - no_ask - fee),
            "over_pnl": float((1 if total > s else 0) - ask - yes_fee), "fee_per_contract": float(fee)}


def _analyze(rows: list[dict], unmatched: list, season: int, n_study: int, skipped: Counter) -> dict:
    valid = [r for r in rows if r.get("kalshi_total_T-5m") is not None]
    for r in valid:
        r["resid_book"] = r["total"] - r["book_close"]
        r["resid_kalshi"] = r["total"] - r["kalshi_total_T-5m"]
        r["kalshi_minus_book"] = r["kalshi_total_T-5m"] - r["book_close"]
        k24 = r.get("kalshi_total_T-24h")
        r["kalshi_move_24h"] = r["kalshi_total_T-5m"] - k24 if k24 is not None else None

    candidates = {"bins": ["wind_10_14", "wind_15p", "temp_le32", "rain", "snow", "indoor"],
                  "linear": ["wind_mph", "cold_deg", "rain", "snow", "indoor"]}
    dropped = sorted({t for ts in candidates.values() for t in ts if all(r[t] == 0 for r in valid)})
    regs = []
    for spec, all_terms in candidates.items():
        terms = [t for t in all_terms if t not in dropped]
        for y in ("resid_book", "resid_kalshi", "kalshi_minus_book"):
            for res in ols_hc1([r[y] for r in valid], [[r[t] for t in terms] for r in valid], terms):
                regs.append({"spec": spec, "outcome": y, **res})

    buckets = []
    for b in ["wind 0-4", "wind 5-9", "wind 10-14", "wind 15+", "dome/closed"]:
        s = [r for r in valid if r["bucket"] == b]
        trades = [r for r in s if r.get("trade_strike") is not None]
        row = {"bucket": b, "games": len(s)}
        for k in ("resid_book", "resid_kalshi", "kalshi_minus_book", "kalshi_move_24h", "p_over_at_line_T-5m"):
            m, se, n = mean_se([r.get(k) for r in s])
            row[k], row[f"{k}_se"] = m, se
        for side in ("under", "over"):
            m, se, n = mean_se([r[f"{side}_pnl"] for r in trades])
            row[f"{side}_trades"], row[f"{side}_ev"], row[f"{side}_ev_se"] = n, m, se
        row["under_win_rate"] = mean_se([r["under_win"] for r in trades])[0]
        buckets.append(row)

    n_variants = 5 * 2 + 2 * 3   # buckets x trade sides + regression specs x outcomes
    con = duckdb.connect(str(DB_PATH))
    con.execute("create schema if not exists research")
    for name, data in (("h4a_games", rows), ("h4a_regression", regs), ("h4a_buckets", buckets)):
        _replace_table(con, f"research.{name}", data)
    con.close()
    report = _write_report(season, n_study, rows, valid, unmatched, regs, buckets, n_variants, skipped, dropped)
    return {"rows": rows, "valid": valid, "unmatched": unmatched, "regs": regs, "buckets": buckets,
            "n_variants": n_variants, "report": report, "skipped": skipped, "dropped": dropped}


def _replace_table(con, name: str, data: list[dict]) -> None:
    import pyarrow as pa
    if not data:
        return
    keys = list(dict.fromkeys(k for d in data for k in d))
    table = pa.Table.from_pylist([{k: d.get(k) for k in keys} for d in data])
    con.register("_tmp", table)
    con.execute(f"create or replace table {name} as select * from _tmp")
    con.unregister("_tmp")


def _f(x, nd=2, signed=True):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:+.{nd}f}" if signed else f"{x:.{nd}f}"


def _write_report(season, n_study, rows, valid, unmatched, regs, buckets, n_variants, skipped, dropped) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"h4a_nfl_weather_{season}.md"
    shifted = sum(1 for r in rows if r.get("ticker_date_shift_days"))
    lines = [f"# H4a — Kalshi NFL totals vs wind, {season} season",
             "",
             f"- Study games (played): {n_study}; Kalshi total ladders matched: {len(rows)}; "
             f"with a valid T-5m Kalshi implied total: {len(valid)}; unmatched in-season Kalshi events: {len(unmatched)}",
             f"- Skipped Kalshi events (logged, not errors): {dict(skipped)}; matched with a ticker-date shift "
             f"(flexed games): {shifted}",
             f"- Terms dropped (no variation in this sample): {dropped or 'none'}",
             f"- n_variants_tested: {n_variants} (5 buckets x 2 trade sides + 2 specs x 3 outcomes)",
             "- Weather = observed kickoff weather (study caveat). Kalshi prices = last 1-min candle at or before the snapshot.",
             "",
             "## Regression: points vs weather terms (HC1 SEs, one season, no fixed effects)",
             "| spec | term | actual − book close | actual − Kalshi T-5m | Kalshi − book |",
             "|---|---|---|---|---|"]
    by = {(r["spec"], r["outcome"], r["term"]): r for r in regs}
    for spec in ("bins", "linear"):
        terms = [r["term"] for r in regs if r["spec"] == spec and r["outcome"] == "resid_book" and r["term"] != "const"]
        for t in terms:
            cells = []
            for y in ("resid_book", "resid_kalshi", "kalshi_minus_book"):
                r = by[(spec, y, t)]
                cells.append(f"{_f(r['coef'])} ({_f(r['se'], signed=False)}), p={_f(r['p'], 3, False)}")
            lines.append(f"| {spec} | {t} | " + " | ".join(cells) + " |")
    lines += ["", "## By wind bucket (means ± SE)",
              "| bucket | games | actual − book | actual − Kalshi | Kalshi − book | Kalshi move T-24h→T-5m | Kalshi P(over @ book line) | under EV/contract (n) | under win % | over EV/contract |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for b in buckets:
        lines.append(
            f"| {b['bucket']} | {b['games']} | {_f(b['resid_book'])} ± {_f(b['resid_book_se'], signed=False)} | "
            f"{_f(b['resid_kalshi'])} ± {_f(b['resid_kalshi_se'], signed=False)} | {_f(b['kalshi_minus_book'])} ± {_f(b['kalshi_minus_book_se'], signed=False)} | "
            f"{_f(b['kalshi_move_24h'])} ± {_f(b['kalshi_move_24h_se'], signed=False)} | {_f(b['p_over_at_line_T-5m'], 3, False)} | "
            f"{_f(b['under_ev'], 3)} ± {_f(b['under_ev_se'], 3, False)} ({b['under_trades']}) | {_f(b['under_win_rate'], 3, False)} | "
            f"{_f(b['over_ev'], 3)} ± {_f(b['over_ev_se'], 3, False)} |")
    if unmatched:
        lines += ["", "## Unmatched Kalshi total events", *[f"- {e}: {why}" for e, why in unmatched]]
    path.write_text("\n".join(lines) + "\n")
    return path
