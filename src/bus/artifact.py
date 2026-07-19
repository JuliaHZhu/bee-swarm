"""
产出物（Artifact）读写 —— File-as-Bus 的产出物管理。

每个任务的产出物存放在 artifacts/{task_id}/ 目录下。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class ArtifactStore:
    """产出物存储：基于文件系统的产出物读写。"""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.artifacts_dir = self.workspace / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def task_dir(self, task_id: str) -> Path:
        """获取任务的产出物目录。"""
        d = self.artifacts_dir / task_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_file(self, task_id: str, filename: str, content: str) -> Path:
        """写入一个文本产出物（原子写）。"""
        path = self.task_dir(task_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(str(tmp_path), str(path))
        return path

    def write_json(self, task_id: str, filename: str, data: Any) -> Path:
        """写入一个 JSON 产出物（原子写）。"""
        path = self.task_dir(task_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(str(tmp_path), str(path))
        return path

    def read_file(self, task_id: str, filename: str) -> str | None:
        """读取一个文本产出物，不存在返回 None。"""
        path = self.task_dir(task_id) / filename
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def read_json(self, task_id: str, filename: str) -> Any:
        """读取一个 JSON 产出物，不存在返回 None。"""
        content = self.read_file(task_id, filename)
        if content is None:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    def list_artifacts(self, task_id: str) -> list[Path]:
        """列出任务的所有产出物文件。"""
        d = self.task_dir(task_id)
        if not d.exists():
            return []
        return [p for p in d.rglob("*") if p.is_file()]

    def relative_path(self, absolute_path: Path) -> str:
        """将绝对路径转为相对 workspace 的路径。"""
        try:
            return str(absolute_path.relative_to(self.workspace))
        except ValueError:
            return str(absolute_path)
