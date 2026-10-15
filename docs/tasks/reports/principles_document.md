# 正式数理原理文档交付记录

日期：2026-10-15。状态：**正文与离线图表已交付；实际浏览器渲染检查未运行，B01 总证据待主代理最终刷新。**

## 修改点

- `docs/MATHEMATICAL_PRINCIPLES.html`：中文持续维护正文，初稿 17 组、第三方案同步后共 19 组原生 MathML / LaTeX 方程。从质量守恒、RL 动量和弹性储能出发，描述当前 0D 心脏／回流、激活恢复、有限开口瓣膜、球囊体积／阻塞、因果测量和整数微秒调度，再连接独立 1D 壁本构、特征边界、分叉、有限体积与 CFL。
- 3 幅默认浅色 diagram-design 内联图：6 节点最终架构、5 生命线因果时序、3 控制体守恒／特征传播。当前桥接运行、B01 独立模块、B04/B05 后续集成分别说明。
- 明确保留一阶 Rusanov/Euler 基线，并解释 MUSCL（generalized minmod θ=1.5）/SSPRK2 为独立方法对照，不能靠改输入或改答案掩盖一阶耗散。
- `tools/update_principles_evidence.py`：标准库证据刷新器。读取真实 JSON/CSV，按实际相邻时间积分，记录读取文件的 SHA-256，比较 demo 的 model.py 来源身份；缺失文件、缺失事件、拓扑不匹配保持可见，不运行求解器或自动提升验收结论。
- `docs/PRINCIPLES_MAINTENANCE.md`：每票正文／公式／图／真实产物同步维护流程。
- `docs/principles_assets/`：由正文派生的三个独立离线图表预览；真实 CSV 的 Matplotlib 科学压力图及 provenance；可选绘图脚本。

旧教学、需求原文、核心方程、模型参数、任务状态和共享配置未由本子任务修改。未执行 Git 提交。

## 实际产物结合方式

第 8 节表格直接来源于磁盘证据，并链接完整 `artifacts/demo/prototype_viewer.html`。科学图连接两份 truth CSV 的全部样本，无平滑、时间平移、重新求解或参数拟合。生成器使用本机已有 Matplotlib **3.10.5**，不新增核心或开发依赖；输入 CSV／provenance 哈希及 SVG 哈希保存在配套 JSON。

当前独立图显示无辅助与演示辅助根部压力；必须与同窗净主动脉出流和 LV 净外部功共同阅读。窗口量未改名为单搏 SV 或闭合稳态 PV 环功。

## 验证结果

| 检查 | 结果与范围 |
|---|---|
| `python -m tools.update_principles_evidence --export-diagrams` | 退出 0；替换有界证据区并派生 3 个图表预览 |
| `python -m tools.update_principles_evidence --check --export-diagrams` | 退出 0，CURRENT；只说明当前文档与磁盘记录一致 |
| diagram-design `self_check.py --offline`，三个独立图表 HTML | 全部退出 0；访问性、单文件资源与 viewBox 静态门通过 |
| `python -m ruff check tools/update_principles_evidence.py docs/principles_assets/render_demo_pressure.py` | 退出 0，All checks passed |
| `python -m compileall -q tools/update_principles_evidence.py docs/principles_assets/render_demo_pressure.py` | 退出 0 |
| HTML 结构／唯一 ID／本地锚点 | 通过；104 个唯一 ID，HTML 嵌套闭合，无活动 iframe/object/script 或远程资源加载 |
| MathML / LaTeX | 当前 19 个 MathML 片段均可按 XML 解析，均有非空 `application/x-tex` annotation；折叠区保留源码 |
| SVG 结构与访问性 | 4 个内联 SVG（3 示意图 + 1 科学图）均可 XML 解析，均含首子元素 title、desc 与解析到的 ARIA ID |
| 本地链接 | 除尚未生成的 `artifacts/arterial1d/benchmark_summary.json`（正文与身份表各 1 处）外全部存在；缺失处显示 NOT_FOUND，不伪造证据 |
| 外部学术引用 | 5 处普通超链接，指向 2 个已浏览的一手来源；不在页面加载时自动取回资源 |
| 缺失事件／拓扑边界 | 构造含 `QAO_ZERO=None`、另一个有限事件值及 topology=False 的记录，确认缺失名、数值差和拓扑状态分别显示；不崩溃或提升通过 |
| 缺失 pytest 计数 | `pytest_counts=None` 显示未记录 |
| 检查模式无写入 | `export_diagrams(..., check=True)` 前后正文及三个派生图 SHA-256 不变 |
| 实际浏览器渲染 | **NOT_RUN_BROWSER_POLICY** |

整篇技术文档包含必要的远程学术引文，直接对长文运行“单图禁止远程引用”的 self_check 会仅因这些引用报错。因此该技能检查施加于与正文相同源图的三个无外部依赖预览；整篇另做上述结构、公式与链接检查，不把静态检查写成浏览器通过。

## 浏览器限制的原始证据

工具：`mcp__cua_repl.js`。尝试打开本地正式 HTML 的 `file:` 地址时，返回：

> Browser Use rejected this action due to browser security policy. … The requested URL protocol is not allowed. Allowed protocols: "http:", "https:". The agent must not attempt to achieve the same outcome via workaround, indirect execution, raw CDP or browser commands, alternate browser surfaces, or policy circumvention.

已按策略停止浏览器尝试，未通过本地服务器、其他浏览器或间接执行重试。主代理保留最终浏览验证的边界记录。

## 数值变化与仍未覆盖范围

本子任务只维护文档与读导出工具，没有改变物理核心或参数，不产生新的模型数值误差变化。当前数值差、血量残差及跨环境复现差从 B00 与根目录真实记录读取；CSV 推导指标与 provenance 的差也在折叠表中保留。

B01 基准仍在执行，交付时文档没有预先宣布 B01 总通过。主代理最终运行完成后，再执行证据刷新命令即可纳入基准 JSON。读到该文件仍不自动代表 0D/1D 整体耦合、分布式球囊、全系统能量核验、真实仪器校准或临床验证完成。

未覆盖实际宽／窄屏浏览器排版、实际字体度量与打印渲染；结构检查只证明静态源满足相应约束。MathML 可读排版依赖现代浏览器原生实现，LaTeX 原文始终保留。

## 第三方案文档同步（同日追加）

按主代理授权，依据 core 代理冻结的实际 `solver.py` 同步 `linear3_ssprk3`：内部与端点三阶有限体积重建、至少 3 格限制、SSPRK3 阶段时刻 t / t+Δt / t+Δt/2，以及实际界面通量和源项权重 1/6 / 1/6 / 2/3。新增公式 (15c)、(15d)，总共 19 组。明确该方案无 TVD 限制器，仅属光滑小振幅实验域，可能振铃，不能扩展为激波／生理场景保证。

证据工具按最终约定 schema 增加：历史一阶、历史 MUSCL、当前第三方案的工程误差表；历史与当前公开数值参考表；各方法极值、参考峰过冲／下冲与逐剖面表；原始结果／run 日志路径和记录哈希；保留完整 JSON 链接。历史精度不足不会被新方案状态覆盖。

极值的准确范围是全部单元在记录观察时刻：工程匹配每 0.5 ms，公开参考仅 8 个原始剖面时刻，不冒称涵盖所有内部步或 RK 阶段。过冲为 `max(0,maxP/reference_peak−1)`，下冲为 `max(0,−minP/reference_peak)`，压力原值不截断。

正文与维护说明区分实际求解 run 与 `--collect` 身份核验门：后者不重复求解，核对已完成 case 的源、结果、CSV、日志后收集。`mode=EVIDENCE_GATE_NO_SOLVER_RUN`、质量门退出码和实际 run 证据分别阅读。Boileau 是公开数值参考，不写作物理实验数据；六法离散与输出采样差意味着 FVM 不构成唯一精确真值。

未运行浏览器；`browser_render=NOT_RUN_BROWSER_POLICY` 保持。没有提前宣布第三方案或 B01 总体通过，最终聚合由主代理执行。

本次增量检查：ruff、compileall 均退出 0；19 组 MathML/LaTeX 静态解析通过；以原始历史结果和仅存在于内存的第三方案边界夹具核查表格，确认历史／当前分组、缺失到达值、未通过候选门、过冲／下冲百分比、日志链接与 HTML 转义正确。缺失 summary 仍显示 NOT_FOUND，不凭表格存在生成总体 PASS。图表静态门与证据 freshness 在同步后各执行一次。

## 最终产物纳入后的静态复核（同日，当前结果）

主代理完成最终聚合并刷新正式 HTML 后，本次只读复核确认真实 `artifacts/arterial1d/benchmark_summary.json` 已纳入正文；先前记录的 summary 缺失是历史状态，现已消除。该文件声明 `mode=EVIDENCE_GATE_NO_SOLVER_RUN`、`engineering_status=PASS`、`public_benchmark_status=PASS_DECLARED_ENGINEERING_TOLERANCE`。这些状态仍限已声明工程与公开数值参考范围，不代表临床验证或整体 0D/1D 集成完成。

| 当前检查 | 结果 |
|---|---|
| `python -m tools.update_principles_evidence --check --export-diagrams` | 退出 0，CURRENT；正文证据与当前磁盘来源一致，三个派生图与正文源图一致 |
| 三个派生图 `self_check.py --offline` | 全部退出 0：architecture / causal_sequence / control_volumes |
| HTML 结构与 ID | 嵌套闭合，104 个唯一 ID，无重复 |
| 本地链接与锚点 | 74 个本地 href 与 10 个锚点均存在；缺失列表为空 |
| MathML / LaTeX | 19 个 MathML 片段均通过 XML 解析，19 个非空 LaTeX annotation 与 19 个源码折叠区齐备 |
| 内联 SVG | 4 个（3 示意图 + 真实 CSV 科学图）均可 XML 解析，首子元素 title、desc、ARIA 引用完整 |
| 活动嵌入／自动外部资源加载 | 未发现 script / iframe / object / embed 或 src 资源加载；5 个外部学术引用是普通链接 |
| 浏览器渲染 | `NOT_RUN_BROWSER_POLICY` 保持，未尝试浏览器 |

本次没有改写 HTML、工具、核心、参数或其他文档，没有重跑数值，只追加此报告。原始检查与当时缺失状态保留在前文，当前结论以本节为准。
