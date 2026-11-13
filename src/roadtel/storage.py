"""SQLite storage for readings, alerts and (in simulation) ground truth."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,   -- receive time, epoch seconds UTC
    node_id     INTEGER NOT NULL,
    seq         INTEGER NOT NULL,
    air_c       REAL    NOT NULL,
    rh_pct      REAL    NOT NULL,
    surface_c   REAL    NOT NULL,
    battery_mv  INTEGER NOT NULL,
    flags       INTEGER NOT NULL,
    dew_c       REAL    NOT NULL,
    risk        INTEGER NOT NULL,
    rssi        REAL,
    gateway     TEXT
);
CREATE INDEX IF NOT EXISTS idx_readings_node_ts ON readings(node_id, ts);

CREATE TABLE IF NOT EXISTS alerts (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL    NOT NULL,
    node_id  INTEGER NOT NULL,
    kind     TEXT    NOT NULL,      -- 'raised' | 'cleared' | 'node_silent'
    risk     INTEGER,
    message  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS rx_stats (
    kind  TEXT PRIMARY KEY,         -- 'accepted' | 'duplicate' | 'crc_error'
    n     INTEGER NOT NULL DEFAULT 0
);

-- Filled only by the simulator: what each node really measured at each transmission.
CREATE TABLE IF NOT EXISTS sim_truth (
    node_id  INTEGER NOT NULL,
    seq      INTEGER NOT NULL,
    ts       REAL    NOT NULL,      -- transmit time
    km       REAL    NOT NULL,
    risk     INTEGER NOT NULL,
    delivered INTEGER NOT NULL,     -- 1 if at least one gateway received it intact
    PRIMARY KEY (node_id, ts)
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
