"""Exercise the static checker's public CLI on valid and invalid documents."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_document.py"
BASE = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Static checker fixture</title><style>html{scroll-behavior:smooth}</style>
</head><body><main id="main">
<!-- PRINCIPLES_NARRATIVE_START -->
<div class="equation"><math xmlns="http://www.w3.org/1998/Math/MathML">
<semantics><mrow><mi>x</mi><mo>=</mo><mi>x</mi></mrow>
<annotation encoding="application/x-tex">x=x</annotation></semantics></math>
<details><summary>LaTeX 源码</summary><pre>x=x</pre></details></div>
<!-- PRINCIPLES_NARRATIVE_END -->
<!-- PRINCIPLES_EVIDENCE_START --><p>NOT_RUN</p><!-- PRINCIPLES_EVIDENCE_END -->
</main></body></html>'''


class StaticDocumentContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="principles-doc-test-")
        self.root = Path(self.temporary.name).resolve()
        self.document = self.root / "docs" / "principles.html"
        self.document.parent.mkdir()

    def tearDown(self) -> None:
        assert self.root.parent == Path(tempfile.gettempdir()).resolve()
        assert self.root.name.startswith("principles-doc-test-")
        self.temporary.cleanup()

    def invoke(self, source: str = BASE, output: str | None = None) -> subprocess.CompletedProcess[str]:
        self.document.write_text(source, encoding="utf-8", newline="\n")
        before = sha256(self.document.read_bytes()).hexdigest()
        args = [sys.executable, str(CHECKER), "--root", str(self.root),
                "--document", "docs/principles.html"]
        if output is not None:
            args += ["--output", output]
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(sha256(self.document.read_bytes()).hexdigest(), before)
        return result

    def assert_valid(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "PASS_STATIC_ONLY")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["numerical_validation"], "NOT_RUN_BY_STATIC_CHECKER")

    def assert_invalid(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["errors"])

    def test_valid_formula_and_scroll_behavior(self) -> None:
        self.assert_valid(self.invoke(output="report.json"))
        self.assertTrue((self.root / "report.json").is_file())

    def test_existing_directory_navigation(self) -> None:
        (self.root / "legacy").mkdir()
        self.assert_valid(self.invoke(BASE.replace("</main>", '<a href="../legacy/">Archive</a></main>')))

    def test_project_specific_evidence_markers(self) -> None:
        custom = BASE.replace("PRINCIPLES_EVIDENCE_START", "BEGIN GENERATED EVIDENCE").replace(
            "PRINCIPLES_EVIDENCE_END", "END GENERATED EVIDENCE")
        self.assert_valid(self.invoke(custom))

    def test_adjacent_sibling_latex_source(self) -> None:
        siblings = BASE.replace('<div class="equation">', '').replace('</details></div>', '</details>')
        self.assert_valid(self.invoke(siblings))

    def test_distant_latex_source_is_not_paired(self) -> None:
        siblings = BASE.replace('<div class="equation">', '').replace('</details></div>', '</details>')
        siblings = siblings.replace('<details>', '<p>Unrelated explanation.</p><details>')
        self.assert_invalid(self.invoke(siblings))

    def test_one_missing_evidence_marker_is_invalid(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace('<!-- PRINCIPLES_EVIDENCE_END -->', '')))

    def test_svg_accessible_title_and_description(self) -> None:
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="fig-title fig-desc">'
               '<title id="fig-title">Boundary</title><desc id="fig-desc">Two connected states.</desc>'
               '<rect width="10" height="10"/></svg>')
        self.assert_valid(self.invoke(BASE.replace('</main>', svg + '</main>')))

    def test_svg_missing_description_is_invalid(self) -> None:
        svg = '<svg role="img" aria-labelledby="fig-title"><title id="fig-title">Boundary</title></svg>'
        self.assert_invalid(self.invoke(BASE.replace('</main>', svg + '</main>')))

    def test_external_citation_is_navigation_only(self) -> None:
        self.assert_valid(self.invoke(BASE.replace("</main>", '<a href="https://example.org/paper">Source</a></main>')))

    def test_local_html_anchor(self) -> None:
        (self.root / "source.html").write_text('<html><body id="definition"></body></html>', encoding="utf-8")
        self.assert_valid(self.invoke(BASE.replace("</main>", '<a href="../source.html#definition">Definition</a></main>')))

    def test_duplicate_id(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace("</main>", '<p id="main">duplicate</p></main>')))

    def test_missing_anchor(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace("</main>", '<a href="#missing">Missing</a></main>')))

    def test_missing_local_file(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace("</main>", '<a href="missing.csv">Missing</a></main>')))

    def test_script_is_rejected_without_execution(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace("</body>", '<script>throw Error("never execute");</script></body>')))

    def test_event_handler_is_rejected(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace('id="main"', 'id="main" onclick="alert(1)"')))

    def test_remote_embedded_image(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace("</main>", '<img src="https://example.org/plot.png" alt="plot"></main>')))

    def test_active_css_expression(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace("scroll-behavior:smooth", "width:expression(alert(1))")))

    def test_invalid_mathml(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace("</mrow>", "</msqrt>")))

    def test_missing_latex_annotation(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace('encoding="application/x-tex"', 'encoding="text/plain"')))

    def test_missing_latex_foldout(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace('<details><summary>LaTeX 源码</summary><pre>x=x</pre></details>', '')))

    def test_duplicate_evidence_marker(self) -> None:
        self.assert_invalid(self.invoke(BASE.replace("</main>", "<!-- PRINCIPLES_EVIDENCE_START --></main>")))

    def test_report_cannot_overwrite_referenced_json(self) -> None:
        path = self.root / "evidence.json"
        path.write_text('{"status":"NOT_RUN"}', encoding="utf-8")
        before = path.read_bytes()
        result = self.invoke(BASE.replace("</main>", '<a href="../evidence.json">Evidence</a></main>'), output="evidence.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
