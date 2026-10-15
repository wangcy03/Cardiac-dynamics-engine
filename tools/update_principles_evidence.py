"""Refresh the mathematical-principles document from recorded evidence only.

No solver is executed, no parameter is changed, and no validation status is
inferred from the existence of a file. Run from any directory with
``python -m tools.update_principles_evidence`` (from the repository root), or
``python tools/update_principles_evidence.py --check`` to detect stale content.
Only the named evidence block in the HTML is replaced. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from html import escape
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "MATHEMATICAL_PRINCIPLES.html"
BEGIN = "<!-- PRINCIPLES_EVIDENCE_START -->"
END = "<!-- PRINCIPLES_EVIDENCE_END -->"
FILES = (
    "artifacts/verification_summary.json",
    "artifacts/numerical_check.json",
    "artifacts/b00/baseline_comparison.json",
    "artifacts/arterial1d/benchmark_summary.json",
    "artifacts/arterial1d/benchmark_matched.json",
    "artifacts/arterial1d/benchmark_reflections.json",
    "artifacts/arterial1d/benchmark_junction.json",
    "artifacts/arterial1d/benchmark_boileau.json",
    "artifacts/arterial1d/history/pre_linear3/manifest.json",
    "artifacts/arterial1d/external/boileau2015/manifest.json",
    "artifacts/arterial1d/external/boileau2015/reference_scheme_spread.json",
    "artifacts/demo/provenance.json",
    "artifacts/demo/baseline_truth.csv",
    "artifacts/demo/assisted_truth.csv",
    "artifacts/demo/prototype_viewer.html",
    "docs/principles_assets/demo_root_pressure.svg",
    "docs/principles_assets/demo_root_pressure_provenance.json",
    "docs/principles_assets/render_demo_pressure.py",
    "iabp/model.py",
    "iabp/components.py",
    "iabp/engine.py",
    "iabp/sensors.py",
    "docs/tasks/B01_SPEC.md",
    "tools/update_principles_evidence.py",
    "tools/arterial1d_check.py",
    "tools/verify_all.py",
)


def value(item: Any) -> str:
    """Escape unknown data before it enters a static HTML document."""
    if item is None:
        return "未记录"
    if isinstance(item, float):
        return escape(f"{item:.9g}")
    if isinstance(item, (dict, list)):
        return escape(json.dumps(item, ensure_ascii=False, sort_keys=True))
    return escape(str(item))


def link(name: str, label: str | None = None) -> str:
    return f'<a href="../{escape(name, quote=True)}">{escape(label or name)}</a>'


def read_json(name: str) -> dict[str, Any] | None:
    path = ROOT / name
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{name}: expected a JSON object")
    return data


def table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    heading = "".join(f"<th scope=\"col\">{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="table-scroll"><table><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table></div>'


def json_record(title: str, name: str, data: dict[str, Any] | None) -> str:
    if data is None:
        return f"<h3>{escape(title)}</h3><p>{link(name)}：<strong>NOT_FOUND</strong>，本次刷新未读取到文件。</p>"
    raw = json.dumps(data, ensure_ascii=False, indent=2)
    excerpt = raw[:24000]
    note = "<p>这里只展示前 24,000 个字符，完整内容见原始文件。</p>" if len(raw) > 24000 else ""
    return (
        f"<h3>{escape(title)}</h3><p>记录来源：{link(name)}。以下是原文件声明，存在文件不代表通过验收。</p>"
        f"<details><summary>展开原始 JSON 记录</summary>{note}<pre>{escape(excerpt)}</pre></details>"
    )


def trace_metrics(name: str) -> dict[str, float] | None:
    path = ROOT / name
    if not path.is_file():
        return None
    required = ("time_us", "p_root", "q_ao", "p_lv", "v_lv", "v_balloon", "mass_error")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or set(required) - set(reader.fieldnames):
            raise ValueError(f"{name}: missing required truth columns")
        rows = [{key: float(row[key]) for key in required} for row in reader]
    if len(rows) < 2 or not all(isfinite(x) for row in rows for x in row.values()):
        raise ValueError(f"{name}: trace must have at least two finite rows")
    if any(b["time_us"] <= a["time_us"] for a, b in zip(rows, rows[1:])):
        raise ValueError(f"{name}: non-increasing time; refusing to connect gaps in provenance")
    return {
        "rows": float(len(rows)),
        "start_s": rows[0]["time_us"] / 1e6,
        "end_s": rows[-1]["time_us"] / 1e6,
        "root_min_mmHg": min(row["p_root"] for row in rows),
        "root_max_mmHg": max(row["p_root"] for row in rows),
        "max_balloon_mL": max(row["v_balloon"] for row in rows),
        "max_mass_error_mL": max(abs(row["mass_error"]) for row in rows),
        "net_aortic_volume_mL": sum(
            (a["q_ao"] + b["q_ao"]) / 2 * (b["time_us"] - a["time_us"]) / 1e6
            for a, b in zip(rows, rows[1:])
        ),
        "lv_net_external_work_mmHg_mL": sum(
            -(a["p_lv"] + b["p_lv"]) / 2 * (b["v_lv"] - a["v_lv"])
            for a, b in zip(rows, rows[1:])
        ),
    }


def render_gates(summary: dict[str, Any] | None) -> str:
    if summary is None:
        return "<p>聚合核验记录缺失：NOT_FOUND。</p>"
    rows = []
    for name, gate in summary.get("gates", {}).items():
        rows.append((
            value(name), value(gate.get("status")), value(gate.get("exit_code")),
            f'<code>{value(gate.get("command", gate.get("reason")))}</code>',
        ))
    counts = summary.get("pytest_counts", {})
    limits = (
        "physiological_validation", "spatial_convergence", "actuator_calibration",
        "real_algorithm_integration", "github_ci", "windows_execution", "clinical_5ms_claim",
    )
    return (
        f'<p>环境：<code>{value(summary.get("python"))}</code>；<code>{value(summary.get("platform"))}</code>。</p>'
        + table(("质量门", "文件声明状态", "退出码", "命令或未运行原因"), rows)
        + f'<p>pytest 计数：<code>{value(counts)}</code>。未记录退出码保持“未记录”，不自动补为 0。</p>'
        + table(("证据边界", "文件声明状态"), [(escape(k), value(summary.get(k))) for k in limits])
    )


def render_numerical(data: dict[str, Any] | None) -> str:
    if data is None:
        return "<p>0D 数值基线缺失：NOT_FOUND。</p>"
    runs = [(value(r.get("step_us")), value(r.get("max_abs_mass_error_mL"))) for r in data.get("runs", [])]
    comparisons = []
    for row in data.get("comparisons", []):
        pressures = row.get("pressure_max_difference_mmHg") or {}
        events = row.get("event_max_difference_ms") or {}
        measured = {
            name: item for name, item in events.items()
            if isinstance(item, (int, float)) and not isinstance(item, bool) and isfinite(item)
        }
        missing = sorted(set(events) - set(measured))
        coverage = (
            "目标事件缺失" if missing or not events else
            "拓扑不一致" if row.get("event_topology_match") is False else
            "拓扑未确认" if row.get("event_topology_match") is not True else
            "仅覆盖本文件列出的事件"
        )
        comparisons.append((
            f'{value(row.get("step_us"))} / {value(row.get("reference_us"))}',
            value(pressures.get("p_root")), value(max(measured.values()) if measured else None),
            value(row.get("event_topology_match")), escape(", ".join(missing) or ("未列出事件" if not events else "无")),
            escape(coverage), value(row.get("status")),
        ))
    return (
        f'<p>{value(data.get("scope"))}；{value(data.get("model"))}。</p>'
        + table(("最大步长 / μs", "最大全循环血量残差 / mL"), runs)
        + table(("比较 / μs", "根部压力最大差 / mmHg", "已有数值的事件最大差 / ms", "事件拓扑一致", "缺失事件", "比较覆盖", "文件声明状态"), comparisons)
        + "<p>这些差值在相同物理时刻比较，未作时间平移。参考解也有离散误差；0D 时间比较不提供 1D 空间收敛或患者事件精度。</p>"
    )


def percentage(item: Any) -> str:
    if isinstance(item, (int, float)) and not isinstance(item, bool) and isfinite(item):
        return value(100 * item)
    return value(item)


def metric(row: dict[str, Any], *names: str) -> Any:
    """Accept explicit schema aliases; never replace a recorded null with zero."""
    return next((row[name] for name in names if name in row), None)


def b01_artifact_path(item: Any) -> str | None:
    if not isinstance(item, str) or not item:
        return None
    path = Path(item)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return None
    normalized = item.replace("\\", "/")
    if ".." in Path(normalized).parts:
        return None
    return normalized if normalized.startswith("artifacts/") else "artifacts/arterial1d/" + normalized


def b01_artifact_link(item: Any) -> str:
    name = b01_artifact_path(item)
    return link(name) if name else value(item)


def render_b01(data: dict[str, Any] | None) -> str:
    name = "artifacts/arterial1d/benchmark_summary.json"
    if data is None:
        return json_record("B01 独立 1D 基准记录", name, data)
    matched = data.get("matched") or {}
    groups = (
        ("历史一阶基线", matched.get("first_order_baseline") or []),
        ("历史 MUSCL 对照", matched.get("high_order_separate_comparison") or []),
        ("当前第三方案对照", matched.get("linear3_current_comparison") or []),
    )
    accuracy, ranges = [], []
    for label, runs in groups:
        if not runs:
            accuracy.append((escape(label), "未记录", "—", "—", "—", "—", "NOT_RECORDED"))
        for run in runs:
            accuracy.append((
                escape(label), value(run.get("scheme")), value(run.get("cells")),
                value(run.get("spatial_pressure_max_abs_error_pa")),
                percentage(run.get("peak_relative_error")), value(run.get("arrival_error_ms")),
                value(run.get("candidate_pass")),
            ))
            ranges.append((
                escape(label), value(run.get("scheme")), value(run.get("cells")),
                "全部单元；每 0.5 ms 观察",
                value(metric(run, "min_pressure_pa", "minimum_pressure_pa")),
                value(metric(run, "max_pressure_pa", "maximum_pressure_pa")),
                percentage(run.get("relative_reference_peak_overshoot")),
                percentage(run.get("relative_reference_peak_undershoot")),
                value(run.get("max_abs_conservation_residual_m3")),
            ))
    external, profiles = [], []
    for label, runs in (
        ("历史 MUSCL 外部参考", data.get("boileau_historical_muscl") or []),
        ("本次外部参考对照", data.get("boileau") or []),
    ):
        if not runs:
            external.append((escape(label), "未记录", "—", "—", "—", "—", "NOT_RECORDED"))
        for run in runs:
            external.append((
                escape(label), value(run.get("scheme")), value(run.get("cells")),
                value(run.get("spatial_pressure_max_abs_error_pa")),
                percentage(run.get("relative_max_profile_error")),
                percentage(run.get("maximum_peak_relative_error")),
                value(run.get("numerical_reproduction_status", run.get("candidate_pass"))),
            ))
            ranges.append((
                escape(label), value(run.get("scheme")), value(run.get("cells")),
                "全部单元；8 个原始剖面时刻",
                value(metric(run, "min_pressure_pa", "minimum_pressure_pa")),
                value(metric(run, "max_pressure_pa", "maximum_pressure_pa")),
                percentage(run.get("relative_reference_peak_overshoot")),
                percentage(run.get("relative_reference_peak_undershoot")),
                value(run.get("max_abs_conservation_residual_m3")),
            ))
            for profile in run.get("profiles") or []:
                profiles.append((
                    escape(label), value(run.get("scheme")), value(run.get("cells")),
                    value(profile.get("time_s")), value(profile.get("max_abs_error_pa")),
                    percentage(profile.get("peak_relative_error")),
                    value(profile.get("peak_position_difference_m")),
                    value(metric(profile, "min_pressure_pa", "minimum_pressure_pa")),
                    value(metric(profile, "max_pressure_pa", "maximum_pressure_pa")),
                    percentage(profile.get("relative_reference_peak_overshoot")),
                    percentage(profile.get("relative_reference_peak_undershoot")),
                ))
    statuses = [(escape(k), value(data.get(k))) for k in (
        "engineering_status", "public_benchmark_status", "overall_status", "selected_case", "mode"
    )]
    output = (
        '<h3>B01：方案、网格与证据范围</h3>'
        + f'<p>来源：{link(name)}。{value(data.get("scope"))}；对齐方式：{value(data.get("alignment"))}。</p>'
        + table(("记录范围", "原文件声明"), statuses)
        + '<p>历史一阶与 MUSCL 结果按原方案保留，不能被第三方案的状态覆盖。历史源与结果快照见 '
        + link("artifacts/arterial1d/history/pre_linear3/manifest.json", "历史身份清单") + '。</p>'
        + '<h3>工程短管：同一输入的空间／时间误差</h3>'
        + table(("证据组", "方案", "单元数", "最大压力差 / Pa", "峰值相对差 / %", "到达差 / ms", "文件候选门"), accuracy)
        + '<h3>Boileau：公开数值参考复现</h3>'
        + table(("证据组", "方案", "单元数", "最大压力差 / Pa", "全剖面相对差 / %", "最大峰值差 / %", "原文件声明"), external)
        + '<p>公开六法输出具有各自离散与采样差；选用 FVM 输出对照，不把它称为唯一精确真值。'
        '外部数值参考通过也不证明物理实验、患者或真实传感时延已经验证。</p>'
        + '<h3>极值与过冲：精度改善不能掩盖振铃</h3>'
        + table(("证据组", "方案", "单元数", "观察范围", "最小压力 / Pa", "最大压力 / Pa", "参考峰过冲 / %", "参考峰下冲 / %", "最大体积账本残差 / m³"), ranges)
        + '<p>min/max 是全部单元在记录观察时刻的极值：工程匹配每 0.5 ms，公开参考仅 8 个原始剖面时刻，'
        '不涵盖所有内部步或 RK 阶段。过冲=max(0,maxP/reference_peak−1)，下冲=max(0,−minP/reference_peak)；'
        '压力值本身不截断。缺字段保持未记录；不拿缺失或有限采样的极值推定没有振铃。</p>'
    )
    if profiles:
        output += '<details><summary>逐个公开剖面时刻的误差、极值与过冲</summary>' + table(
            ("证据组", "方案", "单元数", "时刻 / s", "最大差 / Pa", "峰差 / %", "峰位置差 / m", "最小压 / Pa", "最大压 / Pa", "过冲 / %", "下冲 / %"), profiles
        ) + '</details>'
    reports = []
    for case, report in (data.get("source_reports") or {}).items():
        log = report.get("run_log") or {}
        reports.append((
            value(case), b01_artifact_link(report.get("path")),
            f'<code class="hash">{value(report.get("sha256"))}</code>',
            b01_artifact_link(log.get("path")),
            f'<code class="hash">{value(log.get("sha256"))}</code>',
        ))
    if reports:
        output += '<h3>收集来源与原始运行日志身份</h3>' + table(
            ("Case", "结果 JSON", "记录的结果 SHA-256", "原始 run 日志", "记录的日志 SHA-256"), reports
        )
    output += (
        '<p><code>tools.verify_all</code> 中的 <code>--collect</code> 质量门读取已经实际跑完的 case，'
        '核查源文件、结果、CSV 与运行日志身份后收集；它不重新求解，也不替代原始 run 日志。'
        '门本身的退出码与原始求解退出码需分别阅读。实际收集身份与日志路径保留在下方原 JSON 中。</p>'
        + json_record("B01 原始 JSON 与收集身份", name, data)
    )
    return output


def render_demo(provenance: dict[str, Any] | None) -> str:
    traces = {name: trace_metrics(f"artifacts/demo/{name}_truth.csv") for name in ("baseline", "assisted")}
    if provenance is None or any(trace is None for trace in traces.values()):
        return "<p>配对演示的 provenance 或 truth CSV 缺失，保持 NOT_FOUND。</p>"
    metrics = (
        ("root_min_mmHg", "根部最小压力", "mmHg"),
        ("root_max_mmHg", "根部最大压力", "mmHg"),
        ("net_aortic_volume_mL", "窗口净主动脉出流积分", "mL"),
        ("lv_net_external_work_mmHg_mL", "窗口 LV 净外部功", "mmHg·mL"),
        ("max_balloon_mL", "最大球囊占据体积", "mL"),
        ("max_mass_error_mL", "最大血量残差", "mL"),
    )
    baseline, assisted = traces["baseline"], traces["assisted"]
    assert baseline is not None and assisted is not None
    rows = []
    audit = []
    for key, label, unit in metrics:
        rows.append((escape(label), value(baseline[key]), value(assisted[key]), value(assisted[key] - baseline[key]), escape(unit)))
        for case in ("baseline", "assisted"):
            declared = provenance.get("metrics", {}).get(case, {}).get(key)
            actual = traces[case]
            assert actual is not None
            difference = None if declared is None else actual[key] - float(declared)
            audit.append((escape(case), escape(key), value(difference)))
    current_hash = sha256((ROOT / "iabp/model.py").read_bytes()).hexdigest()
    recorded_hash = provenance.get("model_source_sha256")
    identity = "MATCH" if current_hash == recorded_hash else "DIFFERENT：代码与产物源文件身份不同，不能自动归因于当前代码"
    return (
        f'<p>直接读取两份 truth CSV：无辅助 {int(baseline["rows"])} 行、演示辅助 {int(assisted["rows"])} 行；'
        f'时间窗分别为 {value(baseline["start_s"])}–{value(baseline["end_s"])} s 和 '
        f'{value(assisted["start_s"])}–{value(assisted["end_s"])} s。</p>'
        + table(("量", "无辅助", "演示辅助", "辅助减无辅助", "单位"), rows)
        + f'<p>控制器：<code>{value(provenance.get("controller"))}</code>。固定预热 {value(provenance.get("warmup_s"))} s：'
        "预热时长本身不证明周期稳态。以上窗口积分包含过渡过程，不能直接命名为单搏 SV 或闭合稳态 PV 环功。</p>"
        + f'<p>provenance 记录的 model.py SHA-256：<code>{value(recorded_hash)}</code>；与当前源文件比较：<strong>{escape(identity)}</strong>。</p>'
        + "<p>若峰压增加同时出流减少、做功增加，应保留全部方向相反的结果；不能仅凭峰压宣称辅助有效。</p>"
        + "<details><summary>CSV 重新积分与 provenance 指标的数值差</summary>"
        + table(("分叉", "字段", "CSV 推导值减 JSON 记录值"), audit)
        + "<p>采用 CSV 实际相邻时间间隔作梯形积分，未重新运行物理模型、插值平移或拟合参数。</p></details>"
        + f'<p>{link("artifacts/demo/prototype_viewer.html", "打开本次真实运行观察器")} · '
        + link("artifacts/demo/provenance.json", "参数与运行来源") + "</p>"
        + render_scientific_figure()
    )


def render_scientific_figure() -> str:
    """Inline a separately generated Matplotlib plot, checking its input identity."""
    name = "docs/principles_assets/demo_root_pressure.svg"
    metadata = read_json("docs/principles_assets/demo_root_pressure_provenance.json")
    path = ROOT / name
    if not path.is_file() or metadata is None:
        return "<p>标准绘图产物尚未生成；完整实际波形见上方观察器。</p>"
    if sha256(path.read_bytes()).hexdigest() != metadata.get("svg_sha256"):
        raise ValueError(f"{name}: SVG does not match its recorded hash")
    for source, expected in metadata.get("input_sha256", {}).items():
        current = ROOT / source
        if not current.is_file() or sha256(current.read_bytes()).hexdigest() != expected:
            return "<p>独立波形图的 CSV 来源身份已变化，当前不内联陈旧图。按维护说明重新绘图；完整实际波形见观察器。</p>"
    svg = path.read_text(encoding="utf-8")
    start, end = svg.find("<svg"), svg.rfind("</svg>")
    if start < 0 or end < start:
        raise ValueError(f"{name}: not an SVG document")
    fragment = svg[start:end + len("</svg>")]
    if re.search(r"<(?:script|foreignObject|iframe)\b|\bon\w+\s*=", fragment, re.IGNORECASE):
        raise ValueError(f"{name}: active SVG content is not permitted")
    return (
        '<figure class="scientific"><div class="diagram-container">' + fragment + "</div>"
        '<figcaption>图 4 · 两份真实 truth CSV 的根部压力，全量样本直线连接，未平移、平滑、重新求解或拟合。'
        '两曲线使用同一时间轴与压力轴。峰压变化须与上表出流／做功一起阅读。'
        f'使用 Matplotlib {value(metadata.get("matplotlib_version"))} 生成；'
        + link(name, "独立 SVG") + " · "
        + link("docs/principles_assets/demo_root_pressure_provenance.json", "绘图来源与哈希")
        + "。</figcaption></figure>"
    )


def export_diagrams(source: str, check: bool) -> bool:
    """Keep self-contained schematic previews identical to the canonical HTML."""
    style = re.search(r"<style>(.*?)</style>", source, re.DOTALL)
    assert style is not None
    names = {
        "principles-architecture-title": "architecture",
        "principles-sequence-title": "causal_sequence",
        "principles-control-volume-title": "control_volumes",
    }
    current = True
    for fragment in re.findall(r"<svg\b.*?</svg>", source, re.DOTALL):
        name = next((file for marker, file in names.items() if f'id="{marker}"' in fragment), None)
        if name is None:
            continue
        title = re.search(r"<title[^>]*>(.*?)</title>", fragment)
        assert title is not None
        output = (
            '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title.group(1)}</title><style>{style.group(1)}</style></head>'
            f'<body><main><h1>{title.group(1)}</h1><div class="diagram-container">{fragment}</div>'
            '<p class="small">本预览由 MATHEMATICAL_PRINCIPLES.html 的原图导出；正文是维护源。</p>'
            '</main></body></html>\n'
        )
        path = ROOT / "docs" / "principles_assets" / f"{name}.html"
        if check:
            current = current and path.is_file() and path.read_text(encoding="utf-8") == output
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(output, encoding="utf-8", newline="\n")
    return current


def render_sources() -> str:
    paths = list(FILES)
    summary = read_json("artifacts/arterial1d/benchmark_summary.json")
    for report in ((summary or {}).get("source_reports") or {}).values():
        log = report.get("run_log") or {}
        for item in (report.get("path"), log.get("path")):
            name = b01_artifact_path(item)
            if name and name not in paths:
                paths.append(name)
    paths += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "iabp" / "arterial1d").glob("*.py"))]
    rows = []
    for name in paths:
        path = ROOT / name
        if path.is_file():
            content = path.read_bytes()
            rows.append((link(name), str(len(content)), f'<code class="hash">{sha256(content).hexdigest()}</code>'))
        else:
            rows.append((link(name), "—", "NOT_FOUND"))
    return table(("读取来源（相对于仓库）", "字节数", "SHA-256"), rows)


def render() -> str:
    summary = read_json("artifacts/verification_summary.json")
    numerical = read_json("artifacts/numerical_check.json")
    b00 = read_json("artifacts/b00/baseline_comparison.json")
    b01 = read_json("artifacts/arterial1d/benchmark_summary.json")
    provenance = read_json("artifacts/demo/provenance.json")
    return (
        '\n<div class="evidence-generated">\n'
        '<p class="record-scope">自动证据区：仅整理磁盘中的真实导出值。可重复刷新，未运行求解器；文件中的 PASS 只在其声明范围内有效。</p>\n'
        '<h3>软件质量门与证据范围</h3>\n' + render_gates(summary)
        + '<h3>0D 时间离散与守恒基线</h3>\n' + render_numerical(numerical)
        + json_record("B00 跨环境基线复现记录", "artifacts/b00/baseline_comparison.json", b00)
        + render_b01(b01)
        + '<h3>共享初态的实际 0D 配对运行</h3>\n' + render_demo(provenance)
        + '<h3>本次刷新读取的文件身份</h3>\n'
        + '<p>哈希说明“读到了哪一份文件”，不证明这些文件本身正确，也不把读取时的代码自动当作历史产物的构建代码。缺失路径保留 NOT_FOUND。</p>\n'
        + render_sources() + '\n</div>\n'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="return 1 if the embedded evidence needs refreshing")
    parser.add_argument("--export-diagrams", action="store_true", help="also export the three canonical schematic previews")
    args = parser.parse_args()
    source = DOCUMENT.read_text(encoding="utf-8")
    if source.count(BEGIN) != 1 or source.count(END) != 1:
        raise ValueError("document must contain exactly one ordered evidence marker pair")
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(source):
        raise ValueError("evidence markers are out of order")
    replacement = BEGIN + render() + END
    refreshed = pattern.sub(lambda _: replacement, source)
    diagrams_current = not args.export_diagrams or export_diagrams(refreshed, args.check)
    if args.check:
        if source != refreshed or not diagrams_current:
            print("STALE: refresh with python -m tools.update_principles_evidence")
            raise SystemExit(1)
        print("CURRENT: embedded evidence matches the recorded source files")
    else:
        DOCUMENT.write_text(refreshed, encoding="utf-8", newline="\n")
        print(f"Updated {DOCUMENT}")


if __name__ == "__main__":
    main()
