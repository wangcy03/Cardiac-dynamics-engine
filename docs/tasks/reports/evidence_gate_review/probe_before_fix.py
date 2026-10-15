"""Historical synthetic contract probe. NO_SOLVER_RUN; no benchmark files changed."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
source = ROOT / "artifacts/arterial1d/history/source_bd493b738097c431/files/tools/arterial1d_check.py"
expected = "9b04739a740c6c7fc10d348d78a5cca43e3bbc2607a42a16283ac93396ab8427"
assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
spec = importlib.util.spec_from_file_location("pre_fix_arterial1d_check", source)
assert spec is not None and spec.loader is not None
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

base = ROOT / "artifacts/local_review"
base.mkdir(parents=True, exist_ok=True)
fixture = runpy.run_path("tests/test_arterial1d_benchmarks.py")["_gate_fixture"]
with tempfile.TemporaryDirectory(prefix="spec-gate-before-", dir=base) as temporary:
    root = Path(temporary)
    assert root.resolve().is_relative_to(base.resolve())
    identity, report, run = fixture(root)
    check._verify_report(root, "empty_reflections", report, [], identity)
    run["pass"] = False
    raw = {key: value for key, value in run.items() if key != "result_json"}
    (root / "result.json").write_text(json.dumps(raw), encoding="utf-8")
    run["result_json"]["sha256"] = hashlib.sha256((root / "result.json").read_bytes()).hexdigest()
    suite = copy.deepcopy(report)
    suite["reflections"] = [{"case": "closed", "runs": [run], "candidate_pass": True}]
    check._verify_report(root, "conflicting_reflections", suite, [run], identity)
    check._PROCESS_IDENTITY = check._identity()
    result = check._finish_run(root, "synthetic_data_identity_probe.json", {
        "case": "SYNTHETIC_SCHEMA_PROBE_NOT_A_SOLVER_RUN",
        "identity": {"archive_sha256": "dataset-a", "download_integrity": "PASS"},
    }, {}, ["trace.csv"])
    observation = {
        "scope": "synthetic structure fault probes only; no solver or benchmark run",
        "empty_run_suite_accepted": True,
        "conflicting_unbound_suite_pass_flag_accepted": True,
        "run_pass": run["pass"],
        "suite_candidate_pass": suite["reflections"][0]["candidate_pass"],
        "dataset_archive_hash_retained_by_finish_run": "archive_sha256" in result["identity"],
    }
    assert observation["dataset_archive_hash_retained_by_finish_run"] is False
    print(json.dumps(observation, indent=2))
    (base / "spec_evidence_gate_probe_reproduced.json").write_text(
        json.dumps(observation, indent=2) + "\n", encoding="utf-8"
    )
