"""Dew point and a transparent, rule-based frost/ice risk classification.

The rules are a *heuristic* used to turn raw readings into an actionable level.
They are not calibrated against pavement data; thresholds are plain constants so
they can be tuned once real field data exists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

# Magnus coefficients (WMO-recommended set, valid roughly -45..60 degC)
_A = 17.62
_B = 243.12

# If the surface sensor fails we fall back to air temperature minus this offset
# (clear-sky radiative cooling makes pavement colder than the air at night).
SURFACE_FALLBACK_OFFSET_C = 2.0


class RoadRisk(IntEnum):
    OK = 0
    WATCH = 1
    WARNING = 2
    DANGER = 3


def dew_point_c(air_c: float, rh_pct: float) -> float:
    rh = min(max(rh_pct, 0.1), 100.0)
    g = math.log(rh / 100.0) + _A * air_c / (_B + air_c)
    return _B * g / (_A - g)


def rh_from_dew_point(air_c: float, dew_c: float) -> float:
    """Relative humidity (%) for a given air temperature and dew point, capped at 100."""
    rh = 100.0 * math.exp(_A * dew_c / (_B + dew_c) - _A * air_c / (_B + air_c))
    return min(rh, 100.0)


@dataclass(frozen=True)
class Assessment:
    dew_c: float
    surface_c: float  # the surface temperature actually used
    risk: RoadRisk
    reason: str


def assess(air_c: float, rh_pct: float, surface_c: float, surface_ok: bool = True) -> Assessment:
    surf = surface_c if surface_ok else air_c - SURFACE_FALLBACK_OFFSET_C
    dew = dew_point_c(air_c, rh_pct)

    if surf <= 0.0 and surf <= dew + 0.5:
        risk, why = RoadRisk.DANGER, "surface at/below freezing and at/below dew point: frost or ice likely"
    elif surf <= 2.0 and surf - dew <= 1.5:
        risk, why = RoadRisk.WARNING, "cold, moist surface close to freezing: ice likely if it cools further"
    elif surf <= 3.0:
        risk, why = RoadRisk.WATCH, "surface near freezing"
    else:
        risk, why = RoadRisk.OK, "no frost/ice conditions"
    return Assessment(dew_c=dew, surface_c=surf, risk=risk, reason=why)
