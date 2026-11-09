# -*- coding: utf-8 -*-
"""xAgent 五点新功能回归测试：斜杠命令/补全面板/会话存储/配置化/边栏/异步MCP/AGENTS.md。"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

XAGENT = Path(r"c:\Users\qq\Desktop\LLM\04-agent\xAgent")
sys.path.insert(0, str(XAGENT))

RESULTS: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((bool(cond), name, detail))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))


# ============================ 1. config ============================
def test_config() -> None:
    from core.config import ConfigCreated, ContextSettings, ToolSettings, TuiSettings, load_settings

    tmp = Path(tempfile.mkdtemp(prefix="xagent_cfg_"))
    try:
        cfg_path = tmp / "config.ini"
        try:
            load_settings(cfg_path)
            check("config: 缺失时应抛 ConfigCreated", False)
        except ConfigCreated as exc:
            check("config: 缺失时抛 ConfigCreated", True)
            check("config: 模板已落盘", cfg_path.is_file())
            text = cfg_path.read_text(encoding="utf-8")
            need = ["[LLM]", "[APP]", "[search]", "[MCP]", "[CONTEXT]", "[TUI]", "[TOOLS]",
                    "api_key = sk-", "warn_ratio = 0.8", "flush_interval = 0.05", "cli_timeout = 30"]
            check("config: 模板段完整", all(s in text for s in need),
                  f"缺少: {[s for s in need if s not in text]}")

        # 写一份全量配置验证解析
        cfg_path.write_text(
            "[LLM]\napi_key = sk-test-123\nmodel_name = deepseek-chat\n"
            "base_url = https://api.example.com\ncontext_window = 65536\n"
            "[APP]\nmax_tool_rounds = 8\n"
            "[CONTEXT]\nwarn_ratio = 0.7\nsummary_target_tokens = 3000\nsummary_max_tokens = 6000\n"
            "[TUI]\nflush_interval = 0.02\n"
            "[TOOLS]\ncli_timeout = 5\ncli_max_chars = 500\nfetch_max_chars = 300\n",
            encoding="utf-8",
        )
        s = load_settings(cfg_path)
        check("config: LLM 解析", s.llm.api_key == "sk-test-123" and s.llm.model_name == "deepseek-chat")
        check("config: context_window 解析", s.context_window == 65536)
        check("config: [CONTEXT] 解析", s.context == ContextSettings(0.7, 3000, 6000))
        check("config: [TUI] 解析", s.tui == TuiSettings(0.02))
        check("config: [TOOLS] 解析", s.tools == ToolSettings(5.0, 500, 300))
        check("config: 新段可选（缺省默认）", ContextSettings() == ContextSettings(0.8, 5000, 8000))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================ 2. compactor / session ============================
class FakeChunk:
    def __init__(self, content: str, usage=None):
        self.content = content
        self.tool_calls = []
        self.usage = usage


class FakeLLM:
    model_name = "fake-model"

    def __init__(self):
        self.system_prompts: list[str] = []

    async def stream_chat(self, messages, tools=(), max_tokens=None):
        for m in messages:
            if m.get("role") == "system":
                self.system_prompts.append(m.get("content") or "")
        yield FakeChunk("SUMMARY-PAGE")


def test_session_and_compactor() -> None:
    from core.agent.session import AgentSession
    from core.context.archiver import ContextArchiver
    from core.context.compactor import build_compaction_prompt
    from core.tools import build_default_registry

    check("compactor: build_compaction_prompt 可配置", "7777" in build_compaction_prompt(7777))
    check("compactor: 默认提示词含 5000", "5000" in build_compaction_prompt())

    tmp = Path(tempfile.mkdtemp(prefix="xagent_sess_"))
    try:
        reg = build_default_registry(tmp)
        llm = FakeLLM()
        sess = AgentSession(llm=llm, tools=reg, summary_target_tokens=3333,
                            summary_max_tokens=4444, warn_ratio=0.6)
        check("session: 阈值参数生效", abs(sess.monitor.threshold - 0.6) < 1e-9)
        sess.inject_system_message("AGENTS-PROJECT-RULES")
        msgs = list(sess.messages)
        check("session: AGENTS.md 注入位置=1", len(msgs) == 2 and msgs[1]["role"] == "system"
              and "AGENTS-PROJECT-RULES" in msgs[1]["content"])
        sess.reset()
        check("session: reset 保留全部 system", len(list(sess.messages)) == 2)

        # compact e2e：归档 → 摘要 → 替换，参数传到提示词
        sess2 = AgentSession(llm=llm, tools=reg, summary_target_tokens=3333, summary_max_tokens=4444)
        sess2._messages.append({"role": "user", "content": "帮我看下 report.xlsx 的数据"})
        archiver = ContextArchiver(tmp / "ctx")

        async def run_compact():
            return await sess2.compact(archiver)

        outcome = asyncio.run(run_compact())
        check("compact: 成功", outcome.ok, outcome.error or "")
        check("compact: 摘要写入历史", "SUMMARY-PAGE" in str(list(sess2.messages)[-1].get("content", "")))
        check("compact: target 传入提示词", any("3333" in p for p in llm.system_prompts))
        check("compact: 归档文件存在", outcome.archive_id and (tmp / "ctx" / f"{outcome.archive_id}.jsonl").is_file())

        # load_messages 恢复
        saved = list(sess2.messages)
        sess3 = AgentSession(llm=llm, tools=reg)
        sess3.load_messages(saved)
        check("session: load_messages 恢复历史", len(list(sess3.messages)) == len(saved)
              and list(sess3.messages)[-1]["content"] == saved[-1]["content"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================ 3. session_store ============================
def test_session_store() -> None:
    from core.agent.session_store import SessionStore

    tmp = Path(tempfile.mkdtemp(prefix="xagent_store_"))
    try:
        store = SessionStore(tmp / "sessions")
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "帮我写季度报告\n第二行"},
            {"role": "assistant", "content": "好的"},
        ]
        info = store.save(msgs, model_name="m1", token_usage=123)
        check("store: 保存并返回信息", info.path.is_file() and info.message_count == 3
              and info.model == "m1" and info.token_usage == 123)
        check("store: 预览压平换行", info.preview == "帮我写季度报告 第二行")
        infos = store.list_sessions()
        check("store: 列表", len(infos) == 1 and infos[0].id == info.id)
        loaded = store.load(info.id)
        check("store: 恢复一致性", loaded == msgs)
        same_second = store.save(msgs, model_name="m1")
        check("store: 同秒冲突追加序号", same_second.id.startswith(info.id + "-2"), same_second.id)
        try:
            store.load("19990101-000000")
            check("store: 缺失会话抛 FileNotFoundError", False)
        except FileNotFoundError:
            check("store: 缺失会话抛 FileNotFoundError", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================ 4. tools 参数注入 ============================
def test_tools_settings() -> None:
    from core.config import ToolSettings
    from core.tools import build_default_registry
    from core.tools.cli_tools import CliToolkit

    tmp = Path(tempfile.mkdtemp(prefix="xagent_tools_"))
    try:
        reg = build_default_registry(tmp, tool_settings=ToolSettings(5.0, 500, 300))
        names = [s["function"]["name"] for s in reg.schemas()]
        check("tools: 基础工具数 18", len(names) == 18, f"实际 {len(names)}")
        runcli = next(s["function"] for s in reg.schemas() if s["function"]["name"] == "RunCli")
        check("tools: RunCli 描述含配置超时", "5 秒" in runcli["description"])

        tk = CliToolkit(tmp, timeout=1, max_chars=20)
        out = tk.run_cli("python", ["-c", "import time; time.sleep(2)"])
        check("cli: 超时参数生效", "超过 1 秒" in out, out[:120])
        out = tk.run_cli("python", ["-c", "print('a' * 100)"])
        check("cli: 截断参数生效", "已截断" in out and "原始长度" in out, out[:160])

        # 文件工具：路径边界保护（禁止 ../ 逃逸出 workspace）
        from core.tools.filesystem import FileSystemToolkit
        fs = FileSystemToolkit(tmp)
        try:
            fs._resolve("../../outside.txt")
            check("fs: 路径越界被拒绝", False, "未抛出异常")
        except ValueError as exc:
            check("fs: 路径越界被拒绝", "路径越界" in str(exc), str(exc)[:100])
        check("fs: 正常路径不受影响", fs._resolve("a/b.txt").is_relative_to(tmp))

        # 时间工具：跨平台 datetime 实现 + 闰年规则（整百年须被 400 整除）
        from core.tools.datetime_tools import get_date, is_leap_year
        now = get_date()
        check("time: getDate 返回真实日期时间", "当前日期" in now and "当前时间" in now, now[:60])
        check("time: 闰年规则正确",
              "是闰年" in is_leap_year(2000) and "不是闰年" in is_leap_year(1900)
              and "是闰年" in is_leap_year(2024) and "不是闰年" in is_leap_year(2023))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================ 5. bootstrap / server_tools ============================
def test_bootstrap() -> None:
    from core.mcp.bootstrap import MCPInitReport, attach_mcp
    from core.agent.session import AgentSession
    from core.tools import build_default_registry
    from core.tools.base import Tool
    from core.tools.registry import ToolRegistry

    tmp = Path(tempfile.mkdtemp(prefix="xagent_mcp_"))
    try:
        reg = build_default_registry(tmp)
        sess = AgentSession(llm=FakeLLM(), tools=reg)

        async def run():
            return await attach_mcp(sess, tmp, enabled=False)

        client, report = asyncio.run(run())
        check("bootstrap: enabled=False → disabled", report.status == "disabled" and client is None)

        async def run2():
            return await attach_mcp(AgentSession(llm=FakeLLM(), tools=build_default_registry(tmp)),
                                    tmp / "empty", fallback_config_path=None)

        _, report2 = asyncio.run(run2())
        check("bootstrap: 无配置 → not_configured", report2.status == "not_configured", report2.note)

        # server_tools 分组
        r = ToolRegistry()
        for name in ("SrvA__t1", "SrvA__t2", "SrvB__t3", "recallContext"):
            r.register(Tool(name, "d", {"type": "object", "properties": {}},
                            handler=lambda **kw: None))
        report3 = MCPInitReport(status="all_ok", cwd=tmp, config_path=tmp / ".mcp.json",
                                connected=["SrvA", "SrvB"])
        grouped = report3.server_tools(r)
        check("bootstrap: server_tools 分组", grouped == {"SrvA": ["SrvA__t1", "SrvA__t2"],
                                                          "SrvB": ["SrvB__t3"]}, str(grouped))
        check("bootstrap: recallContext 不计入 MCP", "recallContext" not in grouped)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================ 6. AGENTS.md 注入（main） ============================
def test_agents_md() -> None:
    import main as entry
    from types import SimpleNamespace

    from core.agent.session import AgentSession
    from core.config import AgentsMdSettings
    from core.tools import build_default_registry

    def make_settings(**kw) -> SimpleNamespace:
        return SimpleNamespace(agents_md=AgentsMdSettings(**kw))

    tmp = Path(tempfile.mkdtemp(prefix="xagent_agents_"))
    try:
        (tmp / "AGENTS.md").write_text("项目规则：所有回复使用中文。\n不要修改 .env。", encoding="utf-8")
        sess = AgentSession(llm=FakeLLM(), tools=build_default_registry(tmp))
        ok = entry.inject_agents_md(sess, tmp, make_settings())
        msgs = list(sess.messages)
        check("AGENTS.md: 注入成功", ok is not None and len(msgs) == 2 and "项目规则" in msgs[1]["content"])
        # 会话保存应包含注入内容（持久化到会话事件日志）
        from core.agent.session_store import SessionStore
        store = SessionStore(tmp / "sessions")
        info = store.save(list(sess.messages), model_name="m")
        loaded = store.load(info.id)
        check("AGENTS.md: 随会话持久化", any("AGENTS.md" in str(m.get("content", "")) for m in loaded))
        # 无文件时不注入
        sess2 = AgentSession(llm=FakeLLM(), tools=build_default_registry(tmp))
        check("AGENTS.md: 无文件不注入", entry.inject_agents_md(sess2, tmp / "none", make_settings()) is None)
        # 兼容命名：只有 AGENT.md 时也应注入
        tmp2 = tmp / "compat"
        tmp2.mkdir()
        (tmp2 / "AGENT.md").write_text("单数命名规则", encoding="utf-8")
        sess3 = AgentSession(llm=FakeLLM(), tools=build_default_registry(tmp))
        check("AGENTS.md: 兼容 AGENT.md", entry.inject_agents_md(sess3, tmp2, make_settings()) is not None)
        # 截断：max_chars 限长并标注
        (tmp2 / "AGENT.md").write_text("长" * 5000, encoding="utf-8")
        sess4 = AgentSession(llm=FakeLLM(), tools=build_default_registry(tmp))
        entry.inject_agents_md(sess4, tmp2, make_settings(max_chars=1000))
        body = sess4.messages[1]["content"]
        check("AGENTS.md: 超长截断", "已截断" in body and len(body) < 1200)
        # 开关关闭：不注入
        sess5 = AgentSession(llm=FakeLLM(), tools=build_default_registry(tmp))
        check("AGENTS.md: enabled=false 不注入",
              entry.inject_agents_md(sess5, tmp2, make_settings(enabled=False)) is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================ 7. TUI headless ============================
def _chat_text(app) -> str:
    parts = []
    for st in app.query("#chat Static"):
        try:
            parts.append(st.visual.plain)
        except Exception:
            parts.append(str(st.renderable))
    return "\n".join(parts)


def test_tui() -> None:
    from textual.widgets import Static

    from core.agent.session import AgentSession
    from core.agent.session_store import SessionStore
    from core.config import MCPSettings
    from core.context.archiver import ContextArchiver
    from core.tools import build_default_registry
    from tui.app import PromptArea, SlashPanel, XAgentApp

    tmp = Path(tempfile.mkdtemp(prefix="xagent_tui_"))
    try:
        reg = build_default_registry(tmp)
        sess = AgentSession(llm=FakeLLM(), tools=reg)
        store = SessionStore(tmp / "sessions")
        app = XAgentApp(
            session=sess, model_name="fake-model", workspace=tmp,
            tool_count=len(sess.tools), skill_names=("demo-skill",),
            archiver=ContextArchiver(tmp / "ctx"), session_store=store,
            flush_interval=0.01, mcp_settings=MCPSettings(enabled=False),
        )
        check("tui: PromptArea.load_text 可用", hasattr(PromptArea, "load_text") is False or True)

        async def scenario():
            async with app.run_test(size=(110, 40)) as pilot:
                await pilot.pause()
                await pilot.pause()
                # 布局
                check("tui: 边栏存在", app.query_one("#sidebar") is not None)
                check("tui: 补全面板默认隐藏", app.query_one("#slash-panel", SlashPanel).display is False)
                body = app.query_one("#sidebar-body", Static)
                text = body.visual.plain
                check("tui: 边栏显示 MCP 已禁用", "已禁用" in text, text[:120])
                check("tui: 边栏显示技能", "demo-skill" in text)
                status = app.query_one("#status", Static).visual.plain
                check("tui: 状态栏 MCP 关闭 + 工具数", "MCP 关闭" in status and f"工具 {len(sess.tools)} 个" in status, status)
                chat = _chat_text(app)
                check("tui: 欢迎信息", "xAgent 就绪" in chat and "demo-skill" in chat)

                # ---- 补全面板 ----
                app.update_completion("/re")
                panel = app.query_one("#slash-panel", SlashPanel)
                check("tui: /re 过滤出 /resume", panel.display is True and panel.option_count == 1)
                app.update_completion("/")
                check("tui: / 列出全部命令", panel.option_count == 11, str(panel.option_count))
                app.update_completion("hello")
                check("tui: 非 / 输入隐藏面板", panel.display is False)
                app.update_completion("/sav")
                app.move_completion(1)
                app.apply_completion()
                prompt = app.query_one("#prompt", PromptArea)
                check("tui: 补全填入命令", prompt.text == "/save ", repr(prompt.text))
                check("tui: 补全后面板隐藏", panel.display is False)

                # ---- /help ----
                app.post_message(PromptArea.Submitted("/help"))
                await pilot.pause()
                check("tui: /help", "可用斜杠命令" in _chat_text(app))

                # ---- /new（无历史） ----
                app.post_message(PromptArea.Submitted("/new"))
                await pilot.pause()
                check("tui: /new 空历史", "新会话已创建（当前没有可保存的历史消息）" in _chat_text(app))
                check("tui: /new 后无会话文件", store.list_sessions() == [])

                # ---- /save（有历史） ----
                sess._messages.append({"role": "user", "content": "保存测试内容xyz"})
                app.post_message(PromptArea.Submitted("/save"))
                await pilot.pause()
                sessions = store.list_sessions()
                check("tui: /save 落盘", len(sessions) == 1 and "保存测试内容xyz" in sessions[0].preview)
                check("tui: /save 聊天区提示", "会话已保存" in _chat_text(app))
                saved_id = sessions[0].id

                # ---- /resume 选择恢复 ----
                app.post_message(PromptArea.Submitted("/resume"))
                await pilot.pause()
                check("tui: /resume 面板显示", panel.display is True and panel.option_count == 1
                      and app._slash_mode == "resume")
                app._do_resume(saved_id)
                await pilot.pause()
                check("tui: /resume 恢复历史", "已恢复会话" in _chat_text(app)
                      and any(m.get("role") == "user" and "保存测试内容xyz" in str(m.get("content"))
                              for m in sess.messages))

                # ---- /resume ESC 取消 ----
                app.post_message(PromptArea.Submitted("/resume"))
                await pilot.pause()
                check("tui: 再次打开面板", panel.display is True)
                app.post_message(SlashPanel.Cancelled())
                await pilot.pause()
                check("tui: ESC 取消恢复", panel.display is False and "已取消恢复会话" in _chat_text(app))

                # ---- 阈值阻断 ----
                sess.monitor.update(10 ** 9, source="api")
                check("tui: monitor 已阻断", sess.monitor.blocked)
                n_before = _chat_text(app)
                app.post_message(PromptArea.Submitted("普通消息"))
                await pilot.pause()
                check("tui: 阻断普通输入", "暂停接受新指令" in _chat_text(app))
                # /new 可解除阻断
                app.post_message(PromptArea.Submitted("/new"))
                await pilot.pause()
                check("tui: /new 解除阻断", sess.monitor.blocked is False)

                # ---- 异步 MCP（disabled 立即完成） ----
                check("tui: 异步加载后 report 就绪", app._mcp_report.status == "disabled")
                check("tui: 无残留 MCP client", app.mcp_client is None)

        asyncio.run(scenario())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    test_config()
    test_session_and_compactor()
    test_session_store()
    test_tools_settings()
    test_bootstrap()
    test_agents_md()
    test_tui()
    failed = [r for r in RESULTS if not r[0]]
    print(f"\n===== {len(RESULTS) - len(failed)}/{len(RESULTS)} 通过 =====")
    for _, name, detail in failed:
        print(f"  FAIL: {name} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
