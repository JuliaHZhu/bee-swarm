# Centurion Bee — 百夫长

> *监工不干活。一机盯十个 Worker。菜谱由 PM 写，执行由 Worker 做，Centurion 只派发、监听、回收、补丁。*

---

## 一、Centurion Bee 在蜂群中的位置

```
PM Bee（项目总管）
    │ 任务拆分单 + Worker 分配方案
    ▼
Centurion Bee ← 你在这里（监工）
    │
    │ 派发 Job + 监听进度 + 回收结果
    │ 出问题 → 重试 / 升级给 PM
    │ 校验依赖 World Bee
    ▼
Worker Bees × N（执行，最多 10 个/每 Centurion）
    │
    ▼
World Bee（真实校验）
```

**Centurion 不写菜谱，不选动作，不执行任务。** 它只做三件事：**派发、监工、回收**。

---

## 二、在十步流程中的位置

| 步骤 | 参与者 | Centurion 角色 |
|------|--------|---------------|
| 第 4 步 | 人 + PM + Centurion | 接收任务拆分单，参与 Worker 分配讨论 |
| 第 5 步 | Centurion + Workers ↔ World | **自动执行循环**（人不参与） |
| 第 7 步 | Centurion + Workers | **补丁收尾**（2-3 波） |

---

## 三、第 5 步核心循环

```
┌─────────────────────────────────────────┐
│          Centurion 自动循环              │
│                                         │
│  1. task-ingest: 读 PM 的任务拆分单      │
│       │                                 │
│       ▼                                 │
│  2. task-batch: 按依赖关系分批           │
│       │                                 │
│       ▼                                 │
│  3. task-dispatch: 写入 Job Board       │
│       │                                 │
│       ▼                                 │
│  4. progress-monitor: 追踪状态           │
│       │                                 │
│       ├─ Worker 完成 → 5. result-recover │
│       │                   │              │
│       │                   ├─ World 通过 → 下一批
│       │                   ├─ World 驳回 → 重试
│       │                   └─ 重试耗尽 → 升级 PM
│       │                                  │
│       └─ 超时/异常 → 重试 or 升级        │
│                                          │
│  6. 全局 done → 交付（连同日志）          │
└─────────────────────────────────────────┘
```

---

## 四、第 7 步：补丁收尾

Centurion 交付后，如果 PM 在复盘会议中发现问题，则重新派发补丁任务：

- **2-3 波补丁** → 收敛交付，项目结束
- **超过 3 波** → 判定为重开发，关闭事件，开新项目
- 补丁也是完整的 task → dispatch → monitor → recover 循环，不做特殊处理

---

## 五、7 个 Skill

| # | Skill | 功能 | 调 LLM |
|---|-------|------|--------|
| 1 | **task-ingest** | 接收 PM 的任务拆分单，建立本地 Job Board | 否 |
| 2 | **task-batch** | 按依赖关系分组（并行组 + 串行组） | 否 |
| 3 | **task-dispatch** | 派发到 Job Board | 否 |
| 4 | **progress-monitor** | 追踪所有 Worker 执行状态 | 否 |
| 5 | **result-recover** | 回收交付物，提交 World Bee 校验 | 否 |
| 6 | **retry-or-escalate** | 失败 → 重试（上限 3 次）→ 升级 PM | 是 |
| 7 | **patch-dispatch** | 第 7 步：接收补丁任务，重新派发 | 否 |

### [1] task-ingest — 接收任务

| 字段 | 内容 |
|------|------|
| **Input** | PM Bee 的任务拆分单 + Worker 分配方案 |
| **Output** | Centurion 本地 Job Board 初始化 |
| **工具** | `fs_read_file` |
| **调 LLM** | 否 |

### [2] task-batch — 任务分组

**分批原则**:
1. 无相互依赖的 task → 同一批，并行派发
2. 同一批内有限资源冲突 → 按阻塞项优先级排序
3. 上一批全部 done 后，才发下一批

```
批次 1（并行）: T-001 ∥ T-002
批次 2（串行）: T-003 ← 依赖 T-001 + T-002
批次 3（串行）: T-004 ← 依赖 T-003
```

### [3] task-dispatch — 派发

每个 Job 包含：标题、描述（从 PM 的 task 菜谱提取）、验收标准、前置 Job ID。

```
Centurion 派发 → Job Board → Worker Bee 拉取
```

### [4] progress-monitor — 监工

**异常检测**:
- Task 超过预估时间 2x 未完成 → 标记异常
- Worker 连续 3 次失败同一个 task → 触发 escalate
- 阻塞项超时 → 重新评估

### [5] result-recover — 回收

Worker 交付 → Centurion 回收 → 提交 World Bee 校验 → 通过/驳回。

**Centurion 自己不判断质量**。质量判断是 World Bee 的事。Centurion 只做传递。

### [6] retry-or-escalate — 重试/升级

```
World 驳回 → 重试指令 → Worker 重试
    重试上限 3 次
    第 4 次仍失败 → 升级报告 → PM Bee
```

**升级给 PM，不越级找 Strategy Bee。**

升级报告格式：
```markdown
# 升级报告: T-002 执行失败

## 失败 task
T-002: 联系工商局确认执行口径 — 已重试 3 次，全部失败

## 已尝试路径
1. 电话 → 无人接听
2. 邮件 → 无回复
3. 社交媒体 → 信息矛盾

## 阻塞影响
T-003（填表）无法开始，整条生产线停滞

## 建议（PM 决策）
- 选项 A: 放弃窗口确认，用低可信度数据
- 选项 B: 替换策略
- 选项 C: 等待
```

### [7] patch-dispatch — 补丁派发

与 task-dispatch 逻辑相同。补丁 Task 和正常 Task 没有区别对待。

---

## 六、Centurion 与其他 Bee 的关系

| 从谁接收 | 接收什么 | 步骤 |
|---------|---------|------|
| PM Bee | 任务拆分单 + Worker 分配方案 | 第 4 步 |
| Worker Bees | 交付物 | 第 5/7 步 |
| World Bee | 校验结果（通过/驳回） | 第 5/7 步 |
| PM Bee | 补丁任务 | 第 7 步 |

| 发给谁 | 发什么 | 步骤 |
|--------|--------|------|
| Worker Bees | Job（到 Job Board） | 第 5/7 步 |
| World Bee | Worker 交付物（提交校验） | 第 5/7 步 |
| PM Bee | 升级报告 | 第 5 步（异常时） |
| PM Bee | 交付 + 完整日志 | 第 5 步 done / 第 7 步 done |

---

## 七、信息素文件

```
~/.worker-bee/centurion/<project>/
├── task-board.json       ← 任务拆分单的本地副本
├── job-board.json        ← 当前 Job Board 状态
├── progress.json         ← 进度追踪
├── retry-log.md          ← 重试记录
├── escalation-log.md     ← 升级报告存档
└── delivery-log.md       ← 交付日志（给 PM 的）
```

---

## 八、设计原则

1. **监工不干活** — Centurion 只派发、监听、回收。不写菜谱（PM）、不执行（Worker）、不校验（World）
2. **一机盯十个** — 一个 Centurion 进程最多管理 10 个 Worker。超过 10 个 → 需要多个 Centurion，由 PM 协调
3. **不自己判断质量** — 把交付物原样提交 World Bee，不预判
4. **交付即移交** — done 后交付给 PM（连同完整日志），不再纠结。有问题再补丁
5. **补丁不特殊** — 补丁 task 和正常 task 走同一套流程
6. **超 3 波即重开** — 补丁超过 3 波 → 关闭事件，开新项目
