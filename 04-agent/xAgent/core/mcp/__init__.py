"""MCP 客户端子模块。

- ``config.MCPConfig`` / ``MCPServerConfig``：.mcp.json 读取与校验
- ``client.AsyncMCPClient``：多 server 连接管理、工具转发
- ``toolkit.build_mcp_tools``：把 ``AsyncMCPClient`` 转成 xAgent Tool 列表
"""

from core.mcp.config import MCPConfig, MCPServerConfig
from core.mcp.client import AsyncMCPClient, MCPClientError
from core.mcp.toolkit import build_mcp_tools

__all__ = [
    "AsyncMCPClient",
    "MCPClientError",
    "MCPServerConfig",
    "MCPConfig",
    "build_mcp_tools",
]
