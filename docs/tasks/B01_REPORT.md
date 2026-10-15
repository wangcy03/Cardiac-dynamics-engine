# B01：独立一维传播与公开数值参考

日期：2026-10-15。当前状态：**DONE_DECLARED_STANDALONE_SCOPE**。
仅验收无心脏、无球囊的独立传播模块；B04/B05、患者适用域及约 5 ms 端到端目标不在本票完成范围。

## 改动与方法

新增 iabp/arterial1d/，按 B01_SPEC 保存 SI 面积/流量的守恒状态，
实现平方根管壁本构、局部特征速度、单入射特征边界、共同静压分叉。
各段使用实际面通量更新，分叉共享同一流量和；每步/累计体积账本独立导出。
所有分段、RK 阶段成功后才提交状态；非法面积、非有限量、无亚临界根、
CFL/源项步长及网络时刻漂移显式失败，不做压力或面积 clipping。

| 方案 | 数值处理 | 本票定位 |
|---|---|---|
| rusanov | 一阶 FV Rusanov + Euler | 默认与原始基线，完整保留耗散结果 |
| muscl_ssprk2 | generalized minmod θ=1.5 + SSPRK2 | 单独命名的高阶对照 |
| linear3_ssprk3 | 三阶单侧 FV 重构/端点闭合 + SSPRK3 | 光滑小振幅实验；非 TVD，须报告振铃 |

RK3 边界使用 t、t+dt、t+dt/2，通量/源项按 1/6、1/6、2/3 真实权重记账。
可选 Poiseuille 源项为 −8πνQ/A，α=1 与该阻力的组合是声明的降阶近似。
当前仅支持每段均匀几何/本构；分叉忽略动压和几何局部损失。
SI/mmHg/mL/整数微秒集中在 iabp/units.py；没有将该秒制独立模块接入旧引擎。

阶段缓存优化约 1.6 倍，不改变原两方案的计算顺序/结果：
14 个 40 步场景、全部 StepResult/账本及失败路径与冻结旧 stage 逐字段相等，
可复核脚本及哈希见 artifacts/arterial1d/implementation_checks/。
pyproject 的子包发现已修正；实际 wheel 构建/安装、隔离导入三方案成功，
12 个包内生产源文件与当前源码逐字节一致，见 artifacts/packaging_check.json。

## 冻结输入、误差与失败对照

工程用例严格保留 L=1 m、A0=3e-4 m²、ρ=1060 kg/m³、c0=5 m/s，
20 Pa、0.05–0.09 s 正弦平方压力脉冲及原始末端配置。
一阶 80/160/320 格峰差约 49.93% / 31.58% / 19.44%，精度不足完整留档。
MUSCL 320 格峰差约 2.22%，继续细化到 640 后约 0.781%，到达误差约 0.072 ms。
公开长管窄脉冲更苛刻：MUSCL 640/1280/2560 格最晚剖面压力最大差
11.7644 / 7.18116 / 3.23774 Pa；2560 格峰差仍约 15.58%。
这些历史失败/源码快照位于 artifacts/arterial1d/history/pre_linear3/。
增加第三方案是另外建立方法对照，没有修改上述输入、物理参数或容差，也没有覆盖一阶默认。

当前 linear3 工程三档 80/160/320 格峰差约 4.635% / 0.789% / 0.146%；
320 格到达误差约 0.0467 ms，固定判据仍为 10 Pa 首次上穿、≤0.5 ms 和峰差≤1%。
三档误差阶次均按原始物理时间计算，不作时间/空间平移。
小信号解析式是非线性方程的近似参考：接近其误差底限时，到达误差不必逐档单调，
不能把观察到的每一段误差变化硬称为理论三阶；另有独立非线性 simple-wave 收敛测试。
振铃极值来自记录的观察时刻全部单元，并不覆盖全部内部步/RK 阶段。

端部反射验证 +1、−1、1/3，采用 80/160/320 格；
对称分叉采用每段 40/80/160 格，报告分流、后向波、界面与全网体积误差。
320 格反射系数分别为 0.997300685、−0.996452315、0.332596173，
绝对误差均小于预置 0.05。分叉 160 格分流各为 0.5，
母管后向/前向峰比为 0.0004306864，界面逐步及累计体积差为 0。
全部粗档结果、守恒误差与观察阶次见最终 benchmark_summary.json。

## 公开参考的许可与边界

实际获取 Boileau 数据固定版本 10.6084/m9.figshare.1586944.v1，
保留 CC0 条款、原始 ZIP/README/API、发布 MD5、SHA-256 及 CRC/列核验。
本票比较 inviscid 单脉冲 Benchmark 1；原始数值表是八个时刻的空间压力剖面，
从 kPa 转 Pa，在原 FVM 中心坐标比较，不把它当时间序列或患者记录。
来源、配置与单位换算见 docs/benchmarks/BOILEAU_PROVENANCE.md。

公开用例预置门槛为相对全场最大差≤5%、峰差≤5%、峰位置差≤0.02 m、
累计体积残差/初始容积≤1e-10；本票未因实际失败放宽。
六法原始离散/采样参考的全场范围差可达峰值约 6.6–8.4%，FVM 并非唯一精确真值。
该参考的 1 cm 输出采样也不支持直接认定 0.5 ms 生理精度。
原 viscous 用例为 −22πνQ/A，与本票 −8πνQ/A 不同，保持 NOT_REPRODUCED。

## 证据门修复与重跑

独立 Spec 复审发现并实际复现两个问题：空/不完整反射分叉覆盖及 wrapper 标志可能假绿，
以及公开数据身份被源码身份覆盖。已修复固定 case×scheme×有序网格和完整 CSV/source 集合验证，
从已核验原始数值重算判定，并独立保留实际运行前后数据身份。
34 项工具回归与独立 23 项 NO_SOLVER_RUN 故障探针通过，两项 finding 已关闭。
审查及探针见 docs/tasks/reports/review_spec.md 和 evidence_gate_review/。

修复前中止的进程明确标 ABORTED_FOR_EVIDENCE_GATE_REPAIR，属于记录修复，不计物理解失败；
源码、已完成/部分结果与日志原样留档于 history/linear3_evidence_gate_abort/。
未给旧 run 事后补写成“当时已捕获”的 data_identity。
修复后的四套件重新实际求解，源码、原始 JSON、CSV、日志及数据包身份分别保存。

python -m tools.arterial1d_check --collect 仅核对已实际运行的证据并生成汇总，
模式为 EVIDENCE_GATE_NO_SOLVER_RUN。python -m tools.verify_all 的 1D 门使用此模式，
不会将身份核对写成又一次求解；复现实验使用 --case all 或分别运行四个 case。
Git 使用字节保留属性，避免 Windows 文本换行在 checkout 后破坏输入/源码/产物哈希。

## 最终验收记录

当前四个实际求解套件共 18 个 run：匹配 3、反射 9、分叉 3、公开参考 3。
四套件及最终收集门均退出 0；历史对照、故障探针和四格契约测试不计入这 18 个 run。
工程状态为 PASS，公开数值参考为 PASS_DECLARED_ENGINEERING_TOLERANCE，
汇总为 PASS_DECLARED_CHECKS，范围限定于上述方案、边界和输入。

| 公开 linear3 网格数 | 八剖面最大压力差 / Pa | 最大归一剖面差 | 最低记录压力 / Pa | 候选门 |
|---|---:|---:|---:|---|
| 640 | 7.42674703 | 35.9702% | −0.96650456 | ACCURACY_NOT_MET |
| 1280 | 3.01327971 | 14.5943% | −0.41822784 | ACCURACY_NOT_MET |
| 2560 | 0.67645153 | 3.27628% | −0.01895853 | PASS_DECLARED_ENGINEERING_TOLERANCE |

最大压力差的观察阶次为 1.3014、2.1553；不将其改写成恒定理论三阶。
2560 格最大峰差同为 3.27628%，最大峰位置差为 0 m（原输出采样坐标），
累计体积残差/初始容积为 1.3473e-14。粗档失败与细档负振铃均保留。

最终集成运行于 2026-10-15 10:41:48–10:42:30 UTC，Windows / Python 3.12.9。
`python -m tools.verify_all` 退出 0，执行以下门：

| 实际命令 | 结果 |
|---|---|
| python -m pytest -q --junitxml=artifacts/pytest.xml | 121 passed；0 failures/errors/skipped；退出 0 |
| python -m compileall -q iabp tools examples | PASS；退出 0 |
| python -m tools.numerical_check | PASS_0D_BASELINE_TIME_ONLY；退出 0 |
| python -m ruff check iabp tests tools examples | PASS；退出 0 |
| python -m mypy iabp | PASS，12 个生产文件；退出 0 |
| python -m tools.arterial1d_check --collect | PASS_DECLARED_CHECKS；退出 0；仅核验已求解证据 |

修改后另行实际执行 `python -m examples.run_demo`，退出 0，见 artifacts/demo_run.json。
原 0D 三档数值结果未变：250/50 µs 根部最大差 0.003292393186 mmHg、
可匹配事件最大差 0.002 ms、最大质量残差 1.6280e-10 mL。
B00 跨环境压力误差指标最大变化仅 1.2790e-13 mmHg；未调物理参数。
最终命令、退出码、日志哈希及计数见 artifacts/verification_summary.json；
数值原始 suite、源码/输入身份和日志见 artifacts/arterial1d/benchmark_summary.json 及 run_logs/。

## 正式原理文档与后续

docs/MATHEMATICAL_PRINCIPLES.html 从守恒、动量、弹性储能与因果信息解释实现，
含 19 组离线 MathML/LaTeX、3 幅默认浅色框架/时序/控制体图、真实 CSV 科学图和原型观察器链接。
证据区只读取导出文件，不另外生成物理波形；AGENTS.md 已增加随迭代维护规则。
浏览器策略拒绝 file:，实际渲染为 NOT_RUN_BROWSER_POLICY，静态检查不冒充实际渲染。

旧 0D 核心、教学页面和参考原文保持原始字节；最终路线仍为
0D 心脏/回流 + 1D 动脉 + 分布式球囊。
B02 协议可靠性与 B03 心脏/能量核验可继续；B04 才进行联合耦合验收。
全能量账本、分布式球囊/执行器和测量链标定、患者/动物适用域及临床验证仍未完成。
