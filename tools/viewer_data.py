"""Read real exports into the versioned observer contract; never run a model.

The Git/source identity of *packaging* is separate from the identity recorded by
an earlier simulation.  Reading a CSV successfully cannot fill that gap.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "cardiac-observer/v1"


class BundleError(ValueError):
    """An export is malformed, inconsistent, or fails its declared hash."""


# No units are inferred from magnitude.  A new, unknown channel stays explicit.
_HEART_CHANNELS = {
    "time_us": ("物理时间", "us", "clock"),
    "ecg_ii": ("ECG II（合成）", "mV", "ecg"),
    "p_lv": ("左室压力", "mmHg", "pressure"),
    "p_root": ("主动脉根部压力", "mmHg", "pressure"),
    "p_descending": ("降主动脉压力", "mmHg", "pressure"),
    "p_systemic_vein": ("体静脉压力", "mmHg", "pressure"),
    "p_ra": ("右房压力", "mmHg", "pressure"),
    "p_rv": ("右室压力", "mmHg", "pressure"),
    "p_pulmonary_artery": ("肺动脉压力", "mmHg", "pressure"),
    "p_pulmonary_vein": ("肺静脉压力", "mmHg", "pressure"),
    "p_la": ("左房压力", "mmHg", "pressure"),
    "v_lv": ("左室容积", "mL", "volume"),
    "v_root": ("主动脉根部容积", "mL", "volume"),
    "v_descending": ("降主动脉容积", "mL", "volume"),
    "v_systemic_vein": ("体静脉容积", "mL", "volume"),
    "v_ra": ("右房容积", "mL", "volume"),
    "v_rv": ("右室容积", "mL", "volume"),
    "v_pulmonary_artery": ("肺动脉容积", "mL", "volume"),
    "v_pulmonary_vein": ("肺静脉容积", "mL", "volume"),
    "v_la": ("左房容积", "mL", "volume"),
    "z_mitral": ("二尖瓣有效开口", "1", "valve"),
    "z_aortic": ("主动脉瓣有效开口", "1", "valve"),
    "z_tricuspid": ("三尖瓣有效开口", "1", "valve"),
    "z_pulmonary": ("肺动脉瓣有效开口", "1", "valve"),
    "q_mv": ("二尖瓣流量", "mL/s", "flow"),
    "q_ao": ("主动脉瓣流量", "mL/s", "flow"),
    "q_link": ("主动脉连接流量", "mL/s", "flow"),
    "a_atrial": ("心房激活", "1", "activation"),
    "a_ventricular": ("心室激活", "1", "activation"),
    "recovery": ("恢复代理状态", "1", "activation"),
    "v_balloon": ("球囊占据容积", "mL", "balloon"),
    "blood_volume": ("全循环血量", "mL", "conservation"),
    "mass_error": ("血量残差", "mL", "conservation"),
}

_METRICS = {
    "max_mass_error_mL": {
        "label": "最大血量残差", "unit": "mL",
        "definition": "max(abs(mass_error)) over exported truth rows",
        "method": "sample maximum",
    },
    "root_min_mmHg": {
        "label": "根部最低压", "unit": "mmHg",
        "definition": "min(p_root) over exported truth rows", "method": "sample minimum",
    },
    "root_max_mmHg": {
        "label": "根部最高压", "unit": "mmHg",
        "definition": "max(p_root) over exported truth rows", "method": "sample maximum",
    },
    "max_balloon_mL": {
        "label": "最大球囊容积", "unit": "mL",
        "definition": "max(v_balloon) over exported truth rows", "method": "sample maximum",
    },
    "net_aortic_volume_mL": {
        "label": "窗口净主动脉出流", "unit": "mL",
        "definition": "sum((Q_i + Q_(i+1))/2 * (t_(i+1)-t_i)/1e6)",
        "method": "trapezoid using actual exported time differences; signed flow; not single-beat SV",
    },
    "lv_net_external_work_mmHg_mL": {
        "label": "窗口 LV 净外部功", "unit": "mmHg·mL",
        "definition": "sum(-(P_i + P_(i+1))/2 * (V_(i+1)-V_i))",
        "method": "trapezoid on exported PV trajectory; no forced closure or steady-state claim",
    },
}


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleError(f"{context}: expected JSON object")
    return value


def _list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise BundleError(f"{context}: expected JSON array")
    return value


def _finite(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BundleError(f"{context}: expected finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise BundleError(f"{context}: expected finite number") from exc
    if not math.isfinite(number):
        raise BundleError(f"{context}: expected finite number")
    return number


def _clock(value: Any, context: str) -> int:
    number = _finite(value, context)
    if number < 0 or not number.is_integer() or number > 2**53 - 1:
        raise BundleError(f"{context}: expected nonnegative exact integer clock")
    return int(number)


def _source_clock(value: Any, context: str) -> int:
    """A sensor clock may precede zero when its configured offset is negative."""
    number = _finite(value, context)
    if not number.is_integer() or abs(number) > 2**53 - 1:
        raise BundleError(f"{context}: expected signed exact integer source clock")
    return int(number)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BundleError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise BundleError(f"non-finite JSON number: {value}")


class _Exports:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.files: dict[str, dict[str, Any]] = {}
        self._cache: dict[Path, bytes] = {}

    def path(self, path: Path) -> Path:
        resolved = (self.root / path).resolve()
        if not resolved.is_relative_to(self.root):
            raise BundleError(f"path escapes project: {path}")
        return resolved

    def read(self, path: Path, role: str, expected: str | None = None) -> bytes:
        resolved = self.path(path)
        try:
            if resolved not in self._cache:
                self._cache[resolved] = resolved.read_bytes()
        except OSError as exc:
            raise BundleError(f"cannot read {resolved.relative_to(self.root)}: {exc}") from exc
        raw = self._cache[resolved]
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or digest != expected):
            raise BundleError(f"SHA256 mismatch: {resolved.relative_to(self.root)}")
        relative = resolved.relative_to(self.root).as_posix()
        entry = self.files.setdefault(relative, {
            "path": relative, "sha256": digest, "bytes": len(raw), "role": role, "roles": [],
        })
        if role not in entry["roles"]:
            entry["roles"].append(role)
        return raw

    def json(self, path: Path, role: str, expected: str | None = None) -> Any:
        try:
            return json.loads(self.read(path, role, expected).decode("utf-8-sig"),
                              object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise BundleError(f"invalid JSON {path}: {exc}") from exc

    def csv(self, path: Path, role: str) -> tuple[list[str], list[list[str]]]:
        try:
            parsed = list(csv.reader(io.StringIO(self.read(path, role).decode("utf-8-sig")), strict=True))
        except (UnicodeError, csv.Error) as exc:
            raise BundleError(f"invalid CSV {path}: {exc}") from exc
        if not parsed or not parsed[0] or any(not x for x in parsed[0]):
            raise BundleError(f"{path}: missing CSV header")
        columns, rows = parsed[0], parsed[1:]
        if len(set(columns)) != len(columns):
            raise BundleError(f"{path}: duplicate CSV header")
        if any(len(row) != len(columns) for row in rows):
            raise BundleError(f"{path}: inconsistent CSV row width")
        return columns, rows


def _numeric_table(exports: _Exports, path: Path, kind: str) -> dict[str, Any]:
    columns, raw_rows = exports.csv(path, kind)
    if not raw_rows:
        raise BundleError(f"{path}: no numeric rows")
    rows: list[list[float]] = []
    for index, raw in enumerate(raw_rows, 2):
        try:
            row = [float(value) for value in raw]
        except ValueError as exc:
            raise BundleError(f"{path}:{index}: nonnumeric CSV cell") from exc
        if any(not math.isfinite(value) for value in row):
            raise BundleError(f"{path}:{index}: non-finite CSV cell")
        rows.append(row)
    units: dict[str, str | None] = {}
    for key in columns:
        if key in _HEART_CHANNELS:
            unit: str | None = _HEART_CHANNELS[key][1]
        elif key == "time_s":
            unit = "s"
        elif key.endswith("_m3_s"):
            unit = "m3/s"
        elif key.endswith("_m3"):
            unit = "m3"
        elif key.endswith("_m2"):
            unit = "m2"
        elif key.endswith("_pa"):
            unit = "Pa"
        elif key.endswith("_m"):
            unit = "m"
        else:
            unit = None
        units[key] = unit
    return {"columns": columns, "rows": rows, "units": units, "kind": kind,
            "path": exports.path(path).relative_to(exports.root).as_posix(),
            "display_sampling": "none; all exported rows retained"}


def _samples(exports: _Exports, path: Path) -> list[dict[str, Any]]:
    columns, rows = exports.csv(path, "delivered_samples")
    required = {"channel_id", "units", "sequence_id", "value", "t_available_us",
                "source_time_us", "source_clock_id", "observable_quality"}
    if set(columns) != required:
        raise BundleError(f"{path}: unsupported sample CSV schema")
    result = []
    for line, row in enumerate(rows, 2):
        sample: dict[str, Any] = dict(zip(columns, row))
        try:
            for key in ("sequence_id", "t_available_us"):
                sample[key] = _clock(float(sample[key]), f"{path}:{line}:{key}")
            sample["value"] = _finite(float(sample["value"]), f"{path}:{line}:value")
            sample["source_time_us"] = (
                _source_clock(float(sample["source_time_us"]), f"{path}:{line}:source_time_us")
                if sample["source_time_us"] else None
            )
        except ValueError as exc:
            raise BundleError(f"{path}:{line}: invalid sample number: {exc}") from exc
        sample["source_clock_id"] = sample["source_clock_id"] or None
        if any(not sample[key] for key in ("channel_id", "units", "observable_quality")):
            raise BundleError(f"{path}:{line}: missing sample identity or quality")
        result.append(sample)
    if any(a["t_available_us"] > b["t_available_us"] for a, b in zip(result, result[1:])):
        raise BundleError(f"{path}: delivery clocks must be nondecreasing")
    return result


def _records(exports: _Exports, path: Path, kind: str) -> list[dict[str, Any]]:
    records = _list(exports.json(path, kind), str(path))
    for index, value in enumerate(records):
        record = _object(value, f"{path}:{index}")
        _clock(record.get("at_us"), f"{path}:{index}:at_us")
        required = ("name", "definition") if kind == "events" else ("command_id", "status", "reason")
        if any(not isinstance(record.get(key), str) for key in required):
            raise BundleError(f"{path}:{index}: unsupported {kind} record schema")
    return records


def _source_path(recorded: str) -> Path | None:
    """Relocate a recorded project path, without reading its old absolute path."""
    normalized = recorded.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts:
        return None
    for marker in ("iabp", "tools", "examples", "tests"):
        if marker in parts:
            return Path(*parts[parts.index(marker):])
    if not normalized.startswith("/") and not re.match(r"^[a-zA-Z]:", normalized):
        return Path(normalized)
    return None


def _source_status(exports: _Exports, identity: dict[str, Any] | None,
                   archived: dict[str, list[Path]]) -> tuple[str, list[str]]:
    if not identity or not identity.get("source_sha256"):
        return "NOT_RECORDED", []
    hashes = _object(identity["source_sha256"], "source_sha256")
    mismatches: list[str] = []
    archived_match = True
    for original, expected in hashes.items():
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise BundleError(f"invalid recorded source SHA256: {original}")
        local = _source_path(original)
        if local is not None and exports.path(local).is_file():
            current = hashlib.sha256(exports.read(local, "source_at_packaging")).hexdigest()
        else:
            current = None
        if current != expected:
            mismatches.append(original)
            candidates = archived.get(expected, [])
            if candidates:
                exports.read(candidates[0], "recorded_source_snapshot", expected)
            else:
                archived_match = False
    if not mismatches:
        return "RECORDED_SOURCE_MATCH", []
    return ("HISTORICAL_SOURCE" if archived_match else "SOURCE_MISMATCH"), mismatches


def _metric_check(rows: list[list[float]], columns: list[str], metrics: dict[str, Any],
                  context: str) -> dict[str, Any]:
    by_key = {key: [row[index] for row in rows] for index, key in enumerate(columns)}
    t, q, p, v = (by_key[key] for key in ("time_us", "q_ao", "p_lv", "v_lv"))
    derived = {
        "max_mass_error_mL": max(abs(x) for x in by_key["mass_error"]),
        "root_min_mmHg": min(by_key["p_root"]),
        "root_max_mmHg": max(by_key["p_root"]),
        "max_balloon_mL": max(by_key["v_balloon"]),
        "net_aortic_volume_mL": sum((a + b) / 2 * (tb - ta) / 1e6
                                     for a, b, ta, tb in zip(q, q[1:], t, t[1:])),
        "lv_net_external_work_mmHg_mL": sum(-(a + b) / 2 * (vb - va)
                                             for a, b, va, vb in zip(p, p[1:], v, v[1:])),
    }
    for key, value in metrics.items():
        _finite(value, f"{context}:metrics:{key}")
        if key in derived and not math.isclose(value, derived[key], rel_tol=1e-12, abs_tol=1e-10):
            raise BundleError(f"{context}: recorded metric inconsistent with full CSV window: {key}")
    return {"status": "CHECKED_EXPORTED_SAMPLES", "derived": derived,
            "recorded_keys_checked": [key for key in metrics if key in derived],
            "note": "Read-only arithmetic on export samples; does not run a model or validate physiology."}


def _heart(exports: _Exports, directory: Path, warnings: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    provenance = _object(exports.json(directory / "provenance.json", "heart_provenance"), "provenance")
    recorded_source = provenance.get("source_sha256")
    if recorded_source is not None:
        identity = {"source_sha256": _object(recorded_source, "heart.source_sha256")}
        status, mismatches = _source_status(exports, identity, {})
    elif provenance.get("model_source_sha256"):
        identity = {"source_sha256": {"iabp/model.py": provenance["model_source_sha256"]}}
        status, mismatches = _source_status(exports, identity, {})
        if status == "RECORDED_SOURCE_MATCH":
            status = "PARTIAL_RECORDED_SOURCE_MATCH"
        warnings.append("0D 旧记录只保存 model.py 哈希；引擎、传感器、场景及运行 Git 身份未完整记录。")
    else:
        identity, status, mismatches = None, "NOT_RECORDED", []
        warnings.append("0D 记录未提供运行源码哈希；不能归属当前源码。")
    if mismatches:
        warnings.append("0D 记录源码与当前文件不匹配：" + ", ".join(mismatches))
    all_metrics = _object(provenance.get("metrics", {}), "provenance.metrics")
    cases: dict[str, Any] = {}
    all_columns: list[str] = []
    for name, label in (("baseline", "无辅助"), ("assisted", "因果控制器演示")):
        table = _numeric_table(exports, directory / f"{name}_truth.csv", "physical_truth")
        columns, rows = table["columns"], table["rows"]
        required = {"time_us", "ecg_ii", "p_lv", "p_root", "p_descending", "q_ao", "v_lv", "v_balloon", "mass_error"}
        if not required.issubset(columns):
            raise BundleError(f"{name}: missing required truth columns: {sorted(required - set(columns))}")
        time_index = columns.index("time_us")
        times = [_clock(row[time_index], f"{name}:time_us") for row in rows]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise BundleError(f"{name}: truth physical clocks must be strictly increasing")
        metrics = _object(all_metrics.get(name, {}), f"{name}:metrics")
        if not metrics:
            warnings.append(f"{name} 未导出指标，保留空集；样本积分核对另列，不填充原始指标。")
        cases[name] = {
            "label": label, "columns": columns, "rows": rows,
            "samples": _samples(exports, directory / f"{name}_samples.csv"),
            "events": _records(exports, directory / f"{name}_events.json", "events"),
            "commands": _records(exports, directory / f"{name}_commands.json", "commands"),
            "metrics": metrics, "window_us": [times[0], times[-1]],
            "metric_window_us": [times[0], times[-1]], "source_status": status,
            "source_identity": identity, "metric_check": _metric_check(rows, columns, metrics, name),
            "clock_semantics": {
                "truth": "time_us: engine physical time",
                "sample_delivery": "t_available_us: inbox availability, not callback execution time",
                "sample_source": "source_time_us: optional signed sensor clock including offset; null remains unobservable",
                "events_commands": "at_us: original event or command status time",
            },
        }
        for key in columns:
            if key not in all_columns:
                all_columns.append(key)
    channels = []
    for key in all_columns:
        label, unit, group = _HEART_CHANNELS.get(key, (key, None, "unclassified"))
        channels.append({"key": key, "label": label, "unit": unit, "group": group})
        if unit is None:
            warnings.append(f"未声明心脏通道单位：{key}")
    definitions = {key: {**value, "window": "full_record"} for key, value in _METRICS.items()}
    heart = {"channels": channels, "cases": cases, "metric_definitions": definitions,
             "source_status": status, "source_identity": identity,
             "initial_state": {
                 "within_demo_shared": None,
                 "first_exported_state_equal": (
                     cases["baseline"]["columns"] == cases["assisted"]["columns"]
                     and cases["baseline"]["rows"][0] == cases["assisted"]["rows"][0]
                 ),
                 "cross_iteration": None,
                 "reason": "运行脚本使用共享进程内快照，但旧导出未序列化快照/RNG/队列身份；首行相等不证明全状态一致。",
             }}
    warnings.append("0D 桥接演示与独立 1D 尚未耦合；本数据包不建立临床、5 ms 或患者校准结论。")
    return heart, provenance


def _archive_index(exports: _Exports, directory: Path) -> tuple[dict[str, list[Path]], dict[str, str]]:
    sources: dict[str, list[Path]] = {}
    historical_files: dict[str, str] = {}
    manifest_path = directory / "history/pre_linear3/manifest.json"
    if exports.path(manifest_path).is_file():
        manifest = _object(exports.json(manifest_path, "historical_manifest"), str(manifest_path))
        if manifest.get("schema") != "arterial1d-historical-source-snapshot/v1":
            raise BundleError(f"unsupported historical manifest schema: {manifest_path}")
        for value in _list(manifest.get("files"), str(manifest_path)):
            entry = _object(value, "historical file")
            relative = entry.get("path")
            digest = entry.get("sha256")
            if not isinstance(relative, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise BundleError("invalid historical file declaration")
            local = Path(relative.replace("\\", "/"))
            sources.setdefault(digest, []).append(manifest_path.parent / local)
            historical_files[local.as_posix()] = digest
    return sources, historical_files


def _recorded_snapshot(exports: _Exports, directory: Path, identity: dict[str, Any] | None,
                       archive: dict[str, list[Path]]) -> None:
    if not identity or not identity.get("source_snapshot_manifest"):
        return
    relative = identity["source_snapshot_manifest"]
    if not isinstance(relative, str):
        raise BundleError("source_snapshot_manifest must be a path")
    manifest = _object(exports.json(directory / relative, "source_snapshot_manifest"), relative)
    for value in _list(manifest.get("files"), relative):
        entry = _object(value, "source snapshot file")
        original, path, digest = entry.get("original_path"), entry.get("path"), entry.get("sha256")
        if not all(isinstance(x, str) for x in (original, path, digest)):
            raise BundleError("invalid source snapshot file declaration")
        recorded = _object(identity.get("source_sha256"), "identity.source_sha256")
        if recorded.get(original) != digest:
            raise BundleError(f"source snapshot and recorded identity disagree: {original}")
        source_path = directory / path.replace("\\", "/")
        exports.read(source_path, "recorded_source_snapshot", digest)
        archive.setdefault(digest, []).append(source_path)


def _failures(record: dict[str, Any]) -> list[str]:
    return [f"{key}=false" for key, value in record.items()
            if value is False and (key == "pass" or key.endswith("_pass"))]


def _report_references(exports: _Exports, directory: Path, value: Any) -> None:
    """Verify declared report/result/log hashes without interpreting acceptance."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("result_json", "run_log", "historical_controls"):
                _reference(exports, directory, item, "recorded_report_reference")
            _report_references(exports, directory, item)
    elif isinstance(value, list):
        for item in value:
            _report_references(exports, directory, item)


def _reference(exports: _Exports, directory: Path, value: Any, role: str) -> None:
    entry = _object(value, role)
    if not isinstance(entry.get("path"), str) or not isinstance(entry.get("sha256"), str):
        raise BundleError(f"{role}: expected path and SHA256 declaration")
    exports.read(directory / entry["path"], role, entry["sha256"])


def _public_inputs(exports: _Exports, directory: Path, record: dict[str, Any]) -> None:
    # These are retained local CC0 inputs; no network access or acquisition.
    identity = record.get("data_identity")
    if not isinstance(identity, dict):
        return
    inputs = {
        "archive_sha256": "Benchmark1_SinglePulseModel.zip",
        "manifest_sha256": "manifest.json",
        "source_config_sha256": "case1_source_config.json",
    }
    for field, name in inputs.items():
        if field in identity:
            if not isinstance(identity[field], str):
                raise BundleError(f"public data: invalid {field}")
            exports.read(directory / "external/boileau2015" / name, "public_reference_input", identity[field])


def _arterial(exports: _Exports, directory: Path, warnings: list[str]) -> dict[str, Any]:
    if not exports.path(directory).is_dir():
        warnings.append("独立 1D 导出目录不存在；保持空集。")
        return {"runs": [], "suites": [], "summary": None}
    archive, historical_files = _archive_index(exports, directory)
    reports: dict[str, dict[str, Any]] = {}
    for path in sorted(exports.path(directory).glob("benchmark_*.json")):
        report = _object(exports.json(path, "arterial_suite"), str(path))
        if report.get("schema") != "arterial1d-benchmark/v1":
            raise BundleError(f"unsupported arterial suite schema: {path.name}")
        reports[path.name] = report
        _report_references(exports, directory, report)
    summary = reports.get("benchmark_summary.json")
    if summary:
        for value in _object(summary.get("source_reports", {}), "source_reports").values():
            entry = _object(value, "source report")
            _reference(exports, directory, entry, "arterial_suite")
            run_log = entry.get("run_log")
            if run_log:
                _reference(exports, directory, run_log, "numerical_run_log")
    runs: list[dict[str, Any]] = []
    patterns = (("matched_*.json", "matched"), ("reflection_*.json", "reflections"),
                ("junction_symmetric_*.json", "junction"), ("boileau_*.json", "boileau"))
    for pattern, suite in patterns:
        for path in sorted(exports.path(directory).glob(pattern)):
            record = _object(exports.json(path, "arterial_run"), str(path))
            if not isinstance(record.get("case"), str) or not isinstance(record.get("scheme"), str):
                raise BundleError(f"unsupported arterial run schema: {path.name}")
            cells = record.get("cells", record.get("cells_per_segment"))
            if isinstance(cells, bool) or not isinstance(cells, int) or cells <= 0:
                raise BundleError(f"invalid grid size: {path.name}")
            _public_inputs(exports, directory, record)
            source_identity = record.get("identity")
            if not isinstance(source_identity, dict) or not source_identity.get("source_sha256"):
                fallback = reports.get("benchmark_matched.json" if suite == "matched" else "benchmark_boileau.json", {})
                # Old controls were recorded before per-run source identities.
                # Inherit only from their hash-bound archived report, never by
                # matching a new filename or by copying the current checkout.
                report_name = "benchmark_matched.json" if suite == "matched" else "benchmark_boileau.json"
                if suite in ("matched", "boileau") and path.name in historical_files and report_name in historical_files:
                    exports.read(path, "historical_run", historical_files[path.name])
                    exports.read(directory / report_name, "historical_suite", historical_files[report_name])
                    source_identity = fallback.get("identity")
                else:
                    source_identity = None
            if source_identity is not None:
                source_identity = _object(source_identity, path.name + ":identity")
            _recorded_snapshot(exports, directory, source_identity, archive)
            status, mismatches = _source_status(exports, source_identity, archive)
            historical = status == "HISTORICAL_SOURCE"
            if historical and path.name in historical_files:
                exports.read(path, "historical_run", historical_files[path.name])
            if status == "SOURCE_MISMATCH":
                warnings.append(f"{path.name} 源码身份无法匹配当前或已记录快照：{', '.join(mismatches)}")
            elif status == "NOT_RECORDED":
                warnings.append(f"{path.name} 未记录可归属的运行源码身份，不能回填当前 Git/源码。")
            expected_csv: dict[str, str] = {}
            for value in _list(record.get("csv_artifacts", []), path.name + ":csv_artifacts"):
                entry = _object(value, "csv_artifact")
                if not isinstance(entry.get("path"), str) or not isinstance(entry.get("sha256"), str):
                    raise BundleError(f"{path.name}: invalid CSV hash declaration")
                expected_csv[entry["path"]] = entry["sha256"]
            trace = profiles = None
            for field, kind in (("trace_csv", "time_trace"), ("profile_csv", "spatial_profiles")):
                relative = record.get(field)
                if relative is None:
                    continue
                if not isinstance(relative, str):
                    raise BundleError(f"{path.name}: invalid {field}")
                csv_path = directory / relative
                expected = expected_csv.get(relative)
                if expected is None and historical:
                    expected = historical_files.get(relative.replace("\\", "/"))
                if expected is not None:
                    exports.read(csv_path, kind, expected)
                else:
                    warnings.append(f"{path.name}: {relative} 未记录运行时 CSV 哈希，当前哈希只证明打包副本。")
                table = _numeric_table(exports, csv_path, kind)
                if "time_s" not in table["columns"]:
                    raise BundleError(f"{relative}: missing time_s")
                time_col = table["columns"].index("time_s")
                if kind == "time_trace":
                    times = [row[time_col] for row in table["rows"]]
                    if any(b <= a for a, b in zip(times, times[1:])):
                        raise BundleError(f"{relative}: trace clocks must strictly increase")
                    trace = table
                else:
                    if "x_m" not in table["columns"]:
                        raise BundleError(f"{relative}: profiles require x_m")
                    table["times_s"] = sorted({row[time_col] for row in table["rows"]})
                    x_col = table["columns"].index("x_m")
                    last_x: dict[float, float] = {}
                    for row in table["rows"]:
                        time, x = row[time_col], row[x_col]
                        if time in last_x and x <= last_x[time]:
                            raise BundleError(f"{relative}: profile positions must increase within each time")
                        last_x[time] = x
                    profiles = table
            if trace is None and profiles is None:
                raise BundleError(f"{path.name}: no exported trace or spatial profiles")
            failures = _failures(record)
            flags = [value for key, value in record.items()
                     if key == "pass" or key.endswith("_pass")]
            if any(not isinstance(value, bool) for value in flags):
                raise BundleError(f"{path.name}: declared checks must be boolean")
            declared = "FAIL_DECLARED_CHECKS" if failures else ("PASS_DECLARED_CHECKS" if flags else "NOT_DECLARED")
            case_label = record["case"]
            if record.get("outlet") is not None:
                case_label += " / outlet=" + json.dumps(record["outlet"], ensure_ascii=False, sort_keys=True)
            runs.append({
                "id": path.stem, "label": f"{suite} · {case_label} · {record['scheme']} · {cells}",
                "suite": suite, "method": record["scheme"], "cells": cells,
                "status": declared, "summary": record, "trace": trace, "profiles": profiles,
                "source_status": status, "source_identity": source_identity,
                "source_mismatches": mismatches, "historical": historical,
                "failures": failures, "result_path": path.relative_to(exports.root).as_posix(),
                "status_basis": "original per-run boolean flags; no numerical acceptance re-execution",
                "missing_reason": "Only exported spatial profiles; no continuous time trace was recorded." if trace is None else None,
                "run_git": record.get("git"),
            })
    suites = [{"id": key, "label": key, "summary": value,
               "path": (directory / key).relative_to(exports.root).as_posix()}
              for key, value in reports.items()]
    return {"runs": runs, "suites": suites, "summary": summary,
            "scope": "independent 1D vessels; no coupling to the displayed 0D heart",
            "units": "SI: Pa, m, s, m2, m3, m3/s; no implicit conversion to heart units"}


def _git(root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                                capture_output=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True,
                                    capture_output=True, check=True).stdout.strip())
        return {"commit": commit, "dirty": dirty, "meaning": "packaging checkout, not historical simulation identity"}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None, "meaning": "packaging Git identity unavailable"}


def build_bundle(root: Path, demo_dir: Path, arterial_dir: Path,
                 run_id: str, label: str) -> dict[str, Any]:
    """Build a JSON-serializable, read-only bundle from existing CSV/JSON exports.

    Relative directories are resolved against ``root``. Every input must remain
    within that root. Hash/schema errors raise ``BundleError``. Unknown recorded
    source identity is retained as an explicit status and warning, never filled
    with the current packaging checkout.
    """
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", run_id):
        raise BundleError("run_id must be a portable path-free identifier")
    if not isinstance(label, str) or not label.strip():
        raise BundleError("run label must be nonempty")
    exports = _Exports(root)
    demo_dir, arterial_dir = exports.path(demo_dir), exports.path(arterial_dir)
    warnings: list[str] = []
    heart, provenance = _heart(exports, demo_dir, warnings)
    arterial = _arterial(exports, arterial_dir, warnings)
    source_hashes = {entry["path"]: entry["sha256"] for entry in exports.files.values()
                     if "source_at_packaging" in entry["roles"]}
    statuses = [heart["source_status"], *(run["source_status"] for run in arterial["runs"])]
    source_status = "SOURCE_MISMATCH" if "SOURCE_MISMATCH" in statuses else "MIXED_RECORDED_SCOPE"
    bundle = {
        "schema": SCHEMA,
        "run": {
            "id": run_id, "label": label,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "git": _git(exports.root), "simulation_git": None,
            "source_sha256": source_hashes, "source_status": source_status,
            "files": sorted(exports.files.values(), key=lambda value: value["path"]),
            "provenance": {
                "heart": provenance, "bundle_scope": "OFFLINE_EXPORT_ONLY",
                "initial_state": heart["initial_state"],
                "scene": "Original recorded demo configuration; independent 1D benchmark suites are separate experiments.",
                "numerics": {"heart": provenance.get("engine_config"),
                             "arterial": "see each raw summary.parameters/cfl/dt_policy"},
                "recorded_simulation_git": provenance.get("git"),
                "qualification": "ENGINEERING_SIMULATION_NOT_CLINICAL",
            },
        },
        "heart": heart, "arterial1d": arterial, "warnings": list(dict.fromkeys(warnings)),
        "capabilities": ["exported_0d_truth", "delivered_samples", "original_events", "command_statuses",
                         "independent_1d" if arterial["runs"] else "independent_1d_not_provided",
                         "full_precision_rows", "physical_time_without_alignment"],
    }
    # json permits NaN by default; explicitly exercise the portable contract here.
    try:
        json.dumps(bundle, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise BundleError(f"bundle cannot be serialized as finite JSON: {exc}") from exc
    return bundle
