# IABP 定时引擎 · r2 初步开发包

**状态：工程原型，可移入 Codex 继续开发；尚不能用作临床精度或疗效校验标准。**

从 `START_HERE.md` 开始。当前需求保留在 `docs/reference/`，旧页面在 `legacy/`。

正式原理入口：[数理原理文档](docs/MATHEMATICAL_PRINCIPLES.html)。
它从守恒、动量、弹性与因果关系解释当前实现和最终路线，
包含 LaTeX/离线公式、框架图、时序图及真实运行证据；
迭代维护流程见 [PRINCIPLES_MAINTENANCE.md](docs/PRINCIPLES_MAINTENANCE.md)。
本次接手的冻结基线与环境差异见 [B00_REPORT.md](docs/tasks/B00_REPORT.md)。

## 已能运行
- 九个有限容积结点、四心腔和四动态瓣膜，持续推进而非每搏重置。
- 电事件与机械激活分离，保留有限上升/松弛和简单恢复状态。
- 因果多通道采样、滤波、独立随机流、源时钟/未知时间、交付延迟。
- 预约/取消/反向/重复/迟到命令语义和日志。
- 完整同进程快照分叉；无辅助与只读取 ECG 的示例控制器轨迹对比。
- 可关闭的球囊占据容积/局部阻塞/负荷相关动作实验，不是经验证的执行器。
- 单元/集成测试、独立 Radau 对照、三档时间步长检查和离线观察器。
- 独立均匀弹性管 1D 传播、特征边界、守恒分叉与分列的数值方案；尚未与 0D/球囊耦合。

## 运行
```
python -m pytest -q
python -m tools.numerical_check
python -m examples.run_demo
```
完整本地门使用 `python -m tools.verify_all`；独立 1D 基准使用
`python -m tools.arterial1d_check`。完成核验后运行
`python -m tools.update_principles_evidence --export-diagrams`，
并用 `python -m tools.update_principles_evidence --export-diagrams --check` 检查文档证据是否同步。
打开 `artifacts/demo/prototype_viewer.html`。图从 Python 核心导出，浏览器不重新拼接生理波形。
`*_truth.csv` 只给评估器；`*_samples.csv` 为算法可见样本；两者不能混用。

## 目录
`iabp/` 核心与契约；`tests/` 可执行测试；`examples/` 因果反馈示例；`tools/` 核验/导出；
`docs/` 架构、路线、规则、参考原文；`artifacts/` 本次实际运行证据；`legacy/` 原教学页面。

不要把血量残差或步长差异解释为真实患者精度。5 ms 仍为工程目标，尚未验证。

根目录 `SHA256SUMS.txt` 保留 r2 导入时的原始清单，用于交接复现和归档核对；
后续源码身份读取最新 `artifacts/verification_summary.json`，
数值运行和文档分别保留其输入、源码及产物哈希。
