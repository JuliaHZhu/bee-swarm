"""
极简 Agent 循环 —— 从 nanobot 提取并简化。
原始代码版权：MIT License, Copyright (c) 2025-present Xubin Ren and the nanobot contributors

核心循环：
  1. 构建消息上下文
  2. 调用 LLM
  3. 如果有工具调用，执行工具并回注结果
  4. 重复直到 LLM 返回最终回复或达到最大轮次
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .llm_backend import LLMProvider, LLMResponse, ToolCallRequest
from .tool_calling import ToolRegistry, ToolResult


@dataclass
class AgentLoopConfig:
    """Agent 循环配置。"""
    max_iterations: int = 10
    temperature: float = 0.7
    system_prompt: str = "You are a helpful assistant."
    model: str | None = None


@dataclass
class AgentRunResult:
    """Agent 执行结果。"""
    final_content: str | None
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    iterations: int = 0
    stop_reason: str = "completed"
    error: str | None = None


class SimpleAgentLoop:
    """极简 Agent 循环：LLM + 工具调用，无 session、无记忆、无 hooks。"""

    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry | None = None,
        config: AgentLoopConfig | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tools or ToolRegistry()
        self.config = config or AgentLoopConfig()

    async def run(self, user_message: str, system_prompt: str | None = None) -> AgentRunResult:
        """执行一次完整的 agent 循环。"""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt or self.config.system_prompt},
            {"role": "user", "content": user_message},
        ]
        tools_used: list[str] = []
        iterations = 0
        stop_reason = "completed"
        final_content: str | None = None
        error: str | None = None

        try:
            while iterations < self.config.max_iterations:
                iterations += 1

                # 1. 调用 LLM
                tool_defs = self.tools.get_definitions() if self.tools else None
                response = await self.provider.chat_completions(
                    messages=messages,
                    tools=tool_defs if tool_defs else None,
                    model=self.config.model,
                    temperature=self.config.temperature,
                )

                # 2. 构造 assistant 消息
                assistant_msg = self._build_assistant_message(response)
                messages.append(assistant_msg)

                # 3. 如果没有工具调用，结束循环
                if not response.tool_calls:
                    final_content = response.content or ""
                    stop_reason = response.stop_reason or "stop"
                    break

                # 4. 执行工具调用
                for tc in response.tool_calls:
                    tools_used.append(tc.name)
                    result = await self.tools.execute(tc.name, tc.arguments)
                    result_str = str(result)
                    is_error = isinstance(result, ToolResult) and result.is_error

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result_str,
                    })

                    # ponytail: 不做单工具失败的重试，把错误丢给 LLM 自己处理
                    # 如果 LLM 一直死循环，max_iterations 会兜底

                # 继续下一轮

            else:
                # 达到最大轮次
                final_content = final_content or "Reached maximum iterations without final response."
                stop_reason = "max_iterations"

        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            stop_reason = "error"
            final_content = final_content or f"Error: {error}"

        return AgentRunResult(
            final_content=final_content,
            messages=messages,
            tools_used=tools_used,
            iterations=iterations,
            stop_reason=stop_reason,
            error=error,
        )

    def _build_assistant_message(self, response: LLMResponse) -> dict[str, Any]:
        """从 LLM 响应构造 assistant 消息。"""
        msg: dict[str, Any] = {"role": "assistant"}
        if response.content is not None:
            msg["content"] = response.content
        else:
            msg["content"] = None

        if response.tool_calls:
            tool_calls_list = []
            for tc in response.tool_calls:
                import json
                args_str = tc.arguments if isinstance(tc.arguments, str) else json.dumps(tc.arguments, ensure_ascii=False)
                tool_calls_list.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": args_str,
                    },
                })
            msg["tool_calls"] = tool_calls_list

        return msg
