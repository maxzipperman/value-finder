"""NWS heat index (Rothfusz regression with the NWS adjustments), in degrees F.

Source: NWS Weather Prediction Center, "The Heat Index Equation" (wpc.ncep.noaa.gov/html/heatindex_equation.shtml).
Below about 80 F the simple Steadman form is used, as the NWS does.
"""
from __future__ import annotations

import math


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def heat_index_f(t_f: float | None, rh: float | None) -> float | None:
    if t_f is None or rh is None or math.isnan(t_f) or math.isnan(rh):
        return None
    simple = 0.5 * (t_f + 61.0 + (t_f - 68.0) * 1.2 + rh * 0.094)
    if (simple + t_f) / 2 < 80:
        return simple
    hi = (-42.379 + 2.04901523 * t_f + 10.14333127 * rh - 0.22475541 * t_f * rh - 6.83783e-3 * t_f ** 2
          - 5.481717e-2 * rh ** 2 + 1.22874e-3 * t_f ** 2 * rh + 8.5282e-4 * t_f * rh ** 2 - 1.99e-6 * t_f ** 2 * rh ** 2)
    if rh < 13 and 80 <= t_f <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t_f - 95.0)) / 17)
    elif rh > 85 and 80 <= t_f <= 87:
        hi += ((rh - 85) / 10) * ((87 - t_f) / 5)
    return hi
