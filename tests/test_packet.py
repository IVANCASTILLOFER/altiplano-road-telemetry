import pytest

from roadtel import packet
from roadtel.packet import PACKET_LEN, PacketError, Reading


def sample(**kw):
    base = dict(node_id=7, seq=513, air_c=-4.25, rh_pct=63.5, surface_c=-6.1, battery_mv=3872, flags=0)
    base.update(kw)
    return Reading(**base)


def test_crc_check_value():
    assert packet.crc16_ccitt(b"123456789") == 0x29B1  # standard CRC-16/CCITT-FALSE check value


def test_roundtrip():
    r = sample()
    raw = packet.encode(r)
    assert len(raw) == PACKET_LEN
    assert packet.decode(raw) == r


def test_flags_roundtrip():
    r = sample(flags=packet.FLAG_SURFACE_FAULT | packet.FLAG_LOW_BATTERY)
    assert packet.decode(packet.encode(r)).flags == 3


def test_any_single_bit_flip_is_detected():
    raw = packet.encode(sample())
    for i in range(len(raw)):
        for bit in range(8):
            bad = raw[:i] + bytes([raw[i] ^ (1 << bit)]) + raw[i + 1:]
            with pytest.raises(PacketError):
                packet.decode(bad)


def test_wrong_length_rejected():
    raw = packet.encode(sample())
    for bad in (raw[:-1], raw + b"\x00", b""):
        with pytest.raises(PacketError):
            packet.decode(bad)


def test_unknown_version_rejected():
    raw = bytearray(packet.encode(sample()))
    raw[0] = (2 << 4) | (raw[0] & 0x0F)
    raw[-2:] = packet.crc16_ccitt(bytes(raw[:-2])).to_bytes(2, "big")  # valid CRC, wrong version
    with pytest.raises(PacketError, match="version"):
        packet.decode(bytes(raw))


@pytest.mark.parametrize("field,value", [("node_id", 256), ("seq", -1), ("rh_pct", 100.5), ("air_c", 400.0)])
def test_out_of_range_values_refused_at_encode(field, value):
    with pytest.raises(ValueError):
        packet.encode(sample(**{field: value}))


def test_known_vector():
    # Frozen wire format: any change here is a breaking protocol change (firmware must match).
    # ver/flags=0x10 node=01 seq=0002 air=+1.00C(0064) rh=50.00%(1388) surf=-1.00C(ff9c) batt=3900mV(0f3c) crc=8ad8
    raw = packet.encode(Reading(1, 2, 1.0, 50.0, -1.0, 3900))
    assert raw.hex() == "1001000200641388ff9c0f3c8ad8"
