"""Synthetic Patacamaya -> Tambo Quemado style scenario.

Generates, for a line of nodes along a 180 km road, plausible dry-season weather
(diurnal cycle, altitude lapse rate, optional cold-front event) and pushes it through
a LoRa link model with several gateways. Ground truth is recorded so the pipeline
can be evaluated end to end.

Everything here is synthetic. Altitude profile and climate parameters are rough
assumptions for illustration, not measurements of the real road.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterator

from . import linkbudget as lb
from . import packet, physics
from .ingest import Ingestor
from .storage import connect

START_TS = 1782878400.0  # 2026-07-01 04:00 UTC == midnight in Bolivia (UTC-4)
UTC_OFFSET_H = -4.0


@dataclass
class Scenario:
    length_km: float = 180.0
    node_spacing_km: float = 10.0
    sf: int = 10
    n_gateways: int | None = None  # None -> planned from the link budget
    interval_s: int = 600
    days: float = 7.0
    seed: int = 1
    front_day: float = 3.0  # cold-front start (days from start); None disables
    front_hours: float = 14.0
    corrupt_prob: float = 0.005  # a received copy is corrupted (caught by the CRC)
    link: lb.LinkParams = field(default_factory=lb.LinkParams)


@dataclass(frozen=True)
class Node:
    node_id: int
    km: float
    alt_m: float


@dataclass(frozen=True)
class Reception:
    ts: float
    gateway: str
    rssi: float
    raw: bytes


def altitude_m(km: float, length_km: float = 180.0) -> float:
    """Rough altitude profile: ~3,790 m at Patacamaya rising to ~4,680 m at the border."""
    return 3790.0 + 890.0 * (km / length_km) ** 1.3


def build_nodes(s: Scenario) -> list[Node]:
    n = int(s.length_km // s.node_spacing_km) + 1
    return [Node(i + 1, i * s.node_spacing_km, altitude_m(i * s.node_spacing_km, s.length_km)) for i in range(n)]


def gateway_positions(s: Scenario) -> list[float]:
    n = s.n_gateways or lb.gateways_needed(s.length_km, s.sf, s.link)
    return lb.plan_gateways(s.length_km, n)


def _sun(local_h: float) -> float:
    return max(0.0, math.sin(math.pi * (local_h - 6.0) / 12.0)) if 6.0 <= local_h <= 18.0 else 0.0


def _front_envelope(t_days: float, s: Scenario) -> float:
    if s.front_day is None:
        return 0.0
    x = (t_days - s.front_day) / (s.front_hours / 24.0)
    return 0.5 * (1 - math.cos(2 * math.pi * x)) if 0.0 <= x <= 1.0 else 0.0


class _Weather:
    """Per-node weather with AR(1) noise so consecutive readings are correlated."""

    def __init__(self, node: Node, s: Scenario, rng: random.Random):
        self.node, self.s, self.rng = node, s, rng
        self.t_noise = 0.0
        self.d_noise = 0.0

    def sample(self, ts: float) -> tuple[float, float, float]:
        t_days = (ts - START_TS) / 86400.0
        local_h = ((ts / 3600.0) + UTC_OFFSET_H) % 24.0
        dalt = (self.node.alt_m - 3790.0) / 1000.0

        self.t_noise = 0.9 * self.t_noise + self.rng.gauss(0, 0.35)
        self.d_noise = 0.95 * self.d_noise + self.rng.gauss(0, 0.5)

        mean = 5.0 - 6.5 * dalt
        diurnal = 10.5 * math.sin(2 * math.pi * (local_h - 8.0) / 24.0)  # min ~02h, max ~14h
        env = _front_envelope(t_days, self.s)

        air = mean + diurnal - 6.0 * env + self.t_noise
        dew = -12.0 - 2.0 * dalt + self.d_noise
        dew = dew + (air - 0.5 - dew) * 0.9 * env  # front brings near-saturated air
        dew = min(dew, air - 0.1)

        night_cool = 2.5 if (local_h < 6 or local_h > 18) else 0.0
        surf = air + 6.0 * _sun(local_h) - night_cool * (1.0 - 0.6 * env) + self.rng.gauss(0, 0.2)
        rh = physics.rh_from_dew_point(air, dew)
        return air, rh, surf


def generate(s: Scenario) -> tuple[list[Reception], list[dict]]:
    """Return (receptions sorted by time, per-transmission ground truth)."""
    rng = random.Random(s.seed)
    nodes = build_nodes(s)
    gws = gateway_positions(s)
    airtime = lb.airtime_s(packet.PACKET_LEN, s.sf)

    # fixed shadowing per (node, gateway) link
    shadow = {(n.node_id, g): rng.gauss(0, s.link.shadow_sigma_db) for n in nodes for g in range(len(gws))}
    # how many nodes contend for each gateway (for a pessimistic ALOHA collision estimate)
    contenders = [
        sum(1 for n in nodes if lb.pdr(abs(n.km - gk), s.sf, s.link) > 0.05) for gk in gws
    ]

    receptions: list[Reception] = []
    truth: list[dict] = []
    sens = lb.SENSITIVITY_DBM_BW125[s.sf]
    n_tx = int(s.days * 86400 // s.interval_s)

    for node in nodes:
        weather = _Weather(node, s, random.Random(rng.random()))
        offset = rng.random() * s.interval_s
        for k in range(n_tx):
            ts = START_TS + offset + k * s.interval_s + rng.uniform(-5, 5)
            air, rh, surf = weather.sample(ts)
            rd = packet.Reading(node.node_id, k % 0x10000, air, rh, surf, battery_mv=3900 + int(rng.gauss(0, 15)))
            raw = packet.encode(rd)
            risk = physics.assess(air, rh, surf).risk

            delivered = False
            for gi, gk in enumerate(gws):
                d = abs(node.km - gk)
                rssi = lb.rx_power_dbm(d, s.link) + shadow[(node.node_id, gi)] + rng.gauss(0, s.link.fade_sigma_db)
                if rssi < sens:
                    continue
                p_collide = 1.0 - math.exp(-2.0 * max(contenders[gi] - 1, 0) * airtime / s.interval_s)
                if rng.random() < p_collide:
                    continue
                copy = raw
                if rng.random() < s.corrupt_prob:
                    i = rng.randrange(len(raw))
                    copy = raw[:i] + bytes([raw[i] ^ (1 << rng.randrange(8))]) + raw[i + 1:]
                else:
                    delivered = True
                receptions.append(Reception(ts + airtime + rng.uniform(0, 0.5), f"gw{gi + 1}", round(rssi, 1), copy))
            truth.append({"node_id": node.node_id, "seq": k % 0x10000, "ts": ts, "km": node.km,
                          "risk": int(risk), "delivered": int(delivered)})

    receptions.sort(key=lambda r: r.ts)
    return receptions, truth


def run(s: Scenario, db_path: str) -> dict:
    """Simulate and ingest into a SQLite DB. Returns summary numbers."""
    receptions, truth = generate(s)
    conn = connect(db_path)
    conn.executescript("DELETE FROM readings; DELETE FROM alerts; DELETE FROM rx_stats; DELETE FROM sim_truth;")
    conn.executemany(
        "INSERT INTO sim_truth(node_id,seq,ts,km,risk,delivered) VALUES (:node_id,:seq,:ts,:km,:risk,:delivered)",
        truth,
    )
    ing = Ingestor(conn)
    for r in receptions:
        ing.handle(r.raw, r.ts, r.rssi, r.gateway)
    ing.flush_stats()
    conn.commit()
    return {
        "gateways_km": gateway_positions(s),
        "nodes": len(build_nodes(s)),
        "transmissions": len(truth),
        "receptions": len(receptions),
        "counts": dict(conn.execute("SELECT kind, n FROM rx_stats").fetchall()),
        "alerts": conn.execute("SELECT COUNT(*) FROM alerts WHERE kind='raised'").fetchone()[0],
    }
