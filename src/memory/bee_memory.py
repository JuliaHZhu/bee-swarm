"""BeeMemory — nanobot MemoryStore + GitStore bridge for bee-swarm.

Each bee gets its own isolated memory workspace:
    workspace/memory/{bee_name}/
        memory/MEMORY.md          # long-term facts (consolidated by Dream)
        memory/history.jsonl      # append-only execution history
        memory/.cursor            # history cursor
        memory/.dream_cursor      # dream processing cursor
        SOUL.md                   # bee personality / role definition
        USER.md                   # user preferences (if any)
        .git/                     # automatic version control

Task history is keyed by *task_id* (nanobot session_key) so every task
execution is isolated but share the same long-term memory.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.utils.gitstore import GitStore


class BeeMemory:
    """Lightweight memory for a single bee in the swarm."""

    def __init__(self, workspace: Path, bee_name: str, max_history: int = 1000) -> None:
        self.bee_name = bee_name
        # Each bee owns a sub-directory under the global workspace/memory/
        self.memory_workspace = Path(workspace) / "memory" / bee_name
        self.memory_workspace.mkdir(parents=True, exist_ok=True)

        self.store = MemoryStore(self.memory_workspace, max_history_entries=max_history)
        self.git: GitStore = self.store.git

        # Ensure git is initialised and SOUL.md exists
        self.git.init()
        self._ensure_soul()

    # ------------------------------------------------------------------
    # SOUL / identity
    # ------------------------------------------------------------------

    def _ensure_soul(self) -> None:
        soul = self.store.read_soul()
        if not soul.strip():
            self.store.write_soul(
                f"# {self.bee_name}\n\n"
                f"Role: Bee in the swarm.\n"
                f"Workspace: {self.memory_workspace}\n"
            )
            self.git.auto_commit(f"init: {self.bee_name} soul")

    def read_soul(self) -> str:
        return self.store.read_soul()

    def write_soul(self, content: str) -> None:
        self.store.write_soul(content)
        self.git.auto_commit(f"update: {self.bee_name} soul")

    # ------------------------------------------------------------------
    # Task-scoped history (nanobot session_key == task_id)
    # ------------------------------------------------------------------

    def record_task_start(self, task_id: str, title: str) -> int:
        """Record the start of a task. Returns the history cursor."""
        return self.store.append_history(
            f"📋 Task started: {title} ({task_id})",
            session_key=task_id,
        )

    def record_turn(self, role: str, content: str, task_id: str) -> int:
        """Record one turn (LLM message, tool result, etc.)."""
        # Hard cap per turn to avoid blowing up the history file
        capped = content[:2000] + ("..." if len(content) > 2000 else "")
        return self.store.append_history(
            f"[{role}] {capped}",
            session_key=task_id,
        )

    def record_tool_call(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: str,
        task_id: str,
    ) -> int:
        """Record a tool invocation and its result."""
        params_json = json.dumps(params, ensure_ascii=False, default=str)[:500]
        result_capped = result[:1000] + ("..." if len(result) > 1000 else "")
        return self.store.append_history(
            f"[🔧 {tool_name}] params={params_json} -> {result_capped}",
            session_key=task_id,
        )

    def record_task_end(
        self,
        task_id: str,
        success: bool,
        result: str | None = None,
        error: str | None = None,
    ) -> int:
        """Record task completion or failure."""
        status = "✅ COMPLETED" if success else "❌ FAILED"
        msg = f"{status}: {task_id}"
        if result:
            msg += f" | result={result[:500]}"
        if error:
            msg += f" | error={error[:500]}"
        cursor = self.store.append_history(msg, session_key=task_id)
        self.git.auto_commit(f"task {task_id}: {status}")
        return cursor

    # ------------------------------------------------------------------
    # Context retrieval
    # ------------------------------------------------------------------

    def get_task_context(self, task_id: str, max_entries: int = 50) -> str:
        """Return recent history for a specific task as a single string."""
        entries = self.store.read_recent_history_for_prompt(
            since_cursor=0,
            session_key=task_id,
        )
        recent = entries[-max_entries:] if len(entries) > max_entries else entries
        lines = []
        for e in recent:
            ts = e.get("timestamp", "")
            content = e.get("content", "")
            lines.append(f"[{ts}] {content}")
        return "\n".join(lines)

    def get_long_term_memory(self) -> str:
        """Return the consolidated MEMORY.md content."""
        return self.store.read_memory()

    # ------------------------------------------------------------------
    # Dream (periodic consolidation)
    # ------------------------------------------------------------------

    def dream(self) -> bool:
        """Trigger nanobot Dream consolidation if there is unprocessed history.

        Returns True if consolidation was performed, False if nothing to do.
        """
        dream_prompt = self.store.build_dream_prompt(max_entries=50)
        if dream_prompt is None:
            return False

        prompt, last_cursor = dream_prompt
        # For now we only *prepare* the prompt; actual LLM-driven consolidation
        # can be plugged in later.  We still advance the cursor so the same
        # batch is not re-processed.
        self.store.set_last_dream_cursor(last_cursor)
        self.git.auto_commit(f"dream: consolidate up to cursor {last_cursor}")
        return True

    def dream_prompt(self) -> tuple[str, int] | None:
        """Return the Dream prompt and cursor *without* advancing state.

        Useful when an external LLM provider will perform the consolidation.
        """
        return self.store.build_dream_prompt(max_entries=50)

    # ------------------------------------------------------------------
    # Git utilities
    # ------------------------------------------------------------------

    def log(self, max_entries: int = 20) -> list[Any]:
        """Return recent git commits."""
        return self.git.log(max_entries=max_entries)

    def line_ages(self, file_path: str) -> list[Any]:
        """Return per-line ages for a tracked file."""
        return self.git.line_ages(file_path)
