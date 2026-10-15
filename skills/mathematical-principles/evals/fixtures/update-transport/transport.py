"""Periodic first-order upwind transport; synthetic documentation fixture."""

ADVECTION_SPEED_M_S = 2.0
CFL_MAX = 0.4


def step(values: tuple[float, ...], courant: float) -> tuple[float, ...]:
    """Take an Euler step with positive speed; reject an undeclared CFL."""
    if not 0.0 <= courant <= CFL_MAX:
        raise ValueError("CFL outside declared bound")
    return tuple(value - courant * (value - values[i - 1]) for i, value in enumerate(values))
