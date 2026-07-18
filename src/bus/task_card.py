"""
任务卡片读写 —— File-as-Bus 的核心数据结构。

任务卡片是 JSON 文件，包含任务的所有元数据和状态。
状态通过文件移动（rename）来流转，保证原子性。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .naming import (
    TaskStatus,
    TaskType,
    build_filename,
    parse_filename,
    status_dir,
    generate_task_id,
    list_task_files,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskCard:
    """任务卡片数据结构。"""
    task_id: str                    # 完整 ID：prefix_xxx_yyy
    type: str                       # pm / centurion / worker
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: str = "normal"        # low / normal / high / urgent
    parent_id: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    created_by: str = "system"
    assigned_to: str | None = None
    acceptance_criteria: list[str] = field(default_factory=list)

    # Worker 任务专用
    tool: str | None = None
    tool_params: dict[str, Any] = field(default_factory=dict)

    # Centurion / PM 任务专用
    subtasks: list[str] = field(default_factory=list)

    # 产出物路径（相对 workspace 根）
    artifact_paths: list[str] = field(default_factory=list)

    # 执行结果
    result: str | None = None
    error: str | None = None

    # 扩展元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, TaskStatus) else self.status
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskCard":
        status = data.get("status", "pending")
        if isinstance(status, str):
            status = TaskStatus(status)
        return cls(
            task_id=data["task_id"],
            type=data.get("type", "worker"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=status,
            priority=data.get("priority", "normal"),
            parent_id=data.get("parent_id"),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
            created_by=data.get("created_by", "system"),
            assigned_to=data.get("assigned_to"),
            acceptance_criteria=data.get("acceptance_criteria", []),
            tool=data.get("tool"),
            tool_params=data.get("tool_params", {}),
            subtasks=data.get("subtasks", []),
            artifact_paths=data.get("artifact_paths", []),
            result=data.get("result"),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )

    @property
    def is_done(self) -> bool:
        return self.status in (TaskStatus.DONE, TaskStatus.FAILED)

    @property
    def filename(self) -> str:
        return build_filename(self.task_id, self.status)


class TaskCardStore:
    """任务卡片存储：基于文件系统的 CRUD 操作。"""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        # 确保目录存在
        for dirname in ["task_pool", "in_progress", "done", "artifacts"]:
            (self.workspace / dirname).mkdir(parents=True, exist_ok=True)

    # ---- 写操作 ----

    def create(self, card: TaskCard) -> Path:
        """创建新任务卡片，写入 task_pool/。"""
        card.status = TaskStatus.PENDING
        card.updated_at = _now_iso()
        path = self.workspace / "task_pool" / card.filename
        self._write(path, card)
        return path

    def claim(self, task_id: str, bee_name: str) -> TaskCard | None:
        """领取任务：原子地将 pending 任务移入 in_progress 并标记 claimed。

        使用 rename（同分区原子）实现并发安全。
        返回领取后的 TaskCard，失败返回 None。
        """
        pending_path = self.workspace / "task_pool" / build_filename(task_id, TaskStatus.PENDING)
        if not pending_path.exists():
            return None

        card = self._read(pending_path)
        if card.status != TaskStatus.PENDING:
            return None

        card.status = TaskStatus.CLAIMED
        card.assigned_to = bee_name
        card.updated_at = _now_iso()

        target_path = self.workspace / "in_progress" / card.filename
        try:
            # 先写目标文件，再删除源文件（模拟原子移动）
            # 真正的原子移动用 os.rename，但需要确保在同一文件系统
            self._write(target_path, card)
            pending_path.unlink()
            return card
        except Exception:
            # 并发冲突：目标可能已存在，或源已被删
            if target_path.exists():
                # 回滚：我们写的目标文件，删掉
                try:
                    target_path.unlink()
                except Exception:
                    pass
            return None

    def update(self, card: TaskCard) -> Path:
        """更新任务卡片内容（状态不变时用）。"""
        card.updated_at = _now_iso()
        path = self._current_path(card)
        self._write(path, card)
        return path

    def complete(self, card: TaskCard, result: str | None = None,
                 failed: bool = False, error: str | None = None) -> Path:
        """完成任务：移入 done/ 目录，标记 done 或 failed。"""
        card.status = TaskStatus.FAILED if failed else TaskStatus.DONE
        card.result = result
        card.error = error
        card.updated_at = _now_iso()

        # 从 in_progress 移到 done
        source_dir = self.workspace / "in_progress"
        source_path = source_dir / build_filename(card.task_id, TaskStatus.CLAIMED)
        target_path = self.workspace / "done" / card.filename

        # 写入目标
        self._write(target_path, card)

        # 尝试删除源文件（可能不存在，比如直接从 pending complete）
        if source_path.exists():
            try:
                source_path.unlink()
            except Exception:
                pass

        # 也检查 task_pool 中是否有旧文件
        pool_path = self.workspace / "task_pool" / build_filename(card.task_id, TaskStatus.PENDING)
        if pool_path.exists():
            try:
                pool_path.unlink()
            except Exception:
                pass

        return target_path

    def add_subtask(self, parent: TaskCard, child: TaskCard) -> None:
        """在父任务中添加子任务引用。"""
        if child.task_id not in parent.subtasks:
            parent.subtasks.append(child.task_id)
            self.update(parent)

    # ---- 读操作 ----

    def get(self, task_id: str) -> TaskCard | None:
        """根据 task_id 查找任务卡片（搜索所有状态目录）。"""
        for status in [TaskStatus.PENDING, TaskStatus.CLAIMED,
                       TaskStatus.DONE, TaskStatus.FAILED]:
            path = self.workspace / status_dir(status) / build_filename(task_id, status)
            if path.exists():
                return self._read(path)
        return None

    def list_pending(self, prefix: str | None = None) -> list[TaskCard]:
        """列出待领取的任务。"""
        files = list_task_files(self.workspace, prefix=prefix, status=TaskStatus.PENDING)
        return [self._read(f) for f in files]

    def list_in_progress(self, prefix: str | None = None) -> list[TaskCard]:
        """列出进行中的任务。"""
        files = list_task_files(self.workspace, prefix=prefix, status=TaskStatus.CLAIMED)
        return [self._read(f) for f in files]

    def list_done(self, prefix: str | None = None) -> list[TaskCard]:
        """列出已完成的任务（done 或 failed）。"""
        results: list[TaskCard] = []
        for status in (TaskStatus.DONE, TaskStatus.FAILED):
            files = list_task_files(self.workspace, prefix=prefix, status=status)
            for f in files:
                try:
                    results.append(self._read(f))
                except Exception:
                    continue
        return results

    def list_by_parent(self, parent_id: str) -> list[TaskCard]:
        """列出某个父任务的所有子任务。"""
        results: list[TaskCard] = []
        for status_dir_name in ["task_pool", "in_progress", "done"]:
            d = self.workspace / status_dir_name
            if not d.is_dir():
                continue
            for f in d.iterdir():
                if not f.is_file() or f.suffix != ".json":
                    continue
                try:
                    card = self._read(f)
                    if card.parent_id == parent_id:
                        results.append(card)
                except Exception:
                    continue
        return results

    # ---- 内部方法 ----

    def _current_path(self, card: TaskCard) -> Path:
        """获取任务卡片当前应该所在的路径。"""
        return self.workspace / status_dir(card.status) / card.filename

    def _read(self, path: Path) -> TaskCard:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TaskCard.from_dict(data)

    def _write(self, path: Path, card: TaskCard) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card.to_dict(), f, ensure_ascii=False, indent=2)


def new_task_id(prefix: str, *parts: str) -> str:
    """生成新的任务 ID（带短随机后缀避免冲突）。"""
    short_uuid = uuid.uuid4().hex[:8]
    if parts:
        base = generate_task_id(prefix, *parts)
        return f"{base}_{short_uuid}"
    return f"{prefix}_{short_uuid}"
