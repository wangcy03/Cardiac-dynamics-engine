"""Conservative finite volumes with a preserved first-order Rusanov baseline.

MUSCL/SSPRK2 is an explicitly named comparison, not a replacement of the baseline.
The unlimited linear3/SSPRK3 experiment is for smooth small-amplitude waves only;
it is not TVD, may ring, and does not claim shock robustness.
Junctions use common static pressure and omit dynamic-head/geometric losses.
"""
from dataclasses import dataclass
import math

from .boundaries import Boundary, outgoing_invariant
from .physics import (
    ArterialError, BoundaryError, CFLViolation, FaceState, Flux, NonPhysicalState,
    Scheme, SegmentConfig, Side, State,
    positive_finite, require_subcritical, validate_face,
)


@dataclass(frozen=True)
class VolumeLedger:
    initial_volume_m3: float
    left_inflow_m3: float
    right_outflow_m3: float
    current_volume_m3: float
    residual_m3: float


@dataclass(frozen=True)
class StepResult:
    state: State
    face_fluxes: tuple[Flux, ...]
    left_volume_m3: float
    right_volume_m3: float
    volume_before_m3: float
    volume_after_m3: float
    volume_residual_m3: float
    momentum_source_integral_m4_s: float
    max_wave_speed_m_s: float


@dataclass(frozen=True)
class Junction:
    parent: str
    children: tuple[str, ...]


@dataclass(frozen=True)
class JunctionState:
    parent: str
    children: tuple[str, ...]
    time_s: float
    pressure_pa: float
    parent_flow_m3_s: float
    child_flows_m3_s: tuple[float, ...]
    continuity_residual_m3_s: float
    parent_characteristic_residual_m_s: float


@dataclass(frozen=True)
class NetworkVolumeLedger:
    initial_volume_m3: float
    external_net_volume_m3: float
    current_volume_m3: float
    residual_m3: float


@dataclass(frozen=True)
class NetworkStepResult:
    segments: dict[str, StepResult]
    junctions: tuple[JunctionState, ...]
    external_net_volume_m3: float
    volume_before_m3: float
    volume_after_m3: float
    volume_residual_m3: float


@dataclass(frozen=True)
class _Stage:
    fluxes: tuple[Flux, ...]
    source: tuple[float, ...]
    maximum_speed: float


def _validate_state(config: SegmentConfig, state: State) -> None:
    if len(state.area_m2) != config.cells or len(state.flow_m3_s) != config.cells:
        raise NonPhysicalState("state arrays must match SegmentConfig.cells")
    if not math.isfinite(state.time_s) or state.time_s < 0.0:
        raise NonPhysicalState("time_s must be finite and nonnegative")
    for area, flow in zip(state.area_m2, state.flow_m3_s, strict=True):
        positive_finite(area, "cell area_m2")
        if not math.isfinite(flow):
            raise NonPhysicalState("cell flow_m3_s must be finite")


def _minmod(left: float, right: float) -> float:
    if left * right <= 0.0:
        return 0.0
    return math.copysign(min(abs(left), abs(right)), left)


def _slopes(values: tuple[float, ...]) -> tuple[float, ...]:
    # Minmod with theta=1.5, including one-sided endpoint traces. Reconstructed
    # faces are validated; a failed reconstruction is never clipped to positive A.
    slopes = [values[1] - values[0]]
    for i in range(1, len(values) - 1):
        backward, forward = values[i] - values[i - 1], values[i + 1] - values[i]
        slopes.append(_minmod(0.5 * (backward + forward), _minmod(1.5 * backward, 1.5 * forward)))
    slopes.append(values[-1] - values[-2])
    return tuple(slopes)


def _traces(state: State, scheme: Scheme) -> tuple[tuple[FaceState, ...], tuple[FaceState, ...]]:
    if scheme == "rusanov":
        faces = tuple(FaceState(a, q) for a, q in zip(state.area_m2, state.flow_m3_s, strict=True))
        return faces, faces
    if scheme == "linear3_ssprk3":
        left_a, right_a = _linear3_values(state.area_m2)
        left_q, right_q = _linear3_values(state.flow_m3_s)
        return (
            tuple(FaceState(a, q) for a, q in zip(left_a, left_q, strict=True)),
            tuple(FaceState(a, q) for a, q in zip(right_a, right_q, strict=True)),
        )
    da, dq = _slopes(state.area_m2), _slopes(state.flow_m3_s)
    left = tuple(
        FaceState(a - 0.5 * sa, q - 0.5 * sq)
        for a, q, sa, sq in zip(state.area_m2, state.flow_m3_s, da, dq, strict=True)
    )
    right = tuple(
        FaceState(a + 0.5 * sa, q + 0.5 * sq)
        for a, q, sa, sq in zip(state.area_m2, state.flow_m3_s, da, dq, strict=True)
    )
    return left, right


def _linear3_values(values: tuple[float, ...]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Third-order FV face values, including one-sided endpoint quadratics.

    Difference forms preserve a constant background exactly. No limiter/clipping
    is used: this experimental reconstruction can ring on nonsmooth data.
    """
    left, right = [], []
    d1, d2 = values[1] - values[0], values[2] - values[0]
    left.append(values[0] + (-7.0 * d1 + 2.0 * d2) / 6.0)
    right.append(values[0] + (5.0 * d1 - d2) / 6.0)
    for i in range(1, len(values) - 1):
        backward, forward = values[i - 1] - values[i], values[i + 1] - values[i]
        left.append(values[i] + (2.0 * backward - forward) / 6.0)
        right.append(values[i] + (-backward + 2.0 * forward) / 6.0)
    d1, d2 = values[-2] - values[-1], values[-3] - values[-1]
    left.append(values[-1] + (5.0 * d1 - d2) / 6.0)
    right.append(values[-1] + (-7.0 * d1 + 2.0 * d2) / 6.0)
    return tuple(left), tuple(right)


class Segment:
    """One uniform tube; all boundaries are physical characteristic face states."""

    def __init__(
        self, config: SegmentConfig, initial_state: State | None = None,
        scheme: Scheme = "rusanov",
    ) -> None:
        if scheme not in ("rusanov", "muscl_ssprk2", "linear3_ssprk3"):
            raise ArterialError(f"unknown scheme {scheme!r}")
        if scheme == "linear3_ssprk3" and config.cells < 3:
            raise ArterialError("linear3_ssprk3 requires at least 3 cells")
        self.config = config
        self.scheme: Scheme = scheme
        self._state = initial_state if initial_state is not None else State(
            (config.law.reference_area_m2,) * config.cells, (0.0,) * config.cells
        )
        _validate_state(config, self._state)
        self._initial_volume = self.volume_m3
        self._left_integral = 0.0
        self._right_integral = 0.0

    @property
    def state(self) -> State:
        return self._state

    @property
    def volume_m3(self) -> float:
        return math.fsum(self._state.area_m2) * self.config.dx_m

    @property
    def ledger(self) -> VolumeLedger:
        current = self.volume_m3
        residual = math.fsum((
            current, -self._initial_volume, -self._left_integral, self._right_integral,
        ))
        return VolumeLedger(
            self._initial_volume, self._left_integral, self._right_integral, current, residual
        )

    def coordinates_m(self) -> tuple[float, ...]:
        return tuple((i + 0.5) * self.config.dx_m for i in range(self.config.cells))

    def pressure_pa(self) -> tuple[float, ...]:
        return tuple(self.config.law.pressure_pa(area) for area in self._state.area_m2)

    def sample_pressure_pa(self, x_m: float) -> float:
        if not math.isfinite(x_m) or not 0.0 <= x_m <= self.config.length_m:
            raise ArterialError("pressure sample coordinate must be inside [0, length_m]")
        coordinate = x_m / self.config.dx_m - 0.5
        if coordinate <= 0.0:
            return self.config.law.pressure_pa(self._state.area_m2[0])
        if coordinate >= self.config.cells - 1:
            return self.config.law.pressure_pa(self._state.area_m2[-1])
        index = int(coordinate)
        fraction = coordinate - index
        p0 = self.config.law.pressure_pa(self._state.area_m2[index])
        p1 = self.config.law.pressure_pa(self._state.area_m2[index + 1])
        return (1.0 - fraction) * p0 + fraction * p1

    def _state_limit(self, state: State) -> float:
        maximum = max(
            abs(q / a) + self.config.law.wave_speed_m_s(a)
            for a, q in zip(state.area_m2, state.flow_m3_s, strict=True)
        )
        transport = self.config.cfl * self.config.dx_m / maximum
        viscosity = self.config.kinematic_viscosity_m2_s
        if viscosity > 0.0:
            # Explicit Poiseuille source: Q'=-k Q; dt<=1/k avoids sign reversal.
            return min(transport, min(state.area_m2) / (8.0 * math.pi * viscosity))
        return transport

    def max_stable_dt_s(self) -> float:
        """Current-state limit; step also checks reconstructed/boundary stage states."""
        return self._state_limit(self._state)

    def _stage(
        self, state: State, dt_s: float, left: FaceState, right: FaceState,
        traces: tuple[tuple[FaceState, ...], tuple[FaceState, ...]],
    ) -> _Stage:
        before, after = traces
        law = self.config.law
        reference_area, beta, rho = law.reference_area_m2, law.beta_pa, law.density_kg_m3
        sound_coefficient = beta / (2.0 * rho)
        momentum_denominator = 3.0 * rho

        def cache(face: FaceState) -> tuple[float, float, float]:
            # Compute/validate once per trace and share with Rusanov and CFL.
            # Arithmetic order matches the original public physics functions.
            validate_face(face)
            area, flow = face.area_m2, face.flow_m3_s
            root = math.sqrt(area / reference_area)
            speed = math.sqrt(sound_coefficient * root)
            velocity = flow / area
            maximum = max(abs(velocity - speed), abs(velocity + speed))
            momentum = flow * flow / area + beta * area * root / momentum_denominator
            if not math.isfinite(momentum):
                raise NonPhysicalState("momentum flux is nonfinite")
            return flow, momentum, maximum

        cached_before = tuple(cache(face) for face in before)
        cached_after = cached_before if before is after else tuple(cache(face) for face in after)
        cached_left, cached_right = cache(left), cache(right)
        maximum = max(
            max(item[2] for item in cached_before), max(item[2] for item in cached_after),
            cached_left[2], cached_right[2],
        )
        limit = min(self._state_limit(state), self.config.cfl * self.config.dx_m / maximum)
        if dt_s > limit * (1.0 + 1e-12):
            raise CFLViolation(dt_s, limit)
        fluxes = [Flux(cached_left[0], cached_left[1])]
        for i in range(self.config.cells - 1):
            ql, ml, sl = cached_after[i]
            qr, mr, sr = cached_before[i + 1]
            maximum_face = max(sl, sr)
            fluxes.append(Flux(
                0.5 * (ql + qr) - 0.5 * maximum_face * (before[i + 1].area_m2 - after[i].area_m2),
                0.5 * (ml + mr) - 0.5 * maximum_face * (before[i + 1].flow_m3_s - after[i].flow_m3_s),
            ))
        fluxes.append(Flux(cached_right[0], cached_right[1]))
        coefficient = -8.0 * math.pi * self.config.kinematic_viscosity_m2_s
        source = tuple(
            coefficient * q / a
            for a, q in zip(state.area_m2, state.flow_m3_s, strict=True)
        )
        return _Stage(tuple(fluxes), source, maximum)

    def _euler(self, state: State, dt_s: float, stage: _Stage) -> State:
        ratio = dt_s / self.config.dx_m
        area = tuple(
            state.area_m2[i] - ratio * (
                stage.fluxes[i + 1].area_flux_m3_s - stage.fluxes[i].area_flux_m3_s
            ) for i in range(self.config.cells)
        )
        flow = tuple(
            state.flow_m3_s[i] - ratio * (
                stage.fluxes[i + 1].momentum_flux_m4_s2 - stage.fluxes[i].momentum_flux_m4_s2
            ) + dt_s * stage.source[i] for i in range(self.config.cells)
        )
        candidate = State(area, flow, state.time_s + dt_s)
        _validate_state(self.config, candidate)
        return candidate

    def _result(
        self, before: State, after: State, dt_s: float, stages: tuple[_Stage, ...],
        weights: tuple[float, ...] | None = None,
    ) -> StepResult:
        if weights is None:
            # Preserve the original Euler/SSPRK2 floating-point path exactly.
            weight = 1.0 / len(stages)
            fluxes = tuple(Flux(
                math.fsum(stage.fluxes[i].area_flux_m3_s for stage in stages) * weight,
                math.fsum(stage.fluxes[i].momentum_flux_m4_s2 for stage in stages) * weight,
            ) for i in range(self.config.cells + 1))
            source_integral = (
                dt_s * self.config.dx_m * weight
                * math.fsum(value for stage in stages for value in stage.source)
            )
        else:
            fluxes = tuple(Flux(
                math.fsum(w * stage.fluxes[i].area_flux_m3_s for w, stage in zip(weights, stages, strict=True)),
                math.fsum(w * stage.fluxes[i].momentum_flux_m4_s2 for w, stage in zip(weights, stages, strict=True)),
            ) for i in range(self.config.cells + 1))
            source_integral = dt_s * self.config.dx_m * math.fsum(
                w * value for w, stage in zip(weights, stages, strict=True) for value in stage.source
            )
        left_volume = dt_s * fluxes[0].area_flux_m3_s
        right_volume = dt_s * fluxes[-1].area_flux_m3_s
        volume_before = math.fsum(before.area_m2) * self.config.dx_m
        volume_after = math.fsum(after.area_m2) * self.config.dx_m
        residual = math.fsum((volume_after, -volume_before, -left_volume, right_volume))
        return StepResult(
            after, fluxes, left_volume, right_volume, volume_before, volume_after,
            residual, source_integral, max(stage.maximum_speed for stage in stages),
        )

    def _commit(self, result: StepResult) -> None:
        self._state = result.state
        self._left_integral += result.left_volume_m3
        self._right_integral += result.right_volume_m3

    def step(self, dt_s: float, left: Boundary, right: Boundary) -> StepResult:
        # Reuse the same network stepper so single-tube and branch semantics cannot drift.
        network = Network({"segment": self}, {("segment", "left"): left, ("segment", "right"): right})
        return network.step(dt_s).segments["segment"]


class Network:
    """A directed network of uniform segments, with atomic whole-network steps."""

    def __init__(
        self, segments: dict[str, Segment], boundaries: dict[tuple[str, Side], Boundary],
        junctions: tuple[Junction, ...] = (),
    ) -> None:
        if not segments:
            raise ArterialError("network requires at least one segment")
        self.segments = dict(segments)
        self.boundaries = dict(boundaries)
        self.junctions = junctions
        schemes = {segment.scheme for segment in segments.values()}
        if len(schemes) != 1:
            raise ArterialError("all network segments must use the same explicit scheme")
        if len({id(segment) for segment in segments.values()}) != len(segments):
            raise ArterialError("a Segment instance cannot occupy multiple network positions")
        if len({segment.state.time_s for segment in segments.values()}) != 1:
            raise ArterialError("all network segments must have the same time_s")
        self.scheme = next(iter(schemes))
        expected = {(name, side) for name in segments for side in ("left", "right")}
        occupied: set[tuple[str, str]] = set(boundaries)
        if not occupied <= expected:
            raise ArterialError("boundary references an unknown segment or side")
        for junction in junctions:
            if not junction.children or len(set(junction.children)) != len(junction.children):
                raise ArterialError("junction requires unique children")
            endpoints = [(junction.parent, "right")] + [(child, "left") for child in junction.children]
            if junction.parent in junction.children:
                raise ArterialError("junction cannot connect a segment to itself")
            for endpoint in endpoints:
                if endpoint not in expected or endpoint in occupied:
                    raise ArterialError("junction has an unknown or multiply assigned endpoint")
                occupied.add(endpoint)
        if occupied != expected:
            raise ArterialError("every segment endpoint requires exactly one boundary or junction")
        self._initial_volume = self.volume_m3
        self._external_integral = 0.0

    @property
    def volume_m3(self) -> float:
        return math.fsum(segment.volume_m3 for segment in self.segments.values())

    @property
    def ledger(self) -> NetworkVolumeLedger:
        current = self.volume_m3
        return NetworkVolumeLedger(
            self._initial_volume, self._external_integral, current,
            math.fsum((current, -self._initial_volume, -self._external_integral)),
        )

    def max_stable_dt_s(self) -> float:
        return min(segment.max_stable_dt_s() for segment in self.segments.values())

    def _junction_faces(
        self, junction: Junction,
        traces: dict[str, tuple[tuple[FaceState, ...], tuple[FaceState, ...]]],
        time_s: float,
    ) -> tuple[dict[tuple[str, Side], FaceState], JunctionState]:
        names = (junction.parent,) + junction.children
        sides: tuple[Side, ...] = tuple(
            "right" if i == 0 else "left" for i in range(len(names))
        )
        laws = tuple(self.segments[name].config.law for name in names)
        interiors = tuple(
            traces[name][1][-1] if side == "right" else traces[name][0][0]
            for name, side in zip(names, sides, strict=True)
        )
        invariants = tuple(
            outgoing_invariant(law, face, side)
            for law, face, side in zip(laws, interiors, sides, strict=True)
        )
        # Convert each tube's subcritical c interval to P, then intersect the ranges.
        low, high = -math.inf, math.inf
        for law, invariant in zip(laws, invariants, strict=True):
            c0 = law.wave_speed_m_s(law.reference_area_m2)
            lower_c, upper_c = abs(invariant) / 5.0, abs(invariant) / 3.0
            lower_p = law.reference_pressure_pa + law.beta_pa * ((lower_c / c0) ** 2 - 1.0)
            upper_p = law.reference_pressure_pa + law.beta_pa * ((upper_c / c0) ** 2 - 1.0)
            low, high = max(low, lower_p), min(high, upper_p)
        low, high = math.nextafter(low, math.inf), math.nextafter(high, -math.inf)
        if not low < high:
            raise BoundaryError("junction has no common subcritical static-pressure interval")

        def states_at(pressure: float) -> tuple[tuple[FaceState, ...], float]:
            faces = []
            for law, invariant, side in zip(laws, invariants, sides, strict=True):
                area = law.area_from_pressure_pa(pressure)
                speed = law.wave_speed_m_s(area)
                velocity = invariant - 4.0 * speed if side == "right" else invariant + 4.0 * speed
                faces.append(FaceState(area, area * velocity))
            residual = faces[0].flow_m3_s - math.fsum(face.flow_m3_s for face in faces[1:])
            return tuple(faces), residual

        _, fl = states_at(low)
        _, fh = states_at(high)
        if fl * fh > 0.0:
            raise BoundaryError("junction continuity has no subcritical common-pressure root")
        for _ in range(90):
            mid = 0.5 * (low + high)
            _, fm = states_at(mid)
            if fm == 0.0 or mid == low or mid == high:
                low = high = mid
                break
            if fl * fm <= 0.0:
                high = mid
            else:
                low, fl = mid, fm
        pressure = 0.5 * (low + high)
        faces, _ = states_at(pressure)
        child_sum = math.fsum(face.flow_m3_s for face in faces[1:])
        # The root is resolved to floating-point precision. Use the very same summed
        # child flux at the parent face; do not label unrelated ghost fluxes conservative.
        parent = FaceState(faces[0].area_m2, child_sum)
        adjusted = (parent,) + faces[1:]
        for law, face in zip(laws, adjusted, strict=True):
            require_subcritical(law, face)
        char_residual = (
            parent.flow_m3_s / parent.area_m2 + 4.0 * laws[0].wave_speed_m_s(parent.area_m2)
            - invariants[0]
        )
        tolerance = 1e-11 * max(1.0, abs(invariants[0]))
        if abs(char_residual) > tolerance:
            raise BoundaryError("junction continuity correction exceeds characteristic roundoff budget")
        mapping = {
            (name, side): face for name, side, face in zip(names, sides, adjusted, strict=True)
        }
        record = JunctionState(
            junction.parent, junction.children, time_s, pressure, parent.flow_m3_s,
            tuple(face.flow_m3_s for face in faces[1:]), 0.0, char_residual,
        )
        return mapping, record

    def _stages(
        self, states: dict[str, State], dt_s: float,
    ) -> tuple[dict[str, _Stage], tuple[JunctionState, ...]]:
        traces = {name: _traces(state, self.scheme) for name, state in states.items()}
        faces: dict[tuple[str, Side], FaceState] = {}
        for (name, side), boundary in self.boundaries.items():
            interior = traces[name][0][0] if side == "left" else traces[name][1][-1]
            faces[(name, side)] = boundary.evaluate(
                law=self.segments[name].config.law, interior=interior, side=side,
                time_s=states[name].time_s,
            )
        records = []
        for junction in self.junctions:
            mapping, record = self._junction_faces(junction, traces, states[junction.parent].time_s)
            faces.update(mapping)
            records.append(record)
        stages = {
            name: segment._stage(state, dt_s, faces[(name, "left")], faces[(name, "right")], traces[name])
            for name, segment in self.segments.items() for state in (states[name],)
        }
        return stages, tuple(records)

    def step(self, dt_s: float) -> NetworkStepResult:
        positive_finite(dt_s, "dt_s")
        if len({segment.state.time_s for segment in self.segments.values()}) != 1:
            raise ArterialError("all network segments must have the same time_s before stepping")
        before = {name: segment.state for name, segment in self.segments.items()}
        stage1, records = self._stages(before, dt_s)
        candidates = {
            name: segment._euler(before[name], dt_s, stage1[name])
            for name, segment in self.segments.items()
        }
        stage_groups: dict[str, tuple[_Stage, ...]] = {
            name: (stage1[name],) for name in self.segments
        }
        weights: tuple[float, ...] | None = None
        if self.scheme == "muscl_ssprk2":
            stage2, records2 = self._stages(candidates, dt_s)
            predicted = {
                name: segment._euler(candidates[name], dt_s, stage2[name])
                for name, segment in self.segments.items()
            }
            candidates = {
                name: State(
                    tuple(0.5 * (a + b) for a, b in zip(
                        before[name].area_m2, predicted[name].area_m2, strict=True
                    )),
                    tuple(0.5 * (a + b) for a, b in zip(
                        before[name].flow_m3_s, predicted[name].flow_m3_s, strict=True
                    )),
                    before[name].time_s + dt_s,
                ) for name in self.segments
            }
            stage_groups = {name: (stage1[name], stage2[name]) for name in self.segments}
            records += records2
        elif self.scheme == "linear3_ssprk3":
            stage2, records2 = self._stages(candidates, dt_s)
            predicted = {
                name: segment._euler(candidates[name], dt_s, stage2[name])
                for name, segment in self.segments.items()
            }
            midpoint = {
                name: State(
                    tuple(a + 0.25 * (b - a) for a, b in zip(
                        before[name].area_m2, predicted[name].area_m2, strict=True
                    )),
                    tuple(a + 0.25 * (b - a) for a, b in zip(
                        before[name].flow_m3_s, predicted[name].flow_m3_s, strict=True
                    )),
                    before[name].time_s + 0.5 * dt_s,
                ) for name in self.segments
            }
            for name, state in midpoint.items():
                _validate_state(self.segments[name].config, state)
            stage3, records3 = self._stages(midpoint, dt_s)
            predicted = {
                name: segment._euler(midpoint[name], dt_s, stage3[name])
                for name, segment in self.segments.items()
            }
            candidates = {
                name: State(
                    tuple(a + (2.0 / 3.0) * (b - a) for a, b in zip(
                        before[name].area_m2, predicted[name].area_m2, strict=True
                    )),
                    tuple(a + (2.0 / 3.0) * (b - a) for a, b in zip(
                        before[name].flow_m3_s, predicted[name].flow_m3_s, strict=True
                    )),
                    before[name].time_s + dt_s,
                ) for name in self.segments
            }
            stage_groups = {name: (stage1[name], stage2[name], stage3[name]) for name in self.segments}
            weights = (1.0 / 6.0, 1.0 / 6.0, 2.0 / 3.0)
            records += records2 + records3
        # Nothing has been committed, including integrals, if any stage failed.
        for name, candidate in candidates.items():
            _validate_state(self.segments[name].config, candidate)
        results = {
            name: segment._result(before[name], candidates[name], dt_s, stage_groups[name], weights)
            for name, segment in self.segments.items()
        }
        external = math.fsum(
            results[name].left_volume_m3 if side == "left" else -results[name].right_volume_m3
            for name, side in self.boundaries
        )
        volume_before = math.fsum(result.volume_before_m3 for result in results.values())
        volume_after = math.fsum(result.volume_after_m3 for result in results.values())
        residual = math.fsum((volume_after, -volume_before, -external))
        for name, result in results.items():
            self.segments[name]._commit(result)
        self._external_integral += external
        return NetworkStepResult(results, records, external, volume_before, volume_after, residual)
