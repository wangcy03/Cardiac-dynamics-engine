"""Uniform elastic-tube equations in SI units, independent of the 0D engine."""
from dataclasses import dataclass
import math
from typing import Literal

Side = Literal["left", "right"]
Scheme = Literal["rusanov", "muscl_ssprk2"]


class ArterialError(ValueError):
    """An explicitly rejected configuration, boundary or numerical step."""


class NonPhysicalState(ArterialError):
    """A state has nonpositive area or a nonfinite value; no clipping is applied."""


class BoundaryError(ArterialError):
    """A boundary cannot satisfy the declared subcritical characteristic model."""


class CFLViolation(ArterialError):
    def __init__(self, requested_dt_s: float, max_dt_s: float) -> None:
        self.requested_dt_s = requested_dt_s
        self.max_dt_s = max_dt_s
        super().__init__(f"dt={requested_dt_s:.12g} s exceeds limit {max_dt_s:.12g} s")


def positive_finite(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise NonPhysicalState(f"{name} must be positive and finite, got {value!r}")


@dataclass(frozen=True)
class TubeLaw:
    reference_area_m2: float
    beta_pa: float
    density_kg_m3: float = 1060.0
    reference_pressure_pa: float = 0.0

    def __post_init__(self) -> None:
        positive_finite(self.reference_area_m2, "reference_area_m2")
        positive_finite(self.beta_pa, "beta_pa")
        positive_finite(self.density_kg_m3, "density_kg_m3")
        if not math.isfinite(self.reference_pressure_pa):
            raise NonPhysicalState("reference_pressure_pa must be finite")

    def pressure_pa(self, area_m2: float) -> float:
        positive_finite(area_m2, "area_m2")
        return self.reference_pressure_pa + self.beta_pa * (
            math.sqrt(area_m2 / self.reference_area_m2) - 1.0
        )

    def area_from_pressure_pa(self, pressure_pa: float) -> float:
        if not math.isfinite(pressure_pa):
            raise NonPhysicalState("pressure_pa must be finite")
        stretch = 1.0 + (pressure_pa - self.reference_pressure_pa) / self.beta_pa
        positive_finite(stretch, "pressure-derived wall stretch")
        area = self.reference_area_m2 * stretch * stretch
        positive_finite(area, "pressure-derived area")
        return area

    def wave_speed_m_s(self, area_m2: float) -> float:
        positive_finite(area_m2, "area_m2")
        return math.sqrt(
            self.beta_pa / (2.0 * self.density_kg_m3)
            * math.sqrt(area_m2 / self.reference_area_m2)
        )

    def potential_flux_m4_s2(self, area_m2: float) -> float:
        positive_finite(area_m2, "area_m2")
        return (
            self.beta_pa * area_m2 * math.sqrt(area_m2 / self.reference_area_m2)
            / (3.0 * self.density_kg_m3)
        )


@dataclass(frozen=True)
class SegmentConfig:
    length_m: float
    cells: int
    law: TubeLaw
    kinematic_viscosity_m2_s: float = 0.0
    cfl: float = 0.4

    def __post_init__(self) -> None:
        positive_finite(self.length_m, "length_m")
        if isinstance(self.cells, bool) or not isinstance(self.cells, int) or self.cells < 2:
            raise ArterialError("cells must be an integer >= 2")
        if not math.isfinite(self.kinematic_viscosity_m2_s) or (
            self.kinematic_viscosity_m2_s < 0.0
        ):
            raise ArterialError("kinematic_viscosity_m2_s must be finite and nonnegative")
        if not math.isfinite(self.cfl) or not 0.0 < self.cfl <= 0.5:
            raise ArterialError("cfl must be in (0, 0.5] for the declared explicit schemes")

    @property
    def dx_m(self) -> float:
        return self.length_m / self.cells


@dataclass(frozen=True)
class State:
    """Cell averages; floating-point seconds belong only to this standalone SI solver."""

    area_m2: tuple[float, ...]
    flow_m3_s: tuple[float, ...]
    time_s: float = 0.0


@dataclass(frozen=True)
class FaceState:
    area_m2: float
    flow_m3_s: float


@dataclass(frozen=True)
class Flux:
    area_flux_m3_s: float
    momentum_flux_m4_s2: float


def validate_face(face: FaceState) -> None:
    positive_finite(face.area_m2, "area_m2")
    if not math.isfinite(face.flow_m3_s):
        raise NonPhysicalState("flow_m3_s must be finite")


def characteristic_speeds_m_s(law: TubeLaw, face: FaceState) -> tuple[float, float]:
    validate_face(face)
    velocity = face.flow_m3_s / face.area_m2
    speed = law.wave_speed_m_s(face.area_m2)
    return velocity - speed, velocity + speed


def require_subcritical(law: TubeLaw, face: FaceState) -> None:
    slow, fast = characteristic_speeds_m_s(law, face)
    if not slow < 0.0 < fast:
        raise BoundaryError(
            f"one-incoming-characteristic boundary requires u-c<0<u+c, got {slow}, {fast}"
        )


def physical_flux(law: TubeLaw, face: FaceState) -> Flux:
    validate_face(face)
    momentum = (
        face.flow_m3_s * face.flow_m3_s / face.area_m2
        + law.potential_flux_m4_s2(face.area_m2)
    )
    if not math.isfinite(momentum):
        raise NonPhysicalState("momentum flux is nonfinite")
    return Flux(face.flow_m3_s, momentum)


def rusanov_flux(law: TubeLaw, left: FaceState, right: FaceState) -> Flux:
    fl = physical_flux(law, left)
    fr = physical_flux(law, right)
    speeds = characteristic_speeds_m_s(law, left) + characteristic_speeds_m_s(law, right)
    maximum = max(abs(speed) for speed in speeds)
    return Flux(
        0.5 * (fl.area_flux_m3_s + fr.area_flux_m3_s)
        - 0.5 * maximum * (right.area_m2 - left.area_m2),
        0.5 * (fl.momentum_flux_m4_s2 + fr.momentum_flux_m4_s2)
        - 0.5 * maximum * (right.flow_m3_s - left.flow_m3_s),
    )
