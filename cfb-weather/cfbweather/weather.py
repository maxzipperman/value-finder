"""Kickoff-window summaries of Open-Meteo hourly data (requested in UTC)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def hourly_frame(js: dict | None, kick_utc):
    """Parse UTC hourly rows without inventing timestamps or accepting duplicates."""
    if not js or not isinstance(js, dict) or not isinstance(js.get("hourly"), dict):
        return None, None, "missing_hourly"
    try:
        kick = pd.Timestamp(kick_utc)
        if pd.isna(kick) or kick.tzinfo is None:
            return None, None, "invalid_kickoff"
        k0 = kick.tz_convert("UTC").floor("h")
        h = pd.DataFrame(js["hourly"])
        if "time" not in h or h.empty:
            return None, k0, "missing_time"
        h.index = pd.to_datetime(h.pop("time"), utc=True, errors="raise")
        if h.index.hasnans or h.index.has_duplicates:
            return None, k0, "invalid_hourly_time"
        return h.sort_index(), k0, ""
    except (ValueError, TypeError, OverflowError):
        return None, None, "malformed_hourly"


def required_values(h, hours, column):
    """Return values only for a complete, finite target window, plus denominators."""
    required = len(hours)
    present = int(hours.isin(h.index).sum()) if h is not None else 0
    values = pd.Series(np.nan, index=hours, dtype=float)
    if h is not None and column in h:
        values = pd.to_numeric(h[column].reindex(hours), errors="coerce")
    finite = int(np.isfinite(values.to_numpy(dtype=float)).sum())
    reason = ("missing_hour" if present != required else
              "missing_field" if h is None or column not in h else
              "nonfinite_value" if finite != required else "")
    evidence = dict(required=required, present=present, finite=finite, reason=reason)
    return (values if not reason else None), evidence


def summarize_checked(js: dict | None, kick_utc) -> dict:
    """Diagnose eligibility separately from the legacy dict-or-None summary.

    Required: four wind hours, kickoff temperature, and four precipitation/snow
    accumulation hours. Gust is a display field: incomplete gust stays NaN and
    is diagnosed, without invalidating an otherwise complete required forecast.
    """
    h, k0, error = hourly_frame(js, kick_utc)
    if error:
        return dict(values=None, missing_reason=error, fields={})
    win = pd.date_range(k0, periods=4, freq="h")
    acc = pd.date_range(k0 + pd.Timedelta(hours=1), periods=4, freq="h")
    fields, data = {}, {}
    for name, column, hours in (
        ("om_wind", "wind_speed_10m", win),
        ("om_temp", "temperature_2m", pd.DatetimeIndex([k0])),
        ("om_precip", "precipitation", acc),
        ("om_snow", "snowfall", acc),
        ("om_gust", "wind_gusts_10m", win),
    ):
        data[name], fields[name] = required_values(h, hours, column)
    missing = ";".join(f"{name}:{fields[name]['reason']}" for name in data
                       if name != "om_gust" and fields[name]["reason"])
    values = None if missing else dict(
        om_wind=data["om_wind"].mean(), om_temp=data["om_temp"].iloc[0],
        om_precip=data["om_precip"].sum(), om_snow=data["om_snow"].sum(),
        om_gust=data["om_gust"].max() if data["om_gust"] is not None else np.nan)
    return dict(values=values, missing_reason=missing, fields=fields)


def summarize(js: dict, kick_utc: pd.Timestamp) -> dict | None:
    """Wind: kickoff hour through +3h; temperature: kickoff; precipitation and
    snow: +1h through +4h. Missing required hours/values return None, not a
    partial average or invented dry weather. Complete inputs retain old values."""
    return summarize_checked(js, kick_utc)["values"]
