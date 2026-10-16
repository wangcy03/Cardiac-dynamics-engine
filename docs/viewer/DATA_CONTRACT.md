# 固定观察器数据合同 v1

`tools.viewer_data.build_bundle(root, demo_dir, arterial_dir, run_id, label)` 只读取已存在的导出。
生产代码仅标准库，不导入引擎、不调用求解器、不修改输入 CSV/JSON、不合成压力或事件。
调用方将返回对象保存为 JSON，并用固定 `viewer/` 页面读取。

## 外形

```json
{
  "schema": "cardiac-observer/v1",
  "run": {
    "id": "r2-b01-20261016",
    "label": "r2 + B01 独立传播",
    "generated_utc": "2026-10-16T00:00:00+00:00",
    "git": {"commit": "打包时 Git SHA，或 null", "dirty": true},
    "simulation_git": null,
    "source_sha256": {"iabp/model.py": "打包时文件哈希"},
    "source_status": "MIXED_RECORDED_SCOPE",
    "files": [{"path": "artifacts/demo/baseline_truth.csv", "sha256": "原始字节哈希", "bytes": 0, "role": "physical_truth", "roles": ["physical_truth"]}],
    "provenance": {"heart": {}, "initial_state": {}, "bundle_scope": "OFFLINE_EXPORT_ONLY"}
  },
  "heart": {"channels": [], "cases": {}, "metric_definitions": {}},
  "arterial1d": {"runs": [], "suites": [], "summary": null},
  "warnings": [],
  "capabilities": []
}
```

上面是字段示例，字符串占位值不是实际身份；真实包保留实际哈希、Git 状态、字节数和原始值。
文件路径均为项目根目录内的相对路径，以 `/` 分隔。`run.files` 包含实际读取的原始记录、
声明哈希的日志/报告及用于身份核对的源码/历史快照，可供冻结器逐字节复制。
JSON 使用有限数；未知值为 `null`，缺记录为 `[]`/`{}` 并附原因，不用零补值。

## 0D 心脏/时序

`heart.channels` 为 `{key,label,unit,group}` 数组。`key` 是 truth CSV 原列名；实际 r2 含 33 列。
压力为 `mmHg`，容积/血量为 `mL`，流量为 `mL/s`，合成 ECG 为 `mV`，状态代理为 `1`。
`time_us` 为物理微秒。未知新通道保留原值，但 `unit=null`、分组 `unclassified` 并发出警示。

`heart.cases.baseline` 和 `.assisted` 均含：

| 字段 | 含义 |
|---|---|
| `label,columns,rows` | CSV 列名/顺序与全部数值，不舍入、不重采样；数值按 Python float 的往返精度保存 |
| `samples` | 原 samples CSV 转对象；保留通道、单位、序号、值、质量、交付和源时钟 |
| `events,commands` | 原事件/命令状态 JSON 对象；不补 R 峰、切迹、动作目标或缺失事件 |
| `metrics` | provenance 中原指标；缺失时保持空集 |
| `window_us,metric_window_us` | 第一和最后 truth 行的绝对物理时间 `[start,end]`；指标全窗不随可视缩放变化 |
| `metric_check` | 对导出样本的只读积分/极值核对；`derived` 是核对数，不替换原指标 |
| `source_identity,source_status` | 原记录提供的源码身份及与当前/快照的核对结果 |
| `clock_semantics` | 时钟说明，供信息面板读取 |

`samples` 的 `t_available_us` 是进入收件箱的时刻，不是控制器 callback 的执行时刻。
`source_time_us` 是可选传感器源时钟；`AP_MONITOR` 未公开时保持 `null`，
`source_clock_id` 缺失也保持 `null`。这两个时钟不与 truth 的物理时间混为同一语义。
源时钟包含传感器配置的时钟偏移，允许负值；有值时须为有符号安全整数
`[-(2^53-1), 2^53-1]`。物理时间、样本交付时间和事件/命令时刻仍为非负安全整数。
事件和命令 `at_us` 保留原记录；命令接受/开始/完成是不同状态。

`heart.metric_definitions[指标 key]` 含 `label,unit,definition,method,window='full_record'`。
当前六个指标是最大绝对血量残差、根部压最小/最大值、球囊最大容积、
净主动脉出流和 LV 净外部功。后两者分别按相邻原始行的实际时间差做梯形积分、
按 `-Σ(P_i+P_(i+1))/2·(V_(i+1)-V_i)` 计算。不强制闭合 PV，不能当作稳态单搏 SV。
记录指标与导出全窗不一致将拒绝打包；数值核对容差只用于浮点运算顺序差异。

`heart.initial_state` 同时进入 `run.provenance.initial_state`：
`first_exported_state_equal` 只核对首行；`within_demo_shared=null`、`cross_iteration=null`
表示旧导出未记录可重核的完整快照/RNG/队列身份。
脚本使用同进程共享快照这一实现事实不被首行相等提升为跨迭代全状态一致性证据。

## 独立 1D

`arterial1d.runs` 读取四个套件的逐 run JSON：`matched/reflections/junction/boileau`。
当前共 28 个导出 run：18 个当前源码候选和 10 个保留的一阶/MUSCL 历史对照。
不读取进程中止目录代替完整运行，不把低阶失败移出视图。

每个 run 含 `id,label,suite,method,cells,status,summary,trace,profiles,source_status,
source_identity,source_mismatches,historical,failures,result_path,missing_reason,run_git`。
`summary` 原样保留逐 run JSON，包括参数、阈值相关误差、负压振铃、未复现项、输入数据身份。
`label` 包含原 `case`、方法和格数；若原记录有顶层 `outlet`，也在标签中明示。
因此同格数反射的 `closed/pressure_release/resistance_2z0` 可直接区分，终端名称不靠波形推断。
`run_git` 仅取原 JSON；没有则 `null`，绝不取打包时 Git。
`suites` 为 `{id,label,path,summary}` 数组，保留原套件汇总；总体汇总另在 `arterial1d.summary`。

`trace/profiles` 有数据时统一为：

```json
{"columns": ["time_s", "x_m", "pressure_pa", "reference_pa"],
 "rows": [[0.1, 0.005, -0.0000005, -0.000002]],
 "units": {"time_s": "s", "x_m": "m", "pressure_pa": "Pa", "reference_pa": "Pa"},
 "kind": "spatial_profiles", "path": "项目内原 CSV 路径",
 "display_sampling": "none; all exported rows retained", "times_s": [0.1]}
```

这是结构示例，不是运行结果。实际 `time_trace` 常含 `probe_x_m,flow_m3_s` 及守恒误差；
反射含 `forward_pressure_pa,backward_pressure_pa`；分叉含 `parent_*/child*`。
列顺序和数值始终来自原 CSV。单位按显式列名后缀 `Pa/m/s/m2/m3/m3/s` 声明，
不与心脏页的 `mmHg/mL` 隐式互换。空间剖面另含实际导出时刻 `times_s`。
Boileau 只有八个时刻的空间剖面，`trace=null`，`missing_reason` 解释没有连续探针时序。
负值原样保留，不裁剪、不归一化、不平移。

`status` 是原逐 run 布尔检查 `pass/*_pass` 的展示：有 false 为 `FAIL_DECLARED_CHECKS`，
全 true 为 `PASS_DECLARED_CHECKS`，无声明为 `NOT_DECLARED`。
`failures` 指明具体 false 字段。这不是重新执行数值验收，不能替代汇总器的数值判据与证据门。

## 身份与失败行为

| `source_status` | 只表示源码身份，不表示验证等级 |
|---|---|
| `RECORDED_SOURCE_MATCH` | 原记录提供的每个源码哈希与打包时对应源码一致 |
| `PARTIAL_RECORDED_SOURCE_MATCH` | 旧 0D 仅提供 `model.py`，该项一致，其他运行源未知 |
| `HISTORICAL_SOURCE` | 与当前源码不同，原哈希能对应已保存并核验的历史源码；仍不归属当前核心 |
| `SOURCE_MISMATCH` | 原哈希无法匹配当前或已记录快照；必须显示警示 |
| `NOT_RECORDED` | 未记录可归属源码，不回填当前源码 |
| `MIXED_RECORDED_SCOPE` | 顶层包包含上述不同记录范围，应查看各分支/run |

只有在历史 manifest 同时绑定逐 run 原 JSON 和原套件报告时，旧无逐 run 源码身份的对照
才能继承该套件的历史源；不能仅凭文件名、方法名或当前 CSV 可读就继承身份。
当前源码、历史原身份和打包 Git 分别保存。数据文件 SHA 只证明当前打包的字节，
旧记录没有运行时哈希时警示这一缺口。

错误 JSON/重复键、坏 schema、非有限数、坏 CSV/重复列/列宽不符、
无数值行、时钟倒退、非法路径和声明文件哈希不匹配抛出 `BundleError`，拒绝产出包。
无法归属的源码身份可读取并显示，但 `SOURCE_MISMATCH` 明确警示；冻结/发布方须保留此状态，
不得把它改为通过。输入在整个适配过程中保持原字节。
空缺 1D 目录支持历史 0D-only 包，返回 `runs=[]`、能力标志及警示，不造 1D 数据。

合同版本标识用于固定页面拒绝不兼容输入；任何未来字段语义改变应升级 schema 或显式迁移。
本合同不增加 0D/1D 耦合、球囊分布、临床校准或 5 ms 端到端资格。
