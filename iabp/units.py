"""The explicit unit seam between the independent SI propagator and mmHg/mL core.

The conversion uses the conventional millimetre of mercury, 133.322387415 Pa.
There is no implicit conversion or coupling to the existing 0D model.
"""
import math

PASCAL_PER_MMHG = 133.322387415
CUBIC_METRE_PER_MILLILITRE = 1e-6
MICROSECONDS_PER_SECOND = 1_000_000


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("unit conversion requires a finite value")
    return value


def pa_to_mmhg(pressure_pa: float) -> float:
    return _finite(pressure_pa) / PASCAL_PER_MMHG


def mmhg_to_pa(pressure_mmhg: float) -> float:
    return _finite(_finite(pressure_mmhg) * PASCAL_PER_MMHG)


def m3_to_ml(volume_m3: float) -> float:
    return _finite(_finite(volume_m3) / CUBIC_METRE_PER_MILLILITRE)


def ml_to_m3(volume_ml: float) -> float:
    return _finite(volume_ml) * CUBIC_METRE_PER_MILLILITRE


def m3_s_to_ml_s(flow_m3_s: float) -> float:
    return m3_to_ml(flow_m3_s)


def ml_s_to_m3_s(flow_ml_s: float) -> float:
    return ml_to_m3(flow_ml_s)


def us_to_s(time_us: int) -> float:
    if isinstance(time_us, bool) or not isinstance(time_us, int):
        raise ValueError("interface clock requires integer microseconds")
    return time_us / MICROSECONDS_PER_SECOND


def s_to_us_exact(time_s: float) -> int:
    """Reject unrepresentable times instead of silently rounding a scheduling boundary."""
    scaled = _finite(_finite(time_s) * MICROSECONDS_PER_SECOND)
    nearest = round(scaled)
    if not math.isclose(scaled, nearest, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError("time is not representable as integer microseconds")
    return nearest
