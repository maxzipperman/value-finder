"""MADE-UP F1 cache of F1's real shape, for a size and speed test of the price engine. NOTHING IN IT IS DATA.

Kickoff times and team names come from the committed processed game tables (2020-2025 only; 2026 rows are
filtered out on read and never looked at). Every price, line and last_update is invented here.

Usage (from the worktree's sharp-markets folder):
  uv run python gen_cache.py DATA_DIR [--horizon-days 21] [--fcs] [--workers 6]

Writes DATA_DIR/raw/_schedules/{sport}.parquet (the saved schedules `markets price-engine` plans F1 from) and
one cache record per planned F1 call under DATA_DIR/raw/{sport}/oddsapi/hist_odds/{date}/{key}.parquet, in the
cache's own format (markets.cache.RawCache.get_or_fetch, zstd-compressed parquet).

What a snapshot lists: every game of that sport whose kickoff is between 3.5 hours before the snapshot (in-play
games) and HORIZON days after it; ten books (a few missing per game and per market); h2h, spreads, totals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pandas as pd

from markets.cache import Fetched, RawCache
from markets.oddsapi import bulk

UTC = timezone.utc
WT = Path("/Users/maxzipperman/code/value-finder/.claude/worktrees/wf_4496c14b-845-2")
CFBRAW = Path("/Users/maxzipperman/code/value-finder/cfb-weather/data/raw/cfbfastr")   # read-only
NFL, CFB = "americanfootball_nfl", "americanfootball_ncaaf"
BOOKS = ["pinnacle", "lowvig", "betonlineag", "draftkings", "fanduel", "betmgm", "williamhill_us", "fanatics",
         "betrivers", "espnbet"]
TITLES = {"pinnacle": "Pinnacle", "lowvig": "LowVig.ag", "betonlineag": "BetOnline.ag", "draftkings": "DraftKings",
          "fanduel": "FanDuel", "betmgm": "BetMGM", "williamhill_us": "Caesars", "fanatics": "Fanatics",
          "betrivers": "BetRivers", "espnbet": "ESPN BET"}
SPORT_TITLE = {NFL: "NFL", CFB: "NCAAF"}
INPLAY = timedelta(hours=3, minutes=30)
FAKE_2026_UNTIL = pd.Timestamp("2026-09-29T06:00:00Z")


def _id(*parts) -> str:
    return hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()


# ------------------------------------------------------------------ schedules (kickoffs only, 2020-2025)
def nfl_schedule() -> pd.DataFrame:
    g = pd.read_parquet(WT / "nfl-weather/data/processed/games.parquet",
                        columns=["season", "gameday", "gametime", "home_team", "away_team"])
    g = g[g.season.between(2020, 2025)].copy()
    names = dict(pd.read_csv(WT / "sharp-markets/config/teams/nfl.csv")[["code", "name"]].values)
    local = pd.to_datetime(g.gameday + " " + g.gametime)
    g["kick"] = local.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert(UTC)
    wft = g.season <= 2021
    g["home"] = [("Washington Football Team" if w and c == "WAS" else names[c]) for c, w in zip(g.home_team, wft)]
    g["away"] = [("Washington Football Team" if w and c == "WAS" else names[c]) for c, w in zip(g.away_team, wft)]
    g["sport"] = NFL
    return g[["sport", "season", "kick", "home", "away"]].dropna(subset=["kick"])


def cfb_schedule(fcs: bool) -> pd.DataFrame:
    g = pd.read_parquet(WT / "cfb-weather/data/processed/games.parquet",
                        columns=["season", "start_utc", "home_team", "away_team", "home_division", "away_division"])
    g = g[g.season.between(2020, 2025)].copy()
    keep = {"fbs", "fcs"} if fcs else {"fbs"}
    g = g[g.home_division.isin(keep) | g.away_division.isin(keep)]
    # made-up bowls for 2020-2022 (the processed table stops before them): 2023's games after Dec 10, moved back
    # by whole 52-week steps so weekdays stay put
    b23 = g[(g.season == 2023) & (g.start_utc > pd.Timestamp("2023-12-10", tz=UTC))]
    bowls = [b23.assign(season=s, start_utc=b23.start_utc - pd.Timedelta(days=364 * (2023 - s))) for s in (2020, 2021, 2022)]
    g = pd.concat([g] + bowls, ignore_index=True)
    mascot = {}
    for f in sorted(CFBRAW.glob("team_info_*.parquet")):
        ti = pd.read_parquet(f, columns=["school", "mascot"])
        mascot.update({s: m for s, m in zip(ti.school, ti.mascot) if isinstance(m, str) and m})
    nm = lambda s: f"{s} {mascot[s]}" if s in mascot else s          # noqa: E731
    g["home"], g["away"] = g.home_team.map(nm), g.away_team.map(nm)
    g["sport"], g["kick"] = CFB, g.start_utc
    return g[["sport", "season", "kick", "home", "away"]]


def schedules(fcs: bool) -> pd.DataFrame:
    g = pd.concat([nfl_schedule(), cfb_schedule(fcs)], ignore_index=True)
    # made-up sealed 2026 games: 2025's schedule moved 52 weeks on, only those already played by Sep 29, 2026
    fake = g[g.season == 2025].assign(season=2026)
    fake["kick"] = fake.kick + pd.Timedelta(days=364)
    fake = fake[fake.kick <= FAKE_2026_UNTIL]
    g = pd.concat([g, fake], ignore_index=True)
    g["kick"] = pd.to_datetime(g.kick, utc=True).dt.floor("min")
    g["id"] = [_id(s, se, h, a, k.isoformat()) for s, se, h, a, k in zip(g.sport, g.season, g.home, g.away, g.kick)]
    g = g.drop_duplicates("id").sort_values(["sport", "kick", "id"]).reset_index(drop=True)
    rng = np.random.default_rng(20261001)
    n = len(g)
    cfb = (g.sport == CFB).to_numpy()
    # made-up game parameters
    g["s0"] = np.round(np.where(cfb, rng.normal(-6, 14, n), rng.normal(-2, 6, n)) * 2) / 2
    g["t0"] = np.round(np.where(cfb, rng.normal(55, 8, n), rng.normal(45, 4, n)) * 2) / 2
    for k in ("s", "t"):
        g[f"{k}_amp"] = rng.uniform(0, 1.5, n)
        g[f"{k}_per"] = rng.uniform(48, 200, n)
        g[f"{k}_ph"] = rng.uniform(0, 2 * np.pi, n)
        g[f"{k}_jump"] = np.where(rng.random(n) < 0.3, rng.choice([-1.5, -1, -0.5, 0.5, 1, 1.5], n), 0.0)
        g[f"{k}_jt"] = rng.uniform(0, 168, n)
    g["q_ph"] = rng.uniform(0, 2 * np.pi, n)
    # kickoffs that move: 5% listed at another hour until 6 days out; 0.5% postponed two days (listed early)
    mv = rng.random(n)
    shift_h = np.where(mv < 0.05, rng.choice([-4, -3, -2, -1, 1, 2, 3, 4], n), 0) * 3600
    shift_h = np.where(mv > 0.995, -48 * 3600, shift_h)
    g["early_shift_s"] = shift_h
    g["early_until_h"] = np.where(mv > 0.995, 72.0, 144.0)      # hours before the true kickoff
    # books that never quote a game (Pinnacle skips more small college games)
    absent = rng.random((n, len(BOOKS))) < 0.08
    absent[:, 0] = rng.random(n) < np.where(cfb, 0.10, 0.02)
    g["absent"] = [a.tobytes() for a in absent]
    return g


def save_schedules(g: pd.DataFrame, raw: Path) -> None:
    for sport in (NFL, CFB):
        s = g[g.sport == sport]
        games = [{"id": i, "sport": sport, "commence_time": k.to_pydatetime(), "home_team": h, "away_team": a,
                  "first_seen": None} for i, k, h, a in zip(s.id, s.kick, s.home, s.away)]
        bulk.save_schedule(raw, sport, games)


# ------------------------------------------------------------------ bodies
def _drift(tau, amp, per, ph, jump, jt):
    return amp * np.sin(2 * np.pi * tau / per + ph) + np.where(tau < jt, jump, 0.0)


def _r2(x):
    return np.round(x * 2) / 2


def _prices(pa, vig):
    """two decimal prices for fair P(side a) = pa and total overround vig, as the books show them (2 decimals)"""
    a = np.clip(pa + vig / 2, 0.012, 0.99)
    b = np.clip(1 - pa + vig / 2, 0.012, 0.99)
    return np.maximum(np.round(1 / a, 2), 1.01), np.maximum(np.round(1 / b, 2), 1.01)


G: pd.DataFrame | None = None
CACHE: RawCache | None = None


def _init(gpath: str, raw: str) -> None:
    global G, CACHE
    G = pd.read_pickle(gpath)
    CACHE = RawCache(Path(raw))


def body(sport: str, at: datetime) -> str:
    grid = 600 if at < datetime(2022, 9, 1, tzinfo=UTC) else 300
    ts = datetime.fromtimestamp(int(at.timestamp()) // grid * grid, UTC)
    rng = np.random.default_rng(int(_id(sport, ts.isoformat())[:12], 16))
    s = G[G.sport == sport]
    lo, hi = np.searchsorted(s.kick.values, np.datetime64(pd.Timestamp(ts - INPLAY).tz_convert(None)), "left"), \
        np.searchsorted(s.kick.values, np.datetime64(pd.Timestamp(ts + HORIZON).tz_convert(None)), "right")
    s = s.iloc[lo:hi]
    n, nb = len(s), len(BOOKS)
    tau = ((s.kick - pd.Timestamp(ts)).dt.total_seconds() / 3600).to_numpy()
    cfb = sport == CFB
    tau2 = tau[:, None] + np.zeros((1, nb))
    stale = rng.random((n, nb)) < 0.15
    tau_b = np.where(stale, tau2 + 24, tau2)                          # a stale book shows yesterday's line
    col = lambda c: s[c].to_numpy()[:, None]                          # noqa: E731
    sp = _r2(col("s0") + _drift(tau_b, col("s_amp"), col("s_per"), col("s_ph"), col("s_jump"), col("s_jt")))
    tt = _r2(col("t0") + _drift(tau_b, col("t_amp"), col("t_per"), col("t_ph"), col("t_jump"), col("t_jt")))
    sharp = np.zeros(nb, bool)
    sharp[:3] = True
    off_p = np.array([0.0, 0.5, 1.0, 1.5])
    for arr in (sp, tt):                                              # some books hang a different number
        k = rng.random((n, nb))
        o = np.where(k < 0.08, off_p[1], np.where(k < 0.13, off_p[2], np.where(k < 0.15, off_p[3], 0.0)))
        o = np.where(sharp[None, :], np.where(k < 0.15, 0.5, 0.0), o) * rng.choice([-1, 1], (n, nb))
        o[:, 0] = 0.0
        arr += o
    sp[:, 0] = _r2(s.s0.to_numpy() + _drift(tau, s.s_amp.to_numpy(), s.s_per.to_numpy(), s.s_ph.to_numpy(),
                                           s.s_jump.to_numpy(), s.s_jt.to_numpy()))
    tt[:, 0] = _r2(s.t0.to_numpy() + _drift(tau, s.t_amp.to_numpy(), s.t_per.to_numpy(), s.t_ph.to_numpy(),
                                           s.t_jump.to_numpy(), s.t_jt.to_numpy()))
    q = 0.5 + 0.03 * np.sin(tau / 30 + s.q_ph.to_numpy())[:, None] + rng.normal(0, 0.008, (n, 1))
    noise = np.where(sharp[None, :], rng.normal(0, 0.006, (n, nb)), rng.normal(0, 0.015, (n, nb)))
    slope = 0.03 if not cfb else 0.02
    q_sp = q + (sp - sp[:, [0]]) * -slope * -1 + noise                 # home at a bigger spread covers more often
    q_tt = (1 - q) + (tt - tt[:, [0]]) * -slope + rng.normal(0, 0.015, (n, nb)) * ~sharp[None, :]   # P(over)
    ph = 1 / (1 + np.exp(sp[:, [0]] / (7.5 if cfb else 6.5))) + noise * 0.8
    vig = np.array([0.025, 0.025, 0.04] + [0.045] * 7)[None, :] + (0.01 if cfb else 0.0)
    vig_h = vig + 0.005
    inplay = tau < 0
    if inplay.any():                                                   # in-play: wild prices (dropped anyway)
        q_sp[inplay] = rng.uniform(0.1, 0.9, (inplay.sum(), nb))
        q_tt[inplay] = rng.uniform(0.1, 0.9, (inplay.sum(), nb))
        ph[inplay] = rng.uniform(0.02, 0.98, (inplay.sum(), nb))
    sa, sb = _prices(q_sp, vig)
    oa, ob = _prices(q_tt, vig)
    ha, hb = _prices(ph, vig_h)
    no_h2h = (ph > 0.975) | (ph < 0.025)                               # no moneyline on a huge favourite
    absent = np.stack([np.frombuffer(a, dtype=bool) for a in s.absent]) if n else np.zeros((0, nb), bool)
    miss = rng.random((n, nb, 3)) < 0.03
    upd_b = rng.integers(5, 600, (n, nb))
    upd_m = upd_b[:, :, None] + rng.integers(0, 300, (n, nb, 3))
    t0 = ts.timestamp()
    iso = lambda sec: datetime.fromtimestamp(t0 - int(sec), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    data = []
    ids, homes, aways = s.id.to_numpy(), s.home.to_numpy(), s.away.to_numpy()
    kicks, eshift, euntil = s.kick.to_numpy(), s.early_shift_s.to_numpy(), s.early_until_h.to_numpy()
    for i in range(n):
        k = pd.Timestamp(kicks[i]).tz_localize(UTC) if pd.Timestamp(kicks[i]).tzinfo is None else pd.Timestamp(kicks[i])
        if eshift[i] and tau[i] > euntil[i]:
            k = k + pd.Timedelta(seconds=int(eshift[i]))
        home, away = homes[i], aways[i]
        bms = []
        for j, b in enumerate(BOOKS):
            if absent[i, j]:
                continue
            mk = []
            if not miss[i, j, 0] and not no_h2h[i, j]:
                mk.append({"key": "h2h", "last_update": iso(upd_m[i, j, 0]),
                           "outcomes": [{"name": home, "price": float(ha[i, j])}, {"name": away, "price": float(hb[i, j])}]})
            if not miss[i, j, 1]:
                mk.append({"key": "spreads", "last_update": iso(upd_m[i, j, 1]),
                           "outcomes": [{"name": home, "price": float(sa[i, j]), "point": float(sp[i, j])},
                                        {"name": away, "price": float(sb[i, j]), "point": float(-sp[i, j])}]})
            if not miss[i, j, 2]:
                mk.append({"key": "totals", "last_update": iso(upd_m[i, j, 2]),
                           "outcomes": [{"name": "Over", "price": float(oa[i, j]), "point": float(tt[i, j])},
                                        {"name": "Under", "price": float(ob[i, j]), "point": float(tt[i, j])}]})
            if mk:
                bms.append({"key": b, "title": TITLES[b], "last_update": iso(upd_b[i, j]), "markets": mk})
        if bms:
            data.append({"id": ids[i], "sport_key": sport, "sport_title": SPORT_TITLE[sport],
                         "commence_time": k.strftime("%Y-%m-%dT%H:%M:%SZ"), "home_team": home, "away_team": away,
                         "bookmakers": bms})
    data.sort(key=lambda e: (e["commence_time"], e["id"]))
    step = timedelta(seconds=grid)
    return json.dumps({"timestamp": bulk.iso(ts), "previous_timestamp": bulk.iso(ts - step),
                       "next_timestamp": bulk.iso(ts + step), "data": data})


def _write(job) -> tuple[int, int]:
    sport, source, url, params, at = job
    b = body(sport, at)
    CACHE.get_or_fetch(sport=sport, source=source, data_date=at.date().isoformat(), url=url, params=dict(params),
                       fetch=lambda: Fetched(200, {"x-requests-last": "30", "x-requests-remaining": "4000000",
                                                   "x-requests-used": "1000000", "content-type": "application/json"}, b))
    return len(b), b.count('"bookmakers"')


HORIZON = timedelta(days=21)


def main() -> None:
    global HORIZON
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--horizon-days", type=float, default=21)
    ap.add_argument("--fcs", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="only the first N calls (a smoke test)")
    a = ap.parse_args()
    HORIZON = timedelta(days=a.horizon_days)
    os.environ["GEN_HORIZON_DAYS"] = str(a.horizon_days)
    data = Path(a.data_dir)
    raw = data / "raw"
    t0 = time.monotonic()
    g = schedules(a.fcs)
    save_schedules(g, raw)
    cfg = bulk.load_config()
    calls = bulk.plan_calls(cfg, "F1", bulk.load_schedules(cfg, raw))
    if a.limit:
        calls = calls[:a.limit]
    gp = data / "games.pkl"
    g.to_pickle(gp)
    summary = {"games": {f"{s} {se}": int(n) for (s, se), n in g.groupby(["sport", "season"]).size().items()},
               "calls": len(calls), "calls_by_sport": {s: sum(c.sport == s for c in calls) for s in (NFL, CFB)},
               "sealed_calls": sum(c.sealed for c in calls), "horizon_days": a.horizon_days, "fcs": a.fcs}
    print(json.dumps(summary), flush=True)
    jobs = [(c.cache_sport, c.source, c.url, c.params, c.at) for c in calls]
    nbytes = nev = 0
    with get_context("spawn").Pool(a.workers, initializer=_init_h, initargs=(str(gp), str(raw), a.horizon_days)) as p:
        for i, (nb_, ne) in enumerate(p.imap(_write, jobs, chunksize=8), 1):
            nbytes += nb_
            nev += ne
            if i % 500 == 0:
                print(f"  {i}/{len(jobs)} bodies, {nbytes / 1e9:.2f} GB of JSON, {nev:,} game listings, "
                      f"{time.monotonic() - t0:.0f}s", flush=True)
    files = list((raw).rglob("hist_odds/*/*.parquet"))
    disk = sum(f.stat().st_size for f in files)
    print(json.dumps({"calls": len(jobs), "files": len(files), "json_bytes": nbytes, "game_listings": nev,
                      "cache_bytes_on_disk": disk, "seconds": round(time.monotonic() - t0)}), flush=True)


def _init_h(gpath: str, raw: str, horizon_days: float) -> None:
    global HORIZON
    HORIZON = timedelta(days=horizon_days)
    _init(gpath, raw)


if __name__ == "__main__":
    sys.exit(main())
