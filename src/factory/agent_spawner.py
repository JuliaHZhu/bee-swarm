"""AgentSpawner — spawn a worker process backed by an agent YAML definition.

Spawn model: subprocess + File-as-Bus (async dispatch).
  1. Write a task_card to task_pool/ with metadata.agent = agent_name
  2. subprocess.Popen worker-bee --agent <name> --workspace <ws> --once

The worker process loads the YAML, claims the card, executes, and exits.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.bus.task_card import TaskCard, TaskCardStore, new_task_id
from src.bus.naming import TaskStatus

from .agent_registry import AgentRegistry


class AgentSpawner:
    """Spawns workers based on agent definitions."""

    def __init__(
        self,
        workspace: Path,
        registry: AgentRegistry | None = None,
        python_executable: str | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.task_store = TaskCardStore(self.workspace)
        self.registry = registry or AgentRegistry()
        self.python_executable = python_executable or sys.executable

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def spawn(
        self,
        agent_name: str,
        title: str,
        description: str = "",
        tool: str | None = None,
        tool_params: dict | None = None,
        parent_id: str | None = None,
    ) -> TaskCard:
        """Create a task card for the agent and launch a worker process.

        Returns the created TaskCard.
        """
        agent = self.registry.get(agent_name)
        if agent is None:
            # Fallback to default-worker if unknown agent
            agent_name = "default-worker"

        task_id = new_task_id("worker", agent_name)
        card = TaskCard(
            task_id=task_id,
            type="worker",
            title=title,
            description=description,
            parent_id=parent_id,
            created_by="factory",
            tool=tool,
            tool_params=tool_params or {},
            metadata={"agent": agent_name},
        )
        self.task_store.create(card)

        # Launch worker subprocess
        self._launch_worker(agent_name, task_id)
        return card

    def spawn_batch(
        self,
        agent_name: str,
        subtasks: list[dict],
        parent_id: str | None = None,
    ) -> list[TaskCard]:
        """Spawn multiple subtasks for the same agent.

        Each dict in ``subtasks`` must have at least "title" and optionally
        "description", "tool", "tool_params".
        """
        cards: list[TaskCard] = []
        for info in subtasks:
            card = self.spawn(
                agent_name=agent_name,
                title=info["title"],
                description=info.get("description", ""),
                tool=info.get("tool"),
                tool_params=info.get("tool_params"),
                parent_id=parent_id,
            )
            cards.append(card)
        return cards

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _launch_worker(self, agent_name: str, task_id: str) -> subprocess.Popen:
        """Launch ``worker-bee --agent <name> --workspace <ws> --once``."""
        cmd = [
            self.python_executable, "-m", "src.bees.worker_bee",
            "--agent", agent_name,
            "--workspace", str(self.workspace),
            "--once",
        ]
        # Detach from parent stdout so Centurion isn't blocked
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(self.workspace.parent) if self.workspace.name == "workspace" else str(self.workspace),
        )
