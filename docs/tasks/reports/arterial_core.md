# B01 独立 1D 核心实现记录

日期：2026-10-15。用途：研发软件在环；本模块没有心脏、球囊或患者校准。

## 已实现的方程和离散方法

`iabp/arterial1d/` 在均匀管段内以 SI 单位保存面积 A 和流量 Q。
管壁关系、动量压力势和局部波速严格采用 B01_SPEC：

\[
P=P_0+\beta(\sqrt{A/A_0}-1),\qquad
\Pi(A)=\frac{\beta A\sqrt{A/A_0}}{3\rho},\qquad
c^2=\frac{\beta}{2\rho}\sqrt{A/A_0}.
\]

- `scheme="rusanov"`：原始一阶有限体积 Rusanov 通量和显式 Euler。保留为基线。
- `scheme="muscl_ssprk2"`：单独命名的高阶比较；对 A、Q 使用 theta=1.5 的
  generalized minmod 逐量重构，时间使用 SSPRK2。它没有替换一阶基线。
- `scheme="linear3_ssprk3"`：第三个明确的实验方案，仅适用于光滑小振幅波，非 TVD。
  新增原因是公开 Boileau 长管窄 Gaussian 脉冲对照暴露 MUSCL 峰值耗散显著；
  已取得的失败对照和当时源码保留于 `artifacts/arterial1d/history/pre_linear3/`，
  没有覆盖失败结果、修改波形或放宽门槛。
- 可选显式 Poiseuille 源项 `-8*pi*nu*Q/A`，每个 RK 阶段都计算。
  alpha=1 与该阻力组合仍是降阶近似；没有声称三维速度剖面得到精确解析。
- CFL 由所有单元、重构面及物理边界上的 `u-c`、`u+c` 共同限定。
  黏性源项另要求 `dt <= A/(8*pi*nu)`，避免显式阻力单独导致数值流量反号。
- 仅支持每段均匀的 A0、beta、P0；没有未推导的连续变几何源项。

实验三阶重构在内部单元的右面使用 `(-U[i-1]+5*U[i]+2*U[i+1])/6`，左面镜像。
第一格左/右面使用 `(11*U[0]-7*U[1]+2*U[2])/6`、
`(2*U[0]+5*U[1]-U[2])/6`，末端镜像；实际按均值加差分计算，保留常数背景。
至少需要三格。SSPRK3 按 `t`、`t+dt`、`t+dt/2` 计算阶段边界，
面通量和源项分别按 `1/6, 1/6, 2/3` 的真实权重输出和记账。
此方案没有限幅；正式基准必须报告最小/最大压力及振铃，不能扩大为冲击波适用性声明。

## 特征边界与分叉

特征量为 `u+4c`、`u-4c`。压力入口、流量入口、终端阻力、封闭端和无反射端
每次只规定一个条件，并从内部状态继承另一条出射特征。
`NonReflectingBoundary` 固定参考零流状态的入射特征；它没有偷偷使用未来波形。
`ResistanceBoundary` 解 `P-Pdown=R*Q` 与出射特征。

分叉采用 B01 明确冻结的共同静压近似，忽略动压及几何局部损失。
在共同亚临界压力区间求解 `Qparent=sum(Qchildren)`。面更新直接使用求得状态的物理通量，
而不是用不一致的 ghost-Rusanov 流量冒充守恒。
求根达到浮点精度后父端流量取子端流量的同一浮点和；输出父出射特征残差，
如果此末位修正超过舍入预算则明确失败。

## API、体积账本与失败语义

- `SegmentConfig`、`TubeLaw`、`State`：有单位的配置与不可变状态快照。
- `Segment.max_stable_dt_s()`：当前状态的候选上限；`step` 会复查各阶段与边界。
- `Segment.pressure_pa()`、`sample_pressure_pa(x_m)`：只读取当前导出的物理状态。
- `StepResult.face_fluxes`：全部 n+1 个实际采用的面通量。
  SSPRK2/SSPRK3 返回各自阶段的真实加权通量，账本使用相同的 `dt*Qface`。
- `StepResult` 与 `Segment.ledger`：每步和累计的入口/出口积分体积、实际体积及残差。
- `Network.step`：先求完整候选，再统一提交分段状态和账本。
  `NetworkStepResult` 返回所有分段结果、各阶段分叉解和全网外部净积分体积。

非正/非有限面积、非有限输入、无可用的亚临界特征根、CFL 违规与重构失败均显式抛错。
没有压力/面积 clipping，也不在失败后提交前面已算出的分段或 RK 第一阶段。
已经构造网络后，若某段被独立推进导致时刻不一致，下一次网络步进明确拒绝。

`iabp/units.py` 集中提供 Pa/mmHg、m3/mL、流量和整数微秒接口转换。
输入或转换结果非有限时失败；秒不能表示为整数微秒时不静默舍入。
这只是单位接缝；B04 以前没有将 1D 与旧 0D 引擎耦合。

## 本轮定向验证

环境：项目 `.venv\Scripts\python.exe`，Python 3.12，Windows。

| 命令 | 实际结果 |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q tests/test_arterial1d.py tests/test_arterial1d_linear3.py tests/test_units.py` | 34 passed，0.60 s |
| `.venv\Scripts\python.exe -m mypy iabp/arterial1d iabp/units.py` | Success，5 source files |
| `.venv\Scripts\python.exe -m ruff check iabp/arterial1d iabp/units.py tests/test_arterial1d.py tests/test_arterial1d_linear3.py tests/test_units.py` | All checks passed |

行为覆盖：本构反解与独立差分波速、静止平衡、Rusanov 一致性、实际面通量的体积和动量账本、
阻力耗散和源项步长上限、压力采样、共同静压分叉的对称性/守恒，
以及初始/边界/RK 第二阶段 CFL、非正高阶重构、不可解分叉、网络时刻漂移和转换溢出的原子失败。
三阶专项还验证所有端点的二次多项式精确重构、静止状态、少于三格拒绝，
独立非线性 simple-wave 解的 40/80/160 格收敛阶大于 2.6、真实阶段时刻和不等权重的体积/动量账本，
以及第三阶段失败时全网不提交部分状态。

空间收敛、反射系数、真实公开 Boileau 数据对照由独立的 `tools/arterial1d_check.py`
及 `artifacts/arterial1d/` 记录。上述 34 项行为测试不替代这些数值结果。
原始一阶的耗散必须按原值报告，不能用高阶结果覆盖，也不能改输入波形或物理参数躲过误差门槛。

## 保守的性能优化与身份

每个 stage 对每个 trace 一次校验和预计算，Rusanov 与 CFL 共用同一浮点运算顺序下的
sqrt(A/A0)、c、物理动量通量和最大绝对特征速度。没有改变公开物理通量函数、限幅器或参数。
优化前先冻结历史源，再做探针；最终生产实现又与冻结旧 stage 做完整逐步比较。
两原 scheme × 两档黏性 × 三种边界组合各 40 步，以及两种黏性分叉各 40 步，
每个完整 StepResult 和所有分段/网络账本逐字段相等；失败类型、消息及原子性也一致。
可随 Git 交付的证据为 `artifacts/arterial1d/implementation_checks/compare_cached_stage.json`，
其脚本会从历史冻结源码实际提取原 stage，并记录自身、当前 solver 和参考 solver 的 SHA256。

本地 100 步探针 160/320/640 格整体加速约 1.60/1.65/1.64 倍。
最终源码下 640 格 100 步 CPU 时间：MUSCL/SSPRK2 0.921875 s，
linear3/SSPRK3 1.296875 s，后者单步约 1.41 倍成本。
这只是性能探针，不是完整基准验收或实时性保证。
性能记录保留于同目录的 `stage_cache_performance.json` 与 `linear3_cost_probe.json`。

本次稳定 `solver.py` SHA256：
`8d70b1192ed64efe05a5702415e642ba850040ae094c6e0dfbcb8a7d99c7455b`。
实际正式基准还必须记录最终完整核心身份，不能把旧进程结果重新贴成新源码结果。

## 仍未覆盖

没有 0D/1D 耦合、分布式球囊、变几何源项、壁黏弹性、全能量核验、设备/患者标定或临床验证。
没有证明真实切迹事件、0.5 ms 生理事件精度或 5 ms 临床定时精度。
浮点秒只属于此独立 SI 数值模块；未来接入整数微秒调度仍需 B04 适配和相应验证。
