# Cardiac Dynamics Engine

面向 IABP 定时算法研发和软件在环试验的心脏动力学引擎。当前包含连续 0D 桥接原型和已独立验证的 1D 动脉传播模块。
最终路线保持 **0D 心脏/回流 + 1D 动脉 + 分布式球囊**；目前尚未完成这三者的联合耦合验收。

当前用途为工程研发，不能作为临床精度或疗效校验标准。约 5 ms 是尚待验收的端到端工程目标。

## 阅读入口

| 入口 | 内容 |
|---|---|
| [数理原理文档](docs/MATHEMATICAL_PRINCIPLES.html) | 第一性原理推导、离线公式、框架/时序/控制体图与真实运行证据 |
| [固定观察器](artifacts/demo/prototype_viewer.html) | 三页读取真实心脏/时序、独立 1D 与冻结迭代数据；打开即预载当前包和历史 r2 对照 |
| [总路线图](ROADMAP.md) / [当前迭代计划](docs/plans/NEXT_ITERATION.md) | 长期阶段、依赖、下一轮顺序及出口条件 |
| [文档地图](docs/README.md) | 各文档的职责、状态主源、读取与更新规则 |
| [当前状态](docs/STATUS.md) / [任务登记表](docs/tasks/BACKLOG.md) | 已完成能力与证据、逐票状态及缺口 |
| [B00 报告](docs/tasks/B00_REPORT.md) / [B01 报告](docs/tasks/B01_REPORT.md) | 冻结复现、数值差异、固定门槛与适用域 |
| [B00/B01 历史交付摘要](docs/DELIVERY_NOTES.md) | 2026-10-15 的提交、实际检查与未覆盖风险；后续交付看各票报告 |
| [开发入口](START_HERE.md) / [工作规则](AGENTS.md) | 后续接手约定与验收要求 |
| [数理文档技能](skills/mathematical-principles/README.md) / [验证记录](artifacts/skills/mathematical-principles/README.md) | 手动创建、局部更新或只读检查数理文档；可用于其他项目 |
| [固定迭代观察器](docs/viewer/README.md) / [数据合同](docs/viewer/DATA_CONTRACT.md) | 心脏/时序、独立 1D、冻结迭代比较；使用同一界面刷新真实运行数据包 |

克隆后用本地浏览器打开上述 HTML。正文和观察器均可离线使用；GitHub 文件页仅显示 HTML 源文件。
公式、图表和观察器的实际核验范围统一见相应维护说明及交付报告。

## 能力与证据入口

当前已实现能力、验证等级和缺口统一维护在 [STATUS](docs/STATUS.md)，逐票状态统一维护在 [BACKLOG](docs/tasks/BACKLOG.md)。
软件计数与源码身份读取 [质量门记录](artifacts/verification_summary.json)；独立传播结果与历史失败读取 [B01 报告](docs/tasks/B01_REPORT.md) 和 [数值汇总](artifacts/arterial1d/benchmark_summary.json)。
观察器的实际检查与浏览器限制见 [V1 核验](docs/viewer/ACCEPTANCE.md)。README 不维护第二份结果数字表。

## 安装与快速运行

生产核心仅依赖 Python 标准库，要求 Python 3.11+。下例使用本轮已验证的 Python 3.12；开发依赖由 `pyproject.toml` 声明，数值验证版本由 `requirements-validation.lock` 固定。

```powershell
git clone https://github.com/wangcy03/Cardiac-dynamics-engine.git
cd Cardiac-dynamics-engine
py -3.12 -m venv .venv
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]" -r requirements-validation.lock
python -m pytest -q
python -m examples.run_demo
```

类 Unix 环境使用 `python3 -m venv .venv` 和 `source .venv/bin/activate`。
演示导出位于 `artifacts/demo/`；`*_samples.csv` 是算法可见样本，`*_truth.csv` 仅供评估。
网页只读取这些导出，不合成另一套物理波形。

## 完整数值与质量门

首次在新机器或新目录中验收，先实际运行四套独立传播基准，再执行集成门和文档刷新：

```powershell
python -m tools.arterial1d_check --case all
python -m tools.verify_all
python -m tools.update_principles_evidence --export-diagrams
python -m tools.update_principles_evidence --check --export-diagrams
```

第一条命令会实际求解并生成该环境的运行证据，耗时较长。当前已提交的 1D 证据包含运行时工具路径；换目录后不能直接把旧路径身份当作本机复现。
`python -m tools.arterial1d_check --collect` 仅核验既有运行的源码、输入、CSV、JSON 和日志，不再次求解；`verify_all` 的 1D 门使用此模式。
不要改写旧哈希、放宽门槛或逐工况重调参数来使检查通过。生成的证据应连同环境和范围一起审查。

修改模型后还须实际运行 `python -m examples.run_demo`；更新正文公式、假设和对应图表，并按[维护约定](docs/PRINCIPLES_MAINTENANCE.md) 刷新证据。
CI 配置位于 [.github/workflows/ci.yml](.github/workflows/ci.yml)，覆盖 Ubuntu/Windows、Python 3.11/3.13 的软件门与 0D 数值；不能替代四套完整 1D 求解或临床验证。
CI 是否通过以 GitHub 实际运行结果为准。

## 实现与后续边界

0D 原型包含九个有限容积结点、四心腔、四动态瓣膜和电/机械激活分离，持续推进状态；调度层提供因果多通道交付、独立随机流、命令预约/取消/反向和同进程完整快照。
可关闭的单结点球囊接口提供占据容积、保持阻塞及负荷相关动作试验，尚无真实执行器标定。

独立 1D 模块提供均匀弹性管守恒方程、特征边界、共同静压分叉、实际面通量账本及 CFL/非法状态显式失败。0D 核心使用 mmHg/mL/s 与整数微秒接口，独立 1D 内部使用 SI，转换集中在 `iabp/units.py`。

下一轮顺序与前置门统一维护于 [当前迭代计划](docs/plans/NEXT_ITERATION.md)，任务状态见 [BACKLOG](docs/tasks/BACKLOG.md)。长期保持 B04 双向联合耦合后再接 B05 分布式球囊的路线。
完整能量账本、真实测量链/执行器校准、患者或动物适用域及临床验证尚未完成。
演示中辅助峰压虽升高，窗口出流略降、LV 窗口做功略升；不以峰压增加宣称辅助有效。

## 目录与证据保留

| 目录 | 职责 |
|---|---|
| `iabp/` | 核心模型、调度/契约、单位转换和独立 `arterial1d/` |
| `tests/`、`tools/`、`examples/` | 行为/回归测试、数值与证据工具、因果反馈示例 |
| `docs/` | 正式原理、架构、需求、任务、交付与维护说明 |
| `artifacts/` | 真实运行记录、CSV/JSON、日志、公开参考与历史对照 |
| `legacy/`、`docs/reference/` | 原教学页面及研究/需求原文，保持原始字节 |

根目录 `SHA256SUMS.txt` 是 r2 导入时的原始清单；最新源码身份见 `artifacts/verification_summary.json`，各数值 run 另有输入、源码快照与产物哈希。
`.gitattributes` 保留文件原始字节，避免换行转换破坏证据身份。公开参考的数据许可和来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
