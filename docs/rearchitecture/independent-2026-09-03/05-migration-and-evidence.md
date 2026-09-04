# Migration and Evidence

## 阶段

1. S0：冻结本包合同和用户方向记录。
2. S1：实现 Paper Search Adapter、receipt、candidate admission；legacy native path 保留。
3. S2：Reader/Writer 改为 domain ports，Skill 只替换方法层。
4. S3：加入 experiment/artifact/claim/manuscript lineage。
5. S4：当第二个真实 capability consumer 出现后，再决定 plugin lifecycle。

## Legacy/target 对照

同一 paper-search fixture 同时走 native 与 fake adapter；比较 PaperRecord、evidence、knowledge projection、diagnostics、receipt、failure、replay、checkpoint 和 project files。

## Inventory

在 S1 开始前运行同一脚本生成 baseline 和 target：直接 concrete Store/Evidence imports、registry entries、Application constructor dependencies。脚本和两份输出必须进入 package evidence；依赖数量只能作为辅助指标。

## 回滚/停止

parity、sole-writer、unknown recovery 或 revision check 失败：停止 target promotion，保留 facade 和 native path；不接入真实远程 MCP。
