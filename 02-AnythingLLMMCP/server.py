import os
import sys

import httpx
from mcp.server.mcpserver import MCPServer

BASE_URL = os.getenv("ANYTHINGLLM_BASE_URL", "http://localhost:3001").rstrip("/")
API_KEY = os.getenv("ANYTHINGLLM_API_KEY")
if not API_KEY:
    sys.exit("请先设置环境变量 ANYTHINGLLM_API_KEY（AnythingLLM 生成的 API Key）")
HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8000"))

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def _first_workspace_slug() -> str:
    r = httpx.get(f"{BASE_URL}/api/v1/workspaces", headers=HEADERS, timeout=10.0)
    r.raise_for_status()
    wss = (r.json() or {}).get("workspaces") or []
    if not wss:
        sys.exit("AnythingLLM 中没有可用工作区")
    slug = wss[0].get("slug")
    if not slug:
        sys.exit("AnythingLLM 第一个工作区缺少 slug")
    return slug


SLUG = _first_workspace_slug()

mcp = MCPServer(
    name="AnythingLLM",
    instructions="通过 AnythingLLM 第一个工作区进行基于文档的 RAG 问答。",
)


@mcp.tool(
    name="ask_anythingllm",
    description="向 AnythingLLM 第一个工作区提问，基于该工作区已索引的文档进行 RAG 检索并返回 AI 回答。",
)
def ask_anythingllm(question: str) -> str:
    """question: 要向工作区提出的自然语言问题"""
    r = httpx.post(
        f"{BASE_URL}/api/v1/workspace/{SLUG}/chat",
        headers=HEADERS,
        json={"message": question, "mode": "chat"},
        timeout=120.0,
    )
    r.raise_for_status()
    text = (r.json() or {}).get("textResponse")
    if not text:
        raise ValueError("AnythingLLM 未返回 textResponse")
    return text


if __name__ == "__main__":
    print(f"[mcp-anythingllm] workspace slug = {SLUG}", flush=True)
    print(f"[mcp-anythingllm] listening http://{HOST}:{PORT}/mcp", flush=True)
    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        streamable_http_path="/mcp",
    )
