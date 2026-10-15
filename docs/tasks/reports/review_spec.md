# Spec 轴审查

日期：2026-10-15。固定点：`fc18650722adbfbd05e4077cda456a8dc4bbd82e`；审查包含当前未跟踪文件，不限于 Git diff。

**当前 Blocking 0；Nonblocking 0。增量发现的 2 项证据门问题均 UPHELD → RESOLVED_BY_RECHECK；不代替 B01 数值整体验收。**

- B00 冻结报告保留原始 51 项测试、三档 0D 数值基线、静态门及跨平台差异，未用参数修改掩盖失败；历史复现与最终聚合结果有明确边界。
- 对照 `B01_SPEC.md` 的方程、数值默认与边界条款检查了 `iabp/arterial1d/`、集中单位转换、行为测试及基准测量。均匀管 SI 方程、Rusanov 基线、单入射特征边界、共同静压分叉、共享流量积分及显式失败符合本票范围。MUSCL/SSPRK2 独立命名，未覆盖一阶未通过记录。
- 解析脉冲按原物理时间比较，固定 10 Pa 上穿缺失时不补造事件；反射与分叉记录保留三档误差和守恒结果。没有发现把峰压或极小守恒残差升级为生理正确性的表述。
- 正式 HTML 的方程、LaTeX 源、框架／时序／控制体图及真实导出链接与当前实现边界相符；维护约定区分证据 freshness、浏览器渲染与物理验证。

## 增量复核与修复审计

冻结 `solver.py` SHA256：`8d70b1192ed64efe05a5702415e642ba850040ae094c6e0dfbcb8a7d99c7455b`。
三阶重构、SSPRK3 的 `t/t+dt/t+dt/2` 阶段、`1/6,1/6,2/3` 通量／源项权重、失败原子性与光滑小振幅适用域无新增发现；没有将它宣称为 TVD 或冲击波方案。

1. **UPHELD → RESOLVED：证据覆盖与通过标志未绑定。** 修复前 `tools/arterial1d_check.py:580–636,656` 接受空反射／分叉运行列表；反射缺失时 `all([])` 为真，且聚合使用未受原始运行 JSON 约束的 wrapper `candidate_pass`。探针确认已哈希 `run.pass=False` 与 suite `candidate_pass=True` 可以同时通过身份核验。违反 B01“反射用例”“对称分叉”与 AGENTS.md“没有证据就不能改为 PASS”。修复后固定 case×scheme×有序网格，拒绝空／缺／重覆盖与空／缺／重／额外 CSV，逐字节核验完整源码快照，并从原始数字重算判定。
2. **UPHELD → RESOLVED：公开数据身份被覆盖。** 修复前同文件 `497,536,249–255,606,668–671` 将 archive identity 覆盖为源码 identity，不能绑定实际运行所用数据；探针确认 `archive_sha256` 丢失。B01 要求“公开 Boileau 基准输入需实际下载、核查许可并保留哈希”。修复后独立保留运行开始／结束的 archive、manifest、config 身份，从已捕获字节解析输入，聚合再与当前文件核对；不向旧运行补记新身份。

修复前探针：[脚本](evidence_gate_review/probe_before_fix.py)、[原始结果](evidence_gate_review/probe_before_fix.json)。修复后工具 SHA256：
`a60fa6d721fc9bc63af9c2ff18917a7fc46df68c92bcb472c8cb41a474f0e635`。
独立 23 项故障探针全部 PASS，含空源码清单、CSV 集合、wrapper 冲突及实际 config／manifest／ZIP 字节漂移；[脚本](evidence_gate_review/recheck_after_fix.py)、[原始结果](evidence_gate_review/recheck_after_fix.json)，退出码 0，`NO_SOLVER_RUN`。附件可随仓库克隆，只有临时合成／复制数据会被修改；整理后的两个脚本均再次执行成功。

定向命令 `python -B -m pytest -q tests/test_arterial1d_benchmarks.py -k "not public_run_keeps_data_identity_separate_from_source_identity"`：33 passed，1 deselected，退出码 0；主动排除会运行四格求解器的契约测试。已直接通知 benchmark owner 按主代理授权启动修复后的四个真实套件。

最终四个真实 suite 已完成，只读收尾核对通过：`source_reports` 为 matched 3、反射 9、分叉 3、Boileau 3，合计 18 次运行；逐项核对 21 份 CSV、4 份原始运行日志、5 个当前源码文件及完整字节快照、各运行 JSON 与套件引用哈希，全部匹配。三个公开运行的 data identity 均为开始／结束／当前文件一致；历史失败对照保持独立，不计当前核心覆盖。`benchmark_summary.json` 为 `PASS_DECLARED_CHECKS`。`verification_summary.json` 于 `2026-10-15T10:42:30Z` 完成，121 tests，0 failures／errors／skipped，六项门均 PASS、exit 0。**现可由 root 按声明的 B01 独立传播范围放行**；不代表 0D/1D 耦合、分布式球囊、生理或临床验证完成。B03–B08 的既有缺口不作为 B01 阻塞项。

本审查未重跑昂贵基准、未修改实现或阈值；最后一次收尾只读取已落盘证据，没有再次运行求解器或测试。
