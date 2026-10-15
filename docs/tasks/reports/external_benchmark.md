# B01 外部基准资料核查报告

日期：2026-10-15（Asia/Singapore）。范围：公开来源、许可、原始数据、独立数值工具与证据身份；传播器由独立核心代理实现。

## 结果

`public_input_availability=AVAILABLE`；`download_integrity=PASS`。此前因未取得公开输入而存在的 `BLOCKED_DATA` 已就 Benchmark 1 的公开数据获取项解除。当前数值结论由经过身份核验的 `benchmark_summary.json` 分项给出，数据取得不等于数值复现通过。

已核查 [KCL 机构数据记录](https://kclpure.kcl.ac.uk/portal/en/datasets/a-benchmark-study-of-numerical-schemes-for-one-dimensional-arteri/)、[论文出版页](https://onlinelibrary.wiley.com/doi/10.1002/cnm.2732)、[Figshare v1 API](https://api.figshare.com/v2/articles/1586944/versions/1) 和 [Swansea 作者稿](https://cronfa.swan.ac.uk/Record/cronfa22154/Download/0022154-24062016154300.pdf)。数据 API 标记 CC0，已保留官方条款和原始 JSON。论文版权与数据许可分开处理。

## 交付

- `docs/benchmarks/BOILEAU_PROVENANCE.md`：来源链、日期、许可、SHA256、参数与量纲换算、入口及出口语义、参考列和比较约定。
- `artifacts/arterial1d/external/boileau2015/Benchmark1_SinglePulseModel.zip`：未经修改的真实公开原包，976099 B。
- 同目录 `Data_README_1-6_consolidated.txt`、`figshare_article_1586944_v1.json`、`CC0-1.0-legalcode.txt`：原始说明、许可元数据和条款。
- 同目录 `manifest.json`、`integrity_check.json`、`SHA256SUMS.txt`：来源及文件/成员哈希、完整性结果。
- 同目录 `case1_source_config.json`：明确标记为论文转录及 SI 换算的配置，入口按解析式定义；没有伪称原包内存在入口采样文件。

两个发布数据文件的字节数与 MD5 均匹配；ZIP CRC 通过；12 张参考表合计 50406 行，每行 9 列有限数；坐标非递减。这里只报告数据完整性，不构成模型数值 PASS。

## 对实现者的关键约束

1. 公开单脉冲配置是 10 m 长管、流量高斯入口、吸收出口。它与 B01 的 1 m 正弦平方压力工程用例不同，需要独立命名和产物。
2. B01 的壁参数应使用 `beta_pa=80000`，而不是把原文量纲为 Pa·m 的同名参数直接代入；参考压力是 0 Pa。
3. 参考是空间压力剖面，单位 kPa；需乘 1000。优先 FVM 的严格单调中心坐标；DCG 有重复界面坐标，插值前须声明处理方法。
4. 先复现 inviscid。公开 viscous 原案为 `-22*pi*nu*Q/A`，与 B01 可选 Poiseuille 的 `-8*pi*nu*Q/A` 不同；不能靠改黏度静默配平。
5. 此工作没有修改参数以通过测试，没有临床校准或验证结论。未下载 Benchmark 2–6、患者资料或论文全文。

## 数值工具与固定判据

`python -m tools.arterial1d_check --case all` 执行当前候选的实际求解；`--collect` / `--aggregate-only` 是证据门，只检查既有运行的源码、参数、数据、JSON、CSV、日志和固定覆盖矩阵，不再次求解。证据门从每个原始 run 的数值指标重算结论，不接受 wrapper 的 `candidate_pass` 代替原指标。

固定工程判据：x=0.5 m 首次上穿真实振幅一半的 10 Pa，到达误差 ≤0.5 ms；峰差 ≤1%；累计守恒残差/初始容积 ≤1e-10。反射系数绝对误差 ≤0.05；对称分叉积分分流比误差 ≤0.005、后向/前向峰比 ≤0.05。

固定公开 inviscid 判据：全部 8 个原始时刻的最大压力误差/该剖面参考峰 ≤5%，峰差 ≤5%，峰位置差 ≤0.02 m，守恒残差/初始容积 ≤1e-10。该位置门槛结合原始 FVM 1 cm 输出间距声明，不转写为临床或生理事件时间精度。

当前候选必须包含：linear3 匹配 80/160/320（必要时再细化）、三种反射各 80/160/320、分叉每段 40/80/160、公开 linear3 至少 640/1280/2560。顺序、方案、case 与 CSV 文件集合均须完整；缺项、重复或后加粗网格不能通过。

## 保留的历史与适用范围

- 一阶 Rusanov/Euler 的 80/160/320 格峰差约 49.93%/31.58%/19.44%，保留为精度不足基线。
- 独立 MUSCL/SSPRK2 工程 640 格曾满足峰差约 0.7810%、到达差约 0.07208 ms；不能覆盖公开基准失败。
- 公开 MUSCL 640/1280/2560 格在 t=1.5 s 的最大差分别为 11.76436/7.18116/3.23774 Pa；2560 格峰差约 15.58%，未达到预先声明的 5%。原工具、核心源与全量 JSON/CSV 冻结在 `history/pre_linear3/`，不冒称覆盖后来源码。
- 第三个 `linear3_ssprk3` 是光滑小振幅实验方案，非 TVD；不用于宣称激波或任意强扰动稳定。每个 run 保存全部单元在观察时刻的最小/最大压力与正、负振铃比例；公开用例的极值范围是 8 个原始剖面时刻，不是所有内部 stage。
- 首次 linear3 运行因证据门审查发现空覆盖和数据身份字段覆盖问题而停止；完整 640/1280 和部分 2560 日志以 `ABORTED_FOR_EVIDENCE_GATE_REPAIR` 留在 `history/linear3_evidence_gate_abort/`。这不是物理求解失败，也没有给旧 run 事后补写新数据身份。

修复后的当前候选需重新实际捕获运行前后的原始数据身份；旧失败和中止记录保留为历史。最终状态由集成代理根据当前候选报告、全套测试与数值边界更新，不宣称临床验证完成。

## 最终本任务结果

修复后的四个 suite 已在 Python 3.12.9 上真实运行完成，共 18 个当前 run。工具 SHA256 为 `a60fa6d721fc9bc63af9c2ff18917a7fc46df68c92bcb472c8cb41a474f0e635`，求解器 SHA256 为 `8d70b1192ed64efe05a5702415e642ba850040ae094c6e0dfbcb8a7d99c7455b`。原始 run 日志、逐 run 参数/源码快照/JSON/CSV 哈希及公开数据运行前后身份由 `benchmark_summary.json → source_reports` 引用。

| 当前候选 | 网格 | 实测关键指标 | 分项结论 |
|---|---:|---|---|
| 匹配脉冲 `linear3_ssprk3` | 320 | 峰差 0.145990%，到达差 0.046681 ms；最大体积账本残差 1.0942e-18 m³ | 工程门槛通过 |
| 封闭端 | 320 | Γ=0.99730068，参考 +1 | 工程门槛通过 |
| 压力释放端 | 320 | Γ=−0.99645232，参考 −1 | 工程门槛通过 |
| 2Z0 阻力端 | 320 | Γ=0.33259617，参考 1/3 | 工程门槛通过 |
| 对称分叉 | 每段 160 | 两支积分流量占比 0.5/0.5，后向/前向峰比 0.000430686，归一守恒残差 3.6593e-16 | 工程门槛通过 |
| 公开 inviscid `linear3_ssprk3` | 2560 | 全部 8 剖面最大差 0.67645153 Pa，最大峰/归一剖面差 3.276281%，最大峰位差 0 m | 声明的外部工程门槛通过 |

公开三档 640/1280/2560 的最大压力差为 7.426747/3.013280/0.676452 Pa，最大峰差为 35.5753%/14.5943%/3.2763%，观察到的最大压力误差阶为 1.3014/2.1553。三阶是所用光滑重构的形式阶次，不能把这组实测阶次改写成“三阶收敛已证明”。

公开 2560 格在八个观察时刻、全部单元上的压力范围为 [−0.01895853, 20.57130890] Pa；相对各原始参考峰的最大正超调为 0.344618%，负向比例为 0.091823%。体积账本残差/初始容积为 1.3473e-14。匹配 320 格的最小压力为 −0.09542723 Pa，负向比例约 0.4771%。这些负向振铃没有被剪裁；非 TVD 及光滑小振幅适用范围仍有效。

匹配用例的到达误差在三档间并非单调下降（0.028751/0.024417/0.046681 ms）；工具保留负的局部观察阶。所有值仍在冻结的 0.5 ms 门槛内。小信号解析参考与非线性守恒方程之间的差异也不能通过重新对齐消除。

### 运行与核验

- `.venv/Scripts/python.exe -m tools.arterial1d_check --case linear3_matched`：退出 0；3 个当前 run。
- `.venv/Scripts/python.exe -m tools.arterial1d_check --case reflections`：退出 0；三种端部各 3 档，共 9 个当前 run；粗档失败仍保留。
- `.venv/Scripts/python.exe -m tools.arterial1d_check --case junction`：退出 0；3 个当前 run。
- `.venv/Scripts/python.exe -m tools.arterial1d_check --case linear3_boileau`：退出 0；640/1280/2560 三档，共 3 个当前 run；不需要扩大至 3840/5120。
- `.venv/Scripts/python.exe -m tools.arterial1d_check --collect`：退出 0，`mode=EVIDENCE_GATE_NO_SOLVER_RUN`，`engineering_status=PASS`，`public_benchmark_status=PASS_DECLARED_ENGINEERING_TOLERANCE`，`overall_status=PASS_DECLARED_CHECKS`。
- `.venv/Scripts/python.exe -m pytest -q tests/test_arterial1d_benchmarks.py`：34 passed；定向 ruff、compileall 通过。证据门另经独立代理的 23 项故障探针复核；这些是软件/证据结构检查，不增加物理试验数量。

`propagation_comparison.png/.svg` 由已保存 CSV 绘制，包含原一阶耗散、MUSCL 历史失败和当前 linear3 对照，已目视检查。绘图使用全局 Python 3.12.9 / Matplotlib 3.10.5 的可选 Agg 路径；未给生产核心新增依赖，版本记录在 `plot_runtime.json`。主项目的全套 pytest、0D 数值回归、demo、lint/typecheck 与状态更新由集成代理统一完成；本报告不代替该全体验收。
