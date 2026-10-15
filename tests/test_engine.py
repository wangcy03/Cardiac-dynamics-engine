from dataclasses import fields
import pytest
from iabp.contracts import Command, Sample
from iabp.engine import Engine, EngineConfig
from iabp.model import ModelConfig
from iabp.sensors import SensorConfig


def ap(name='a', **kwargs):
    return SensorConfig(name, 'p_root', 'mmHg', **kwargs)


def test_no_delivery_before_available():
    e = Engine(sensors=(ap(latency_us=5000),))
    assert e.advance_to(4999) == []
    samples = e.advance_to(5000)
    assert len(samples) == 1 and samples[0].t_available_us == 5000
    assert samples[0].source_time_us == 0


def test_repeated_advance_at_same_time_is_empty():
    e = Engine(sensors=(ap(),))
    assert len(e.advance_to(0)) == 1
    assert e.advance_to(0) == []


def test_unknown_source_clock_not_leaked():
    s = Engine(sensors=(ap(expose_source_time=False),)).advance_to(0)[0]
    assert s.source_time_us is None and s.source_clock_id is None
    names = {f.name for f in fields(Sample)}
    assert 'true_time_us' not in names and 'latency_us' not in names
    assert 'ac' not in names and 'next_r' not in names


def test_same_site_same_chain_identical():
    e = Engine(sensors=(ap('a'), ap('b')))
    samples = e.advance_to(10000)
    assert [s.value for s in samples if s.channel_id=='a'] == [s.value for s in samples if s.channel_id=='b']


def test_different_chain_does_not_change_truth():
    a = Engine(sensors=(ap('a'),))
    b = Engine(sensors=(ap('a', gain=-1, noise_std=1, tau_us=5000),))
    a.advance_to(100000)
    b.advance_to(100000)
    assert a.model.state == b.model.state


def test_channel_rng_is_independent_of_other_channels():
    a = Engine(sensors=(ap('one', noise_std=1),))
    b = Engine(sensors=(ap('extra', noise_std=7), ap('one', noise_std=1)))
    x = a.advance_to(5000)
    y = [s for s in b.advance_to(5000) if s.channel_id=='one']
    assert x == y


def test_seed_changes_noise_not_truth():
    a = Engine(EngineConfig(seed=1), sensors=(ap(noise_std=1),))
    b = Engine(EngineConfig(seed=2), sensors=(ap(noise_std=1),))
    assert a.advance_to(10000) != b.advance_to(10000)
    assert a.model.state == b.model.state


def test_snapshot_restores_all_rng_queue_filter_state():
    a = Engine(sensors=(ap(tau_us=4000, noise_std=2, latency_us=7000),))
    a.schedule_stimulus(100000, 'ventricular')
    a.advance_to(55000)
    b = Engine.from_snapshot(a.snapshot())
    assert a.advance_to(200000) == b.advance_to(200000)
    assert a.model.state == b.model.state
    assert a.truth_events == b.truth_events


def test_future_electrical_event_cannot_change_prefix():
    a = Engine()
    b = Engine()
    a.schedule_stimulus(100000, 'ventricular')
    b.schedule_stimulus(300000, 'ventricular')
    assert a.advance_to(99999) == b.advance_to(99999)
    assert a.model.state == b.model.state
    assert a.ecg(99999) == 0


def test_qrs_and_mechanical_start_distinct():
    e = Engine(sensors=())
    e.schedule_stimulus(100000,'ventricular')
    e.advance_to(134999)
    assert e.model.state.activation[1] == 0
    e.advance_to(140000)
    assert e.model.state.activation[1] > 0
    names = [x.name for x in e.truth_events]
    assert 'QRS_ONSET' in names and 'VENTRICULAR_DRIVE_START' in names


def test_nonperiodic_stimulus_does_not_reset_volume():
    e = Engine(sensors=())
    e.schedule_stimulus(100000,'ventricular')
    e.schedule_stimulus(421750,'ventricular')
    e.advance_to(421749)
    before = e.model.state.volumes.copy()
    e.advance_to(421750)
    assert max(abs(a-b) for a,b in zip(e.model.state.volumes,before)) < .01


def test_pending_cancel_does_not_inflate():
    e = Engine(model_config=ModelConfig(balloon_enabled=True), sensors=())
    assert e.submit(Command('i','INFLATE',0,10000)).status == 'accepted'
    assert e.submit(Command('c','CANCEL_PENDING',0,cancels_command_id='i')).status == 'accepted'
    e.advance_to(100000)
    assert e.model.state.balloon_v == 0


def test_started_cancel_rejected_and_reverse_preserves_volume():
    e = Engine(model_config=ModelConfig(balloon_enabled=True), sensors=())
    e.submit(Command('i','INFLATE',0))
    e.advance_to(50000)
    vb = e.model.state.balloon_v
    assert vb > 0
    assert e.submit(Command('c','CANCEL_PENDING',50000,cancels_command_id='i')).status == 'rejected'
    e.submit(Command('d','DEFLATE',50000))
    assert e.model.state.balloon_v == vb
    e.advance_to(200000)
    assert e.model.state.balloon_v < vb


def test_command_transport_latency_separate_from_motion():
    e = Engine(model_config=ModelConfig(balloon_enabled=True), sensors=())
    e.submit(Command('i','INFLATE',0))
    e.advance_to(5000)
    assert e.model.state.balloon_v == 0  # start occurs, volume remains continuous
    assert [x.at_us for x in e.command_log if x.status=='started'] == [5000]
    e.advance_to(6000)
    assert e.model.state.balloon_v > 0


def test_reject_late_duplicate_and_disabled_commands():
    e = Engine(model_config=ModelConfig(balloon_enabled=True), sensors=())
    e.submit(Command('x','INFLATE',0))
    assert e.submit(Command('x','INFLATE',0)).reason == 'duplicate_id'
    e.advance_to(10000)
    assert e.submit(Command('y','DEFLATE',10000,9999)).status == 'rejected'
    assert Engine().submit(Command('z','INFLATE',0)).reason == 'actuator_disabled'


def test_same_timestamp_last_command_wins_deterministically():
    e = Engine(model_config=ModelConfig(balloon_enabled=True), sensors=())
    e.submit(Command('i','INFLATE',0))
    e.submit(Command('d','DEFLATE',0))
    e.advance_to(10000)
    assert not e.model.inflate and e.model.state.balloon_v == 0
    assert any(x.command_id=='i' and x.status=='superseded' for x in e.command_log)


def test_clock_drift_changes_sampling_grid_and_stamp():
    e = Engine(sensors=(ap(drift_ppm=1000, clock_offset_us=500),))
    samples = e.advance_to(10000)
    assert samples[1].t_available_us == 999
    assert samples[1].source_time_us == 1500


def test_dropped_samples_have_sequence_gaps():
    e = Engine(sensors=(ap(drop_every=2),))
    assert [s.sequence_id for s in e.advance_to(4000)] == [0,2,4]


@pytest.mark.parametrize('site,units', [('unknown','mmHg'),('p_root','mV')])
def test_invalid_sensor_mapping_rejected(site, units):
    with pytest.raises(ValueError):
        SensorConfig('bad',site,units)


def test_duplicate_channels_rejected():
    with pytest.raises(ValueError):
        Engine(sensors=(ap(),ap()))


def test_backward_time_rejected():
    e = Engine(sensors=())
    e.advance_to(1000)
    with pytest.raises(ValueError):
        e.advance_to(999)


def test_partitioned_advances_on_core_grid_preserve_results():
    a, b = Engine(), Engine()
    x = a.advance_to(10000)
    y = []
    for t in range(1000,10001,1000):
        y.extend(b.advance_to(t))
    assert x == y and a.model.state == b.model.state


def test_filter_constant_input_has_exact_known_response():
    import math
    from iabp.sensors import Sensor
    sensor = Sensor(ap(tau_us=10000), 1, 0)
    sensor.advance(100, 4000)
    assert sensor.filtered == pytest.approx(100*(1-math.exp(-.4)))


def test_snapshot_preserves_started_motion_and_pending_reverse():
    e = Engine(model_config=ModelConfig(balloon_enabled=True))
    e.submit(Command('i','INFLATE',0))
    e.submit(Command('d','DEFLATE',0,150000))
    e.advance_to(75000)
    fork = Engine.from_snapshot(e.snapshot())
    assert fork.advance_to(300000) == e.advance_to(300000)
    assert fork.model.state == e.model.state
    assert fork.command_log == e.command_log


def test_unstimulated_model_does_not_invent_ac_events():
    e = Engine(sensors=())
    e.advance_to(500000)
    assert not any(x.name == 'QRS_ONSET' for x in e.truth_events)
    assert not any(x.name == 'AORTIC_CLOSE_02' for x in e.truth_events)
