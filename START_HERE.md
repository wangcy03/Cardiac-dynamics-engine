# 给 Codex 的起始入口

## 目标和阶段
这是 IABP 定时算法物理引擎的初步开发交接包 r2。
用户已确认 r1 需求。本包包含真实运行的连续 0D 原型，而不是最终的经过生理验证的 0D/1D 引擎。
先读 AGENTS.md、docs/STATUS.md 和 docs/tasks/BACKLOG.md。不要先改网页样式，也不要重问输入输出边界。

## 第一条任务
先执行 B00：复现原型基线，补齐尚未运行的 lint/mypy，检查测试映射和边界；
然后执行 B01：独立一维传播模块及公开基准。不可跳过基准直接宣布 5 ms 精度。

## 在项目根目录执行
```
python -m venv .venv
# 激活 .venv：Windows PowerShell 为 .venv\Scripts\Activate.ps1；类 Unix 为 source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
python -m tools.numerical_check
python -m examples.run_demo
```
已有 Python/pytest/scipy 时，可不安装项目直接在根目录运行上面三个 `python -m ...` 命令。
核心运行无第三方依赖；SciPy 仅供独立参考核验，pytest 供测试。
验证 Python 的版本与 dependencies 记录，不将环境差异误当作模型变更。

## 交接时必须知道的边界
- 0D 模型含四心腔、有限体/肺回流、动态开口瓣膜、惯性管路、两级激活与恢复。
- 不是 1D 波传播；没有几何网格/分叉/CFL 验证，不可用于真实部位延迟的定量校准。
- 球囊仅一个降主动脉占据容积、阻塞及负荷相关一阶动作试验。
- ECG 是处理过的同一激活事件的合成观测，不是实测或完整心电生理。
- 未校准患者、真实执行器、实际 AP/ECG 链路；未取得新的中央高保真原始文件。
- 示例控制器只说明反馈链可运行，不是正确或最优的 IABP 定时策略。
- 现有快照仅在同版本进程内受信对象恢复。跨进程/跨版本格式未完成。
- CI 配置已提供，但尚未在 GitHub 或 Windows 上运行；没有创建或推送远程仓库。

## 建议交给 Codex 的第一段话
> 按 START_HERE.md 和 AGENTS.md 接手 IABP 引擎。先完成 B00：重跑基线、执行 lint/typecheck、核对原型与 r1 的差距，更新证据。不删旧教学内容，不改最终 0D/1D 路线，不调参掩盖失败。随后按 B01 先实现并验证独立一维传播模块，完成后给出代码、测试结果、数值收敛和下一步风险，不宣称临床验证完成。

## 本地与云端
可直接将解压后的目录作为本地 Codex 工作目录；云端使用时先放入用户自行管理的仓库并配置开发依赖。
本包用项目根目录的 AGENTS.md 保存持续规则，而不是要求 Codex 记住这段聊天。
官方说明： https://developers.openai.com/codex/guides/agents-md
