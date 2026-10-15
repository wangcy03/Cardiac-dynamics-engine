# Spec 证据门审查附件

范围：仅合成临时结构数据、复制公开输入到临时目录后注入字节变化；**不运行 solver**，不改真实基准文件、参数或阈值。这里的 PASS 只表示证据门按预期拒绝缺失／冲突／漂移，不是传播精度通过。

| 文件 | 用途 |
|---|---|
| `probe_before_fix.py` | 对已冻结的修复前工具重现空覆盖、wrapper 冲突与数据身份覆盖 |
| `probe_before_fix.json` | 首轮内联探针的原始记录，退出码 0 |
| `recheck_after_fix.py` | 修复后 23 项独立探针；只调用证据校验 helper，不调用求解器 |
| `recheck_after_fix.json` | 修复后实际运行记录，23 项 PASS、退出码 0、NO_SOLVER_RUN |

脚本从原内联探针整理为可执行文件，补充仓库定位和工具哈希检查；结果 JSON 从 `artifacts/local_review/` 原样复制。历史探针加载 `artifacts/arterial1d/history/source_bd493b738097c431/files/tools/arterial1d_check.py`，SHA256 为 `9b04739a740c6c7fc10d348d78a5cca43e3bbc2607a42a16283ac93396ab8427`。修复后探针要求当前工具 SHA256 为 `a60fa6d721fc9bc63af9c2ff18917a7fc46df68c92bcb472c8cb41a474f0e635`；后续工具变化时应重新审查，不改哈希来沿用旧结论。

在仓库根目录复现：

```powershell
.venv/Scripts/python.exe -B docs/tasks/reports/evidence_gate_review/probe_before_fix.py
.venv/Scripts/python.exe -B docs/tasks/reports/evidence_gate_review/recheck_after_fix.py
```

新输出写入已忽略的 `artifacts/local_review/`；不会覆盖本目录的已审查结果。临时文件由 `TemporaryDirectory` 创建并清理。修复后探针只读公开原包，漂移注入全部发生在临时副本。整理后的两个脚本均实际执行，退出码 0，结果分别重现首轮发现和 23 项预期行为。

两项发现已 `UPHELD → RESOLVED_BY_RECHECK`，详见上级 `review_spec.md`。**本票最终放行由 root 在当前四个真实 suite 完成并核对后进行**；本附件不批准未完成的 Boileau 运行，也不提供生理或临床验证结论。
