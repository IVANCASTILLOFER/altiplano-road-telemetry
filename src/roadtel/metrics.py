"""End-to-end metrics for a simulated run (ground truth vs what the pipeline stored)."""

from __future__ import annotations

import sqlite3
import statistics

from .alerts import ALERT_LEVEL


def compute(conn: sqlite3.Connection, interval_s: int) -> dict:
    q = conn.execute
    n_tx = q("SELECT COUNT(*) FROM sim_truth").fetchone()[0]
    n_delivered = q("SELECT SUM(delivered) FROM sim_truth").fetchone()[0] or 0
    rx = dict(q("SELECT kind, n FROM rx_stats").fetchall())

    per_node = [
        {"node_id": r["node_id"], "km": r["km"], "pdr": r["d"] / r["n"]}
        for r in q("SELECT node_id, km, COUNT(*) n, SUM(delivered) d FROM sim_truth GROUP BY node_id ORDER BY km")
    ]

    # Does the stored risk level match the ground-truth level? (differences come from
    # 0.01-degree quantisation in the packet format, only visible right at a threshold)
    rows = q(
        "SELECT r.risk AS got, t.risk AS want FROM readings r JOIN sim_truth t "
        "ON t.node_id = r.node_id AND t.seq = r.seq AND ABS(t.ts - r.ts) < 60"
    ).fetchall()
    agree = sum(1 for r in rows if r["got"] == r["want"]) / len(rows) if rows else float("nan")

    # Episodes of WARNING+ in the truth, and whether the operator was already being warned
    # (an alert raised during the episode, or one still active from a previous episode).
    intervals: dict[int, list[tuple[float, float]]] = {}
    open_at: dict[int, float] = {}
    for a in q("SELECT node_id, ts, kind FROM alerts WHERE kind IN ('raised','cleared') ORDER BY ts"):
        n = a["node_id"]
        if a["kind"] == "raised":
            open_at.setdefault(n, a["ts"])
        elif n in open_at:
            intervals.setdefault(n, []).append((open_at.pop(n), a["ts"]))
    for n, start in open_at.items():
        intervals.setdefault(n, []).append((start, float("inf")))

    episodes, detected, lags = 0, 0, []
    for node_id in [r[0] for r in q("SELECT DISTINCT node_id FROM sim_truth")]:
        run_start = last = None
        seq = q("SELECT ts, risk FROM sim_truth WHERE node_id=? ORDER BY ts", (node_id,)).fetchall()
        spans = []
        for row in seq + [None]:
            if row is not None and row["risk"] >= ALERT_LEVEL:
                run_start = run_start if run_start is not None else row["ts"]
                last = row["ts"]
            elif run_start is not None:
                spans.append((run_start, last))
                run_start = None
        for start, end in spans:
            episodes += 1
            # first moment inside [start, end + 2 intervals] at which an alert was active
            horizon = end + interval_s * 2
            hits = [max(a, start) for a, b in intervals.get(node_id, []) if a <= horizon and b >= start]
            if hits:
                detected += 1
                lags.append(min(hits) - start)

    return {
        "transmissions": n_tx,
        "delivery_ratio": n_delivered / n_tx if n_tx else float("nan"),
        "readings_stored": q("SELECT COUNT(*) FROM readings").fetchone()[0],
        "duplicates_dropped": rx.get("duplicate", 0),
        "crc_errors_rejected": rx.get("crc_error", 0),
        "risk_level_agreement": agree,
        "warning_episodes": episodes,
        "episodes_alerted": detected,
        "alert_lag_median_min": statistics.median(lags) / 60 if lags else None,
        "alert_lag_p90_min": (sorted(lags)[int(0.9 * (len(lags) - 1))] / 60) if lags else None,
        "per_node": per_node,
    }
