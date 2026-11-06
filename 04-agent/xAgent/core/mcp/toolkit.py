"""把 ``AsyncMCPClient`` 的工具注册为 xAgent 的 ``Tool``。

核心思路：连接完成后，由 ``client.all_raw_tools()`` 一次性拿到
所有 ``{exposed_name: mcp.types.Tool}`` 映射，为每个工具构造一个
异步 handler，handler 内部调用 ``client.call_tool`` 并把结果转成
``ToolResult``。
"""

from __future__ import annotations

from typing import Any

from core.mcp.client import AsyncMCPClient
from core.tools.base import Tool, ToolResult


def _async_tool_factory(
    client: AsyncMCPClient, exposed_name: str, original_name: str
):
    """闭包：为单个 MCP 工具生成一个异步 handler。

    handler 接收任意 kwargs（由 LLM 按 inputSchema 填），转发给
    MCP Server 并返回 ``ToolResult``。
    """

    async def handler(**kwargs: Any) -> ToolResult:
        content, is_error = await client.call_tool(exposed_name, kwargs)
        return ToolResult(content, ok=not is_error)

    handler.__name__ = f"mcp_{exposed_name.replace('__', '_')}"
    handler.__qualname__ = handler.__name__
    return handler


def build_mcp_tools(client: AsyncMCPClient) -> list[Tool]:
    """从已连接的 ``AsyncMCPClient`` 构造所有 MCP 工具的 ``Tool`` 列表。"""
    tools: list[Tool] = []
    for exposed_name, mcp_tool in client.all_raw_tools().items():
        original_name = client.exposed_to_original(exposed_name)
        if original_name is None:
            continue
        server_name, orig = original_name

        # input_schema 可能是 pydantic 模型或 dict
        input_schema_obj = getattr(mcp_tool, "input_schema", None)
        if input_schema_obj is None:
            parameters: dict[str, Any] = {"type": "object", "properties": {}}
        elif isinstance(input_schema_obj, dict):
            parameters = input_schema_obj
        else:
            parameters = input_schema_obj.model_dump()

        desc = (getattr(mcp_tool, "description", "") or "").strip()
        if desc:
            full_desc = f"[MCP · {server_name}] {desc}"
        else:
            full_desc = f"[MCP · {server_name}] （{orig}）"

        handler = _async_tool_factory(client, exposed_name, orig)
        tools.append(
            Tool(
                name=exposed_name,
                description=full_desc,
                parameters=parameters,
                handler=handler,
            )
        )
    return tools
