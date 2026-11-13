"""LoRa link-budget model: path loss, packet delivery vs distance, time on air.

This is a *model*, not a measurement. Defaults describe a ground-level node and
gateway on open high-plain terrain with small stub antennas. Every number below
that is not from a formula is an assumption to be replaced by field data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Typical SX126x sensitivity at BW=125 kHz (dBm). Vendor-typical figures used as an
# assumption; check the Semtech SX1262 datasheet for the exact values.
SENSITIVITY_DBM_BW125 = {7: -123.0, 8: -126.0, 9: -129.0, 10: -132.0, 11: -134.5, 12: -137.0}

SPREADING_FACTORS = tuple(sorted(SENSITIVITY_DBM_BW125))


@dataclass(frozen=True)
class LinkParams:
    freq_mhz: float = 915.0
    tx_power_dbm: float = 20.0  # conservative; the SX1262 can do +22 but check local rules
    antenna_gain_dbi: float = 0.0  # sum of both ends; small stub antennas are poor
    system_losses_db: float = 3.0  # cable, enclosure, connector, mismatch
    path_loss_exp: float = 3.5  # 2.0 = free space; 3-4 typical near the ground
    shadow_sigma_db: float = 5.0  # fixed per link (terrain, obstacles)
    fade_sigma_db: float = 3.0  # per packet (multipath, weather)

    @property
    def sigma_db(self) -> float:
        return math.hypot(self.shadow_sigma_db, self.fade_sigma_db)


def fspl_1km_db(freq_mhz: float) -> float:
    """Free-space path loss at 1 km: 32.44 + 20 log10(f_MHz) + 20 log10(d_km)."""
    return 32.44 + 20.0 * math.log10(freq_mhz)


def path_loss_db(distance_km: float, p: LinkParams = LinkParams()) -> float:
    d = max(distance_km, 0.01)
    return fspl_1km_db(p.freq_mhz) + 10.0 * p.path_loss_exp * math.log10(d)


def rx_power_dbm(distance_km: float, p: LinkParams = LinkParams()) -> float:
    return p.tx_power_dbm + p.antenna_gain_dbi - p.system_losses_db - path_loss_db(distance_km, p)


def pdr(distance_km: float, sf: int, p: LinkParams = LinkParams()) -> float:
    """Probability a packet is received: P(rx power > sensitivity) under Gaussian fading."""
    z = (SENSITIVITY_DBM_BW125[sf] - rx_power_dbm(distance_km, p)) / (p.sigma_db * math.sqrt(2))
    return 0.5 * math.erfc(z)


def range_km(sf: int, p: LinkParams = LinkParams(), target_pdr: float = 0.95) -> float:
    """Largest distance with PDR >= target (bisection; PDR is monotonic in distance)."""
    lo, hi = 0.01, 1000.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if pdr(mid, sf, p) >= target_pdr:
            lo = mid
        else:
            hi = mid
    return lo


def airtime_s(payload_bytes: int, sf: int, bw_hz: int = 125_000, cr: int = 1, preamble: int = 8,
              explicit_header: bool = True, crc: bool = True) -> float:
    """LoRa time on air (Semtech AN1200.13). cr: 1 -> 4/5 ... 4 -> 4/8."""
    t_sym = (2 ** sf) / bw_hz
    de = 1 if t_sym > 0.016 else 0  # low-data-rate optimisation
    ih = 0 if explicit_header else 1
    num = 8 * payload_bytes - 4 * sf + 28 + (16 if crc else 0) - 20 * ih
    n_payload = 8 + max(math.ceil(num / (4 * (sf - 2 * de))) * (cr + 4), 0)
    return (preamble + 4.25) * t_sym + n_payload * t_sym


def gateways_needed(length_km: float, sf: int, p: LinkParams = LinkParams(), target_pdr: float = 0.95) -> int:
    """Gateways on the road line so that every point is within range of one."""
    return max(1, math.ceil(length_km / (2.0 * range_km(sf, p, target_pdr))))


def plan_gateways(length_km: float, n: int) -> list[float]:
    """Evenly spaced gateway positions (km along the road), centred in their segments."""
    seg = length_km / n
    return [round(seg * (i + 0.5), 3) for i in range(n)]
