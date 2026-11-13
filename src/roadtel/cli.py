from __future__ import annotations

import argparse
import json
import sys

from . import linkbudget as lb
from . import metrics, simulator
from .storage import connect


def _cmd_simulate(a: argparse.Namespace) -> int:
    s = simulator.Scenario(days=a.days, seed=a.seed, sf=a.sf, n_gateways=a.gateways, interval_s=a.interval)
    summary = simulator.run(s, a.db)
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_link(a: argparse.Namespace) -> int:
    p = lb.LinkParams(path_loss_exp=a.exponent)
    print(f"path-loss exponent {a.exponent}, {p.freq_mhz:.0f} MHz, TX {p.tx_power_dbm:.0f} dBm, 14-byte packet")
    print(f"{'SF':>3} {'range@95% (km)':>15} {'airtime (ms)':>13} {'gateways for 180 km':>20}")
    for sf in lb.SPREADING_FACTORS:
        print(f"{sf:>3} {lb.range_km(sf, p):>15.1f} {lb.airtime_s(packet_len(), sf) * 1000:>13.0f}"
              f" {lb.gateways_needed(180, sf, p):>20}")
    return 0


def packet_len() -> int:
    from .packet import PACKET_LEN
    return PACKET_LEN


def _cmd_report(a: argparse.Namespace) -> int:
    from . import report
    conn = connect(a.db)
    m = metrics.compute(conn, a.interval)
    report.write_all(conn, m, a.out)
    print(f"report written to {a.out}")
    return 0


def _cmd_serial(a: argparse.Namespace) -> int:  # pragma: no cover - needs hardware
    import time

    from .ingest import Ingestor
    from .sources import parse_serial_line, serial_lines

    conn = connect(a.db)
    ing = Ingestor(conn, None)
    ing.engine.sinks.append(lambda al: print(f"ALERT [{al.kind}] {al.message}", flush=True))
    for line in serial_lines(a.port, a.baud):
        parsed = parse_serial_line(line)
        if parsed:
            raw, rssi = parsed
            print(ing.handle(raw, time.time(), rssi, gateway=a.port).value, flush=True)
            conn.commit()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="roadtel", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("simulate", help="run the synthetic road scenario into a SQLite DB")
    sp.add_argument("--db", default="data/sim.db")
    sp.add_argument("--days", type=float, default=7.0)
    sp.add_argument("--seed", type=int, default=1)
    sp.add_argument("--sf", type=int, default=10, choices=lb.SPREADING_FACTORS)
    sp.add_argument("--gateways", type=int, default=None, help="default: planned from the link budget")
    sp.add_argument("--interval", type=int, default=600, help="seconds between reports per node")
    sp.set_defaults(fn=_cmd_simulate)

    lp = sub.add_parser("link-budget", help="print range / airtime / gateways per spreading factor")
    lp.add_argument("--exponent", type=float, default=3.5, help="path-loss exponent")
    lp.set_defaults(fn=_cmd_link)

    rp = sub.add_parser("report", help="write metrics and figures from a simulated DB")
    rp.add_argument("--db", default="data/sim.db")
    rp.add_argument("--out", default="docs")
    rp.add_argument("--interval", type=int, default=600)
    rp.set_defaults(fn=_cmd_report)

    gp = sub.add_parser("serial", help="ingest from a LoRa gateway on a serial port (untested on hardware)")
    gp.add_argument("--port", required=True)
    gp.add_argument("--baud", type=int, default=115200)
    gp.add_argument("--db", default="data/live.db")
    gp.set_defaults(fn=_cmd_serial)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
