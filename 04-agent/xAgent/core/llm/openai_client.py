"""OpenAI 兼容接口适配器（DeepSeek 等兼容 OpenAI 协议的服务同样适用）。"""

from __future__ import annotations

from typing import Any, AsyncIterator, Sequence

from openai import AsyncOpenAI, BadRequestError

from core.llm.base import ChatChunk, TokenUsage, ToolCallDelta


class OpenAIChatClient:
    """把 OpenAI SDK 的流式响应归一化为 ``ChatChunk``。"""

    def __init__(
        self, *, api_key: str, base_url: str | None, model_name: str
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

    async def stream_chat(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
        *,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": list(messages),
            "stream": True,
        }
        if tools:
            # 压缩等内部调用传入空 tools 时省略该参数，模型便无法发起工具调用
            kwargs["tools"] = list(tools)
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        try:
            # include_usage：最后一个 chunk 会携带本次调用的 token 用量
            stream = await self._client.chat.completions.create(
                stream_options={"include_usage": True}, **kwargs
            )
        except BadRequestError:
            # 个别兼容网关不认识 stream_options，退回不带用量的普通请求
            stream = await self._client.chat.completions.create(**kwargs)

        try:
            async for chunk in stream:
                usage: TokenUsage | None = None
                raw_usage = getattr(chunk, "usage", None)
                if raw_usage is not None:
                    usage = TokenUsage(
                        prompt_tokens=raw_usage.prompt_tokens or 0,
                        completion_tokens=raw_usage.completion_tokens or 0,
                    )
                if not chunk.choices:
                    # include_usage 的收尾 chunk 没有 choices，只有 usage
                    if usage is not None:
                        yield ChatChunk(usage=usage)
                    continue
                delta = chunk.choices[0].delta
                tool_calls = tuple(
                    ToolCallDelta(
                        index=call.index,
                        call_id=call.id,
                        name=call.function.name if call.function else None,
                        arguments=call.function.arguments if call.function else None,
                    )
                    for call in (delta.tool_calls or ())
                )
                if delta.content or tool_calls or usage is not None:
                    yield ChatChunk(content=delta.content, tool_calls=tool_calls, usage=usage)
        finally:
            await stream.close()
