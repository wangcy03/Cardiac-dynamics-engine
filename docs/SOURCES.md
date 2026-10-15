# 来源与声明边界

原始 r0/r1 全文及出处在 docs/reference/，本轮没有复制外部研究代码、补充受限数据或新增临床记录。
以下公开摘要/官方页面于 2026-10-15 核查：

- Schampaert et al., 2013. Modeling the interaction between IABP and cardiovascular system: effect of timing.
  https://pubmed.ncbi.nlm.nih.gov/23263334/ 。支持用干预响应而非单个压力峰评价时序；不是本原型系数来源。
- Mynard et al., 2012. A simple, versatile valve model.
  https://pubmed.ncbi.nlm.nih.gov/25364842/ 。支持有限瓣膜运动状态；本原型不是其模型已校准复现。
- Codex AGENTS.md 官方说明： https://developers.openai.com/codex/guides/agents-md 。说明持久项目规则入口。
- 云环境官方入口： https://developers.openai.com/codex/cloud/environments 。本包不绑定特定云环境或账号设置。

本轮具体激活、阀阻、容积、顺应性、动作/传感器时间常数均为未校准工程选值。
不能引用以上论文给这些数值背书。无新的临床验证数据。

## B01 独立数值参考，2026-10-15

- [Boileau et al., 2015，论文 DOI 10.1002/cnm.2732](https://onlinelibrary.wiley.com/doi/10.1002/cnm.2732)。
  单脉冲均匀管的几何、本构与入口按作者稿核查；没有用这些工程用例给患者参数背书。
- [KCL 机构数据记录](https://kclpure.kcl.ac.uk/portal/en/datasets/a-benchmark-study-of-numerical-schemes-for-one-dimensional-arteri/)
  与 [Figshare 固定版本](https://doi.org/10.6084/m9.figshare.1586944.v1)。
  已实际获取 CC0 单脉冲原包，保留原始字节和哈希；许可/列含义/SI 换算见
  [BOILEAU_PROVENANCE.md](benchmarks/BOILEAU_PROVENANCE.md)。
  数值复现结论以实际 benchmark_summary.json 为准，数据可获得不等于复现通过。
