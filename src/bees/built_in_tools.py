"""
Worker Bee 内置工具集。

第一阶段提供基础文件操作工具：
- read_file: 读取文件
- write_file: 写入文件
- list_dir: 列出目录
- search_text: 在文件中搜索文本
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..base.tool_calling import Tool, ToolResult, tool_parameters


class _BaseFileTool(Tool):
    """文件工具基类：工作区路径解析。"""

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace).resolve()

    def _resolve_path(self, path: str) -> Path:
        """解析路径，限制在工作区内。"""
        target = (self._workspace / path).resolve()
        # 确保在工作区内（简单的安全检查）
        try:
            target.relative_to(self._workspace)
        except ValueError:
            # 如果路径跳出工作区，强制回到工作区根
            target = self._workspace / Path(path).name
        return target


@tool_parameters({
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "要读取的文件路径（相对工作区）",
        },
        "max_lines": {
            "type": "integer",
            "description": "最大读取行数，默认不限制",
            "minimum": 1,
        },
    },
    "required": ["path"],
})
class ReadFileTool(_BaseFileTool):
    """读取工作区内的文件内容。"""

    name = "read_file"
    description = "读取工作区内的文本文件内容"
    read_only = True

    async def execute(self, path: str, max_lines: int | None = None, **kwargs: Any) -> str:
        target = self._resolve_path(path)
        if not target.exists():
            return ToolResult.error(f"Error: File not found: {path}")
        if not target.is_file():
            return ToolResult.error(f"Error: Not a file: {path}")
        try:
            with open(target, "r", encoding="utf-8") as f:
                if max_lines:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            break
                        lines.append(line)
                    content = "".join(lines)
                    if len(lines) == max_lines:
                        content += f"\n... (truncated at {max_lines} lines)"
                    return content
                return f.read()
        except UnicodeDecodeError:
            return ToolResult.error(f"Error: Cannot decode file as UTF-8: {path}")
        except Exception as e:
            return ToolResult.error(f"Error reading file: {e}")


@tool_parameters({
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "写入的文件路径（相对工作区）",
        },
        "content": {
            "type": "string",
            "description": "要写入的文件内容",
        },
        "append": {
            "type": "boolean",
            "description": "是否追加模式，默认覆盖",
        },
    },
    "required": ["path", "content"],
})
class WriteFileTool(_BaseFileTool):
    """写入文件到工作区。"""

    name = "write_file"
    description = "将内容写入工作区内的文件"

    async def execute(self, path: str, content: str, append: bool = False, **kwargs: Any) -> str:
        target = self._resolve_path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(target, mode, encoding="utf-8") as f:
                f.write(content)
            action = "Appended to" if append else "Wrote"
            return f"{action} file: {path} ({len(content)} chars)"
        except Exception as e:
            return ToolResult.error(f"Error writing file: {e}")


@tool_parameters({
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "要列出的目录路径（相对工作区，默认根目录）",
        },
        "recursive": {
            "type": "boolean",
            "description": "是否递归列出子目录",
        },
    },
    "required": [],
})
class ListDirTool(_BaseFileTool):
    """列出工作区内的目录内容。"""

    name = "list_dir"
    description = "列出工作区内指定目录的文件和子目录"
    read_only = True

    async def execute(self, path: str = ".", recursive: bool = False, **kwargs: Any) -> str:
        target = self._resolve_path(path)
        if not target.exists():
            return ToolResult.error(f"Error: Directory not found: {path}")
        if not target.is_dir():
            return ToolResult.error(f"Error: Not a directory: {path}")
        try:
            lines: list[str] = []
            if recursive:
                for root, dirs, files in os.walk(target):
                    rel_root = os.path.relpath(root, target)
                    if rel_root == ".":
                        rel_root = ""
                    indent = rel_root.count(os.sep) * 2 if rel_root else 0
                    prefix = " " * indent
                    if rel_root:
                        lines.append(f"{prefix}{os.path.basename(root)}/")
                    for f in sorted(files):
                        lines.append(f"{prefix}  {f}")
            else:
                for item in sorted(target.iterdir()):
                    suffix = "/" if item.is_dir() else ""
                    lines.append(f"{item.name}{suffix}")
            return "\n".join(lines) if lines else "(empty directory)"
        except Exception as e:
            return ToolResult.error(f"Error listing directory: {e}")


@tool_parameters({
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "要搜索的文本模式",
        },
        "path": {
            "type": "string",
            "description": "搜索起始路径（相对工作区，默认根目录）",
        },
        "max_results": {
            "type": "integer",
            "description": "最大结果数，默认 20",
            "minimum": 1,
            "maximum": 100,
        },
    },
    "required": ["pattern"],
})
class SearchTextTool(_BaseFileTool):
    """在工作区文件中搜索文本。"""

    name = "search_text"
    description = "在工作区的文本文件中搜索指定内容"
    read_only = True

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        max_results: int = 20,
        **kwargs: Any,
    ) -> str:
        target = self._resolve_path(path)
        if not target.exists():
            return ToolResult.error(f"Error: Path not found: {path}")

        results: list[str] = []
        count = 0

        try:
            if target.is_file():
                files_to_search = [target]
            else:
                files_to_search = []
                for root, _, files in os.walk(target):
                    for f in files:
                        files_to_search.append(Path(root) / f)

            for filepath in files_to_search:
                if count >= max_results:
                    break
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        for lineno, line in enumerate(f, 1):
                            if pattern.lower() in line.lower():
                                rel = filepath.relative_to(self._workspace)
                                results.append(f"{rel}:{lineno}: {line.strip()[:120]}")
                                count += 1
                                if count >= max_results:
                                    break
                except (IsADirectoryError, PermissionError):
                    continue
        except Exception as e:
            return ToolResult.error(f"Error searching: {e}")

        if not results:
            return f"No matches found for '{pattern}'"
        return f"Found {count} match(es) for '{pattern}':\n" + "\n".join(results)


def register_worker_tools(registry, workspace: Path) -> None:
    """向工具注册表注册 Worker Bee 的默认工具集。"""
    registry.register(ReadFileTool(workspace))
    registry.register(WriteFileTool(workspace))
    registry.register(ListDirTool(workspace))
    registry.register(SearchTextTool(workspace))
