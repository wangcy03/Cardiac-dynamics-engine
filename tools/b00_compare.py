"""Compare frozen B00 reproductions with the imported r2 evidence; never retune."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    out = ROOT / "artifacts" / "b00"
    original = out / "imported"
    reproduced = out / "reproduced"
    old = read_json(original / "numerical_check.json")
    new = read_json(reproduced / "numerical_check.json")
    comparisons = []
    for before, after in zip(old["comparisons"], new["comparisons"], strict=True):
        comparisons.append({
            "step_us": after["step_us"],
            "pressure_metric_delta_mmHg": {
                key: after["pressure_max_difference_mmHg"][key] - value
                for key, value in before["pressure_max_difference_mmHg"].items()
            },
            "event_metric_delta_ms": {
                key: (after["event_max_difference_ms"][key] - value
                      if value is not None and after["event_max_difference_ms"][key] is not None
                      else None)
                for key, value in before["event_max_difference_ms"].items()
            },
            "event_topology_unchanged": (
                before["event_topology_match"] == after["event_topology_match"]
            ),
            "reproduced_status": after["status"],
        })
    old_demo = read_json(original / "demo_provenance.json")
    new_demo = read_json(reproduced / "demo_provenance.json")
    metric_deltas = {
        case: {key: new_demo["metrics"][case][key] - value
               for key, value in values.items()}
        for case, values in old_demo["metrics"].items()
    }
    immutable = {}
    original_core = {}
    for line in (ROOT / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split(maxsplit=1)
        if relative.startswith(("legacy/", "docs/reference/", "iabp/")):
            actual = sha256((ROOT / relative).read_bytes()).hexdigest()
            entry = {"sha256": actual, "matches_imported_manifest": actual == expected}
            (original_core if relative.startswith("iabp/") else immutable)[relative] = entry
    max_pressure_delta = max(
        abs(value) for row in comparisons for value in row["pressure_metric_delta_mmHg"].values()
    )
    old_summary = read_json(original / "verification_summary.json")
    new_summary = read_json(reproduced / "verification_summary.json")
    result = {
        "schema": "iabp-b00-reproduction/v1",
        "scope": "Frozen B00 before B01; software/numerical reproduction only",
        "imported_commit": "fc18650722adbfbd05e4077cda456a8dc4bbd82e",
        "original_environment": {
            "python": old_summary["python"], "platform": old_summary["platform"],
        },
        "reproduced_environment": read_json(out / "environment.json"),
        "pytest_counts": new_summary["pytest_counts"],
        "gates": new_summary["gates"],
        "comparisons": comparisons,
        "max_abs_pressure_metric_change_mmHg": max_pressure_delta,
        "mass_residual_change_mL": [
            {"step_us": b["step_us"],
             "delta": b["max_abs_mass_error_mL"] - a["max_abs_mass_error_mL"]}
            for a, b in zip(old["runs"], new["runs"], strict=True)
        ],
        "demo_metric_changes": metric_deltas,
        "demo_configuration_unchanged": all(
            old_demo[key] == new_demo[key]
            for key in ("model_config", "engine_config", "sensors", "controller")
        ),
        "original_core_files": original_core,
        "immutable_assets": immutable,
        "reporting_defect_found": (
            "Imported verify_all.py hardcodes windows_execution=NOT_RUN even on Windows; "
            "B00 frozen reproduction preserves this raw record. Fixed in the maintained runner."
        ),
        "physiological_validation": "NOT_VALIDATED",
        "clinical_5ms_claim": "NOT_ESTABLISHED",
    }
    good = (
        all(gate["status"] == "PASS" for gate in new_summary["gates"].values())
        and new_summary["pytest_counts"] == old_summary["pytest_counts"]
        and result["demo_configuration_unchanged"]
        and all(entry["matches_imported_manifest"]
                for entry in (*immutable.values(), *original_core.values()))
        and all(row["event_topology_unchanged"] for row in comparisons)
        and all(value == 0 for row in comparisons
                for value in row["event_metric_delta_ms"].values())
        and max_pressure_delta < 1e-8
    )
    result["status"] = "PASS_REPRODUCTION_ONLY" if good else "FAIL"
    (out / "baseline_comparison.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "max_abs_pressure_metric_change_mmHg": max_pressure_delta,
        "demo_configuration_unchanged": result["demo_configuration_unchanged"],
        "original_core_and_archived_assets_unchanged": all(
            entry["matches_imported_manifest"]
            for entry in (*immutable.values(), *original_core.values())
        ),
    }, indent=2))
    if not good:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
