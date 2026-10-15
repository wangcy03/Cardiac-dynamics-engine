"""Failure evidence must remain a failure, even when another report exists."""
from pathlib import Path
import sys

from tools.verify_all import read_pytest_counts, run_job


def test_failed_gate_retains_exit_status_and_stderr(tmp_path: Path) -> None:
    result = run_job(
        "failed_probe",
        [sys.executable, "-c", "import sys; print('failed explicitly', file=sys.stderr); "
         "raise SystemExit(7)"],
        tmp_path,
    )
    assert result["status"] == "FAIL"
    assert result["exit_code"] == 7
    assert "failed explicitly" in (tmp_path / "failed_probe.log").read_text(encoding="utf-8")


def test_missing_or_partial_pytest_report_cannot_supply_pass_counts(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    assert read_pytest_counts(report) is None
    report.write_text("<testsuites><testsuite", encoding="utf-8")
    assert read_pytest_counts(report) is None
