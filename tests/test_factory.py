"""Factory Phase1 tests."""
from __future__ import annotations

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.factory import AgentDefinition, AgentRegistry, AgentSpawner
from src.bus.task_card import TaskCardStore


class TestAgentDefinition:
    def test_from_yaml_valid(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "test-agent.yaml"
        yaml_path.write_text("""
name: test-agent
role: worker
system_prompt: |
  You are a test agent.
tools:
  - read_file
  - write_file
version: "1.0.0"
""")
        agent = AgentDefinition.from_yaml(yaml_path)
        assert agent.name == "test-agent"
        assert agent.role == "worker"
        assert "test agent" in agent.system_prompt
        assert agent.tools == ["read_file", "write_file"]
        assert agent.version == "1.0.0"

    def test_validate_ok(self) -> None:
        agent = AgentDefinition(
            name="ok",
            role="worker",
            system_prompt="OK",
            tools=["read_file"],
            version="1.0.0",
        )
        assert agent.validate() is True

    def test_validate_missing_field(self) -> None:
        agent = AgentDefinition(
            name="",
            role="worker",
            system_prompt="OK",
            tools=[],
            version="1.0.0",
        )
        with pytest.raises(ValueError, match="name"):
            agent.validate()

    def test_validate_bad_tool(self) -> None:
        agent = AgentDefinition(
            name="bad",
            role="worker",
            system_prompt="OK",
            tools=["read_file", "magic_spell"],
            version="1.0.0",
        )
        with pytest.raises(ValueError, match="magic_spell"):
            agent.validate()


class TestAgentRegistry:
    def test_scan_builtin(self) -> None:
        # 使用默认 builtin_dir（repo root / agents/）
        reg = AgentRegistry()
        # 实际 agents/ 目录应该有 default-worker
        names = {a.name for a in reg.list_all()}
        assert "default-worker" in names

    def test_get_builtin(self) -> None:
        reg = AgentRegistry()
        agent = reg.get("default-worker")
        assert agent is not None
        assert agent.name == "default-worker"
        assert "read_file" in agent.tools

    def test_get_missing(self) -> None:
        reg = AgentRegistry()
        assert reg.get("nonexistent") is None

    def test_workspace_override(self, tmp_path: Path) -> None:
        workspace_agents = tmp_path / "agents"
        workspace_agents.mkdir()
        (workspace_agents / "custom.yaml").write_text("""
name: custom
role: worker
system_prompt: Custom
tools:
  - list_dir
version: "0.1.0"
""")
        reg = AgentRegistry(workspace_dir=workspace_agents)
        custom = reg.get("custom")
        assert custom is not None
        assert custom.name == "custom"


class TestAgentSpawner:
    def test_spawn_writes_task_card(self, tmp_path: Path) -> None:
        store = TaskCardStore(tmp_path)
        spawner = AgentSpawner(tmp_path, python_executable="/usr/bin/false")
        # spawn 返回创建的 card，内部生成 task_id
        card = spawner.spawn("default-worker", "Test task")
        # 验证 task_card 写入
        fetched = store.get(card.task_id)
        assert fetched is not None
        assert fetched.metadata.get("agent") == "default-worker"
        assert fetched.status.value == "pending"

    def test_spawn_unknown_agent(self, tmp_path: Path) -> None:
        # 未知 agent 会回落到 default-worker，不抛异常
        spawner = AgentSpawner(tmp_path, python_executable="/usr/bin/false")
        card = spawner.spawn("ghost-agent", "Fallback task")
        assert card.metadata.get("agent") == "default-worker"
