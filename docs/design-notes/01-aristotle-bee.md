# Aristotle Bee — 术语管家

> **版本：v4 MVP（已实现）**
> **实现位置**：`bee-knowledge/aristotle.py`
> **设计文档**：`docs/design/aristotle-v4.md`
>
> 前身 v3.1 的过度设计已归档至 `archive/01b-aristotle-skills-v3.1.md`。

---

## 定位

多 Agent 说同一个词时意思不一样，沟通就坍塌了。

Aristotle 唯一的职责：**让大家说的是同一个东西。**

它不是只在某个阶段参与的临时工，而是持续在场的术语管理员——有人喊它就工作，没人喊它就等着。

---

## 核心约束（一条铁律）

```python
BLOCKED = {"dict.md", "decisions/"}

def _guard(path: str) -> None:
    for p in BLOCKED:
        if p in path:
            raise PermissionError(f"AI 不能写 {p} — 只能写 drafts/")
```

- **人**维护 `dict.md` 和 `decisions/`（宪法）
- **AI（Aristotle）**所有产出写 `drafts/`（草稿）
- 宪法更新 = 人把草稿 merge 进宪法，不是 AI 直接改

没有双模式权限状态机，没有精细字段级规则，没有文件系统只读挂载。**一条路径检查就够了。**

---

## 目录结构

```
bee-knowledge/
├── aristotle.py      # 10 skills + 5 tools
├── dict.md           # 术语词典（人维护）
├── decisions/        # 决策日志 NNNN-slug.md（人维护）
└── drafts/           # AI 草稿区（Aristotle 唯一可写目录）
```

### dict.md 格式

```markdown
## swarm
- **Definition**: 多Agent协作系统，由有限规则组合产生无限行为，强调自组织涌现
- **Status**: stable
- **Notes**: 区别于 multi-agent system——swarm 强调涌现和自组织
```

Status 只有三值：`stable`（已确认）/ `draft`（待讨论）/ `suspended`（暂不定义）。

### decisions/ 格式

```markdown
# 0001: swarm 定义边界

**Context**: 多Agent系统和蜂群系统的边界在讨论中反复混淆
**Decision**: swarm = 有限规则×无限生成的多Agent系统，强调自组织涌现
**Date**: 2026-07-16
**Notes**: （可选）
```

---

## Skills（10 个）

Aristotle 只会这 10 件事，不多不少。

### Campaign Mode（7 个）

| Skill | 输入 | 输出 | 触发 |
|-------|------|------|------|
| **define** | 一个概念 + 上下文对话 | `drafts/define-<term>.md` | 讨论中出现无定义的新词 |
| **fork** | 一个术语 + 两种实际用法 | `drafts/fork-<term>.md` | 发现同一词被用作两个意思 |
| **resolve** | 一个 fork draft + 讨论结论 | `drafts/resolve-<term>.md` | fork 待解决 |
| **align** | 术语 + 实际误用实例 | `drafts/align-<term>.md` | 发现某 Bee 用错词 |
| **decide** | 争议 + 拍板结论 | `drafts/decide-<NNNN>-<slug>.md` | 术语争议有人拍板 |
| **grill** | 一个术语定义 + 追问角度 | `drafts/grill-<term>.md` | 定义看起来不稳 |
| **relate** | 两个术语 + 关系类型 | 写入 `drafts/define-*.md` 的 Notes 字段（See also） | define 时附带 |

### Research Mode（3 个）

| Skill | 输入 | 输出 | 触发 |
|-------|------|------|------|
| **drift-watch** | 日志/对话文本 | `drafts/drift-YYYY-MM-DD.md` | 人喊："看看有没有用错词" |
| **ammo-prep** | 请求方问题 + dict.md | `drafts/ammo-<topic>.md`（标 `[DRAFT]`） | 其他 Bee 问"X 是什么意思" |
| **audit-debt** | drafts/ 目录快照 + dict.md | `drafts/audit-YYYY-MM-DD.md` | 批次收尾时人喊："清算一下" |

---

## Tools（5 个）

Skills 不直接碰文件系统，通过 Tools 操作。

| Tool | 功能 | 被谁用 | 铁律 |
|------|------|--------|------|
| **dict-reader** | 读取 `dict.md`，返回术语列表+定义 | 所有 skill | 只读 |
| **decision-reader** | 读取 `decisions/NNNN-*.md` | decide, audit-debt | 只读 |
| **draft-writer** | 写入 `drafts/*.md` | 所有 skill | **唯一可写入口** |
| **log-scanner** | `grep` 日志/对话中的术语使用实例 | drift-watch | 只读，不解析格式 |
| **git-commit** | `git add + git commit` drafts/ 变更 | 所有 skill 完成后自动调用 | 只提交 drafts/ |

---

## 语法规则（Skills 怎么组合）

不是任意组合，有合法转移：

```
define ──► relate（定义时顺手标关系）
   │
   ▼
grill（定义不稳就追问）
   │
   ▼
fork（追问发现歧义）
   │
   ▼
resolve（解决歧义）
   │
   ▼
decide（拍板后记录）
   │
   ▼
[人 merge 进 dict.md / decisions/]
```

**非法组合**（代码层禁止）：
- `define` 不能直接写 `dict.md` → 必须经过 `draft-writer` → 人 merge
- `drift-watch` 不能直接改 `dict.md` → 只能写 `drafts/drift-*.md`
- `decide` 不能直接写 `decisions/` → 只能写 `drafts/decide-*.md`

---

## 其他 Bee 的接口（不是 skills，是约定）

| Bee | 读 | 写 |
|-----|----|----|
| **Cardmaster** | `dict-reader` + 找人要 `drafts/ammo-*.md` | 不写 |
| **World** | `dict-reader` | 不写（漂移信号通过 PM/人转达）|
| **Strategy** | `dict-reader` + `decision-reader` | 不写 |
| **PM** | 读全部；协调 Campaign Mode | 人通过 PM 调度，PM 不直接调 skill |
| **人** | 读全部 | 唯一有权把 draft merge 进 `dict.md`/`decisions/` |

没有 API、没有消息队列、没有事件协议。**"接口"就是文件路径。**

---

## 用法

### 作为模块

```python
from aristotle import define, drift_watch, dict_reader

define("swarm", "在今天的讨论中，我们说 swarm 是...")
drift_watch(open("chat.log").read())
print(dict_reader())
```

### 作为 CLI

```bash
cd bee-knowledge

# 定义
python aristotle.py define "swarm" "上下文文本"

# 漂移检测
python aristotle.py drift_watch "日志内容"

# 清算草稿债务
python aristotle.py audit_debt
```

CLI 跑完后自动 `git commit`。

---

## 一句话

> **10 个 skills × 5 个 tools × 1 条 if 语句 = Aristotle 的全部。**

没有第 11 个 skill，没有第 6 个 tool，没有第二层约束。
