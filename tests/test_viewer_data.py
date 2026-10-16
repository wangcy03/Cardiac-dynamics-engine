"""Observer data behavior: no solver, no cosmetic values, no invented identity."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from tools.viewer_data import BundleError, build_bundle


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _csv(path: Path, columns: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


@pytest.fixture
def exported(tmp_path: Path) -> Path:
    (tmp_path / "iabp").mkdir()
    (tmp_path / "iabp/model.py").write_bytes(b"# synthetic source identity fixture, no model executed\n")
    demo = tmp_path / "demo"
    columns = ["time_us", "ecg_ii", "p_lv", "p_root", "p_descending", "q_ao", "v_lv",
               "v_balloon", "mass_error", "z_mitral"]
    rows = [
        [1000000.0, 0.12345678901234567, 10.0, 100.12345678901234, 98.0, -2.0, 70.0, 0.0, -1e-12, 8.637599892070397e-148],
        [1001000.0, -0.23456789012345678, 12.0, 99.76543210987654, 97.0, 6.0, 69.0, 1.0, 2e-12, 5e-149],
    ]
    metrics = {
        "max_mass_error_mL": 2e-12, "root_min_mmHg": rows[1][3],
        "root_max_mmHg": rows[0][3], "max_balloon_mL": 1.0,
        "net_aortic_volume_mL": 0.002, "lv_net_external_work_mmHg_mL": 11.0,
    }
    for case in ("baseline", "assisted"):
        _csv(demo / f"{case}_truth.csv", columns, rows)
        _csv(demo / f"{case}_samples.csv",
             ["channel_id", "units", "sequence_id", "value", "t_available_us", "source_time_us", "source_clock_id", "observable_quality"],
             [["AP_MONITOR", "mmHg", 19, 96.12345678901234, 1000003, "", "", "OK"],
              ["ECG_II", "mV", 20, -0.23456789012345678, 1001000, 1000999, "ECG_CLOCK", "OK"]])
        _json(demo / f"{case}_events.json", [{"name": "QRS_ONSET", "at_us": 1000123,
                                               "definition": "external electrical stimulus"}])
        _json(demo / f"{case}_commands.json", [] if case == "baseline" else [
            {"command_id": "test-i", "at_us": 1000234, "status": "accepted", "reason": ""},
        ])
    _json(demo / "provenance.json", {
        "kind": "SYNTHETIC_TEST_FIXTURE", "model_source_sha256": _sha(tmp_path / "iabp/model.py"),
        "engine_config": {"step_us": 250, "seed": 42},
        "metrics": {"baseline": metrics, "assisted": metrics},
    })
    (tmp_path / "arterial").mkdir()
    return tmp_path


def _build(root: Path) -> dict:
    return build_bundle(root, Path("demo"), Path("arterial"), "fixture-v1", "Recorded fixture")


def _run(root: Path, *, historical: bool = False) -> Path:
    source = root / "iabp/arterial1d/solver.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"# current solver bytes; never executed\n")
    digest = _sha(source)
    if historical:
        snapshot = root / "arterial/history/pre_linear3/iabp/arterial1d/solver.py"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(b"# historical source, not current\n")
        digest = _sha(snapshot)
        _json(root / "arterial/history/pre_linear3/manifest.json", {
            "schema": "arterial1d-historical-source-snapshot/v1",
            "files": [{"path": "iabp/arterial1d/solver.py", "sha256": digest}],
        })
    trace = root / "arterial/matched_fixture_4_trace.csv"
    _csv(trace, ["time_s", "pressure_pa", "reference_pa", "flow_m3_s"],
         [[0, -0.01895853103839329, 0, -1e-12], [0.001, 20.12345678901234, 20, 1e-6]])
    record = {
        "case": "engineering_fixture", "scheme": "fixture", "cells": 4,
        "candidate_pass": False, "conservation_pass": True, "arrival_time_s": None,
        "min_pressure_pa": -0.01895853103839329,
        "trace_csv": trace.name,
        "identity": {"source_sha256": {"iabp/arterial1d/solver.py": digest}},
        "csv_artifacts": [{"path": trace.name, "sha256": _sha(trace)}],
    }
    path = root / "arterial/matched_fixture_4.json"
    _json(path, record)
    return path


def test_bundle_preserves_numeric_precision_null_clocks_and_input_bytes(exported: Path) -> None:
    before = {p.relative_to(exported): _sha(p) for p in exported.rglob("*") if p.is_file()}
    bundle = _build(exported)
    assert bundle["schema"] == "cardiac-observer/v1"
    case = bundle["heart"]["cases"]["baseline"]
    assert case["rows"][0][1] == 0.12345678901234567
    assert case["rows"][0][-1] == 8.637599892070397e-148
    assert case["rows"][0][5] == -2.0
    assert case["samples"][0]["source_time_us"] is None
    assert case["samples"][0]["source_clock_id"] is None
    assert case["samples"][1]["source_time_us"] == 1000999
    assert case["samples"][1]["t_available_us"] == 1001000
    assert case["events"] == json.loads((exported / "demo/baseline_events.json").read_text())
    assert case["commands"] == []
    assert bundle["heart"]["cases"]["assisted"]["commands"][0]["status"] == "accepted"
    assert bundle["heart"]["initial_state"]["first_exported_state_equal"] is True
    assert bundle["heart"]["initial_state"]["within_demo_shared"] is None
    assert bundle["run"]["simulation_git"] is None
    assert before == {p.relative_to(exported): _sha(p) for p in exported.rglob("*") if p.is_file()}
    assert {f["path"]: f["sha256"] for f in bundle["run"]["files"]} == {
        p.as_posix(): digest for p, digest in before.items()
    }
    # JSON round trips preserve exported floating values, including tiny openings.
    assert json.loads(json.dumps(bundle, allow_nan=False))["heart"]["cases"] == bundle["heart"]["cases"]


def test_recorded_metrics_keep_full_window_and_signed_integrals(exported: Path) -> None:
    bundle = _build(exported)
    case = bundle["heart"]["cases"]["baseline"]
    assert case["metric_window_us"] == [1000000, 1001000]
    assert case["metrics"]["net_aortic_volume_mL"] == 0.002
    assert case["metrics"]["lv_net_external_work_mmHg_mL"] == 11
    assert case["metric_check"]["status"] == "CHECKED_EXPORTED_SAMPLES"
    assert bundle["heart"]["metric_definitions"]["net_aortic_volume_mL"]["window"] == "full_record"


def test_inconsistent_recorded_metric_is_rejected(exported: Path) -> None:
    path = exported / "demo/provenance.json"
    data = json.loads(path.read_text())
    data["metrics"]["baseline"]["net_aortic_volume_mL"] = 100
    _json(path, data)
    with pytest.raises(BundleError, match="metric inconsistent"):
        _build(exported)


def test_unknown_source_is_not_replaced_by_packaging_git(exported: Path) -> None:
    path = exported / "demo/provenance.json"
    data = json.loads(path.read_text())
    del data["model_source_sha256"]
    _json(path, data)
    bundle = _build(exported)
    assert bundle["heart"]["source_status"] == "NOT_RECORDED"
    assert bundle["heart"]["source_identity"] is None
    assert bundle["run"]["provenance"]["recorded_simulation_git"] is None


def test_source_mismatch_is_visible_not_pass(exported: Path) -> None:
    (exported / "iabp/model.py").write_bytes(b"# changed after the recorded export\n")
    bundle = _build(exported)
    assert bundle["heart"]["source_status"] == "SOURCE_MISMATCH"
    assert bundle["run"]["source_status"] == "SOURCE_MISMATCH"
    assert any("model.py" in warning for warning in bundle["warnings"])


def test_0d_only_historical_package_has_no_invented_1d(exported: Path) -> None:
    bundle = build_bundle(exported, Path("demo"), Path("not-recorded"), "old", "Old 0D")
    assert bundle["arterial1d"]["runs"] == []
    assert "independent_1d_not_provided" in bundle["capabilities"]
    assert bundle["heart"]["source_status"] == "PARTIAL_RECORDED_SOURCE_MATCH"


def test_1d_failures_negative_values_and_si_units_survive(exported: Path) -> None:
    _run(exported)
    run = _build(exported)["arterial1d"]["runs"][0]
    assert run["status"] == "FAIL_DECLARED_CHECKS"
    assert run["failures"] == ["candidate_pass=false"]
    assert run["summary"]["arrival_time_s"] is None
    assert run["trace"]["rows"][0][1] == -0.01895853103839329
    assert run["trace"]["units"]["pressure_pa"] == "Pa"
    assert run["trace"]["units"]["flow_m3_s"] == "m3/s"
    assert run["source_status"] == "RECORDED_SOURCE_MATCH"
    assert run["run_git"] is None


def test_historical_source_matches_snapshot_not_current_source(exported: Path) -> None:
    path = _run(exported, historical=True)
    original = json.loads(path.read_text())
    bundle = _build(exported)
    run = bundle["arterial1d"]["runs"][0]
    assert run["source_status"] == "HISTORICAL_SOURCE"
    assert run["historical"] is True
    assert run["source_identity"] == original["identity"]
    assert run["source_identity"]["source_sha256"]["iabp/arterial1d/solver.py"] != _sha(exported / "iabp/arterial1d/solver.py")
    assert run["run_git"] is None


def test_missing_1d_identity_does_not_inherit_unbound_suite(exported: Path) -> None:
    path = _run(exported)
    record = json.loads(path.read_text())
    identity = record.pop("identity")
    _json(path, record)
    _json(exported / "arterial/benchmark_matched.json", {
        "schema": "arterial1d-benchmark/v1", "identity": identity,
    })
    run = _build(exported)["arterial1d"]["runs"][0]
    assert run["source_identity"] is None
    assert run["source_status"] == "NOT_RECORDED"


def test_spatial_profiles_do_not_become_time_trace(exported: Path) -> None:
    csv_path = exported / "arterial/boileau_fixture_4_profiles.csv"
    _csv(csv_path, ["time_s", "x_m", "pressure_pa", "reference_pa", "error_pa"],
         [[0.1, 0.005, -0.01, 0, -0.01], [0.1, 0.015, 0.2, 0.3, -0.1],
          [0.3, 0.005, 0.0, 0.0, 0.0]])
    _json(exported / "arterial/boileau_fixture_4.json", {
        "case": "boileau_fixture", "cells": 4, "scheme": "fixture", "candidate_pass": False,
        "profile_csv": csv_path.name, "csv_artifacts": [{"path": csv_path.name, "sha256": _sha(csv_path)}],
    })
    run = _build(exported)["arterial1d"]["runs"][0]
    assert run["trace"] is None
    assert run["profiles"]["kind"] == "spatial_profiles"
    assert run["profiles"]["times_s"] == [0.1, 0.3]
    assert "no continuous time trace" in run["missing_reason"]


def test_tampered_csv_hash_rejects_package(exported: Path) -> None:
    _run(exported)
    trace = exported / "arterial/matched_fixture_4_trace.csv"
    trace.write_bytes(trace.read_bytes().replace(b"20.12345678901234", b"21.12345678901234"))
    with pytest.raises(BundleError, match="SHA256 mismatch"):
        _build(exported)


def test_tampered_record_hash_bound_by_suite_is_rejected(exported: Path) -> None:
    path = _run(exported)
    _json(exported / "arterial/benchmark_summary.json", {
        "schema": "arterial1d-benchmark/v1",
        "runs": [{"result_json": {"path": path.name, "sha256": _sha(path)}}],
    })
    record = json.loads(path.read_text())
    record["candidate_pass"] = True
    _json(path, record)
    with pytest.raises(BundleError, match="SHA256 mismatch"):
        _build(exported)


def test_malformed_csv_hash_declaration_is_not_treated_as_unknown(exported: Path) -> None:
    path = _run(exported)
    record = json.loads(path.read_text())
    record["csv_artifacts"][0]["sha256"] = None
    _json(path, record)
    with pytest.raises(BundleError, match="invalid CSV hash declaration"):
        _build(exported)


def test_missing_hashed_report_path_is_a_schema_error(exported: Path) -> None:
    _json(exported / "arterial/benchmark_summary.json", {
        "schema": "arterial1d-benchmark/v1", "runs": [{"result_json": {"sha256": "0" * 64}}],
    })
    with pytest.raises(BundleError, match="expected path and SHA256"):
        _build(exported)


def test_nonfinite_delivered_sample_is_rejected(exported: Path) -> None:
    path = exported / "demo/baseline_samples.csv"
    path.write_bytes(path.read_bytes().replace(b"96.12345678901234", b"NaN"))
    with pytest.raises(BundleError, match="expected finite number"):
        _build(exported)


@pytest.mark.parametrize("source_us", [-9007199254740991, -1000000, -1, 9007199254740991])
def test_signed_sensor_source_clock_round_trips_without_changing_delivery(exported: Path, source_us: int) -> None:
    path = exported / "demo/baseline_samples.csv"
    path.write_bytes(path.read_bytes().replace(b"1000999", str(source_us).encode("ascii")))
    bundle = _build(exported)
    sample = bundle["heart"]["cases"]["baseline"]["samples"][1]
    assert sample["source_time_us"] == source_us
    assert sample["source_clock_id"] == "ECG_CLOCK"
    assert sample["t_available_us"] == 1001000
    assert json.loads(json.dumps(sample))["source_time_us"] == source_us


@pytest.mark.parametrize("source_us", [-9007199254740992, 9007199254740992, -1.25])
def test_source_clock_still_rejects_unsafe_or_fractional_values(exported: Path, source_us: int | float) -> None:
    path = exported / "demo/baseline_samples.csv"
    path.write_bytes(path.read_bytes().replace(b"1000999", str(source_us).encode("ascii")))
    with pytest.raises(BundleError, match="signed exact integer source clock"):
        _build(exported)


def test_negative_delivery_clock_is_rejected_even_when_source_clock_may_be_negative(exported: Path) -> None:
    path = exported / "demo/baseline_samples.csv"
    path.write_bytes(path.read_bytes().replace(b"1000003", b"-3"))
    with pytest.raises(BundleError, match="nonnegative exact integer clock"):
        _build(exported)


def test_explicit_outlet_is_in_label_and_original_record_is_preserved(exported: Path) -> None:
    path = _run(exported)
    record = json.loads(path.read_text())
    record["outlet"] = "closed"
    _json(path, record)
    run = _build(exported)["arterial1d"]["runs"][0]
    assert record["case"] in run["label"]
    assert 'outlet="closed"' in run["label"]
    assert run["summary"] == record


@pytest.mark.parametrize("contents,match", [
    ("time_us,time_us\n1,2\n", "duplicate CSV header"),
    ("time_us,x\n1,2,3\n", "row width"),
    ("time_us,x\n1,NaN\n", "non-finite CSV"),
    ("time_us,x\n1,inf\n", "non-finite CSV"),
    ("time_us,x\n1,no-number\n", "nonnumeric CSV"),
    ("time_us,x\n", "no numeric rows"),
    ("", "missing CSV header"),
])
def test_malformed_truth_rejected(exported: Path, contents: str, match: str) -> None:
    (exported / "demo/baseline_truth.csv").write_text(contents, encoding="utf-8")
    with pytest.raises(BundleError, match=match):
        _build(exported)


@pytest.mark.parametrize("contents,match", [
    ('{"metrics":NaN}', "non-finite JSON"),
    ('{"metrics":{},"metrics":{}}', "duplicate JSON"),
    ('[1,2,3]', "expected JSON object"),
])
def test_malformed_provenance_rejected(exported: Path, contents: str, match: str) -> None:
    (exported / "demo/provenance.json").write_text(contents, encoding="utf-8")
    with pytest.raises(BundleError, match=match):
        _build(exported)


def test_bad_suite_schema_rejected(exported: Path) -> None:
    _json(exported / "arterial/benchmark_summary.json", {"schema": "unknown/v9"})
    with pytest.raises(BundleError, match="unsupported arterial suite schema"):
        _build(exported)


def test_backwards_physical_clock_rejected(exported: Path) -> None:
    path = exported / "demo/baseline_truth.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2], lines[1]]) + "\n", encoding="utf-8")
    with pytest.raises(BundleError, match="strictly increasing"):
        _build(exported)


@pytest.mark.parametrize("run_id", ["../outside", "a/b", "C:\\outside", "", ".", ".."])
def test_portable_run_identifier_rejects_paths(exported: Path, run_id: str) -> None:
    with pytest.raises(BundleError, match="portable path-free"):
        build_bundle(exported, Path("demo"), Path("arterial"), run_id, "label")


def test_input_directory_cannot_escape_project(exported: Path) -> None:
    with pytest.raises(BundleError, match="path escapes project"):
        build_bundle(exported, Path("../elsewhere"), Path("arterial"), "good", "label")


def test_real_project_exports_match_bundle_without_solver() -> None:
    root = Path(__file__).resolve().parents[1]
    raw_paths = [*Path(root / "artifacts/demo").glob("*.csv"), *Path(root / "artifacts/demo").glob("*.json")]
    before = {path: _sha(path) for path in raw_paths}
    bundle = build_bundle(root, Path("artifacts/demo"), Path("artifacts/arterial1d"), "real-exports", "Actual records")
    case = bundle["heart"]["cases"]["baseline"]
    assert len(case["rows"]) == 4001
    assert len(case["columns"]) == 33
    assert len(case["samples"]) == 13000
    with (root / "artifacts/demo/baseline_truth.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert case["columns"] == rows[0]
    assert case["rows"] == [[float(value) for value in row] for row in rows[1:]]
    runs = bundle["arterial1d"]["runs"]
    assert len(runs) == 28
    assert sum(run["historical"] for run in runs) == 10
    finest = next(run for run in runs if run["id"] == "boileau_linear3_ssprk3_2560")
    assert finest["summary"]["min_pressure_pa"] == -0.01895853103839329
    assert finest["trace"] is None
    assert finest["profiles"]["times_s"] == [0.1, 0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5]
    assert all(entry["run_git"] is None for entry in runs)
    reflections = [run for run in runs if run["suite"] == "reflections" and run["cells"] == 80]
    assert len(reflections) == 3
    assert len({run["label"] for run in reflections}) == 3
    assert all(run["summary"]["case"] in run["label"] for run in reflections)
    assert before == {path: _sha(path) for path in raw_paths}
