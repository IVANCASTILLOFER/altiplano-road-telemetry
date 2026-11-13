"""Ingestion: validate raw packets, de-duplicate across gateways, store, raise alerts."""

from __future__ import annotations

import sqlite3
from enum import Enum

from . import packet, physics
from .alerts import Alert, AlertEngine

# Two gateways hearing the same transmission report it within seconds of each other.
DEDUP_WINDOW_S = 120.0


class Outcome(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CRC_ERROR = "crc_error"


class Ingestor:
    def __init__(self, conn: sqlite3.Connection, engine: AlertEngine | None = None):
        self.conn = conn
        self.engine = engine or AlertEngine()
        self.alerts: list[Alert] = []
        self.engine.sinks.append(self._store_alert)
        self.counts = {o.value: 0 for o in Outcome}

    def _store_alert(self, a: Alert) -> None:
        self.alerts.append(a)
        self.conn.execute(
            "INSERT INTO alerts(ts, node_id, kind, risk, message) VALUES (?,?,?,?,?)",
            (a.ts, a.node_id, a.kind, None if a.risk is None else int(a.risk), a.message),
        )

    def handle(self, raw: bytes, ts: float, rssi: float | None = None, gateway: str = "gw0") -> Outcome:
        try:
            r = packet.decode(raw)
        except packet.PacketError:
            self.counts[Outcome.CRC_ERROR.value] += 1
            return Outcome.CRC_ERROR

        dup = self.conn.execute(
            "SELECT id, rssi FROM readings WHERE node_id=? AND seq=? AND ABS(ts-?) < ?",
            (r.node_id, r.seq, ts, DEDUP_WINDOW_S),
        ).fetchone()
        if dup is not None:
            # keep the copy with the stronger signal (more useful for link diagnostics)
            if rssi is not None and (dup["rssi"] is None or rssi > dup["rssi"]):
                self.conn.execute("UPDATE readings SET rssi=?, gateway=? WHERE id=?", (rssi, gateway, dup["id"]))
            self.counts[Outcome.DUPLICATE.value] += 1
            return Outcome.DUPLICATE

        a = physics.assess(r.air_c, r.rh_pct, r.surface_c, surface_ok=not (r.flags & packet.FLAG_SURFACE_FAULT))
        self.conn.execute(
            "INSERT INTO readings(ts,node_id,seq,air_c,rh_pct,surface_c,battery_mv,flags,dew_c,risk,rssi,gateway)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ts, r.node_id, r.seq, r.air_c, r.rh_pct, r.surface_c, r.battery_mv, r.flags,
             a.dew_c, int(a.risk), rssi, gateway),
        )
        self.engine.update(ts, r.node_id, a.risk, a.reason)
        self.counts[Outcome.ACCEPTED.value] += 1
        return Outcome.ACCEPTED

    def flush_stats(self) -> None:
        for kind, n in self.counts.items():
            self.conn.execute(
                "INSERT INTO rx_stats(kind, n) VALUES (?,?) ON CONFLICT(kind) DO UPDATE SET n = n + excluded.n",
                (kind, n),
            )
        self.counts = {o.value: 0 for o in Outcome}
        self.conn.commit()

    def check_silent_nodes(self, now: float, expected_interval_s: float, factor: float = 3.0) -> list[Alert]:
        """Raise 'node_silent' for nodes not heard for factor x their reporting interval."""
        out = []
        rows = self.conn.execute("SELECT node_id, MAX(ts) AS last FROM readings GROUP BY node_id").fetchall()
        for row in rows:
            gap = now - row["last"]
            if gap > factor * expected_interval_s:
                out.append(self.engine.node_silent(now, row["node_id"], gap / 60.0))
        return out
