import pytest
from iabp.engine import Engine
from iabp.model import ModelConfig
from iabp.scenarios import add_sinus_schedule, ThresholdDemoController

def test_paced_closed_loop_stays_continuous_and_conservative():
    e = Engine(sensors=())
    add_sinus_schedule(e, 5000000)
    for t in range(1000, 5000001, 1000):
        e.advance_to(t)
    assert abs(e.model.observe()['mass_error']) < 1e-07
    names = {x.name for x in e.truth_events}
    assert {'AORTIC_OPEN_05', 'AORTIC_CLOSE_02', 'QAO_ZERO'} <= names
    assert len([x for x in e.truth_events if x.name == 'QRS_ONSET']) == 5

def test_only_delivered_data_drives_demo_controller():
    e = Engine(model_config=ModelConfig(balloon_enabled=True))
    add_sinus_schedule(e, 3000000)
    controller = ThresholdDemoController()
    for t in range(0, 3000001, 1000):
        for cmd in controller.on_samples(e.advance_to(t), t):
            assert e.submit(cmd).status == 'accepted'
    assert controller.count >= 2
    assert any((s.status == 'completed' for s in e.command_log))
    assert abs(e.model.observe()['mass_error']) < 1e-07

def test_snapshot_command_changes_only_future():
    e = Engine(model_config=ModelConfig(balloon_enabled=True), sensors=())
    add_sinus_schedule(e, 2000000)
    e.advance_to(1000000)
    fork = Engine.from_snapshot(e.snapshot())
    from iabp.contracts import Command
    fork.submit(Command('inflate', 'INFLATE', fork.now_us))
    assert e.model.state == fork.model.state
    e.advance_to(1200000)
    fork.advance_to(1200000)
    assert e.model.observe()['p_root'] != fork.model.observe()['p_root']
    assert e.model.blood_volume() == pytest.approx(fork.model.blood_volume(), abs=1e-08)
