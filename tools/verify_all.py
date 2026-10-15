"""Run gates, retain exit codes and identities, and fail closed on missing evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from typing import Any
import xml.etree.ElementTree as ET

from iabp import __version__


def read_pytest_counts(path: Path) -> dict[str, int] | None:
    """A crashed pytest process must not inherit counts from a previous run."""
    if not path.exists():
        return None
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return {
        key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def run_job(name: str, command: list[str], out: Path) -> dict[str, Any]:
    start = perf_counter()
    run = subprocess.run(
        command, text=True, capture_output=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    log = out / f"{name}.log"
    log.write_text(run.stdout + run.stderr, encoding="utf-8")
    return {
        "status": "PASS" if run.returncode == 0 else "FAIL",
        "command": command,
        "exit_code": run.returncode,
        "elapsed_seconds": perf_counter() - start,
        "log": log.as_posix(),
        "log_sha256": sha256(log.read_bytes()).hexdigest(),
    }


def package_versions() -> dict[str, str | None]:
    packages: dict[str, str | None] = {}
    for name in ("pytest", "numpy", "scipy", "ruff", "mypy"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return packages


def main() -> None:
    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    report = out / "pytest.xml"
    # Remove this generated report before pytest so a crash cannot reuse old counts.
    report.unlink(missing_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    jobs = {
        "compile": ["compileall", "-q", "iabp", "tools", "examples"],
        "pytest": ["pytest", "-q", f"--junitxml={report.as_posix()}"],
        "numerical": ["tools.numerical_check"],
    }
    results = {
        name: run_job(name, [sys.executable, "-m", *args], out)
        for name, args in jobs.items()
    }
    for tool, args in (
        ("ruff", ["check", "iabp", "tests", "tools", "examples"]),
        ("mypy", ["iabp"]),
    ):
        if importlib.util.find_spec(tool) is None:
            results[tool] = {
                "status": "NOT_RUN",
                "exit_code": None,
                "reason": "tool unavailable; install declared dev dependencies",
            }
        else:
            results[tool] = run_job(tool, [sys.executable, "-m", tool, *args], out)
    # B01 never replaces the separate 0D time-step study.
    if Path("tools/arterial1d_check.py").exists():
        results["arterial1d"] = run_job(
            "arterial1d", [sys.executable, "-m", "tools.arterial1d_check"], out,
        )
    counts = read_pytest_counts(report)
    if counts is None or counts["tests"] == 0:
        results["pytest"]["status"] = "FAIL"
        results["pytest"]["reason"] = "No fresh nonempty pytest XML evidence"
    complete = all(gate["status"] == "PASS" for gate in results.values())
    source_hashes = {
        path.as_posix(): sha256(path.read_bytes()).hexdigest()
        for folder in ("iabp", "tools", "tests", "examples")
        for path in sorted(Path(folder).rglob("*.py"))
    }
    summary = {
        "schema": "iabp-local-verification/v2",
        "release": f"r2 / {__version__}",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": package_versions(),
        "source_sha256": source_hashes,
        "gates": results,
        "pytest_counts": counts,
        "software_gates": "PASS" if complete else "INCOMPLETE_OR_FAIL",
        "physiological_validation": "NOT_VALIDATED",
        "spatial_convergence": (
            "SEE_INDEPENDENT_B01_REPORT_NOT_COUPLED_ENGINE"
            if "arterial1d" in results else "NOT_IMPLEMENTED"
        ),
        "actuator_calibration": "NOT_VALIDATED",
        "real_algorithm_integration": "NOT_IMPLEMENTED",
        "github_ci": "NOT_RUN",
        "windows_execution": (
            ("PASS_LOCAL" if complete else "INCOMPLETE_OR_FAIL")
            if platform.system() == "Windows" else "NOT_RUN_THIS_ENVIRONMENT"
        ),
        "clinical_5ms_claim": "NOT_ESTABLISHED",
    }
    (out / "verification_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in summary.items()
                      if key != "source_sha256"}, indent=2))
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
