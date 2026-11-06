"""工具注册表：工具的唯一登记与执行入口。"""

from __future__ import annotations

import inspect
import json

from core.tools.base import Tool, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, *tools: Tool) -> None:
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"工具重复注册：{tool.name}")
            self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    async def execute(self, name: str, raw_arguments: str) -> ToolResult:
        """执行工具；任何异常都转成文本结果回写给模型，避免中断会话。

        同步 handler 会放到线程池里跑（避免阻塞事件循环），
        异步 handler 会直接 await（供 MCP 等网络工具使用）。
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(f"未知的工具：{name}", ok=False)

        try:
            kwargs = json.loads(raw_arguments) if raw_arguments.strip() else {}
        except json.JSONDecodeError as exc:
            return ToolResult(f"错误：工具参数不是合法 JSON - {exc}", ok=False)

        if not isinstance(kwargs, dict):
            return ToolResult("错误：工具参数必须是 JSON 对象", ok=False)

        try:
            inspect.signature(tool.handler).bind(**kwargs)
        except TypeError as exc:
            return ToolResult(f"错误：工具参数不匹配 - {exc}", ok=False)

        try:
            if inspect.iscoroutinefunction(tool.handler):
                result = await tool.handler(**kwargs)
            else:
                import asyncio
                result = await asyncio.to_thread(tool.handler, **kwargs)
        except Exception as exc:  # 工具内部失败不应打断整轮对话
            return ToolResult(f"错误：工具执行失败 - {exc}", ok=False)

        # 结果归一化：字符串直接用，其他转 JSON 字符串
        if isinstance(result, ToolResult):
            return result
        if isinstance(result, str):
            return ToolResult(result)
        try:
            return ToolResult(json.dumps(result, ensure_ascii=False, indent=2))
        except TypeError:
            return ToolResult(str(result))
