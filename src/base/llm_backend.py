"""
LLM 后端适配层 —— 从 nanobot 提取并简化。
原始代码版权：MIT License, Copyright (c) 2025-present Xubin Ren and the nanobot contributors

多模型后端适配，支持：
- OpenAI 兼容 API
- Mock 后端（用于测试）
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRequest:
    """LLM 返回的工具调用请求。"""
    id: str
    name: str
    arguments: Any


@dataclass
class LLMResponse:
    """LLM 响应。"""
    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    stop_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)


class LLMProvider(ABC):
    """LLM 提供者抽象基类。"""

    @abstractmethod
    async def chat_completions(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 1.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """发起聊天补全请求。"""
        ...

    def get_default_model(self) -> str:
        return "default"


class MockLLMProvider(LLMProvider):
    """Mock LLM 后端，用于测试。

    支持预设响应序列，模拟简单的工具调用流程。
    """

    def __init__(
        self,
        responses: list[LLMResponse] | None = None,
        model: str = "mock-model",
    ) -> None:
        self._responses = responses or []
        self._index = 0
        self._model = model
        # 历史调用记录，用于断言
        self.call_history: list[dict[str, Any]] = []

    def add_response(self, response: LLMResponse) -> None:
        self._responses.append(response)

    async def chat_completions(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 1.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.call_history.append({
            "messages": list(messages),
            "tools": tools,
            "model": model,
            "temperature": temperature,
        })

        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp

        # 默认响应：直接返回一条结束语
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str):
                    last_user_msg = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            last_user_msg = block.get("text", "")
                            break
                break

        return LLMResponse(
            content=f"[Mock LLM] Received: {last_user_msg[:80]}",
            stop_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 10},
        )

    def get_default_model(self) -> str:
        return self._model

    def reset(self) -> None:
        self._index = 0
        self.call_history = []


class OpenAICompatProvider(LLMProvider):
    """OpenAI 兼容 API 提供者。

    支持任何 OpenAI 格式的 API 端点（OpenAI、Azure OpenAI、本地模型等）。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self._model = model

    def get_default_model(self) -> str:
        return self._model

    async def chat_completions(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 1.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        # ponytail: 使用 aiohttp 异步请求，不引入额外依赖
        import aiohttp

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"LLM API error {resp.status}: {text}")
                data = await resp.json()

        return self._parse_response(data)

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        choice = data["choices"][0]
        message = choice.get("message", {})
        content = message.get("content")

        tool_calls: list[ToolCallRequest] = []
        raw_tool_calls = message.get("tool_calls", [])
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            args_raw = fn.get("arguments", "{}")
            try:
                arguments = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                arguments = args_raw
            tool_calls.append(ToolCallRequest(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=arguments,
            ))

        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=choice.get("finish_reason", "stop"),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
        )
