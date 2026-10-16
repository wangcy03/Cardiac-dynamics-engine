"""One incoming characteristic per subcritical boundary; no prescribed P-and-Q pairs."""
from dataclasses import dataclass
import math
from typing import Callable, Protocol

from .physics import (
    BoundaryError, FaceState, Side, TubeLaw, require_subcritical,
)

Signal = float | Callable[[float], float]


class Boundary(Protocol):
    def evaluate(
        self, *, law: TubeLaw, interior: FaceState, side: Side, time_s: float
    ) -> FaceState: ...


def _value(signal: Signal, time_s: float) -> float:
    value = signal(time_s) if callable(signal) else signal
    if not math.isfinite(value):
        raise BoundaryError("boundary signal must return a finite SI value")
    return value


def outgoing_invariant(law: TubeLaw, interior: FaceState, side: Side) -> float:
    require_subcritical(law, interior)
    velocity = interior.flow_m3_s / interior.area_m2
    speed = law.wave_speed_m_s(interior.area_m2)
    return velocity - 4.0 * speed if side == "left" else velocity + 4.0 * speed


def characteristic_pressure_state(
    law: TubeLaw, interior: FaceState, side: Side, pressure_pa: float
) -> FaceState:
    invariant = outgoing_invariant(law, interior, side)
    area = law.area_from_pressure_pa(pressure_pa)
    speed = law.wave_speed_m_s(area)
    velocity = invariant + 4.0 * speed if side == "left" else invariant - 4.0 * speed
    face = FaceState(area, area * velocity)
    require_subcritical(law, face)
    return face


@dataclass(frozen=True)
class PressureBoundary:
    pressure_pa: Signal

    def evaluate(
        self, *, law: TubeLaw, interior: FaceState, side: Side, time_s: float
    ) -> FaceState:
        return characteristic_pressure_state(law, interior, side, _value(self.pressure_pa, time_s))


@dataclass(frozen=True)
class FlowBoundary:
    flow_m3_s: Signal

    def evaluate(
        self, *, law: TubeLaw, interior: FaceState, side: Side, time_s: float
    ) -> FaceState:
        target = _value(self.flow_m3_s, time_s)
        invariant = outgoing_invariant(law, interior, side)
        reference_speed = law.wave_speed_m_s(law.reference_area_m2)
        magnitude = abs(invariant)
        # Within this interval the boundary remains subcritical and Q(c) is monotonic.
        low = math.nextafter(magnitude / 5.0, math.inf)
        high = math.nextafter(magnitude / 3.0, 0.0)

        def state_at(speed: float) -> FaceState:
            area = law.reference_area_m2 * (speed / reference_speed) ** 4
            velocity = invariant + 4.0 * speed if side == "left" else invariant - 4.0 * speed
            return FaceState(area, area * velocity)

        fl = state_at(low).flow_m3_s - target
        fh = state_at(high).flow_m3_s - target
        if fl * fh > 0.0:
            raise BoundaryError("prescribed flow has no subcritical characteristic solution")
        for _ in range(80):
            mid = 0.5 * (low + high)
            fm = state_at(mid).flow_m3_s - target
            if fm == 0.0 or mid == low or mid == high:
                break
            if fl * fm <= 0.0:
                high = mid
            else:
                low, fl = mid, fm
        approximate = state_at(0.5 * (low + high))
        face = FaceState(approximate.area_m2, target)
        require_subcritical(law, face)
        return face


@dataclass(frozen=True)
class ClosedBoundary:
    def evaluate(
        self, *, law: TubeLaw, interior: FaceState, side: Side, time_s: float
    ) -> FaceState:
        invariant = outgoing_invariant(law, interior, side)
        speed = abs(invariant) / 4.0
        reference_speed = law.wave_speed_m_s(law.reference_area_m2)
        return FaceState(law.reference_area_m2 * (speed / reference_speed) ** 4, 0.0)


@dataclass(frozen=True)
class NonReflectingBoundary:
    """Hold the incoming invariant at its zero-flow reference value (inviscid model)."""

    def evaluate(
        self, *, law: TubeLaw, interior: FaceState, side: Side, time_s: float
    ) -> FaceState:
        outgoing = outgoing_invariant(law, interior, side)
        reference_speed = law.wave_speed_m_s(law.reference_area_m2)
        incoming = 4.0 * reference_speed if side == "left" else -4.0 * reference_speed
        plus, minus = (incoming, outgoing) if side == "left" else (outgoing, incoming)
        speed = (plus - minus) / 8.0
        if speed <= 0.0:
            raise BoundaryError("nonreflecting characteristic state has nonpositive wave speed")
        area = law.reference_area_m2 * (speed / reference_speed) ** 4
        face = FaceState(area, area * (plus + minus) / 2.0)
        require_subcritical(law, face)
        return face


@dataclass(frozen=True)
class ResistanceBoundary:
    resistance_pa_s_m3: float
    downstream_pressure_pa: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.resistance_pa_s_m3) or self.resistance_pa_s_m3 < 0.0:
            raise BoundaryError("terminal resistance must be finite and nonnegative")
        if not math.isfinite(self.downstream_pressure_pa):
            raise BoundaryError("downstream pressure must be finite")

    def evaluate(
        self, *, law: TubeLaw, interior: FaceState, side: Side, time_s: float
    ) -> FaceState:
        if side != "right":
            raise BoundaryError("ResistanceBoundary is a right terminal boundary")
        if self.resistance_pa_s_m3 == 0.0:
            return characteristic_pressure_state(law, interior, side, self.downstream_pressure_pa)
        invariant = outgoing_invariant(law, interior, side)
        reference_speed = law.wave_speed_m_s(law.reference_area_m2)
        low = math.nextafter(invariant / 5.0, math.inf)
        high = math.nextafter(invariant / 3.0, 0.0)

        def state_and_residual(speed: float) -> tuple[FaceState, float]:
            area = law.reference_area_m2 * (speed / reference_speed) ** 4
            face = FaceState(area, area * (invariant - 4.0 * speed))
            residual = (
                law.pressure_pa(area) - self.downstream_pressure_pa
                - self.resistance_pa_s_m3 * face.flow_m3_s
            )
            return face, residual

        _, fl = state_and_residual(low)
        _, fh = state_and_residual(high)
        if fl * fh > 0.0:
            raise BoundaryError("resistance has no subcritical characteristic solution")
        for _ in range(80):
            mid = 0.5 * (low + high)
            _, fm = state_and_residual(mid)
            if fm == 0.0 or mid == low or mid == high:
                break
            if fl * fm <= 0.0:
                high = mid
            else:
                low, fl = mid, fm
        face, _ = state_and_residual(0.5 * (low + high))
        require_subcritical(law, face)
        return face
