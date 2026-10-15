"""Independent arterial propagation checks, retaining unshifted numerical evidence.

Run ``python -m tools.arterial1d_check`` after installing development dependencies.
Only ``--plot-only`` uses optional matplotlib; the numerical checks use the standard library.
The Boileau viscous case uses a different friction coefficient and is not reproduced here.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import platform
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Sequence


ENGINEERING_THRESHOLDS = {
    "arrival_error_ms": 0.5,
    "peak_relative_error": 0.01,
    "conservation_relative_initial_volume": 1e-10,
    "reflection_coefficient_absolute_error": 0.05,
    "symmetric_split_absolute_error": 0.005,
    "junction_backward_forward_peak_ratio": 0.05,
}
BOILEAU_THRESHOLDS = {
    "relative_max_profile_error": 0.05,
    "maximum_peak_relative_error": 0.05,
    "peak_position_absolute_difference_m": 0.02,
    "conservation_relative_initial_volume": 1e-10,
}
PULSE_START_S = 0.05
PULSE_END_S = 0.09
PULSE_PEAK_PA = 20.0
ENGINEERING_AREA_M2 = 3e-4
ENGINEERING_DENSITY_KG_M3 = 1060.0
ENGINEERING_WAVE_SPEED_M_S = 5.0
ENGINEERING_Z0 = ENGINEERING_DENSITY_KG_M3 * ENGINEERING_WAVE_SPEED_M_S / ENGINEERING_AREA_M2
BOILEAU_PROFILE_TIMES_S = (0.1, 0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5)
_PROCESS_IDENTITY: dict[str, Any] | None = None
_RUN_LOG: Path | None = None


def pulse_pressure_pa(t_s: float) -> float:
    if not PULSE_START_S < t_s < PULSE_END_S:
        return 0.0
    phase = math.pi * (t_s - PULSE_START_S) / (PULSE_END_S - PULSE_START_S)
    return PULSE_PEAK_PA * math.sin(phase) ** 2


def pressure_pulse_integral(t_s: float) -> float:
    """Exact integral from time zero; units Pa s."""
    width = PULSE_END_S - PULSE_START_S
    elapsed = min(width, max(0.0, t_s - PULSE_START_S))
    return PULSE_PEAK_PA / 2 * (
        elapsed - width / (2 * math.pi) * math.sin(2 * math.pi * elapsed / width)
    )


def crossing_time(points: Sequence[tuple[float, float]], threshold: float) -> float | None:
    """First rising crossing of a fixed truth-based threshold, with linear interpolation."""
    for (t0, p0), (t1, p1) in zip(points, points[1:]):
        if p0 < threshold <= p1:
            return t0 + (threshold - p0) * (t1 - t0) / (p1 - p0)
    return None


def timing_and_peak_metrics(
    points: Sequence[tuple[float, float]], expected_arrival_s: float
) -> dict[str, Any]:
    peak = max(p for _, p in points)
    arrival = crossing_time(points, PULSE_PEAK_PA / 2)
    arrival_error = None if arrival is None else abs(arrival - expected_arrival_s) * 1000
    peak_error = abs(peak - PULSE_PEAK_PA) / PULSE_PEAK_PA
    return {
        "arrival_definition": "first rising crossing of fixed 10 Pa; no time translation",
        "arrival_time_s": arrival,
        "expected_arrival_time_s": expected_arrival_s,
        "arrival_error_ms": arrival_error,
        "peak_pressure_pa": peak,
        "peak_relative_error": peak_error,
        "candidate_pass": arrival_error is not None
        and arrival_error <= ENGINEERING_THRESHOLDS["arrival_error_ms"]
        and peak_error <= ENGINEERING_THRESHOLDS["peak_relative_error"],
    }


def observed_orders(cells: Sequence[int], errors: Sequence[float]) -> list[float | None]:
    return [
        math.log(a / b) / math.log(n1 / n0) if a > 0 and b > 0 else None
        for n0, n1, a, b in zip(cells, cells[1:], errors, errors[1:])
    ]


def verify_boileau_data(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["original_files"]:
        data = (root / item["path"]).read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Boileau original-file identity mismatch: {item['path']}")
        if "published_md5" in item and hashlib.md5(data).hexdigest() != item["published_md5"]:
            raise ValueError(f"Boileau published MD5 mismatch: {item['path']}")
    tables = 0
    with zipfile.ZipFile(root / "Benchmark1_SinglePulseModel.zip") as archive:
        if archive.testzip() is not None:
            raise ValueError("Boileau ZIP CRC failure")
        for item in manifest["archive_members"]:
            data = archive.read(item["path"])
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError(f"Boileau member identity mismatch: {item['path']}")
            if "rows" in item:
                tables += 1
    return {
        "download_integrity": "PASS",
        "reference_table_count": tables,
        "dataset_doi": manifest["dataset_doi"],
        "archive_sha256": next(
            x["sha256"] for x in manifest["original_files"] if x["path"].endswith(".zip")
        ),
        "license": manifest["license"],
    }


def load_boileau_reference(root: Path) -> list[list[float]]:
    with zipfile.ZipFile(root / "Benchmark1_SinglePulseModel.zip") as archive:
        raw = archive.read("Benchmark1_SinglePulseModel/NumData/FVM_inviscid.txt")
    rows = [[float(v) for v in line.split()] for line in raw.decode("ascii").splitlines() if line]
    if not rows or any(len(row) != 9 for row in rows):
        raise ValueError("Expected Boileau spatial profiles with one x and eight pressure columns")
    if any(not math.isfinite(value) for row in rows for value in row):
        raise ValueError("Nonfinite Boileau reference")
    if any(a[0] >= b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError("FVM reference coordinates must be strictly increasing")
    return [[row[0], *(p * 1000 for p in row[1:])] for row in rows]


def analyze_boileau_reference(root: Path) -> dict[str, Any]:
    """Quantify differences between published schemes; keep original bytes unchanged.

    The ensemble analysis averages repeated DCG interface coordinates explicitly.
    The solver comparison itself uses the original strictly increasing FVM coordinates.
    """
    reference = load_boileau_reference(root)
    schemes: dict[str, Any] = {}
    interpolated: list[list[list[float]]] = []
    with zipfile.ZipFile(root / "Benchmark1_SinglePulseModel.zip") as archive:
        for name in ("DCG", "LCG", "FEM", "FVM", "McC", "STM"):
            raw = archive.read(f"Benchmark1_SinglePulseModel/NumData/{name}_inviscid.txt")
            rows = [[float(v) for v in line.split()] for line in raw.decode("ascii").splitlines() if line]
            unique: list[list[float]] = []
            duplicates = 0
            index = 0
            while index < len(rows):
                end = index + 1
                while end < len(rows) and rows[end][0] == rows[index][0]:
                    end += 1
                duplicates += end - index - 1
                unique.append([rows[index][0], *(sum(row[c] for row in rows[index:end]) / (end - index) * 1000 for c in range(1, 9))])
                index = end
            coordinates = [row[0] for row in unique]
            projected: list[list[float]] = []
            for source in reference:
                k = max(0, min(len(unique) - 2, bisect.bisect_right(coordinates, source[0]) - 1))
                weight = (source[0] - unique[k][0]) / (unique[k + 1][0] - unique[k][0])
                projected.append([source[0], *(unique[k][c] * (1 - weight) + unique[k + 1][c] * weight for c in range(1, 9))])
            interpolated.append(projected)
            profiles = []
            for column, t in enumerate(BOILEAU_PROFILE_TIMES_S, 1):
                errors = [abs(a[column] - b[column]) for a, b in zip(projected, reference)]
                profiles.append({"time_s": t, "max_absolute_difference_from_fvm_pa": max(errors),
                                 "rms_difference_from_fvm_pa": math.sqrt(sum(e * e for e in errors) / len(errors))})
            positive_spacing = [b[0] - a[0] for a, b in zip(unique, unique[1:])]
            schemes[name] = {"original_output_rows": len(rows), "repeated_adjacent_coordinates": duplicates,
                             "output_spacing_min_m": min(positive_spacing), "output_spacing_max_m": max(positive_spacing),
                             "profiles": profiles}
    spread = []
    for column, t in enumerate(BOILEAU_PROFILE_TIMES_S, 1):
        widths = [max(s[k][column] for s in interpolated) - min(s[k][column] for s in interpolated) for k in range(len(reference))]
        spread.append({"time_s": t, "max_ensemble_range_pa": max(widths)})
    result = {"schema": "boileau-reference-ensemble/v1", "schemes": schemes, "ensemble_spread": spread,
              "comparison_coordinates": "original FVM output centers, 0.005..9.995 m; spacing 0.01 m",
              "interpolation": "linear; duplicate DCG interface values averaged for ensemble analysis only",
              "interpretation": "Published numerical solutions differ and have finite sampling resolution; none is clinical ground truth. Output sampling spacing need not equal computational mesh spacing."}
    _write_json(root / "reference_scheme_spread.json", result)
    return result


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _progress(message: str) -> None:
    print(message, flush=True)
    if _RUN_LOG is not None:
        with _RUN_LOG.open("a", encoding="utf-8") as stream:
            stream.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")


def _snapshot_identity(output: Path) -> dict[str, Any]:
    global _PROCESS_IDENTITY
    if _PROCESS_IDENTITY is not None:
        return _PROCESS_IDENTITY
    identity = _identity()
    digest = hashlib.sha256(json.dumps(identity["source_sha256"], sort_keys=True).encode()).hexdigest()
    destination = output / "history" / f"source_{digest[:16]}"
    entries = []
    for name, expected in identity["source_sha256"].items():
        original = Path(name)
        data = original.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Source changed while freezing run identity")
        relative = original.relative_to(Path.cwd()) if original.is_absolute() else original
        target = destination / "files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != data:
            raise ValueError("Immutable source snapshot collision")
        target.write_bytes(data)
        entries.append({"original_path": name, "path": str(target.relative_to(output)), "sha256": expected})
    _write_json(destination / "manifest.json", {"source_sha256": identity["source_sha256"], "files": entries})
    identity["source_snapshot_manifest"] = str((destination / "manifest.json").relative_to(output))
    _PROCESS_IDENTITY = identity
    return identity


def _engineering_parameters(cells: int, scheme: str) -> dict[str, Any]:
    return {"length_m": 1.0, "cells": cells, "scheme": scheme, "reference_area_m2": 3e-4,
            "density_kg_m3": 1060.0, "beta_pa": 53000.0, "reference_pressure_pa": 0.0,
            "initial_flow_m3_s": 0.0, "kinematic_viscosity_m2_s": 0.0, "cfl": 0.4,
            "inlet": {"quantity": "pressure_pa", "amplitude_pa": 20.0, "start_s": 0.05,
                      "end_s": 0.09, "shape": "sine_squared; zero otherwise"}}


def _finish_run(output: Path, filename: str, result: dict[str, Any], parameters: dict[str, Any], csv_names: list[str]) -> dict[str, Any]:
    identity = _snapshot_identity(output)
    unchanged = _identity()["source_sha256"] == identity["source_sha256"]
    result.update({"identity": identity, "parameters": parameters,
                   "source_unchanged_during_run": unchanged,
                   "run_log_path": str(_RUN_LOG.relative_to(output)) if _RUN_LOG else None,
                   "csv_artifacts": [{"path": name, "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()} for name in csv_names]})
    if not unchanged:
        result["candidate_pass"] = False
        if "pass" in result:
            result["pass"] = False
        result["source_status"] = "SOURCE_CHANGED_DURING_RUN"
    path = output / filename
    _write_json(path, result)
    result["result_json"] = {"path": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


def _flow_at(segment: Any, x_m: float) -> float:
    values = segment.state.flow_m3_s
    dx = segment.config.length_m / len(values)
    coordinate = x_m / dx - 0.5
    lower = max(0, min(len(values) - 1, math.floor(coordinate)))
    upper = min(len(values) - 1, lower + 1)
    weight = min(1.0, max(0.0, coordinate - lower))
    return values[lower] * (1 - weight) + values[upper] * weight


def _engineering_segment(cells: int, scheme: str, length: float = 1.0, area: float = ENGINEERING_AREA_M2) -> Any:
    from iabp.arterial1d import Segment, SegmentConfig, TubeLaw

    law = TubeLaw(area, 53000.0, ENGINEERING_DENSITY_KG_M3, 0.0)
    return Segment(SegmentConfig(length, cells, law, cfl=0.4), scheme=scheme)


def run_matched(cells: int, scheme: str, output: Path) -> dict[str, Any]:
    from iabp.arterial1d import NonReflectingBoundary, PressureBoundary

    _snapshot_identity(output)
    _progress(f"[matched] scheme={scheme} cells={cells}")
    started = perf_counter()
    segment = _engineering_segment(cells, scheme)
    left, right = PressureBoundary(pulse_pressure_pa), NonReflectingBoundary()
    initial_volume = segment.volume_m3
    max_conservation = 0.0
    max_linear_volume_error = 0.0
    max_pressure_error = 0.0
    squared_error = 0.0
    value_count = 0
    steps = 0
    min_area = ENGINEERING_AREA_M2
    min_pressure = max_pressure = 0.0
    traces: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    width = 1.0 / cells
    for observation in range(641):
        target = observation * 0.0005
        while segment.state.time_s < target - 1e-14:
            dt = min(0.95 * segment.max_stable_dt_s(), target - segment.state.time_s)
            result = segment.step(dt, left, right)
            max_conservation = max(max_conservation, abs(result.volume_residual_m3))
            steps += 1
        pressures = segment.pressure_pa()
        min_pressure = min(min_pressure, min(pressures))
        max_pressure = max(max_pressure, max(pressures))
        max_at_time = 0.0
        for index, pressure in enumerate(pressures):
            x = (index + 0.5) * width
            expected = pulse_pressure_pa(target - x / ENGINEERING_WAVE_SPEED_M_S)
            error = pressure - expected
            max_at_time = max(max_at_time, abs(error))
            squared_error += error * error
            value_count += 1
            if observation in (200, 300, 400, 500, 600):
                profiles.append({"time_s": target, "x_m": x, "pressure_pa": pressure, "reference_pa": expected})
        max_pressure_error = max(max_pressure_error, max_at_time)
        min_area = min(min_area, min(segment.state.area_m2))
        expected_volume = (
            pressure_pulse_integral(target) - pressure_pulse_integral(target - 0.2)
        ) / ENGINEERING_Z0
        volume_error = segment.volume_m3 - initial_volume - expected_volume
        max_linear_volume_error = max(max_linear_volume_error, abs(volume_error))
        max_conservation = max(max_conservation, abs(segment.ledger.residual_m3))
        traces.append({
            "time_s": target,
            "probe_x_m": 0.5,
            "pressure_pa": segment.sample_pressure_pa(0.5),
            "reference_pa": pulse_pressure_pa(target - 0.1),
            "flow_m3_s": _flow_at(segment, 0.5),
            "spatial_max_abs_error_pa": max_at_time,
            "volume_m3": segment.volume_m3,
            "linear_volume_error_m3": volume_error,
            "conservation_residual_m3": segment.ledger.residual_m3,
        })
    result = timing_and_peak_metrics([(row["time_s"], row["pressure_pa"]) for row in traces], 0.16)
    relative_conservation = max_conservation / initial_volume
    result.update({
        "case": "engineering_matched_pressure_pulse", "cells": cells, "scheme": scheme,
        "cfl": 0.4, "dt_policy": "0.95 * max_stable_dt_s, clipped to observation time",
        "observation_interval_s": 0.0005, "spatial_pressure_max_abs_error_pa": max_pressure_error,
        "spatiotemporal_pressure_rms_error_pa": math.sqrt(squared_error / value_count),
        "max_abs_linear_volume_error_m3": max_linear_volume_error,
        "max_abs_conservation_residual_m3": max_conservation,
        "conservation_relative_initial_volume": relative_conservation,
        "conservation_pass": relative_conservation <= ENGINEERING_THRESHOLDS["conservation_relative_initial_volume"],
        "minimum_area_m2": min_area, "steps": steps, "wall_seconds": perf_counter() - started,
        "min_pressure_pa": min_pressure, "max_pressure_pa": max_pressure,
        "relative_reference_peak_overshoot": max(0.0, max_pressure / PULSE_PEAK_PA - 1),
        "relative_reference_peak_undershoot": max(0.0, -min_pressure / PULSE_PEAK_PA),
        "scheme_scope": "smooth small-amplitude only; non-TVD; not a shock test" if scheme == "linear3_ssprk3" else "baseline or TVD limited separate comparison",
        "trace_csv": f"matched_{scheme}_{cells}_trace.csv", "profile_csv": f"matched_{scheme}_{cells}_profiles.csv",
    })
    _write_csv(output / result["trace_csv"], traces)
    _write_csv(output / result["profile_csv"], profiles)
    _progress(f"  peak_error={result['peak_relative_error']:.6g}, arrival_ms={result['arrival_error_ms']}, candidate={result['candidate_pass']}")
    return _finish_run(output, f"matched_{scheme}_{cells}.json", result, _engineering_parameters(cells, scheme), [result["trace_csv"], result["profile_csv"]])


def run_reflection(cells: int, kind: str, output: Path) -> dict[str, Any]:
    from iabp.arterial1d import ClosedBoundary, PressureBoundary, ResistanceBoundary

    expected = {"closed": 1.0, "pressure_release": -1.0, "resistance_2z0": 1 / 3}[kind]
    right = {
        "closed": ClosedBoundary(), "pressure_release": PressureBoundary(0.0),
        "resistance_2z0": ResistanceBoundary(2 * ENGINEERING_Z0),
    }[kind]
    scheme = "muscl_ssprk2"
    _snapshot_identity(output)
    _progress(f"[reflection] kind={kind} cells={cells}")
    started = perf_counter()
    segment = _engineering_segment(cells, scheme)
    rows: list[dict[str, Any]] = []
    for index in range(841):
        target = index * 0.0005
        while segment.state.time_s < target - 1e-14:
            dt = min(0.95 * segment.max_stable_dt_s(), target - segment.state.time_s)
            segment.step(dt, PressureBoundary(pulse_pressure_pa), right)
        p, q = segment.sample_pressure_pa(0.75), _flow_at(segment, 0.75)
        rows.append({"time_s": target, "pressure_pa": p, "flow_m3_s": q,
                     "forward_pressure_pa": (p + ENGINEERING_Z0 * q) / 2,
                     "backward_pressure_pa": (p - ENGINEERING_Z0 * q) / 2})
    incident_peak = max(row["forward_pressure_pa"] for row in rows if 0.17 <= row["time_s"] <= 0.27)
    reflected = [row["backward_pressure_pa"] for row in rows if 0.27 <= row["time_s"] <= 0.39]
    reflected_peak = min(reflected) if expected < 0 else max(reflected)
    coefficient = reflected_peak / incident_peak
    error = abs(coefficient - expected)
    conservation = abs(segment.ledger.residual_m3) / segment.ledger.initial_volume_m3
    result = {
        "case": kind, "cells": cells, "scheme": scheme, "probe_x_m": 0.75,
        "coefficient_definition": "signed peak p- in fixed reflected window / peak p+ in fixed incident window",
        "incident_window_s": [0.17, 0.27], "reflected_window_s": [0.27, 0.39],
        "expected_coefficient": expected, "measured_coefficient": coefficient,
        "coefficient_absolute_error": error,
        "conservation_relative_initial_volume": conservation,
        "pass": error <= ENGINEERING_THRESHOLDS["reflection_coefficient_absolute_error"]
        and conservation <= ENGINEERING_THRESHOLDS["conservation_relative_initial_volume"],
        "wall_seconds": perf_counter() - started, "trace_csv": f"reflection_{kind}_{cells}.csv",
    }
    _write_csv(output / result["trace_csv"], rows)
    result["max_abs_conservation_residual_m3"] = abs(segment.ledger.residual_m3)
    result["integrated_left_inflow_m3"] = segment.ledger.left_inflow_m3
    result["integrated_right_outflow_m3"] = segment.ledger.right_outflow_m3
    parameters = _engineering_parameters(cells, scheme)
    parameters["outlet"] = {"type": kind, "expected_linear_reflection": expected}
    if kind == "resistance_2z0":
        parameters["outlet"]["resistance_pa_s_m3"] = 2 * ENGINEERING_Z0
    _progress(f"  gamma={coefficient:.8g}, abs_error={error:.6g}, pass={result['pass']}")
    return _finish_run(output, f"reflection_{kind}_{cells}.json", result, parameters, [result["trace_csv"]])


def run_junction(cells: int, output: Path) -> dict[str, Any]:
    from iabp.arterial1d import Junction, Network, NonReflectingBoundary, PressureBoundary

    _snapshot_identity(output)
    _progress(f"[junction] symmetric cells_per_segment={cells}")
    started = perf_counter()
    segments = {
        "parent": _engineering_segment(cells, "muscl_ssprk2", 0.5),
        "child1": _engineering_segment(cells, "muscl_ssprk2", 0.5, ENGINEERING_AREA_M2 / 2),
        "child2": _engineering_segment(cells, "muscl_ssprk2", 0.5, ENGINEERING_AREA_M2 / 2),
    }
    network = Network(segments, {
        ("parent", "left"): PressureBoundary(pulse_pressure_pa),
        ("child1", "right"): NonReflectingBoundary(),
        ("child2", "right"): NonReflectingBoundary(),
    }, (Junction("parent", ("child1", "child2")),))
    initial_volume = network.volume_m3
    parent_volume = child1_volume = child2_volume = 0.0
    max_interface_balance = max_network_residual = 0.0
    rows: list[dict[str, Any]] = []
    for index in range(641):
        target = index * 0.0005
        while segments["parent"].state.time_s < target - 1e-14:
            dt = min(0.95 * network.max_stable_dt_s(), target - segments["parent"].state.time_s)
            step = network.step(dt)
            parent_flux = step.segments["parent"].right_volume_m3
            first_flux = step.segments["child1"].left_volume_m3
            second_flux = step.segments["child2"].left_volume_m3
            parent_volume += parent_flux
            child1_volume += first_flux
            child2_volume += second_flux
            max_interface_balance = max(max_interface_balance, abs(parent_flux - first_flux - second_flux))
            max_network_residual = max(max_network_residual, abs(step.volume_residual_m3), abs(network.ledger.residual_m3))
        p = segments["parent"].sample_pressure_pa(0.375)
        q = _flow_at(segments["parent"], 0.375)
        rows.append({"time_s": target, "parent_pressure_pa": p, "parent_flow_m3_s": q,
                     "parent_forward_pressure_pa": (p + ENGINEERING_Z0 * q) / 2,
                     "parent_backward_pressure_pa": (p - ENGINEERING_Z0 * q) / 2,
                     "child1_pressure_pa": segments["child1"].sample_pressure_pa(0.125),
                     "child2_pressure_pa": segments["child2"].sample_pressure_pa(0.125)})
    total_child = child1_volume + child2_volume
    split = child1_volume / total_child
    backward = max(abs(row["parent_backward_pressure_pa"]) for row in rows)
    forward = max(row["parent_forward_pressure_pa"] for row in rows)
    ratio = backward / forward
    conservation = max_network_residual / initial_volume
    result = {
        "case": "symmetric_static_pressure_junction", "cells_per_segment": cells,
        "scheme": "muscl_ssprk2", "junction_model": "common static pressure; no kinetic/local losses",
        "parent_integrated_outflow_m3": parent_volume, "child1_integrated_inflow_m3": child1_volume,
        "child2_integrated_inflow_m3": child2_volume, "child1_fraction": split,
        "child2_fraction": 1 - split, "symmetric_split_absolute_error": abs(split - 0.5),
        "parent_backward_forward_peak_ratio": ratio,
        "max_single_step_interface_volume_mismatch_m3": max_interface_balance,
        "integrated_interface_volume_mismatch_m3": parent_volume - total_child,
        "conservation_relative_initial_volume": conservation,
        "pass": abs(split - 0.5) <= ENGINEERING_THRESHOLDS["symmetric_split_absolute_error"]
        and ratio <= ENGINEERING_THRESHOLDS["junction_backward_forward_peak_ratio"]
        and conservation <= ENGINEERING_THRESHOLDS["conservation_relative_initial_volume"],
        "wall_seconds": perf_counter() - started, "trace_csv": f"junction_symmetric_{cells}.csv",
    }
    _write_csv(output / result["trace_csv"], rows)
    result["max_abs_conservation_residual_m3"] = max_network_residual
    parameters = _engineering_parameters(cells, "muscl_ssprk2")
    parameters.update({"length_m": 0.5, "daughter_length_m": 0.5,
                       "daughter_reference_area_m2": ENGINEERING_AREA_M2 / 2,
                       "outlets": "two nonreflecting", "junction": "common static pressure"})
    _progress(f"  split={split:.8g}, backward_ratio={ratio:.6g}, pass={result['pass']}")
    return _finish_run(output, f"junction_symmetric_{cells}.json", result, parameters, [result["trace_csv"]])


def run_boileau(cells: int, scheme: str, output: Path) -> dict[str, Any]:
    from iabp.arterial1d import FlowBoundary, NonReflectingBoundary, Segment, SegmentConfig, TubeLaw

    _snapshot_identity(output)
    _progress(f"[Boileau inviscid] scheme={scheme} cells={cells}")
    started = perf_counter()
    root = output / "external" / "boileau2015"
    identity = verify_boileau_data(root)
    config = json.loads((root / "case1_source_config.json").read_text(encoding="utf-8"))
    law = TubeLaw(config["reference_area_m2"], config["module_beta_pa"], config["density_kg_m3"], 0.0)
    segment = Segment(SegmentConfig(10.0, cells, law, cfl=0.4), scheme=scheme)
    inlet = FlowBoundary(lambda t: 1e-6 * math.exp(-10000 * (t - 0.05) ** 2))
    outlet = NonReflectingBoundary()
    reference = load_boileau_reference(root)
    profile_rows: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    steps = 0
    max_conservation = 0.0
    for column, target in enumerate(BOILEAU_PROFILE_TIMES_S, 1):
        while segment.state.time_s < target - 1e-14:
            dt = min(0.95 * segment.max_stable_dt_s(), target - segment.state.time_s)
            step = segment.step(dt, inlet, outlet)
            max_conservation = max(max_conservation, abs(step.volume_residual_m3), abs(segment.ledger.residual_m3))
            steps += 1
        calculated = [segment.sample_pressure_pa(row[0]) for row in reference]
        all_pressures = segment.pressure_pa()
        errors = [a - row[column] for a, row in zip(calculated, reference)]
        reference_peak = max(row[column] for row in reference)
        numeric_peak = max(calculated)
        numeric_x = reference[max(range(len(reference)), key=lambda k: calculated[k])][0]
        reference_x = max(reference, key=lambda row: row[column])[0]
        metrics.append({"time_s": target, "max_abs_error_pa": max(abs(e) for e in errors),
                        "rms_error_pa": math.sqrt(sum(e * e for e in errors) / len(errors)),
                        "reference_peak_pa": reference_peak, "calculated_peak_pa": numeric_peak,
                        "peak_relative_error": abs(numeric_peak - reference_peak) / reference_peak,
                        "peak_position_difference_m": numeric_x - reference_x,
                        "min_pressure_pa": min(all_pressures), "max_pressure_pa": max(all_pressures),
                        "relative_reference_peak_overshoot": max(0.0, max(all_pressures) / reference_peak - 1),
                        "relative_reference_peak_undershoot": max(0.0, -min(all_pressures) / reference_peak),
                        "minimum_area_m2": min(segment.state.area_m2)})
        profile_rows.extend({"time_s": target, "x_m": row[0], "pressure_pa": pressure,
                             "reference_pa": row[column], "error_pa": error}
                            for row, pressure, error in zip(reference, calculated, errors))
        _progress(f"  t={target:.1f}s max_error={metrics[-1]['max_abs_error_pa']:.6g} Pa min={min(all_pressures):.6g} max={max(all_pressures):.6g} Pa")
    result = {
        "case": "boileau2015_single_pulse_inviscid", "cells": cells, "scheme": scheme,
        "cfl": 0.4, "identity": identity, "reference_method": "published FVM spatial pressure profiles",
        "reference_pressure_unit": "kPa converted to Pa", "temporal_alignment": "none",
        "spatial_comparison": "core linear sampling at original FVM cell centers; no shift",
        "profiles": metrics, "spatial_pressure_max_abs_error_pa": max(row["max_abs_error_pa"] for row in metrics),
        "maximum_peak_relative_error": max(row["peak_relative_error"] for row in metrics),
        "relative_max_profile_error": max(row["max_abs_error_pa"] / row["reference_peak_pa"] for row in metrics),
        "maximum_peak_position_absolute_difference_m": max(abs(row["peak_position_difference_m"]) for row in metrics),
        "conservation_relative_initial_volume": max_conservation / segment.ledger.initial_volume_m3,
        "max_abs_conservation_residual_m3": max_conservation,
        "min_pressure_pa": min(row["min_pressure_pa"] for row in metrics),
        "max_pressure_pa": max(row["max_pressure_pa"] for row in metrics),
        "relative_reference_peak_overshoot": max(row["relative_reference_peak_overshoot"] for row in metrics),
        "relative_reference_peak_undershoot": max(row["relative_reference_peak_undershoot"] for row in metrics),
        "scheme_scope": "smooth small-amplitude only; non-TVD; not a shock test" if scheme == "linear3_ssprk3" else "TVD limited separate comparison",
        "steps": steps, "wall_seconds": perf_counter() - started,
        "viscous_case_status": "NOT_REPRODUCED_DIFFERENT_FRICTION_COEFFICIENT",
        "profile_csv": f"boileau_{scheme}_{cells}_profiles.csv",
    }
    result["candidate_pass"] = (
        result["relative_max_profile_error"] <= BOILEAU_THRESHOLDS["relative_max_profile_error"]
        and result["maximum_peak_relative_error"] <= BOILEAU_THRESHOLDS["maximum_peak_relative_error"]
        and result["maximum_peak_position_absolute_difference_m"] <= BOILEAU_THRESHOLDS["peak_position_absolute_difference_m"]
        and result["conservation_relative_initial_volume"] <= BOILEAU_THRESHOLDS["conservation_relative_initial_volume"]
    )
    result["numerical_reproduction_status"] = "PASS_DECLARED_ENGINEERING_TOLERANCE" if result["candidate_pass"] else "ACCURACY_NOT_MET"
    _write_csv(output / result["profile_csv"], profile_rows)
    parameters = dict(config)
    parameters.update({"cells": cells, "scheme": scheme, "cfl": 0.4,
                       "source_config_sha256": hashlib.sha256((root / "case1_source_config.json").read_bytes()).hexdigest()})
    return _finish_run(output, f"boileau_{scheme}_{cells}.json", result, parameters, [result["profile_csv"]])


def _convergence_metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    cells = [row["cells"] for row in runs]
    arrival = [row["arrival_error_ms"] for row in runs]
    return {
        "pressure_max_error_orders": observed_orders(cells, [r["spatial_pressure_max_abs_error_pa"] for r in runs]),
        "peak_relative_error_orders": observed_orders(cells, [r["peak_relative_error"] for r in runs]),
        "arrival_error_orders": observed_orders(cells, arrival) if all(x is not None for x in arrival) else None,
        "linear_volume_error_orders": observed_orders(cells, [r["max_abs_linear_volume_error_m3"] for r in runs]),
        "roundoff_balance_order": "not interpreted as truncation error convergence",
    }


def collect_existing(output: Path) -> dict[str, Any]:
    """Evidence gate only: validate current runs and retain frozen historical controls."""
    identity = _identity()
    reports = {name: json.loads((output / f"benchmark_{name}.json").read_text(encoding="utf-8"))
               for name in ("linear3_matched", "reflections", "junction", "linear3_boileau")}
    runs_by_case = {
        "linear3_matched": reports["linear3_matched"]["linear3_matched"],
        "reflections": [run for case in reports["reflections"]["reflections"] for run in case["runs"]],
        "junction": reports["junction"]["junction"]["runs"],
        "linear3_boileau": reports["linear3_boileau"]["linear3_boileau"],
    }
    for name, report in reports.items():
        _verify_report(output, name, report, runs_by_case[name], identity)
    history_root = output / "history" / "pre_linear3"
    history_manifest = json.loads((history_root / "manifest.json").read_text(encoding="utf-8"))
    for item in history_manifest["files"]:
        if hashlib.sha256((history_root / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Historical artifact changed: {item['path']}")
    historical_matched = json.loads((history_root / "benchmark_matched.json").read_text(encoding="utf-8"))["matched"]
    historical_boileau = json.loads((history_root / "benchmark_boileau.json").read_text(encoding="utf-8"))["boileau"]
    current_matched = reports["linear3_matched"]["linear3_matched"]
    if [run["cells"] for run in current_matched[:3]] != [80, 160, 320]:
        raise ValueError("Current matched candidate requires at least the declared 80/160/320 grids")
    current_public = reports["linear3_boileau"]["linear3_boileau"]
    if [run["cells"] for run in current_public[:3]] != [640, 1280, 2560]:
        raise ValueError("Current public candidate requires at least the declared 640/1280/2560 grids")
    public_identity = verify_boileau_data(output / "external" / "boileau2015")
    summary: dict[str, Any] = {
        "schema": "arterial1d-benchmark/v1", "identity": identity,
        "thresholds_declared_before_runs": ENGINEERING_THRESHOLDS,
        "boileau_thresholds_declared_before_runs": BOILEAU_THRESHOLDS,
        "scope": "independent uniform vessels; no heart, balloon, clinical calibration or event accuracy claim",
        "alignment": "none", "mode": "EVIDENCE_GATE_NO_SOLVER_RUN",
        "selected_case": "current_candidates_and_explicit_historical_controls",
        "source_reports": {name: {"path": f"benchmark_{name}.json", "sha256": hashlib.sha256((output / f"benchmark_{name}.json").read_bytes()).hexdigest(), "identity": report["identity"], "run_log": report["run_log"]} for name, report in reports.items()},
        "historical_controls": {"path": "history/pre_linear3/manifest.json", "sha256": hashlib.sha256((history_root / "manifest.json").read_bytes()).hexdigest(), "current_core_coverage": False},
        "matched": {"first_order_baseline": historical_matched["first_order_baseline"],
                    "high_order_separate_comparison": historical_matched["high_order_separate_comparison"],
                    "linear3_current_comparison": current_matched,
                    "historical_core_coverage": "Frozen pre-linear3 source only; never counted as current-core runs",
                    "candidate_pass": current_matched[-1]["candidate_pass"] and current_matched[-1]["conservation_pass"]},
        "reflections": reports["reflections"]["reflections"],
        "junction": reports["junction"]["junction"], "boileau": current_public,
        "boileau_historical_muscl": historical_boileau,
        "public_data_identity": public_identity,
        "boileau_reference_ensemble": analyze_boileau_reference(output / "external" / "boileau2015"),
        "boileau_pressure_error_orders": observed_orders([r["cells"] for r in current_public], [r["spatial_pressure_max_abs_error_pa"] for r in current_public]),
        "wall_seconds": sum(report["wall_seconds"] for report in reports.values()),
    }
    summary["matched"]["first_order_convergence"] = _convergence_metrics(summary["matched"]["first_order_baseline"])
    summary["matched"]["high_order_convergence"] = _convergence_metrics(summary["matched"]["high_order_separate_comparison"])
    summary["matched"]["linear3_convergence"] = _convergence_metrics(current_matched)
    engineering = summary["matched"]["candidate_pass"] and summary["junction"]["candidate_pass"] and all(row["candidate_pass"] for row in summary["reflections"])
    public = summary["boileau"][-1]["candidate_pass"]
    summary["engineering_status"] = "PASS" if engineering else "FAIL"
    summary["public_benchmark_status"] = summary["boileau"][-1]["numerical_reproduction_status"]
    summary["overall_status"] = "PASS_DECLARED_CHECKS" if engineering and public else "FAIL"
    _write_json(output / "benchmark_summary.json", summary)
    return summary


def _verify_report(output: Path, name: str, report: dict[str, Any], runs: list[dict[str, Any]], identity: dict[str, Any]) -> None:
    if report["identity"]["source_sha256"] != identity["source_sha256"]:
        raise ValueError(f"Current source identity changed since {name}; this is not current-core coverage")
    if report["thresholds_declared_before_runs"] != ENGINEERING_THRESHOLDS or report["boileau_thresholds_declared_before_runs"] != BOILEAU_THRESHOLDS:
        raise ValueError(f"Predeclared thresholds changed since {name}")
    log = report["run_log"]
    if hashlib.sha256((output / log["path"]).read_bytes()).hexdigest() != log["sha256"]:
        raise ValueError(f"Original run log changed since {name}")
    snapshot_path = report["identity"]["source_snapshot_manifest"]
    snapshot = json.loads((output / snapshot_path).read_text(encoding="utf-8"))
    if snapshot["source_sha256"] != identity["source_sha256"]:
        raise ValueError(f"Source snapshot identity mismatch for {name}")
    for item in snapshot["files"]:
        if hashlib.sha256((output / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Source snapshot bytes changed: {item['path']}")
    for run in runs:
        if run["identity"]["source_sha256"] != identity["source_sha256"] or not run["source_unchanged_during_run"]:
            raise ValueError(f"Run source was unstable in {name}")
        artifact = run["result_json"]
        data = (output / artifact["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            raise ValueError(f"Run result changed: {artifact['path']}")
        if json.loads(data) != {key: value for key, value in run.items() if key != "result_json"}:
            raise ValueError(f"Suite does not match its original run result: {artifact['path']}")
        for item in run["csv_artifacts"]:
            if hashlib.sha256((output / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError(f"Run CSV changed: {item['path']}")
        if run.get("case") == "boileau2015_single_pulse_inviscid":
            source = output / "external" / "boileau2015" / "case1_source_config.json"
            if hashlib.sha256(source.read_bytes()).hexdigest() != run["parameters"]["source_config_sha256"]:
                raise ValueError("Boileau source configuration changed")


def _identity() -> dict[str, Any]:
    files = [Path(__file__), *sorted(Path("iabp/arterial1d").glob("*.py"))]
    return {"python_executable": sys.executable, "python_version": platform.python_version(),
            "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}


def plot_existing(output: Path) -> None:
    """Optional publication-style evidence figures from already saved CSV, without solver calls."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    matched = sorted(output.glob("matched_*_trace.csv"))
    for path in matched:
        with path.open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        label = path.stem.removeprefix("matched_").removesuffix("_trace")
        axes[0].plot([float(row["time_s"]) for row in rows], [float(row["pressure_pa"]) for row in rows], label=label, linewidth=1)
    if matched:
        axes[0].plot([float(row["time_s"]) for row in rows], [float(row["reference_pa"]) for row in rows], "k--", label="linear truth", linewidth=1.5)
    axes[0].set(xlabel="Time (s)", ylabel="Pressure (Pa)", title="Matched tube: x = 0.5 m")
    axes[0].legend(fontsize=6)
    for path in sorted(output.glob("boileau_*_profiles.csv")):
        with path.open(encoding="utf-8") as stream:
            data = [row for row in csv.DictReader(stream) if float(row["time_s"]) == 1.5]
        axes[1].plot([float(row["x_m"]) for row in data], [float(row["pressure_pa"]) for row in data], label=path.stem.removeprefix("boileau_").removesuffix("_profiles"), linewidth=1)
    if list(output.glob("boileau_*_profiles.csv")):
        axes[1].plot([float(row["x_m"]) for row in data], [float(row["reference_pa"]) for row in data], "k--", label="Boileau FVM", linewidth=1.5)
    axes[1].set(xlabel="Distance (m)", ylabel="Pressure (Pa)", title="Public single pulse: t = 1.5 s", xlim=(8.2, 9.8))
    axes[1].legend(fontsize=7)
    for axis in axes:
        axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(output / "propagation_comparison.png", dpi=180)
    figure.savefig(output / "propagation_comparison.svg")
    plt.close(figure)
    _write_json(output / "plot_runtime.json", {"python_executable": sys.executable, "python_version": platform.python_version(), "matplotlib": matplotlib.__version__, "backend": "Agg", "inputs": "existing benchmark CSV only; no generated physical waveforms"})


def _run_case(case: str, output: Path) -> dict[str, Any]:
    global _RUN_LOG
    (output / "run_logs").mkdir(parents=True, exist_ok=True)
    _RUN_LOG = output / "run_logs" / f"{case}_{uuid.uuid4().hex[:12]}.log"
    _progress(f"[start] case={case}; argv={sys.argv!r}; mode=ACTUAL_SOLVER_RUN")
    identity = _snapshot_identity(output)
    started = perf_counter()
    summary: dict[str, Any] = {
        "schema": "arterial1d-benchmark/v1", "identity": identity,
        "thresholds_declared_before_runs": ENGINEERING_THRESHOLDS,
        "boileau_thresholds_declared_before_runs": BOILEAU_THRESHOLDS,
        "scope": "independent uniform vessels; no heart, balloon, clinical calibration or event accuracy claim",
        "alignment": "none", "selected_case": case, "mode": "ACTUAL_SOLVER_RUN",
    }
    engineering_checks: list[bool] = []
    public_checks: list[bool] = []
    if case == "matched":
        first = [run_matched(n, "rusanov", output) for n in (80, 160, 320)]
        high = [run_matched(n, "muscl_ssprk2", output) for n in (80, 160, 320)]
        for n in (640, 1280):
            if high[-1]["candidate_pass"] and high[-1]["conservation_pass"]:
                break
            high.append(run_matched(n, "muscl_ssprk2", output))
        summary["matched"] = {"first_order_baseline": first, "high_order_separate_comparison": high,
            "first_order_convergence": _convergence_metrics(first), "high_order_convergence": _convergence_metrics(high),
            "candidate_pass": high[-1]["candidate_pass"] and high[-1]["conservation_pass"]}
        engineering_checks.append(summary["matched"]["candidate_pass"])
    if case == "linear3_matched":
        runs = [run_matched(n, "linear3_ssprk3", output) for n in (80, 160, 320)]
        for n in (640, 1280):
            if runs[-1]["candidate_pass"] and runs[-1]["conservation_pass"]:
                break
            runs.append(run_matched(n, "linear3_ssprk3", output))
        summary["linear3_matched"] = runs
        summary["linear3_convergence"] = _convergence_metrics(runs)
        engineering_checks.append(runs[-1]["candidate_pass"] and runs[-1]["conservation_pass"])
    if case == "reflections":
        summary["reflections"] = []
        for kind in ("closed", "pressure_release", "resistance_2z0"):
            runs = [run_reflection(n, kind, output) for n in (80, 160, 320)]
            summary["reflections"].append({"case": kind, "runs": runs,
                "coefficient_error_orders": observed_orders([r["cells"] for r in runs], [r["coefficient_absolute_error"] for r in runs]),
                "candidate_pass": runs[-1]["pass"]})
        engineering_checks.extend(row["candidate_pass"] for row in summary["reflections"])
    if case == "junction":
        runs = [run_junction(n, output) for n in (40, 80, 160)]
        summary["junction"] = {"runs": runs,
            "backward_ratio_orders": observed_orders([r["cells_per_segment"] for r in runs], [r["parent_backward_forward_peak_ratio"] for r in runs]),
            "candidate_pass": runs[-1]["pass"]}
        engineering_checks.append(summary["junction"]["candidate_pass"])
    if case in ("boileau", "linear3_boileau"):
        summary["boileau_reference_ensemble"] = analyze_boileau_reference(output / "external" / "boileau2015")
        scheme = "linear3_ssprk3" if case == "linear3_boileau" else "muscl_ssprk2"
        runs = [run_boileau(n, scheme, output) for n in (640, 1280, 2560)]
        if case == "linear3_boileau":
            for n in (3840, 5120):
                if runs[-1]["candidate_pass"]:
                    break
                runs.append(run_boileau(n, scheme, output))
        summary[case] = runs
        summary["boileau_pressure_error_orders"] = observed_orders([x["cells"] for x in runs], [x["spatial_pressure_max_abs_error_pa"] for x in runs])
        summary["public_benchmark_status"] = runs[-1]["numerical_reproduction_status"]
        public_checks.append(runs[-1]["candidate_pass"])
    summary["wall_seconds"] = perf_counter() - started
    summary["engineering_status"] = ("PASS" if all(engineering_checks) else "FAIL") if engineering_checks else "NOT_RUN"
    summary.setdefault("public_benchmark_status", "NOT_RUN")
    checks = engineering_checks + public_checks
    summary["overall_status"] = "PASS_DECLARED_CHECKS" if checks and all(checks) else "FAIL"
    _progress(f"[complete] engineering={summary['engineering_status']}; public={summary['public_benchmark_status']}; overall={summary['overall_status']}")
    summary["run_log"] = {"path": str(_RUN_LOG.relative_to(output)), "sha256": hashlib.sha256(_RUN_LOG.read_bytes()).hexdigest()}
    _write_json(output / f"benchmark_{case}.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/arterial1d"))
    parser.add_argument("--plot-only", action="store_true", help="optional matplotlib; saved CSV only")
    parser.add_argument("--collect", "--aggregate-only", action="store_true", help="evidence gate only; never run the solver")
    parser.add_argument("--case", choices=("all", "matched", "linear3_matched", "reflections", "junction", "boileau", "linear3_boileau"), default="all")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.plot_only:
        plot_existing(args.output)
        return 0
    if args.collect:
        summary = collect_existing(args.output)
        print(f"[collected: NO_SOLVER_RUN] engineering={summary['engineering_status']}; public={summary['public_benchmark_status']}", flush=True)
        return 0 if summary["overall_status"] == "PASS_DECLARED_CHECKS" else 1
    if args.case == "all":
        for case in ("linear3_matched", "reflections", "junction", "linear3_boileau"):
            _run_case(case, args.output)
        summary = collect_existing(args.output)
    else:
        summary = _run_case(args.case, args.output)
    return 0 if summary["overall_status"] == "PASS_DECLARED_CHECKS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        _progress(f"[FAILED] {type(error).__name__}: {error}")
        raise
