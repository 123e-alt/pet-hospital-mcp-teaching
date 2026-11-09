"""AnythingLLM MCP Server.

把 AnythingLLM 的工作区管理、文档上传/向量化、RAG 问答三类能力
封装成 MCP 工具，供任意 MCP 客户端（Claude Desktop / xAgent 等）调用。

配置（全部经环境变量注入，不落盘、不硬编码）：
    ANYTHINGLLM_API_KEY   必填，AnythingLLM 设置页生成的 API Key
    ANYTHINGLLM_BASE_URL  可选，默认 http://localhost:3001
    ANYTHINGLLM_WORKSPACE 可选，默认工作区 slug；留空 = 自动取第一个工作区
    MCP_HOST / MCP_PORT   可选，MCP 监听地址，默认 127.0.0.1:8000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer

BASE_URL = os.getenv("ANYTHINGLLM_BASE_URL", "http://localhost:3001").rstrip("/")
API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "").strip()
if not API_KEY:
    sys.exit(
        "[配置错误] 缺少环境变量 ANYTHINGLLM_API_KEY。\n"
        "请在 AnythingLLM 设置页 -> API Keys 生成 Key 后，设置该环境变量再启动。"
    )
DEFAULT_WORKSPACE = os.getenv("ANYTHINGLLM_WORKSPACE", "").strip()
HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8000"))

_client = httpx.Client(
    base_url=f"{BASE_URL}/api/v1",
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=httpx.Timeout(30.0, read=120.0),
)

mcp = MCPServer(
    name="AnythingLLM",
    instructions=(
        "AnythingLLM 工作区与文档管理、RAG 问答。"
        "工作区相关工具的 workspace 参数留空时，默认使用 "
        + (f"配置的工作区「{DEFAULT_WORKSPACE}」。" if DEFAULT_WORKSPACE else "AnythingLLM 的第一个工作区。")
    ),
)

_slug_cache: dict[str, str] = {}


def _req(method: str, path: str, **kwargs) -> dict:
    """统一请求入口：把网络/HTTP 错误转成清晰的报错信息。"""
    try:
        r = _client.request(method, path, **kwargs)
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"无法连接 AnythingLLM（{BASE_URL}）。请确认服务已启动、ANYTHINGLLM_BASE_URL 配置正确。"
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"请求 AnythingLLM 超时：{exc}") from exc
    if r.status_code == 401:
        raise RuntimeError("AnythingLLM 鉴权失败（401）：ANYTHINGLLM_API_KEY 无效或已删除。")
    if r.status_code == 403:
        raise RuntimeError("AnythingLLM 拒绝访问（403）：该 API Key 没有执行此操作的权限。")
    if r.status_code >= 400:
        raise RuntimeError(f"AnythingLLM API 返回 {r.status_code}：{r.text[:300]}")
    return r.json() or {}


def _resolve_slug(workspace: str | None = None) -> str:
    """惰性解析工作区 slug：指定 > 环境变量 > 第一个工作区，结果缓存。

    不在启动时请求，保证 AnythingLLM 未启动时工具仍可被客户端枚举；
    真正调用时才报「连不上」的错。
    """
    slug = (workspace or "").strip() or DEFAULT_WORKSPACE
    if slug:
        return slug
    if "_default" not in _slug_cache:
        wss = _req("GET", "/workspaces").get("workspaces") or []
        if not wss:
            raise RuntimeError(
                "AnythingLLM 中没有任何工作区。请先创建工作区（可用 create_workspace 工具），"
                "或设置 ANYTHINGLLM_WORKSPACE 指定已有工作区。"
            )
        _slug_cache["_default"] = wss[0]["slug"]
    return _slug_cache["_default"]


# ---------- 类别一：工作区管理 ----------


@mcp.tool(
    name="list_workspaces",
    description="列出 AnythingLLM 中所有工作区（名称、slug、文档数量）。",
)
def list_workspaces() -> str:
    wss = _req("GET", "/workspaces").get("workspaces") or []
    if not wss:
        return "当前没有任何工作区。"
    lines = [
        f"- {w.get('name')}（slug: {w.get('slug')}）"
        for w in wss
    ]
    return "工作区列表：\n" + "\n".join(lines)


@mcp.tool(
    name="create_workspace",
    description="在 AnythingLLM 中新建一个工作区，返回其 slug。",
)
def create_workspace(name: str) -> str:
    """name: 新工作区的名称"""
    name = name.strip()
    if not name:
        raise ValueError("工作区名称不能为空")
    data = _req("POST", "/workspace/new", json={"name": name})
    ws = data.get("workspace") or {}
    slug = ws.get("slug")
    if not slug:
        raise RuntimeError(f"创建工作区未返回 slug：{data}")
    _slug_cache["_default"] = _slug_cache.get("_default") or slug
    return f"工作区已创建：{ws.get('name')}（slug: {slug}）"


# ---------- 类别二：文档上传 / 向量化 ----------


@mcp.tool(
    name="list_documents",
    description="列出 AnythingLLM 已上传的全部文档（按目录分组，含向量化所需的路径）。",
)
def list_documents() -> str:
    data = _req("GET", "/documents")
    files = (data.get("localFiles") or {}).get("items") or []
    if not files:
        return "尚未上传任何文档。"
    lines: list[str] = []

    def _walk(items, prefix: str = "") -> None:
        for it in items:
            if it.get("type") == "folder":
                _walk(it.get("items") or [], prefix + it.get("name", "") + "/")
            else:
                lines.append(f"- {prefix}{it.get('name')}（路径: {it.get('id') or it.get('location', '?')}）")

    _walk(files)
    return "文档列表：\n" + "\n".join(lines)


@mcp.tool(
    name="upload_document",
    description="把本地文件上传到 AnythingLLM（PDF/TXT/MD/DOCX 等）。返回文档路径，需再用 add_document_to_workspace 向量化后才能在问答中检索到。",
)
def upload_document(file_path: str) -> str:
    """file_path: 本地文件的绝对路径"""
    p = Path(file_path)
    if not p.is_file():
        raise ValueError(f"文件不存在：{file_path}")
    with p.open("rb") as f:
        data = _req("POST", "/document/upload", files={"file": (p.name, f)})
    if not data.get("success", True):
        raise RuntimeError(f"上传失败：{data.get('error') or data}")
    docs = data.get("documents") or []
    if not docs:
        raise RuntimeError("上传响应中没有文档信息")
    loc = docs[0].get("location", "?")
    return (
        f"已上传：{p.name} → {loc}\n"
        f"下一步：调用 add_document_to_workspace(doc_path=\"{loc}\") 将其向量化到工作区。"
    )


@mcp.tool(
    name="add_document_to_workspace",
    description="把已上传的文档加入工作区并触发向量化（embedding），之后该工作区的问答即可检索到此文档。",
)
def add_document_to_workspace(doc_path: str, workspace: str = "") -> str:
    """doc_path: upload_document 返回的文档路径（形如 custom-documents/xxx.json）
    workspace: 目标工作区 slug，留空用默认工作区"""
    slug = _resolve_slug(workspace)
    data = _req(
        "POST",
        f"/workspace/{slug}/update-embeddings",
        json={"adds": [doc_path], "deletes": []},
    )
    ws = data.get("workspace") or {}
    docs = ws.get("documents") or []
    return f"文档已向量化到工作区「{slug}」（该工作区现有 {len(docs)} 篇文档）。"


# ---------- 类别三：对话 / 检索问答 ----------


@mcp.tool(
    name="ask_anythingllm",
    description="向 AnythingLLM 工作区提问，基于该工作区已向量化的文档进行 RAG 检索并返回答案与引用来源。",
)
def ask_anythingllm(question: str, workspace: str = "") -> str:
    """question: 自然语言问题
    workspace: 目标工作区 slug，留空用默认工作区"""
    question = question.strip()
    if not question:
        raise ValueError("问题不能为空")
    slug = _resolve_slug(workspace)
    data = _req(
        "POST",
        f"/workspace/{slug}/chat",
        json={"message": question, "mode": "chat"},
    )
    text = (data.get("textResponse") or "").strip()
    if not text:
        raise RuntimeError(f"AnythingLLM 未返回答案：{data}")
    sources = data.get("sources") or []
    if sources:
        titles = sorted({s.get("title", "?") for s in sources})
        text += "\n\n来源文档：" + "、".join(titles)
    return text


if __name__ == "__main__":
    print(f"[mcp-anythingllm] AnythingLLM = {BASE_URL}", flush=True)
    print(
        f"[mcp-anythingllm] workspace = {DEFAULT_WORKSPACE or '（自动取第一个，调用时解析）'}",
        flush=True,
    )
    print(f"[mcp-anythingllm] listening http://{HOST}:{PORT}/mcp", flush=True)
    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        streamable_http_path="/mcp",
    )
