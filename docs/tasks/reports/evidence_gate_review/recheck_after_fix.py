"""Independent evidence-gate fault probes. NO_SOLVER_RUN; temporary data only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from tools import arterial1d_check as gate

EXPECTED_TOOL = "a60fa6d721fc9bc63af9c2ff18917a7fc46df68c92bcb472c8cb41a474f0e635"
tool = ROOT / "tools/arterial1d_check.py"
assert hashlib.sha256(tool.read_bytes()).hexdigest() == EXPECTED_TOOL
base = ROOT / "artifacts/local_review"
base.mkdir(parents=True, exist_ok=True)
checks = []


def rejected(label, action):
    try:
        action()
    except (ValueError, FileNotFoundError):
        checks.append({"case": label, "result": "REJECTED_AS_REQUIRED"})
    else:
        raise AssertionError(f"Failed to reject {label}")


def coverage():
    def rows(case, scheme, grids, key="cells"):
        return [{"case": case, "scheme": scheme, key: n} for n in grids]

    return {
        "linear3_matched": {"linear3_matched": rows("engineering_matched_pressure_pulse", "linear3_ssprk3", [80, 160, 320])},
        "linear3_boileau": {"linear3_boileau": rows("boileau2015_single_pulse_inviscid", "linear3_ssprk3", [640, 1280, 2560])},
        "reflections": {"reflections": [{"case": kind, "runs": rows(kind, "muscl_ssprk2", [80, 160, 320])} for kind in ("closed", "pressure_release", "resistance_2z0")]},
        "junction": {"junction": {"runs": rows("symmetric_static_pressure_junction", "muscl_ssprk2", [40, 80, 160], "cells_per_segment")}},
    }


gate._validate_coverage(coverage())
for label in ("empty_reflections", "missing_type", "duplicate_type", "missing_reflection_grid", "empty_junction", "wrong_scheme", "wrong_run_case", "reordered_public", "append_coarser", "missing_public_grid"):
    report = coverage()
    groups = report["reflections"]["reflections"]
    if label == "empty_reflections":
        groups.clear()
    elif label == "missing_type":
        groups.pop()
    elif label == "duplicate_type":
        groups[-1] = copy.deepcopy(groups[0])
    elif label == "missing_reflection_grid":
        groups[0]["runs"].pop()
    elif label == "empty_junction":
        report["junction"]["junction"]["runs"].clear()
    elif label == "wrong_scheme":
        report["linear3_matched"]["linear3_matched"][0]["scheme"] = "rusanov"
    elif label == "wrong_run_case":
        groups[0]["runs"][0]["case"] = "pressure_release"
    elif label == "reordered_public":
        report["linear3_boileau"]["linear3_boileau"].reverse()
    elif label == "append_coarser":
        report["linear3_boileau"]["linear3_boileau"].append(copy.deepcopy(report["linear3_boileau"]["linear3_boileau"][0]))
    else:
        report["linear3_boileau"]["linear3_boileau"].pop()
    rejected(label, lambda: gate._validate_coverage(report))

csv_run = {"case": "engineering_matched_pressure_pulse", "scheme": "linear3_ssprk3", "cells": 80,
           "csv_artifacts": [{"path": "matched_linear3_ssprk3_80_trace.csv"}, {"path": "matched_linear3_ssprk3_80_profiles.csv"}]}
gate._verify_csv_coverage(csv_run)
for label in ("empty_csv", "missing_csv", "duplicate_csv", "extra_csv"):
    run = copy.deepcopy(csv_run)
    if label == "empty_csv":
        run["csv_artifacts"].clear()
    elif label == "missing_csv":
        run["csv_artifacts"].pop()
    elif label == "duplicate_csv":
        run["csv_artifacts"].append(copy.deepcopy(run["csv_artifacts"][0]))
    else:
        run["csv_artifacts"].append({"path": "unrelated.csv"})
    rejected(label, lambda: gate._verify_csv_coverage(run))

failed = {"case": "closed", "pass": True, "candidate_pass": True, "measured_coefficient": 0.5, "conservation_relative_initial_volume": 0.0}
assert gate._run_acceptance(failed, "reflection") is False
checks.append({"case": "wrapper_true_cannot_override_numeric_fail", "result": "FALSE_AS_REQUIRED"})
failed.update({"pass": False, "candidate_pass": False, "measured_coefficient": 1.0})
assert gate._run_acceptance(failed, "reflection") is True
checks.append({"case": "wrapper_false_is_not_numeric_evidence", "result": "TRUE_FROM_VALID_NUMBERS"})

with tempfile.TemporaryDirectory(prefix="spec-gate-repaired-", dir=base) as temporary:
    root = Path(temporary)
    assert root.resolve().is_relative_to(base.resolve())
    raw_source = b"fixed source\n"
    digest = hashlib.sha256(raw_source).hexdigest()
    (root / "source.py").write_bytes(raw_source)
    identity = {"source_sha256": {"source.py": digest}, "source_snapshot_manifest": "snapshot.json"}
    snapshot = {"source_sha256": identity["source_sha256"], "files": [{"original_path": "source.py", "path": "source.py", "sha256": digest}]}
    (root / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    (root / "trace.csv").write_bytes(b"time_s,pressure_pa\n0,0\n")
    (root / "run.log").write_bytes(b"ACTUAL_SOLVER_RUN complete\n")
    run = {"case": "fixture", "identity": identity, "source_unchanged_during_run": True, "run_log_path": "run.log",
           "csv_artifacts": [{"path": "trace.csv", "sha256": hashlib.sha256((root / "trace.csv").read_bytes()).hexdigest()}]}
    (root / "result.json").write_text(json.dumps(run), encoding="utf-8")
    run["result_json"] = {"path": "result.json", "sha256": hashlib.sha256((root / "result.json").read_bytes()).hexdigest()}
    suite = {"identity": identity, "selected_case": "fixture", "mode": "ACTUAL_SOLVER_RUN", "thresholds_declared_before_runs": gate.ENGINEERING_THRESHOLDS,
             "boileau_thresholds_declared_before_runs": gate.BOILEAU_THRESHOLDS, "run_log": {"path": "run.log", "sha256": hashlib.sha256((root / "run.log").read_bytes()).hexdigest()}}
    gate._verify_report(root, "fixture", suite, [run], identity)
    rejected("empty_current_runs", lambda: gate._verify_report(root, "fixture", suite, [], identity))
    (root / "snapshot.json").write_text(json.dumps({**snapshot, "files": []}), encoding="utf-8")
    rejected("empty_snapshot_source_files", lambda: gate._verify_report(root, "fixture", suite, [run], identity))
    (root / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    (root / "source.py").write_bytes(b"changed source\n")
    rejected("snapshot_source_byte_drift", lambda: gate._verify_report(root, "fixture", suite, [run], identity))

    source_data = ROOT / "artifacts/arterial1d/external/boileau2015"
    destination = root / "external/boileau2015"
    shutil.copytree(source_data, destination)
    current = gate.verify_boileau_data(destination)
    public_run = {"data_identity": {**current, "before": copy.deepcopy(current), "after": copy.deepcopy(current), "unchanged_during_run": True,
                                    "reference_archive_member": "Benchmark1_SinglePulseModel/NumData/FVM_inviscid.txt"},
                  "parameters": {"source_config_sha256": current["source_config_sha256"]}}
    gate._validate_public_data_identity(root, public_run)
    for filename in ("case1_source_config.json", "manifest.json", "Benchmark1_SinglePulseModel.zip"):
        artifact = destination / filename
        original = artifact.read_bytes()
        artifact.write_bytes(original + b"\n")
        rejected("actual_input_drift_" + filename, lambda: gate._validate_public_data_identity(root, public_run))
        artifact.write_bytes(original)
    rejected("missing_captured_public_data_identity", lambda: gate._validate_public_data_identity(root, {"parameters": public_run["parameters"]}))

assert hashlib.sha256(tool.read_bytes()).hexdigest() == EXPECTED_TOOL
assert len(checks) == 23
result = {"scope": "independent repaired evidence-gate fault probes; NO_SOLVER_RUN", "tool_sha256": EXPECTED_TOOL,
          "checks": checks, "count": len(checks), "status": "PASS"}
(base / "spec_evidence_gate_recheck_reproduced.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "count": result["count"], "tool_sha256": EXPECTED_TOOL}, indent=2))
