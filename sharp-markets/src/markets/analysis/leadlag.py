"""Two-way lead-lag between Pinnacle and Kalshi (descriptive; may look forward — it is not a trade rule).

One market per game (the home team's), so the two mirror-image team markets are not double counted.

Pinnacle-origin events: |Δ pin fair| >= X between snapshot s and the snapshot as of s - W (dense windows only).
  Kalshi crossing time T_K = first minute in (prev_s - search, s + search] where Kalshi's mid has moved
  >= follow_frac x |Δ| from its level at (prev_s - search), in the same direction.
  snapshot timing:   T_K <= prev_s -> kalshi_first; prev_s < T_K <= s -> same_bucket; T_K > s -> pinnacle_first
  last_update timing (when Pinnacle's market last_update falls inside (prev_s, s]): T_K < lu -> kalshi_first else pinnacle_first
Kalshi-origin events: |Δ Kalshi mid| >= X over W minutes (1-min grid). Kalshi half-move time T_K inside the window;
  Pinnacle response = first snapshot s in [start - search, T_K + search] with a >= follow_frac x |Δ| same-direction move
  from its level at (start - search). s <= T_K -> pinnacle_first; prev_s < T_K < s -> same_bucket; prev_s >= T_K -> kalshi_first.
"""
from __future__ import annotations

import math
from datetime import timedelta

from .backtest import _mid_asof, pinnacle_moves
from .data import MarketSeries, SharpSeries


def _bucket(mtt: float) -> str:
    return "0-30m" if mtt <= 30 else "30-90m" if mtt <= 90 else "90m-2h" if mtt <= 120 else "2-6h" if mtt <= 360 else ">6h"


def pinnacle_origin(ms: MarketSeries, s: SharpSeries, X: float, W: int, search: int, frac: float) -> list[dict]:
    out = []
    for ev in pinnacle_moves(s, ms.commence, X, W, both_directions=True):
        d = 1 if ev["delta"] > 0 else -1
        start = ev["prev_t"] - timedelta(minutes=search)
        base = _mid_asof(ms, start)
        rec = {"origin": "pinnacle", "X": X, "W": W, "game_id": ms.game_id, "event_ts": ev["t"], "delta": ev["delta"],
               "mtt_bucket": _bucket((ms.commence - ev["t"]).total_seconds() / 60), "has_last_update": ev["last_update"] is not None}
        tk = None
        if base is not None:
            i0 = ms.index_at_or_after(start + timedelta(minutes=1))
            if i0 is not None:
                for i in range(i0, len(ms.ts)):
                    if ms.ts[i] > ev["t"] + timedelta(minutes=search) or ms.mtt[i] <= 0:
                        break
                    if ms.mid[i] is not None and d * (ms.mid[i] - base) >= frac * abs(ev["delta"]):
                        tk = ms.ts[i]
                        break
        if base is None:
            rec["cls_snapshot"] = rec["cls_last_update"] = "no_kalshi_mid"
        elif tk is None:
            rec["cls_snapshot"] = rec["cls_last_update"] = "no_follow"
        else:
            rec["cls_snapshot"] = "kalshi_first" if tk <= ev["prev_t"] else "same_bucket" if tk <= ev["t"] else "pinnacle_first"
            rec["lead_min_snapshot"] = (ev["t"] - tk).total_seconds() / 60           # + = Kalshi earlier
            lu = ev["last_update"]
            if lu is not None:
                rec["cls_last_update"] = "kalshi_first" if tk < lu else "pinnacle_first"
                rec["lead_min_last_update"] = (lu - tk).total_seconds() / 60
            else:
                rec["cls_last_update"] = rec["cls_snapshot"]
        out.append(rec)
    return out


def kalshi_origin(ms: MarketSeries, s: SharpSeries, X: float, W: int, search: int, frac: float) -> list[dict]:
    out, next_ok = [], None
    for i, t in enumerate(ms.ts):
        if ms.mtt[i] <= 0:
            break
        if next_ok is not None and t < next_ok:
            continue
        j = ms.index_asof(t - timedelta(minutes=W))
        if j is None or ms.mid[i] is None or ms.mid[j] is None or (ms.ts[i] - ms.ts[j]) != timedelta(minutes=W):
            continue
        delta = ms.mid[i] - ms.mid[j]
        if abs(delta) < X:
            continue
        d = 1 if delta > 0 else -1
        next_ok = t + timedelta(minutes=W)
        tk = next(ms.ts[k] for k in range(j + 1, i + 1)
                  if ms.mid[k] is not None and d * (ms.mid[k] - ms.mid[j]) >= frac * abs(delta))
        start = ms.ts[j] - timedelta(minutes=search)
        pb = s.asof(start)
        rec = {"origin": "kalshi", "X": X, "W": W, "game_id": ms.game_id, "event_ts": t, "delta": delta,
               "mtt_bucket": _bucket(ms.mtt[i]), "has_last_update": False}
        if pb is None:
            rec["cls_snapshot"] = rec["cls_last_update"] = "no_pinnacle_line"
            out.append(rec)
            continue
        hit = None
        for k in range(pb + 1, len(s.ts)):
            if s.ts[k] > tk + timedelta(minutes=search):
                break
            if d * (s.pin[k] - s.pin[pb]) >= frac * abs(delta):
                hit = k
                break
        if hit is None:
            rec["cls_snapshot"] = rec["cls_last_update"] = "no_follow"
        else:
            sp, sprev = s.ts[hit], s.ts[hit - 1]
            rec["cls_snapshot"] = "pinnacle_first" if sp <= tk else "same_bucket" if sprev < tk else "kalshi_first"
            rec["lead_min_snapshot"] = (sp - tk).total_seconds() / 60               # + = Kalshi earlier
            lu = s.last_update[hit]
            if lu is not None and sprev < lu <= sp:
                rec["has_last_update"] = True
                rec["cls_last_update"] = "kalshi_first" if tk < lu else "pinnacle_first"
                rec["lead_min_last_update"] = (lu - tk).total_seconds() / 60
            else:
                rec["cls_last_update"] = rec["cls_snapshot"]
        out.append(rec)
    return out


def cross_correlation(markets: dict[str, MarketSeries], window_min: int = 120, step: int = 5, max_lag: int = 12) -> list[dict]:
    """corr(Δpin_t, Δmid_{t+k}) on a 5-min grid over the final `window_min` before tip, pooled over games.
    Positive k with the peak => Kalshi follows Pinnacle."""
    pairs: dict[int, list[tuple[float, float]]] = {k: [] for k in range(-max_lag, max_lag + 1)}
    for ms in markets.values():
        if not ms.is_home:
            continue
        grid = [ms.commence - timedelta(minutes=window_min - step * n) for n in range(window_min // step + 1)]

        def val(series, t):
            i = ms.index_asof(t)
            return series[i] if i is not None and (t - ms.ts[i]) <= timedelta(minutes=1) else None

        dp, dk = [], []
        for t in grid:
            p1, p0 = val(ms.pin, t), val(ms.pin, t - timedelta(minutes=step))
            k1, k0 = val(ms.mid, t), val(ms.mid, t - timedelta(minutes=step))
            dp.append(p1 - p0 if p1 is not None and p0 is not None else None)
            dk.append(k1 - k0 if k1 is not None and k0 is not None else None)
        for lag in pairs:
            for n in range(len(grid)):
                m = n + lag
                if 0 <= m < len(grid) and dp[n] is not None and dk[m] is not None:
                    pairs[lag].append((dp[n], dk[m]))
    out = []
    for lag, xy in sorted(pairs.items()):
        n = len(xy)
        if n < 3:
            out.append({"lag_min": lag * step, "n": n, "corr": None})
            continue
        mx, my = sum(x for x, _ in xy) / n, sum(y for _, y in xy) / n
        sxy = sum((x - mx) * (y - my) for x, y in xy)
        sxx, syy = sum((x - mx) ** 2 for x, _ in xy), sum((y - my) ** 2 for _, y in xy)
        out.append({"lag_min": lag * step, "n": n, "corr": sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None})
    return out
