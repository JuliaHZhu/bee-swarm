---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 2725045121849659_7576853131280810010-data_volume/7647463580660547874-files/所有对话/主对话/worker-bee/design_notes/02b-skeleton-skills.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 2725045121849659#1784195013121
    ReservedCode2: ""
---
# Skeleton Bee — 总工程师/首席架构师（CAO）

> 版本：MVP v3.1（红队修订版）
> 日期：2026-07-16
> 前身：v1 Step2出场 → v2 24/7首席架构师（过度设计，已归档 `archive/02b-skeleton-skills-v2.md`）→ v3 MVP（核心设计正确，但"人确认/复盘/对齐"靠信任和记忆，无持久化痕迹）

---

## 为什么存在

项目开始前要有人画蓝图——目标是什么、核心约束是什么、产出长什么样、复杂度多大。没蓝图就开工，后面全是返工。
Skeleton 唯一的职责：**给每个生产批次画对蓝图。**

---

## 核心约束（技术硬约束，不是文档约定）

```python
CONSTITUTION_PATHS = {"arch/"}

def safe_write(path: str, content: str, approved_by: str = ""):
    """
    写 arch/ 必须带 approved_by（厂长在回路时的批准标记）。
    Research Mode 不提供 approved_by，写 arch/ 直接报错。
    drafts/ 无需批准。
    """
    if any(p in path for p in CONSTITUTION_PATHS):
        if not approved_by:
            raise PermissionError(f"写 arch/ 必须提供 approved_by：{path}")
        # 在内容头部嵌入批准元数据
        content = f"<!-- Approved by: {approved_by} | {datetime.now().strftime('%Y-%m-%d')} -->\n" + content
    path_obj.write_text(content, encoding="utf-8")
```

**规则**：
- Campaign Mode（厂长在回路）：写 `arch/<project>/`，必须传 `approved_by="厂长"`（或具体人名）
- Research Mode（执行期）：`approved_by=""`，写 `arch/` 直接抛异常，只能写 `drafts/`
- 批准信息嵌入文件头部HTML注释，不影响Markdown渲染，但30天后`cat arch/core.md | head -1`就知道谁批的、什么时候批的

这不是"AI获得了写宪法的权限"，而是"人在对话中实时确认，批准动作有文件级持久化痕迹"。和Aristotle"AI永远只写drafts/"的区别：Aristotle的宪法（dict.md）极低频更新，适合人完全手动merge；Skeleton的蓝图是每批次必须产出的5个文件，Campaign时5步流程同步阻塞，每步都要等人工merge太重，所以用"批准元数据嵌入"替代"drafts→人merge"流程。

---

## 目录结构

```
bee-skeleton/
├── arch/                      # 宪法：各项目正式蓝图（带批准元数据）
│   └── <project>/
│       ├── intent.md          # capture-intent 产出
│       ├── goals.md           # decompose-goal 产出
│       ├── core.md            # reduce-to-core 产出（🔥灵魂）
│       ├── archetype.md       # expose-archetype 产出
│       ├── complexity.md      # evaluate-complexity 产出
│       └── closure.md         # 🔥Campaign收尾强制产出（偏差/踩坑/提案）
├── patterns.md                # 参考：经多次验证的结构模式（人merge积累）
├── anti-patterns.md           # 参考：踩过的坑（人merge积累）
└── drafts/                    # 草稿区：Research Mode唯一可写目录
    ├── pattern-*.md           # 新模式提案（来自closure的MERGE-PROPOSAL）
    ├── anti-pattern-*.md      # 新反模式记录
    ├── prototype-*.md         # 新产出形态原型草稿
    ├── audit-*.md             # 复杂度偏差记录
    └── refactor-*.md          # 重构提案
```

每个`arch/<project>/`蓝图文件头部必须有批准元数据：

```markdown
<!-- Approved by: 厂长 | 2026-07-16 -->
# Core: <project>
**规约到不能规约的核心**：...
```

`closure.md`是v3.1新增的强制文件，详见下文"Campaign收尾"一节。

### 蓝图文件格式

**intent.md**
```markdown
<!-- Approved by: 厂长 | 2026-07-16 -->
# Intent: <project>
**原始需求**：（用户/厂长说了什么）
**真正想要什么**：（一句话捕捉本质冲动）
**不做什么**：（明确排除的范围）
```

**goals.md**
```markdown
<!-- Approved by: 厂长 | 2026-07-16 -->
# Goals: <project>
## 目标层级
1. 顶层目标：...
2. 子目标：...
## 反目标（不达成什么）
- ...
```

**core.md**（最关键）
```markdown
<!-- Approved by: 厂长 | 2026-07-16 -->
# Core: <project>
**规约到不能规约的核心**：（一句话，删无可删）
**为什么是这个而不是别的**：
- 保留了：...
- 砍掉了：...（为什么）
**正交基底**：（核心由哪几个独立维度构成）
- 基底1：...
- 基底2：...
```

**archetype.md**
```markdown
<!-- Approved by: 厂长 | 2026-07-16 -->
# Archetype: <project>
**产出形态**：report / demo / pipeline / standard / deck ...
**结构模板**：（产出由哪些部分组成，顺序是什么）
**参考模式**：（是否复用 patterns.md 中的已有模式）
```

**complexity.md**
```markdown
<!-- Approved by: 厂长 | 2026-07-16 -->
# Complexity: <project>
| 维度 | 预估值 | 实际值（closure填写） | 偏差 |
|------|--------|---------------------|------|
| 时间 | O(?) | | |
| 认知负荷 | O(?) | | |
| 概念密度 | O(?) | | |
| Worker 需求 | ? 个 | | |
| 补丁轮次 | ? 轮 | | |
```

**注意**：complexity.md里"实际值"和"偏差"列在Campaign Step5时留空，等closure.md时回填。这让"预估vs实际"对比有明确位置，不靠记忆。

### patterns.md / anti-patterns.md 格式

```markdown
# Patterns

## pipeline-linear
- 适用：内容生产类（写作/调研/报告）
- 结构：输入规范 → N个串行阶段 → 输出规格 → 质检门
- 用过：3次（最后更新：2026-07-16）
- 备注：阶段间不要循环依赖
```

```markdown
# Anti-Patterns

## circular-dependency
- 症状：A等B的输出，B等A的输出
- 根因：正交基底没切干净
- 踩过：2次（最后踩：2026-07-16）
- 怎么避：画依赖图，检查环
```

---

## Campaign Mode：批次总工（5步+1收尾）

### 5步核心原语（保留v1实战验证的流水线）

| 步骤 | 原语 | 做什么 | 产出 |
|------|------|--------|------|
| 1 | **capture-intent** | 把原始冲动锚定成文字，划清"做/不做" | intent.md |
| 2 | **decompose-goal** | 目标层级展开，写清反目标 | goals.md |
| 3 | **reduce-to-core** | 🔥 层层删，规约到不能再删的一句话核心+正交基底 | core.md |
| 4 | **expose-archetype** | 暴露产出形态和结构模板 | archetype.md |
| 5 | **evaluate-complexity** | 多维度量纲评估（预估值，实际值留空） | complexity.md |

每步产出写`arch/<project>/`，带approved_by元数据。Step3（core.md）是灵魂，决定Step4选什么结构、Step5怎么估。

启动时先查`patterns.md`和`anti-patterns.md`——有能复用的直接用，有已知反模式主动规避。没有就从0设计。

### 被其他Bee喊时的强制行为约定

当Cardmaster/PM/World喊Skeleton时，**第一回复不是给判断，是确认上下文**：

```
"当前项目 <project> 核心规约是「X」，正交基底是 Y/Z，你问的是不是 Z 相关的问题？"
```

对方确认后再给判断。这避免"各自拿着不同版本蓝图对话"——零成本，纯行为约定，不需要任何协议或文件。

### 🔥 Campaign收尾：closure.md（v3.1新增，强制产出）

项目完成（生产批次报告归档）后，Skeleton必须产出`arch/<project>/closure.md`，**不需要等谁喊**——这是Campaign的正式结束信号。

```markdown
<!-- Approved by: 厂长 | 2026-07-16（closure也需要人确认） -->
# Closure: <project>

## 复杂度偏差（回填complexity.md）
| 维度 | 预估 | 实际 | 偏差原因 |
|------|------|------|---------|
| 时间 | O(?) | O(?) | ... |
| 补丁轮次 | ?轮 | ?轮 | ... |

## 本次踩的坑（一句话一条）
1. ...
2. ...

## 可提炼的模式（MERGE-PROPOSAL）
- [ ] `pattern-<name>.md`：（一句话描述可复用的结构，draft已写好）
- [ ] 无新模式可提炼

## 应记录的反模式（MERGE-PROPOSAL）
- [ ] `anti-pattern-<name>.md`：（一句话描述踩的坑，draft已写好）
- [ ] 无新反模式

## 废弃的模式/反模式
- （如果本次实战证明某个已有模式/反模式不对，在这里标注）
```

**closure的作用**：
1. **把复盘从可选项变成必选项**——不产出closure，Campaign不算结束
2. **complexity偏差自动回填**——3个Research skill中的complexity-recal不再需要"手动触发"，closure本身就是校准记录
3. **MERGE-PROPOSAL强制列出可提炼项**——人花30秒批yes/no打勾，不需要主动去翻drafts/
4. **pattern/anti-pattern的draft由Skeleton在closure时自动写好**，人只需要决定merge还是discard

closure.md本身也需要approved_by——人确认偏差记录和提案后，Skeleton写closure入arch/，对应draft入drafts/。

---

## Research Mode：架构研究员（3个skill，由closure驱动）

v3说"手动触发"是错的——靠人记着喊就等于不会触发。v3.1改为：**3个skill全部由closure驱动或定时检查驱动，不需要人单独喊。**

| Skill | 做什么 | 产出 | 触发时机 |
|-------|--------|------|---------|
| **pattern-mining** | closure里标记"可提炼模式"时，自动写`drafts/pattern-*.md` | 模式提案draft | Campaign closure自动触发 |
| **anti-pattern-log** | closure里标记"踩坑"时，自动写`drafts/anti-pattern-*.md`；或World报告架构违规时随时记录 | 反模式draft | closure自动触发+问题出现时随时记 |
| **complexity-recal** | closure时自动回填complexity.md的实际值列+偏差原因，写`drafts/audit-*.md`记录校准 | 校准记录 | Campaign closure自动触发 |
| **triple-scan**（v3.1新增） | 每完成3个项目，主动跑一次全量扫描：(1)所有complexity偏差汇总 (2)patterns.md使用率 (3)是否有被证伪的模式 | `drafts/audit-scan-N.md` | 每3个项目自动触发 |

**人只需要做的事**：
1. closure产出后看MERGE-PROPOSAL，打yes/no——30秒
2. 打yes的pattern/anti-pattern，人merge进patterns.md/anti-patterns.md（更新"用过N次"计数）
3. triple-scan报告出来后扫一眼，决定是否需要调整模式库或启动重构

**人不需要做的事**：
- 不需要记得喊"跑一下复盘"——closure强制产出
- 不需要主动翻drafts/看有什么提案——MERGE-PROPOSAL列好了
- 不需要对比预估和实际——complexity.md留了位置，closure自动回填

### pattern-mining和anti-pattern-log的draft内容

Skeleton在写closure时，如果识别到可提炼的模式或坑，**同时**写好对应的draft文件，人merge时不需要从零写：

`drafts/pattern-pipeline-linear.md`：
```markdown
# Pattern Proposal: pipeline-linear
- 来自项目: <project>
- closure中的MERGE-PROPOSAL已标记
- 适用：...
- 结构：...
- 正交性验证：...
```

人merge到patterns.md时精炼几句话即可，不需要从零组织内容。

---

## 其他 Bee 怎么用

| Bee | 读什么 | 怎么交互 |
|-----|--------|---------|
| **厂长（人）** | 全部；Campaign实时确认5步+closure，批MERGE-PROPOSAL，merge pattern/anti-pattern | Campaign对话，closure审阅30秒 |
| **PM** | arch/<project>/complexity.md（排期依据）+ anti-patterns.md（避坑） | 需要架构裁决时喊Skeleton（Skeleton先确认上下文） |
| **Cardmaster** | arch/<project>/archetype.md（pipeline蓝图） | Produce需要内部结构设计时喊Skeleton（Skeleton先确认上下文） |
| **World** | arch/<project>/（执行基线）| 校验发现架构违规时报告（Skeleton写anti-pattern draft） |
| **Strategy** | patterns.md/anti-patterns.md（看什么结构可行） | 方向决策参考 |

喊一声、读一个文件、先对齐上下文再回答——没有消息队列、没有结构化协议、没有主动推送。

---

## 升级路线图（按需触发，v3.1加入主动扫描）

v2文档（`archive/02b-skeleton-skills-v2.md`）是完整设计储备。

**被动触发信号**（等问题出现才升级）：

| 信号 | 升级动作 | 参考 v2 设计 |
|------|---------|-------------|
| patterns.md 超过30条单文件太长 | 拆为 patterns/ 目录 | pattern-library 独立目录 |
| 多次踩同类型坑但anti-pattern没提前预警 | 引入接口审计流程 | interface-audit skill |
| 新类型任务第一次总是估不准 | 引入原型沙盒预研 | archetype-prototypes |
| 多项目并行、架构债务积压 | 引入重构预案流程 | refactor-prep |
| 跨Bee接口真的出现循环依赖/冗余 | 做定期接口审计 | interface-audit + structure-metrics |
| 项目规模增长到当前结构hold不住 | 引入规模化预案 | scaling-prep |

**主动扫描信号**（不等待失败，定期检查）：

| 信号 | 动作 |
|------|------|
| 每完成3个项目 | triple-scan自动跑全量偏差扫描（已内置，不是升级项） |
| triple-scan连续2次报告同一模式"成功率下降" | 审查该模式是否应降级或拆分为anti-pattern |
| patterns.md中有模式"用过0次"超过5个项目 | 清理或标记suspended |

**核心原则：closure是保底，triple-scan是早期预警，被动信号是升级触发。** 不全被动等失败，也不提前筑墙。

---

## 不做的事（和 v2 的区别）

| v2 设计 | MVP 不做 | 为什么 |
|---------|---------|--------|
| 10个Research skill | 3个+1个triple-scan（closure驱动） | 3-5熟手工具；7个无真实消费者 |
| 8个独立信息素目录 | 3个位置（arch/patterns+anti-patterns/drafts） | YAGNI |
| structure-metrics量化指标 | 不做 | 正交是判断力不是公式 |
| archetype-prototypes原型沙盒 | 不做 | 新类型遇一次设计一次 |
| complexity-bench/benchmarks.json | 不单独建，complexity.md实际值列+closure审计记录自然积累 | 项目不够多不需要独立基准库 |
| interface-audit定期审计 | 不做 | 出问题anti-pattern-log记 |
| refactor-prep重构预案库 | 不做 | 重构直接Campaign讨论 |
| cross-pollinate跨域授粉 | 不做 | 灵感是人的事 |
| scaling-prep规模化预案 | 不做 | 没到规模 |
| method-sharpen方法论打磨 | 不做独立skill | closure+triple-scan自然积累 |
| "人记得去复盘/merge" | 不做——closure强制产出+MERGE-PROPOSAL | 靠记忆=不会发生 |
| "人对话里说行就算确认" | 不做——文件头部approved_by元数据 | 口头确认无痕迹=30天后不可追溯 |
| 异步推送/消息队列 | 不做 | 手动pull，closure自动产出 |

---

## v3→v3.1 修订记录（红队回应）

| 红队Kill-Assumption | v3问题 | v3.1修复 |
|---------------------|--------|---------|
| KA1："人确认"无持久化痕迹 | 对话里说"行"无记录，30天后不知道谁批的 | 每个arch/文件头部嵌入`<!-- Approved by -->`元数据，safe_write强制要求approved_by参数 |
| KA2：patterns"人merge"靠主动翻 | 人不会定期翻drafts/，模式库过时 | closure强制产出MERGE-PROPOSAL，人30秒打yes/no；Skeleton同时写好pattern/anti-pattern draft |
| KA3：Research skill触发靠记忆 | "手动触发"=不会触发，5个项目后预估还是拍脑袋 | closure.md强制收尾产出，complexity实际值回填，3个Research skill由closure自动驱动 |
| KA4：Bee间"喊一声"靠自觉对齐 | 两人对核心规约理解不一致，设计冲突 | 被喊时第一回复强制确认上下文（核心规约+正交基底），再回答 |
| KA5：safe_write是文档伪代码 | 任何skill都能写任何目录，约束只在文档里 | safe_write硬编码approved_by检查，写arch/不传就raise PermissionError |
| 升级路线图全被动等失败 | 复杂度偏差/模式失效等问题"多次出现"时损失已发生 | 加triple-scan每3项目主动扫描，连续异常触发审查 |

---

## 设计哲学

- **蓝图是核心产出**——5步流水线是灵魂，特别是reduce-to-core
- **模式和反模式从实战长出来**——closure强制提炼，人30秒审批
- **架构是判断力不是指标体系**——正交/内聚靠训练有素的判断
- **宪法必须有批准痕迹**——口头"行"不算数，文件头部元数据才是防火墙
- **强制动作优于记忆依赖**——closure、MERGE-PROPOSAL、上下文确认、approved_by都是"不用记也会发生"的机制
- **文件即数据**——纯Markdown，零依赖，grep即查询
- **小而精**——3+1个Research skill，3个目录位置，一条代码级权限约束

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
