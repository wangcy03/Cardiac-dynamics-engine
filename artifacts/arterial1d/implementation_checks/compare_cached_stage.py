"""Exact equivalence against the frozen original stage; no large benchmark.

From the repository root run:
python -m artifacts.arterial1d.implementation_checks.compare_cached_stage
"""
import ast
import hashlib
import json
import math
from pathlib import Path

from iabp.arterial1d import (
    BoundaryError, CFLViolation, ClosedBoundary, FlowBoundary, Junction, Network,
    NonPhysicalState, NonReflectingBoundary, PressureBoundary, ResistanceBoundary,
    Segment, SegmentConfig, State, TubeLaw, FaceState, characteristic_speeds_m_s,
    physical_flux, rusanov_flux,
)
from iabp.arterial1d.solver import _Stage


repo_root = Path(__file__).resolve().parents[3]
snapshot = repo_root / "artifacts/arterial1d/history/pre_linear3/iabp/arterial1d/solver.py"
snapshot_bytes = snapshot.read_bytes()
parsed = ast.parse(snapshot_bytes.decode("utf-8"))
segment_class = next(node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == "Segment")
old_stage = next(node for node in segment_class.body if isinstance(node, ast.FunctionDef) and node.name == "_stage")
namespace = dict(globals())
exec(compile(ast.Module(body=[old_stage], type_ignores=[]), str(snapshot), "exec"), namespace)
ReferenceSegment = type("ReferenceSegment", (Segment,), {"_stage": namespace["_stage"]})


def make(kind, scheme, viscosity=0.0, area=3e-4, perturb=False):
    law = TubeLaw(area, 53000.0)
    config = SegmentConfig(1.0, 40, law, viscosity)
    if perturb:
        state = State(
            tuple(law.area_from_pressure_pa(10 * math.sin(i * 0.1) ** 2) for i in range(40)),
            tuple(1e-6 * math.cos(i * 0.1) for i in range(40)),
        )
        return kind(config, state, scheme)
    return kind(config, scheme=scheme)


def compare_steps(scheme, viscosity, left, right):
    original = make(ReferenceSegment, scheme, viscosity, perturb=True)
    cached = make(Segment, scheme, viscosity, perturb=True)
    for _ in range(40):
        dt = 0.8 * original.max_stable_dt_s()
        assert original.step(dt, left, right) == cached.step(dt, left, right)
        assert original.ledger == cached.ledger


def make_network(kind, scheme):
    segments = {
        "parent": make(kind, scheme, 3e-6),
        "left": make(kind, scheme, 3e-6, 1.5e-4),
        "right": make(kind, scheme, 3e-6, 1.5e-4),
    }
    return Network(
        segments,
        {("parent", "left"): PressureBoundary(lambda t: 20 * math.sin(100 * t) ** 2),
         ("left", "right"): ResistanceBoundary(1060 * 5 / 1.5e-4),
         ("right", "right"): NonReflectingBoundary()},
        (Junction("parent", ("left", "right")),),
    )


def failure(kind, scheme, scenario):
    tube = make(kind, scheme)
    left, right = ClosedBoundary(), ClosedBoundary()
    dt = 1.01 * tube.max_stable_dt_s()
    if scenario == "boundary_cfl":
        left = PressureBoundary(5000.0)
        dt = 0.99 * tube.max_stable_dt_s()
    elif scenario == "stage2":
        left = PressureBoundary(lambda t: 0.0 if t == 0.0 else math.nan)
        dt = 0.8 * tube.max_stable_dt_s()
    elif scenario == "reconstruction":
        tube = kind(
            SegmentConfig(1.0, 3, TubeLaw(3e-4, 53000.0)),
            State((1e-6, 1e-4, 2e-4), (0.0,) * 3), "muscl_ssprk2",
        )
        dt = 0.8 * tube.max_stable_dt_s()
    before = tube.state, tube.ledger
    try:
        tube.step(dt, left, right)
    except (CFLViolation, BoundaryError, NonPhysicalState) as error:
        assert (tube.state, tube.ledger) == before
        return type(error).__name__, str(error)
    raise AssertionError("failure scenario did not fail")


if __name__ == "__main__":
    cases = []
    for scheme in ("rusanov", "muscl_ssprk2"):
        for viscosity in (0.0, 3e-6):
            for name, left, right in (
                ("pressure_resistance", PressureBoundary(12.0), ResistanceBoundary(2 * 1060 * 5 / 3e-4)),
                ("flow_absorbing", FlowBoundary(1e-6), NonReflectingBoundary()),
                ("closed", ClosedBoundary(), ClosedBoundary()),
            ):
                compare_steps(scheme, viscosity, left, right)
                cases.append({"scheme": scheme, "viscosity_m2_s": viscosity, "boundaries": name,
                              "steps": 40, "exact_step_and_ledger_equality": True})
        original, cached = make_network(ReferenceSegment, scheme), make_network(Segment, scheme)
        for _ in range(40):
            dt = 0.8 * original.max_stable_dt_s()
            assert original.step(dt) == cached.step(dt)
            assert original.ledger == cached.ledger
            assert {name: value.ledger for name, value in original.segments.items()} == {
                name: value.ledger for name, value in cached.segments.items()
            }
        cases.append({"scheme": scheme, "case": "viscous_branch", "steps": 40,
                      "exact_step_and_ledger_equality": True})
        for scenario in ("initial_cfl", "boundary_cfl", "reconstruction"):
            assert failure(ReferenceSegment, scheme, scenario) == failure(Segment, scheme, scenario)
        if scheme == "muscl_ssprk2":
            assert failure(ReferenceSegment, scheme, "stage2") == failure(Segment, scheme, "stage2")
    current_solver = repo_root / "iabp/arterial1d/solver.py"
    result = {"status": "PASS", "frozen_original_stage_reference": str(snapshot.relative_to(repo_root)),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "current_solver_sha256": hashlib.sha256(current_solver.read_bytes()).hexdigest(),
              "reference_solver_sha256": hashlib.sha256(snapshot_bytes).hexdigest(), "cases": cases,
              "failure_types_messages_and_atomicity_exact": True}
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
