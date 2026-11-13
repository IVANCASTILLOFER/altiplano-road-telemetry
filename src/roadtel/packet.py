"""Compact over-the-air packet format (14 bytes, big-endian).

    offset  size  field
    0       1     version (high nibble) | flags (low nibble)
    1       1     node_id
    2       2     seq (u16, wraps)
    4       2     air temperature, centi-degC (i16)
    6       2     relative humidity, centi-percent (u16)
    8       2     road surface temperature, centi-degC (i16)
    10      2     battery, mV (u16)
    12      2     CRC-16/CCITT-FALSE over bytes 0..11

LoRa has its own payload CRC, but it is optional on some stacks and does not
protect against a relay/bridge corrupting bytes, so we carry an application
CRC too. The same layout is implemented in firmware/include/packet.h.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

VERSION = 1
PACKET_LEN = 14

FLAG_SURFACE_FAULT = 0x1  # surface (IR) sensor failed; surface_c is not trustworthy
FLAG_LOW_BATTERY = 0x2

_BODY = struct.Struct(">BBHhHhH")  # 12 bytes
_FULL = struct.Struct(">BBHhHhHH")  # 14 bytes


class PacketError(ValueError):
    """Raised when a packet cannot be decoded (bad length, version or CRC)."""


@dataclass(frozen=True)
class Reading:
    node_id: int
    seq: int
    air_c: float
    rh_pct: float
    surface_c: float
    battery_mv: int
    flags: int = 0


def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF). check("123456789") == 0x29B1."""
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _check(name: str, value: float, lo: float, hi: float) -> None:
    if not lo <= value <= hi:
        raise ValueError(f"{name}={value} outside [{lo}, {hi}]")


def encode(r: Reading) -> bytes:
    _check("node_id", r.node_id, 0, 255)
    _check("seq", r.seq, 0, 0xFFFF)
    _check("air_c", r.air_c, -327.0, 327.0)
    _check("rh_pct", r.rh_pct, 0.0, 100.0)
    _check("surface_c", r.surface_c, -327.0, 327.0)
    _check("battery_mv", r.battery_mv, 0, 0xFFFF)
    _check("flags", r.flags, 0, 0x0F)
    body = _BODY.pack(
        (VERSION << 4) | r.flags,
        r.node_id,
        r.seq,
        round(r.air_c * 100),
        round(r.rh_pct * 100),
        round(r.surface_c * 100),
        int(r.battery_mv),
    )
    return body + struct.pack(">H", crc16_ccitt(body))


def decode(raw: bytes) -> Reading:
    if len(raw) != PACKET_LEN:
        raise PacketError(f"expected {PACKET_LEN} bytes, got {len(raw)}")
    if crc16_ccitt(raw[:-2]) != struct.unpack(">H", raw[-2:])[0]:
        raise PacketError("CRC mismatch")
    ver_flags, node_id, seq, air, rh, surf, batt, _crc = _FULL.unpack(raw)
    if ver_flags >> 4 != VERSION:
        raise PacketError(f"unsupported version {ver_flags >> 4}")
    return Reading(
        node_id=node_id,
        seq=seq,
        air_c=air / 100.0,
        rh_pct=rh / 100.0,
        surface_c=surf / 100.0,
        battery_mv=batt,
        flags=ver_flags & 0x0F,
    )
