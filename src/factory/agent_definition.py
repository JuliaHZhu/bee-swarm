"""AgentDefinition — minimal 5-field YAML-based agent config.

Phase1 fields (required):
  name, role, system_prompt, tools, version

Uses pydantic BaseModel for validation and serialization.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class AgentDefinition(BaseModel):
    """A single agent definition loaded from YAML."""

    name: str
    role: str
    system_prompt: str
    tools: list[str]
    version: str = "1.0.0"

    # Phase2+ fields (not validated in Phase1, kept for forward compat)
    metadata: dict[str, Any] = Field(default_factory=dict, exclude=True)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("name", "role", "system_prompt")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be non-empty")
        return v

    @field_validator("tools")
    @classmethod
    def _tools_list(cls, v: list[str]) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("must be a list of strings")
        return v

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
        # Pop known fields; leftovers go into metadata
        known = {"name", "role", "system_prompt", "tools", "version"}
        kwargs = {k: data.pop(k) for k in list(data.keys()) if k in known}
        metadata = dict(data)  # whatever remains
        if metadata:
            kwargs["metadata"] = metadata
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (round-trippable)."""
        d = self.model_dump(exclude={"metadata"})
        d.update(self.metadata)
        return d

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def check(self) -> bool:
        """Phase1 lightweight validation.

        Raises ValueError on first problem found.
        Returns True when valid.
        """
        # Pydantic already validated types on construction; this checks business rules
        if self.role not in {"worker", "pm", "centurion"}:
            raise ValueError(f"role '{self.role}' not in supported set (worker/pm/centurion)")

        _ALLOWED = {"read_file", "write_file", "list_dir", "search_text"}
        unknown = [t for t in self.tools if t not in _ALLOWED]
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")

        return True
