# Standards 只读审查

日期：2026-10-15。结论：**无阻塞发现；无须为代码气味强行追加修改。**

范围：原始导入 `fc18650722adbfbd05e4077cda456a8dc4bbd82e` 到当前工作树；审查时 HEAD 为 `046a1f6a9d5985b88f2daa175c530581073de041`。除已跟踪差异，直接读取了未跟踪的 `iabp/arterial1d/`、单位层、测试和文档证据工具。依据 `AGENTS.md`、`docs/ARCHITECTURE.md`、`docs/tasks/B01_SPEC.md`，应用 code-review 的 Standards 轴；未重复报告 ruff/mypy 可覆盖的样式。

## 已核实

- 生产新增模块的绝对导入仅为 `dataclasses`、`math`、`typing`；没有第三方依赖，没有引用心脏、球囊、控制器或 UI。`pyproject.toml:15` 的包发现结果包含 `iabp` 和 `iabp.arterial1d`。
- `iabp/units.py:8` 集中定义 SI 与 mmHg/mL 换算；整数微秒接口拒绝无法表示的时间。独立传播器内部秒制与 B01 明示的 SI 范围一致。
- `iabp/arterial1d/physics.py:29`、`solver.py:84` 拒绝非有限值和非正面积，未发现用压力／面积 clipping 隐藏失败。边界保持一进一出特征的亚临界适用域；失败显式抛出。
- `solver.py:496` 先完成全部段的全部阶段与候选状态验证，再提交状态和积分。分叉以共同静压求解，并让母管使用同一子管流量和；特征修正有独立舍入预算。
- `tools/verify_all.py` 保留退出码、日志和源码哈希，旧 pytest XML 先失效；缺少静态工具不能聚合为全部通过。B00 原始冻结记录与当前聚合身份分开，文档刷新仅读取导出数据，并显示缺失／历史身份差异。

## 本次复核证据

命令：`.venv/Scripts/python.exe -B -m pytest -q tests/test_arterial1d.py tests/test_units.py tests/test_verification.py -p no:cacheprovider --basetemp=artifacts/local_review/standards_pytest_tmp`。

退出码 `0`，`31 passed in 1.07s`。另以 AST 核对新增生产导入，以宿主 setuptools 核对包发现。项目 `.venv` 未安装 setuptools，因此未把 `.venv` 内直接导入构建后端的失败当作安装失败；PEP 517 隔离构建和 wheel 安装未在此审查中运行。

首次审查读取的 `solver.py` SHA-256：`eefea67a6d57300c7cb6b781749150e37ffed0c3fb3e7faf7680aeae771c5708`；`boundaries.py`：`131d46cca8e20573b7daae9fc2686bacb19785fbf53e76e3236c695786ad408d`。

## 冻结核心后的增量复审

结论：**无新增阻塞发现。** 本次仅复审 stage 预计算缓存、显式 `linear3_ssprk3` 及相关测试，不重复运行大型基准。

- `solver.py:240` 的缓存是每次 stage 的局部计算，逐个验证 face 后共享相同算术顺序的波速、动量通量和最大特征速度；没有跨状态缓存。CFL、非正面积、非有限值与亚临界边界拒绝路径仍在提交前执行。已读取既有 `compare_cached_stage.py` 与其最终 JSON，并核对旧 stage 冻结文件哈希与首次审查一致；其 14 类各 40 步逐字段等价和失败探针是既有证据，本次未冒充重新执行。
- `solver.py:135` 对 FV 单元平均值作三阶内部与单侧端点重构，至少 3 格；常数背景通过差分形式保留。该方案明确为光滑小波实验，非 TVD、可能振铃，默认方案仍为 Rusanov。
- `solver.py:529` 的 SSPRK3 边界求值时刻为 `t`、`t+dt`、`t+dt/2`，中间状态分别以 `1/4` 与 `2/3` 组合。`solver.py:297` 以 `1/6, 1/6, 2/3` 汇总真实面通量与源项；体积和动量账本使用相同权重。全部阶段验证成功后才在 `solver.py:581` 提交整网。
- `.gitattributes` 的 `* -text` 明示保留源码和证据字节，符合当前 SHA-256 身份约定。最终 wheel 安装 smoke 由主流程负责，此复审没有据包发现宣称安装通过。

本次执行 `.venv/Scripts/python.exe -B -m pytest -q tests/test_arterial1d_linear3.py -p no:cacheprovider --basetemp=artifacts/local_review/standards_linear3_pytest_tmp`：退出码 `0`，`5 passed in 0.38s`，包括二次多项式端点重构、静止状态、阶段时刻及真实通量／源账本、第三阶段失败原子性与短窗光滑简单波收敛。此 5 项不作为聚合测试总数。

本次冻结源码 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `iabp/arterial1d/solver.py` | `8d70b1192ed64efe05a5702415e642ba850040ae094c6e0dfbcb8a7d99c7455b` |
| `iabp/arterial1d/physics.py` | `f7455b4f9fac8b52d8cedd43389d162e58aa551bc5db28e0826c1fb233c88761` |
| `iabp/arterial1d/boundaries.py` | `131d46cca8e20573b7daae9fc2686bacb19785fbf53e76e3236c695786ad408d` |

## 边界

本报告不接管 B01 Spec 轴与数值精度裁决，不把进行中的公开基准或尚未更新的聚合记录当作代码缺陷，也不将聚焦软件测试写成完整 B01 验收、生理验证或临床通过。后续源码修改需按改动范围重新审查。
