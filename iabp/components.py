"""Analytically integrated passive components, with explicit engineering units.

Time: s; pressure: mmHg; volume: mL; flow: mL/s.
Resistance: mmHg*s/mL; inertance: mmHg*s^2/mL.
No pressure/volume clipping is used to conceal numerical failures.
"""
from math import exp, expm1, isfinite


def positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def relax(value: float, target: float, tau_s: float, dt_s: float) -> float:
    """Exact solution of dy/dt=(target-y)/tau for a frozen target."""
    positive("tau_s", tau_s)
    if not isfinite(dt_s) or dt_s < 0:
        raise ValueError("dt_s must be finite and nonnegative")
    return target + (value - target) * exp(-dt_s / tau_s)


def inertial_step(q: float, dp: float, r: float, inertance: float,
                  dt_s: float) -> tuple[float, float]:
    """Return endpoint flow AND integrated volume for L*q'=dp-R*q.

    This frozen-coefficient solve is exact. Coupling varying pressures requires
    the predictor/corrector in model.py; component exactness is not whole-system exactness.
    """
    positive("r", r)
    positive("inertance", inertance)
    if not isfinite(dt_s) or dt_s < 0:
        raise ValueError("dt_s must be finite and nonnegative")
    if not isfinite(q) or not isfinite(dp):
        raise ValueError("q and dp must be finite")
    a = -expm1(-r * dt_s / inertance)
    qinf = dp / r
    return q + (qinf - q) * a, qinf * dt_s + (q - qinf) * (inertance / r) * a


def gate_step(z: float, dp: float, dt_s: float,
              k_open: float = 7.0, k_close: float = 12.0) -> float:
    """Finite valve opening, z in [0,1], exact at frozen dp.

    z'=ko*max(dp,0)*(1-z)-kc*max(-dp,0)*z.
    Coefficients are uncalibrated engineering choices, not imported clinical values.
    """
    if not 0 <= z <= 1 or not isfinite(dp) or not isfinite(dt_s) or dt_s < 0:
        raise ValueError("invalid gate state/pressure/time")
    positive("k_open", k_open)
    positive("k_close", k_close)
    a, b = k_open * max(dp, 0.0), k_close * max(-dp, 0.0)
    return z if a + b == 0 else relax(z, a / (a + b), 1 / (a + b), dt_s)


def valve_resistance(z: float, r_open: float, r_closed: float = 20.0) -> float:
    """Smooth positive dissipative surrogate; finite closed leakage is deliberate."""
    if not 0 <= z <= 1:
        raise ValueError("valve opening outside [0,1]")
    positive("r_open", r_open)
    if not isfinite(r_closed) or r_closed < r_open:
        raise ValueError("r_closed must be finite and >= r_open")
    return r_open + (r_closed - r_open) * (1 - z) ** 4
