"""Textual 前端：把 core 的事件流翻译为界面交互。

- 斜杠命令 + 补全引导面板（/help /new /resume /save /quit …）
- 右侧边栏展示 MCP 服务器与工具，MCP 异步加载后动态刷新
- 上下文压缩 / 阈值阻断
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Sequence

from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import Footer, Header, OptionList, Static, TextArea
from textual.widgets.option_list import Option
from textual.worker import Worker

from core.agent.session import AgentSession
from core.agent.session_store import SessionInfo, SessionStore
from core.config import MCPSettings
from core.events import (
    ErrorOccurred,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnCompleted,
)
from core.mcp.bootstrap import MCPInitReport
from tui.widgets.chat_view import ChatView
from tui.widgets.sidebar import Sidebar

# 斜杠命令清单：补全面板与 /help 都从这里生成
SLASH_COMMANDS: tuple[tuple[str, str], ...] = (
    ("/help", "显示全部斜杠命令与说明"),
    ("/new", "新建会话（自动保存当前会话历史）"),
    ("/resume", "恢复历史会话（上下键选择，回车确认，ESC 取消）"),
    ("/save", "保存当前会话到 .agents/sessions/"),
    ("/compact", "压缩上下文并归档原始记录"),
    ("/context", "查看当前上下文用量详情"),
    ("/tools", "查看当前可用工具列表"),
    ("/skills", "查看已加载的技能"),
    ("/mcp", "查看 MCP 服务器状态与暴露的工具"),
    ("/clear", "清空屏幕与会话历史"),
    ("/quit", "退出 xAgent"),
)


class SlashPanel(OptionList):
    """斜杠命令补全 / 历史会话选择共用面板。"""

    class Cancelled(Message):
        """用户按 ESC 取消面板。"""

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.post_message(self.Cancelled())
            return
        await super()._on_key(event)


class PromptArea(TextArea):
    """多行指令输入框：Enter 发送，Ctrl+J 换行。

    TextArea 原生支持多行粘贴，避免长指令被截断成一行。
    补全面板可见时，上下键/回车/Tab/ESC 先交给面板处理。
    """

    BINDINGS = [
        # Windows 控制台把 Shift/Ctrl/Alt+Enter 都上报为普通 Enter，
        # 只有 Ctrl+J（\n）是可稳定识别的换行键，因此放在首位。
        Binding("ctrl+j", "insert_newline", "换行", show=True),
        Binding("shift+enter", "insert_newline", "换行", show=False),
        Binding("ctrl+enter", "insert_newline", "换行", show=False),
        Binding("alt+enter", "insert_newline", "换行", show=False),
    ]

    class Submitted(Message):
        """用户按下 Enter，请求发送当前内容。"""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    async def _on_key(self, event: events.Key) -> None:
        app = self.app
        panel_active = getattr(app, "slash_panel_active", False)

        if event.key == "enter":
            event.stop()
            event.prevent_default()
            if panel_active:
                app.apply_completion()
                return
            self.post_message(self.Submitted(self.text))
            return

        if panel_active:
            if event.key == "down":
                event.stop()
                event.prevent_default()
                app.move_completion(1)
                return
            if event.key == "up":
                event.stop()
                event.prevent_default()
                app.move_completion(-1)
                return
            if event.key == "tab":
                event.stop()
                event.prevent_default()
                app.apply_completion()
                return
            if event.key == "escape":
                event.stop()
                event.prevent_default()
                app.hide_completion()
                return

        await super()._on_key(event)
        # 输入内容变化后刷新补全列表（面板可见时实时过滤）
        if getattr(app, "update_completion", None):
            app.update_completion(self.text)

    def action_insert_newline(self) -> None:
        self.insert("\n")


class XAgentApp(App[None]):
    CSS_PATH = "app.tcss"
    TITLE = "xAgent"
    SUB_TITLE = "本地文件操作助手"
    BINDINGS = [
        Binding("escape", "cancel_turn", "取消回合"),
        Binding("ctrl+l", "clear_chat", "清空会话"),
        Binding("ctrl+c", "quit", "退出"),
    ]

    def __init__(
        self,
        *,
        session: AgentSession,
        model_name: str,
        workspace: Path,
        tool_count: int,
        skill_names: Sequence[str] = (),
        archiver=None,
        session_store: SessionStore | None = None,
        flush_interval: float = 0.05,
        mcp_report=None,
        mcp_settings: MCPSettings | None = None,
        project_root: Path | None = None,
        fallback_mcp_config: Path | None = None,
    ) -> None:
        super().__init__()
        self._session = session
        self._model_name = model_name
        self._workspace = workspace
        self._tool_count = tool_count
        self._skill_names = tuple(skill_names)
        # ContextArchiver：/compact 压缩时保存原始上下文（main.py 传入）
        self._archiver = archiver
        # 会话持久化（/save /new /resume）；main.py 传入
        self._session_store = session_store
        # 流式文本刷新间隔（秒），来自 config.ini [TUI] flush_interval
        self._flush_interval = flush_interval
        self._busy = False
        self._worker: Worker[None] | None = None

        # ---------- MCP 异步加载 ----------
        self.mcp_client: Any = None  # AsyncMCPClient；连接成功后由 main 关闭
        root = project_root if project_root is not None else workspace
        if mcp_report is not None:
            # 同步模式：外部已加载完成（兼容旧调用与测试脚本）
            self._mcp_report = mcp_report
            self._mcp_settings: MCPSettings | None = None
        elif mcp_settings is not None:
            self._mcp_settings = mcp_settings
            self._mcp_report = MCPInitReport(
                status="loading",
                cwd=root,
                config_path=root / ".mcp.json",
                note="正在后台连接 MCP 服务器…",
            )
        else:
            self._mcp_settings = None
            self._mcp_report = MCPInitReport(
                status="disabled",
                cwd=root,
                config_path=root / ".mcp.json",
                note="未提供 MCP 配置",
            )
        self._mcp_fallback = fallback_mcp_config
        self._mcp_root = root

        # ---------- 斜杠命令面板状态 ----------
        # None=隐藏 / "completion"=命令补全 / "resume"=历史会话选择
        self._slash_mode: str | None = None
        self._completion_matches: tuple[tuple[str, str], ...] = ()
        self._completion_prefix: str | None = None
        self._resume_sessions: list[SessionInfo] = []

    # ---------- 布局 ----------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Container(id="chat-container"):
                yield ChatView(id="chat")
            yield Sidebar(id="sidebar")
        yield SlashPanel(id="slash-panel")
        yield Static(id="status")
        yield PromptArea(
            placeholder="输入指令或 / 命令；Enter 发送，Ctrl+J 换行（Esc 取消当前回合）",
            id="prompt",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#slash-panel", SlashPanel).display = False
        self._chat.add_system(
            f"xAgent 就绪 · 模型 {self._model_name} · 工作目录 {self._workspace}"
        )
        if self._skill_names:
            self._chat.add_system(f"已加载技能：{'、'.join(self._skill_names)}")
        if self._mcp_report.status == "loading":
            self._chat.add_system("MCP 正在后台连接…（完成后自动刷新边栏）")
        else:
            self._render_mcp_result(self._mcp_report)
        self._chat.add_system(
            "提示：输入 / 可弹出命令补全面板；/help 查看全部命令；"
            "/compact 压缩上下文；/resume 恢复历史会话。"
        )
        self._refresh_sidebar()
        self._update_status()
        self.query_one("#prompt", PromptArea).focus()

        # MCP 异步加载：先进入 TUI，后台连接，完成后动态刷新界面
        if self._mcp_settings is not None:
            self.run_worker(self._load_mcp(), group="mcp", exclusive=True)

    # ---------- MCP 异步加载 ----------

    async def _load_mcp(self) -> None:
        from core.mcp.bootstrap import attach_mcp

        settings = self._mcp_settings
        assert settings is not None
        try:
            client, report = await attach_mcp(
                self._session,
                self._mcp_root,
                enabled=settings.enabled,
                retries=settings.retries,
                retry_backoff=settings.retry_backoff,
                call_timeout=settings.call_timeout,
                connect_timeout=settings.connect_timeout,
                fallback_config_path=self._mcp_fallback,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            report = MCPInitReport(
                status="internal_error",
                cwd=self._mcp_root,
                config_path=self._mcp_root / ".mcp.json",
                note=f"初始化异常（已跳过）：{type(exc).__name__}: {exc}",
            )
            client = None

        self.mcp_client = client
        self._mcp_report = report
        self._tool_count = len(self._session.tools)
        self._refresh_sidebar()
        self._update_status()
        self._render_mcp_result(report)

    def _render_mcp_result(self, report) -> None:
        """把 MCP 加载结果输出到欢迎区/聊天区。"""
        status = report.status
        if status == "loading":
            return  # 由 on_mount 的加载提示负责
        if status == "disabled":
            self._chat.add_system("MCP 已禁用（config.ini [MCP] enabled=false）")
        elif status == "not_configured":
            self._chat.add_system(f"MCP 未配置：{report.note or '未找到 .mcp.json'}")
        elif status == "sdk_missing":
            self._chat.add_system("[警告] MCP Python SDK 未安装，MCP 功能不可用")
        elif status == "internal_error":
            self._chat.add_system(f"[警告] MCP 初始化阶段异常：{report.note or ''}")
        elif status == "all_ok":
            self._chat.add_system(
                f"MCP Server 已连接：{'、'.join(report.connected)}"
                f"（配置：{report.config_path}）"
            )
        elif status == "partial_ok":
            self._chat.add_system(
                f"MCP Server 已连接：{'、'.join(report.connected)}"
                f"（配置：{report.config_path}）"
            )
            for name, err in report.failed:
                self._chat.add_system(f"[警告] MCP Server「{name}」连接失败：{err}")
        elif status == "all_fail":
            for name, err in report.failed:
                self._chat.add_system(f"[警告] MCP Server「{name}」连接失败：{err}")
        if status in ("all_ok", "partial_ok", "all_fail") and report.note:
            # 双份 .mcp.json 冲突等提示（见 bootstrap._detect_config_conflict）
            self._chat.add_system(f"[提示] {report.note}")

    def _mcp_status_label(self) -> str:
        """状态栏里用的简洁 MCP 状态标签。"""
        status = self._mcp_report.status
        if status == "loading":
            return "MCP 加载中"
        if status == "disabled":
            return "MCP 关闭"
        if status == "not_configured":
            return ""  # 未配置时不占状态栏位置
        if status == "sdk_missing":
            return "MCP 缺 SDK"
        if status == "internal_error":
            return "MCP 异常"
        if status == "all_ok":
            names = self._mcp_report.connected
            return f"MCP {len(names)} OK"
        if status == "partial_ok":
            ok = len(self._mcp_report.connected)
            fail = len(self._mcp_report.failed)
            return f"MCP {ok}/{ok+fail}"
        if status == "all_fail":
            return f"MCP {len(self._mcp_report.failed)} 全失败"
        return ""

    def _refresh_sidebar(self) -> None:
        """用当前 MCP 报告 + 注册表刷新边栏。"""
        tools_by_server: dict[str, list[str]] = {}
        report = self._mcp_report
        if report.status in ("all_ok", "partial_ok"):
            try:
                tools_by_server = report.server_tools(self._session.tools)
            except Exception:
                tools_by_server = {}
        self.query_one("#sidebar", Sidebar).render_mcp(
            report,
            tools_by_server,
            tool_count=self._tool_count,
            skill_names=self._skill_names,
        )

    @property
    def _chat(self) -> ChatView:
        return self.query_one("#chat", ChatView)

    # ---------- 斜杠命令补全面板 ----------

    @property
    def slash_panel_active(self) -> bool:
        return self._slash_mode == "completion"

    def update_completion(self, text: str) -> None:
        """根据当前输入刷新补全列表；非 / 前缀时隐藏面板。"""
        if self._slash_mode == "resume":
            return
        stripped = text.strip()
        if not stripped.startswith("/") or len(stripped.split()) > 1:
            self.hide_completion()
            return
        prefix = stripped.lower()
        if self._slash_mode == "completion" and prefix == self._completion_prefix:
            return  # 前缀没变，避免重复渲染
        matches = tuple(
            (cmd, desc) for cmd, desc in SLASH_COMMANDS if cmd.startswith(prefix)
        )
        if not matches:
            self.hide_completion()
            return
        self._completion_matches = matches
        self._completion_prefix = prefix
        panel = self.query_one("#slash-panel", SlashPanel)
        panel.clear_options()
        for cmd, desc in matches:
            panel.add_option(Option(f"{cmd}  — {desc}"))
        self._slash_mode = "completion"
        panel.display = True
        panel.highlighted = 0

    def hide_completion(self) -> None:
        if self._slash_mode == "completion":
            self._hide_panel()

    def move_completion(self, delta: int) -> None:
        panel = self.query_one("#slash-panel", SlashPanel)
        count = panel.option_count
        if count == 0:
            return
        current = panel.highlighted if panel.highlighted is not None else 0
        panel.highlighted = max(0, min(count - 1, current + delta))

    def apply_completion(self) -> None:
        """把选中的命令填入输入框（不直接发送，给用户补参数的机会）。"""
        if self._slash_mode != "completion" or not self._completion_matches:
            return
        panel = self.query_one("#slash-panel", SlashPanel)
        index = panel.highlighted if panel.highlighted is not None else 0
        index = max(0, min(index, len(self._completion_matches) - 1))
        command = self._completion_matches[index][0]
        self._hide_panel()
        prompt = self.query_one("#prompt", PromptArea)
        prompt.load_text(command + " ")
        prompt.cursor_location = prompt.document.end
        prompt.focus()

    def _hide_panel(self) -> None:
        panel = self.query_one("#slash-panel", SlashPanel)
        panel.display = False
        self._slash_mode = None
        self._completion_matches = ()
        self._completion_prefix = None
        self._resume_sessions = []
        prompt = self.query_one("#prompt", PromptArea)
        if not prompt.disabled:
            prompt.focus()

    @on(SlashPanel.Cancelled)
    def _on_panel_cancelled(self) -> None:
        was_resume = self._slash_mode == "resume"
        self._hide_panel()
        if was_resume:
            self._chat.add_system("已取消恢复会话")

    @on(OptionList.OptionSelected, "#slash-panel")
    async def _on_panel_selected(self, event: OptionList.OptionSelected) -> None:
        # 补全模式的回车在 PromptArea 里拦截处理，只有 resume 模式
        # 才会把焦点交给面板，因此这里只需处理会话选择。
        event.stop()
        if self._slash_mode != "resume":
            self._hide_panel()
            return
        session_id = str(event.option_id) if event.option_id else ""
        self._hide_panel()
        if session_id:
            self._do_resume(session_id)

    # ---------- 斜杠命令 ----------

    @on(PromptArea.Submitted)
    async def _submit_prompt(self, event: PromptArea.Submitted) -> None:
        text = event.value.strip()
        if not text or self._busy:
            return
        prompt = self.query_one("#prompt", PromptArea)

        if text.startswith("/"):
            prompt.text = ""
            await self._dispatch_command(text)
            return

        # 上下文达到阈值：暂停接受新的普通提示词，直到压缩完成
        monitor = self._session.monitor
        if monitor.blocked:
            self._chat.add_system(
                f"⚠ {monitor.label()}，已达到 {int(monitor.threshold * 100)}% 阈值，"
                "暂停接受新指令。请先执行 /compact 压缩上下文。"
            )
            return

        prompt.text = ""
        self._set_busy(True)
        self._chat.add_user(text)
        self._worker = self.run_worker(
            self._run_turn(text), group="turn", exclusive=True
        )

    async def _dispatch_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        if cmd == "/help":
            self._show_help()
        elif cmd == "/new":
            self._cmd_new()
        elif cmd == "/save":
            self._cmd_save()
        elif cmd == "/resume":
            self._start_resume()
        elif cmd == "/compact":
            self._start_compaction()
        elif cmd == "/context":
            self._show_context()
        elif cmd == "/tools":
            self._show_tools()
        elif cmd == "/skills":
            self._show_skills()
        elif cmd == "/mcp":
            self._show_mcp()
        elif cmd == "/clear":
            self.action_clear_chat()
        elif cmd == "/quit":
            self.exit()
        else:
            self._chat.add_system(
                f"未知命令「{cmd}」。输入 / 查看补全面板，或 /help 查看全部命令。"
            )

    def _show_help(self) -> None:
        lines = ["可用斜杠命令："]
        lines += [f"  {cmd:<10} {desc}" for cmd, desc in SLASH_COMMANDS]
        lines.append("快捷键：Enter 发送 · Ctrl+J 换行 · Esc 取消当前回合 · Ctrl+L 清空会话")
        self._chat.add_system("\n".join(lines))

    def _cmd_new(self) -> None:
        """新建会话：先自动保存当前历史，再清空。"""
        saved = self._save_history(quiet_if_empty=True)
        self._session.reset()
        self._chat.remove_children()
        if saved is not None:
            self._chat.add_system(
                f"已自动保存会话 {saved.id}，新会话已创建。"
            )
        else:
            self._chat.add_system("新会话已创建（当前没有可保存的历史消息）。")
        self._update_status()

    def _cmd_save(self) -> None:
        self._save_history(quiet_if_empty=False)

    def _save_history(self, *, quiet_if_empty: bool) -> SessionInfo | None:
        if self._session_store is None:
            self._chat.add_error("会话存储未初始化，无法保存（需从 main.py 正常启动）")
            return None
        messages = list(self._session.messages)
        if not any(m.get("role") == "user" for m in messages):
            if not quiet_if_empty:
                self._chat.add_system("当前会话没有用户消息，无需保存。")
            return None
        try:
            info = self._session_store.save(
                messages,
                model_name=self._model_name,
                token_usage=self._session.monitor.usage,
            )
        except OSError as exc:
            self._chat.add_error(f"会话保存失败：{exc}")
            return None
        self._chat.add_system(
            f"💾 会话已保存：{info.id}（{info.message_count} 条消息）→ {info.path}"
        )
        return info

    def _start_resume(self) -> None:
        """打开历史会话列表面板（上下键选择、回车恢复、ESC 取消）。"""
        if self._session_store is None:
            self._chat.add_error("会话存储未初始化，无法恢复（需从 main.py 正常启动）")
            return
        try:
            sessions = self._session_store.list_sessions()
        except OSError as exc:
            self._chat.add_error(f"读取历史会话失败：{exc}")
            return
        if not sessions:
            self._chat.add_system(
                f"没有可恢复的历史会话（目录：{self._session_store.sessions_dir}）。"
                "先用 /save 或 /new 保存会话。"
            )
            return
        panel = self.query_one("#slash-panel", SlashPanel)
        panel.clear_options()
        for info in sessions:
            label = f"{info.id}  ·  {info.preview}  ({info.message_count} 条)"
            panel.add_option(Option(label, id=info.id))
        self._resume_sessions = list(sessions)
        self._slash_mode = "resume"
        panel.display = True
        panel.highlighted = 0
        panel.focus()

    def _do_resume(self, session_id: str) -> None:
        try:
            messages = self._session_store.load(session_id)
        except FileNotFoundError as exc:
            self._chat.add_error(f"恢复失败：{exc}")
            return
        except OSError as exc:
            self._chat.add_error(f"恢复失败（读取文件出错）：{exc}")
            return
        self._session.load_messages(messages)
        self._chat.remove_children()
        user_count = sum(1 for m in messages if m.get("role") == "user")
        self._chat.add_system(
            f"已恢复会话 {session_id}（{len(messages)} 条消息，其中用户消息 "
            f"{user_count} 条）。历史内容不回放，可直接继续对话；"
            "需要历史细节可让我调用 recallContext 检索压缩归档。"
        )
        self._update_status()

    def _show_context(self) -> None:
        monitor = self._session.monitor
        state = "已阻断普通输入（/compact 后恢复）" if monitor.blocked else "正常"
        source = getattr(monitor, "source", "estimated")
        self._chat.add_system(
            f"上下文用量：{monitor.label()}\n"
            f"  窗口：{monitor.window:,} tokens · 阈值：{int(monitor.threshold * 100)}%"
            f" · 用量来源：{'API 实测' if source == 'api' else '本地估算'}\n"
            f"  状态：{state}\n"
            f"  说明：/compact 可压缩历史并归档原始记录；/new 新建会话。"
        )

    def _show_tools(self) -> None:
        names = [schema["function"]["name"] for schema in self._session.tools.schemas()]
        lines = [f"当前可用工具 {len(names)} 个："]
        lines += [f"  · {name}" for name in names]
        self._chat.add_system("\n".join(lines))

    def _show_skills(self) -> None:
        if self._skill_names:
            self._chat.add_system(
                f"已加载技能 {len(self._skill_names)} 个："
                + "、".join(self._skill_names)
            )
        else:
            self._chat.add_system("未加载任何技能（目录 .agents/skills/ 为空）。")

    def _show_mcp(self) -> None:
        report = self._mcp_report
        status = report.status
        lines = [f"MCP 状态：{status}（配置：{report.config_path}）"]
        if report.connected:
            tools_by_server = {}
            try:
                tools_by_server = report.server_tools(self._session.tools)
            except Exception:
                pass
            for server in report.connected:
                lines.append(f"  ● {server}")
                for name in tools_by_server.get(server, []):
                    lines.append(f"      · {name}")
        if report.failed:
            lines.append("  连接失败：")
            for name, err in report.failed:
                lines.append(f"    ✖ {name}：{err}")
        if status in ("disabled", "not_configured", "sdk_missing", "loading") and report.note:
            lines.append(f"  {report.note}")
        self._chat.add_system("\n".join(lines))

    # ---------- 交互 ----------

    def action_cancel_turn(self) -> None:
        if self._worker is not None and self._busy:
            self._worker.cancel()

    def action_clear_chat(self) -> None:
        self._chat.remove_children()
        self._session.reset()
        self._chat.add_system("会话已清空")
        self._update_status()

    # ---------- 上下文压缩 ----------

    def _start_compaction(self) -> None:
        if self._archiver is None:
            self._chat.add_error("归档器未初始化，无法执行 /compact")
            return
        self._set_busy(True)
        self._chat.add_system("开始压缩上下文：归档原始记录 → 生成摘要 → 替换历史…")
        self._worker = self.run_worker(
            self._run_compaction(), group="turn", exclusive=True
        )

    async def _run_compaction(self) -> None:
        try:
            outcome = await self._session.compact(self._archiver)
        except asyncio.CancelledError:
            self._chat.add_system("已取消压缩（原上下文未改动）")
            raise
        except Exception as exc:  # 兜底：任何异常都不能破坏原上下文
            self._chat.add_error(
                f"压缩失败：{type(exc).__name__}: {exc}（原上下文未改动）"
            )
            return
        finally:
            self._set_busy(False)
            self._worker = None
            self._update_status()

        if outcome.ok:
            self._chat.add_system(
                f"✅ 上下文压缩完成：归档编号 {outcome.archive_id}"
                f"（原 {outcome.message_count} 条消息 → 摘要约 {outcome.summary_tokens} tokens）。"
                "需要历史细节时可让我调用 recallContext 工具检索。"
            )
        else:
            self._chat.add_error(f"压缩失败：{outcome.error}")

    def _check_context_threshold(self) -> None:
        """回合结束后检查用量，首次越过阈值时给出一次性警告。"""
        monitor = self._session.monitor
        if monitor.blocked and not monitor.warned:
            monitor.warned = True
            self._chat.add_system(
                f"⚠ {monitor.label()}，已达到 {int(monitor.threshold * 100)}% 阈值。"
                "请执行 /compact 压缩上下文；压缩完成前无法发送新指令。"
            )
            self._update_status()

    # ---------- 事件流消费 ----------

    async def _run_turn(self, text: str) -> None:
        pending = ""
        last_flush = time.monotonic()

        try:
            async for event in self._session.send(text):
                if isinstance(event, TextDelta):
                    pending += event.text
                    now = time.monotonic()
                    if now - last_flush >= self._flush_interval:
                        self._chat.append_assistant(pending)
                        pending = ""
                        last_flush = now
                elif isinstance(event, ToolCallStarted):
                    if pending:
                        self._chat.append_assistant(pending)
                        pending = ""
                    self._chat.add_tool_call(event.name, event.arguments)
                elif isinstance(event, ToolCallFinished):
                    self._chat.add_tool_result(event.result, event.ok)
                elif isinstance(event, ErrorOccurred):
                    if pending:
                        self._chat.append_assistant(pending)
                        pending = ""
                    self._chat.add_error(event.message)
                elif isinstance(event, TurnCompleted):
                    if pending:
                        self._chat.append_assistant(pending)
                        pending = ""
                    self._chat.end_assistant()
        except asyncio.CancelledError:
            if pending:
                self._chat.append_assistant(pending)
            self._chat.add_system("已取消当前回合")
            raise
        finally:
            if pending:
                self._chat.append_assistant(pending)
            self._chat.end_assistant()
            self._set_busy(False)
            self._worker = None
            self._check_context_threshold()

    # ---------- 状态显示 ----------

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        prompt = self.query_one("#prompt", PromptArea)
        prompt.disabled = busy
        if not busy:
            prompt.focus()
        self._update_status()

    def _update_status(self) -> None:
        monitor = self._session.monitor
        state = "运行中…" if self._busy else ("需 /compact" if monitor.blocked else "就绪")
        skill_part = f" │ 技能 {len(self._skill_names)} 个" if self._skill_names else ""
        mcp_label = self._mcp_status_label()
        mcp_part = f" │ {mcp_label}" if mcp_label else ""
        self.query_one("#status", Static).update(
            f" 模型 {self._model_name} │ 工作目录 {self._workspace} "
            f"│ 工具 {self._tool_count} 个{skill_part}{mcp_part}"
            f" │ {monitor.label()} │ {state}"
        )
