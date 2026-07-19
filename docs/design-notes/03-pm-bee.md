# PM Bee — 项目总管

> *从头脑风暴到菜谱，从排期到监听汇总结案。*

---

## 一、PM Bee 的三重角色

PM Bee 在十步流程中出现三次，每次角色不同：

| 步骤 | 参与者 | PM 角色 |
|------|--------|--------|
| **第 3 步** | 人 + PM | 排期协调：调研现实条件，联系内外部，安排工作排期 |
| **第 4 步** | 人 + PM + Centurion | 拆分配兵：拆分任务，决定需要几个 Worker，与 Centurion 对接 |
| **第 6 步** | PM（后台监听） | 全局汇总结案：监听所有 Centurion 交付，分析漏洞，100% 时通知人开会 |

---

## 二、角色一（第 3 步）：排期协调

### 输入
- Strategy Report（第 1 步产出）
- 牌型 + 验收标准（第 2 步产出）

### 做什么
1. 调研现实条件：可用时间、预算、人员、工具
2. 联系内外部人员/部门，确认协作窗口
3. 排出粗略工作排期（大阶段时间线，不进入 task 级细节）

### 产出
- 排期表（大阶段级）
- 资源协调记录（联系了谁、确认了什么）

---

## 三、角色二（第 4 步）：拆分配兵

### 参与者
人 + PM Bee + Centurion Bee

### 做什么
1. PM 负责拆：把项目按第 2 步的验收标准拆成独立任务
2. Centurion 负责配：决定需要几个 Worker Bee，每个 Worker 的能力匹配
3. 人与 PM 共同确认任务拆分方案
4. PM 将最终方案移交给 Centurion，此后不再介入执行

### 产出
- 任务拆分单
- Worker 分配方案（给 Centurion）

---

## 四、角色三（第 6 步）：全局汇总结案

### 模式
**后台监听，不主动干预。**

PM Bee 持续监听所有 Centurion Bee 的交付日志和产出，分析记录：

1. **漏洞与不符合处**：哪些交付偏离了验收标准
2. **准备会议议题**：为补丁/复盘会议准备议程，只记录不行动
3. **进度 100% 触发**：所有 Centurion 管辖的 worker 都交付完成时

### 100% 时的动作
当全局进度到 100%，PM Bee 自动通知人：
- 建议开会时间（早上或次日早上）
- 附带漏洞清单和议题草案

**人看到通知后自行定日程。PM 不等回复，不催。**

---

## 五、角色零（底层能力）：行动计划生成器

PM Bee 底层有一整套**菜谱生成流水线**——当需要在第 4 步拆任务时，这套机制自动运转。

### 信息素文件体系

```
~/.worker-bee/pm/<project>/
├── GOAL.md                  ← 头脑风暴（人写，自由格式）
├── PLAN.md                  ← 行动计划（PM 生成，LOCKED 后只读）
├── PLAN.lock                ← 决策锁
├── state.json               ← 执行状态追踪
├── _internal/
│   ├── 01-goal-parsed.md    ← 结构化目标摘要
│   ├── 02-irreducibles.md   ← 不可约分环节清单
│   ├── 03-tasks-raw.md      ← task 骨架列表
│   ├── 04-recipes.md        ← 完整 task 菜谱
│   ├── 05-deps.md           ← 依赖图
│   ├── 06-resources.md      ← 资源估算
│   └── 07-contingency.md    ← 容错矩阵
└── delivery/
    ├── diffs/
    ├── state.json
    └── follow-ups.md
```

### 9 步流水线

```
GOAL.md
  │
  ▼
[1] goal-parse        → 01-goal-parsed.md     （解析目标）
  │
  ▼
[2] irreducible-extract → 02-irreducibles.md  （提取不可约分环节）
  │
  ▼
[3] task-decompose    → 03-tasks-raw.md       （拆成 task 骨架）
  │
  ▼
[4] task-recipe       → 04-recipes.md         （填充菜谱）
  │
  ├─────────────────────────────────────┐
  ▼                                     ▼
[5] dependency-graph  → 05-deps.md     [6] resource-estimate → 06-resources.md
  │                                     │
  └─────────────┬───────────────────────┘
                ▼
[7] contingency-plan  → 07-contingency.md    （容错矩阵）
                │
                ▼
[8] plan-assemble     → PLAN.md              （组装最终计划）
                │
                ▼
[9] plan-lock         → PLAN.lock            （决策锁）
```

### [4] task-recipe — 最核心的 skill

每个 task 填满全部 9 个字段，是 Centurion Bee 派发的依据：

| 字段 | 含义 |
|------|------|
| Input | 需要的输入文件/数据 |
| Output | 产出什么（精确到文件路径） |
| 时间 | 预估耗时 |
| 资源 | 所需工具/平台 |
| 人员 | 执行者 |
| 前置 | 依赖哪些 task |
| 阻塞项 | 是否阻塞后续 |
| 容错 | 失败后的备选路径 |
| 完成标准 | 怎样算 done |

---

## 六、PM Bee 与其他 Bee 的关系

| 从谁接收 | 接收什么 | 步骤 |
|---------|---------|------|
| Strategy Bee + Skeleton | 战略报告 + 牌型 + 验收标准 | 第 3 步 |
| 人 | 确认信息、排期反馈 | 第 3-4 步 |
| 所有 Centurion Bee | 交付日志、产出 | 第 6 步（监听） |

| 发给谁 | 发什么 | 步骤 |
|--------|--------|------|
| Centurion Bee | 任务拆分单 + Worker 分配方案 | 第 4 步 |
| 人 | 100% 通知 + 漏洞清单 + 议题草案 | 第 6 步 |

---

## 七、PM Bee 的 Skill 总表

| # | Skill | 功能 | 调 LLM |
|---|-------|------|--------|
| 1 | goal-parse | 解析自由格式 GOAL → 结构化摘要 | 否 |
| 2 | irreducible-extract | 提取不可约分环节 | 是 |
| 3 | task-decompose | 拆成 task 骨架 | 是 |
| 4 | task-recipe | 填充 9 字段菜谱 | 是 |
| 5 | dependency-graph | 生成依赖图 + 关键路径 | 否 |
| 6 | resource-estimate | 资源估算 + 冲突检测 | 否 |
| 7 | contingency-plan | 容错矩阵 | 否 |
| 8 | plan-assemble | 组装 PLAN.md | 否 |
| 9 | plan-lock | 决策锁 | 否 |
| 10 | schedule-coordinate | 第 3 步：排期 + 协调内外部 | 是 |
| 11 | task-allocate | 第 4 步：与 Centurion 拆分 + 分配 | 否 |
| 12 | monitor-all-centurions | 第 6 步：监听所有 Centurion 交付 | 否 |
| 13 | gap-analyze | 第 6 步：漏洞分析 + 议题准备 | 是 |
| 14 | notify-100percent | 第 6 步：全局 100% → 通知人 | 否 |

---

## 八、设计原则

1. **第 3-4 步人在回路，第 6 步人不在回路** — PM 第 6 步是纯后台监听
2. **不催促，只通知** — 100% 时发一次通知，不反复提醒
3. **只记录不行动** — 第 6 步发现的漏洞只记录为议题，不自行处理
4. **交接即退场** — 第 4 步完成后 PM 不再介入执行（第 6 步是只读监听）
