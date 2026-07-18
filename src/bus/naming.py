"""
File-as-Bus 命名规范。

命名协议：
  任务卡片文件名：{prefix}_{task_id}_{status}.json
  产出物目录：artifacts/{task_id}/

状态：pending / claimed / done / failed
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TaskStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    DONE = "done"
    FAILED = "failed"


class TaskType(str, Enum):
    PM = "pm"
    CENTURION = "centurion"
    WORKER = "worker"


# 目录名常量
TASK_POOL_DIR = "task_pool"
IN_PROGRESS_DIR = "in_progress"
DONE_DIR = "done"
ARTIFACTS_DIR = "artifacts"


# 文件名正则：{prefix}_{task_id}_{status}.json
_FILENAME_RE = re.compile(
    r"^(?P<prefix>pm|centurion|worker)_(?P<task_id>.+)_(?P<status>pending|claimed|done|failed)\.json$"
)


@dataclass(frozen=True)
class TaskFileName:
    """解析后的任务文件名信息。"""
    prefix: str          # pm / centurion / worker
    task_id: str         # 完整任务 ID（不含前缀和状态）
    status: TaskStatus
    full_id: str         # prefix + "_" + task_id（用于唯一标识）

    @property
    def type(self) -> TaskType:
        return TaskType(self.prefix)


def parse_filename(filename: str) -> TaskFileName | None:
    """解析任务卡片文件名，返回 None 表示不匹配。"""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None
    prefix = m.group("prefix")
    task_id = m.group("task_id")
    status = TaskStatus(m.group("status"))
    return TaskFileName(
        prefix=prefix,
        task_id=task_id,
        status=status,
        full_id=f"{prefix}_{task_id}",
    )


def build_filename(full_id: str, status: TaskStatus) -> str:
    """根据完整任务 ID 和状态构造文件名。"""
    return f"{full_id}_{status.value}.json"


def status_dir(status: TaskStatus) -> str:
    """根据状态返回对应的目录名。"""
    if status == TaskStatus.PENDING:
        return TASK_POOL_DIR
    if status in (TaskStatus.CLAIMED,):
        return IN_PROGRESS_DIR
    if status in (TaskStatus.DONE, TaskStatus.FAILED):
        return DONE_DIR
    return TASK_POOL_DIR


def artifact_dir(full_id: str) -> str:
    """返回任务对应的产出物目录名。"""
    return f"{ARTIFACTS_DIR}/{full_id}"


def generate_task_id(prefix: str, *parts: str) -> str:
    """生成任务 ID：prefix + parts 用下划线连接。"""
    clean_parts = [re.sub(r"[^\w\-]", "_", p) for p in parts]
    return f"{prefix}_" + "_".join(clean_parts)


def list_task_files(workspace: Path, prefix: str | None = None,
                    status: TaskStatus | None = None) -> list[Path]:
    """列出工作区中匹配的任务卡片文件。

    Args:
        workspace: 工作区根目录
        prefix: 可选，按前缀过滤（pm/centurion/worker）
        status: 可选，按状态过滤
    """
    if status is not None:
        dirs = [workspace / status_dir(status)]
    else:
        dirs = [
            workspace / TASK_POOL_DIR,
            workspace / IN_PROGRESS_DIR,
            workspace / DONE_DIR,
        ]

    results: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.suffix != ".json":
                continue
            parsed = parse_filename(f.name)
            if parsed is None:
                continue
            if prefix is not None and parsed.prefix != prefix:
                continue
            if status is not None and parsed.status != status:
                continue
            results.append(f)
    return results
