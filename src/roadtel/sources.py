"""Where raw packets come from. The gateway firmware prints one line per packet:

    RX,<hex payload>,<rssi dBm>,<snr dB>

parse_serial_line() is unit-tested. serial_lines() needs pyserial and a real gateway,
so it is NOT tested here.
"""

from __future__ import annotations

from typing import Iterator


def parse_serial_line(line: str) -> tuple[bytes, float | None] | None:
    """Return (raw_packet, rssi) or None if the line is not a well-formed RX line."""
    parts = line.strip().split(",")
    if len(parts) < 2 or parts[0] != "RX":
        return None
    try:
        raw = bytes.fromhex(parts[1])
    except ValueError:
        return None
    try:
        rssi = float(parts[2]) if len(parts) > 2 else None
    except ValueError:
        rssi = None
    return raw, rssi


def serial_lines(port: str, baud: int = 115200) -> Iterator[str]:  # pragma: no cover - needs hardware
    import serial  # type: ignore[import-not-found]

    with serial.Serial(port, baud, timeout=1) as ser:
        while True:
            line = ser.readline().decode("ascii", errors="ignore")
            if line:
                yield line
