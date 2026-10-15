"""Optional scientific figure: plot actual exported CSV, never run a solver.

Requires Matplotlib in the selected documentation environment. This optional
renderer is not a dependency of the core, evidence refresher, or test gates.
"""
from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import platform

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "principles_assets"


def main() -> None:
    sources = [
        "artifacts/demo/baseline_truth.csv",
        "artifacts/demo/assisted_truth.csv",
        "artifacts/demo/provenance.json",
    ]
    traces = {}
    for name in ("baseline", "assisted"):
        with (ROOT / f"artifacts/demo/{name}_truth.csv").open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        traces[name] = (
            [float(row["time_us"]) / 1e6 for row in rows],
            [float(row["p_root"]) for row in rows],
        )
    # Stable SVG identifiers and no creation timestamp keep repeated plots reviewable.
    plt.rcParams.update({
        "svg.hashsalt": "iabp-principles-demo-root-pressure-v1",
        "svg.fonttype": "none", "font.family": "DejaVu Sans",
        "font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
    })
    fig, ax = plt.subplots(figsize=(16, 6))
    fig.patch.set_facecolor("#f5f5f5")
    ax.set_facecolor("#f5f5f5")
    for name, label, color in (
        ("baseline", "No assist", "#4f5d75"),
        ("assisted", "Causal demo assist", "#bf4520"),
    ):
        time, pressure = traces[name]
        ax.plot(time, pressure, label=label, color=color, linewidth=1.6)
    ax.set(xlabel="Engine physical time (s)", ylabel="Aortic root pressure (mmHg)")
    ax.set_xlim(traces["baseline"][0][0], traces["baseline"][0][-1])
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", color="#bfc0c0", linewidth=0.6)
    ax.legend(frameon=False, loc="upper center", ncol=2)
    ax.set_title("Same initial state; raw exported 0D traces", loc="left", pad=18)
    fig.text(0.075, 0.025,
             "Engineering simulation only. All CSV samples are connected; no smoothing or time alignment.",
             fontsize=10, color="#4f5d75")
    fig.subplots_adjust(left=0.075, right=0.98, bottom=0.17, top=0.86)
    output = OUT / "demo_root_pressure.svg"
    fig.savefig(output, format="svg", metadata={
        "Date": None, "Creator": f"Matplotlib {matplotlib.__version__}; render_demo_pressure.py v1",
        "Description": "Actual exported IABP engineering simulation; not a clinical trace.",
    })
    plt.close(fig)
    svg = output.read_text(encoding="utf-8")
    position = svg.index(">", svg.index("<svg"))
    svg = (svg[:position]
           + ' role="img" aria-labelledby="principles-demo-pressure-title principles-demo-pressure-desc"'
           + svg[position:position + 1]
           + '<title id="principles-demo-pressure-title">实际导出的 0D 根部压力</title>'
           + '<desc id="principles-demo-pressure-desc">共享初态的无辅助与因果演示辅助根部压力按全部 CSV 样本绘制，峰压须与出流及做功共同评价。</desc>'
           + svg[position + 1:])
    output.write_text(svg, encoding="utf-8", newline="\n")
    record = {
        "schema": "iabp-principles-scientific-figure/v1",
        "generator": "docs/principles_assets/render_demo_pressure.py v1",
        "matplotlib_version": matplotlib.__version__,
        "python_version": platform.python_version(),
        "scope": "Read raw CSV and plot every exported sample; no solver, smoothing, fitting or time alignment",
        "input_sha256": {
            name: sha256((ROOT / name).read_bytes()).hexdigest() for name in sources
        },
        "rows": {name: len(trace[0]) for name, trace in traces.items()},
        "svg_sha256": sha256(output.read_bytes()).hexdigest(),
    }
    (OUT / "demo_root_pressure_provenance.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Created {output}; Matplotlib {matplotlib.__version__}")


if __name__ == "__main__":
    main()
