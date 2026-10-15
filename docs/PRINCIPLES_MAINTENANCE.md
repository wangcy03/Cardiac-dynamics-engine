# 数理原理文档维护约定

`docs/MATHEMATICAL_PRINCIPLES.html` 是正式、持续维护的工程原理正文。它与需求基线、实现和证据一起演进，不能用本文件或页面排版完整来替代模型验收。

可手动调用 `$mathematical-principles update` 或 `check` 接续本流程；可复用技能源码与跨项目用法见 [技能说明](../skills/mathematical-principles/README.md)。
本文件保留本项目的具体约定，通用技能优先复用这里的刷新器和已有产物。

## 文件责任与依赖

| 文件 | 作用 | 维护方式 |
|---|---|---|
| `MATHEMATICAL_PRINCIPLES.html` | 中文原理、MathML/LaTeX、3 幅内联框架／时序图、实际证据 | 正文人工维护；有界证据区由工具替换 |
| `../tools/update_principles_evidence.py` | 读取真实 JSON/CSV，重新积分导出值，记录 SHA-256 | Python 3.11+ 标准库；不运行求解器、不改参数或任务状态 |
| `principles_assets/architecture.html`、`causal_sequence.html`、`control_volumes.html` | 与正文原图完全一致的独立离线预览 | `--export-diagrams` 派生，不单独编辑 |
| `principles_assets/render_demo_pressure.py` | 可选科学绘图：全量 truth CSV → 独立 SVG | 需要选定文档环境已有 Matplotlib；不加入核心或开发依赖 |
| `principles_assets/demo_root_pressure.svg` 与配套 provenance | 实际配对运行的根部压力图、绘图环境及输入哈希 | CSV 更新后重新绘制；身份不一致时证据工具拒绝内联陈旧图 |

公式以 MathML 原生排版，`annotation[encoding="application/x-tex"]` 和折叠区保留 LaTeX 源。不依赖 MathJax、KaTeX、CDN 或网络字体；默认采用 diagram-design 浅色，字体使用本机回退。

## 每票执行流程

1. 先确定变更影响的物理对象、状态、单位、边界、事件与证据范围；读对应规格、ADR 和当前源代码。
2. 涉及方程／事件／方法时，同一变更更新正文解释、MathML、LaTeX 源、代码映射与适用域。若改变项目保留的架构／风险／事件决策，按 AGENTS.md 提交 ADR 决策。
3. 按项目门运行测试、数值核验与静态检查；保留失败、缺失、拓扑变化与未运行项。更新模型后重新运行真实 demo。
4. 若真实 demo CSV 或 provenance 变化，使用已安装 Matplotlib 的文档 Python 执行 `python docs/principles_assets/render_demo_pressure.py`。工具只读导出，不求解或平滑波形；绘图依赖及版本独立于项目 `.venv`。
5. 在仓库根目录执行：

   ```powershell
   python -m tools.update_principles_evidence --export-diagrams
   python -m tools.update_principles_evidence --check --export-diagrams
   ```

6. 检查第 8 节是否引用本票最终产物，区分 B00 冻结复现、最新聚合记录、0D 数值研究和独立 B01 基准。阅读缺失事件列表和代码／产物身份差异，不能只看文件声明的 PASS。
7. 图表有变更时，对三个派生 HTML 运行安装的 diagram-design `scripts/self_check.py --offline`；检查连接正交、标签与连线的间隙、节点预算、图例、中文字体回退及局部横向滚动。
8. 在支持的浏览器环境查看长文、公式、SVG 和本地观察器链接；检查常规宽度与窄屏。只有实际完成渲染／交互检查后才记录对应通过；静态检查不冒充浏览器渲染。

## 证据区的数据约定

证据刷新仅替换 `PRINCIPLES_EVIDENCE_START` 与 `PRINCIPLES_EVIDENCE_END` 之间的内容。正文和任务状态不自动改写，旧教学与研究归档不修改。

- `artifacts/verification_summary.json`：软件质量门、环境、计数及未验证边界。退出码缺失就显示未记录；不能凭 PASS 补 0。
- `artifacts/numerical_check.json`：相同物理时间的 0D 步长比较。事件值为 `null` 时保留缺失事件名称，只对已有有限数值求最大差；事件缺失与拓扑不匹配独立显示，不能把剩余子集写成全事件通过。
- `artifacts/b00/baseline_comparison.json`：B01 开始前的跨环境冻结复现，历史身份不能被最新聚合结果覆盖。
- `artifacts/arterial1d/benchmark_summary.json`：独立传播模块的方法／网格／边界与基准记录。关键指标分为历史一阶、历史 MUSCL、当前第三方案和公开数值参考表；极值／过冲另列，缺字段保持未记录。原 JSON 在折叠区保留，并提供完整原文件链接和哈希。
- `artifacts/arterial1d/history/pre_linear3/manifest.json`：新增第三方案之前的原始核心、工具与失败结果归档；不得用当前方案的通过状态覆盖历史精度不足。
- `tools.arterial1d_check --collect`：核查已实际完成 case 的源、结果、CSV、运行日志身份后收集，不重复求解。维护时分别阅读收集门退出码、原始求解日志与各方案精度状态；历史记录仅作对照。
- `artifacts/demo/provenance.json` 与两份 truth CSV：实际运行配置和同初态配对导出。窗口出流用相邻实际时间差作梯形积分，窗口 LV 净外部功为 `−Σ P_avg ΔV`；不命名为单搏 SV 或闭合稳态环功。
- 源文件 SHA-256：标明刷新时读取的文件身份。provenance 中 model.py 哈希不符时显式显示 `DIFFERENT`，不自动声称输出来自当前源代码。

缺失文件保留 `NOT_FOUND`。无效 JSON、缺少必需 truth 列、非有限数值、非递增 CSV 时间或图像哈希不符会显式报错，工具不会修复数据来获得通过。`--check` 只比较派生内容，陈旧则退出 1；不写文档或图表。`CURRENT` 只表示文档与当前磁盘记录一致，不表示其模型验收通过。

## 图表与科学图的范围

三幅正式示意图采用 doc-wide（1280×720），分别为 6 节点架构、5 生命线时序、3 控制体守恒／传播图。它们展示结构与因果关系，不生成示意生理压力峰。箭头标签与主体字体区分，中文标签至少 12 px，本机字体可影响字形度量。

科学波形图使用 Matplotlib 常规坐标轴和真实 CSV 全量样本直线连接，输出独立 SVG 后内联；它不是 diagram-design 的示意折线模板。图与配套 provenance 均可独立查看。整篇正式文档有必要的远程学术引用链接，因此 diagram-design 的“单图不含远程引用”检查应施加于三个无外部依赖的图表预览；整篇文档另做结构、链接与公式检查。

本轮访问浏览器时，工具明确拒绝 `file:` 协议并指示不得绕过。已停止浏览器尝试；这不影响离线文件交付和静态检查，但不能据此记录本轮浏览器渲染通过。

## 不得自动升级的结论

0D 时间收敛、1D 独立解析基准、公开数值参考复现、全引擎耦合、分布式球囊、全能量核验、真实传感／执行器校准及患者／动物适用域各有自己的证据。软件测试通过不写为临床验证完成；约 5 ms 的工程目标不改称安全常数。

`linear3_ssprk3` 是至少 3 格、无 TVD 限制器的光滑小振幅实验方案。它的阶段边界时刻是 t、t+Δt、t+Δt/2，界面通量和源项权重是 1/6、1/6、2/3。每次更新须核对重建、阶段、权重和原子失败语义。当前 min/max 覆盖全部单元的已记录观察时刻：工程匹配每 0.5 ms，公开参考仅 8 个剖面时刻，不是所有内部步或 RK 阶段。过冲为 `max(0,maxP/reference_peak−1)`，下冲为 `max(0,−minP/reference_peak)`；压力原值不截断。出现过冲、下冲或振铃须保留，不能借 SSPRK 名称外推为激波或生理场景的 TVD 保证。

Boileau 本轮对照为公开数值输出，不是物理实验数据。原始六法与 FVM 的差异含自身数值离散和输出采样差；即使某一方法达到本项目门槛，也不能把 FVM 当作唯一精确真值。
