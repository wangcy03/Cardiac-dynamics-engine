"""Regression checks for independently defined 1D benchmark measurements."""
from __future__ import annotations

import math
import json
import hashlib
import shutil
import copy
from pathlib import Path

import pytest

from tools.arterial1d_check import (
    ENGINEERING_THRESHOLDS,
    BOILEAU_THRESHOLDS,
    _verify_report,
    _validate_coverage,
    _run_acceptance,
    _validate_public_data_identity,
    _artifact_path,
    _verify_csv_coverage,
    crossing_time,
    load_boileau_reference,
    observed_orders,
    pressure_pulse_integral,
    pulse_pressure_pa,
    timing_and_peak_metrics,
    verify_boileau_data,
    run_boileau,
)


def test_arrival_is_missing_when_fixed_pressure_threshold_is_never_reached() -> None:
    assert crossing_time([(0.0, 0.0), (0.1, 9.0), (0.2, 0.0)], 10.0) is None
    metrics = timing_and_peak_metrics(
        [(0.0, 0.0), (0.1, 9.0), (0.2, 0.0)], expected_arrival_s=0.1
    )
    assert metrics["arrival_time_s"] is None
    assert metrics["arrival_error_ms"] is None
    assert metrics["candidate_pass"] is False


def test_unshifted_arrival_and_absolute_peak_are_measured() -> None:
    times = [index / 10000 for index in range(2201)]
    exact = [(t, pulse_pressure_pa(t - 0.1)) for t in times]
    delayed = [(t, pulse_pressure_pa(t - 0.102)) for t in times]
    assert timing_and_peak_metrics(exact, 0.16)["candidate_pass"] is True
    result = timing_and_peak_metrics(delayed, 0.16)
    assert result["arrival_error_ms"] == pytest.approx(2.0, abs=1e-9)
    assert result["candidate_pass"] is False
    assert ENGINEERING_THRESHOLDS["arrival_error_ms"] == 0.5
    assert ENGINEERING_THRESHOLDS["peak_relative_error"] == 0.01


def test_pulse_integral_has_exact_support_and_total_volume_basis() -> None:
    assert pressure_pulse_integral(0.0) == 0.0
    assert pressure_pulse_integral(0.05) == 0.0
    assert pressure_pulse_integral(0.07) == pytest.approx(0.2)
    assert pressure_pulse_integral(0.09) == pytest.approx(0.4)
    assert pressure_pulse_integral(1.0) == pytest.approx(0.4)


def test_orders_report_divergence_and_do_not_hide_nonpositive_errors() -> None:
    assert observed_orders([80, 160, 320], [0.4, 0.2, 0.1]) == pytest.approx([1.0, 1.0])
    assert observed_orders([80, 160, 320], [0.1, 0.2, 0.4]) == pytest.approx([-1.0, -1.0])
    assert observed_orders([80, 160], [0.1, 0.0]) == [None]


def test_original_boileau_data_identity_and_pressure_units() -> None:
    identity = verify_boileau_data(Path("artifacts/arterial1d/external/boileau2015"))
    assert identity["download_integrity"] == "PASS"
    assert identity["reference_table_count"] == 12
    rows = load_boileau_reference(Path("artifacts/arterial1d/external/boileau2015"))
    assert len(rows) == 1000
    assert rows[0][0] == pytest.approx(0.005)
    assert rows[-1][0] == pytest.approx(9.995)
    assert max(row[1] for row in rows) == pytest.approx(20.50066)
    assert all(math.isfinite(value) for row in rows for value in row)


def test_changed_original_data_cannot_be_reported_as_verified(tmp_path: Path) -> None:
    (tmp_path / "original.txt").write_bytes(b"abd")
    manifest = {"original_files": [{
        "path": "original.txt", "bytes": 3,
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    }]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="identity mismatch"):
        verify_boileau_data(tmp_path)


def _gate_fixture(root: Path) -> tuple[dict, dict, dict]:
    source = b"frozen source\n"
    source_hash = hashlib.sha256(source).hexdigest()
    (root / "source.py").write_bytes(source)
    identity = {"source_sha256": {"source.py": source_hash}, "source_snapshot_manifest": "snapshot.json"}
    (root / "snapshot.json").write_text(json.dumps({"source_sha256": identity["source_sha256"], "files": [{"original_path": "source.py", "path": "source.py", "sha256": source_hash}]}), encoding="utf-8")
    (root / "trace.csv").write_text("time_s,pressure_pa\n0,0\n", encoding="utf-8")
    (root / "run.log").write_text("ACTUAL_SOLVER_RUN complete\n", encoding="utf-8")
    run = {"identity": identity, "source_unchanged_during_run": True, "case": "fixture", "run_log_path": "run.log",
           "csv_artifacts": [{"path": "trace.csv", "sha256": hashlib.sha256((root / "trace.csv").read_bytes()).hexdigest()}]}
    (root / "result.json").write_text(json.dumps(run), encoding="utf-8")
    run["result_json"] = {"path": "result.json", "sha256": hashlib.sha256((root / "result.json").read_bytes()).hexdigest()}
    report = {"identity": identity, "selected_case": "fixture", "mode": "ACTUAL_SOLVER_RUN", "thresholds_declared_before_runs": ENGINEERING_THRESHOLDS,
              "boileau_thresholds_declared_before_runs": BOILEAU_THRESHOLDS,
              "run_log": {"path": "run.log", "sha256": hashlib.sha256((root / "run.log").read_bytes()).hexdigest()}}
    return identity, report, run


@pytest.mark.parametrize("changed_file", ["source.py", "trace.csv", "result.json", "run.log"])
def test_evidence_gate_rejects_modified_run_artifacts(tmp_path: Path, changed_file: str) -> None:
    identity, report, run = _gate_fixture(tmp_path)
    _verify_report(tmp_path, "fixture", report, [run], identity)
    with (tmp_path / changed_file).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError):
        _verify_report(tmp_path, "fixture", report, [run], identity)


def test_evidence_gate_rejects_current_source_drift(tmp_path: Path) -> None:
    identity, report, run = _gate_fixture(tmp_path)
    changed = {"source_sha256": {"source.py": "new_source"}}
    with pytest.raises(ValueError, match="source identity changed"):
        _verify_report(tmp_path, "fixture", report, [run], changed)


def test_evidence_gate_rejects_empty_current_run_set(tmp_path: Path) -> None:
    identity, report, _ = _gate_fixture(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        _verify_report(tmp_path, "fixture", report, [], identity)


def test_public_run_keeps_data_identity_separate_from_source_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import arterial1d_check

    monkeypatch.setattr(arterial1d_check, "_PROCESS_IDENTITY", None)
    target = tmp_path / "external" / "boileau2015"
    shutil.copytree(Path("artifacts/arterial1d/external/boileau2015"), target)
    # Four cells are intentionally not a numerical accuracy acceptance run. This
    # tiny actual propagation checks the artifact contract without a costly grid.
    result = run_boileau(4, "rusanov", tmp_path)
    assert result["data_identity"]["archive_sha256"] == "da31f4730aa3236e6dd3a686cc92a9bc19887807122b7b31f73c0ae695a2f86e"
    assert result["identity"]["source_sha256"]


def _coverage_fixture() -> dict:
    def rows(case: str, scheme: str, grids: list[int], key: str = "cells") -> list[dict]:
        return [{"case": case, "scheme": scheme, key: n} for n in grids]

    return {
        "linear3_matched": {"linear3_matched": rows("engineering_matched_pressure_pulse", "linear3_ssprk3", [80, 160, 320])},
        "linear3_boileau": {"linear3_boileau": rows("boileau2015_single_pulse_inviscid", "linear3_ssprk3", [640, 1280, 2560])},
        "reflections": {"reflections": [{"case": kind, "candidate_pass": True, "runs": rows(kind, "muscl_ssprk2", [80, 160, 320])} for kind in ["closed", "pressure_release", "resistance_2z0"]]},
        "junction": {"junction": {"candidate_pass": True, "runs": rows("symmetric_static_pressure_junction", "muscl_ssprk2", [40, 80, 160], "cells_per_segment")}},
    }


@pytest.mark.parametrize("mutation", ["empty_reflections", "missing_type", "duplicate_type", "missing_reflection_grid", "empty_junction", "junction_grid_order", "wrong_scheme", "wrong_run_case", "append_coarser_grid", "missing_public_grid"])
def test_declared_case_scheme_grid_matrix_is_required(mutation: str) -> None:
    reports = _coverage_fixture()
    _validate_coverage(reports)
    reflection_groups = reports["reflections"]["reflections"]
    if mutation == "empty_reflections":
        reflection_groups.clear()
    elif mutation == "missing_type":
        reflection_groups.pop()
    elif mutation == "duplicate_type":
        reflection_groups[-1] = copy.deepcopy(reflection_groups[0])
    elif mutation == "missing_reflection_grid":
        reflection_groups[0]["runs"].pop()
    elif mutation == "empty_junction":
        reports["junction"]["junction"]["runs"].clear()
    elif mutation == "junction_grid_order":
        reports["junction"]["junction"]["runs"].reverse()
    elif mutation == "wrong_scheme":
        reports["linear3_matched"]["linear3_matched"][0]["scheme"] = "rusanov"
    elif mutation == "wrong_run_case":
        reflection_groups[0]["runs"][0]["case"] = "pressure_release"
    elif mutation == "append_coarser_grid":
        runs = reports["linear3_boileau"]["linear3_boileau"]
        runs.append(copy.deepcopy(runs[0]))
    else:
        reports["linear3_boileau"]["linear3_boileau"].pop()
    with pytest.raises(ValueError):
        _validate_coverage(reports)


def test_wrapper_pass_cannot_override_failed_original_numerical_metric() -> None:
    wrapper = {"candidate_pass": True, "runs": [{"case": "closed", "pass": True,
               "measured_coefficient": 0.5, "conservation_relative_initial_volume": 0.0}]}
    assert _run_acceptance(wrapper["runs"][-1], "reflection") is False
    wrapper["runs"][-1]["measured_coefficient"] = 1.0
    wrapper["candidate_pass"] = False
    assert _run_acceptance(wrapper["runs"][-1], "reflection") is True


@pytest.mark.parametrize("field", ["archive_sha256", "manifest_sha256", "source_config_sha256", "missing_identity"])
def test_public_identity_requires_original_before_after_values(field: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import arterial1d_check

    current = {"archive_sha256": "archive", "manifest_sha256": "manifest", "source_config_sha256": "config"}
    monkeypatch.setattr(arterial1d_check, "verify_boileau_data", lambda root: current)
    run = {"data_identity": {**current, "before": copy.deepcopy(current), "after": copy.deepcopy(current), "unchanged_during_run": True,
                             "reference_archive_member": "Benchmark1_SinglePulseModel/NumData/FVM_inviscid.txt"},
           "parameters": {"source_config_sha256": "config"}}
    _validate_public_data_identity(Path("unused"), run)
    if field == "missing_identity":
        del run["data_identity"]
    else:
        run["data_identity"]["after"][field] = "changed"
    with pytest.raises(ValueError):
        _validate_public_data_identity(Path("unused"), run)


@pytest.mark.parametrize("relative", ["nested/data.txt", "nested\\data.txt"])
def test_artifact_reader_accepts_current_and_historical_path_separators(tmp_path: Path, relative: str) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "data.txt").write_bytes(b"original manifest bytes\r\n")
    assert _artifact_path(tmp_path, relative).read_bytes() == b"original manifest bytes\r\n"


@pytest.mark.parametrize("mutation", ["empty", "missing", "duplicate", "extra"])
def test_required_original_csv_set_is_complete_and_unique(mutation: str) -> None:
    run = {"case": "engineering_matched_pressure_pulse", "scheme": "linear3_ssprk3", "cells": 320,
           "csv_artifacts": [{"path": "matched_linear3_ssprk3_320_trace.csv"}, {"path": "matched_linear3_ssprk3_320_profiles.csv"}]}
    _verify_csv_coverage(run)
    items = run["csv_artifacts"]
    if mutation == "empty":
        items.clear()
    elif mutation == "missing":
        items.pop()
    elif mutation == "duplicate":
        items.append(dict(items[0]))
    else:
        items.append({"path": "extra.csv"})
    with pytest.raises(ValueError):
        _verify_csv_coverage(run)
