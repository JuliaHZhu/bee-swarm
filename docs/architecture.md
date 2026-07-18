# Bee Swarm 架构设计

## 1. 设计哲学

蜂群系统是一个基于 **File-as-Bus**（文件即总线）的分布式协作框架。
所有 Bee（智能体）通过文件系统进行通信，没有消息队列、没有 RPC、没有数据库服务。

> 命名规范即协议，文件系统即总线，pull 模式即调度。

## 2. 三层架构

```
┌─────────────┐
│   PM Bee    │  向上负责：想法 → 实现方案
│  (规划层)   │  产出：高层任务卡片
└──────┬──────┘
       │ 写入 task_pool/
       ▼
┌─────────────┐
│ Centurion Bee│ 向下负责：分活 + 调度容量
│  (调度层)    │ 产出：子任务卡片 + 状态流转
└──────┬──────┘
       │ 写入 task_pool/
       ▼
┌─────────────┐
│  Worker Bee │ 执行：调用工具完成具体任务
│  (执行层)   │ 产出：artifact 文件 + 完成标记
└─────────────┘
```

### 2.1 PM Bee（产品经理蜂）
- **职责**：将高层次的目标/想法转化为可执行的任务规划
- **输入**：用户需求、项目目标
- **输出**：`pm_` 前缀的任务卡片，包含任务描述、验收标准
- **触发**：外部调用 / 手动创建

### 2.2 Centurion Bee（百夫长蜂）
- **职责**：领取 PM 任务，拆分为 Worker 可执行的子任务；监控子任务完成状态
- **输入**：`task_pool/` 中 `pm_` 或 `centurion_` 前缀的任务
- **输出**：`worker_` 前缀的子任务卡片；汇总父任务结果
- **触发**：轮询 `task_pool/`

### 2.3 Worker Bee（工蜂）
- **职责**：执行具体的工具调用任务（读写文件、搜索等）
- **输入**：`task_pool/` 中 `worker_` 前缀的任务
- **输出**：`artifacts/` 中的产出物 + 完成后的任务卡片移入 `done/`
- **触发**：轮询 `task_pool/`

## 3. File-as-Bus 协议

### 3.1 目录结构

```
workspace/
├── task_pool/      # 待领取任务池
├── in_progress/    # 进行中的任务
├── done/           # 已完成的任务
└── artifacts/      # 产出物（按任务ID组织）
```

### 3.2 任务卡片命名规范

格式：`{prefix}_{task_id}_{status}.json`

| 前缀 | 含义 | 产生者 | 消费者 |
|------|------|--------|--------|
| `pm` | PM 规划任务 | PM Bee | Centurion Bee |
| `centurion` | Centurion 拆分/汇总任务 | Centurion Bee | Worker Bee / Centurion Bee |
| `worker` | Worker 执行任务 | Centurion Bee | Worker Bee |

状态流转：
- `pending` → 待领取（在 `task_pool/` 中）
- `claimed` → 已领取（移入 `in_progress/`）
- `done` → 已完成（移入 `done/`）
- `failed` → 失败（移入 `done/`，状态标记为 failed）

**完整文件名示例**：
- `pm_001_goals_pending.json` — PM 生成的待领取任务
- `worker_001_01_write_file_pending.json` — 可被 Worker 领取的子任务
- `centurion_001_summary_claimed.json` — Centurion 正在汇总的任务

### 3.3 任务卡片格式（JSON）

```json
{
  "task_id": "pm_001_goals",
  "parent_id": null,
  "type": "pm",
  "title": "创建项目文档",
  "description": "为新项目创建 README 和架构文档",
  "status": "pending",
  "priority": "normal",
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z",
  "created_by": "pm_bee_01",
  "assigned_to": null,
  "acceptance_criteria": [
    "README.md 包含项目介绍",
    "docs/architecture.md 包含架构图"
  ],
  "tool": null,
  "tool_params": null,
  "subtasks": [],
  "artifact_paths": [],
  "result": null,
  "error": null,
  "metadata": {}
}
```

字段说明：
- `task_id`: 唯一任务标识，与文件名一致（不含状态后缀）
- `parent_id`: 父任务 ID，用于追踪任务树
- `type`: 任务类型 `pm` / `centurion` / `worker`
- `tool`: Worker 任务专用，指定要调用的工具名
- `tool_params`: Worker 任务专用，工具参数
- `subtasks`: Centurion 任务的子任务 ID 列表
- `artifact_paths`: 产出物路径列表（相对 workspace 根目录）
- `result`: 执行结果摘要
- `error`: 错误信息（失败时）

### 3.4 产出物（Artifact）命名规范

产出物存放在 `artifacts/{task_id}/` 目录下，文件名为任务产出的实际内容。

示例：
```
artifacts/
└── worker_001_01_write_file/
    └── README.md
```

### 3.5 状态流转协议

**领取（Claim）**：
1. Bee 在 `task_pool/` 中扫描匹配前缀的 `_pending.json` 文件
2. 原子操作：将文件移动到 `in_progress/` 并将状态改为 `claimed`，同时写入 `assigned_to`
3. 若移动失败（并发冲突），则跳过该任务

**完成（Complete）**：
1. Bee 更新任务卡片的 `status` 为 `done` / `failed`
2. 写入 `result` 或 `error`
3. 将文件从 `in_progress/` 移动到 `done/`

**子任务发现**：
- Centurion 拆分任务时，直接将子任务写入 `task_pool/`
- Worker 完成任务后，Centurion 通过扫描 `done/` 中父任务对应子任务的完成状态来推进

## 4. 底座（Base Layer）

基于 nanobot 提取核心能力，保留 MIT 版权声明。

### 4.1 Agent Loop（极简）
- 输入：系统提示 + 用户消息 + 工具定义
- 循环：LLM 调用 → 工具调用 → 结果回注 → 下一轮
- 终止：达到最大轮次 或 LLM 返回最终回复

### 4.2 Tool Calling
- 工具基类：`name` / `description` / `parameters` / `execute()`
- 工具注册：`ToolRegistry` 管理工具注册和调度
- 参数校验：JSON Schema 校验

### 4.3 LLM Backend
- 抽象接口：`chat_completions()` 方法
- OpenAI 兼容实现：支持 OpenAI 格式 API
- Mock 实现：用于测试，无需真实 API Key

## 5. 知识图谱层（Knowledge Layer）

第一阶段为极简骨架，借鉴 CRG（Cognitive Resource Graph）思路：

- 使用 SQLite 存储节点和边
- 节点类型：task、artifact、concept、file
- 边类型：depends_on、produces、references、contains
- 第一阶段只写入不查询，作为未来扩展的基础

## 6. 并发与调度

- **Pull 模式**：每个 Bee 独立轮询任务池，没有中央调度器
- **原子操作**：使用文件系统的 rename（同分区原子）实现任务领取
- **并发安全**：每个任务只能被一个 Bee 领取（rename 原子性保证）
- **幂等性**：所有 Bee 脚本设计为可重复执行

## 7. 关键设计决策

### 7.1 为什么用 File-as-Bus 而不是消息队列？
- 极简：零基础设施依赖，文件系统到处都有
- 可观测：`ls` 就能看到所有任务状态，天然可调试
- 持久化：消息不会丢，进程重启不影响
- 并发安全：rename 是原子操作

### 7.2 为什么是三层而不是更多？
- PM → Centurion → Worker 对应了"做什么 → 怎么拆 → 谁来做"的经典分工
- 三层足以覆盖大多数软件协作场景
- 更多层可以通过 Centurion 的递归拆分实现（Centurion 可以生成 Centurion 任务）

### 7.3 半异构角色设计
- 所有 Bee 共享同一个底座（agent loop + tool calling + LLM backend）
- 不同 Bee 通过加载不同的系统提示和工具包来差异化角色
- 好处：代码复用率高，新增角色只需写 prompt + 工具配置
