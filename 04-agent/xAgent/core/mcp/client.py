"""MCP 客户端：建立连接、枚举工具、转发调用。

使用 mcp SDK 的高层 ``Client`` 类——它把 transport、JSON-RPC dispatcher、
initialize/discover 握手全部封装在一个 async context manager 里。

**事件循环约束（关键）**：``Client`` 内部的 anyio TaskGroup 绑定在创建它的
事件循环（以及创建它的 task）上。因此 ``connect_all()``、``call_tool()``、
``close()`` 必须在**同一个** asyncio 事件循环里执行；一旦跨循环使用，
会话会立即失效并报 ``MCPError: Connection closed``。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from core.mcp.config import MCPServerConfig
from core.mcp.log import get_logger

# --- 延迟导入，避免 MCP SDK 缺失时 core 本身无法 import ---
try:  # pragma: no cover - 运行期依赖
    from mcp.client import Client as _MCPClient
    from mcp.client.stdio import StdioServerParameters as _StdioParams
    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover - 开发环境无 mcp SDK 时降级
    _MCPClient = None  # type: ignore[assignment]
    _StdioParams = None  # type: ignore[assignment]
    _MCP_AVAILABLE = False

logger = get_logger()


class MCPClientError(RuntimeError):
    """MCP 客户端所有错误的统一基类。"""


@dataclass
class ServerSession:
    """单个 MCP Server 的已建立连接。"""

    name: str
    client: Any  # mcp.client.Client（高层客户端对象）
    # 暴露给 LLM 的名字 → McpTool（原始对象，含 input_schema / description）
    raw_tools: dict[str, Any] = field(default_factory=dict)


class AsyncMCPClient:
    """管理多个 MCP Server 的客户端集合。

    用法::

        client = AsyncMCPClient()
        await client.connect_all(configs)
        content, is_err = await client.call_tool("Bazi-MCP__getChineseCalendar", {})
        await client.close()

    命名约定：暴露给 LLM 的工具名 = ``{server_name}__{mcp_tool_name}``
    （双下划线分隔），避免不同 server 之间重名。

    重试策略：``call_tool`` 失败时按 ``retry_backoff * attempt`` 线性退避，
    重连该 server 后重试，最多 ``retries`` 次；全部失败才把错误文本回写给模型。
    """

    def __init__(
        self,
        *,
        retries: int = 2,
        retry_backoff: float = 1.0,
        call_timeout: float = 60.0,
        connect_timeout: float = 30.0,
    ) -> None:
        self._sessions: dict[str, ServerSession] = {}
        # 暴露名 → (server_name, mcp 原始工具名)
        self._tool_map: dict[str, tuple[str, str]] = {}
        # server 名 → 原始配置（重连时复用）
        self._configs: dict[str, MCPServerConfig] = {}
        self._lock = asyncio.Lock()
        self._retries = max(0, retries)
        self._retry_backoff = max(0.0, retry_backoff)
        self._call_timeout = call_timeout
        self._connect_timeout = connect_timeout

    # ---------- 连接 ----------

    @property
    def is_available(self) -> bool:
        return _MCP_AVAILABLE

    async def connect_all(
        self, configs: list[MCPServerConfig]
    ) -> list[tuple[str, str | None]]:
        """连接所有 server，每个 server 的错误被隔离。"""
        results: list[tuple[str, str | None]] = []
        for cfg in configs:
            self._configs[cfg.name] = cfg
            err = await self._connect_one(cfg)
            results.append((cfg.name, err))
        return results

    async def _connect_one(self, cfg: MCPServerConfig) -> str | None:
        """连接单个 server；成功返回 None，失败返回可展示的错误信息。"""
        if not _MCP_AVAILABLE:
            return "mcp Python SDK 未安装，请执行 `pip install mcp`"

        started = time.monotonic()
        try:
            client = await asyncio.wait_for(
                self._open_client(cfg), timeout=self._connect_timeout
            )
            result = await asyncio.wait_for(
                client.list_tools(), timeout=self._connect_timeout
            )
        except Exception as exc:
            detail = _format_exception(exc)
            logger.error(
                "connect server=%s type=%s target=%s FAILED in %.0fms: %s",
                cfg.name, cfg.type, _target_of(cfg),
                (time.monotonic() - started) * 1000, detail,
            )
            return detail

        raw_tools = self._register_names(cfg, result.tools)
        self._sessions[cfg.name] = ServerSession(
            name=cfg.name, client=client, raw_tools=raw_tools
        )
        logger.info(
            "connect server=%s type=%s target=%s OK in %.0fms, tools=%s",
            cfg.name, cfg.type, _target_of(cfg),
            (time.monotonic() - started) * 1000,
            [t.name for t in result.tools],
        )
        return None

    def _register_names(self, cfg: MCPServerConfig, tools: Any) -> dict[str, Any]:
        """把 server 的原始工具表映射为「暴露名 → McpTool」。"""
        raw_tools: dict[str, Any] = {}
        for t in tools:
            exposed = f"{cfg.name}__{t.name}"
            final = exposed
            i = 2
            while final in self._tool_map:
                final = f"{exposed}_{i}"
                i += 1
            self._tool_map[final] = (cfg.name, t.name)
            raw_tools[final] = t
        return raw_tools

    async def _open_client(self, cfg: MCPServerConfig) -> Any:
        """根据 config.type 打开高层 mcp Client（无超时，由调用方包 wait_for）。"""
        if cfg.type == "streamable_http":
            assert cfg.url is not None
            target: Any = cfg.url
        elif cfg.type == "stdio":
            assert cfg.command is not None
            target = _StdioParams(
                command=cfg.command,
                args=list(cfg.args),
                env=cfg.env,
            )
        else:
            raise MCPClientError(f"不支持的传输类型：{cfg.type}")

        client = _MCPClient(target)
        await client.__aenter__()
        return client

    async def _reconnect(self, server_name: str) -> str | None:
        """关闭旧连接并按原配置重建；成功返回 None，失败返回错误文本。"""
        cfg = self._configs.get(server_name)
        if cfg is None:
            return f"缺少 server「{server_name}」的配置，无法重连"

        old = self._sessions.pop(server_name, None)
        if old is not None:
            try:
                await asyncio.wait_for(
                    old.client.__aexit__(None, None, None), timeout=10.0
                )
            except Exception as exc:
                # 旧连接可能已经处于异常状态，关闭失败不影响重建
                logger.debug(
                    "reconnect close server=%s ignored: %s",
                    server_name, _format_exception(exc),
                )

        started = time.monotonic()
        try:
            client = await asyncio.wait_for(
                self._open_client(cfg), timeout=self._connect_timeout
            )
            result = await asyncio.wait_for(
                client.list_tools(), timeout=self._connect_timeout
            )
        except Exception as exc:
            detail = _format_exception(exc)
            logger.error(
                "reconnect server=%s FAILED in %.0fms: %s",
                server_name, (time.monotonic() - started) * 1000, detail,
            )
            return detail

        # 复用已有的暴露名，保证 registry 里已注册的 Tool 名字仍然有效
        existing = {e: orig for e, (srv, orig) in self._tool_map.items() if srv == server_name}
        raw_tools: dict[str, Any] = {}
        for t in result.tools:
            exposed = next(
                (e for e, orig in existing.items() if orig == t.name),
                f"{server_name}__{t.name}",
            )
            self._tool_map.setdefault(exposed, (server_name, t.name))
            raw_tools[exposed] = t

        added = set(raw_tools) - set(existing)
        if added:
            logger.warning(
                "reconnect server=%s 出现新增工具 %s（需重启 xAgent 才会注册为 Function Calling）",
                server_name, sorted(added),
            )

        self._sessions[server_name] = ServerSession(
            name=server_name, client=client, raw_tools=raw_tools
        )
        logger.info(
            "reconnect server=%s OK in %.0fms",
            server_name, (time.monotonic() - started) * 1000,
        )
        return None

    # ---------- 枚举与调用 ----------

    def exposed_to_original(self, exposed_name: str) -> tuple[str, str] | None:
        return self._tool_map.get(exposed_name)

    def all_raw_tools(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for ss in self._sessions.values():
            out.update(ss.raw_tools)
        return out

    def server_names(self) -> list[str]:
        return list(self._sessions)

    async def call_tool(
        self, exposed_name: str, arguments: dict[str, Any] | None
    ) -> tuple[str, bool]:
        """转发工具调用，失败自动重连并重试。返回 ``(文本结果, is_error)``。"""
        mapping = self._tool_map.get(exposed_name)
        if mapping is None:
            return f"错误：未知的 MCP 工具 {exposed_name}", True

        server_name, original_name = mapping
        attempts = self._retries + 1
        last_error = ""

        for attempt in range(1, attempts + 1):
            ss = self._sessions.get(server_name)
            if ss is None:
                last_error = f"MCP Server「{server_name}」未连接"
            else:
                started = time.monotonic()
                try:
                    result = await asyncio.wait_for(
                        ss.client.call_tool(
                            original_name,
                            arguments or {},
                            read_timeout_seconds=self._call_timeout,
                        ),
                        timeout=self._call_timeout,
                    )
                    logger.info(
                        "call tool=%s server=%s attempt=%d/%d OK in %.0fms isError=%s",
                        exposed_name, server_name, attempt, attempts,
                        (time.monotonic() - started) * 1000,
                        bool(getattr(result, "isError", False)),
                    )
                    return (
                        _render_mcp_result(result),
                        bool(getattr(result, "isError", False)),
                    )
                except Exception as exc:
                    last_error = _format_exception(exc)
                    logger.warning(
                        "call tool=%s server=%s attempt=%d/%d FAILED in %.0fms: %s",
                        exposed_name, server_name, attempt, attempts,
                        (time.monotonic() - started) * 1000, last_error,
                    )

            if attempt >= attempts:
                break

            # 退避 → 重连 → 下一轮重试
            delay = self._retry_backoff * attempt
            logger.info(
                "retry tool=%s in %.1fs (attempt %d/%d)",
                exposed_name, delay, attempt, attempts,
            )
            await asyncio.sleep(delay)
            reconnect_error = await self._reconnect(server_name)
            if reconnect_error is not None:
                last_error = f"{last_error}；重连失败：{reconnect_error}"

        logger.error(
            "call tool=%s server=%s GAVE UP after %d attempt(s): %s",
            exposed_name, server_name, attempts, last_error,
        )
        return (
            f"错误：MCP 调用失败（已重试 {attempts - 1} 次）- {last_error}",
            True,
        )

    # ---------- 生命周期 ----------

    async def close(self) -> None:
        """关闭所有连接（幂等）。必须在建立连接时的同一事件循环里调用。"""
        async with self._lock:
            for ss in list(self._sessions.values()):
                try:
                    await asyncio.wait_for(
                        ss.client.__aexit__(None, None, None), timeout=10.0
                    )
                    logger.info("close server=%s OK", ss.name)
                except Exception as exc:
                    logger.debug(
                        "close server=%s ignored: %s",
                        ss.name, _format_exception(exc),
                    )
            self._sessions.clear()
            self._tool_map.clear()
            self._configs.clear()


# ---------- 辅助函数 ----------


def _target_of(cfg: MCPServerConfig) -> str:
    return cfg.url or f"{cfg.command} {' '.join(cfg.args)}".strip()


def _format_exception(exc: BaseException) -> str:
    """把异常转成稳定、可展示的文本。

    递归展开 ``ExceptionGroup``（mcp SDK 在 anyio/TaskGroup 里抛出的连接错误
    往往被 ExceptionGroup 包一层），取最内层的 HTTP/network 信息。
    """
    parts: list[str] = []
    seen: set[int] = set()

    def walk(e: BaseException, depth: int = 0) -> None:
        if id(e) in seen or depth > 3:
            return
        seen.add(id(e))
        msg = str(e).strip()
        head = f"{type(e).__name__}"
        if msg:
            head += f": {msg}"
        parts.append(head)
        if hasattr(e, "exceptions"):
            for sub in getattr(e, "exceptions", ()):
                walk(sub, depth + 1)
        for attr in ("__cause__", "__context__"):
            sub = getattr(e, attr, None)
            if sub is not None:
                walk(sub, depth + 1)

    walk(exc)
    unique: list[str] = []
    for p in parts:
        if p not in unique:
            unique.append(p)
    return " → ".join(unique[:3])


def _render_mcp_result(result: Any) -> str:
    """把 mcp.types.CallToolResult 渲染成模型可读的文本。"""
    content_list = getattr(result, "content", None) or []
    if not content_list:
        return "(空结果)"

    chunks: list[str] = []
    for item in content_list:
        kind = getattr(item, "type", None)
        if kind == "text":
            chunks.append(getattr(item, "text", "") or "")
        elif kind == "image":
            mime = getattr(item, "mimeType", "image")
            data = getattr(item, "data", "") or ""
            chunks.append(f"[{mime} image, {len(data)} bytes]")
        elif kind == "resource":
            res = getattr(item, "resource", None)
            if res is not None:
                chunks.append(
                    f"[resource {getattr(res, 'uri', '?')} "
                    f"{getattr(res, 'mimeType', '')}]"
                )
        else:
            try:
                chunks.append(json.dumps(item, ensure_ascii=False))
            except TypeError:
                chunks.append(str(item))

    text = "\n".join(chunks).strip()
    return text or "(空结果)"
