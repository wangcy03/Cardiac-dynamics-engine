"""Publish the fixed offline observer from recorded exports, without a solver."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "cardiac-observer/v1"
IMPLEMENTATION_FILES = (
    "tools/viewer.py", "tools/viewer_data.py", "viewer/index.html",
    "viewer/viewer.js", "viewer/viewer.css",
)
DEMO_FILES = (
    "provenance.json", "baseline_truth.csv", "baseline_samples.csv",
    "baseline_events.json", "baseline_commands.json", "assisted_truth.csv",
    "assisted_samples.csv", "assisted_events.json", "assisted_commands.json",
)


def encoded_bundle(bundle: dict[str, Any]) -> str:
    """Preserve numerical precision and prevent closing an HTML script element."""
    if bundle.get("schema") != SCHEMA:
        raise ValueError("Unsupported observer schema")
    if not isinstance(bundle.get("run"), dict) or not bundle["run"].get("id"):
        raise ValueError("Observer bundle needs a run ID")
    return (json.dumps(bundle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def write_viewer(path: Path, bundle: dict[str, Any], *, assets: Path | None = None) -> None:
    """Inline the one maintained HTML/CSS/JS implementation for a portable copy."""
    assets = assets or ROOT / "viewer"
    template = (assets / "index.html").read_text(encoding="utf-8")
    if 'href="../docs/' in template:
        docs = assets.resolve().parent / "docs"
        try:
            docs_prefix = Path(os.path.relpath(docs, path.resolve().parent)).as_posix()
        except ValueError:
            # A user-selected export on another Windows drive cannot be relative.
            docs_prefix = docs.as_uri()
        template = template.replace('href="../docs/', f'href="{docs_prefix}/')
    replacements = {
        "__BUNDLE__": encoded_bundle(bundle),
        '<link rel="stylesheet" href="viewer.css">':
            "<style>\n" + (assets / "viewer.css").read_text(encoding="utf-8") + "\n</style>",
        '<script src="viewer.js"></script>':
            "<script>\n" + (assets / "viewer.js").read_text(encoding="utf-8") + "\n</script>",
    }
    for marker, replacement in replacements.items():
        if template.count(marker) != 1:
            raise ValueError(f"Fixed viewer template needs exactly one {marker!r}")
        template = template.replace(marker, replacement)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template, encoding="utf-8")


def freeze_bundle(root: Path, bundle: dict[str, Any], run_dir: Path) -> Path:
    """Save an exclusive, verifiable raw snapshot; an existing run is never replaced."""
    root = root.resolve()
    run_dir = run_dir.resolve()
    if not run_dir.is_relative_to(root / "artifacts/runs"):
        raise ValueError("Frozen runs must stay within artifacts/runs")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", run_dir.name):
        raise ValueError("Invalid frozen run directory name")
    serialized = encoded_bundle(bundle)
    sources = []
    for record in bundle["run"].get("files", []):
        name = record.get("path")
        if not isinstance(name, str):
            raise ValueError("Raw snapshot file path is missing")
        source = (root / name).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError(f"Raw source is outside the project or missing: {name}")
        relative = source.relative_to(root)
        digest = sha256(source.read_bytes()).hexdigest()
        if digest != record.get("sha256"):
            raise ValueError(f"Raw source changed before freeze: {name}")
        sources.append((source, relative, digest))
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "schema": "cardiac-observer-frozen-run/v1", "status": "INCOMPLETE",
        "run_id": bundle["run"]["id"], "raw_files": [],
    }
    implementation = {}
    for name in IMPLEMENTATION_FILES:
        source = root / name
        if source.is_file():
            raw = source.read_bytes()
            implementation[name] = (raw, sha256(raw).hexdigest())
    manifest_path = run_dir / "manifest.json"
    try:
        for name, (raw, digest) in implementation.items():
            target = run_dir / "implementation" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        manifest["observer_implementation_sha256"] = {
            name: digest for name, (_, digest) in implementation.items()
        }
        for source, relative, digest in sources:
            target = run_dir / "raw" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Raw source changed while copying: {relative}")
            manifest["raw_files"].append({
                "original_path": relative.as_posix(),
                "path": target.relative_to(run_dir).as_posix(), "sha256": digest,
                "bytes": target.stat().st_size,
            })
        data_path = run_dir / "viewer_bundle.json"
        data_path.write_text(serialized + "\n", encoding="utf-8")
        manifest["bundle"] = {
            "path": data_path.name, "sha256": sha256(data_path.read_bytes()).hexdigest(),
        }
        manifest["status"] = "FROZEN_RECORDED_EXPORTS"
    except Exception as error:
        manifest["error"] = str(error)
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    return run_dir


def refresh_viewer(
    root: Path, *, demo_dir: Path | None = None, arterial_dir: Path | None = None,
    run_id: str | None = None, label: str = "当前模型 · 真实导出", freeze: bool = True,
    output: Path | None = None, imported_from_git: dict[str, Any] | None = None,
    comparison_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bundle, optionally archive raw inputs, then refresh the familiar entry."""
    from tools.viewer_data import build_bundle

    root = root.resolve()
    run_id = run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    demo_dir = demo_dir or root / "artifacts/demo"
    arterial_dir = arterial_dir or root / "artifacts/arterial1d"
    bundle = build_bundle(root, demo_dir, arterial_dir, run_id, label)
    if imported_from_git:
        bundle["run"]["imported_from_git"] = imported_from_git
        bundle["warnings"].append(
            "历史导出从已注明的 Git 提交按原字节提取；该提交是归档位置，不是已记录的运行 Git 身份。"
        )
    output = (output or root / "artifacts/demo/prototype_viewer.html").resolve()
    if output.suffix.lower() != ".html" or output == ROOT / "viewer/index.html":
        raise ValueError("Portable output must be a separate .html file")
    if output.is_relative_to(root / "artifacts/runs"):
        raise ValueError("Observer output must not modify a frozen run directory")
    protected = {(root / item["path"]).resolve() for item in bundle["run"].get("files", [])}
    if output in protected or output.parent / "viewer_bundle.json" in protected:
        raise ValueError("Observer output must not overwrite an input")
    if freeze:
        freeze_bundle(root, bundle, root / "artifacts/runs" / run_id)
    displayed = bundle
    if comparison_baseline is not None:
        encoded_bundle(comparison_baseline)
        displayed = {**bundle, "comparison_baseline": comparison_baseline}
    write_viewer(output, displayed)
    (output.parent / "viewer_bundle.json").write_text(encoded_bundle(bundle) + "\n", encoding="utf-8")
    return bundle


def materialize_git_demo(root: Path, ref: str, destination: Path) -> str:
    """Read only the nine known raw demo files from a local commit; never switch Git."""
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", ref + "^{commit}"], cwd=root, text=True,
    ).strip()
    content = {
        name: subprocess.check_output(["git", "show", f"{commit}:artifacts/demo/{name}"], cwd=root)
        for name in DEMO_FILES
    }
    destination = destination.resolve()
    if not destination.is_relative_to(root.resolve() / "artifacts/local_viewer_import"):
        raise ValueError("Historical import staging must stay inside artifacts/local_viewer_import")
    destination.mkdir(parents=True, exist_ok=False)
    for name, raw in content.items():
        (destination / name).write_bytes(raw)
    return commit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--demo-dir", type=Path)
    parser.add_argument("--arterial-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--label", default="当前模型 · 真实导出")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--comparison", type=Path, help="Frozen baseline JSON to preload in the UI")
    parser.add_argument("--no-freeze", action="store_true", help="Refresh a preview without an archive")
    args = parser.parse_args()
    root = args.root.resolve()

    def relative(value: Path | None) -> Path | None:
        return None if value is None else root / value

    bundle = refresh_viewer(
        root, demo_dir=relative(args.demo_dir), arterial_dir=relative(args.arterial_dir),
        run_id=args.run_id, label=args.label, freeze=not args.no_freeze,
        output=relative(args.output),
        comparison_baseline=(json.loads((root / args.comparison).read_text(encoding="utf-8"))
                             if args.comparison else None),
    )
    print(json.dumps({"run_id": bundle["run"]["id"], "schema": bundle["schema"],
                      "heart_cases": list(bundle["heart"]["cases"]),
                      "arterial_runs": len(bundle["arterial1d"]["runs"]),
                      "frozen": not args.no_freeze}, ensure_ascii=False))


if __name__ == "__main__":
    main()
