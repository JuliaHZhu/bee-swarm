"""AgentRegistry — two-level config scan (built-in + workspace)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .agent_definition import AgentDefinition


class AgentRegistry:
    """Scan and cache agent definitions from YAML files.

    Loading order (later overrides earlier):
      1. <builtin_dir>/   — shipped with bee-swarm package
      2. <workspace_dir>/ — user-defined, workspace-scoped
    """

    def __init__(
        self,
        builtin_dir: Path | None = None,
        workspace_dir: Path | None = None,
    ) -> None:
        if builtin_dir is None:
            builtin_dir = Path(__file__).parent.parent.parent / "agents"
        self.builtin_dir = builtin_dir
        self.workspace_dir = workspace_dir
        self._cache: dict[str, AgentDefinition] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Re-scan all directories and rebuild cache."""
        self._cache.clear()
        for src_dir in (self.builtin_dir, self.workspace_dir):
            if src_dir is None or not src_dir.is_dir():
                continue
            for path in sorted(src_dir.glob("*.yaml")):
                try:
                    agent = AgentDefinition.from_yaml(path)
                except Exception:
                    continue
                self._cache[agent.name] = agent

    def get(self, name: str) -> AgentDefinition | None:
        """Fetch an agent by name."""
        if not self._cache:
            self.reload()
        return self._cache.get(name)

    def list_all(self) -> list[AgentDefinition]:
        """Return all registered agents."""
        if not self._cache:
            self.reload()
        return list(self._cache.values())

    def list_by_tag(self, tag: str) -> list[AgentDefinition]:
        """Phase1: simple tag inclusion match.

        Searches in ``metadata.tags`` (list) or falls back to substring match
        on name / system_prompt.
        """
        results: list[AgentDefinition] = []
        for agent in self.list_all():
            tags = agent.metadata.get("tags", [])
            if isinstance(tags, list) and tag in tags:
                results.append(agent)
            elif tag.lower() in agent.name.lower():
                results.append(agent)
        return results

    def names(self) -> Iterator[str]:
        """Yield all registered agent names."""
        if not self._cache:
            self.reload()
        yield from self._cache.keys()
