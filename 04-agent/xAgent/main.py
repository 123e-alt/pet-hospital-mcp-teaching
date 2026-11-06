"""xAgent 装配入口：唯一同时引用 core 与某个前端目录的地方。

替换前端（tui / web / desktop / mobile）时只需改这里，
core 无需任何改动。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.agent.prompt import build_system_prompt
from core.agent.session import AgentSession
from core.agent.session_store import SessionStore
from core.config import AppSettings, ConfigCreated, ConfigError, load_settings
from core.context.archiver import ContextArchiver
from core.llm.openai_client import OpenAIChatClient
from core.mcp import log as mcp_log
from core.skills import SkillRegistry
from core.tools import build_default_registry


def build_session(
    settings: AppSettings,
    skills: SkillRegistry | None = None,
    context_dir: Path | None = None,
) -> AgentSession:
    llm = OpenAIChatClient(
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        model_name=settings.llm.model_name,
    )
    registry = build_default_registry(
        settings.workspace,
        baidu_qianfan_api_key=(
            settings.search.baidu_qianfan_api_key if settings.search else None
        ),
        skills=skills,
        context_dir=context_dir,
        tool_settings=settings.tools,
    )
    return AgentSession(
        llm=llm,
        tools=registry,
        system_prompt=build_system_prompt(tuple(skills) if skills else ()),
        max_tool_rounds=settings.max_tool_rounds,
        context_window=settings.context_window,
        # [CONTEXT] 段：阈值 / 摘要目标 / 摘要输出上限
        warn_ratio=settings.context.warn_ratio,
        summary_target_tokens=settings.context.summary_target_tokens,
        summary_max_tokens=settings.context.summary_max_tokens,
    )


def inject_agents_md(session: AgentSession, project_root: Path) -> bool:
    """AGENTS.md「一次注入，全程复用」。

    会话首次加载时，若启动目录存在 AGENTS.md，就把内容作为一条
    system 消息插入到主提示词之后；此后所有轮次随历史一起发送
    （前缀稳定，缓存友好），并随 /save、/new 持久化到会话事件日志。
    """
    agents_md = project_root / "AGENTS.md"
    if not agents_md.is_file():
        return False
    try:
        content = agents_md.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"[AGENTS.md] 读取失败（已跳过注入）：{exc}", file=sys.stderr)
        return False
    if not content:
        return False
    session.inject_system_message(
        "以下是本项目 AGENTS.md 的内容（项目约定与工作指引），"
        "请在本次会话中始终遵守：\n\n" + content
    )
    return True


async def _run(settings: AppSettings, project_root: Path) -> int:
    skills = SkillRegistry.discover(
        project_root / ".agents" / "skills", project_root=project_root
    )
    if not skills.names:
        # 项目目录没有技能时，回退到源码目录的内置技能，避免「0 技能」困惑
        skills = SkillRegistry.discover(
            PROJECT_ROOT / ".agents" / "skills", project_root=PROJECT_ROOT
        )
    context_dir = project_root / ".agents" / "context"
    session = build_session(settings, skills, context_dir=context_dir)
    # 压缩归档目录与 recallContext 检索目录保持同一处
    archiver = ContextArchiver(context_dir)
    # 会话持久化目录：.agents/sessions/（/save、/new、/resume）
    session_store = SessionStore(project_root / ".agents" / "sessions")

    # AGENTS.md：一次注入，全程复用
    if inject_agents_md(session, project_root):
        mcp_log.get_logger().info("AGENTS.md 已注入会话：%s", project_root / "AGENTS.md")

    # 延迟导入前端：确保 core 不依赖任何界面框架
    from tui.app import XAgentApp

    app = XAgentApp(
        session=session,
        model_name=settings.llm.model_name,
        workspace=settings.workspace,
        tool_count=len(session.tools),
        skill_names=skills.names,
        archiver=archiver,
        session_store=session_store,
        flush_interval=settings.tui.flush_interval,
        # MCP 在 TUI 启动后异步加载：先进界面，加载完成动态刷新边栏
        mcp_settings=settings.mcp,
        project_root=project_root,
        fallback_mcp_config=PROJECT_ROOT / ".mcp.json",
    )
    try:
        await app.run_async()
    finally:
        # MCP 连接必须在本事件循环内关闭（TaskGroup 与循环绑定）
        if app.mcp_client is not None:
            try:
                await app.mcp_client.close()
            except Exception:
                mcp_log.get_logger().exception("关闭 MCP 连接时出现异常（已忽略）")
    return 0


def main() -> int:
    try:
        settings = load_settings()
    except ConfigCreated as exc:
        # 首次运行：已自动生成 mock 模板，提示用户修改后重启
        print("[首次运行] 已生成带 mock 信息的配置模板：")
        print(f"  {exc.path}")
        print("请用编辑器打开该文件，至少填写 [LLM] 段的真实 api_key，")
        print("然后重新启动 xAgent 才能正常工作。")
        return 2
    except ConfigError as exc:
        print(f"[配置错误] {exc}", file=sys.stderr)
        return 1

    mcp_log.configure(PROJECT_ROOT / "logs")

    # 技能与 .mcp.json 都跟随启动时的工作目录
    project_root = Path.cwd()
    return asyncio.run(_run(settings, project_root))


if __name__ == "__main__":
    raise SystemExit(main())
