"""A portable observer must preserve inputs and cannot overwrite frozen runs."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools.viewer import encoded_bundle, freeze_bundle, refresh_viewer, write_viewer


def bundle(files: list[dict] | None = None) -> dict:
    return {"schema": "cardiac-observer/v1", "run": {"id": "test-run", "files": files or []},
            "heart": {"cases": {}}, "arterial1d": {"runs": []}, "warnings": []}


def test_inline_bundle_cannot_close_script_or_lose_float_precision() -> None:
    data = bundle()
    data["warnings"] = ["</script><script>bad()</script>&\u2028"]
    data["value"] = 0.12345678901234566
    text = encoded_bundle(data)
    assert "</script>" not in text
    assert json.loads(text) == data


def test_nonfinite_and_unknown_schema_rejected() -> None:
    data = bundle()
    data["value"] = float("nan")
    with pytest.raises(ValueError):
        encoded_bundle(data)
    with pytest.raises(ValueError, match="schema"):
        encoded_bundle({"schema": "future/v999"})


def test_portable_output_reuses_the_fixed_template(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    template = ('<link rel="stylesheet" href="viewer.css">'
                '<script id="observer-bundle" type="application/json">__BUNDLE__</script>'
                '<script src="viewer.js"></script>')
    (assets / "index.html").write_text(template, encoding="utf-8")
    (assets / "viewer.css").write_text("/* fixed css */", encoding="utf-8")
    (assets / "viewer.js").write_text("/* fixed js */", encoding="utf-8")
    path = tmp_path / "portable.html"
    write_viewer(path, bundle(), assets=assets)
    text = path.read_text(encoding="utf-8")
    assert "fixed css" in text and "fixed js" in text
    assert "__BUNDLE__" not in text and 'src="viewer.js"' not in text
    (assets / "index.html").write_text(template + "__BUNDLE__", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        write_viewer(path, bundle(), assets=assets)


def test_frozen_run_copies_raw_bytes_and_refuses_replacement(tmp_path: Path) -> None:
    source = tmp_path / "artifacts/demo/raw.csv"
    source.parent.mkdir(parents=True)
    raw = b"time,value\r\n0,-0.00000000000123\r\n"
    source.write_bytes(raw)
    data = bundle([{"path": "artifacts/demo/raw.csv", "sha256": sha256(raw).hexdigest()}])
    out = tmp_path / "artifacts/runs/test-run"
    freeze_bundle(tmp_path, data, out)
    assert (out / "raw/artifacts/demo/raw.csv").read_bytes() == raw == source.read_bytes()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FROZEN_RECORDED_EXPORTS"
    with pytest.raises(FileExistsError):
        freeze_bundle(tmp_path, data, out)
    assert (out / "raw/artifacts/demo/raw.csv").read_bytes() == raw


def test_hash_change_and_escaping_paths_fail_before_archive_creation(tmp_path: Path) -> None:
    source = tmp_path / "raw.csv"
    source.write_text("actual", encoding="utf-8")
    data = bundle([{"path": "raw.csv", "sha256": "0" * 64}])
    out = tmp_path / "artifacts/runs/refuse"
    with pytest.raises(ValueError, match="changed"):
        freeze_bundle(tmp_path, data, out)
    assert not out.exists()
    data["run"]["files"][0]["path"] = "../outside.csv"
    with pytest.raises(ValueError, match="outside"):
        freeze_bundle(tmp_path, data, out)
    with pytest.raises(ValueError, match="within"):
        freeze_bundle(tmp_path, bundle(), tmp_path / "outside")


def test_publish_cannot_overwrite_input_or_frozen_archive(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "raw.html"
    source.write_bytes(b"raw scientific input bytes")
    data = bundle([{"path": "raw.html", "sha256": sha256(source.read_bytes()).hexdigest()}])
    monkeypatch.setattr("tools.viewer_data.build_bundle", lambda *args: data)
    with pytest.raises(ValueError, match="overwrite an input"):
        refresh_viewer(tmp_path, run_id="test-run", output=source)
    assert source.read_bytes() == b"raw scientific input bytes"
    assert not (tmp_path / "artifacts/runs/test-run").exists()
    with pytest.raises(ValueError, match="frozen run"):
        refresh_viewer(tmp_path, run_id="test-run", output=tmp_path / "artifacts/runs/old/out.html")
