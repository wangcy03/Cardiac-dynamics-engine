# 第三方与分发说明
核心代码本轮新建，未导入外部模型源代码；开发依赖的许可由各软件包提供。
legacy/ 包含用户既有教学HTML及其中的来源/临床片段，保持原文件；本轮未重新认定其数据许可。
对外公开发布前应单独核实 legacy 内所有资料许可。本包用于用户私有项目交接，不替用户选择开源许可。
不包含字体文件、访问令牌、患者身份信息或受限数据库凭证。

## B01 公开数值参考数据
Boileau et al., 2015, A benchmark study of numerical schemes for one-dimensional
arterial blood flow modelling，单脉冲 Benchmark 1 原始数值输出。
数据固定版本 DOI：[10.6084/m9.figshare.1586944.v1](https://doi.org/10.6084/m9.figshare.1586944.v1)。
Figshare 数据条目明确给出 CC0；原包、发布元数据、CC0 官方条款与文件哈希保存在
artifacts/arterial1d/external/boileau2015/，来源及换算说明见
[BOILEAU_PROVENANCE.md](docs/benchmarks/BOILEAU_PROVENANCE.md)。
保留作者归属；该许可仅说明数据条目的许可，没有向本项目转让论文全文或作者背书。
本仓库未导入研究团队的求解器源代码，也未保存论文全文。

文档中的科学图由本机 Matplotlib 读取本项目真实导出 CSV 生成。
未打包 Matplotlib 库或字体文件；绘图环境和输入哈希随图单独记录。
