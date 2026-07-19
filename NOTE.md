# Bee Swarm — 开发笔记（聊天档）

> 这是给自己看的。随便写。

---

## 我到底想干什么

把 **nanobot 的 tool calling** 和 **hermes agent 的框架能力** 搞到一起，做一个最小可用的多智能体协作框架。

不要 Redis、不要 Kafka、不要 Docker、不要数据库。
只要文件系统 + rename 原子操作。

---

## 已经完成的

| Phase | 内容 | 状态 |
|-------|-------|-------|
| Phase 1 | File-as-Bus 协议骨架 + PM/Centurion/Worker 三层分工 | ✓ 18/18 测试通过 |
| Phase 2 | nanobot MemoryStore + GitStore 桥接，每个 bee 有独立 Git 记忆空间 | ✓ 32/32 测试通过 |

---

## 还没做的（下一步）

1. **接真 LLM backend** — 现在只有 Mock，需要实际调用 OpenAI/Claude API
2. **nanobot 的 Tool Calling 全套移植** — 工具注册表、JSON Schema 校验、工具调用循环
3. **hermes agent 的 Agent Loop 融合** — session 管理、上下文压缩、多轮对话
4. **知识图谱自动建链** — 现在只有 SQLite 骨架，需要任务完成后自动提取概念并建链
5. **Web UI / 观测** — 现在靠 `ls`，需要一个简单的界面看蜂群状态

---

## 核心信念

- 规约到不能规约
- 命名规范即协议
- 文件系统即总线
- 无锁、无中央调度器、无外部依赖

---

*写于 2026-07-19 — 这个项目还在长。*
