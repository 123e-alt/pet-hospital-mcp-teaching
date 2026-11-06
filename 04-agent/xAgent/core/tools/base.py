"""工具抽象：统一描述一个可被模型调用的工具及其返回值。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ToolResult:
    """工具执行结果。ok=False 表示执行失败（内容仍会回写给模型）。"""

    content: str
    ok: bool = True


ToolHandler = Callable[..., Any]


@dataclass(frozen=True)
class Tool:
    """一个可调用的工具：元数据 + JSON Schema + 处理函数。"""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler = field(repr=False)

    def to_openai_schema(self) -> dict[str, Any]:
        """转换为 OpenAI function calling 所需的 schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
