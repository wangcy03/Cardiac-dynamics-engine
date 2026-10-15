# B00：交接基线复现与静态质量门

日期：2026-10-15。结论：**PASS_REPRODUCTION_ONLY**。先完成本票，再启动 B01 实现。
这仅是软件与指定 0D 方程的数值复现，不是生理验证或约 5 ms 的端到端精度证明。

## 输入身份与环境

原始交接包已作为本地 Git 的根提交 fc18650722adbfbd05e4077cda456a8dc4bbd82e 保存。
没有配置或推送远程仓库。原始关键证据保存在 artifacts/b00/imported/；
独立复现冻结在 artifacts/b00/reproduced/，不会被后续全量验收覆盖。

原包环境为 Linux / CPython 3.13.5。本次为 Windows 10 / Python 3.12.9（Anaconda 构建）。
项目隔离环境 .venv，pytest 9.0.2、NumPy 2.3.5、SciPy 1.17.0，
ruff 0.17.0、mypy 1.20.2。前三项按原 requirements-validation.lock 安装；
静态工具在 pyproject.toml 已声明的范围内安装，没有新增核心运行依赖。
精确环境见 artifacts/b00/environment.json。

Windows 默认 cp936 使 pip 24.3.1 读取含中文注释的 UTF-8 锁文件失败。
在当前 PowerShell 进程设置 PYTHONUTF8=1 后，原锁文件无需改动即可安装。
在隔离环境安装期间还用宿主现有环境作过一次未改代码复现：
其 NumPy 2.3.2 / SciPy 1.16.1 与锁文件不同，单独留在 host_reproduction/，
不拿该次运行冒充锁定依赖的复现。

## 实际运行

以下均在项目根目录、隔离环境内执行；原始日志与报告在 reproduced/。

| 命令 | 退出码 | 结果 |
|---|---:|---|
| python -m pytest -q | 0 | 51 passed，0 failed / errors / skipped |
| python -m compileall -q iabp tools examples | 0 | PASS |
| python -m tools.numerical_check | 0 | 两组 PASS_0D_BASELINE_TIME_ONLY |
| python -m ruff check iabp tests tools examples | 0 | All checks passed |
| python -m mypy iabp | 0 | 7 个源文件，strict，无问题 |
| python -m examples.run_demo | 0 | 18 s 预热后同快照 4 s 配对轨迹与观察器 |

前五项由原版 tools.verify_all 实际逐项运行并记录。它发现的报告缺陷是：
即使正在 Windows 运行，windows_execution 仍被硬编码为 NOT_RUN。
冻结的原版报告保留此原始输出；维护后的 runner 按本次实际环境与门状态记录，
并新增退出码、日志哈希、源码哈希、依赖版本、开始/结束时间。
pytest 报告在运行前失效，缺失/截断报告不能沿用上一轮通过计数。
未安装静态工具时仍记 NOT_RUN，聚合执行返回非零，不称全部通过。

## 数值差异，未改变物理参数

12 s 无辅助运行，比较相同物理时间 9–12 s，没有时间对齐平移。
保留 250 / 125 / 50 us 三档：

| 量 | 原包 | Windows 复现 |
|---|---:|---:|
| 250 vs 50 us 根部压力最大差 / mmHg | 0.003292393186043796 | 0.003292393186043796 |
| 125 vs 50 us 根部压力最大差 / mmHg | 0.0006875505573162854 | 0.0006875505574441831 |
| 所比较事件最大差 / ms | 0.002 | 0.002 |
| 三档最大全循环血量残差 / mL | 1.6370904631912708e-10 | 1.6279955161735415e-10 |

所有压力误差指标的最大跨平台变化为 1.2789769243681803e-13 mmHg；
全部事件误差指标变化为零，事件拓扑不变。这是浮点尾数差异，不是新的生理精度结论。

4 s 演示复现：无辅助净主动脉出流 282.557134778036 mL，
辅助 277.43862461156937 mL；LV 窗口净外部功分别为
36277.18238459368 与 36617.40080942296 mmHg·mL。
保留峰压增加而净出流略降、窗口功略升的结果，不把过渡窗口称为独立患者 SV 或稳态 PV 环。

原有 7 个核心文件、legacy/ 与 docs/reference/ 的所有已列清单文件，
均与输入 SHA256SUMS.txt 的原始字节哈希一致。
模型配置、引擎配置、传感器配置和示例控制器没有变化。
可重复核对命令 python -m tools.b00_compare；
机器可读差异、哈希及缺口在 artifacts/b00/baseline_comparison.json。

## 测试映射与未覆盖风险

docs/verification_trace_r2.json 中 T01–T30 的含义保持不变。
B00 只补齐静态门与运行环境证据，不把既有 PARTIAL / BLOCKED_DATA 项升级。
新增 runner 的失败退出与缺失/截断 XML 行为测试，验证证据失效时不会给出通过计数。
最终完整测试计数应读最新聚合报告，不与本票冻结的 51 项混用。

仍缺 0D/1D 联合空间/时间与完整能量核验、真实执行器/传感器标定、
独立生理数据、真实算法接入和临床验证。GitHub CI 没有运行。
后续 B01 只做无心脏、无球囊的独立传播模块；B04 才负责心脏耦合。
