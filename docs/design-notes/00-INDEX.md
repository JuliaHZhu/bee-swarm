# Design Notes

> **声明：本目录是设计愿景与架构探讨文档，部分功能尚未在代码中实现。**
> 具体已实现的功能请以代码为准。

本目录包含 Worker Bee 的设计文档 — 基于同一套核心 shell 的专业化认知工具。

| 文件 | 说明 |
|------|------|
| [01-aristotle-bee.md](01-aristotle-bee.md) | 定义大师 — 术语守护 |
| [02-skeleton-bee.md](02-skeleton-bee.md) | 骨架规约器 — 从模糊想法到不可再分约束 |
| [03-pm-bee.md](03-pm-bee.md) | 编排优化器 — 现实材料分解与排期 |
| [04-world-bee.md](04-world-bee.md) | 环境引擎 — 现实检查、数据验证 |
| [05-centurion-bee.md](05-centurion-bee.md) | CenturionBee — 代理店长与日结工 |
| [07-full-agent-ecosystem.md](07-full-agent-ecosystem.md) | 全 Agent 蜂群：分层架构与双仓库 |
| [08-strategy-bee.md](08-strategy-bee.md) | 策略引擎 — 决策与路径优化 |
| [09-cardmaster-bee.md](09-cardmaster-bee.md) | 卡牌大师 — 技能组合与状态管理 |

## 外部架构研究

[architecture-study/](architecture-study/) — 外部架构论文与系统的对比拆解，用于参考设计和定位 Worker-Bee 的差异化。

| 文件 | 说明 |
|------|------|
| [aevo-harnessing-agentic-evolution.md](architecture-study/aevo-harnessing-agentic-evolution.md) | AEvo: 把进化建模成交互式环境，meta-agent 编辑搜索机制而非产生候选 |
| [autogenesis-self-evolving-agent-protocol.md](architecture-study/autogenesis-self-evolving-agent-protocol.md) | AGP: 双层自进化协议——RSPL 资源注册层 + SEPL 闭环算子层，填补 MCP/A2A 的资源管理空白 |

## 核心架构

见仓库根目录的 [README.md](../README.md) — Deck、Registry、Skill 系统、Batch Handoff。
