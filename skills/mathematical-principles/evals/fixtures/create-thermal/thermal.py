"""Lumped thermal RC model; no experiment or numerical run is supplied."""

THERMAL_RESISTANCE_K_W = 2.0
HEAT_CAPACITY_J_K = 10.0
AMBIENT_K = 293.15
INPUT_POWER_W = 5.0


def temperature_rate(temperature_k: float, power_w: float) -> float:
    """Return dT/dt in K/s; outward conduction is positive for T > ambient."""
    conduction_w = (temperature_k - AMBIENT_K) / THERMAL_RESISTANCE_K_W
    return (power_w - conduction_w) / HEAT_CAPACITY_J_K
