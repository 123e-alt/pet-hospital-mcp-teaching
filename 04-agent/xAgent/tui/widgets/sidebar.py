"""边栏组件：展示已连接 MCP 服务器及其暴露给 LLM 的工具。

MCP 异步加载完成后由 app 调用 ``render_mcp`` 动态刷新，
不阻塞 TUI 首屏。
"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static

_SEPARATOR = "─" * 24


class Sidebar(VerticalScroll):
    """右侧信息栏：MCP 状态 + 工具清单 + 技能。"""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._body = Static("", markup=False, id="sidebar-body")

    def compose(self):
        yield self._body

    def update_content(self, text: str) -> None:
        self._body.update(text)

    def render_mcp(
        self,
        report,
        tools_by_server: dict[str, list[str]],
        *,
        tool_count: int,
        skill_names: tuple[str, ...] = (),
    ) -> None:
        """根据 MCPInitReport 与注册表刷新边栏内容。"""
        lines: list[str] = ["MCP 服务器", _SEPARATOR]
        status = report.status

        if status == "loading":
            lines.append("◌ 正在后台连接…")
            lines.append("  连接完成后自动刷新")
        elif status == "disabled":
            lines.append("○ 已禁用")
            lines.append("  config.ini [MCP] enabled=false")
        elif status == "not_configured":
            lines.append("○ 未配置")
            lines.append("  当前目录缺少 .mcp.json")
        elif status == "sdk_missing":
            lines.append("✖ 缺少 mcp SDK")
            lines.append("  请执行 pip install mcp")
        elif status == "internal_error":
            lines.append("✖ 初始化异常")
            note = (report.note or "").strip()
            if note:
                lines.append(f"  {note[:80]}")
        elif status in ("all_ok", "partial_ok", "all_fail"):
            for server in report.connected:
                lines.append(f"● {server}")
                tools = tools_by_server.get(server, [])
                for name in tools:
                    lines.append(f"   · {name}")
                if not tools:
                    lines.append("   · (该服务器无工具)")
            if report.failed:
                if report.connected:
                    lines.append("")
                lines.append("连接失败：")
                for name, err in report.failed:
                    lines.append(f"✖ {name}")
                    if err:
                        lines.append(f"   {err[:60]}")
            if not report.connected and not report.failed:
                lines.append("(无已连接服务器)")

        lines += ["", _SEPARATOR, f"工具总数：{tool_count}"]
        if skill_names:
            lines.append(f"技能：{'、'.join(skill_names)}")
        self.update_content("\n".join(lines))
