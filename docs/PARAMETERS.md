# 工程参数清单与可追溯性

所有下述默认值均为本轮工程选择，没有用论文给它们作临床背书。
精确可配置值由 `ModelConfig` / `EngineConfig` / `reference_sensors()` 及 demo/provenance.json 保存。

| 对象 | 单位／当前选值 | 状态 |
|---|---|---|
| LV/RV有效主动弹性 | 2.1 / 0.50 mmHg/mL | UNCALIBRATED |
| 主动脉根部/降主动脉顺应性 | 0.22 / 0.85 mL/mmHg | UNCALIBRATED |
| 体/肺外周阻力 | 1.1 / 0.09 mmHg·s/mL | UNCALIBRATED |
| 主动脉连接R/L | 0.08 mmHg·s/mL / 0.0007 mmHg·s²/mL | UNCALIBRATED |
| 张力两级上升/松弛τ | 50 / 35 ms | UNCALIBRATED |
| QRS→室驱动起点、驱动时长 | 35 / 230 ms | ENGINEERING_SCHEDULE，不是AO/AC定时 |
| 房驱动起点/时长 | P后20 / 100 ms | ENGINEERING_SCHEDULE |
| 可视ECG QRS时长/QT | 95 / 380 ms；R形态峰约QRS后30ms | SYNTHETIC_OBSERVATION |
| 恢复时间常数、每次消耗 | 600ms，乘0.5 | 仅间期记忆，不是PESP验证 |
| 开口ko/kc | 7 / 12 (mmHg·s)⁻¹ | UNCALIBRATED |
| MV/AV/TV/PV开瓣阻力 | 0.012/0.035/0.009/0.012 mmHg·s/mL | UNCALIBRATED |
| 关闭阻力 | 20 mmHg·s/mL | 有限泄漏；非严格密封 |
| MV/AV/TV/PV有效惯量 | .0002/.0004/.0002/.00015 mmHg·s²/mL | UNCALIBRATED |
| 流量事件与有效开口事件 | Qao过零；z上穿5%或下穿2% | MODEL_EVENT_DEFINITION |
| 球囊容量 | 默认40mL，可关闭 | ENGINEERING_SPIKE |
| 命令链延迟 | 5ms | 任意工程配置，不是用户5ms误差目标 |
| 固态/光纤/监护链 | 按代码/provenance独立记录 | 全部未测量；不能称真实器件模型 |

初始容积是一个受控启动状态，不是稳态患者：
LV120，根部70，降主动脉150，体静脉3000，RA55，RV120，肺动脉150，肺静脉500，LA60 mL。
18秒预热用于演示，没有额外宣布周期稳态已验证；正式稳态测试须比较归一化多搏残差。
