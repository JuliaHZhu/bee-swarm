"""
知识图谱存储 —— 第一阶段极简骨架。

借鉴 CRG（Cognitive Resource Graph）思路，使用 SQLite 存储节点和边。

节点类型：task、artifact、concept、file、bee
边类型：depends_on、produces、references、contains、assigned_to、created_by、parent_of

第一阶段：只写入不查询，作为未来扩展的基础。
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


# 节点类型
NODE_TYPES = {"task", "artifact", "concept", "file", "bee"}

# 边类型
EDGE_TYPES = {
    "depends_on",    # task depends_on task
    "produces",      # task produces artifact
    "references",    # artifact references concept
    "contains",      # file contains concept
    "assigned_to",   # task assigned_to bee
    "created_by",    # task created_by bee
    "parent_of",     # task parent_of task
}


class GraphStore:
    """SQLite 图存储：节点 + 边。"""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表。"""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);

                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
                CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_unique
                    ON edges(source_id, target_id, type);
            """)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- 节点操作 ----

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """添加或更新一个节点。"""
        now = time.time()
        props_json = json.dumps(properties or {}, ensure_ascii=False)

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO nodes (id, type, label, properties, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type = excluded.type,
                    label = excluded.label,
                    properties = excluded.properties,
                    updated_at = excluded.updated_at
                """,
                (node_id, node_type, label, props_json, now, now),
            )

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """获取节点。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM nodes WHERE id = ?", (node_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "id": row["id"],
                "type": row["type"],
                "label": row["label"],
                "properties": json.loads(row["properties"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def list_nodes(self, node_type: str | None = None) -> list[dict[str, Any]]:
        """列出节点，可选按类型过滤。"""
        with self._conn() as conn:
            if node_type:
                rows = conn.execute(
                    "SELECT * FROM nodes WHERE type = ? ORDER BY created_at",
                    (node_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM nodes ORDER BY created_at",
                ).fetchall()
            return [
                {
                    "id": r["id"],
                    "type": r["type"],
                    "label": r["label"],
                    "properties": json.loads(r["properties"]),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]

    # ---- 边操作 ----

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """添加一条边（幂等）。如果端点节点不存在，创建占位节点。"""
        now = time.time()
        edge_id = f"{source_id}->{target_id}:{edge_type}"
        props_json = json.dumps(properties or {}, ensure_ascii=False)

        with self._conn() as conn:
            # 确保两端节点存在
            for nid in (source_id, target_id):
                existing = conn.execute(
                    "SELECT id FROM nodes WHERE id = ?", (nid,),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO nodes (id, type, label, properties, created_at, updated_at)
                        VALUES (?, 'unknown', ?, '{}', ?, ?)
                        """,
                        (nid, nid, now, now),
                    )

            conn.execute(
                """
                INSERT OR IGNORE INTO edges (id, source_id, target_id, type, properties, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (edge_id, source_id, target_id, edge_type, props_json, now),
            )

    def get_outgoing(self, node_id: str, edge_type: str | None = None) -> list[dict[str, Any]]:
        """获取从节点出发的边。"""
        with self._conn() as conn:
            if edge_type:
                rows = conn.execute(
                    "SELECT * FROM edges WHERE source_id = ? AND type = ?",
                    (node_id, edge_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM edges WHERE source_id = ?",
                    (node_id,),
                ).fetchall()
            return [
                {
                    "id": r["id"],
                    "source_id": r["source_id"],
                    "target_id": r["target_id"],
                    "type": r["type"],
                    "properties": json.loads(r["properties"]),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    def get_incoming(self, node_id: str, edge_type: str | None = None) -> list[dict[str, Any]]:
        """获取指向节点的边。"""
        with self._conn() as conn:
            if edge_type:
                rows = conn.execute(
                    "SELECT * FROM edges WHERE target_id = ? AND type = ?",
                    (node_id, edge_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM edges WHERE target_id = ?",
                    (node_id,),
                ).fetchall()
            return [
                {
                    "id": r["id"],
                    "source_id": r["source_id"],
                    "target_id": r["target_id"],
                    "type": r["type"],
                    "properties": json.loads(r["properties"]),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    # ---- 便捷方法 ----

    def record_task(self, task_id: str, title: str, **props: Any) -> None:
        """记录一个任务节点。"""
        self.add_node(task_id, "task", title, props)

    def record_artifact(self, artifact_id: str, label: str, **props: Any) -> None:
        """记录一个产出物节点。"""
        self.add_node(artifact_id, "artifact", label, props)

    def record_bee(self, bee_id: str, bee_type: str, **props: Any) -> None:
        """记录一个 Bee 节点。"""
        self.add_node(bee_id, "bee", bee_type, props)

    def task_produces_artifact(self, task_id: str, artifact_id: str) -> None:
        """记录 task produces artifact 关系。"""
        self.add_edge(task_id, artifact_id, "produces")

    def task_parent_of(self, parent_id: str, child_id: str) -> None:
        """记录任务父子关系。"""
        self.add_edge(parent_id, child_id, "parent_of")

    def task_created_by(self, task_id: str, bee_id: str) -> None:
        """记录任务创建者。"""
        self.add_edge(task_id, bee_id, "created_by")
