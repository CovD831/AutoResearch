# 迁移与证据计划

S0 合同冻结：完成本包并等待三项用户决策。S1 Literature Pilot Adapter：native connector 为 legacy fixture，受控 fake capability 为 target fixture；同一 query 比较 PaperRecord、diagnostic、receipt、EvidenceCandidate、Gate 和 checkpoint。S2 Reader port：仅在 S1 通过后扩展阅读。

每阶段必须有同场景 legacy/target fixture、成功/失败/超时/冲突 replay/重启测试、依赖与注册清单、持久化事实和 receipt 对照。性能只作为命名基线下的附加证据，不替代语义等价。

晋级门：`pytest -q`、`ruff check src tests`、旧 CLI/API 仍可运行、Evidence 唯一写入者成立、无重复 evidence、restart/resume 通过。任何 receipt/state/checkpoint/失败语义不等价则停止，保留旧 facade 并修订合同。
