"""Run H1, H2 and lead-lag for a date range; persist results and write a markdown report."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median

import pyarrow as pa

from ..build.run import connect
from ..context import Context
from ..settings import REPORTS_DIR, utcnow
from ..sport import load_backtest_config
from .backtest import FillParams, run_h1, run_h2, summarize, variant_id
from .data import load_markets, load_sharp
from .leadlag import cross_correlation, kalshi_origin, pinnacle_origin


def _bucket(v, edges, labels):
    if v is None:
        return "n/a"
    for lo, hi, lab in zip(edges, edges[1:] + [float("inf")], labels):
        if lo <= v < hi:
            return lab
    return "below"


def _replace(con, name, rows):
    if not rows:
        con.execute(f"DROP TABLE IF EXISTS {name}")
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    norm = [{k: (json.dumps(r.get(k), default=str) if isinstance(r.get(k), (dict, list)) else
                 float(r[k]) if isinstance(r.get(k), Decimal) else r.get(k)) for k in keys} for r in rows]
    con.register("_tmp", pa.Table.from_pylist(norm))
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp")
    con.unregister("_tmp")


def run_backtest(ctx: Context, start: date, end: date) -> dict:
    bt = load_backtest_config()
    con = connect()
    markets = load_markets(con, start, end, max_spread=bt["kalshi"]["max_spread_for_mid"])
    sharp = load_sharp(con, start, end)
    fp = FillParams(stake=Decimal(str(bt["fills"]["stake_dollars"])), participation=Decimal(str(bt["fills"]["participation"])),
                    window=int(bt["fills"]["fill_window_min"]), rounding=bt["fees"]["rounding"])
    sens = [replace(fp, participation=Decimal(str(p))) for p in bt["fills"]["participation_sensitivity"]]
    run_ts = utcnow()
    splits = sorted({ms.split for ms in markets.values()})
    variants, summaries, all_bets, h2_events = [], [], [], []

    def record(hyp, params, bets, bets_by_sens):
        vid = variant_id({"hypothesis": hyp, **params})
        s = summarize(bets)
        row = {"variant_id": vid, "hypothesis": hyp, **params, **s}
        for f, b in bets_by_sens.items():
            ss = summarize(b)
            row.update({f"fill_rate_p{f}": ss["fill_rate"], f"pnl_p{f}": ss["pnl"], f"roi_p{f}": ss["roi"], f"clv_net_p{f}": ss["clv_net"]})
        summaries.append(row)
        variants.append({"variant_id": vid, "hypothesis": hyp, "params_json": json.dumps(params), "split": ",".join(splits),
                         "run_ts": run_ts, "n_signals": s["signals"], "n_fills": s["bets_filled"]})
        all_bets.extend({**b, "variant_id": vid, "hypothesis": hyp} for b in bets)
        return vid

    for fair_key in bt["h1"]["fair_sources"]:
        for theta in bt["h1"]["edge_thresholds"]:
            bets = run_h1(markets, theta, fair_key, fp)
            record("H1", {"theta": theta, "fair_source": fair_key}, bets,
                   {float(f.participation): run_h1(markets, theta, fair_key, f) for f in sens})
    for X in bt["h2"]["move_pts"]:
        for W in bt["h2"]["windows_min"]:
            bets, evs = run_h2(markets, sharp, X, W, bt["h2"]["min_edge_to_trade"], fp, bt["h2"]["lag_cap_min"])
            vid = record("H2", {"X": X, "W": W}, bets,
                         {float(f.participation): run_h2(markets, sharp, X, W, bt["h2"]["min_edge_to_trade"], f,
                                                         bt["h2"]["lag_cap_min"])[0] for f in sens})
            h2_events.extend({**e, "variant_id": vid, "X": X, "W": W} for e in evs)
    n_variants = len(variants)

    ll = []
    homes = [ms for ms in markets.values() if ms.is_home]
    for X in bt["h2"]["move_pts"]:
        for W in bt["h2"]["windows_min"]:
            for ms in homes:
                s = sharp.get((ms.game_id, ms.team_code))
                if s:
                    ll += pinnacle_origin(ms, s, X, W, bt["leadlag"]["search_min"], bt["leadlag"]["follow_frac"])
                    ll += kalshi_origin(ms, s, X, W, bt["leadlag"]["search_min"], bt["leadlag"]["follow_frac"])
    xcorr = cross_correlation(markets)

    _replace(con, "variants", variants)
    _replace(con, "bt_summary", summaries)
    _replace(con, "bt_bets", all_bets)
    _replace(con, "bt_h2_events", h2_events)
    _replace(con, "bt_leadlag", ll)
    _replace(con, "bt_xcorr", xcorr)
    coverage = _coverage(con, ctx.sport, start, end)
    con.close()
    report = _report(start, end, bt, markets, summaries, all_bets, h2_events, ll, xcorr, coverage, n_variants)
    return {"report": report, "n_variants": n_variants, "summaries": summaries, "coverage": coverage}


def _coverage(con, sport, start, end) -> dict:
    q = lambda s, p=(): con.execute(s, list(p)).fetchall()
    games = q("""SELECT match_status, count(*) FROM games WHERE sport = ? AND game_date_et BETWEEN ? AND ?
                 AND phase = 'regular' GROUP BY 1""", (sport, start, end))
    unmatched = q("""SELECT game_id, away_code, home_code, kalshi_est_tip FROM games WHERE sport = ? AND game_date_et BETWEEN ? AND ?
                     AND phase = 'regular' AND match_status <> 'matched' ORDER BY 1""", (sport, start, end))
    excluded = q("""SELECT x.reason, count(DISTINCT x.game_id) FROM excluded_markets x JOIN games g USING (sport, game_id)
                    WHERE x.sport = ? AND g.game_date_et BETWEEN ? AND ? GROUP BY 1""", (sport, start, end))
    anomalies = q("""SELECT a.kind, a.game_id, a.detail FROM anomalies a LEFT JOIN games g USING (sport, game_id)
                     WHERE a.sport = ? AND (g.game_date_et BETWEEN ? AND ? OR a.game_id IS NULL)
                       AND a.kind NOT IN ('nba_cup_game') ORDER BY 1, 2""", (sport, start, end))
    snaps = q("SELECT count(DISTINCT snapshot_ts), count(DISTINCT requested_ts), min(snapshot_ts), max(snapshot_ts) FROM sharp_odds")
    lu = q("""SELECT bookmaker, count(*), count(market_last_update) FROM sharp_odds GROUP BY 1 ORDER BY 1""")
    tip = q("""SELECT count(*), avg(abs(tip_diff_min)), max(abs(tip_diff_min)), count(*) FILTER (WHERE tip_diff_flag)
               FROM games WHERE sport = ? AND game_date_et BETWEEN ? AND ? AND match_status = 'matched'""", (sport, start, end))
    recon = q("""SELECT count(*), sum(candle_volume), sum(trade_volume), max(abs(diff)) FROM (
                   SELECT c.market_ticker, sum(c.volume) candle_volume, coalesce(sum(t.all_volume), 0) trade_volume,
                          sum(c.volume) - coalesce(sum(t.all_volume), 0) diff
                   FROM kalshi_candles c LEFT JOIN kalshi_yes_taker_1m t
                     ON c.market_ticker = t.market_ticker AND c.end_ts = t.minute_end_ts GROUP BY 1)""")
    return {"games": dict(games), "unmatched": unmatched, "excluded": dict(excluded), "anomalies": anomalies,
            "snapshots": snaps[0], "last_update": lu, "tip": tip[0], "recon": recon[0]}


def _fmt(v, nd=3, pct=False):
    if v is None:
        return "—"
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return f"{v:,}"
    return f"{v * 100:.1f}%" if pct else f"{v:+.{nd}f}" if isinstance(v, float) and nd else str(v)


def _table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers), *["| " + " | ".join(map(str, r)) + " |" for r in rows]]


def _breakdown(bets, keyfn):
    groups = defaultdict(list)
    for b in bets:
        groups[keyfn(b)].append(b)
    return [(k, summarize(v)) for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))]


def _report(start, end, bt, markets, summaries, bets, h2_events, ll, xcorr, cov, n_variants) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"sample_week_{start}_{end}.md"
    e_edges, m_edges = bt["buckets"]["edge"], bt["buckets"]["minutes_to_tip"]
    e_labels = [f"{a*100:.0f}-{b*100:.0f}%" for a, b in zip(e_edges, e_edges[1:])] + [f"{e_edges[-1]*100:.0f}%+"]
    m_labels = ["0-30m", "30-90m", "90-120m", "2-6h", "6-24h", ">24h"]
    snaps, recon, tip = cov["snapshots"], cov["recon"], cov["tip"]
    L = [f"# Sample week {start} → {end} (NBA) — descriptive only (train split)", "",
         f"**n_variants_tested = {n_variants}** (H1: {len(bt['h1']['edge_thresholds'])} thresholds × "
         f"{len(bt['h1']['fair_sources'])} fair sources; H2: {len(bt['h2']['move_pts'])} move sizes × "
         f"{len(bt['h2']['windows_min'])} windows). Participation 100% is a sensitivity case, not a selection variant. "
         "One week cannot validate anything; thresholds get tuned on the full train split only.", "",
         "## Coverage & data quality",
         f"- Regular-season games by match status: {cov['games']}; match rate "
         f"{cov['games'].get('matched', 0) / max(sum(cov['games'].values()), 1):.1%}",
         f"- Unmatched: {[u[0] for u in cov['unmatched']] or 'none'}",
         f"- Excluded games in range by reason: {cov['excluded'] or 'none'}",
         f"- Odds snapshots: {snaps[0]} distinct snapshot times from {snaps[1]} requests ({snaps[2]} → {snaps[3]})",
         f"- market-level `last_update` present: " + ", ".join(f"{b} {n2}/{n1}" for b, n1, n2 in cov["last_update"]),
         f"- Tip-off: {tip[0]} matched games, mean |commence − Kalshi est| {_fmt(tip[1], 1)} min, max {_fmt(tip[2], 1)} min, "
         f"{tip[3]} flagged > 30 min",
         f"- Candle vs trade volume: {recon[0]} markets, candles {recon[1]:,} vs trades {recon[2]:,} contracts, "
         f"max per-market |diff| {recon[3]:,}",
         f"- Markets in analysis: {len(markets)}", "",
         "### Anomalies in range"]
    kinds = Counter(a[0] for a in cov["anomalies"])
    L += [f"- {k}: {n}" for k, n in sorted(kinds.items())]
    for kind, gid, detail in cov["anomalies"]:
        if kind in ("ask_sum_lt_1", "scalar_settlement", "tip_diff_gt_flag", "unmatched_kalshi", "unknown_team_name", "match_conflict"):
            L.append(f"  - `{kind}` {gid or ''}: {detail}")

    def srow(s, extra):
        return [*extra, s["signals"], _fmt(s["fill_rate"], pct=True), _fmt(s.get("fill_rate_p1.0"), pct=True), s["bets_filled"],
                f"{s['contracts']:,}", _fmt(s["avg_edge"]), _fmt(s["ev"], 2), _fmt(s["pnl"], 2), _fmt(s["roi"], pct=True),
                f"{_fmt(s['clv_net'])} ± {_fmt(s['clv_net_se'])}" if s["clv_net"] is not None else "—",
                _fmt(s["line_move_clv"]), _fmt(s.get("pnl_p1.0"), 2), _fmt(s.get("clv_net_p1.0"))]

    hdr = ["signals", "fill rate (25%)", "fill rate (100%)", "bets", "contracts", "avg edge", "EV $", "P&L $", "ROI",
           "CLV net (mean ± SE)", "line-move CLV", "P&L $ @100%", "CLV net @100%"]
    L += ["", "## H1 — static edge (buy YES when fair − ask − fee ≥ θ; first signal per market)",
          *_table(["θ", "fair", *hdr], [srow(s, [s["theta"], s["fair_source"]]) for s in summaries if s["hypothesis"] == "H1"])]
    base = next((s for s in summaries if s["hypothesis"] == "H1" and s["fair_source"] == "pinnacle"
                 and s["theta"] == min(bt["h1"]["edge_thresholds"])), None)
    if base:
        b1 = [b for b in bets if b["variant_id"] == base["variant_id"]]
        for title, fn in (("edge bucket", lambda b: _bucket(b["edge_at_signal"], e_edges, e_labels)),
                          ("minutes to tip", lambda b: _bucket(b["minutes_to_tip"], m_edges, m_labels)),
                          ("favorite / underdog", lambda b: "favorite" if b["is_favorite"] else "underdog"),
                          ("back-to-back", lambda b: f"team b2b={b['b2b']}, opp b2b={b['opp_b2b']}")):
            L += ["", f"### H1 breakdown by {title} (θ={base['theta']}, pinnacle)",
                  *_table([title, "signals", "fill rate", "bets", "contracts", "avg edge", "P&L $", "ROI", "CLV net"],
                          [[k, s["signals"], _fmt(s["fill_rate"], pct=True), s["bets_filled"], f"{s['contracts']:,}",
                            _fmt(s["avg_edge"]), _fmt(s["pnl"], 2), _fmt(s["roi"], pct=True), _fmt(s["clv_net"])]
                           for k, s in _breakdown(b1, fn)])]

    L += ["", "## H2 — trade after a Pinnacle move (buy the team whose fair rose, if edge net of fee ≥ 0)",
          *_table(["X", "W (min)", *hdr], [srow(s, [s["X"], s["W"]]) for s in summaries if s["hypothesis"] == "H2"]),
          "", "### H2 lag of Kalshi after Pinnacle moves (minutes from the snapshot that revealed the move)"]
    rows = []
    by = defaultdict(list)
    for e in h2_events:
        by[(e["X"], e["W"], "late (≤90m)" if e["minutes_to_tip"] <= bt["h2"]["late_news_min"] else "earlier")].append(e)
    for (X, W, when), evs in sorted(by.items()):
        ok = [e for e in evs if e["lag_status"] == "ok"]
        l50 = [e["lag50_min"] for e in ok if e.get("lag50_min") is not None]
        l80 = [e["lag80_min"] for e in ok if e.get("lag80_min") is not None]
        rows.append([X, W, when, len(evs), Counter(e["lag_status"] for e in evs).get("no_gap", 0), len(ok),
                     _fmt(sum(e["kalshi_already_moved"] for e in ok) / len(ok), pct=True) if ok else "—",
                     f"{median(l50):.0f}" if l50 else "—", f"{len(ok) - len(l50)}", f"{median(l80):.0f}" if l80 else "—",
                     _fmt(median([e["gap"] for e in ok]), 3) if ok else "—"])
    L += _table(["X", "W", "timing", "events", "no gap (Kalshi already there)", "with gap", "already ≥50% at detection",
                 "median lag50", "censored lag50", "median lag80", "median gap"], rows)

    L += ["", "## Lead-lag, both directions (home-team market per game)",
          "Classes use snapshot timing (conservative) and, where Pinnacle's market `last_update` is inside the snapshot "
          "interval, last_update timing. A `kalshi_first` that survives last_update timing is the robust signal.", ""]
    rows = []
    groups = defaultdict(list)
    for r in ll:
        groups[(r["origin"], r["X"], r["W"])].append(r)
    for (origin, X, W), rs in sorted(groups.items()):
        for timing in ("snapshot", "last_update"):
            c = Counter(r[f"cls_{timing}"] for r in rs)
            leads = [r[f"lead_min_{timing}"] for r in rs if r.get(f"lead_min_{timing}") is not None
                     and r[f"cls_{timing}"] in ("kalshi_first", "pinnacle_first")]
            rows.append([origin, X, W, timing, len(rs), c.get("pinnacle_first", 0), c.get("kalshi_first", 0),
                         c.get("same_bucket", 0), c.get("no_follow", 0), f"{median(leads):+.0f}" if leads else "—",
                         sum(r["has_last_update"] for r in rs)])
    L += _table(["origin", "X", "W", "timing", "events", "pinnacle first", "kalshi first", "same 5-min bucket",
                 "no follow", "median lead (min, + = Kalshi earlier)", "events with last_update"], rows)
    L += ["", "### Cross-correlation of 5-min changes, final 2h (corr(Δpin_t, Δkalshi_{t+lag}); peak at lag > 0 ⇒ Kalshi follows)",
          *_table(["lag (min)", "n", "corr"], [[x["lag_min"], x["n"], _fmt(x["corr"])] for x in xcorr])]
    path.write_text("\n".join(L) + "\n")
    return path
