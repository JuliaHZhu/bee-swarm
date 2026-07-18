"""
PM Bee（产品经理蜂）—— 向上负责：想法 → 实现方案。

职责：
1. 接收高层次的用户需求/想法
2. 转化为结构化的任务卡片（PM 任务）
3. 将任务卡片写入 task_pool/ 供 Centurion Bee 领取

第一阶段 PM Bee 是极简版：主要功能是创建任务卡片，
真正的"规划"能力未来再扩展。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.base.llm_backend import LLMProvider, MockLLMProvider
from src.base.tool_calling import ToolRegistry
from src.base.agent_loop import SimpleAgentLoop, AgentLoopConfig
from src.bus.task_card import TaskCard, TaskCardStore, new_task_id
from src.bus.artifact import ArtifactStore
from src.bus.naming import TaskStatus
from src.memory import BeeMemory


PM_SYSTEM_PROMPT = """\
You are a PM Bee in a bee swarm system.
Your job is to turn high-level ideas and goals into well-structured project plans.

Rules:
1. Understand the user's goal and intent
2. Define clear acceptance criteria for the project
3. Break the goal into major milestones (high-level tasks, not detailed steps)
4. Each milestone should be achievable and verifiable
5. Focus on WHAT needs to be done, not HOW (that's for Centurion Bee)
6. Be pragmatic — start with an MVP approach
"""


class PMBee:
    """PM Bee：规划层，将想法转化为任务。"""

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider | None = None,
        bee_name: str = "pm_01",
        max_iterations: int = 5,
    ) -> None:
        self.workspace = Path(workspace)
        self.bee_name = bee_name
        self.provider = provider or MockLLMProvider()
        self.max_iterations = max_iterations

        self.task_store = TaskCardStore(self.workspace)
        self.artifact_store = ArtifactStore(self.workspace)
        self.memory = BeeMemory(self.workspace, self.bee_name)
        self.tools = ToolRegistry()

        self.agent_loop = SimpleAgentLoop(
            provider=self.provider,
            tools=self.tools,
            config=AgentLoopConfig(
                max_iterations=max_iterations,
                system_prompt=PM_SYSTEM_PROMPT,
            ),
        )

    async def create_task(
        self,
        goal: str,
        title: str | None = None,
        acceptance_criteria: list[str] | None = None,
    ) -> TaskCard:
        """从一个目标创建 PM 任务卡片。

        Args:
            goal: 用户的目标/想法描述
            title: 可选，任务标题（不填则由 LLM 生成）
            acceptance_criteria: 可选，验收标准（不填则由 LLM 生成）

        Returns:
            创建的 TaskCard
        """
        # 如果提供了标题和验收标准，直接创建
        if title and acceptance_criteria is not None:
            task_id = new_task_id("pm", self._slugify(title))
            card = TaskCard(
                task_id=task_id,
                type="pm",
                title=title,
                description=goal,
                created_by=self.bee_name,
                acceptance_criteria=acceptance_criteria,
            )
            self.task_store.create(card)
            self.memory.record_task_start(task_id, title)
            self.memory.record_task_end(task_id, success=True, result=f"Created with {len(acceptance_criteria)} criteria")
            print(f"[{self.bee_name}] Created PM task: {task_id} - {title}")
            return card

        # 否则用 LLM 生成规划
        self.memory.record_turn("system", f"Generating plan for goal: {goal[:80]}", "pm_planning")
        plan = await self._generate_plan(goal)
        task_id = new_task_id("pm", self._slugify(plan.get("title", goal)))
        card = TaskCard(
            task_id=task_id,
            type="pm",
            title=plan.get("title", goal[:80]),
            description=goal,
            created_by=self.bee_name,
            acceptance_criteria=plan.get("acceptance_criteria", []),
            metadata={"plan_details": plan.get("details", "")},
        )
        self.task_store.create(card)
        self.memory.record_task_start(task_id, card.title)
        self.memory.record_turn("system", f"Plan generated: {plan.get('title', '')}", task_id)
        self.memory.record_task_end(task_id, success=True, result=f"Plan with {len(card.acceptance_criteria)} criteria")
        print(f"[{self.bee_name}] Created PM task: {task_id} - {card.title}")
        return card

    async def _generate_plan(self, goal: str) -> dict[str, Any]:
        """使用 LLM 生成任务规划。"""
        prompt = f"""
Analyze this goal and create a project plan:

Goal: {goal}

Return a JSON object with:
- "title": a short, descriptive title for the project
- "acceptance_criteria": array of 3-5 clear, testable acceptance criteria
- "details": brief description of the approach

Respond with ONLY the JSON object, no other text.
"""
        result = await self.agent_loop.run(prompt)
        content = result.final_content or ""

        import json
        try:
            # 找到第一个 { 和最后一个 }
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                json_str = content[start:end + 1]
                plan = json.loads(json_str)
                if isinstance(plan, dict):
                    return {
                        "title": plan.get("title", goal[:80]),
                        "acceptance_criteria": plan.get("acceptance_criteria", []),
                        "details": plan.get("details", ""),
                    }
        except (json.JSONDecodeError, ValueError):
            pass

        # 兜底
        return {
            "title": goal[:80],
            "acceptance_criteria": [f"Complete: {goal[:80]}"],
            "details": goal,
        }

    @staticmethod
    def _slugify(text: str) -> str:
        """将文本转换为安全的文件名片段。"""
        import re
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "_", text)
        return text[:40].strip("_")


def main() -> None:
    parser = argparse.ArgumentParser(description="PM Bee - create tasks from goals")
    parser.add_argument(
        "--workspace", type=str, default="./workspace",
        help="Path to the swarm workspace (default: ./workspace)",
    )
    parser.add_argument(
        "--name", type=str, default="pm_01",
        help="Bee name for identification (default: pm_01)",
    )
    parser.add_argument(
        "--goal", type=str, required=True,
        help="The goal or idea to turn into a task",
    )
    parser.add_argument(
        "--title", type=str, default=None,
        help="Optional task title",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    bee = PMBee(workspace=workspace, bee_name=args.name)
    asyncio.run(bee.create_task(goal=args.goal, title=args.title))


if __name__ == "__main__":
    main()
