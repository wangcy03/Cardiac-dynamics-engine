# 心脏引擎的既有维护入口

仅当工作目录是建立本技能的 Cardiac-dynamics-engine/IABP Engine 项目，且相应文件存在时读取本页。
其他项目沿用通用流程；这些单位、方案、数字和结论不是技能默认值。

## 复用入口

- 正式正文：`docs/MATHEMATICAL_PRINCIPLES.html`。
- 维护约定：`docs/PRINCIPLES_MAINTENANCE.md`。
- 有界证据刷新器：`tools/update_principles_evidence.py`。
- 刷新：`python -m tools.update_principles_evidence --export-diagrams`。
- freshness：`python -m tools.update_principles_evidence --check --export-diagrams`。
- 可选真实科学图：`docs/principles_assets/render_demo_pressure.py`，只读 CSV，使用已有 Matplotlib 环境。

起源版本有 19 组 MathML/LaTeX 公式、3 幅示意图（架构、因果时序、控制体），
以及独立科学图。这是版本快照，不是今后强制公式/图表数量。
三个独立示意图由正文导出，不单独修改：
`architecture.html`、`causal_sequence.html`、`control_volumes.html`。
正文的引用链接与单图自检的离线依赖检查分别处理。

## 证据范围与读取行为

| 输入 | 范围与注意事项 |
|---|---|
| `artifacts/verification_summary.json` | 软件质量门/环境/命令/退出码；文件声明不替代原始日志 |
| `artifacts/numerical_check.json` | 0D 同物理时间步长比较；缺失事件与有限子集最大差分别显示 |
| `artifacts/b00/baseline_comparison.json` | B01 前的冻结跨环境复现，保留历史身份 |
| `artifacts/arterial1d/benchmark_summary.json` | 独立传播器的方案、网格、误差、极值和身份 |
| `artifacts/arterial1d/history/pre_linear3/manifest.json` | 原方案与失败结果归档，不被当前通过覆盖 |
| `artifacts/demo/provenance.json` 与 truth CSV | 实际共享初态的配对运行，不合成压力曲线 |
| `artifacts/demo/prototype_viewer.html` | 现有原型观察器的真实运行入口；固定化按项目后续方案推进 |

`tools.arterial1d_check --collect` 核查已有 case 的源、结果、CSV 和运行日志后收集，
不重新求解；不要把收集门退出码叫作新求解的退出码。
当前文件哈希只是本次读取身份；运行记录未写源哈希时不回填为当前哈希。
证据刷新不自动运行模型、不改参数、不改状态，也不升级验证结论。

0D 配对窗口的净出流和 LV 净外部功分别从实际 CSV 时间差/状态差积分，
不能直接称为单搏 SV 或闭合稳态环功。峰压增加不能独自证明辅助有效。
观察到出流减少、做功增加或振铃时，原样展示联合结果。

## 不可混淆的路线与适用域

最终路线为 0D 心脏/回流 + 1D 动脉 + 分布式球囊；当前闭环演示仍为 0D 桥接原型。
独立 B01 通过不代表 0D/1D 耦合、分布式球囊、整体能量核验、仪器或临床校准完成。
约 5 ms 是工程目标。事件名称按项目定义；缺失不补固定时延，切迹不当关闭真值。
核心通常使用 mmHg/mL/s、整数微秒接口；B01 SI 单位经集中转换，不自行混换。

`linear3_ssprk3` 是光滑小振幅的实验方案，至少 3 格，无 TVD 限制器。
阶段时刻与通量/源项权重、重建和失败原子性按当前实现与冻结规格核查。
记录极值的观察时刻不涵盖所有内部步/RK 阶段，不能据有限采样声称不存在振铃。
Boileau 公开对照是多方法数值输出，不是物理实验或唯一精确真值；未复现项继续保留。

`legacy/` 教学 HTML 和 `docs/reference/` 研究原文保留，不作为新核心的测试 oracle。
可参考 `legacy/wiggers_complete_teaching_guide_v3_2_timing.html` 的信息组织，
但其中教学波形/固定时序不能冒充当前核心的真实导出。

## 浏览器与验证记录

起源会话的浏览器工具拒绝 `file:` 协议，并明确禁止绕过；该轮渲染记录为
`NOT_RUN_BROWSER_POLICY`。这是历史事实，不预先断言未来所有受支持浏览器都不可用。
后续遇到明确拒绝时停止，不改用本地服务器、代理、另一浏览器入口等规避限制。
静态检查、实际浏览器渲染、软件测试、数值验证、物理/临床验证始终分别记录。
