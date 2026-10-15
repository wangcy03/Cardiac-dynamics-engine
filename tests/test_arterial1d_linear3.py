"""The unlimited third-order experiment is restricted to smooth small waves."""
import math

import pytest

from iabp.arterial1d import (
    ArterialError, BoundaryError, ClosedBoundary, FlowBoundary, Network,
    NonReflectingBoundary, PressureBoundary, Segment, SegmentConfig, State, TubeLaw,
)
from iabp.arterial1d.solver import _traces


def test_linear3_reconstructs_cell_average_quadratics_including_both_endpoints() -> None:
    cells, length = 8, 1.0
    dx = length / cells
    centers = [(i + 0.5) * dx for i in range(cells)]
    state = State(
        tuple(3e-4 + 1e-6 * (x * x + dx * dx / 12.0) for x in centers),
        tuple(1e-7 * (x * x + dx * dx / 12.0 + 0.3 * x) for x in centers),
    )
    left, right = _traces(state, "linear3_ssprk3")
    for i in range(cells):
        for face, x in ((left[i], i * dx), (right[i], (i + 1) * dx)):
            assert face.area_m2 == pytest.approx(3e-4 + 1e-6 * x * x, abs=1e-19)
            assert face.flow_m3_s == pytest.approx(1e-7 * (x * x + 0.3 * x), abs=1e-22)


def test_linear3_preserves_stationary_reference_and_rejects_too_few_cells() -> None:
    law = TubeLaw(3e-4, 53000.0)
    with pytest.raises(ArterialError, match="at least 3"):
        Segment(SegmentConfig(1.0, 2, law), scheme="linear3_ssprk3")
    tube = Segment(SegmentConfig(1.0, 3, law), scheme="linear3_ssprk3")
    for _ in range(4):
        result = tube.step(0.8 * tube.max_stable_dt_s(), ClosedBoundary(), ClosedBoundary())
        assert result.state.area_m2 == (3e-4,) * 3
        assert result.state.flow_m3_s == (0.0,) * 3
        assert result.volume_residual_m3 == 0.0
    assert tube.ledger.residual_m3 == 0.0


def test_linear3_uses_physical_stage_times_and_true_weighted_flux_source_ledger() -> None:
    dt = 4e-4
    times: list[float] = []

    def prescribed_flow(time_s: float) -> float:
        times.append(time_s)
        return 1e-6 * (1.0 + time_s / dt) ** 2

    config = SegmentConfig(1.0, 10, TubeLaw(3e-4, 53000.0), 1e-3)
    initial = State((3e-4,) * 10, (1e-6,) * 10)
    tube = Segment(config, initial, "linear3_ssprk3")
    result = tube.step(dt, FlowBoundary(prescribed_flow), ClosedBoundary())
    assert times == [0.0, dt, 0.5 * dt]
    # Simpson weights are exact for this quadratic boundary flow signal.
    exact_left_volume = dt * 1e-6 * (1.0 + 1.0 + 1.0 / 3.0)
    assert result.left_volume_m3 == pytest.approx(exact_left_volume, abs=3e-25)
    assert result.right_volume_m3 == 0.0
    assert abs(result.volume_residual_m3) < 2e-19
    actual_momentum_change = config.dx_m * math.fsum(
        end - start for start, end in zip(initial.flow_m3_s, result.state.flow_m3_s, strict=True)
    )
    from_reported_flux_and_source = dt * (
        result.face_fluxes[0].momentum_flux_m4_s2 - result.face_fluxes[-1].momentum_flux_m4_s2
    ) + result.momentum_source_integral_m4_s
    assert actual_momentum_change == pytest.approx(from_reported_flux_and_source, abs=2e-20)


def test_linear3_third_stage_failure_cannot_commit_any_segment_or_ledger() -> None:
    config = SegmentConfig(1.0, 10, TubeLaw(3e-4, 53000.0))
    first, second = (Segment(config, scheme="linear3_ssprk3") for _ in range(2))
    dt = 0.8 * first.max_stable_dt_s()
    times: list[float] = []

    def fail_only_at_half_step(time_s: float) -> float:
        times.append(time_s)
        return math.nan if time_s == 0.5 * dt else 0.0

    network = Network(
        {"a": first, "b": second},
        {("a", "left"): PressureBoundary(fail_only_at_half_step),
         ("a", "right"): ClosedBoundary(),
         ("b", "left"): FlowBoundary(1e-6), ("b", "right"): ClosedBoundary()},
    )
    before = first.state, second.state, first.ledger, second.ledger, network.ledger
    with pytest.raises(BoundaryError, match="finite"):
        network.step(dt)
    assert times == [0.0, dt, 0.5 * dt]
    assert (first.state, second.state, first.ledger, second.ledger, network.ledger) == before


_GAUSS = (
    (-0.9061798459386640, 0.2369268850561891),
    (-0.5384693101056831, 0.4786286704993665),
    (0.0, 0.5688888888888889),
    (0.5384693101056831, 0.4786286704993665),
    (0.9061798459386640, 0.2369268850561891),
)


def _simple_wave_state(cells: int, time_s: float) -> State:
    """Independent inviscid simple-wave characteristic solution, integrated per cell.

    w-=u-4c=-20 is constant, so u_t+(5+1.25u)u_x=0. The
    characteristic foot is found by a rapidly contractive fixed point; no shocks
    occur in the short, smooth test window.
    """
    areas, flows = [], []
    for i in range(cells):
        samples_a, samples_q = [], []
        for node, weight in _GAUSS:
            x = (i + 0.5 + 0.5 * node) / cells
            foot = x - 5.0 * time_s
            for _ in range(12):
                velocity = 0.002 * math.exp(-((foot - 0.35) / 0.07) ** 2)
                foot = x - (5.0 + 1.25 * velocity) * time_s
            velocity = 0.002 * math.exp(-((foot - 0.35) / 0.07) ** 2)
            area = 3e-4 * (1.0 + velocity / 20.0) ** 4
            samples_a.append(0.5 * weight * area)
            samples_q.append(0.5 * weight * area * velocity)
        areas.append(math.fsum(samples_a))
        flows.append(math.fsum(samples_q))
    return State(tuple(areas), tuple(flows), time_s)


def test_linear3_has_third_order_convergence_for_a_smooth_nonlinear_simple_wave() -> None:
    errors = []
    end_s = 0.025
    for cells in (40, 80, 160):
        tube = Segment(
            SegmentConfig(1.0, cells, TubeLaw(3e-4, 53000.0)),
            _simple_wave_state(cells, 0.0), "linear3_ssprk3",
        )
        boundary = NonReflectingBoundary()
        while tube.state.time_s < end_s:
            dt = min(0.8 * tube.max_stable_dt_s(), end_s - tube.state.time_s)
            tube.step(dt, boundary, boundary)
        exact = _simple_wave_state(cells, end_s)
        errors.append(math.fsum(
            abs(actual - expected) for actual, expected in zip(
                tube.state.flow_m3_s, exact.flow_m3_s, strict=True
            )
        ) / cells)
    orders = [math.log(a / b, 2) for a, b in zip(errors, errors[1:])]
    assert min(orders) > 2.6, (errors, orders)
