# 给 Codex 的起始入口

## 目标和阶段
这是从 r2 交接原型持续迭代的 IABP 定时算法物理引擎仓库。用户已确认 r1 需求。
当前能力和证据以 `docs/STATUS.md` 为准；目标架构不能因现有实现而缩水。
按 `AGENTS.md → docs/STATUS.md → ROADMAP.md → docs/plans/NEXT_ITERATION.md → docs/tasks/BACKLOG.md → 选中票SPEC` 阅读。
文档职责见 `docs/README.md`。不要先改网页样式，也不要重问已确认的输入输出边界。

## 当前任务入口
接手复现 B00 已完成，冻结证据及跨平台差异见 `docs/tasks/B00_REPORT.md`。
B01 已完成独立模块的声明范围验收，数值、适用域与后续缺口见 `docs/tasks/B01_REPORT.md`。
当前能力看 `docs/STATUS.md`，逐票状态看 `docs/tasks/BACKLOG.md`，执行顺序只看 `docs/plans/NEXT_ITERATION.md`。
开始时先核对 HEAD 与并行分支；环境基线复现属于 C00，不是重复实施 B00/B01。
B01 的独立一维传播与公开基准不能替代 B04 的心脏耦合或 5 ms 端到端验证。
数理解释见 `docs/MATHEMATICAL_PRINCIPLES.html`，持续维护步骤见
`docs/PRINCIPLES_MAINTENANCE.md`。

## 在项目根目录执行
```
python -m venv .venv
# 激活 .venv：Windows PowerShell 为 .venv\Scripts\Activate.ps1；类 Unix 为 source .venv/bin/activate
# Windows 的 GBK 默认环境先执行：$env:PYTHONUTF8 = '1'
python -m pip install -e ".[dev]" -r requirements-validation.lock
python -m pytest -q
python -m tools.numerical_check
python -m examples.run_demo
```
已有 Python/pytest/scipy 时，可不安装项目直接在根目录运行上面三个 `python -m ...` 命令。
核心运行无第三方依赖；SciPy 仅供独立参考核验，pytest 供测试。
验证 Python 的版本与 dependencies 记录，不将环境差异误当作模型变更。

## 按任务读取边界
用途、物理/时间硬规则和决策权限读 `AGENTS.md`；已实现能力和未验证项读 `docs/STATUS.md`。
组件、本构、时钟和当前连接方式读 `docs/ARCHITECTURE.md`；参数与缺失数据分别读 `docs/PARAMETERS.md`、`docs/DATA_GAPS.md`。
本入口不复制第二份能力清单；远端 CI 与 Git 同步状态以实际查询为准，不由旧报告推定。

## 建议交给 Codex 的第一段话
> 按 START_HERE.md、AGENTS.md 和 docs/plans/NEXT_ITERATION.md 接手。先核对当前HEAD、任务状态与证据，选择尚未被领取且前置条件满足的任务。已验收的B00/B01不重复开发；每个新切片先固定输入/验收，后实现和保存原始结果。保留历史内容，不改最终0D/1D路线，不调参掩盖失败；实际结果与未覆盖风险分别写清，不宣称临床验证完成。

## 复现与证据注意
上述快速命令不覆盖完整独立1D求解。新目录/新环境或相关源码改变时，按根README和当前计划实际重跑独立1D，再执行集成门。
`--collect`仅核验旧结果身份；不要将它叫做当前环境重新求解。先冻结旧证据，避免覆盖唯一历史。

## 本地与云端
可直接将解压后的目录作为本地 Codex 工作目录；云端使用时先放入用户自行管理的仓库并配置开发依赖。
本包用项目根目录的 AGENTS.md 保存持续规则，而不是要求 Codex 记住这段聊天。
官方说明： https://developers.openai.com/codex/guides/agents-md
