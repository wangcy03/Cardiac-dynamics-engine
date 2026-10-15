"""Read-only, offline structural checks for a mathematical-principles HTML page.

This is a conservative static-document contract, not an HTML security sandbox,
browser renderer, mathematical equivalence checker, or numerical validator.
Relative document/report paths are resolved against --root. Exit 0 means only
PASS_STATIC_ONLY; exit 1 reports a failed check; exit 2 is a CLI error.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Iterator
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
BLOCKED = frozenset("iframe object embed frame frameset form base foreignobject animate animatemotion animatetransform set".split())
INERT_SCRIPTS = frozenset(("application/json", "application/ld+json", "application/x-tex"))
MATH_NS = "http://www.w3.org/1998/Math/MathML"
CSS_URL = re.compile(r"url\s*\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})(?:\s)?|\\([^\r\n\f])")


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    line: int
    start: int
    parent: Element | None = field(default=None, repr=False)
    end: int | None = None
    children: list[Element | str] = field(default_factory=list)

    def descendants(self, tag: str | None = None) -> Iterator[Element]:
        for child in self.children:
            if isinstance(child, Element):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.descendants(tag)

    def text(self) -> str:
        return "".join(child.text() if isinstance(child, Element) else child for child in self.children)


class Markup(HTMLParser):
    """Keep enough structure and raw spans to XML-parse each MathML fragment."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.offsets = [0]
        for line in source.splitlines(keepends=True):
            self.offsets.append(self.offsets[-1] + len(line))
        self.root = Element("document", {}, 1, 0, end=len(source))
        self.stack = [self.root]
        self.comments: list[tuple[str, int]] = []
        self.feed(source)
        self.close()
        self.elements = list(self.root.descendants())
        self.ids: dict[str, list[Element]] = {}
        for node in self.elements:
            if "id" in node.attrs:
                self.ids.setdefault(node.attrs["id"], []).append(node)

    def source_offset(self) -> int:
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self.source_offset()
        node = Element(tag, {key: value or "" for key, value in attrs}, self.getpos()[0], start, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag in VOID:
            node.end = start + len(self.get_starttag_text())
        else:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop().end = self.source_offset() + len(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack[index].end = self.source.find(">", self.source_offset()) + 1
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)

    def handle_comment(self, data: str) -> None:
        self.comments.append((data.strip(), self.source_offset()))


class Audit:
    def __init__(self, root: Path, document: Path) -> None:
        self.root = root
        self.document = document
        self.errors: list[dict[str, object]] = []
        self.warnings: list[dict[str, object]] = []
        self.cache: dict[Path, Markup] = {}
        self.inputs: dict[Path, str] = {}
        self.local_targets: set[Path] = set()
        self.scanned: set[Path] = set()
        self.external_navigation: set[str] = set()
        self.counts = {"local_links": 0, "anchors": 0, "mathml": 0, "inline_svg": 0, "stylesheets": 0}

    def label(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def issue(self, code: str, message: str, path: Path, line: int = 0, *, warning: bool = False) -> None:
        (self.warnings if warning else self.errors).append({
            "code": code, "path": self.label(path), "line": line, "message": message,
        })

    def inside(self, path: Path) -> bool:
        return path.is_relative_to(self.root)

    def read_text(self, path: Path) -> str | None:
        try:
            data = path.read_bytes()
            self.inputs[path] = sha256(data).hexdigest()
            return data.decode("utf-8-sig")
        except (OSError, UnicodeError) as error:
            self.issue("READ_FAILED", str(error), path)
            return None

    def markup(self, path: Path) -> Markup | None:
        if path in self.cache:
            return self.cache[path]
        source = self.read_text(path)
        if source is None:
            return None
        parsed = Markup(source)
        self.cache[path] = parsed
        return parsed

    def url(self, raw: str, path: Path, line: int, *, navigation: bool = False, resource: bool = False) -> None:
        raw = unescape(raw).strip()
        if not raw or any(ord(char) < 32 for char in raw):
            self.issue("INVALID_URL", "Empty URL or control character in URL", path, line)
            return
        try:
            parts = urlsplit(raw.replace("\\", "/"))
        except ValueError as error:
            self.issue("INVALID_URL", str(error), path, line)
            return
        scheme = parts.scheme.lower()
        if scheme in ("http", "https") or (not scheme and parts.netloc):
            if navigation:
                self.external_navigation.add(raw)
            else:
                self.issue("EXTERNAL_DEPENDENCY", f"Remote resource is not allowed: {raw}", path, line)
            return
        if scheme == "mailto" and navigation:
            self.external_navigation.add(raw)
            return
        if scheme or parts.netloc:
            self.issue("UNSUPPORTED_URL_SCHEME", f"Unsupported static-document URL: {raw}", path, line)
            return
        target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
        if not self.inside(target):
            self.issue("LOCAL_PATH_OUTSIDE_ROOT", f"Local target escapes --root: {raw}", path, line)
            return
        self.counts["local_links"] += 1
        self.local_targets.add(target)
        if navigation and target.is_dir():
            if parts.fragment:
                self.issue("ANCHOR_NOT_CHECKED", f"Directory navigation has no HTML anchor table: {raw}", path, line, warning=True)
            return
        if not target.is_file():
            self.issue("LOCAL_TARGET_MISSING", f"Local file does not exist: {raw}", path, line)
            return
        fragment = unquote(parts.fragment)
        if fragment:
            self.counts["anchors"] += 1
            if target.suffix.lower() in (".html", ".htm", ".svg"):
                parsed = self.markup(target)
                if parsed is not None and fragment not in parsed.ids:
                    self.issue("ANCHOR_MISSING", f"Missing anchor in {self.label(target)}: {fragment}", path, line)
            else:
                self.issue("ANCHOR_NOT_CHECKED", f"Anchor target is not HTML/SVG: {raw}", path, line, warning=True)
        if resource and target.suffix.lower() == ".css":
            self.stylesheet(target)
        elif resource and target.suffix.lower() in (".svg", ".html", ".htm"):
            self.scan_markup(target)

    def css(self, source: str, path: Path, line: int) -> None:
        def decode(match: re.Match[str]) -> str:
            if match.group(1):
                number = int(match.group(1), 16)
                return chr(number) if 0 < number <= 0x10FFFF else "\ufffd"
            return match.group(2)

        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        source = CSS_ESCAPE.sub(decode, source)
        if re.search(r"@import\b", source, re.I):
            self.issue("CSS_IMPORT_FORBIDDEN", "Inline/local CSS is allowed; CSS import is not", path, line)
        if re.search(r"expression\s*\(|(?:^|[;{])\s*(?:-moz-binding|behavior)\s*:", source, re.I):
            self.issue("ACTIVE_CSS_FORBIDDEN", "Executable CSS is outside the static-document contract", path, line)
        matches = list(CSS_URL.finditer(source))
        if len(matches) != len(re.findall(r"url\s*\(", source, re.I)):
            self.issue("CSS_URL_MALFORMED", "Unparseable CSS url()", path, line)
        for match in matches:
            self.url(match.group(2), path, line, resource=True)

    def stylesheet(self, path: Path) -> None:
        if path in self.scanned:
            return
        self.scanned.add(path)
        self.counts["stylesheets"] += 1
        source = self.read_text(path)
        if source is not None:
            self.css(source, path, 1)

    def markers(self, parsed: Markup, path: Path) -> None:
        for kind in ("EVIDENCE", "NARRATIVE"):
            begin = [offset for text, offset in parsed.comments if text == f"PRINCIPLES_{kind}_START"]
            end = [offset for text, offset in parsed.comments if text == f"PRINCIPLES_{kind}_END"]
            if not begin and not end:
                message = (
                    "Project-specific evidence boundaries are not assessed; keep the existing refresher contract"
                    if kind == "EVIDENCE" else "Existing document may keep an unmarked manual body"
                )
                self.issue(f"{kind}_MARKERS_ABSENT", message, path, warning=True)
            elif len(begin) != 1 or len(end) != 1 or begin[0] >= end[0]:
                self.issue("MARKER_PAIR_INVALID", f"Expected one ordered PRINCIPLES_{kind}_START/END comment pair", path)

    def math(self, node: Element, parsed: Markup, path: Path) -> None:
        self.counts["mathml"] += 1
        if node.end is None:
            self.issue("MATHML_XML_INVALID", "MathML element is not closed", path, node.line)
            return
        try:
            tree = ET.fromstring(parsed.source[node.start:node.end])
        except ET.ParseError as error:
            self.issue("MATHML_XML_INVALID", str(error), path, node.line)
            return
        if tree.tag != f"{{{MATH_NS}}}math":
            self.issue("MATHML_NAMESPACE_INVALID", "Use the native MathML namespace", path, node.line)
        annotations = [
            "".join(item.itertext()).strip() for item in tree.iter()
            if item.tag.rsplit("}", 1)[-1] == "annotation"
            and item.attrib.get("encoding", "").lower() == "application/x-tex"
        ]
        if not annotations or not all(annotations):
            self.issue("LATEX_ANNOTATION_MISSING", "Each MathML formula needs a nonempty application/x-tex annotation", path, node.line)
        details: list[Element] = []
        if node.parent is not None:
            after_formula = False
            for sibling in node.parent.children:
                if sibling is node:
                    after_formula = True
                    continue
                if not after_formula or (isinstance(sibling, str) and not sibling.strip()):
                    continue
                if isinstance(sibling, Element) and sibling.tag == "details":
                    details.append(sibling)
                break
        if not details:
            container = node.parent
            while container is not None and container.tag not in ("section", "main", "body", "document"):
                if "data-equation" in container.attrs or set(container.attrs.get("class", "").split()) & {"equation", "formula"}:
                    break
                if container.tag in ("div", "figure") and len(list(container.descendants("math"))) == 1:
                    break
                container = container.parent
            if container is not None and container.tag not in ("section", "main", "body", "document"):
                details = list(container.descendants("details"))
        folded = [
            pre.text().strip() for detail in details
            if any(re.search(r"(?:La)?TeX|公式源码", summary.text(), re.I) for summary in detail.descendants("summary"))
            for pre in detail.descendants("pre") if pre.text().strip()
        ]
        if not folded:
            self.issue("LATEX_FOLDOUT_MISSING", "Put a nonempty LaTeX details/pre source beside the formula", path, node.line)
        elif annotations and all(annotations):
            def normalized(text: str) -> str:
                return re.sub(r"\s+", "", text)
            if not all(any(normalized(annotation) in normalized(source) for source in folded) for annotation in annotations):
                self.issue("LATEX_SOURCE_TEXT_DIFFERS", "Annotation and foldout text differ; manually check mathematical consistency", path, node.line, warning=True)

    def svg(self, node: Element, path: Path) -> None:
        self.counts["inline_svg"] += 1
        descendants = list(node.descendants())
        titles = [item for item in descendants if item.tag == "title" and item.text().strip()]
        descriptions = [item for item in descendants if item.tag == "desc" and item.text().strip()]
        ids = {item.attrs["id"]: item for item in descendants if item.attrs.get("id")}
        labels = node.attrs.get("aria-labelledby", "").split()
        described = node.attrs.get("aria-describedby", "").split()
        if node.attrs.get("role") not in ("img", "graphics-document") or not titles or not descriptions:
            self.issue("SVG_ACCESSIBILITY_INVALID", "SVG needs an image role and nonempty title/desc", path, node.line)
        if not labels or any(label not in ids or not ids[label].text().strip() for label in labels + described):
            self.issue("SVG_ACCESSIBLE_REFERENCE_INVALID", "SVG aria references must resolve to nonempty text within this SVG", path, node.line)
        elif not any(item.attrs.get("id") in labels for item in titles) or not any(item.attrs.get("id") in labels + described for item in descriptions):
            self.issue("SVG_ACCESSIBLE_REFERENCE_INVALID", "Reference the title and description from SVG aria attributes", path, node.line)

    def scan_markup(self, path: Path, *, entry: bool = False) -> None:
        if path in self.scanned:
            return
        self.scanned.add(path)
        parsed = self.markup(path)
        if parsed is None:
            return
        for identifier, nodes in parsed.ids.items():
            if not identifier or len(nodes) > 1:
                self.issue("DUPLICATE_OR_EMPTY_ID", f"ID must be nonempty and unique: {identifier!r}", path, nodes[0].line)
        if entry:
            self.markers(parsed, path)
            html = next((node for node in parsed.elements if node.tag == "html"), None)
            if html is None or not html.attrs.get("lang"):
                self.issue("DOCUMENT_LANGUAGE_MISSING", "HTML document needs lang", path)
            if not any(node.tag == "title" and node.text().strip() for node in parsed.elements):
                self.issue("DOCUMENT_TITLE_MISSING", "Document needs a nonempty title", path)
            if not any(node.tag == "math" for node in parsed.elements):
                self.issue("MATHML_MISSING", "Mathematical document contains no native MathML formula", path)
        for node in parsed.elements:
            if node.tag in BLOCKED:
                self.issue("ACTIVE_EMBED_FORBIDDEN", f"Element outside the static contract: {node.tag}", path, node.line)
            if node.tag == "script" and (node.attrs.get("type", "").lower() not in INERT_SCRIPTS or "src" in node.attrs):
                self.issue("EXECUTABLE_SCRIPT_FORBIDDEN", "Use native MathML and static HTML; executable scripts are not allowed", path, node.line)
            if node.tag == "meta" and node.attrs.get("http-equiv", "").lower() == "refresh":
                self.issue("META_REFRESH_FORBIDDEN", "Automatic navigation is not allowed", path, node.line)
            if node.tag == "style":
                self.css(node.text(), path, node.line)
            if node.tag == "math":
                self.math(node, parsed, path)
            if node.tag == "svg":
                self.svg(node, path)
            for key, value in node.attrs.items():
                if key.startswith("on") or key in ("ping", "srcdoc"):
                    self.issue("ACTIVE_ATTRIBUTE_FORBIDDEN", f"Active attribute is not allowed: {key}", path, node.line)
                elif key == "style":
                    self.css(value, path, node.line)
                elif key in ("href", "xlink:href"):
                    self.url(value, path, node.line, navigation=node.tag == "a", resource=node.tag != "a")
                elif key in ("src", "poster", "data", "action", "formaction"):
                    self.url(value, path, node.line, resource=True)
                elif key == "srcset":
                    for candidate in value.split(","):
                        words = candidate.split()
                        self.url(words[0] if words else "", path, node.line, resource=True)

    def report(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "status": "FAIL_STATIC" if self.errors else "PASS_STATIC_ONLY",
            "root": str(self.root),
            "document": self.label(self.document),
            "checks": self.counts,
            "errors": self.errors,
            "warnings": self.warnings,
            "inputs_sha256_at_check": {self.label(path): digest for path, digest in sorted(self.inputs.items())},
            "external_navigation_not_fetched": sorted(self.external_navigation),
            "browser_rendering": "NOT_RUN_BY_STATIC_CHECKER",
            "freshness_and_run_identity": "NOT_ASSESSED_BY_STATIC_CHECKER",
            "numerical_validation": "NOT_RUN_BY_STATIC_CHECKER",
            "domain_or_clinical_validation": "NOT_ASSESSED",
            "scope": "Read-only offline structural checks; not mathematical equivalence, a sanitizer, browser rendering, or model acceptance.",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="project root containing all local targets")
    parser.add_argument("--document", type=Path, required=True, help="HTML path, relative to --root or absolute within it")
    parser.add_argument("--output", type=Path, help="optional JSON report path; relative to --root")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("--root must be an existing directory")
    document = (root / args.document).resolve()
    output = (root / args.output).resolve() if args.output is not None else None
    audit = Audit(root, document)
    if not audit.inside(document):
        audit.issue("DOCUMENT_OUTSIDE_ROOT", "Document must be inside --root", document)
    else:
        audit.scan_markup(document, entry=True)
    if output is not None and (output.suffix.lower() != ".json" or output == document or output in audit.inputs or output in audit.local_targets):
        parser.error("--output must be a .json report and must not overwrite the document or a referenced dependency")
    report = audit.report()
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 1 if audit.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
