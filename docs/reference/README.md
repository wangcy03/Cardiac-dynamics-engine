# IABP 引擎规格包 r1

本包把用户本轮确定的多通道 AP、II 导联起步、充放气命令接口、软件在环用途及约 5 ms 目标写入规格。

先读 `IABP_Engine_Spec_r1.md`。`CONFIRMED` 只表示用户已确认的需求；`ENGINEERING_DEFAULT` 表示可调整的工程设置。

- `CONTEXT.md`：领域词典，保留 r0 并补充时钟、通道、误差定义。
- `requirements.json`：需求与来源、时间目标。
- `verification_plan.json`：30 项待执行测试，全部为 NOT_RUN。
- `reference_configuration.json`：用于设计接口的工程参考配置；外部监护仪示例参数不是设备实测值，配置不等于可运行引擎。
- `research_r0/`：原设计、词典及原版本指纹，完整保留。
- `package_check.json`：只检查文件格式、关联和源文件保留，不测试任何生理模型。

本包没有新物理求解器，也没有模拟输出、患者验证或设备校准结果。现有 Wiggers 页面未修改。
