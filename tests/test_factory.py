"""Factory Phase1 tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.factory import AgentDefinition, AgentRegistry


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

    def test_construct_empty_name_raises(self) -> None:
        with pytest.raises(ValidationError, match="name"):
            AgentDefinition(
                name="",
                role="worker",
                system_prompt="OK",
                tools=["read_file"],
                version="1.0.0",
            )

    def test_check_ok(self) -> None:
        agent = AgentDefinition(
            name="ok",
            role="worker",
            system_prompt="OK",
            tools=["read_file"],
            version="1.0.0",
        )
        assert agent.check() is True

    def test_check_bad_role(self) -> None:
        agent = AgentDefinition(
            name="bad",
            role="wizard",
            system_prompt="OK",
            tools=["read_file"],
            version="1.0.0",
        )
        with pytest.raises(ValueError, match="role"):
            agent.check()

    def test_check_bad_tool(self) -> None:
        agent = AgentDefinition(
            name="bad",
            role="worker",
            system_prompt="OK",
            tools=["read_file", "magic_spell"],
            version="1.0.0",
        )
        with pytest.raises(ValueError, match="magic_spell"):
            agent.check()


class TestAgentRegistry:
    def test_scan_builtin(self) -> None:
        reg = AgentRegistry()
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
