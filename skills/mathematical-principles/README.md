# mathematical-principles

用于把第一性原理、实现和真实运行证据维护为可离线阅读的正式 HTML。
版本源在仓库 `skills/mathematical-principles/`；安装时将该目录作为同字节副本放入个人技能目录，
不把具体机器路径写进技能正文。后续先改仓库版本，验证后再同步安装副本。

手动调用示例：

```text
$mathematical-principles create：为当前项目建立正式数理原理文档，先读规格与代码；没有真实运行就保留缺失。
$mathematical-principles update：按本轮变更局部更新原理、公式和真实证据，复用项目刷新器，保留历史失败。
$mathematical-principles check：只审计现有文档的推导映射、身份、陈旧性和离线静态结构，不改文件、不重跑模型。
```

静态检查命令（相对路径均相对 `--root`）：

```text
python <skill-dir>/scripts/check_document.py --root <project-root> --document docs/MATHEMATICAL_PRINCIPLES.html --output artifacts/principles_static_check.json
```

退出 0 / `PASS_STATIC_ONLY` 仅表示离线静态契约通过，不能替代 freshness、浏览器渲染或数值验证。
不加 `--output` 时仅向标准输出输出 JSON。检查器不联网、不求解、不修改文档。

本技能包含起始模板、静态检查器、通用推导/适配约定和按需读取的心脏工程参考。
`evals/` 是技能评测输入，不是任何项目的真实运行证据；不拿评测夹具生成验收结论。

检查静态工具的公开接口与已知误报/破坏风险（仅使用临时合成文档，不运行项目模型）：

```text
python -m unittest discover -s <skill-dir>/evals -p "test_*.py"
```
