"""Deterministic continuous-time harness with integer-microsecond event clocks.

Priority at a boundary: external electrical/activation events; previously queued
commands; acquisition; delivery. A controller can submit only AFTER delivery.
The controller-facing protocol is data separation, not a hostile-code sandbox.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from heapq import heappop, heappush
from math import exp, sin, pi
from typing import Literal

from .contracts import Command, CommandStatus, Sample
from .model import Model, ModelConfig, VALVE_NAMES
from .sensors import Sensor, SensorConfig, reference_sensors

# (time, priority, serial, kind, tag, generation)
QueuedEvent = tuple[int, int, int, str, str, int]


@dataclass(frozen=True)
class EngineConfig:
    step_us: int = 250
    seed: int = 20261015
    command_latency_us: int = 5000

    def __post_init__(self) -> None:
        if type(self.step_us) is not int or not 1 <= self.step_us <= 250:
            raise ValueError("step_us must be an integer in [1,250]")
        if type(self.seed) is not int:
            raise ValueError("seed must be integer")
        if type(self.command_latency_us) is not int or self.command_latency_us < 0:
            raise ValueError("invalid command latency")


@dataclass(frozen=True)
class TruthEvent:
    name: str
    at_us: int
    definition: str


@dataclass
class Snapshot:
    """Trusted in-process snapshot only. No pickle file loading or portable ABI yet."""
    version: str
    engine: Engine


class Engine:
    def __init__(self, config: EngineConfig | None = None,
                 model_config: ModelConfig | None = None,
                 sensors: tuple[SensorConfig, ...] | None = None) -> None:
        self.config = config or EngineConfig()
        self.model = Model(model_config)
        self.now_us = 0
        self._events: list[QueuedEvent] = []
        self._serial = 0
        self._generation = {"atrial": 0, "ventricular": 0}
        self._electrical: list[tuple[int, str]] = []
        self._delivered: list[Sample] = []
        self._in_transit: list[tuple[int, int, Sample]] = []
        self._commands: dict[str, Command] = {}
        self._command_states: dict[str, str] = {}
        self._active_command: str | None = None
        self.command_log: list[CommandStatus] = []
        self.truth_events: list[TruthEvent] = []
        self.sample_audit: list[tuple[int, Sample]] = []
        self._last_processed_us = -1
        cfgs = reference_sensors() if sensors is None else sensors
        if len({c.channel_id for c in cfgs}) != len(cfgs):
            raise ValueError("duplicate sensor channel id")
        self._sensors = [Sensor(c, self.config.seed, self._raw(c.site)) for c in cfgs]

    def _queue(self, at_us: int, priority: int, kind: str, tag: str, generation: int = 0) -> None:
        self._serial += 1
        heappush(self._events, (at_us, priority, self._serial, kind, tag, generation))

    def schedule_stimulus(self, at_us: int, chamber: Literal['atrial', 'ventricular']) -> None:
        if type(at_us) is not int or at_us < self.now_us or chamber not in self._generation:
            raise ValueError("invalid stimulus or time in the past")
        self._queue(at_us, 0, "electrical", chamber)
        self._last_processed_us = -1

    def _raw(self, site: str) -> float:
        if site != "ecg_ii":
            p = self.model.pressures()
            return p[1] if site == 'p_root' else p[2]
        return self.ecg(self.now_us)

    def ecg(self, at_us: int) -> float:
        """Causal morphology observation of processed electrical events only.

        Not a whole-heart electrical field solver. No earlier output depends on
        scheduled but unprocessed stimuli; QRS onset is distinct from its R peak.
        """
        total = 0.
        for t, chamber in reversed(self._electrical):
            u = (at_us-t)/1000
            if u > 600:
                break
            if u < 0:
                continue
            if chamber == 'atrial' and u < 90:
                total += .16*sin(pi*u/90)**2
            elif chamber == 'ventricular':
                if u < 95:
                    window = sin(pi*u/95)**2
                    total += window*(1.5*exp(-.5*((u-30)/6)**2)
                                     -.2*exp(-.5*((u-14)/4)**2)
                                     -.4*exp(-.5*((u-48)/6)**2))
                if 220 < u < 380:
                    total += .25*sin(pi*(u-220)/160)**2
        return total

    def submit(self, command: Command) -> CommandStatus:
        reason = ''
        when = command.t_execute_us if command.t_execute_us is not None else self.now_us
        if not command.command_id:
            reason = 'empty_id'
        elif command.command_id in self._commands:
            reason = 'duplicate_id'
        elif type(command.t_issued_us) is not int or command.t_issued_us != self.now_us:
            reason = 'issued_time_must_equal_current_time'
        elif type(when) is not int or when < self.now_us:
            reason = 'past_or_invalid_execute_time'
        elif command.action not in ('INFLATE', 'DEFLATE', 'CANCEL_PENDING'):
            reason = 'invalid_action'
        elif command.action != 'CANCEL_PENDING' and not self.model.config.balloon_enabled:
            reason = 'actuator_disabled'
        if not reason and command.action == 'CANCEL_PENDING':
            target = command.cancels_command_id
            if when != self.now_us:
                reason = 'cancellation_must_be_immediate'
            elif target is None or self._command_states.get(target) != 'accepted':
                reason = 'target_not_pending'
            else:
                self._command_states[target] = 'cancelled'
                self.command_log.append(CommandStatus(target, 'cancelled', self.now_us))
        status = CommandStatus(command.command_id, 'rejected' if reason else 'accepted',
                               self.now_us, reason)
        self.command_log.append(status)
        if reason:
            return status
        self._commands[command.command_id] = command
        self._command_states[command.command_id] = 'accepted'
        if command.action == 'CANCEL_PENDING':
            self._command_states[command.command_id] = 'completed'
            self.command_log.append(CommandStatus(command.command_id, 'completed', self.now_us))
        else:
            self._queue(when+self.config.command_latency_us, 1, 'command', command.command_id)
            self._last_processed_us = -1
        return status

    def _process_boundary(self) -> None:
        if self._last_processed_us == self.now_us:
            return
        while self._events and self._events[0][0] <= self.now_us:
            t, _, _, kind, tag, gen = heappop(self._events)
            if kind == 'electrical':
                self._electrical.append((t, tag))
                self._generation[tag] += 1
                g = self._generation[tag]
                self.truth_events.append(TruthEvent('P_ONSET' if tag == 'atrial' else 'QRS_ONSET',
                                                    t, 'external electrical stimulus'))
                delay = 20000 if tag == 'atrial' else 35000
                self._queue(t+delay, 0, 'start', tag, g)
                self._queue(t+delay+(100000 if tag == 'atrial' else 230000), 0, 'end', tag, g)
            elif kind in ('start','end') and gen == self._generation[tag]:
                if kind == 'start':
                    self.model.excite(tag)
                else:
                    self.model.release(tag)
                self.truth_events.append(TruthEvent(f'{tag.upper()}_DRIVE_{kind.upper()}', t,
                                                   'uncalibrated effective tension drive'))
            elif kind == 'command' and self._command_states.get(tag) == 'accepted':
                if self._active_command is not None:
                    prior = self._active_command
                    if self._command_states[prior] == 'started':
                        self._command_states[prior] = 'superseded'
                        self.command_log.append(CommandStatus(prior, 'superseded', self.now_us))
                self._active_command = tag
                self.model.inflate = self._commands[tag].action == 'INFLATE'
                self._command_states[tag] = 'started'
                self.command_log.append(CommandStatus(tag, 'started', self.now_us))
        for sensor in self._sensors:
            if sensor.next_sample_us() == self.now_us:
                sample = sensor.sample(self.now_us, self._raw(sensor.config.site))
                if sample is not None:
                    self._serial += 1
                    heappush(self._in_transit, (sample.t_available_us, self._serial, sample))
                    self.sample_audit.append((self.now_us, sample))
        while self._in_transit and self._in_transit[0][0] <= self.now_us:
            self._delivered.append(heappop(self._in_transit)[2])
        self._last_processed_us = self.now_us

    def _track(self, previous: dict[str, float], start: int) -> None:
        obs = self.model.observe()
        for name in VALVE_NAMES:
            old, new = previous[f'z_{name}'], obs[f'z_{name}']
            for direction, threshold in (('OPEN_05',.05), ('CLOSE_02',.02)):
                hit = old < threshold <= new if direction == 'OPEN_05' else old > threshold >= new
                if hit:
                    t = start + round((self.now_us-start)*(threshold-old)/(new-old))
                    self.truth_events.append(TruthEvent(name.upper()+'_'+direction, t,
                                                       f'effective opening threshold {threshold}; not leaflet truth'))
        old_dp, new_dp = previous['p_lv']-previous['p_root'], obs['p_lv']-obs['p_root']
        if old_dp > 0 >= new_dp:
            t = start + round((self.now_us-start)*old_dp/(old_dp-new_dp))
            self.truth_events.append(TruthEvent('DP_LV_AO_REVERSE', t,
                                                'positive-to-negative LV-root pressure difference'))
        old, new = previous['q_ao'], obs['q_ao']
        if old > 0 >= new:
            t = start + round((self.now_us-start)*old/(old-new))
            self.truth_events.append(TruthEvent('QAO_ZERO', t, 'forward-to-reverse flow zero crossing'))
        if self._active_command:
            ident = self._active_command
            if self._command_states[ident] == 'started':
                vb = obs['v_balloon']
                done = vb >= .95*self.model.config.balloon_capacity if self.model.inflate else vb <= .5
                if done:
                    self._command_states[ident] = 'completed'
                    self.command_log.append(CommandStatus(ident, 'completed', self.now_us,
                        'engineering threshold: >=95% nominal capacity or <=0.5 mL; not clinical'))

    def advance_to(self, until_us: int) -> list[Sample]:
        if type(until_us) is not int or until_us < self.now_us:
            raise ValueError("target time must be integer microseconds, not in past")
        self._process_boundary()
        while self.now_us < until_us:
            next_time = min(until_us, (self.now_us//self.config.step_us+1)*self.config.step_us)
            if self._events:
                next_time = min(next_time, self._events[0][0])
            if self._in_transit:
                next_time = min(next_time, self._in_transit[0][0])
            for s in self._sensors:
                next_time = min(next_time, s.next_sample_us())
            if next_time <= self.now_us:
                raise RuntimeError('scheduler failed to progress')
            old_raw = [self._raw(s.config.site) for s in self._sensors]
            previous = self.model.observe()
            start = self.now_us
            self.model.advance((next_time-start)/1e6)
            self.now_us = next_time
            for s, old in zip(self._sensors, old_raw):
                s.advance((old+self._raw(s.config.site))/2, next_time-start)
            self._track(previous, start)
            self._process_boundary()
        samples, self._delivered = self._delivered, []
        return samples

    def snapshot(self) -> Snapshot:
        return Snapshot('0.2.0', deepcopy(self))

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot) -> Engine:
        if snapshot.version != '0.2.0':
            raise ValueError('incompatible snapshot version')
        return deepcopy(snapshot.engine)

    def evaluator_truth(self) -> dict[str, float]:
        return {'time_us': float(self.now_us), 'ecg_ii': self.ecg(self.now_us), **self.model.observe()}
