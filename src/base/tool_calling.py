"""
工具调用层 —— 从 nanobot 提取并简化。
原始代码版权：MIT License, Copyright (c) 2025-present Xubin Ren and the nanobot contributors

极简工具调用框架：
- Tool 基类：name / description / parameters / execute()
- ToolRegistry：工具注册、查找、执行
- JSON Schema 参数校验
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any


class ToolResult(str):
    """字符串兼容的工具输出，带结构化状态。"""

    is_error: bool

    def __new__(cls, content: str, *, is_error: bool = False) -> ToolResult:
        obj = str.__new__(cls, content)
        obj.is_error = is_error
        return obj

    @classmethod
    def error(cls, content: str) -> ToolResult:
        return cls(content, is_error=True)


def validate_json_schema_value(val: Any, schema: dict[str, Any], path: str = "") -> list[str]:
    """校验值是否符合 JSON Schema；返回错误列表（空表示通过）。"""
    raw_type = schema.get("type")
    nullable = (isinstance(raw_type, list) and "null" in raw_type) or schema.get("nullable", False)

    def _resolve_type(t: Any) -> str | None:
        if isinstance(t, list):
            return next((x for x in t if x != "null"), None)
        return t

    t = _resolve_type(raw_type)
    label = path or "parameter"

    if nullable and val is None:
        return []
    if t == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
        return [f"{label} should be integer"]
    if t == "number" and not isinstance(val, (int, float)) or (t == "number" and isinstance(val, bool)):
        return [f"{label} should be number"]
    _type_map = {"string": str, "boolean": bool, "array": list, "object": dict}
    if t in _type_map and not isinstance(val, _type_map[t]):
        return [f"{label} should be {t}"]

    errors: list[str] = []
    if "enum" in schema and val not in schema["enum"]:
        errors.append(f"{label} must be one of {schema['enum']}")
    if t in ("integer", "number"):
        if "minimum" in schema and val < schema["minimum"]:
            errors.append(f"{label} must be >= {schema['minimum']}")
        if "maximum" in schema and val > schema["maximum"]:
            errors.append(f"{label} must be <= {schema['maximum']}")
    if t == "string":
        if "minLength" in schema and len(val) < schema["minLength"]:
            errors.append(f"{label} must be at least {schema['minLength']} chars")
        if "maxLength" in schema and len(val) > schema["maxLength"]:
            errors.append(f"{label} must be at most {schema['maxLength']} chars")
    if t == "object":
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in val:
                errors.append(f"missing required {path + '.' if path else ''}{k}")
        additional = schema.get("additionalProperties", True)
        for k, v in val.items():
            subpath = f"{path}.{k}" if path else k
            if k in props:
                errors.extend(validate_json_schema_value(v, props[k], subpath))
            elif additional is False:
                errors.append(f"unexpected parameter {subpath}")
            elif isinstance(additional, dict):
                errors.extend(validate_json_schema_value(v, additional, subpath))
    if t == "array":
        if "minItems" in schema and len(val) < schema["minItems"]:
            errors.append(f"{label} must have at least {schema['minItems']} items")
        if "maxItems" in schema and len(val) > schema["maxItems"]:
            errors.append(f"{label} must be at most {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(val):
                errors.extend(validate_json_schema_value(item, schema["items"], f"{path}[{i}]"))
    return errors


class Tool(ABC):
    """工具基类：Agent 的能力单元。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名，用于 function calling。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述。"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """工具参数的 JSON Schema。"""
        ...

    @property
    def read_only(self) -> bool:
        """是否无副作用，可安全并行。"""
        return False

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """执行工具，返回内容字符串；失败时返回 ToolResult.error(...)。"""
        ...

    def to_schema(self) -> dict[str, Any]:
        """OpenAI function schema 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def cast_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """简单的类型转换（字符串 → 数字/布尔）。"""
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            return params
        return self._cast_object(params, schema)

    def _cast_object(self, obj: Any, schema: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(obj, dict):
            return obj
        props = schema.get("properties", {})
        casted: dict[str, Any] = {}
        for k, v in obj.items():
            if k in props:
                casted[k] = self._cast_value(v, props[k])
            else:
                casted[k] = v
        return casted

    def _cast_value(self, val: Any, schema: dict[str, Any]) -> Any:
        def _resolve_type(t: Any) -> str | None:
            if isinstance(t, list):
                return next((x for x in t if x != "null"), None)
            return t

        t = _resolve_type(schema.get("type"))
        if isinstance(val, str) and t in ("integer", "number"):
            try:
                return int(val) if t == "integer" else float(val)
            except ValueError:
                return val
        if t == "string" and val is not None:
            return str(val)
        if t == "boolean" and isinstance(val, str):
            low = val.lower()
            if low in ("true", "1", "yes"):
                return True
            if low in ("false", "0", "no"):
                return False
        if t == "array" and isinstance(val, list) and "items" in schema:
            return [self._cast_value(x, schema["items"]) for x in val]
        if t == "object" and isinstance(val, dict):
            return self._cast_object(val, schema)
        return val

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """校验参数，返回错误列表。"""
        if not isinstance(params, dict):
            return [f"parameters must be an object, got {type(params).__name__}"]
        schema = self.parameters or {}
        return validate_json_schema_value(params, {**schema, "type": "object"}, "")


class ToolRegistry:
    """工具注册表：注册、查找、执行工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._cached_definitions: list[dict[str, Any]] | None = None

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        self._cached_definitions = None

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def get_definitions(self) -> list[dict[str, Any]]:
        """获取所有工具的 OpenAI schema 定义。"""
        if self._cached_definitions is not None:
            return self._cached_definitions
        self._cached_definitions = [
            self._tools[name].to_schema() for name in sorted(self._tools.keys())
        ]
        return self._cached_definitions

    async def execute(self, name: str, params: Any) -> Any:
        """执行一个工具调用。"""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult.error(
                f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}"
            )

        # 参数兼容：字符串 JSON 解析
        if isinstance(params, str):
            stripped = params.strip()
            if stripped.startswith(("{", "[")):
                try:
                    params = json.loads(stripped)
                except Exception:
                    pass  # 保留原样，后续校验会报错

        if not isinstance(params, dict):
            return ToolResult.error(
                f"Error: Tool '{name}' parameters must be a JSON object, got {type(params).__name__}."
            )

        cast_params = tool.cast_params(params)
        errors = tool.validate_params(cast_params)
        if errors:
            return ToolResult.error(
                f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors)
            )

        try:
            result = await tool.execute(**cast_params)
            if isinstance(result, ToolResult) and result.is_error:
                return result
            return result
        except Exception as e:
            return ToolResult.error(f"Error executing {name}: {e}")


def tool_parameters(schema: dict[str, Any]):
    """类装饰器：为 Tool 子类附加 parameters 属性。

    用法:
        @tool_parameters({
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        })
        class ReadFileTool(Tool):
            ...
    """
    frozen = deepcopy(schema)

    def decorator(cls: type) -> type:
        @property
        def parameters(self: Any) -> dict[str, Any]:
            return deepcopy(frozen)

        cls.parameters = parameters  # type: ignore[assignment]
        abstract = getattr(cls, "__abstractmethods__", None)
        if abstract is not None and "parameters" in abstract:
            cls.__abstractmethods__ = frozenset(abstract - {"parameters"})  # type: ignore[misc]
        return cls

    return decorator
