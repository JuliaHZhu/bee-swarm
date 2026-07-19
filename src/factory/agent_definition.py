"""AgentDefinition — minimal 5-field YAML-based agent config.

Phase1 fields (required):
  name, role, system_prompt, tools, version

No pydantic — dataclass + handwritten validate() per YAGNI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AgentDefinition:
    """A single agent definition loaded from YAML."""

    REQUIRED_FIELDS = ("name", "role", "system_prompt", "tools", "version")

    name: str
    role: str
    system_prompt: str
    tools: list[str]
    version: str = "1.0.0"

    # Phase2+ fields (not validated in Phase1, kept for forward compat)
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path) -> "AgentDefinition":
        """Load from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"YAML root must be a dict, got {type(data).__name__}")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentDefinition":
        """Load from a plain dict (e.g. parsed YAML)."""
        name = data.get("name", "")
        role = data.get("role", "")
        system_prompt = data.get("system_prompt", "")
        tools = data.get("tools", [])
        version = data.get("version", "1.0.0")

        # Validate required fields
        if not name:
            raise ValueError("AgentDefinition missing required field: 'name'")
        if not role:
            raise ValueError(f"AgentDefinition '{name}' missing required field: 'role'")
        if not system_prompt:
            raise ValueError(f"AgentDefinition '{name}' missing required field: 'system_prompt'")
        if not isinstance(tools, list):
            raise ValueError(f"AgentDefinition '{name}' field 'tools' must be a list")

        # Strip unknown fields into metadata for forward compat
        known = {"name", "role", "system_prompt", "tools", "version"}
        metadata = {k: v for k, v in data.items() if k not in known}

        return cls(
            name=name,
            role=role,
            system_prompt=system_prompt,
            tools=list(tools),
            version=version,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (round-trippable)."""
        return {
            "name": self.name,
            "role": self.role,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "version": self.version,
            **self.metadata,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def validate(self) -> bool:
        """Phase1 lightweight validation.

        Raises ValueError on first problem found.
        Returns True when valid.
        """
        missing = [f for f in self.REQUIRED_FIELDS if not getattr(self, f, None)]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        # tool whitelist check
        _ALLOWED = {"read_file", "write_file", "list_dir", "search_text", "run_command", "complete_task"}
        unknown = [t for t in self.tools if t not in _ALLOWED]
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")

        return True
