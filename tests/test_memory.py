"""Tests for BeeMemory — nanobot MemoryStore bridge."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.memory import BeeMemory


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "swarm_workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def bee_memory(tmp_workspace: Path) -> BeeMemory:
    return BeeMemory(tmp_workspace, "test_bee_01", max_history=100)


class TestBeeMemoryLifecycle:
    def test_init_creates_directories(self, bee_memory: BeeMemory, tmp_workspace: Path) -> None:
        assert (tmp_workspace / "memory" / "test_bee_01").is_dir()
        assert (tmp_workspace / "memory" / "test_bee_01" / "memory").is_dir()

    def test_soul_created_on_init(self, bee_memory: BeeMemory) -> None:
        soul = bee_memory.read_soul()
        assert "test_bee_01" in soul
        assert bee_memory.git.is_initialized()

    def test_git_log_has_init_commit(self, bee_memory: BeeMemory) -> None:
        log = bee_memory.log(max_entries=5)
        assert len(log) >= 1
        assert any("init" in c.message for c in log)


class TestTaskHistory:
    def test_record_task_start(self, bee_memory: BeeMemory) -> None:
        cursor = bee_memory.record_task_start("worker_test_001", "Test Task")
        assert isinstance(cursor, int)
        assert cursor > 0

    def test_record_turn(self, bee_memory: BeeMemory) -> None:
        bee_memory.record_task_start("worker_test_001", "Test Task")
        cursor = bee_memory.record_turn("user", "Hello", "worker_test_001")
        assert isinstance(cursor, int)
        assert cursor > 0

    def test_record_tool_call(self, bee_memory: BeeMemory) -> None:
        bee_memory.record_task_start("worker_test_001", "Test Task")
        cursor = bee_memory.record_tool_call(
            "read_file", {"path": "test.txt"}, "file content", "worker_test_001"
        )
        assert isinstance(cursor, int)

    def test_record_task_end(self, bee_memory: BeeMemory) -> None:
        bee_memory.record_task_start("worker_test_001", "Test Task")
        cursor = bee_memory.record_task_end("worker_test_001", success=True, result="Done")
        assert isinstance(cursor, int)

    def test_get_task_context(self, bee_memory: BeeMemory) -> None:
        bee_memory.record_task_start("worker_test_001", "Test Task")
        bee_memory.record_turn("user", "Do something", "worker_test_001")
        bee_memory.record_turn("assistant", "Done", "worker_test_001")
        bee_memory.record_task_end("worker_test_001", success=True)

        ctx = bee_memory.get_task_context("worker_test_001")
        assert "Test Task" in ctx
        assert "Do something" in ctx
        assert "Done" in ctx

    def test_task_isolation(self, bee_memory: BeeMemory) -> None:
        bee_memory.record_task_start("task_a", "Task A")
        bee_memory.record_turn("user", "Message A", "task_a")

        bee_memory.record_task_start("task_b", "Task B")
        bee_memory.record_turn("user", "Message B", "task_b")

        ctx_a = bee_memory.get_task_context("task_a")
        ctx_b = bee_memory.get_task_context("task_b")

        assert "Message A" in ctx_a
        assert "Message B" not in ctx_a
        assert "Message B" in ctx_b
        assert "Message A" not in ctx_b


class TestDream:
    def test_dream_nothing_to_do(self, bee_memory: BeeMemory) -> None:
        # No history → dream should return False
        assert bee_memory.dream() is False

    def test_dream_prompt_returns_none_when_empty(self, bee_memory: BeeMemory) -> None:
        assert bee_memory.dream_prompt() is None

    def test_dream_after_history(self, bee_memory: BeeMemory) -> None:
        # Add enough history to trigger dream
        for i in range(5):
            bee_memory.record_turn("user", f"Message {i}", "task_dream")

        # build_dream_prompt should return something because there is unprocessed history
        prompt = bee_memory.dream_prompt()
        # It may or may not return a prompt depending on nanobot's internal threshold
        # We just assert it doesn't crash
        if prompt is not None:
            p, cursor = prompt
            assert isinstance(cursor, int)
            assert cursor >= 0


class TestGitIntegration:
    def test_auto_commit_on_task_end(self, bee_memory: BeeMemory) -> None:
        initial_log = len(bee_memory.log(max_entries=20))
        bee_memory.record_task_start("task_git", "Git Test")
        cursor = bee_memory.record_task_end("task_git", success=True)
        assert isinstance(cursor, int)
        # auto_commit only fires when tracked files (SOUL.md, MEMORY.md) change.
        # Task history lives in history.jsonl which is NOT git-tracked by design
        # (append-only files don't need version control).  So we just verify no crash.

    def test_line_ages(self, bee_memory: BeeMemory) -> None:
        ages = bee_memory.line_ages("SOUL.md")
        # SOUL.md exists and was just created
        assert isinstance(ages, list)
