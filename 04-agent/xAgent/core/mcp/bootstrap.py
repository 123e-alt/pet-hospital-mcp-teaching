"""MCP 启动引导：加载 .mcp.json → 连接 server → 注册工具。

独立于 main.py 存在，这样 TUI 也能在界面启动后异步调用同一份逻辑
（先进入界面，MCP 后台连接，完成后动态刷新边栏与状态栏）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from core.agent.session import AgentSession
from core.mcp import AsyncMCPClient, MCPConfig, build_mcp_tools
from core.mcp import log as mcp_log
from core.tools import ToolRegistry

McpStatus = Literal[
    "disabled", "not_configured", "sdk_missing", "loading",
    "all_ok", "partial_ok", "all_fail", "internal_error",
]


@dataclass
class MCPInitReport:
    """MCP 初始化结果（结构化，用于前端展示）。"""

    status: McpStatus
    cwd: Path
    config_path: Path
    connected: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    note: str = ""

    def server_tools(self, registry: ToolRegistry) -> dict[str, list[str]]:
        """从注册表导出 {server 名: [暴露给 LLM 的工具名]}，供边栏显示。"""
        by_server: dict[str, list[str]] = {}
        for schema in registry.schemas():
            name = schema["function"]["name"]
            if "__" in name and name not in ("recallContext",):
                server = name.split("__", 1)[0]
                by_server.setdefault(server, []).append(name)
        return by_server


async def attach_mcp(
    session: AgentSession,
    project_root: Path,
    *,
    enabled: bool = True,
    retries: int = 2,
    retry_backoff: float = 1.0,
    call_timeout: float = 60.0,
    connect_timeout: float = 30.0,
    fallback_config_path: Path | None = None,
) -> tuple[AsyncMCPClient | None, MCPInitReport]:
    """加载 .mcp.json → 连接所有 server → 注册工具到 session.tools。

    **必须运行在最终使用这些连接的那个事件循环里**：mcp SDK 的
    Client 内部 TaskGroup 绑定在创建它的事件循环上，换循环会立刻
    ``MCPError: Connection closed``。

    配置查找顺序：``<project_root>/.mcp.json`` → ``fallback_config_path``
    （通常是源码目录的默认配置）。
    """
    config_path = project_root / ".mcp.json"
    logger = mcp_log.get_logger()

    if not enabled:
        return None, MCPInitReport(
            status="disabled", cwd=project_root, config_path=config_path,
            note="已在 config.ini 的 [MCP] 段关闭",
        )

    mcp_cfg = MCPConfig.load(config_path)
    if (mcp_cfg is None or len(mcp_cfg) == 0) and fallback_config_path is not None \
            and fallback_config_path != config_path:
        # 启动目录没有配置时，回退到源码目录的默认 .mcp.json
        fallback_cfg = MCPConfig.load(fallback_config_path)
        if fallback_cfg is not None and len(fallback_cfg) > 0:
            mcp_cfg = fallback_cfg
            config_path = fallback_config_path
            logger.info("MCP 配置回退：使用 %s", fallback_config_path)
    if mcp_cfg is None or len(mcp_cfg) == 0:
        checked = [config_path]
        if fallback_config_path is not None and fallback_config_path != config_path:
            checked.append(fallback_config_path)
        return None, MCPInitReport(
            status="not_configured", cwd=project_root, config_path=config_path,
            note="未找到 .mcp.json 或其中无 server（已查 " + " 与 ".join(map(str, checked)) + "）",
        )

    # 双份配置防护：启动目录与源码目录都存在 .mcp.json 且内容不一致时，
    # 启动目录版本静默生效——主动告警，避免「改了源码目录配置却不生效」。
    conflict_note = ""
    if config_path != fallback_config_path and fallback_config_path is not None:
        conflict_note = _detect_config_conflict(config_path, fallback_config_path)
        if conflict_note:
            logger.warning(conflict_note)

    client = AsyncMCPClient(
        retries=retries,
        retry_backoff=retry_backoff,
        call_timeout=call_timeout,
        connect_timeout=connect_timeout,
    )
    if not client.is_available:
        note = "mcp Python SDK 未安装，请执行 `pip install mcp`"
        logger.error(note)
        return None, MCPInitReport(
            status="sdk_missing", cwd=project_root, config_path=config_path,
            note=note,
        )

    try:
        results = await client.connect_all(list(mcp_cfg.servers.values()))
    except Exception as exc:
        note = f"初始化阶段抛出异常：{type(exc).__name__}: {exc}"
        logger.exception("connect_all 异常")
        return None, MCPInitReport(
            status="internal_error", cwd=project_root, config_path=config_path,
            note=note,
        )
    connected: list[str] = []
    failed: list[tuple[str, str]] = []
    for name, err in results:
        if err is None:
            connected.append(name)
        else:
            failed.append((name, err))

    if connected:
        for t in build_mcp_tools(client):
            try:
                session.tools.register(t)
            except ValueError as exc:
                logger.warning("工具注册跳过：%s", exc)

    if connected and not failed:
        status: McpStatus = "all_ok"
    elif connected and failed:
        status = "partial_ok"
    else:
        status = "all_fail"

    return client, MCPInitReport(
        status=status, cwd=project_root, config_path=config_path,
        connected=connected, failed=failed, note=conflict_note,
    )


def _detect_config_conflict(active_path: Path, fallback_path: Path) -> str:
    """两份 .mcp.json 都存在且内容不一致时，返回告警文本；否则返回空串。"""
    if not active_path.is_file() or not fallback_path.is_file():
        return ""
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
        fallback = json.loads(fallback_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(active, dict) or not isinstance(fallback, dict) or active == fallback:
        return ""
    return (
        f"检测到两份不同的 .mcp.json，本次生效的是启动目录版本：{active_path}"
        f"（另一份：{fallback_path}）。若刚修改了 MCP 配置，请同步另一处或删除其中一份。"
    )
