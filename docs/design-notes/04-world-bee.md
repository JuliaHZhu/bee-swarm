# World Bee — 真实校验 + 运维知识库

> *第一道防线：过滤事实错误。第二道防线：拼凑环环相扣的证据链。*
> *第三职能：复盘归档，区分机制性方案 vs 无解 gap，skill 运维提醒。*

---

## 一、World Bee 的三种职能

| 职能 | 角色 | 触发 | 消费者 |
|------|------|------|--------|
| **免疫过滤**（第一道） | 事实校验 → 过滤错误 → 重试指令 | 每个 Worker 提交产出 | Centurion（重试指令） |
| **证据链引擎**（第二道） | 交叉验证 → 拼凑证据 → 阶段性结论 + 新假设 | 多个 Worker 产出汇集 | Strategy Bee（战役报告） |
| **复盘归档**（第三职能） | 生产问题归档 → 区分有/无机制性方案 → skill 运维提醒 | 项目结束后 | Worker Bee（下次使用提醒） |

---

## 二、核心假设

1. **Worker Bee 没有 subagent 机制** — 它不会自己查自己。出错就交给 World Bee 检测 → Centurion 重试。
2. **流程切细碎** — 每个 skill 做一件事，错了只回滚那一步，不用整个阶段重做。
3. **后期合并** — 细碎 skill 跑通后，相邻的纯规则 skill 可以合并。
4. **证据链必须是闭环的** — 不能只靠一个 Worker 的数据下结论。至少 2 个方向的数据相互印证。
5. **回报 Strategy Bee** — World Bee 不做战略决策，只把"验证过的数据 + 发现的新问题"打包给 Strategy Bee。

---

## 三、在十步流程中的位置

| 步骤 | 参与者 | World Bee 角色 |
|------|--------|---------------|
| 第 5 步 | Centurion + Workers ↔ World | 自动执行循环中的实时校验 |
| 第 7 步 | Centurion + Workers ↔ World | 补丁阶段的校验 |
| 第 8 步 | 生产问题 ↔ World | **复盘归档**（运维） |
| 第 9 步 | World → Strategy | 提供验证数据给战役报告 |

### 第 8 步详解：复盘归档

**触发**: 项目所有补丁（第 7 步）完成后。

**做什么**: 把生产过程中暴露的所有问题跟 World Bee 对账，分两类：

| 类型 | World Bee 动作 |
|------|---------------|
| **有机制性方案但没用对 skill** | 记录为 skill 运维提醒，下次 Worker 执行时自动提醒正确使用 |
| **没有机制性方案** | 记录为未解决的 gap，留待后续研究 |

**运维提醒格式**:
```json
{
  "task_type": "financial_writing",
  "problem": "Worker 使用了错误的税率（旧税法）",
  "mechanism_exists": true,
  "correct_skill": "tax-law-lookup",
  "reminder": "写财务数据前先调用 tax-law-lookup 确认当前税率"
}
```

---

## 四、信息素文件体系

```
~/.worker-bee/world/<project>/
├── ledger.json                  ← 所有 Worker 产出的注册表
├── verified/                    ← 通过验证的干净数据
├── suspect/                     ← 可疑但未驳回的
├── rejected/                    ← 驳回的数据 + 原因
├── _internal/
│   ├── 01-ingested.json
│   ├── 02-normalized.json
│   ├── 03-fact-checked.json
│   ├── 04-verdicts.json
│   ├── 05-pairwise.json
│   ├── 06-triangulated.json
│   ├── 07-contradictions.json
│   ├── 08-evidence-chain.md
│   ├── 09-summary.md
│   ├── 10-hypotheses.md
│   └── 11-gaps.md
├── reports/
│   └── strategic-<date>.md      ← 给 Strategy Bee 的定期报告
└── ops/
    ├── known-gaps.md            ← 无机制性方案的 gap 日志
    └── skill-reminders.json     ← 有机制性方案的运维提醒
```

---

## 五、14 步细碎流水线

```
Worker 产出
    │
    ▼
── 阶段 0：接收与标准化 ──
[1] data-ingest       → ledger.json            登记入库
[2] data-normalize    → 02-normalized.json     提取可验证 claims
    │
    ▼
── 阶段 1：事实校验（第一道防线）──
[3] fact-check-basic   → 03-fact-checked.json  格式/完整性/明显错误
[4] fact-check-source  → 03-fact-checked.json  来源可信度评分
[5] fact-check-internal → 03-fact-checked.json  内部一致性
[6] fact-verdict       → 04-verdicts.json      通过/可疑/驳回
    │
    ├─ 驳回 → Centurion（重试指令）
    ├─ 可疑 → suspect/
    └─ 通过 → verified/
    │
    ▼
── 阶段 2：交叉验证（第二道防线）──
[7] cross-pairwise      → 05-pairwise.json     两两对比
[8] cross-triangulate   → 06-triangulated.json 3+ 源一致确认
[9] cross-contradiction → 07-contradictions.json 矛盾检测
[10] evidence-chain     → 08-evidence-chain.md  拼凑证据链
    │
    ▼
── 阶段 3：汇总与假设 ──
[11] summary-synthesize → 09-summary.md         阶段性结论
[12] hypothesis-generate → 10-hypotheses.md     新假设
[13] gap-detect         → 11-gaps.md            信息缺口
[14] report-strategic   → reports/strategic-*.md 回报 Strategy Bee
```

### 追加 Skill（第 8 步复盘用）

| # | Skill | 功能 | 调 LLM |
|---|-------|------|--------|
| 15 | ops-classify | 将生产问题分类：有机制性方案 vs 无 | 是 |
| 16 | ops-skill-reminder | 有机制性方案 → 生成 skill 运维提醒 | 否 |
| 17 | ops-gap-log | 无机制性方案 → 记录到 known-gaps.md | 否 |

---

## 六、阶段 1 判定矩阵

```
pass = basic_check==pass AND source_credibility>=medium AND internal_consistency==pass
suspect = basic_check==pass AND (source_credibility==low OR internal_consistency==fail)
reject = basic_check==fail

pass → verified/
suspect → suspect/
reject → rejected/（附原因）→ 触发 Centurion 重试
```

---

## 七、三角验证置信度

| 源数量 | 置信度 |
|--------|--------|
| 1 | low — 孤证 |
| 2 | medium — 需要更多验证 |
| ≥3 | high — 可信 |

---

## 八、设计原则

1. **不信孤证** — 任何结论至少 2 个方向的数据印证
2. **流程切细碎** — 错了只回滚一步
3. **运维知识可积累** — 每次项目的 gap 和 skill 提醒都归档，下次自动生效
4. **不做战略决策** — 只提供验证过的数据，决策权归 Strategy Bee 和人
