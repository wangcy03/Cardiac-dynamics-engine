# 固定观察器 V1：软件与真实数据核验

日期：2026-10-16。兼容入口为 `artifacts/demo/prototype_viewer.html`；
当前冻结包为 `artifacts/runs/r2-b01-observer-v1-20261016/`，
预载历史对照为 `artifacts/runs/r2-original-fc18650-v1/`。

## 修改范围

固定 `viewer/` 三页界面读取 `cardiac-observer/v1` 数据包；
Python 适配器负责原值、单位、缺失和记录身份，发布器保存不可覆盖的原始副本。
`examples.run_demo` 接入同一刷新流程，数理文档与 README 已链接新入口。
旧教学与参考原文保留，生产核心的 12 个源文件字节均未改变。

当前包有两个 0D 分支，各 4001 行 × 33 列真值、13000 个交付样本、76 条事件；
无辅助命令为空，有辅助命令状态 26 条。所有指标使用完整 18–22 s 记录。
28 个独立 1D 对照中，18 个有当前记录源码身份、10 个归属历史源码；
原声明状态为 14 PASS / 14 FAIL，全部保留。Boileau 仅展示八个实际时刻的空间剖面。

## 实际命令与测试映射

| 实际命令/证据 | 结果 | 证明范围 |
|---|---|---|
| `python -m tools.verify_all` | 退出 0；六项门 PASS，171 项 pytest，零失败/错误/跳过 | 包含下列 Python 验证；并不证明浏览器或生理资格 |
| `python -m pytest -q` | 集成门记录 171 项通过 | 原 121 项 + 44 项导出适配 + 6 项冻结/发布回归 |
| `python -m compileall -q iabp tools examples` | 退出 0 | Python 语法 |
| `python -m tools.numerical_check` | 退出 0 | 原 0D 时间步长数值核验 |
| `python -m ruff check iabp tests tools examples` | 退出 0 | Python 静态规则 |
| `python -m mypy iabp` | 退出 0 | 生产核心 strict 类型检查 |
| `python -m tools.arterial1d_check --collect` | 退出 0 | 已实际求解记录的身份核验，未重跑 1D 求解 |
| `node --check viewer/viewer.js` | 退出 0 | 固定脚本语法 |
| `node --test viewer/viewer.test.js` | 25 项通过 | schema、时钟、保极值抽样、缺失断线、精确坐标差值、窗口和场景可比性 |
| `python -m examples.run_demo` | 退出 0 | 更新后的真实 0D→导出→冻结→观察器路径可执行 |
| `python -m tools.viewer --run-id r2-b01-observer-v1-20261016 --comparison artifacts/runs/r2-original-fc18650-v1/viewer_bundle.json` | 退出 0 | 最终冻结包与含预载对照的兼容 HTML；实际命令另带人类可读 label |
| `python -m tools.update_principles_evidence --check --export-diagrams` | CURRENT，退出 0 | 文档证据与当前磁盘记录相符 |
| 数理文档静态检查 | PASS_STATIC_ONLY；0 错误、12 个原有警告 | 19 组 MathML、4 幅 SVG、108 个本地链接；不验证数学等价 |

机器记录见 `../../artifacts/verification_summary.json`、
`../../artifacts/viewer/acceptance.json`、`javascript_check.json`、`demo_refresh.json` 与 `principles_static.json`。
当前包和全部冻结副本的 raw、bundle、已捕获界面/适配器源码哈希均已核对。
便携 HTML 内嵌的当前包与冻结 JSON 相等，预载旧包也与其冻结 JSON 相等；90 个 DOM ID 唯一。
这只是静态结构和数据一致性证据，不是渲染或点击验收。

## 数值差异和复审

真实演示重新运行后的 9 份原始 CSV/JSON 与本轮更新前逐字节相同。
0D 数值检查记录仅三项 wall time 改变；误差、事件和守恒数值未变。
1D 未重新求解，原 18 个当前 run、10 个历史对照和既有精度失败继续原样展示。
原始 r2 与当前根压的有限差值约在浮点末位，属于相同方程/配置的复现对照。

Standards 轴关闭负源时钟拒绝问题：源时钟支持有符号安全整数，物理/交付时钟仍非负。
冻结目录覆盖入口也已拒绝，并有针对性回归。
Spec 轴关闭反射终端标签/比较场景混淆，以及缺少事件定义链接的问题。
不同终端、物理参数、输入身份或探针不能自动混算；方法、网格和 CFL 对照另作数值比较说明。

## 明确保留的未验证项

- 实际浏览器布局、窄屏和点击交互：`NOT_RUN_BROWSER_POLICY`。工具此前拒绝 file 协议并禁止绕过；未启动替代服务器或浏览器。
- 旧导出只记录 model.py 源身份，完整运行 Git、完整跨版本初态/RNG/队列身份仍缺失；不以打包时 Git 补写。
- 0D 心脏与独立 1D 尚未耦合；分布式球囊、完整能量账本、执行器/传感器校准仍未完成。
- 临床、生理及约 5 ms 端到端资格未建立。

较早的试产数据包及 demo 自动冻结包也保留在 runs 下，不覆盖、不冒充最终包；
读取当前与历史正式 V1 对照时以上述两个明确 ID 为准。
