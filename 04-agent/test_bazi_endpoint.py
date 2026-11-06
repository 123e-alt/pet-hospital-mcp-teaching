# -*- coding: utf-8 -*-
"""验证新 Bazi MCP 端点连通性（模拟从 D:\\reports 启动）。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, r"c:\Users\qq\Desktop\LLM\04-agent\xAgent")

from core.mcp import AsyncMCPClient, MCPConfig

async def main() -> int:
    cfg = MCPConfig.load(Path(r"D:\reports\.mcp.json"))
    client = AsyncMCPClient(retries=1, retry_backoff=0.5, connect_timeout=20.0)
    try:
        results = await client.connect_all(list(cfg.servers.values()))
        print("connect results:", results)
        if client.is_available and results and results[0][1] is None:
            tools = await client.list_tools()
            print("tools:", [t.name for t in tools])
            return 0
        return 1
    finally:
        try:
            await client.close()
        except Exception:
            pass

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
