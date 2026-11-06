"""LLM 适配层接口定义。

上层（agent）只依赖 ``ChatClient`` 协议，不依赖 openai SDK，
便于未来替换为其他模型供应商或测试用的假客户端。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, Sequence


@dataclass(frozen=True)
class ToolCallDelta:
    """单个工具调用在流式响应中的一个增量片段。"""

    index: int
    call_id: str | None = None
    name: str | None = None
    arguments: str | None = None


@dataclass(frozen=True)
class TokenUsage:
    """一次 LLM 调用的 token 用量（来自 API 返回，用于上下文监控）。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class ChatChunk:
    """归一化后的流式响应块。"""

    content: str | None = None
    tool_calls: tuple[ToolCallDelta, ...] = ()
    # 仅最后一个 chunk 携带本次调用的用量（API 开启 include_usage 时）
    usage: TokenUsage | None = None


class ChatClient(Protocol):
    """所有 LLM 适配器需要实现的接口。"""

    model_name: str

    def stream_chat(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
        *,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        ...
