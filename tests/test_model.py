from dataclasses import replace
import pytest
from iabp.model import Model, ModelConfig


def test_closed_loop_mass_conserved_without_pacing():
    m = Model()
    v = m.blood_volume()
    for _ in range(2000):
        m.advance(.00025)
    assert m.blood_volume() == pytest.approx(v, abs=1e-8)


def test_activation_is_not_instant_pressure_reset():
    m = Model()
    before = m.observe()
    m.excite('ventricular')
    assert m.observe()['p_lv'] == before['p_lv']
    for _ in range(200):
        m.advance(.00025)
    assert m.observe()['p_lv'] > before['p_lv']
    assert m.observe()['v_lv'] != before['v_lv']


def test_balloon_displaces_does_not_inject_blood():
    m = Model(ModelConfig(balloon_enabled=True))
    initial = m.blood_volume()
    m.inflate = True
    for _ in range(1000):
        m.advance(.00025)
    assert m.state.balloon_v > 30
    assert m.blood_volume() == pytest.approx(initial, abs=1e-8)
    assert m.obstruction(m.state) > 1


def test_no_pressure_volume_clipping():
    m = Model()
    m.state.volumes[0] = 150  # permitted > old HTML's arbitrary 145 mL cap
    m.advance(.00001)
    assert m.state.volumes[0] > 145


@pytest.mark.parametrize('key', ['e_lv','c_root','r_systemic','l_link','tau_relax'])
def test_config_rejects_invalid(key):
    with pytest.raises(ValueError):
        replace(ModelConfig(), **{key: -1})


def test_mechanical_recovery_changes_short_interval_drive():
    a, b = Model(), Model()
    a.excite('ventricular')
    b.excite('ventricular')
    for _ in range(400):
        a.advance(.00025)
    for _ in range(4000):
        b.advance(.00025)
    a.excite('ventricular')
    b.excite('ventricular')
    assert a.targets[1] < b.targets[1]


def test_balloon_load_influences_motion():
    low = Model(ModelConfig(balloon_enabled=True))
    high = Model(ModelConfig(balloon_enabled=True))
    low.state.volumes[2] = 75 + .85*60
    high.state.volumes[2] = 75 + .85*140
    low.inflate = high.inflate = True
    for _ in range(40):
        low.advance(.00025)
        high.advance(.00025)
    assert high.state.balloon_v < low.state.balloon_v
