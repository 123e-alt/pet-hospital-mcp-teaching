"""Agent 会话：编排 LLM 流式响应与工具调用，并向前端输出事件流。

这是 core 对外的唯一业务门面：前端只需要 ``send()`` 的异步迭代，
不必了解 OpenAI 消息格式、工具执行细节或循环控制。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Sequence

from core.agent.prompt import SYSTEM_PROMPT
from core.context.archiver import ContextArchiver
from core.context.compactor import (
    CompactOutcome,
    build_compaction_prompt,
    summarize_messages,
)
from core.context.tokens import (
    DEFAULT_CONTEXT_WINDOW,
    ContextMonitor,
    estimate_tokens,
)
from core.events import (
    AgentEvent,
    ErrorOccurred,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnCompleted,
)
from core.llm.base import ChatClient
from core.tools.registry import ToolRegistry


class AgentSession:
    def __init__(
        self,
        *,
        llm: ChatClient,
        tools: ToolRegistry,
        system_prompt: str = SYSTEM_PROMPT,
        max_tool_rounds: int = 16,
        context_window: int = 0,
        warn_ratio: float = 0.8,
        summary_target_tokens: int = 5000,
        summary_max_tokens: int = 8000,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._max_tool_rounds = max_tool_rounds
        self._summary_target = summary_target_tokens
        self._summary_max = summary_max_tokens
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        # 上下文监控：window<=0 表示配置未指定，使用默认 128k（TUI 会标「默认」）
        window = context_window if context_window > 0 else DEFAULT_CONTEXT_WINDOW
        self._monitor = ContextMonitor(
            window=window,
            window_is_default=context_window <= 0,
            threshold=warn_ratio,
        )
        self._monitor.estimate_from_messages(self._messages)

    @property
    def messages(self) -> Sequence[dict[str, Any]]:
        """只读的会话历史快照。"""
        return tuple(self._messages)

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    @property
    def monitor(self) -> ContextMonitor:
        """上下文用量监控（供前端显示与阈值判断）。"""
        return self._monitor

    def reset(self) -> None:
        """清空会话历史，保留全部 system 消息（主提示词 + AGENTS.md 注入）。"""
        self._messages = [m for m in self._messages if m.get("role") == "system"]
        self._monitor.estimate_from_messages(self._messages)
        self._monitor.warned = False

    def inject_system_message(self, content: str) -> None:
        """在主 system 消息之后追加一条 system 消息（用于 AGENTS.md 注入）。

        「一次注入，全程复用」：注入后始终位于消息列表头部区域，
        后续所有轮次都会携带，保证 LLM 缓存前缀稳定。
        """
        self._messages.insert(1, {"role": "system", "content": content})
        self._monitor.estimate_from_messages(self._messages)

    def load_messages(self, messages: list[dict[str, Any]]) -> None:
        """恢复一个已保存会话（/resume）：整体替换当前消息列表。

        保存文件里已包含 system 消息（主提示词、AGENTS.md 注入、
        历次压缩摘要），恢复后无需重新注入即可继续会话。
        """
        restored = [dict(m) for m in messages]
        if not restored or restored[0].get("role") != "system":
            restored.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        self._messages = restored
        self._monitor.estimate_from_messages(self._messages)
        self._monitor.warned = False

    async def send(self, user_text: str) -> AsyncIterator[AgentEvent]:
        """处理一条用户输入，产出流式事件直到本回合结束。"""
        self._messages.append({"role": "user", "content": user_text})
        tool_call_count = 0

        try:
            for _ in range(self._max_tool_rounds):
                assistant_text = ""
                pending: dict[int, dict[str, str]] = {}
                last_usage = None

                async for chunk in self._llm.stream_chat(
                    self._messages, self._tools.schemas()
                ):
                    if chunk.usage is not None:
                        last_usage = chunk.usage
                    if chunk.content:
                        assistant_text += chunk.content
                        yield TextDelta(chunk.content)
                    for delta in chunk.tool_calls:
                        item = pending.setdefault(
                            delta.index, {"id": "", "name": "", "arguments": ""}
                        )
                        if delta.call_id:
                            item["id"] = delta.call_id
                        if delta.name:
                            item["name"] += delta.name
                        if delta.arguments:
                            item["arguments"] += delta.arguments

                # 每次响应结束后更新上下文用量：优先用 API 的真实 usage，
                # 拿不到时按消息文本估算
                if last_usage is not None:
                    self._monitor.update(last_usage.total_tokens, source="api")
                else:
                    self._monitor.estimate_from_messages(self._messages)

                calls = [pending[index] for index in sorted(pending)]

                if not calls:
                    self._messages.append(
                        {"role": "assistant", "content": assistant_text}
                    )
                    yield TurnCompleted(
                        reply=assistant_text, tool_call_count=tool_call_count
                    )
                    return

                for call in calls:
                    if not call["id"]:
                        call["id"] = f"call_{uuid.uuid4().hex[:8]}"

                self._messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_text or None,
                        "tool_calls": [
                            {
                                "id": call["id"],
                                "type": "function",
                                "function": {
                                    "name": call["name"],
                                    "arguments": call["arguments"],
                                },
                            }
                            for call in calls
                        ],
                    }
                )

                for call in calls:
                    yield ToolCallStarted(
                        call_id=call["id"],
                        name=call["name"],
                        arguments=call["arguments"],
                    )
                    # 工具执行已内置同步 handler 走线程池、异步 handler 直接 await 的分流
                    result = await self._tools.execute(call["name"], call["arguments"])
                    tool_call_count += 1
                    yield ToolCallFinished(
                        call_id=call["id"],
                        name=call["name"],
                        result=result.content,
                        ok=result.ok,
                    )
                    self._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": result.content,
                        }
                    )

            yield ErrorOccurred(
                f"已达到单轮最大工具调用轮数（{self._max_tool_rounds}），已停止。"
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield ErrorOccurred(f"{type(exc).__name__}: {exc}")

    # ---------- 上下文压缩 ----------

    async def compact(self, archiver: ContextArchiver) -> CompactOutcome:
        """压缩上下文：归档 → LLM 摘要 → 替换历史。

        顺序保证：
        1. 原始记录必须成功保存后才继续（保存失败直接中止）；
        2. 摘要生成失败时保持原上下文不变，可重新执行 /compact；
        3. 压缩调用不携带任何工具定义，期间不可能触发 Function Calling。
        """
        compressible = [m for m in self._messages if m.get("role") != "system"]
        if not compressible:
            return CompactOutcome(ok=False, error="会话没有可压缩的历史消息")

        model_name = getattr(self._llm, "model_name", "unknown")

        # 1. 归档原始上下文（必须成功）
        try:
            info = archiver.save(
                self._messages,
                model_name=model_name,
                token_usage=self._monitor.usage,
            )
        except OSError as exc:
            return CompactOutcome(
                ok=False, error=f"归档保存失败：{exc}（原上下文未改动）"
            )

        # 2. 调用 LLM 生成摘要（无工具；目标长度/输出上限来自配置）
        try:
            summary = await summarize_messages(
                self._llm,
                self._messages,
                system_prompt=build_compaction_prompt(self._summary_target),
                max_tokens=self._summary_max,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return CompactOutcome(
                ok=False,
                archive_id=info.id,
                error=(
                    f"摘要生成失败：{type(exc).__name__}: {exc}"
                    f"（原上下文未改动，归档 {info.id} 已保存，可重试 /compact）"
                ),
            )
        if not summary:
            return CompactOutcome(
                ok=False,
                archive_id=info.id,
                error="摘要生成失败：LLM 返回了空内容（原上下文未改动，可重试 /compact）",
            )

        # 3. 用摘要替换历史（保留 System Prompt）
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note = (
            f"此前上下文已于 {stamp} 完成压缩，原始上下文保存在编号为 "
            f"{info.id} 的归档文件中。如需查找历史信息，请使用 recallContext 工具。"
        )
        self.replace_history(summary, note)

        # 4. 重置监控：新上下文重新估算，解除阈值阻断
        self._monitor.estimate_from_messages(self._messages)
        self._monitor.warned = False
        return CompactOutcome(
            ok=True,
            archive_id=info.id,
            message_count=info.message_count,
            summary_tokens=estimate_tokens(summary),
        )

    def replace_history(self, summary: str, archive_note: str) -> None:
        """用压缩摘要替换全部非 system 历史消息，保留 System Prompt。"""
        system_messages = [m for m in self._messages if m.get("role") == "system"]
        compacted = {
            "role": "user",
            "content": f"[上下文压缩摘要]\n\n{summary}\n\n---\n{archive_note}",
        }
        self._messages = [*system_messages, compacted]
