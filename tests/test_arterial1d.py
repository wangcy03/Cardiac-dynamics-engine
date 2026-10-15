"""Behavioral checks for the standalone propagator, including rejection atomicity."""
import math

import pytest

from iabp.arterial1d import (
    ArterialError, BoundaryError, CFLViolation, ClosedBoundary, FaceState,
    FlowBoundary, Junction, Network, NonPhysicalState, NonReflectingBoundary,
    PressureBoundary, ResistanceBoundary, Segment, SegmentConfig, State, TubeLaw,
    characteristic_speeds_m_s, physical_flux, rusanov_flux,
)


def law(area: float = 3e-4) -> TubeLaw:
    return TubeLaw(area, 53000.0)


def segment(scheme: str = "rusanov", viscosity: float = 0.0) -> Segment:
    return Segment(SegmentConfig(1.0, 20, law(), viscosity), scheme=scheme)


def test_tube_law_inverts_pressure_and_matches_differential_wave_speed() -> None:
    tube = law()
    for pressure in (-20000.0, 0.0, 20.0, 13000.0):
        area = tube.area_from_pressure_pa(pressure)
        assert tube.pressure_pa(area) == pytest.approx(pressure, abs=2e-11)
        delta = area * 1e-5
        derivative = (tube.pressure_pa(area + delta) - tube.pressure_pa(area - delta)) / (2 * delta)
        assert tube.wave_speed_m_s(area) ** 2 == pytest.approx(
            area * derivative / tube.density_kg_m3, rel=1e-9
        )
    assert characteristic_speeds_m_s(tube, FaceState(3e-4, 0.0)) == (-5.0, 5.0)


@pytest.mark.parametrize("area", [0.0, -1e-4, math.inf, math.nan])
def test_invalid_area_is_rejected_without_clipping(area: float) -> None:
    with pytest.raises(NonPhysicalState):
        law().pressure_pa(area)
    with pytest.raises(NonPhysicalState):
        Segment(SegmentConfig(1.0, 2, law()), State((3e-4, area), (0.0, 0.0)))


@pytest.mark.parametrize("scheme", ["rusanov", "muscl_ssprk2"])
def test_stationary_tube_remains_stationary(scheme: str) -> None:
    tube = segment(scheme)
    before = tube.state
    for _ in range(4):
        result = tube.step(0.9 * tube.max_stable_dt_s(), ClosedBoundary(), ClosedBoundary())
        assert result.volume_residual_m3 == 0.0
        assert result.left_volume_m3 == result.right_volume_m3 == 0.0
    assert tube.state.area_m2 == before.area_m2
    assert tube.state.flow_m3_s == before.flow_m3_s
    assert tube.ledger.residual_m3 == 0.0


def test_rusanov_consistency_and_one_step_mass_momentum_ledger() -> None:
    tube_law = law()
    face = FaceState(3.01e-4, 1e-6)
    assert rusanov_flux(tube_law, face, face) == physical_flux(tube_law, face)
    config = SegmentConfig(1.0, 20, tube_law, 3e-6)
    state = State(
        tuple(3e-4 * (1 + 0.001 * math.sin(i * 0.2)) for i in range(20)),
        tuple(1e-6 * math.cos(i * 0.2) for i in range(20)),
    )
    tube = Segment(config, state, "muscl_ssprk2")
    dt = 0.8 * tube.max_stable_dt_s()
    result = tube.step(dt, PressureBoundary(12.0), ResistanceBoundary(1060 * 5 / 3e-4))
    assert len(result.face_fluxes) == config.cells + 1
    assert abs(result.volume_residual_m3) < 2e-19
    assert result.left_volume_m3 == dt * result.face_fluxes[0].area_flux_m3_s
    assert result.right_volume_m3 == dt * result.face_fluxes[-1].area_flux_m3_s
    actual_change = config.dx_m * math.fsum(
        new - old for old, new in zip(state.flow_m3_s, result.state.flow_m3_s, strict=True)
    )
    expected_change = dt * (
        result.face_fluxes[0].momentum_flux_m4_s2 - result.face_fluxes[-1].momentum_flux_m4_s2
    ) + result.momentum_source_integral_m4_s
    assert actual_change == pytest.approx(expected_change, abs=1e-20)
    assert abs(tube.ledger.residual_m3) < 2e-19


def test_declared_poiseuille_source_dissipates_uniform_flow() -> None:
    config = SegmentConfig(1.0, 20, law(), 3e-6)
    q0 = 1e-6
    tube = Segment(config, State((3e-4,) * 20, (q0,) * 20))
    dt = 0.8 * tube.max_stable_dt_s()
    result = tube.step(dt, FlowBoundary(q0), FlowBoundary(q0))
    expected = q0 * (1.0 - dt * 8.0 * math.pi * 3e-6 / 3e-4)
    assert result.state.flow_m3_s == pytest.approx((expected,) * 20, abs=1e-17)
    assert result.state.area_m2 == pytest.approx((3e-4,) * 20, abs=1e-18)
    assert result.momentum_source_integral_m4_s < 0.0


def test_source_step_limit_is_exposed_and_enforced() -> None:
    tube = segment(viscosity=100.0)
    source_limit = 3e-4 / (8.0 * math.pi * 100.0)
    assert tube.max_stable_dt_s() == source_limit
    with pytest.raises(CFLViolation):
        tube.step(1.1 * source_limit, ClosedBoundary(), ClosedBoundary())


def test_cfl_rejection_leaves_state_and_integrals_unchanged() -> None:
    tube = segment()
    before, ledger = tube.state, tube.ledger
    with pytest.raises(CFLViolation) as failure:
        tube.step(1.01 * tube.max_stable_dt_s(), ClosedBoundary(), ClosedBoundary())
    assert failure.value.max_dt_s == tube.max_stable_dt_s()
    assert tube.state is before
    assert tube.ledger == ledger


def test_second_rk_stage_failure_is_atomic_for_whole_network() -> None:
    first, second = segment("muscl_ssprk2"), segment("muscl_ssprk2")
    network = Network(
        {"first": first, "second": second},
        {("first", "left"): PressureBoundary(lambda t: 0.0 if t == 0.0 else math.nan),
         ("first", "right"): ClosedBoundary(),
         ("second", "left"): PressureBoundary(20.0),
         ("second", "right"): ClosedBoundary()},
    )
    states = (first.state, second.state)
    ledgers = (first.ledger, second.ledger, network.ledger)
    with pytest.raises(BoundaryError, match="finite"):
        network.step(0.8 * network.max_stable_dt_s())
    assert (first.state, second.state) == states
    assert (first.ledger, second.ledger, network.ledger) == ledgers


def test_cfl_includes_injected_boundary_state_and_rk_second_stage() -> None:
    tube = segment("muscl_ssprk2")
    before = tube.state
    # The initial state permits this dt; the higher-pressure boundary does not.
    with pytest.raises(CFLViolation):
        tube.step(0.99 * tube.max_stable_dt_s(), PressureBoundary(5000.0), ClosedBoundary())
    assert tube.state is before
    with pytest.raises(CFLViolation):
        tube.step(
            0.99 * tube.max_stable_dt_s(),
            PressureBoundary(lambda t: 0.0 if t == 0.0 else 5000.0), ClosedBoundary(),
        )
    assert tube.state is before


def test_boundary_characteristic_count_and_unphysical_pressure_fail_explicitly() -> None:
    config = SegmentConfig(1.0, 2, law())
    tube = Segment(config, State((3e-4,) * 2, (3e-4 * 6.0,) * 2))
    with pytest.raises(BoundaryError, match="characteristic"):
        tube.step(0.001, NonReflectingBoundary(), NonReflectingBoundary())
    tube = segment()
    with pytest.raises(NonPhysicalState):
        tube.step(0.001, PressureBoundary(-53000.0), ClosedBoundary())
    with pytest.raises(BoundaryError, match="no subcritical"):
        tube.step(0.001, FlowBoundary(10.0), ClosedBoundary())


def test_nonpositive_high_order_reconstruction_is_rejected_without_state_change() -> None:
    tube = Segment(
        SegmentConfig(1.0, 3, law()),
        State((1e-6, 1e-4, 2e-4), (0.0,) * 3), "muscl_ssprk2",
    )
    before, ledger = tube.state, tube.ledger
    with pytest.raises(NonPhysicalState):
        tube.step(0.5 * tube.max_stable_dt_s(), NonReflectingBoundary(), ClosedBoundary())
    assert tube.state is before
    assert tube.ledger == ledger


def test_resistance_boundary_satisfies_pressure_flow_and_outgoing_characteristic() -> None:
    tube_law = law()
    area = tube_law.area_from_pressure_pa(20.0)
    interior = FaceState(area, area * 0.01)
    resistance = 2.0 * 1060.0 * 5.0 / 3e-4
    face = ResistanceBoundary(resistance).evaluate(
        law=tube_law, interior=interior, side="right", time_s=0.0
    )
    assert tube_law.pressure_pa(face.area_m2) == pytest.approx(
        resistance * face.flow_m3_s, abs=2e-10
    )
    assert face.flow_m3_s / face.area_m2 + 4 * tube_law.wave_speed_m_s(face.area_m2) == (
        interior.flow_m3_s / interior.area_m2 + 4 * tube_law.wave_speed_m_s(interior.area_m2)
    )


@pytest.mark.parametrize("scheme", ["rusanov", "muscl_ssprk2"])
def test_junction_uses_one_common_pressure_and_conservative_physical_flux(scheme: str) -> None:
    parent_law, child_law = law(), law(1.5e-4)
    parent = Segment(
        SegmentConfig(1.0, 20, parent_law),
        State((parent_law.area_from_pressure_pa(20.0),) * 20, (0.0,) * 20), scheme=scheme,
    )
    children = [Segment(SegmentConfig(1.0, 20, child_law), scheme=scheme) for _ in range(2)]
    network = Network(
        {"parent": parent, "c1": children[0], "c2": children[1]},
        {("parent", "left"): ClosedBoundary(),
         ("c1", "right"): NonReflectingBoundary(),
         ("c2", "right"): NonReflectingBoundary()},
        (Junction("parent", ("c1", "c2")),),
    )
    result = network.step(0.8 * network.max_stable_dt_s())
    pf = result.segments["parent"].face_fluxes[-1]
    c1f, c2f = (result.segments[name].face_fluxes[0] for name in ("c1", "c2"))
    assert pf.area_flux_m3_s == c1f.area_flux_m3_s + c2f.area_flux_m3_s
    assert children[0].state == children[1].state
    assert abs(result.volume_residual_m3) < 4e-19
    for record in result.junctions:
        assert record.parent_flow_m3_s == sum(record.child_flows_m3_s)
        assert record.continuity_residual_m3_s == 0.0
        assert abs(record.parent_characteristic_residual_m_s) < 1e-12
        assert 0.0 < record.pressure_pa < 20.0
    assert abs(network.ledger.residual_m3) < 4e-19


def test_pressure_sampling_uses_exported_cell_pressures_without_time_shift() -> None:
    tube_law = law()
    tube = Segment(
        SegmentConfig(1.0, 2, tube_law),
        State((tube_law.area_from_pressure_pa(10.0), tube_law.area_from_pressure_pa(20.0)), (0., 0.)),
    )
    assert tube.coordinates_m() == (0.25, 0.75)
    assert tube.sample_pressure_pa(0.5) == pytest.approx(15.0, abs=2e-11)
    assert tube.sample_pressure_pa(0.0) == tube.pressure_pa()[0]
    with pytest.raises(ArterialError):
        tube.sample_pressure_pa(-1e-3)


def test_network_rejects_missing_or_multiply_assigned_ends() -> None:
    tube = segment()
    with pytest.raises(ArterialError, match="every"):
        Network({"a": tube}, {("a", "left"): ClosedBoundary()})
    with pytest.raises(ArterialError, match="multiple"):
        Network({"a": tube, "b": tube}, {})


def test_junction_without_common_subcritical_pressure_fails_atomically() -> None:
    tube_law = law()
    parent = Segment(SegmentConfig(1.0, 2, tube_law), State((3e-2,) * 2, (0., 0.)))
    child = Segment(SegmentConfig(1.0, 2, tube_law), State((3e-7,) * 2, (0., 0.)))
    network = Network(
        {"p": parent, "c": child},
        {("p", "left"): ClosedBoundary(), ("c", "right"): ClosedBoundary()},
        (Junction("p", ("c",)),),
    )
    before = parent.state, child.state, network.ledger
    with pytest.raises(BoundaryError, match="no common"):
        network.step(0.5 * network.max_stable_dt_s())
    assert (parent.state, child.state, network.ledger) == before


def test_network_detects_segment_advanced_independently_after_construction() -> None:
    parent, child = segment(), segment()
    network = Network(
        {"p": parent, "c": child},
        {("p", "left"): ClosedBoundary(), ("c", "right"): ClosedBoundary()},
        (Junction("p", ("c",)),),
    )
    dt = 0.5 * network.max_stable_dt_s()
    parent.step(dt, ClosedBoundary(), ClosedBoundary())
    before = parent.state, child.state, parent.ledger, child.ledger, network.ledger
    with pytest.raises(ArterialError, match="same time_s"):
        network.step(dt)
    assert (parent.state, child.state, parent.ledger, child.ledger, network.ledger) == before

