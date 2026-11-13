"""Figures and a results file for a simulated run (needs matplotlib)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import linkbudget as lb  # noqa: E402
from .physics import RoadRisk  # noqa: E402

RISK_COLORS = ["#2a9d8f", "#e9c46a", "#f4a261", "#d62828"]


def _fig_timeseries(conn: sqlite3.Connection, out: Path, node_id: int) -> None:
    rows = conn.execute(
        "SELECT ts, air_c, surface_c, dew_c, risk FROM readings WHERE node_id=? ORDER BY ts", (node_id,)
    ).fetchall()
    t0 = rows[0]["ts"]
    x = np.array([(r["ts"] - t0) / 86400 for r in rows])
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(x, [r["air_c"] for r in rows], lw=1, label="air", color="#264653")
    ax.plot(x, [r["surface_c"] for r in rows], lw=1, label="road surface", color="#e76f51")
    ax.plot(x, [r["dew_c"] for r in rows], lw=1, label="dew point", color="#457b9d", ls="--")
    ax.axhline(0, color="k", lw=0.6)
    danger = np.array([r["risk"] >= RoadRisk.WARNING for r in rows])
    ax.fill_between(x, ax.get_ylim()[0], ax.get_ylim()[1], where=danger, color="#d62828", alpha=0.15,
                    label="WARNING / DANGER", step="mid")
    ax.set_xlabel("days since start")
    ax.set_ylabel("°C")
    ax.set_title(f"Node {node_id}: received readings (synthetic data)")
    ax.legend(loc="upper right", ncol=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "timeseries.png", dpi=140)
    plt.close(fig)


def _fig_heatmap(conn: sqlite3.Connection, out: Path) -> None:
    rows = conn.execute(
        "SELECT t.km AS km, CAST((t.ts - (SELECT MIN(ts) FROM sim_truth)) / 3600 AS INT) AS hr, "
        "MAX(t.risk) AS risk FROM sim_truth t GROUP BY t.km, hr"
    ).fetchall()
    kms = sorted({r["km"] for r in rows})
    hrs = max(r["hr"] for r in rows) + 1
    grid = np.full((len(kms), hrs), np.nan)
    for r in rows:
        grid[kms.index(r["km"]), r["hr"]] = r["risk"]
    from matplotlib.colors import ListedColormap
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.imshow(grid, aspect="auto", cmap=ListedColormap(RISK_COLORS), vmin=0, vmax=3,
              extent=[0, hrs / 24, kms[-1] + 5, kms[0] - 5], interpolation="nearest")
    ax.set_xlabel("days since start")
    ax.set_ylabel("km along road")
    ax.set_title("Frost/ice risk along the road over time (max per hour, ground truth, synthetic)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in RISK_COLORS]
    ax.legend(handles, [r.name for r in RoadRisk], loc="upper right", fontsize=8, ncol=4)
    fig.tight_layout()
    fig.savefig(out / "risk_heatmap.png", dpi=140)
    plt.close(fig)


def _fig_pdr(m: dict, out: Path, sf_sim: int) -> None:
    d = np.linspace(1, 60, 200)
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for sf in lb.SPREADING_FACTORS:
        ax.plot(d, [lb.pdr(x, sf) for x in d], label=f"SF{sf}", lw=2 if sf == sf_sim else 1)
    ax.axhline(0.95, color="k", lw=0.6, ls=":")
    ax.set_xlabel("distance to gateway (km)")
    ax.set_ylabel("packet delivery ratio")
    ax.set_title("Modelled delivery vs distance (path-loss exponent 3.5)")
    ax.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "pdr_vs_distance.png", dpi=140)
    plt.close(fig)


def write_all(conn: sqlite3.Connection, m: dict, out_dir: str, sf_sim: int = 10) -> None:
    out = Path(out_dir) / "img"
    out.mkdir(parents=True, exist_ok=True)
    node = conn.execute("SELECT node_id FROM sim_truth GROUP BY node_id ORDER BY ABS(MAX(km) - 150) LIMIT 1").fetchone()[0]
    _fig_timeseries(conn, out, node)
    _fig_heatmap(conn, out)
    _fig_pdr(m, out, sf_sim)

    summary = {k: v for k, v in m.items() if k != "per_node"}
    Path(out_dir, "results.json").write_text(json.dumps({**summary, "per_node": m["per_node"]}, indent=2))
