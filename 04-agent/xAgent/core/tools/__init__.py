"""工具层聚合入口：注册表与默认工具集装配。"""

from __future__ import annotations

from pathlib import Path

from core.config import ToolSettings
from core.skills import SkillRegistry
from core.tools.base import Tool, ToolResult
from core.tools.cli_tools import CliToolkit, build_cli_tools
from core.tools.context_tools import RecallContextToolkit, build_context_tools
from core.tools.datetime_tools import build_datetime_tools
from core.tools.filesystem import FileSystemToolkit, build_filesystem_tools
from core.tools.registry import ToolRegistry
from core.tools.skill_tools import SkillToolkit, build_skill_tools
from core.tools.web_tools import WebToolkit, build_web_tools


def build_default_registry(
    workspace: Path | None = None,
    baidu_qianfan_api_key: str | None = None,
    skills: SkillRegistry | None = None,
    context_dir: Path | None = None,
    tool_settings: ToolSettings | None = None,
) -> ToolRegistry:
    """装配默认工具集；新增工具时只需在此注册。

    tool_settings 为空时使用 ToolSettings 的内置默认值
    （与 config.ini [TOOLS] 段的默认值保持一致）。
    """
    settings = tool_settings or ToolSettings()
    registry = ToolRegistry()
    registry.register(*build_datetime_tools())
    registry.register(*build_filesystem_tools(FileSystemToolkit(workspace)))
    registry.register(
        *build_web_tools(WebToolkit(baidu_qianfan_api_key,
                                    fetch_max_chars=settings.fetch_max_chars))
    )
    registry.register(
        *build_cli_tools(CliToolkit(workspace,
                                    timeout=settings.cli_timeout,
                                    max_chars=settings.cli_max_chars))
    )
    # 注意不能用 `skills or SkillRegistry()`：空技能集 __len__ 为 0，会被判为假值
    skill_registry = skills if skills is not None else SkillRegistry()
    registry.register(*build_skill_tools(SkillToolkit(skill_registry)))
    # 历史上下文检索：归档目录跟随启动目录（.agents/context/）
    context_directory = (
        context_dir if context_dir is not None else (workspace or Path.cwd()) / ".agents" / "context"
    )
    registry.register(*build_context_tools(RecallContextToolkit(context_directory)))
    return registry


__all__ = [
    "CliToolkit",
    "FileSystemToolkit",
    "SkillToolkit",
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "WebToolkit",
    "build_default_registry",
]
