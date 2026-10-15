# IABP Engine 工作规则

## 先读
1. `START_HERE.md` 与 `docs/STATUS.md`。
2. `docs/reference/IABP_Engine_Spec_r1.md` 是需求基线，r0 研究原文在 `docs/reference/research_r0/`。
3. 本次实现范围见 `docs/ARCHITECTURE.md`，下一任务见 `docs/tasks/BACKLOG.md`。
4. 审查 `artifacts/verification_summary.json`；没有证据就不能改为 PASS。

## 已决定，不反复询问
多路 AP（位置、技术、仪器链各自配置）；直接 ECG，先 II 导联，预留十二导联；
命令级输出；先研发软件在环；约 5 ms 是工程目标，不是临床安全常数。
最终路线为 0D 心脏/回流 + 1D 动脉 + 分布式球囊。r2 的 0D 桥接原型不得偷换最终路线。

## 开发边界
本会话/项目负责人：用途、架构、事件定义、验收准则、路线及原型。
Codex：按票实现、测试、数值核验、模块集成、技术债修复。
改变用途/风险结论/核心事件定义/最终架构/5 ms 目标时，写 ADR 并提交负责人决策。
普通实现细节由 Codex 执行，不为已定事项反复停工。

## 物理和时间硬规则
- 不按搏重置状态，不用周期曲线平铺替代最终引擎。
- 不用压力/容积 clipping 隐藏求解失败；真正的本构边界与失败处理须明确区分。
- 球囊占据体积要从总血量扣除；保持充盈仍须有阻塞效应；禁止重复计入排挤量。
- QRS、R、压差反向、出流零交叉、有效开口关闭、切迹候选、命令和动作分别命名。
- 没有事件就保持缺失，不补固定延时；切迹不是关闭真值。
- 控制器只接收已交付 Sample；不传 Engine、Model、未来节律或评估器状态。
- Python 对象边界不是恶意代码安全沙箱；外部算法隔离是后续任务。
- 不用观察 AP 峰值增加就宣称辅助有效；SV、LV 负担与参考窗口必须联合比较。
- 人工参数/工程场景不能变为“临床实测”“已校准”或“临床通过”。

## 工程约束
Python 3.11+；生产核心仅标准库；开发依赖在 pyproject.toml。
核心单位 mmHg/mL/s，接口时钟为整数微秒；SI 接口必须集中转换和测试。
旧 HTML 和原文在 legacy/、docs/reference/ 保留，不作为新核心的测试 oracle。
演示观察器只能读取核心导出的值，不生成另一套“漂亮的物理波形”。
任何新依赖说明必要性；不要下载受限数据；不含患者身份/凭证。
公开推送唯一例外：负责人于 2026-10-15 明确授权将本项目 main 正常推送至
`https://github.com/wangcy03/Cardiac-dynamics-engine.git`，允许该仓库为 public。
推送前核对 origin 的全部 push URL 均为上述唯一地址；其他公开仓库仍禁止推送。

## 每个任务的完成条件
最小可运行切片 -> 有失败判据的测试 -> 数值/回归测试 -> 更新测试映射和状态。
运行：
```
python -m pytest -q
python -m compileall -q iabp tools examples
python -m tools.numerical_check
python -m ruff check iabp tests tools examples
python -m mypy iabp
```
修改模型后再运行 `python -m examples.run_demo`。静态工具缺失只能记 NOT_RUN，不得声称已通过。
不要无依据放宽阈值来绿化测试。不能为了支持临床结论而逐工况重拟合参数。
提交说明必须给出：修改点、测试命令/结果、数值误差变化、仍未覆盖的风险。

## 数理原理文档随迭代维护
修改方程、本构参数、数值方法、事件或接口时，同步维护
`docs/MATHEMATICAL_PRINCIPLES.html` 的相应推导、假设和实现边界；
按 `docs/PRINCIPLES_MAINTENANCE.md` 刷新实际产物证据及图表，再完成 freshness 检查。
正文是解释的维护源，自动证据区只读取导出文件；刷新文档不替代数值或生理验证。
