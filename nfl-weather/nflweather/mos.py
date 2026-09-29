"""NWS MOS forecasts as issued, from the Iowa Environmental Mesonet archive (issue #40).

MOS (Model Output Statistics) is the National Weather Service's station forecast: the GFS
model's output corrected, station by station, to what that airport's instruments report. The
Iowa Environmental Mesonet (IEM) keeps every run since 2000. Each row is one forecast step of
one run: `runtime` (the model cycle, UTC), `ftime` (the valid time, UTC) and `wsp`, the
forecast wind speed in KNOTS at that valid time.

GFS MOS (the "MAV" product, model=GFS here) runs at 00, 06, 12 and 18 UTC with steps every
3 hours out to +60 h, then +66 h and +72 h.

This module is copied between cfb-weather/cfbweather/mos.py and nfl-weather/nflweather/mos.py;
keep the two identical (cfb-weather/tests/test_mos.py checks). It is GET-only.

Timing (no lookahead), the way the live rules count lead time (cfb-weather PREREGISTRATION
amendment 3, nfl-weather amendment 5): lead = the kickoff's Eastern date minus the date of the
run on the Mac's clock (Pacific). A MOS run counts as "on the Mac's clock" on the Pacific date
of the first scheduled alert run (07:30, 11:30, 15:30, 19:30 Pacific) at or after it was
published, taken conservatively as the cycle time plus PUBLISH_H hours. For every cycle this
is the cycle's UTC date (tests/test_mos.py checks all four cycles in summer and winter). For
lead L the replay uses the LAST run on date kickoff_date - L whose steps cover the whole
kickoff window; if none does, that lead is missing.

Window: the live CFB rule averages wind over the kickoff hour and the next three (k0, k0+1,
k0+2, k0+3, with k0 the kickoff time floored to the hour). MOS steps are 3-hourly, so each of
those four hours is linearly interpolated in time between the two MOS steps around it (an
hour that falls on a step takes that step's value), and the four values are averaged. The
steps around an hour may be at most MAX_GAP_H hours apart; an hour outside the run's steps,
or next to a missing value, leaves the window uncovered. The NFL rule reads its forecast at
the kickoff instant (how="kickoff"): one time, interpolated the same way.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .config import RAW, USER_AGENT

URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py"
MODEL = "GFS"
SHARED_CACHE = Path.home() / ".cache" / "value-finder" / "mos"   # outlives any one checkout
# data/raw/mos is meant to be a symlink to SHARED_CACHE (see the README); without it, use SHARED_CACHE
# directly rather than start a second, empty cache inside the checkout
CACHE = RAW / "mos" if (RAW / "mos").exists() else SHARED_CACHE
KT_TO_MPH = 1852 / 1609.344         # 1 knot = 1,852 m per hour; 1 mile = 1,609.344 m -> 1.150779
LEADS = (1, 2, 3)
WINDOW_H = 3                        # the window is k0 .. k0 + 3 hours (four hourly points)
MAX_GAP_H = 6                       # MAV steps are 3-hourly to +60 h, then 6-hourly to +72 h
PUBLISH_H = 5                       # cycle time to publication, conservative (MAV is out about 4 h after)
MAC_TZ = "America/Los_Angeles"
MAC_SLOTS = ((7, 30), (11, 30), (15, 30), (19, 30))   # the scheduled alert runs (install_alerts.sh)
KICK_TZ = "America/New_York"
MIN_INTERVAL_S = 7.0                # one request every 7 s: IEM answered 429 at 4 and 6 s spacing (Sep 29)
MAX_INTERVAL_S = 15.0               # each rate-limit answer widens the spacing by 1 s, up to this
BACKOFF_S = (60, 120, 300, 600, 900)  # waits after a rate limit or server error
RETRY_CONN_S = 15                   # first wait after a dropped connection


def kt_to_mph(kt):
    """Knots to miles per hour (1 kt = 1.150779 mph). Works on scalars, arrays and Series."""
    return kt * KT_TO_MPH


# --------------------------------------------------------------------------- timing
def mac_date(runtime_utc) -> date:
    """The Pacific date of the first scheduled alert run at or after this MOS run was published."""
    pub = pd.Timestamp(runtime_utc)
    pub = (pub.tz_localize("UTC") if pub.tzinfo is None else pub.tz_convert("UTC")) + pd.Timedelta(hours=PUBLISH_H)
    local = pub.tz_convert(MAC_TZ)
    d = local.date()
    for _ in range(3):
        for h, m in MAC_SLOTS:
            slot = pd.Timestamp(datetime(d.year, d.month, d.day, h, m)).tz_localize(MAC_TZ)
            if slot >= local:
                return d
        d += timedelta(days=1)
    raise AssertionError("unreachable")


def mac_slot_utc(d: date) -> pd.Timestamp:
    """The last scheduled alert run on Pacific date d, in UTC: a bet on date d can be no later."""
    h, m = MAC_SLOTS[-1]
    return pd.Timestamp(datetime(d.year, d.month, d.day, h, m)).tz_localize(MAC_TZ).tz_convert("UTC")


def kick_date(kick_utc) -> date:
    """The kickoff's Eastern calendar date."""
    k = pd.Timestamp(kick_utc)
    k = k.tz_localize("UTC") if k.tzinfo is None else k
    return k.tz_convert(KICK_TZ).date()


def _naive_utc(t) -> pd.Timestamp:
    k = pd.Timestamp(t)
    return k.tz_convert("UTC").tz_localize(None) if k.tzinfo is not None else k


def window_hours(kick_utc) -> pd.DatetimeIndex:
    """The four UTC hours the CFB wind average covers: the kickoff hour and the next three (naive UTC)."""
    k0 = _naive_utc(kick_utc).floor("h")
    return pd.date_range(k0, k0 + pd.Timedelta(hours=WINDOW_H), freq="h")


def target_times(kick_utc, how="window") -> pd.DatetimeIndex:
    """The times a forecast is read at: the CFB 4-hour window ("window"), or the kickoff instant
    ("kickoff"), which is how the NFL rule reads its forecast (nflweather/weather.summarize_hourly)."""
    if how == "window":
        return window_hours(kick_utc)
    if how == "kickoff":
        return pd.DatetimeIndex([_naive_utc(kick_utc)])
    raise ValueError(how)


def window_wind_kt(steps: pd.DataFrame, kick_utc, how="window") -> float:
    """Mean forecast wind (knots) at target_times(kick_utc, how) from one run's steps (ftime, wsp; naive UTC).

    Each time is linearly interpolated between the steps around it; NaN when any time is not
    covered (outside the steps, a gap over MAX_GAP_H, or a missing wsp next to it)."""
    s = steps[["ftime", "wsp"]].sort_values("ftime")
    t = s.ftime.to_numpy(dtype="datetime64[ns]")
    v = s.wsp.to_numpy(dtype=float)
    vals = []
    for h in target_times(kick_utc, how).to_numpy(dtype="datetime64[ns]"):
        i = np.searchsorted(t, h, side="left")
        if i < len(t) and t[i] == h:
            if np.isnan(v[i]):
                return np.nan
            vals.append(v[i])
            continue
        if i == 0 or i == len(t):
            return np.nan
        t1, t2, v1, v2 = t[i - 1], t[i], v[i - 1], v[i]
        gap = (t2 - t1) / np.timedelta64(1, "h")
        if gap > MAX_GAP_H or np.isnan(v1) or np.isnan(v2):
            return np.nan
        w = ((h - t1) / np.timedelta64(1, "h")) / gap
        vals.append(v1 + w * (v2 - v1))
    return float(np.mean(vals))


def select_runs(runs: pd.DataFrame, kick_utc, leads=LEADS, how="window") -> dict:
    """For each lead, the last run on Mac date (kickoff's Eastern date - lead) that covers the window.

    `runs`: rows of one station (runtime, ftime, wsp; naive UTC). Returns {lead: dict(runtime,
    wind_kt, wind_mph, published_utc, bet_by_utc)} with None for a lead no run covers. A run is
    only eligible if it was published before the last alert run of its Mac date and before
    kickoff, so nothing here can use information from after the bet."""
    out = {n: None for n in leads}
    if runs is None or runs.empty:
        return out
    kd = kick_date(kick_utc)
    k = pd.Timestamp(kick_utc)
    k = k.tz_localize("UTC") if k.tzinfo is None else k.tz_convert("UTC")
    lo = pd.Timestamp(kd - timedelta(days=max(leads) + 1))    # only runs near the game can qualify
    near = runs[(runs.runtime >= lo) & (runs.runtime < pd.Timestamp(kd + timedelta(days=1)))]
    runs = near
    rts = pd.Series(near.runtime.unique()).sort_values(ascending=False)
    md = {rt: mac_date(rt) for rt in rts}
    for n in leads:
        want = kd - timedelta(days=n)
        for rt in rts:
            if md[rt] != want:
                continue
            published = pd.Timestamp(rt).tz_localize("UTC") + pd.Timedelta(hours=PUBLISH_H)
            bet_by = mac_slot_utc(want)
            assert published <= bet_by < k, (rt, kick_utc, n)   # no lookahead, by construction
            kt = window_wind_kt(runs[runs.runtime == rt], kick_utc, how)
            if np.isnan(kt):
                continue
            out[n] = dict(runtime=pd.Timestamp(rt), wind_kt=kt, wind_mph=kt_to_mph(kt),
                          published_utc=published, bet_by_utc=bet_by)
            break
    return out


# --------------------------------------------------------------------------- fetching
_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last_request = [0.0]
_interval = [MIN_INTERVAL_S]


def _pace(min_interval=MIN_INTERVAL_S):
    wait = _last_request[0] + min_interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def _fmt(t) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%MZ")


def cache_file(station, sts, ets, model=MODEL, cache=None) -> Path:
    cache = Path(cache or CACHE)
    return cache / model / station / f"{station}_{model}_{pd.Timestamp(sts):%Y%m%d%H}_{pd.Timestamp(ets):%Y%m%d%H}.csv"


def _span(p: Path):
    a, b = p.stem.split("_")[-2:]
    return pd.Timestamp(datetime.strptime(a, "%Y%m%d%H")), pd.Timestamp(datetime.strptime(b, "%Y%m%d%H"))


def cached_cover(station, sts, ets, model=MODEL, cache=None) -> Path | None:
    """A cached file whose run-time span contains [sts, ets], if any (reruns never re-fetch)."""
    d = Path(cache or CACHE) / model / station
    if not d.exists():
        return None
    sts, ets = pd.Timestamp(sts), pd.Timestamp(ets)
    for p in sorted(d.glob(f"{station}_{model}_*.csv")):
        a, b = _span(p)
        if a <= sts and b >= ets:
            return p
    return None


class RateLimited(RuntimeError):
    pass


def fetch_runs(station, sts, ets, model=MODEL, cache=None, log=print) -> Path:
    """Every `model` MOS run for `station` with run time in [sts, ets] (inclusive, UTC), cached.

    One GET to IEM's bulk request script. The response is stored before it is parsed; only a
    CSV with the expected header is kept (an empty result is kept too, so a station with no
    runs isn't asked again). Throttled to one request every MIN_INTERVAL_S seconds or more: a
    rate-limit answer widens the spacing for the rest of the run and waits BACKOFF_S."""
    hit = cached_cover(station, sts, ets, model, cache)
    if hit is not None:
        return hit
    dest = cache_file(station, sts, ets, model, cache)
    dest.parent.mkdir(parents=True, exist_ok=True)
    params = dict(station=station, model=model, sts=_fmt(sts), ets=_fmt(ets), format="csv")
    for attempt in range(len(BACKOFF_S) + 1):
        _pace(_interval[0])
        try:
            r = _session.get(URL, params=params, timeout=180)
            status, text = r.status_code, r.text
        except requests.RequestException as e:
            status, text = None, repr(e)
        if status == 200 and text.startswith("runtime,"):
            tmp = dest.with_suffix(".part")
            tmp.write_text(text)
            tmp.replace(dest)
            return dest
        if attempt == len(BACKOFF_S):
            break
        if status == 429:
            _interval[0] = min(_interval[0] + 1.0, MAX_INTERVAL_S)
        wait = RETRY_CONN_S if status is None and attempt == 0 else BACKOFF_S[attempt]
        log(f"  {station} {params['sts']}..{params['ets']}: HTTP {status} {text[:80]!r}; waiting {wait}s, "
            f"then one request every {_interval[0]:.0f} s")
        time.sleep(wait)
    raise RateLimited(f"{station} {params['sts']}..{params['ets']}: gave up after {len(BACKOFF_S) + 1} tries")


def read_file(p: Path) -> pd.DataFrame:
    d = pd.read_csv(p, usecols=lambda c: c in ("runtime", "ftime", "wsp", "wdr", "station"))
    if d.empty:
        return pd.DataFrame(columns=["runtime", "ftime", "wsp", "wdr", "station"])
    d["runtime"] = pd.to_datetime(d.runtime)
    d["ftime"] = pd.to_datetime(d.ftime)
    d["wsp"] = pd.to_numeric(d.wsp, errors="coerce")
    return d


def load_station(station, model=MODEL, cache=None) -> pd.DataFrame:
    """Every cached run for one station (runtime, ftime, wsp in knots, wdr), duplicates dropped."""
    d = Path(cache or CACHE) / model / station
    files = sorted(d.glob(f"{station}_{model}_*.csv")) if d.exists() else []
    if not files:
        return pd.DataFrame(columns=["runtime", "ftime", "wsp", "wdr", "station"])
    out = pd.concat([read_file(p) for p in files], ignore_index=True)
    return out.drop_duplicates(["runtime", "ftime"]).sort_values(["runtime", "ftime"]).reset_index(drop=True)


# --------------------------------------------------------------------------- stations
def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


STATION_TABLE_URL = "https://www.weather.gov/mdl/mos_stations_stadrggfs2009"   # MDL's GFS MOS station list, 2009
MAX_KM = 40.0


def station_table(cache=None) -> pd.DataFrame:
    """The GFS MOS (MAV) station list (1,693 stations: ICAO id, name, state, lat, lon to 0.01 degree).

    Fetched once from the NWS Meteorological Development Laboratory and cached as HTML."""
    import html
    import re
    p = Path(cache or CACHE) / "stations_gfs2009.html"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        _pace()
        r = _session.get(STATION_TABLE_URL, timeout=120)
        r.raise_for_status()
        p.write_text(r.text)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", p.read_text()))
    rx = re.compile(r"^\s*([A-Z0-9]{4})\s+(.+?)\s+([A-Z]{2})\s+(\d+\.\d+)([NS])\s+(\d+\.\d+)([EW])\s*$")
    rows = []
    for line in text.splitlines():
        m = rx.match(line)
        if m:
            icao, name, st, la, ns, lo, ew = m.groups()
            rows.append(dict(icao=icao, mos_name=name.strip(), mos_state=st,
                             mos_lat=float(la) * (1 if ns == "N" else -1), mos_lon=float(lo) * (1 if ew == "E" else -1)))
    return pd.DataFrame(rows).drop_duplicates("icao").reset_index(drop=True)


def nearest_mos(venues: pd.DataFrame, table: pd.DataFrame, k=3, max_km=MAX_KM) -> pd.DataFrame:
    """Up to k MOS stations within max_km of each venue (columns venue_key, lat, lon), nearest first.

    Venues with none within max_km get no rows: they are left out rather than guessed."""
    km = haversine_km(venues.lat.to_numpy()[:, None], venues.lon.to_numpy()[:, None],
                      table.mos_lat.to_numpy()[None, :], table.mos_lon.to_numpy()[None, :])
    out = []
    for i, key in enumerate(venues.venue_key.to_numpy()):
        order = np.argsort(km[i])[:k]
        for rank, j in enumerate(o for o in order if km[i, o] <= max_km):
            out.append(dict(venue_key=key, rank=rank, icao=table.icao[j], km=round(float(km[i, j]), 2),
                            mos_name=table.mos_name[j], mos_state=table.mos_state[j],
                            mos_lat=table.mos_lat[j], mos_lon=table.mos_lon[j]))
    return pd.DataFrame(out, columns=["venue_key", "rank", "icao", "km", "mos_name", "mos_state", "mos_lat", "mos_lon"])


def season_windows(games: pd.DataFrame, leads=LEADS) -> pd.DataFrame:
    """One MOS request per (station, season): run times from the 00Z run of (first kickoff date - max
    lead) through the 18Z run of (last kickoff date - min lead). `games`: icao, season, start_utc."""
    g = games.assign(kd=[kick_date(k) for k in games.start_utc])
    w = g.groupby(["icao", "season"]).kd.agg(["min", "max", "size"]).reset_index()
    w["sts"] = [pd.Timestamp(d - timedelta(days=max(leads))) for d in w["min"]]
    w["ets"] = [pd.Timestamp(d - timedelta(days=min(leads))) + pd.Timedelta(hours=18) for d in w["max"]]
    return w.rename(columns={"size": "games"})[["icao", "season", "sts", "ets", "games"]]
