"""core 与所有前端之间的唯一通信契约。

前端只消费这里定义的事件，不直接访问 LLM 客户端或工具实现；
内核也不引用任何前端类型。新增 Web / 桌面 / 移动端时复用同一套事件。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextDelta:
    """模型流式输出的一个文本片段。"""

    text: str


@dataclass(frozen=True)
class ToolCallStarted:
    """模型请求调用工具，arguments 为聚合完成的原始 JSON 字符串。"""

    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolCallFinished:
    """工具执行结束，result 为回写给模型的文本。"""

    call_id: str
    name: str
    result: str
    ok: bool = True


@dataclass(frozen=True)
class ErrorOccurred:
    """本回合中需要展示给用户的错误。"""

    message: str


@dataclass(frozen=True)
class TurnCompleted:
    """一次用户输入对应的完整回合结束。"""

    reply: str
    tool_call_count: int


AgentEvent = (
    TextDelta | ToolCallStarted | ToolCallFinished | ErrorOccurred | TurnCompleted
)
