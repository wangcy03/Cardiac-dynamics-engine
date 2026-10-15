# Boileau 公开一维动脉基准：来源、许可与接入约定

核查日期：2026-10-15（Asia/Singapore）。本页随 B01 基准适配和数值报告持续维护。

## 当前结论

公开数据已取得，获取障碍已解除：`public_input_availability=AVAILABLE`。下载完整性已核验。数值状态以独立运行报告与 `artifacts/arterial1d/benchmark_summary.json` 的各项范围为准，不能由数据可获取性推导为通过。取得数据、通过解析用例和复现公开基准是三个不同的结论。它们均不代表临床验证，也不确定真实生理事件的毫秒级误差。

本次仅取得单脉冲均匀管段 Benchmark 1 的原始压缩包、总说明、Figshare 版本元数据和 CC0 条款；未取得病例数据或受限资料，未将论文图形数字化作为输入。Benchmark 2–6 不在本次下载范围。

## 一手来源链

1. [Boileau et al., 2015，论文 DOI 10.1002/cnm.2732](https://onlinelibrary.wiley.com/doi/10.1002/cnm.2732)：正式论文身份及作者补充数据入口。出版者页面另有约 36.4 MB 的总补充包；本次没有下载该总包。
2. [King's College London 机构数据记录](https://kclpure.kcl.ac.uk/portal/en/datasets/a-benchmark-study-of-numerical-schemes-for-one-dimensional-arteri/)：指向数据 DOI `10.6084/m9.figshare.1586944`，将其与论文建立关联。
3. [Figshare 固定版本 DOI](https://doi.org/10.6084/m9.figshare.1586944.v1) 与 [公共 API v1](https://api.figshare.com/v2/articles/1586944/versions/1)：实际文件名、字节数、MD5、关联论文 DOI、作者和许可来源；原始 JSON 已留存。
4. [Swansea 作者稿](https://cronfa.swan.ac.uk/Record/cronfa22154/Download/0022154-24062016154300.pdf)：本次实际读取的参数和方程来源。表 II 位于作者稿印刷页 18（PDF 第 20 页）；式 (14) 位于印刷页 8（PDF 第 10 页）；本构式 (3) 位于印刷页 3（PDF 第 5 页）。这是作者稿，不能将其页码写成正式出版版页码。

API 当前给出的数据许可为 `CC0`，链接 [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)。本地保存了 [官方法律文本](https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt)。该许可来自数据条目，不自动扩展为论文 PDF 的再分发许可；本仓库没有保存论文全文。仍保留作者和 DOI 归属，避免将独立实现表述为作者认可。

## 保留的文件与哈希

原始字节位于 `artifacts/arterial1d/external/boileau2015/`。下载均为无登录的公开 HTTPS 请求，最终由 PowerShell `Invoke-WebRequest` 保存。完整文件来源、压缩包成员哈希和坐标检查见该目录的 `manifest.json`；整体 SHA256 清单见 `SHA256SUMS.txt`。

| 原始文件 | 精确下载地址 | 字节数 | SHA256 |
|---|---|---:|---|
| `Benchmark1_SinglePulseModel.zip` | https://ndownloader.figshare.com/files/2386679 | 976099 | `da31f4730aa3236e6dd3a686cc92a9bc19887807122b7b31f73c0ae695a2f86e` |
| `Data_README_1-6_consolidated.txt` | https://ndownloader.figshare.com/files/2382481 | 5142 | `922dc96ddc0377fa7188550553bea6a953d96d1536e258584a3a491579bbfe29` |
| `figshare_article_1586944_v1.json` | https://api.figshare.com/v2/articles/1586944/versions/1 | 8559 | `1e19fe90398faa9beab638f57b9c815a434da41498ed8b88b1da7ff6bbfdc6c4` |

发布者给出的 ZIP MD5 为 `3eddc3dfae6bca6baf270be8ce7a1a2d`，总说明 MD5 为 `623c88a22c6b38eed800e8c8ef6fa4f0`；本次计算均一致。ZIP CRC 检查通过，包内 12 张数值表合计 50406 行，每行均为 9 列有限数。这些是数据完整性检查，不能标记成传播器验证 PASS。

## Benchmark 1 的具体物理配置

这是无心脏、无球囊的均匀长管单脉冲测试，适合独立传播模块。`case1_source_config.json` 是从论文转录并作 SI 换算的配置，不是冒充作者发布的机器输入文件。原始包没有单独的入口采样文件；入口按论文式 (14) 解析定义。

| 量 | 原文值 | 本项目 SI 值 |
|---|---|---|
| 长度 $L$ | $10\,\mathrm{m}$ | $10\,\mathrm{m}$ |
| 参考面积 $A_0$ | $\pi\,\mathrm{cm^2}$ | $\pi\times10^{-4}\,\mathrm{m^2}$ |
| 密度 $\rho$ | $1050\,\mathrm{kg/m^3}$ | $1050\,\mathrm{kg/m^3}$ |
| 壁厚 $h$ | $1.5\,\mathrm{mm}$ | $0.0015\,\mathrm{m}$ |
| 弹性模量 $E$ | $400\,\mathrm{kPa}$ | $400000\,\mathrm{Pa}$ |
| 参考/外部/出口压力 | $P_d=P_{ext}=P_{out}=0$ | $0\,\mathrm{Pa}$ |
| 初态 | $A=A_0,\;U=0,\;P=0$ | $Q=0\,\mathrm{m^3/s}$ |
| 黏度 | $\mu=0$ 或 $4\,\mathrm{mPa\,s}$ | $0$ 或 $0.004\,\mathrm{Pa\,s}$ |
| 速度剖面指数 | $\zeta=9$ | 无量纲 |

入口只指定流量，不同时强制压力：

$$
Q_{in}(t)=10^{-6}\exp[-10000(t-0.05)^2]\quad[\mathrm{m^3/s}],\qquad t\ [\mathrm{s}].
$$

出口为完全吸收边界（反射系数为零），不等同于固定零压力边界。

论文的壁参数与 B01 的 `beta_pa` 同名但量纲不同。对均匀管段，原式可写成：

$$
P-P_{ext}=P_d+\frac{\beta_{paper}}{A_0}(\sqrt A-\sqrt{A_0}),\qquad
\beta_{paper}=\frac43\sqrt\pi E h\quad[\mathrm{Pa\,m}].
$$

因此 B01 的 $P=P_0+\beta_{B01}(\sqrt{A/A_0}-1)$ 应使用：

$$
\beta_{B01}=\frac{\beta_{paper}}{\sqrt{A_0}}=80000\ \mathrm{Pa},\qquad
c_0=\sqrt{\frac{\beta_{B01}}{2\rho}}=6.17213399848\ \mathrm{m/s}.
$$

由这些值推得 $Z_0=\rho c_0/A_0=2.06288383410\times10^7\,\mathrm{Pa\,s/m^3}$，小信号峰压约 $20.62884\,\mathrm{Pa}$。这些是声明的换算/推导值，不是新增测量。

原文黏性配置对应动量源：

$$
S_f=-2(\zeta+2)\pi\nu\frac QA=-22\pi\nu\frac QA,\qquad
\nu=\mu/\rho.
$$

B01 可选的 Poiseuille 近似为 $-8\pi\nu Q/A$。两者系数不同；在未实现并声明一致的摩擦模型前，只能先作公开 **inviscid** 数值比较。不能把使用 $8\pi$ 的结果标成该论文 **viscous** 原案复现。

## 原始参考列与比较约定

压缩包内 `Benchmark1_SinglePulseModel/NumData/X_Y.txt` 的 `X` 为 `DCG, LCG, FEM, FVM, McC, STM`，`Y` 为 `inviscid, viscous`。

- 第 1 列是距离 $x$，单位 m。
- 第 2–9 列是压力，单位 **kPa**，依次对应 $t=0.1,0.3,0.5,0.7,0.9,1.1,1.3,1.5$ s；进入核心比较时乘 $1000$ 得 Pa。
- 这些是多个时刻的**空间剖面**，不是每个位置的时间序列，也不是流量参考。
- FVM 两表各 1000 行，$x=0.005$ 到 $9.995$ m，严格递增，适合优先做中心坐标比较。
- DCG 两表各 5000 行，相邻重复坐标各 999 处；若使用，必须声明界面左右值的处理方式，不能直接交给假定严格递增的插值器。
- 参考表包含各方法的离散误差和极小数值负值，不应剪裁、逐列重标度或按峰值归一化后计算绝对误差。

实现核验建议：冻结以上配置；在记录的原始时刻读取本引擎状态；声明空间采样/插值与网格；对每个原始剖面计算 Pa 误差、峰值误差和峰位置差；同时保留不同网格及一阶/高阶方案的独立结果。禁止用时间或空间平移后的误差替代原始误差。公开表不提供入口/出口逐步通量，体积守恒仍需用本引擎的实际边界通量核验。

## 维护责任与状态变化

首次接入工具后，数值报告应引用数据包 SHA256、配置来源、方案、网格、CFL、误差定义及返回码。本页的来源和许可结论不随求解器成败变化；数值复现是否通过由独立运行产物决定。数据版本或内容变化时，保留旧哈希并重新核查许可，不覆盖旧证据。

工具的公开运行会在开始时捕获配置与压缩包原字节，从这些字节解析，并独立保留 `data_identity.before/after`（原包、manifest、配置 SHA256）。运行结束和证据汇总再次核对，不把结束后重新读取的配置哈希误当成开始时使用的输入。源码身份保存在独立的 `identity` 字段。
