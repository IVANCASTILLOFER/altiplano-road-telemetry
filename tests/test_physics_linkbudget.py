import math

import pytest

from roadtel import linkbudget as lb
from roadtel import physics
from roadtel.physics import RoadRisk, assess


def test_dew_point_reference_values():
    assert physics.dew_point_c(20.0, 50.0) == pytest.approx(9.27, abs=0.1)
    assert physics.dew_point_c(0.0, 100.0) == pytest.approx(0.0, abs=1e-6)
    assert physics.dew_point_c(-10.0, 100.0) == pytest.approx(-10.0, abs=1e-6)


def test_rh_dew_point_are_inverse():
    for t, rh in [(15, 20), (-5, 70), (3, 95)]:
        assert physics.rh_from_dew_point(t, physics.dew_point_c(t, rh)) == pytest.approx(rh, abs=1e-6)


@pytest.mark.parametrize(
    "air,rh,surf,expected",
    [
        (12.0, 20.0, 18.0, RoadRisk.OK),        # sunny afternoon
        (4.0, 30.0, 2.8, RoadRisk.WATCH),       # cold but dry
        (1.5, 90.0, 1.0, RoadRisk.WARNING),     # near freezing and moist
        (-6.0, 90.0, -8.0, RoadRisk.DANGER),    # frozen and at dew point
        (-8.0, 30.0, -10.0, RoadRisk.WATCH),    # dry freeze, dew point far below surface
    ],
)
def test_risk_levels(air, rh, surf, expected):
    assert assess(air, rh, surf).risk == expected


def test_surface_sensor_fault_uses_conservative_fallback():
    a = assess(1.0, 80.0, surface_c=25.0, surface_ok=False)  # absurd surface value ignored
    assert a.surface_c == pytest.approx(1.0 - physics.SURFACE_FALLBACK_OFFSET_C)
    assert a.risk >= RoadRisk.WARNING


def test_airtime_matches_semtech_calculator():
    # Reference: SF7/BW125/CR4/5, 8-symbol preamble, explicit header, CRC -> 10 bytes = 41.216 ms
    assert lb.airtime_s(10, 7) == pytest.approx(0.041216, abs=1e-6)
    assert lb.airtime_s(14, 7) == pytest.approx(0.046336, abs=1e-6)


def test_airtime_grows_with_sf():
    times = [lb.airtime_s(14, sf) for sf in lb.SPREADING_FACTORS]
    assert times == sorted(times)


def test_free_space_loss_at_1km_915mhz():
    assert lb.fspl_1km_db(915.0) == pytest.approx(91.67, abs=0.05)


def test_pdr_is_monotonic_and_half_at_link_limit():
    p = lb.LinkParams()
    vals = [lb.pdr(d, 10, p) for d in (1, 5, 10, 20, 40, 80)]
    assert vals == sorted(vals, reverse=True)
    # at the distance where mean rx power == sensitivity, PDR is exactly 50 %
    d50 = 10 ** ((p.tx_power_dbm - p.system_losses_db + p.antenna_gain_dbi
                  - lb.SENSITIVITY_DBM_BW125[10] - lb.fspl_1km_db(p.freq_mhz)) / (10 * p.path_loss_exp))
    assert lb.pdr(d50, 10, p) == pytest.approx(0.5, abs=1e-6)


def test_range_increases_with_sf_and_shrinks_with_exponent():
    p = lb.LinkParams()
    ranges = [lb.range_km(sf, p) for sf in lb.SPREADING_FACTORS]
    assert ranges == sorted(ranges)
    assert lb.range_km(10, lb.LinkParams(path_loss_exp=4.0)) < lb.range_km(10, lb.LinkParams(path_loss_exp=3.0))
    assert lb.pdr(lb.range_km(10, p), 10, p) == pytest.approx(0.95, abs=1e-3)


def test_gateway_planning_covers_the_road():
    p = lb.LinkParams()
    n = lb.gateways_needed(180, 10, p)
    gws = lb.plan_gateways(180, n)
    r = lb.range_km(10, p)
    assert len(gws) == n
    assert max(min(abs(km - g) for g in gws) for km in range(0, 181)) <= r + 1e-9
    assert math.isclose(gws[1] - gws[0], 180 / n)
