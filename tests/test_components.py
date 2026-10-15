import math
import pytest
from iabp.components import gate_step, inertial_step, relax, valve_resistance


def test_rc_exact():
    assert relax(100, 0, 2, 1) == pytest.approx(100 * math.exp(-0.5))


def test_rl_exact_flow_and_volume():
    q, volume = inertial_step(0, 10, 2, 1, 0.25)
    assert q == pytest.approx(5 * (1 - math.exp(-0.5)))
    assert volume == pytest.approx(5 * 0.25 - 2.5 * (1 - math.exp(-0.5)))


def test_negative_gradient_does_not_instantly_stop_positive_flow():
    q, _ = inertial_step(100, -5, 0.02, 0.001, 0.001)
    assert q > 0


def test_gate_bounds_and_finite_closure():
    assert 0 < gate_step(1, -10, 0.001) < 1
    assert 0 < gate_step(0, 10, 0.001) < 1
    assert gate_step(0.4, 0, 10) == 0.4


def test_passive_rl_energy_decays():
    q, _ = inertial_step(100, 0, 0.01, 0.001, 0.01)
    assert 0.5 * 0.001 * q*q < 0.5 * 0.001 * 100**2


@pytest.mark.parametrize('bad', [0, -1, float('nan'), float('inf')])
def test_invalid_parameters_fail(bad):
    with pytest.raises(ValueError):
        inertial_step(0, 10, bad, 1, 0.001)


def test_closed_valve_has_finite_declared_leakage():
    assert valve_resistance(0, 0.02) == 20
    assert valve_resistance(1, 0.02) == 0.02
