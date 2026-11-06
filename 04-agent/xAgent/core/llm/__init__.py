"""LLM 适配层：定义统一接口并提供 OpenAI 兼容实现。"""

from core.llm.base import ChatChunk, ChatClient, ToolCallDelta
from core.llm.openai_client import OpenAIChatClient

__all__ = ["ChatChunk", "ChatClient", "OpenAIChatClient", "ToolCallDelta"]
