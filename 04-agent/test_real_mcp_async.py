# -*- coding: utf-8 -*-
"""真实 MCP 异步加载验证：TUI 先启动，后台连 MCP，完成后动态刷新边栏。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

XAGENT = Path(r"c:\Users\qq\Desktop\LLM\04-agent\xAgent")
sys.path.insert(0, str(XAGENT))

from textual.widgets import Static

from core.agent.session import AgentSession
from core.agent.session_store import SessionStore
from core.config import load_settings
from core.context.archiver import ContextArchiver
from core.skills import SkillRegistry
from tui.app import XAgentApp


async def main() -> int:
    settings = load_settings(XAGENT / "config.ini")
    skills = SkillRegistry.discover(XAGENT / ".agents" / "skills", project_root=XAGENT)
    session = AgentSession(
        llm=__import__("core.llm.openai_client", fromlist=["OpenAIChatClient"]).OpenAIChatClient(
            api_key=settings.llm.api_key,
            base_url=settings.llm.base_url,
            model_name=settings.llm.model_name,
        ),
        tools=__import__("core.tools", fromlist=["build_default_registry"]).build_default_registry(
            XAGENT, baidu_qianfan_api_key=None, skills=skills,
            context_dir=XAGENT / ".agents" / "context", tool_settings=settings.tools,
        ),
        system_prompt="你是一个测试助手。",
        context_window=settings.context_window,
        warn_ratio=settings.context.warn_ratio,
    )
    base_tools = len(session.tools)
    app = XAgentApp(
        session=session, model_name=settings.llm.model_name, workspace=XAGENT,
        tool_count=base_tools, skill_names=skills.names,
        archiver=ContextArchiver(XAGENT / ".agents" / "context"),
        session_store=SessionStore(XAGENT / ".agents" / "sessions"),
        flush_interval=settings.tui.flush_interval,
        mcp_settings=settings.mcp, project_root=XAGENT,
        fallback_mcp_config=XAGENT / ".mcp.json",
    )
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        print(f"启动时: 状态={app._mcp_report.status}, 工具数={app._tool_count}")
        # 轮询等待异步 MCP 加载完成（最多 60 秒）
        for _ in range(120):
            await asyncio.sleep(0.5)
            await pilot.pause()
            if app._mcp_report.status != "loading":
                break
        report = app._mcp_report
        print(f"加载后: 状态={report.status}, connected={report.connected}, failed={report.failed}")
        print(f"加载后: 工具数={app._tool_count}（MCP 新增 {app._tool_count - base_tools} 个）")
        sidebar = app.query_one("#sidebar-body", Static).visual.plain
        print("---- 边栏内容 ----")
        print(sidebar)
        status_bar = app.query_one("#status", Static).visual.plain
        print("---- 状态栏 ----")
        print(status_bar)
        ok = report.status in ("all_ok", "partial_ok") and app.mcp_client is not None
        checks = [
            ("状态 all_ok/partial_ok", report.status in ("all_ok", "partial_ok")),
            ("client 已持有", app.mcp_client is not None),
            ("边栏含服务器名", any(s in sidebar for s in report.connected)),
            ("边栏含 MCP 工具", "·" in sidebar and report.connected[0] in sidebar if report.connected else False),
            ("状态栏 MCP 计数", "MCP" in status_bar and "加载中" not in status_bar),
        ]
        all_ok = True
        for name, cond in checks:
            print(f"[{'PASS' if cond else 'FAIL'}] {name}")
            all_ok &= cond
        if app.mcp_client is not None:
            await app.mcp_client.close()
        return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
