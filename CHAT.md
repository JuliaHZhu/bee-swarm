# Chat Log — 2026-07-19

> 随意写的，当作聊天。记录当下在想什么。

---

## 今天的目的

把 **nanobot 的 tool calling** 和 **hermes agent** 搞到一起。

不是简单拼起来，是让 nanobot 那套 tool-use（注册表、JSON Schema、调用循环）能长在 hermes agent 的框架里。

hermes 有 session、有 skill 体系、有记忆管理；nanobot 有干净的 tool calling 抽象。两边各取所长，拼成一个最小可用的东西。

---

## 为什么现在想搞这个

Phase 1（File-as-Bus + 三层蜂群）和 Phase 2（MemoryStore + GitStore）都跑通了。
骨架有了，但 Worker Bee 还是 mock 的，不会真的调 tool。

下一步就是给 Worker Bee 装上真脑子：
- 能调用外部 tool（搜索、读文件、写文件、执行代码）
- 能利用 hermes 的 session / context 管理能力
- 所有调用痕迹进 Git，可追溯

---

## 极简原则不变

- 无 Redis / Kafka / Docker / 数据库
- 文件系统即总线，Git 即时间轴
- 先能用，再好用

---

*随手记，随时改。*
