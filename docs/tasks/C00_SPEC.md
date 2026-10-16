# C00：基线、持续回归与证据门强化

工作状态见 [BACKLOG](BACKLOG.md)。这是持续工程任务，不重新打开 B00。
依据：[当前状态](../STATUS.md)、[已有运行入口](../../README.md)、`tools/verify_all.py`。

## 目标和范围

让新环境、每次修改和远端 CI 都能明确区分“实际求解”“核验旧证据”“未运行”。
本票不改物理参数、数值门槛或核心事件，不升级任何生理资格。

## 切片与验收

| 子项 | 输入/动作 | 完成条件 |
|---|---|---|
| C00.1 固定基线 | 记录 HEAD、diff、环境、输入与已提交证据；安装既有锁定验证环境 | 命令/返回码/源码及数据身份清楚，旧失败与中止记录原样保留 |
| C00.2 分层回归 | 软件门+Node+1D轻量回归；数值相关变更触发完整独立1D | 轻量测试实际跑求解，不仅 --collect；不将未执行完整套件写成通过 |
| C00.3 CI 与证据身份 | 保留已有跨平台矩阵，区分锁定参考环境与兼容性环境 | 引入故意的失败/缺失/过期记录时，汇总非PASS；真正运行后保存命令/日志 |

## 当前可用命令

```text
python -m pip install -e ".[dev]" -r requirements-validation.lock
python -m pytest -q
python -m compileall -q iabp tools examples
python -m ruff check iabp tests tools examples
python -m mypy iabp
node --check viewer/viewer.js
node --test viewer/viewer.test.js
python -m tools.numerical_check
python -m tools.arterial1d_check --collect
```

`--collect` 为旧证据身份校核。需要当前环境完整求解时先执行：

```text
python -m tools.arterial1d_check --case all
python -m tools.verify_all
```

未改变核心时不要求为纯规划文档生成新数值证据。新机器/相关源码变化时不能只用旧路径身份通过。
Node 检查只验证软件，浏览器布局验收继续单独标注。

## 新增 CI 策略（待实现，不是本计划已经修改的工作流）

- 每次相关 PR：原软件门、Node、轻量传播/反射/分叉与证据工具的失败测试。
- `iabp/arterial1d/`、单位、边界、基准工具、参考输入或耦合相关改动：完整独立1D套件。
- 定期或人工触发完整套件作为补充；不能作为数值关键 PR 跳过必要核验的理由。
- Python 锁定参考环境与跨版本兼容环境分开命名；不强迫不兼容版本使用同一锁文件，也不静默更新锁文件。
- 原有输出目录可能被覆盖：先冻结，或使用独立工作树；新工具优先提供明确输出目录，拒绝覆盖同一 run ID。

## 交付

在 `tasks/reports/` 提交报告，列出本机实际执行及远端 CI 的独立状态。
修改映射和状态，不把本票新增测试计入生理通过数量。框架入口和文件存在性以当前仓库为准。
