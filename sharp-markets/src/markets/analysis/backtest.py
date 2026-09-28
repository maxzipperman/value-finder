"""H1 (static edge) and H2 (post-sharp-move lag) paper backtests.

Fill model (approved): signal at minute t uses data <= t; the order takes liquidity during the following
minutes at the ask prevailing at the start of each minute (never below the decision ask), capped by
`participation` x YES-taker volume that actually traded in that minute; it keeps taking for up to
`fill_window_min` minutes while the signal still holds, and never after tip. Each minute is a separate
order for fee rounding. One entry per market per variant (first qualifying signal).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal

from ..fees import order_fee
from .data import MarketSeries, SharpSeries

TAKER_RATE = 0.07


def variant_id(params: dict) -> str:
    return hashlib.sha1(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:12]


def fair_at(ms: MarketSeries, i: int, fair_key: str) -> float | None:
    return (ms.pin if fair_key == "pinnacle" else ms.blend)[i]


def edge_at(ms: MarketSeries, i: int, fair_key: str) -> float | None:
    fair, ask = fair_at(ms, i, fair_key), ms.ask[i]
    if fair is None or ask is None:
        return None
    a = float(ask)
    return fair - a - TAKER_RATE * float(ms.fee_multiplier) * a * (1 - a)


@dataclass
class FillParams:
    stake: Decimal
    participation: Decimal
    window: int
    rounding: str


def simulate_fill(ms: MarketSeries, i: int, fair_key: str, min_edge: float, fp: FillParams) -> dict:
    ask0 = ms.ask[i]
    qty_req = int((fp.stake / ask0).to_integral_value(rounding=ROUND_FLOOR)) if ask0 else 0
    fills, remaining = [], qty_req
    for j in range(1, fp.window + 1):
        k = i + j
        if k >= len(ms.ts) or ms.mtt[k] <= 0 or remaining <= 0:
            break
        d = k - 1                                   # decision minute for this order
        if j > 1:
            e = edge_at(ms, d, fair_key)
            if e is None or e < min_edge:
                break
        dec_ask = ms.ask[d]
        if dec_ask is None:
            break
        price = max(dec_ask, ms.ask_open_raw[k]) if ms.ask_open_raw[k] is not None else dec_ask
        cap = int((fp.participation * ms.yes_taker.get(ms.ts[k], Decimal(0))).to_integral_value(rounding=ROUND_FLOOR))
        q = min(remaining, cap)
        if q > 0:
            fills.append((ms.ts[k], q, price))
            remaining -= q
    qty = sum(q for _, q, _ in fills)
    cost = sum((q * p for _, q, p in fills), Decimal(0))
    fees = sum((order_fee([(q, p)], multiplier=ms.fee_multiplier, fee_type="quadratic_with_maker_fees",
                          rounding=fp.rounding) for _, q, p in fills), Decimal(0))
    return {"qty_req": qty_req, "qty": qty, "cost": cost, "fees": fees, "n_fill_minutes": len(fills),
            "avg_price": (cost / qty) if qty else None, "first_fill_ts": fills[0][0] if fills else None}


def bet_record(ms: MarketSeries, i: int, fair_key: str, fill: dict, extra: dict) -> dict:
    fair0 = fair_at(ms, i, fair_key)
    close = ms.close_fair.get(fair_key)
    rec = {"market_ticker": ms.market_ticker, "game_id": ms.game_id, "team_code": ms.team_code, "split": ms.split,
           "signal_ts": ms.ts[i], "minutes_to_tip": ms.mtt[i], "ask_at_signal": float(ms.ask[i]),
           "fair_at_signal": fair0, "edge_at_signal": edge_at(ms, i, fair_key), "close_fair": close,
           "is_favorite": fair0 > 0.5 if fair0 is not None else None, "b2b": ms.b2b, "opp_b2b": ms.opp_b2b,
           "result": ms.result, "qty_req": fill["qty_req"], "qty": fill["qty"], "n_fill_minutes": fill["n_fill_minutes"],
           "filled": fill["qty"] > 0, **extra}
    if fill["qty"] > 0:
        q, avg, fees, cost = fill["qty"], float(fill["avg_price"]), float(fill["fees"]), float(fill["cost"])
        fee_pc = fees / q
        rec.update(avg_price=avg, cost=cost, fees=fees, fee_per_contract=fee_pc,
                   pnl=q * ms.result - cost - fees if ms.result is not None else None,
                   ev_at_entry=q * fair0 - cost - fees if fair0 is not None else None,
                   clv_gross=close - avg if close is not None else None,
                   clv_net=close - avg - fee_pc if close is not None else None,
                   clv_pct=close / avg - 1 if close is not None else None,
                   line_move_clv=close - fair0 if close is not None and fair0 is not None else None)
    return rec


def run_h1(markets: dict[str, MarketSeries], theta: float, fair_key: str, fp: FillParams) -> list[dict]:
    bets = []
    for ms in markets.values():
        for i in range(len(ms.ts)):
            if ms.mtt[i] <= 0:
                break
            e = edge_at(ms, i, fair_key)
            if e is not None and e >= theta:
                bets.append(bet_record(ms, i, fair_key, simulate_fill(ms, i, fair_key, theta, fp), {}))
                break
    return bets


def pinnacle_moves(s: SharpSeries, commence: datetime, X: float, W: int, *, both_directions: bool = False,
                   slack_min: int = 5) -> list[dict]:
    """Moves of >= X in Pinnacle fair prob between snapshot s and the snapshot as of s - W.

    Only valid where the schedule is dense enough: the reference snapshot must be within W + slack of s.
    Cooldown of W after each event for the same series.
    """
    out, next_ok = [], None
    for k, t in enumerate(s.ts):
        if t >= commence or (next_ok is not None and t < next_ok):
            continue
        p = s.asof(t - timedelta(minutes=W))
        if p is None or (t - s.ts[p]) > timedelta(minutes=W + slack_min):
            continue
        delta = s.pin[k] - s.pin[p]
        if delta >= X or (both_directions and delta <= -X):
            lu = s.last_update[k]
            out.append({"t": t, "prev_t": s.ts[p], "delta": delta, "fair_new": s.pin[k], "fair_prev": s.pin[p],
                        "last_update": lu if lu is not None and s.ts[p] < lu <= t else None})
            next_ok = t + timedelta(minutes=W)
    return out


def _mid_asof(ms: MarketSeries, t: datetime, lookback_min: int = 30) -> float | None:
    i = ms.index_asof(t)
    while i is not None and i >= 0 and (t - ms.ts[i]) <= timedelta(minutes=lookback_min):
        if ms.mid[i] is not None:
            return ms.mid[i]
        i -= 1
    return None


def lag_stats(ms: MarketSeries, ev: dict, cap_min: int) -> dict:
    m0 = _mid_asof(ms, ev["prev_t"])
    if m0 is None:
        return {"lag_status": "no_kalshi_mid"}
    gap = ev["fair_new"] - m0
    if gap < 0.01:
        return {"lag_status": "no_gap", "kalshi_mid_before": m0, "gap": gap}
    i0 = ms.index_at_or_after(ev["t"])
    out = {"lag_status": "ok", "kalshi_mid_before": m0, "gap": gap}
    for frac in (0.5, 0.8):
        target = m0 + frac * gap
        lag = None
        if i0 is not None:
            for i in range(i0, len(ms.ts)):
                if (ms.ts[i] - ev["t"]) > timedelta(minutes=cap_min) or ms.mtt[i] <= 0:
                    break
                if ms.mid[i] is not None and ms.mid[i] >= target:
                    lag = (ms.ts[i] - ev["t"]).total_seconds() / 60
                    break
        out[f"lag{int(frac * 100)}_min"] = lag
    out["kalshi_already_moved"] = out.get("lag50_min") == 0
    return out


def run_h2(markets: dict[str, MarketSeries], sharp: dict[tuple[str, str], SharpSeries], X: float, W: int,
           min_edge: float, fp: FillParams, lag_cap_min: int) -> tuple[list[dict], list[dict]]:
    by_game_team = {(ms.game_id, ms.team_code): ms for ms in markets.values()}
    bets, events = [], []
    for (gid, team), s in sharp.items():
        ms = by_game_team.get((gid, team))
        if ms is None:
            continue
        for ev in pinnacle_moves(s, ms.commence, X, W):
            i = ms.index_at_or_after(ev["t"])
            rec = {"game_id": gid, "team_code": team, "market_ticker": ms.market_ticker, "event_ts": ev["t"],
                   "delta": ev["delta"], "fair_new": ev["fair_new"],
                   "minutes_to_tip": (ms.commence - ev["t"]).total_seconds() / 60, **lag_stats(ms, ev, lag_cap_min)}
            if i is not None and ms.mtt[i] > 0:
                e = edge_at(ms, i, "pinnacle")
                rec["edge_at_event"] = e
                if e is not None and e >= min_edge:
                    bets.append(bet_record(ms, i, "pinnacle", simulate_fill(ms, i, "pinnacle", min_edge, fp),
                                           {"event_ts": ev["t"], "delta": ev["delta"]}))
            events.append(rec)
    return bets, events


def summarize(bets: list[dict]) -> dict:
    filled = [b for b in bets if b["filled"]]
    q = sum(b["qty"] for b in filled)
    cost = sum(b["cost"] + b["fees"] for b in filled)
    pnl = [b["pnl"] for b in filled if b.get("pnl") is not None]

    def m(key):
        v = [b[key] for b in filled if b.get(key) is not None]
        if not v:
            return None, None
        mu = sum(v) / len(v)
        se = math.sqrt(sum((x - mu) ** 2 for x in v) / (len(v) - 1) / len(v)) if len(v) > 1 else None
        return mu, se

    clv, clv_se = m("clv_net")
    return {"signals": len(bets), "bets_filled": len(filled), "fill_rate": len(filled) / len(bets) if bets else None,
            "avg_fill_share": (sum(b["qty"] / b["qty_req"] for b in filled if b["qty_req"]) / len(filled)) if filled else None,
            "contracts": q, "capital": cost, "pnl": sum(pnl) if pnl else 0.0,
            "roi": sum(pnl) / cost if cost else None,
            "ev": sum(b["ev_at_entry"] for b in filled if b.get("ev_at_entry") is not None),
            "avg_edge": m("edge_at_signal")[0], "clv_net": clv, "clv_net_se": clv_se,
            "clv_gross": m("clv_gross")[0], "line_move_clv": m("line_move_clv")[0], "clv_pct": m("clv_pct")[0]}
