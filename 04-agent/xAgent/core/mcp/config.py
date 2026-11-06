"""MCP 客户端配置加载与校验。

约定：读取项目启动目录下的 ``.mcp.json``，格式类似 Claude Desktop：

.. code-block:: json

    {
      "mcpServers": {
        "Bazi-MCP": {
          "type": "streamable_http",
          "url": "https://..."
        },
        "local-calc": {
          "type": "stdio",
          "command": "node",
          "args": ["calc-mcp-server.js"]
        }
      }
    }

本模块只负责「把 JSON 映射成已校验的 dataclass」，不处理连接。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, final


TransportType = Literal["streamable_http", "http", "stdio"]


@dataclass(frozen=True)
class MCPServerConfig:
    """单个 MCP Server 的连接参数。"""

    name: str
    type: TransportType
    # streamable_http / http
    url: str | None = None
    headers: dict[str, str] | None = None
    # stdio
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.type in ("streamable_http", "http") and not self.url:
            raise ValueError(f"MCP Server「{self.name}」缺少 url")
        if self.type == "stdio" and not self.command:
            raise ValueError(f"MCP Server「{self.name}」缺少 command")


@final
class MCPConfig:
    """汇总所有 MCP Server 配置。"""

    def __init__(self, servers: dict[str, MCPServerConfig]) -> None:
        self._servers = dict(servers)

    @property
    def servers(self) -> dict[str, MCPServerConfig]:
        return dict(self._servers)

    def __len__(self) -> int:
        return len(self._servers)

    def __getitem__(self, name: str) -> MCPServerConfig:
        return self._servers[name]

    def __iter__(self):
        return iter(self._servers)

    @classmethod
    def load(cls, path: Path) -> "MCPConfig | None":
        """读取并解析 ``.mcp.json``；文件不存在返回 ``None``，坏配置抛 ``ValueError``。"""
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f".mcp.json 读取失败：{exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError(".mcp.json 顶层必须是对象")

        servers_raw = raw.get("mcpServers")
        if servers_raw is None:
            return cls({})
        if not isinstance(servers_raw, dict):
            raise ValueError(".mcp.json 的 mcpServers 必须是对象")

        built: dict[str, MCPServerConfig] = {}
        for name, item in servers_raw.items():
            if not isinstance(item, dict):
                raise ValueError(f"MCP Server「{name}」配置必须是对象")
            transport = str(item.get("type", "streamable_http")).lower()
            if transport == "sse":
                # 旧版 sse 统一归到 streamable_http
                transport = "streamable_http"
            if transport not in ("streamable_http", "stdio", "http"):
                raise ValueError(
                    f"MCP Server「{name}」type 不支持：{transport}（仅 streamable_http / stdio）"
                )
            cfg = MCPServerConfig(
                name=name,
                type=transport,
                url=item.get("url"),
                headers=item.get("headers"),
                command=item.get("command"),
                args=tuple(item.get("args") or ()),
                env=item.get("env"),
            )
            built[name] = cfg
        return cls(built)
