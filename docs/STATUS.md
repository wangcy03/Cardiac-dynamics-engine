# 当前状态：B00、B01 已完成声明范围验收；正式原理文档已建立

日期：2026-10-16。用途仍是研发/软件在环。r0/r1 已归档，不覆盖。

## 当前开发接手状态

- B00 已完成：Windows/Python 3.12.9 下复现原始 51 项测试和三档 0D 数值基线，
  ruff、strict mypy 实际通过。原始核心、legacy/ 和 docs/reference/ 字节哈希保持一致。
  冻结差异报告见 `tasks/B00_REPORT.md`，最大压力误差指标变化为 1.28e-13 mmHg。
- 独立 1D 核心已实现：默认一阶 Rusanov、独立 MUSCL/SSPRK2 和限光滑小振幅的
  非 TVD linear3/SSPRK3；特征边界、共同静压分叉、实际通量/体积账本、CFL 与失败原子性。
  34 项核心/单位行为测试已通过，未将其接入 0D 或球囊。
- 本地工程脉冲的 linear3 320 格候选：峰差约 0.146%，固定阈值到达误差约 0.047 ms。
  一阶与 MUSCL 的所有低精度结果另行保留，没有修改输入、参数或门槛。
- 公开 Boileau CC0 输入与八个空间剖面已实际复现：linear3 的 640/1280/2560 格
  最大压力差为 7.42675 / 3.01328 / 0.676452 Pa，细档归一误差 3.27628%，
  满足预置 5% 工程门槛；粗档失败及细档 −0.0189585 Pa 振铃保留。
- 独立复审发现的反射空覆盖/汇总标志及公开数据身份覆盖缺陷已修复：
  34 项基准工具回归与独立 23 项无求解故障探针通过；旧进程中止记录原样留档。
  最终固定工具已重新实际完成四个数值套件（18 个 run），源码/数据/CSV/日志身份均核验。
- B01 完成时（2026-10-15）的 `python -m tools.verify_all` 退出 0：121 项测试，0 失败/错误/跳过；
  compileall、0D 数值、ruff、mypy 和独立 1D 证据门全部 PASS。
  修改后演示已实际运行，保留原有增压但输出略降、做功略升的工程结果。
- 正式 `MATHEMATICAL_PRINCIPLES.html` 已含 19 组离线 MathML/LaTeX、框架与时序图、
  真实 CSV 压力图和原型观察器链接；按 `PRINCIPLES_MAINTENANCE.md` 持续维护。
  静态图表/公式检查已过；浏览器 file: 协议被策略拒绝，实际渲染为 NOT_RUN_BROWSER_POLICY。
- 数理文档流程已封装为可手动调用的 `mathematical-principles` 技能，版本源在
  `../skills/mathematical-principles/`；22 项静态工具回归与两个合成项目对照记录见
  `../artifacts/skills/mathematical-principles/README.md`。技能封装时未改模型或重跑上述心脏数值门。
- 固定迭代观察器已实现心脏/时序、独立 1D、冻结迭代比较三页；兼容 HTML 入口读取
  33 列真值、采样/事件/命令及 28 个 1D 对照，历史失败和部分源码身份保持可见。
  UI 固定源码与版本化真实数据包分离，使用与更新见 `viewer/README.md`；
  本轮六项软件门 PASS、171 项 Python 与 25 项 Node 测试通过；demo 真实重跑后 9 份原始导出字节未变。
  核验和范围见 `viewer/ACCEPTANCE.md`，浏览器渲染仍未验收。
- Git 已初始化，分步保留原始导入、B00、独立核心与最终证据；origin 指向
  `https://github.com/wangcy03/Cardiac-dynamics-engine.git`。推送/上游状态以 Git 为准，CI 以远端实际运行为准。

最终质量门读取 `../artifacts/verification_summary.json`，B01 数值读取
`../artifacts/arterial1d/benchmark_summary.json`，范围与未覆盖项见 `tasks/B01_REPORT.md`。
核心/基准/文档/两轴复审的工作记录在 `tasks/reports/`。

## 历史背景

原始 r2 导入的检查和分工见 [原始交接](../handoff/IABP_Codex_Handoff_r2.md)、[原始自审](REVIEW.md)；接手复现见 [B00 报告](tasks/B00_REPORT.md)。
这些历史记录保留原路径，不再在当前能力摘要重复展开。当前执行顺序只看 [NEXT_ITERATION](plans/NEXT_ITERATION.md)，逐票状态只看 [BACKLOG](tasks/BACKLOG.md)。
