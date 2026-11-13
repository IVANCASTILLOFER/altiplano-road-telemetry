import pytest

from roadtel import packet
from roadtel.ingest import Ingestor, Outcome
from roadtel.packet import Reading
from roadtel.sources import parse_serial_line
from roadtel.storage import connect


@pytest.fixture
def ing():
    return Ingestor(connect(":memory:"))


def pkt(seq=1, air=-6.0, rh=90.0, surf=-8.0, node=3, flags=0):
    return packet.encode(Reading(node, seq, air, rh, surf, 3900, flags))


SAFE = dict(air=12.0, rh=20.0, surf=18.0)
ICY = dict(air=-6.0, rh=90.0, surf=-8.0)


def test_valid_packet_is_stored_with_risk(ing):
    assert ing.handle(pkt(**ICY), 1000.0, -100.0, "gw1") == Outcome.ACCEPTED
    row = ing.conn.execute("SELECT * FROM readings").fetchone()
    assert (row["node_id"], row["seq"], row["risk"], row["gateway"]) == (3, 1, 3, "gw1")


def test_corrupted_packet_rejected_not_stored(ing):
    raw = bytearray(pkt())
    raw[5] ^= 0xFF
    assert ing.handle(bytes(raw), 1000.0) == Outcome.CRC_ERROR
    assert ing.conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 0


def test_duplicate_from_second_gateway_is_dropped_but_keeps_best_rssi(ing):
    ing.handle(pkt(seq=9), 1000.0, -110.0, "gw1")
    assert ing.handle(pkt(seq=9), 1001.5, -90.0, "gw2") == Outcome.DUPLICATE
    rows = ing.conn.execute("SELECT rssi, gateway FROM readings").fetchall()
    assert len(rows) == 1 and (rows[0]["rssi"], rows[0]["gateway"]) == (-90.0, "gw2")


def test_same_seq_much_later_is_not_a_duplicate(ing):
    ing.handle(pkt(seq=9), 1000.0)
    assert ing.handle(pkt(seq=9), 1000.0 + 3600, ) == Outcome.ACCEPTED  # seq wrapped around


def test_alert_raised_once_then_cleared_after_two_safe_readings(ing):
    t = 0.0
    for i in range(3):
        ing.handle(pkt(seq=i, **ICY), t := t + 600)
    assert [a.kind for a in ing.alerts] == ["raised"]  # not repeated while it stays dangerous

    ing.handle(pkt(seq=3, **SAFE), t := t + 600)
    assert [a.kind for a in ing.alerts] == ["raised"]  # one safe reading is not enough
    ing.handle(pkt(seq=4, **SAFE), t := t + 600)
    assert [a.kind for a in ing.alerts] == ["raised", "cleared"]
    stored = ing.conn.execute("SELECT kind FROM alerts ORDER BY id").fetchall()
    assert [r["kind"] for r in stored] == ["raised", "cleared"]


def test_alert_escalation_warning_to_danger(ing):
    ing.handle(pkt(seq=1, air=1.5, rh=90.0, surf=1.0), 100.0)  # WARNING
    ing.handle(pkt(seq=2, **ICY), 700.0)  # DANGER
    assert [(a.kind, int(a.risk)) for a in ing.alerts] == [("raised", 2), ("raised", 3)]


def test_nodes_are_independent(ing):
    ing.handle(pkt(seq=1, node=1, **ICY), 100.0)
    ing.handle(pkt(seq=1, node=2, **SAFE), 100.0)
    assert [a.node_id for a in ing.alerts] == [1]


def test_silent_node_detection(ing):
    ing.handle(pkt(seq=1, node=1, **SAFE), 0.0)
    ing.handle(pkt(seq=1, node=2, **SAFE), 3000.0)
    out = ing.check_silent_nodes(now=3100.0, expected_interval_s=600)
    assert [a.node_id for a in out] == [1]


def test_stats_flushed(ing):
    ing.handle(pkt(seq=1), 0.0)
    ing.handle(b"\x00" * 14, 1.0)
    ing.flush_stats()
    stats = dict(ing.conn.execute("SELECT kind, n FROM rx_stats").fetchall())
    assert stats == {"accepted": 1, "duplicate": 0, "crc_error": 1}


def test_parse_serial_line():
    raw = pkt()
    assert parse_serial_line(f"RX,{raw.hex()},-97,6.5\r\n") == (raw, -97.0)
    assert parse_serial_line(f"RX,{raw.hex()}") == (raw, None)
    for bad in ("", "boot ok", "RX,zz,-90", "TX,00,-1"):
        assert parse_serial_line(bad) is None
