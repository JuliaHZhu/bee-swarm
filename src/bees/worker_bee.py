"""
Worker Bee（工蜂）—— 执行具体的工具任务。

职责：
1. 轮询 task_pool/ 中 worker_ 前缀的 pending 任务
2. 领取任务（原子操作）
3. 执行任务（调用指定工具）
4. 将结果写入产出物，标记任务完成

每个 Worker Bee 是独立进程，可启动多个实例实现并发。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

# 确保父目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.base.llm_backend import LLMProvider, MockLLMProvider
from src.base.tool_calling import ToolRegistry
from src.base.agent_loop import SimpleAgentLoop, AgentLoopConfig
from src.bus.task_card import TaskCard, TaskCardStore
from src.bus.artifact import ArtifactStore
from src.bus.naming import TaskStatus
from src.memory import BeeMemory
from .built_in_tools import register_worker_tools


WORKER_SYSTEM_PROMPT = """\
You are a Worker Bee in a bee swarm system.
Your job is to execute specific tool-based tasks assigned to you.

Rules:
1. Use the provided tools to complete the task
2. Read the task description carefully and follow instructions precisely
3. After completing the task, report what you did and the result
4. If you encounter an error, report it clearly
5. Be concise and direct in your final response
"""


class WorkerBee:
    """Worker Bee：执行具体任务。"""

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider | None = None,
        bee_name: str = "worker_01",
        max_iterations: int = 5,
    ) -> None:
        self.workspace = Path(workspace)
        self.bee_name = bee_name
        self.provider = provider or MockLLMProvider()
        self.max_iterations = max_iterations

        # 存储层
        self.task_store = TaskCardStore(self.workspace)
        self.artifact_store = ArtifactStore(self.workspace)
        self.memory = BeeMemory(self.workspace, self.bee_name)

        # 工具注册（工作区为整个 workspace，产出物路径通过 prompt 约束）
        self.tools = ToolRegistry()
        register_worker_tools(self.tools, self.workspace)

        # Agent loop
        self.agent_loop = SimpleAgentLoop(
            provider=self.provider,
            tools=self.tools,
            config=AgentLoopConfig(
                max_iterations=max_iterations,
                system_prompt=WORKER_SYSTEM_PROMPT,
            ),
        )

    async def run_once(self) -> bool:
        """执行一次任务循环：领取一个任务并执行。

        Returns:
            True 如果执行了任务，False 如果没有可领取的任务。
        """
        # 1. 领取一个 pending 的 worker 任务
        pending = self.task_store.list_pending(prefix="worker")
        if not pending:
            return False

        # 尝试领取第一个任务
        card = None
        for task in pending:
            claimed = self.task_store.claim(task.task_id, self.bee_name)
            if claimed is not None:
                card = claimed
                break

        if card is None:
            return False

        print(f"[{self.bee_name}] Claimed task: {card.task_id} - {card.title}")

        # 2. 执行任务
        try:
            result_summary, artifact_paths = await self._execute_task(card)
            # 3. 标记完成
            card.artifact_paths = artifact_paths
            self.task_store.complete(card, result=result_summary)
            print(f"[{self.bee_name}] Completed task: {card.task_id}")
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            self.task_store.complete(card, failed=True, error=error_msg)
            print(f"[{self.bee_name}] Failed task: {card.task_id} - {error_msg}")

        return True

    async def _execute_task(self, card: TaskCard) -> tuple[str, list[str]]:
        """执行一个任务，返回 (结果摘要, 产出物路径列表)。"""
        artifact_paths: list[str] = []
        self.memory.record_task_start(card.task_id, card.title)

        # 如果任务指定了具体工具和参数，直接执行（简单模式）
        if card.tool and card.tool_params:
            self.memory.record_turn("system", f"Direct tool call: {card.tool}", card.task_id)
            result = await self.tools.execute(card.tool, card.tool_params)
            result_str = str(result)
            is_error = hasattr(result, "is_error") and result.is_error
            self.memory.record_tool_call(card.tool, card.tool_params, result_str, card.task_id)

            # 记录产出物
            artifact_dir = self.artifact_store.task_dir(card.task_id)
            result_file = artifact_dir / "result.txt"
            with open(result_file, "w", encoding="utf-8") as f:
                f.write(result_str)
            artifact_paths.append(self.artifact_store.relative_path(result_file))

            if is_error:
                self.memory.record_task_end(card.task_id, success=False, error=result_str)
                raise RuntimeError(result_str)

            self.memory.record_task_end(card.task_id, success=True, result=result_str)
            return result_str, artifact_paths

        # 否则用 agent loop 让 LLM 决定怎么执行
        self.memory.record_turn("system", "Using agent loop for task execution", card.task_id)
        task_description = f"""
Task ID: {card.task_id}
Title: {card.title}
Description: {card.description}
Acceptance Criteria: {chr(10).join('- ' + c for c in card.acceptance_criteria) if card.acceptance_criteria else 'None'}

Write all output files to the artifacts directory using the write_file tool.
Use the task ID '{card.task_id}' as a subdirectory when writing files.
"""
        # 注入 memory 上下文到 system prompt
        system_prompt = WORKER_SYSTEM_PROMPT + "\n\n" + self.memory.build_system_prompt(card.task_id)
        result = await self.agent_loop.run(task_description, system_prompt=system_prompt)

        # 记录 LLM 交互
        if result.messages:
            for msg in result.messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if content:
                    self.memory.record_turn(role, str(content), card.task_id)
        if result.error:
            self.memory.record_turn("system", f"Agent loop error: {result.error}", card.task_id)

        # 收集产出物
        artifact_files = self.artifact_store.list_artifacts(card.task_id)
        artifact_paths = [self.artifact_store.relative_path(f) for f in artifact_files]

        if result.error:
            self.memory.record_task_end(card.task_id, success=False, error=result.error)
            raise RuntimeError(result.error)

        self.memory.record_task_end(card.task_id, success=True, result=result.final_content)
        return result.final_content or "Task completed.", artifact_paths

    async def run_loop(self, poll_interval: float = 2.0, max_tasks: int = 0,
                       reclaim_interval: float = 60.0) -> None:
        """持续运行，轮询任务池。

        Args:
            poll_interval: 轮询间隔（秒）
            max_tasks: 最多执行多少个任务，0 表示无限
            reclaim_interval: stale claim 回收间隔（秒）
        """
        executed = 0
        last_reclaim = 0.0
        print(f"[{self.bee_name}] Starting worker loop (poll_interval={poll_interval}s)")

        while True:
            if max_tasks > 0 and executed >= max_tasks:
                break

            # 定期回收超时任务
            now = asyncio.get_event_loop().time()
            if now - last_reclaim >= reclaim_interval:
                reclaimed = self.task_store.reclaim_stale(timeout_seconds=300.0)
                if reclaimed:
                    print(f"[{self.bee_name}] Reclaimed stale tasks: {reclaimed}")
                last_reclaim = now

            did_work = await self.run_once()
            if did_work:
                executed += 1
            else:
                await asyncio.sleep(poll_interval)

        print(f"[{self.bee_name}] Worker loop ended after {executed} tasks")


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker Bee - execute tasks from the task pool")
    parser.add_argument(
        "--workspace",
        type=str,
        default="./workspace",
        help="Path to the swarm workspace (default: ./workspace)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="worker_01",
        help="Bee name for identification (default: worker_01)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=0,
        help="Maximum number of tasks to execute (0=infinite, default: 0)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (process one task or exit if none)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="LLM model name (default: gpt-4o-mini, or env OPENAI_MODEL)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="",
        help="LLM API base URL (default: env OPENAI_BASE_URL)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default="",
        help="LLM API key (default: env OPENAI_API_KEY)",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()

    # 构造 provider：有 key/model 则用真模型，否则 Mock（并警告）
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
        print(f"[{args.name}] WARNING: No API key provided. Running with MOCK LLM. "
              f"Set --api-key or OPENAI_API_KEY for real model.")

    bee = WorkerBee(workspace=workspace, bee_name=args.name, provider=provider)

    if args.once:
        asyncio.run(bee.run_once())
    else:
        asyncio.run(bee.run_loop(
            poll_interval=args.poll_interval,
            max_tasks=args.max_tasks,
        ))


if __name__ == "__main__":
    main()
