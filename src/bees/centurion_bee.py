"""
Centurion Bee（百夫长蜂）—— 分活 + 调度容量。

职责：
1. 轮询 task_pool/ 中 pm_ 或 centurion_ 前缀的 pending 任务
2. 领取任务（原子操作）
3. 将任务拆分为若干 worker_ 子任务
4. 监控子任务完成状态
5. 所有子任务完成后，汇总结果并标记父任务完成

Centurion Bee 是"向下负责"的：它的价值在于把大任务拆成可执行的小任务。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.base.llm_backend import LLMProvider, MockLLMProvider, LLMResponse, ToolCallRequest
from src.base.tool_calling import ToolRegistry
from src.base.agent_loop import SimpleAgentLoop, AgentLoopConfig
from src.bus.task_card import TaskCard, TaskCardStore, new_task_id
from src.bus.artifact import ArtifactStore
from src.bus.naming import TaskStatus
from src.memory import BeeMemory


CENTURION_SYSTEM_PROMPT = """\
You are a Centurion Bee in a bee swarm system.
Your job is to break down high-level tasks into concrete, executable subtasks for Worker Bees.

Rules:
1. Analyze the task description and acceptance criteria carefully
2. Break the task into 2-5 clear, independent subtasks
3. Each subtask should be a simple file operation (read, write, list, search)
4. Subtasks should be ordered logically
5. Be specific about what each subtask should produce
6. Keep subtasks small and focused — one clear action per subtask
"""


class CenturionBee:
    """Centurion Bee：分活 + 调度。"""

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider | None = None,
        bee_name: str = "centurion_01",
        max_iterations: int = 8,
    ) -> None:
        self.workspace = Path(workspace)
        self.bee_name = bee_name
        self.provider = provider or MockLLMProvider()
        self.max_iterations = max_iterations
        # 存储层
        self.task_store = TaskCardStore(self.workspace)
        self.artifact_store = ArtifactStore(self.workspace)
        self.memory = BeeMemory(self.workspace, self.bee_name)

        # Centurion 不需要太多工具，主要靠 LLM 做拆分决策
        self.tools = ToolRegistry()

        self.agent_loop = SimpleAgentLoop(
            provider=self.provider,
            tools=self.tools,
            config=AgentLoopConfig(
                max_iterations=max_iterations,
                system_prompt=CENTURION_SYSTEM_PROMPT,
            ),
        )

    async def run_once(self) -> bool:
        """执行一次循环：领取一个任务并拆分。

        Returns:
            True 如果处理了任务，False 如果没有可领取的任务。
        """
        # 1. 先尝试处理有已完成子任务的父任务（汇总）
        did_summary = await self._try_summarize_completed()
        if did_summary:
            return True

        # 2. 再尝试领取新的 pm/centurion 任务进行拆分
        pending = self.task_store.list_pending(prefix="pm")
        pending += self.task_store.list_pending(prefix="centurion")
        pending = [t for t in pending if not t.subtasks]  # 还没拆分过的

        if not pending:
            return False

        card = None
        for task in pending:
            claimed = self.task_store.claim(task.task_id, self.bee_name)
            if claimed is not None:
                card = claimed
                break

        if card is None:
            return False

        print(f"[{self.bee_name}] Claimed task for decomposition: {card.task_id} - {card.title}")
        self.memory.record_task_start(card.task_id, card.title)

        try:
            # 3. 拆分子任务
            self.memory.record_turn("system", f"Starting decomposition of {card.task_id}", card.task_id)
            subtasks = await self._decompose_task(card)
            self.memory.record_turn("system", f"Decomposed into {len(subtasks)} subtasks", card.task_id)
            print(f"[{self.bee_name}] Decomposed into {len(subtasks)} subtasks")

            # 4. 创建子任务卡片
            for i, subtask_info in enumerate(subtasks):
                sub_id = new_task_id("worker", card.task_id, f"{i+1:02d}")
                sub_card = TaskCard(
                    task_id=sub_id,
                    type="worker",
                    title=subtask_info["title"],
                    description=subtask_info["description"],
                    parent_id=card.task_id,
                    created_by=self.bee_name,
                    tool=subtask_info.get("tool"),
                    tool_params=subtask_info.get("tool_params", {}),
                    acceptance_criteria=subtask_info.get("acceptance_criteria", []),
                    priority=card.priority,
                )
                self.task_store.create(sub_card)
                card.subtasks.append(sub_id)

            # 5. 更新父任务（保持 in_progress，等待子任务完成）
            self.task_store.update(card)
            self.memory.record_task_end(card.task_id, success=True,
                result=f"Created {len(subtasks)} subtasks: {', '.join(card.subtasks)}")

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            self.memory.record_task_end(card.task_id, success=False, error=error_msg)
            self.task_store.complete(card, failed=True, error=error_msg)
            print(f"[{self.bee_name}] Failed to decompose: {card.task_id} - {error_msg}")

        return True

    async def _decompose_task(self, card: TaskCard) -> list[dict[str, Any]]:
        """将任务拆分为子任务列表。

        每个子任务是 dict: {"title", "description", "tool", "tool_params", "acceptance_criteria"}
        """
        # ponytail: 第一阶段用规则 + LLM 混合的方式
        # 如果是简单的文件任务，直接用规则拆分；复杂任务走 LLM

        # 启发式：根据任务描述识别简单模式
        desc_lower = card.description.lower()
        title_lower = card.title.lower()

        # 模式1：写文档类任务 → 拆成写多个文件
        if any(kw in desc_lower or kw in title_lower for kw in ["文档", "document", "readme", "架构", "architecture"]):
            return self._heuristic_doc_task(card)

        # 模式2：研究/搜索类任务 → 先搜索再汇总
        if any(kw in desc_lower or kw in title_lower for kw in ["搜索", "研究", "search", "research", "调研"]):
            return self._heuristic_research_task(card)

        # 默认：走 LLM 拆分
        return await self._llm_decompose(card)

    def _heuristic_doc_task(self, card: TaskCard) -> list[dict[str, Any]]:
        """启发式：文档类任务拆分为写 README + 写架构文档。"""
        subtasks = []

        # 子任务1：写 README
        subtasks.append({
            "title": f"Write README for {card.title}",
            "description": f"Create a README.md file for the project: {card.description}\n\n"
                           f"Include: project name, brief description, quick start.",
            "tool": "write_file",
            "tool_params": {
                "path": f"{card.task_id}/README.md",
                "content": f"# {card.title}\n\n{card.description}\n\n## Quick Start\n\nTBD\n",
            },
            "acceptance_criteria": ["README.md created with project name and description"],
        })

        # 子任务2：写架构文档（如果提到了架构）
        if any(kw in card.description.lower() or kw in card.title.lower()
               for kw in ["架构", "architecture", "设计", "design"]):
            subtasks.append({
                "title": f"Write architecture doc for {card.title}",
                "description": f"Create architecture documentation: {card.description}",
                "tool": "write_file",
                "tool_params": {
                    "path": f"{card.task_id}/docs/architecture.md",
                    "content": f"# Architecture: {card.title}\n\n## Overview\n\n{card.description}\n\n"
                               f"## Components\n\nTBD\n",
                },
                "acceptance_criteria": ["architecture.md created"],
            })

        return subtasks

    def _heuristic_research_task(self, card: TaskCard) -> list[dict[str, Any]]:
        """启发式：研究类任务拆分为搜索 + 汇总。"""
        # 提取关键词（简单提取前几个词）
        keywords = card.title[:50]
        return [
            {
                "title": f"Search for: {keywords}",
                "description": f"Search for information about: {card.description}",
                "tool": "search_text",
                "tool_params": {
                    "pattern": keywords,
                    "path": ".",
                    "max_results": 20,
                },
                "acceptance_criteria": ["Search results obtained"],
            },
            {
                "title": f"Summarize findings for {card.title}",
                "description": f"Write a summary of findings for: {card.description}",
                "tool": "write_file",
                "tool_params": {
                    "path": f"{card.task_id}/summary.md",
                    "content": f"# Research Summary: {card.title}\n\nBased on search results.\n\nTBD\n",
                },
                "acceptance_criteria": ["Summary document created"],
            },
        ]

    async def _llm_decompose(self, card: TaskCard) -> list[dict[str, Any]]:
        """使用 LLM 拆分任务。"""
        prompt = f"""
Break down this task into subtasks for Worker Bees.

Task: {card.title}
Description: {card.description}
Acceptance Criteria:
{chr(10).join('- ' + c for c in card.acceptance_criteria) if card.acceptance_criteria else '- None'}

Available tools for workers:
- read_file(path, max_lines): Read a file
- write_file(path, content, append): Write content to a file
- list_dir(path, recursive): List directory contents
- search_text(pattern, path, max_results): Search for text in files

Return a JSON array of subtasks. Each subtask must have:
- "title": short title
- "description": detailed description
- "tool": tool name (read_file/write_file/list_dir/search_text) or null if multi-step
- "tool_params": object with tool parameters
- "acceptance_criteria": array of strings

Example:
[
  {{"title": "Read config", "description": "Read the config file", "tool": "read_file", "tool_params": {{"path": "config.json"}}, "acceptance_criteria": ["Config file read"]}}
]

Respond with ONLY the JSON array, no other text.
"""
        system_prompt = CENTURION_SYSTEM_PROMPT + "\n\n" + self.memory.build_system_prompt(card.task_id)
        result = await self.agent_loop.run(prompt, system_prompt=system_prompt)

        # 尝试从 LLM 回复中解析 JSON
        content = result.final_content or ""
        import json
        try:
            # 找到第一个 [ 和最后一个 ]
            start = content.find("[")
            end = content.rfind("]")
            if start >= 0 and end > start:
                json_str = content[start:end + 1]
                subtasks = json.loads(json_str)
                if isinstance(subtasks, list):
                    # 规范化每个 subtask
                    normalized = []
                    for st in subtasks:
                        if isinstance(st, dict):
                            normalized.append({
                                "title": st.get("title", "Untitled"),
                                "description": st.get("description", ""),
                                "tool": st.get("tool"),
                                "tool_params": st.get("tool_params", {}),
                                "acceptance_criteria": st.get("acceptance_criteria", []),
                            })
                    if normalized:
                        return normalized
        except (json.JSONDecodeError, ValueError):
            pass

        # 兜底：生成一个默认子任务
        return [{
            "title": f"Execute: {card.title}",
            "description": card.description,
            "tool": None,
            "tool_params": {},
            "acceptance_criteria": card.acceptance_criteria,
        }]

    async def _try_summarize_completed(self) -> bool:
        """尝试汇总已完成子任务的父任务。

        Returns:
            True 如果完成了一个汇总
        """
        # 找出所有 in_progress 且有子任务的 centurion/pm 任务
        in_progress = self.task_store.list_in_progress(prefix="pm")
        in_progress += self.task_store.list_in_progress(prefix="centurion")

        for card in in_progress:
            if not card.subtasks:
                continue

            # 检查所有子任务是否都完成
            all_done = True
            all_results: list[str] = []
            for sub_id in card.subtasks:
                sub_card = self.task_store.get(sub_id)
                if sub_card is None:
                    all_done = False
                    break
                if sub_card.status == TaskStatus.FAILED:
                    # 有子任务失败，父任务也失败
                    error_msg = f"Subtask failed: {sub_id} - {sub_card.error}"
                    self.memory.record_task_end(card.task_id, success=False, error=error_msg)
                    self.task_store.complete(card, failed=True, error=error_msg)
                    print(f"[{self.bee_name}] Parent failed due to subtask: {card.task_id}")
                    return True
                if sub_card.status != TaskStatus.DONE:
                    all_done = False
                    break
                if sub_card.result:
                    all_results.append(f"## {sub_card.title}\n{sub_card.result}")

            if all_done:
                # 所有子任务完成，汇总结果
                summary = "\n\n".join(all_results) if all_results else "All subtasks completed."
                self.memory.record_task_end(card.task_id, success=True, result=summary)
                self.task_store.complete(card, result=summary)
                print(f"[{self.bee_name}] Summarized and completed: {card.task_id}")
                return True

        return False

    async def run_loop(self, poll_interval: float = 2.0, max_tasks: int = 0) -> None:
        """持续运行，轮询任务池。"""
        processed = 0
        print(f"[{self.bee_name}] Starting centurion loop (poll_interval={poll_interval}s)")

        while True:
            if max_tasks > 0 and processed >= max_tasks:
                break

            did_work = await self.run_once()
            if did_work:
                processed += 1
            else:
                await asyncio.sleep(poll_interval)

        print(f"[{self.bee_name}] Centurion loop ended after processing {processed} tasks")


def main() -> None:
    parser = argparse.ArgumentParser(description="Centurion Bee - decompose and monitor tasks")
    parser.add_argument(
        "--workspace", type=str, default="./workspace",
        help="Path to the swarm workspace (default: ./workspace)",
    )
    parser.add_argument(
        "--name", type=str, default="centurion_01",
        help="Bee name for identification (default: centurion_01)",
    )
    parser.add_argument(
        "--max-tasks", type=int, default=0,
        help="Maximum tasks to process (0=infinite, default: 0)",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=2.0,
        help="Polling interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run once and exit",
    )
    parser.add_argument(
        "--model", type=str, default="",
        help="LLM model name (default: gpt-4o-mini, or env OPENAI_MODEL)",
    )
    parser.add_argument(
        "--base-url", type=str, default="",
        help="LLM API base URL (default: env OPENAI_BASE_URL)",
    )
    parser.add_argument(
        "--api-key", type=str, default="",
        help="LLM API key (default: env OPENAI_API_KEY)",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "")
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL", "")
    model = args.model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if api_key:
        from src.base.llm_backend import OpenAICompatProvider
        provider = OpenAICompatProvider(api_key=api_key, base_url=base_url or None, model=model)
        print(f"[{args.name}] Using LLM: {model} @ {base_url or 'https://api.openai.com/v1'}")
    else:
        from src.base.llm_backend import MockLLMProvider
        provider = MockLLMProvider(model=model)
        print(f"[{args.name}] WARNING: No API key. Running with MOCK LLM.")

    bee = CenturionBee(workspace=workspace, bee_name=args.name, provider=provider)

    if args.once:
        asyncio.run(bee.run_once())
    else:
        asyncio.run(bee.run_loop(
            poll_interval=args.poll_interval,
            max_tasks=args.max_tasks,
        ))


if __name__ == "__main__":
    main()
