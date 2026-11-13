import pytest

from roadtel import metrics, simulator
from roadtel.simulator import Scenario
from roadtel.storage import connect


def small(**kw):
    return Scenario(days=2.0, node_spacing_km=30.0, seed=5, front_day=1.0, **kw)


def test_same_seed_same_result():
    a, ta = simulator.generate(small())
    b, tb = simulator.generate(small())
    assert [(r.ts, r.raw) for r in a] == [(r.ts, r.raw) for r in b]
    assert ta == tb


def test_different_seed_differs():
    a, _ = simulator.generate(small())
    b, _ = simulator.generate(Scenario(days=2.0, node_spacing_km=30.0, seed=6, front_day=1.0))
    assert [r.raw for r in a] != [r.raw for r in b]


def test_altitude_profile():
    assert simulator.altitude_m(0) == pytest.approx(3790)
    assert simulator.altitude_m(180) == pytest.approx(4680)


def test_end_to_end_pipeline(tmp_path):
    s = small()
    summary = simulator.run(s, str(tmp_path / "sim.db"))
    assert summary["receptions"] > 0 and summary["counts"]["accepted"] > 0

    conn = connect(str(tmp_path / "sim.db"))
    m = metrics.compute(conn, s.interval_s)
    assert 0.8 <= m["delivery_ratio"] <= 1.0                 # the planned gateways cover the road
    assert m["risk_level_agreement"] >= 0.99                 # pipeline reproduces ground-truth risk
    # every transmission heard intact by >=1 gateway ends up stored exactly once
    assert m["readings_stored"] == round(m["transmissions"] * m["delivery_ratio"])
    # every stored reading is unique per (node, seq, time-window): no duplicates leaked through
    dup = conn.execute(
        "SELECT COUNT(*) FROM (SELECT node_id, seq, CAST(ts/120 AS INT) b, COUNT(*) c FROM readings "
        "GROUP BY 1,2,3 HAVING c > 1)"
    ).fetchone()[0]
    assert dup == 0


def test_cold_front_creates_dangerous_conditions(tmp_path):
    s = small()
    simulator.run(s, str(tmp_path / "sim.db"))
    conn = connect(str(tmp_path / "sim.db"))
    in_front = conn.execute(
        "SELECT COUNT(*) FROM sim_truth WHERE risk >= 2 AND ts BETWEEN ? AND ?",
        (simulator.START_TS + 86400, simulator.START_TS + 86400 + 14 * 3600),
    ).fetchone()[0]
    assert in_front > 0
    assert conn.execute("SELECT COUNT(*) FROM alerts WHERE kind='raised'").fetchone()[0] > 0


def test_too_few_gateways_hurts_delivery(tmp_path):
    good = simulator.run(Scenario(days=1.0, node_spacing_km=30.0, seed=2), str(tmp_path / "a.db"))
    bad = simulator.run(Scenario(days=1.0, node_spacing_km=30.0, seed=2, n_gateways=1, sf=7), str(tmp_path / "b.db"))
    assert bad["receptions"] < good["receptions"]
