"""配置加载：只依赖标准库，不感知任何界面。"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.ini"


class ConfigError(RuntimeError):
    """配置文件缺失或内容非法。"""


class ConfigCreated(ConfigError):
    """配置文件不存在时已自动生成 mock 模板，需用户填写后重启。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"已生成配置模板：{path}")


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    base_url: str | None
    model_name: str


@dataclass(frozen=True)
class ContextSettings:
    """上下文压缩与监控参数，来自 config.ini 的 [CONTEXT] 段。"""

    # 用量达到窗口该比例后警告并暂停普通输入，直到 /compact 完成
    warn_ratio: float = 0.8
    # 压缩摘要的目标长度（tokens，写入压缩 Prompt）
    summary_target_tokens: int = 5000
    # 摘要生成的输出上限（tokens）
    summary_max_tokens: int = 8000


@dataclass(frozen=True)
class TuiSettings:
    """界面刷新参数，来自 config.ini 的 [TUI] 段。"""

    # 流式文本刷新间隔（秒）
    flush_interval: float = 0.05


@dataclass(frozen=True)
class ToolSettings:
    """工具执行参数，来自 config.ini 的 [TOOLS] 段。"""

    # RunCli 单条命令超时（秒）
    cli_timeout: float = 30.0
    # RunCli stdout/stderr 各自的返回上限（字符）
    cli_max_chars: int = 4000
    # fetchWeb 返回 Markdown 上限（字符）
    fetch_max_chars: int = 8000


@dataclass(frozen=True)
class AgentsMdSettings:
    """AGENTS.md 注入参数，来自 config.ini 的 [AGENTS_MD] 段。"""

    # 总开关：false 时完全跳过注入
    enabled: bool = True
    # 兼容文件名（逗号分隔，按顺序取第一个存在的）
    filenames: str = "AGENTS.md,AGENT.md"
    # 注入内容长度上限（字符），超出截断并标注
    max_chars: int = 20000


@dataclass(frozen=True)
class SearchSettings:
    """联网搜索相关密钥配置。缺失时工具会给出提示而非让启动失败。"""

    baidu_qianfan_api_key: str


@dataclass(frozen=True)
class MCPSettings:
    """MCP 连接与重试参数，来自 config.ini 的 [MCP] 段。"""

    # 总开关：false 时完全跳过 MCP 初始化
    enabled: bool = True
    # 单次工具调用失败后的重试次数（0 表示不重试）
    retries: int = 2
    # 线性退避基数（秒）：第 n 次重试前等待 retry_backoff * n
    retry_backoff: float = 1.0
    # 单次工具调用超时（秒）
    call_timeout: float = 60.0
    # 建立连接 / list_tools 超时（秒）
    connect_timeout: float = 30.0


@dataclass(frozen=True)
class AppSettings:
    llm: LLMSettings
    workspace: Path
    max_tool_rounds: int
    search: SearchSettings | None = None
    # MCP 功能总开关与重试参数
    mcp: MCPSettings = MCPSettings()
    # 模型上下文窗口（tokens）；0 表示未知，运行时使用默认 128k 并在界面标注「默认」
    context_window: int = 0
    # 上下文压缩 / 界面刷新 / 工具执行参数
    context: ContextSettings = ContextSettings()
    tui: TuiSettings = TuiSettings()
    tools: ToolSettings = ToolSettings()
    agents_md: AgentsMdSettings = AgentsMdSettings()


def load_settings(config_path: str | Path | None = None) -> AppSettings:
    """读取并校验配置，返回不可变的应用设置对象。"""
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    if not path.is_file():
        # 首次运行：生成一份带 mock 信息的完整模板，提示用户修改后重启
        _create_default_config(path)
        raise ConfigCreated(path)

    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")

    if not parser.has_section("LLM"):
        raise ConfigError(f"配置文件缺少 [LLM] 段：{path}")

    api_key = parser.get("LLM", "api_key", fallback="").strip()
    if not api_key or api_key.startswith("sk-xxxx"):
        raise ConfigError("请在 config.ini 的 [LLM] 段填写有效的 api_key")

    model_name = parser.get("LLM", "model_name", fallback="").strip()
    if not model_name:
        raise ConfigError("请在 config.ini 的 [LLM] 段填写 model_name")

    base_url = parser.get("LLM", "base_url", fallback="").strip() or None

    # 模型上下文窗口（tokens）：0 或缺省 = 未知，运行时用默认 128k
    context_window = _read_int(parser, "LLM", "context_window", 0, minimum=0)
    if 0 < context_window < 1000:
        raise ConfigError("context_window 应为不小于 1000 的 token 数，或留空使用默认值")

    workspace_text = parser.get("APP", "workspace", fallback="").strip()
    workspace = Path(workspace_text).expanduser() if workspace_text else Path.cwd()

    rounds_text = parser.get("APP", "max_tool_rounds", fallback="16").strip()
    try:
        max_tool_rounds = int(rounds_text)
    except ValueError as exc:
        raise ConfigError(f"max_tool_rounds 必须是整数，当前为：{rounds_text}") from exc
    if max_tool_rounds < 1:
        raise ConfigError("max_tool_rounds 必须大于 0")

    # [search] 段为可选，缺失时联网工具会返回提示信息
    search: SearchSettings | None = None
    if parser.has_section("search"):
        search_api_key = parser.get("search", "baidu_qianfan_api_key", fallback="").strip()
        if search_api_key:
            search = SearchSettings(baidu_qianfan_api_key=search_api_key)

    # [MCP] 段为可选
    mcp_enabled = True
    mcp_retries = 2
    mcp_backoff = 1.0
    mcp_call_timeout = 60.0
    mcp_connect_timeout = 30.0
    if parser.has_section("MCP"):
        enabled_text = parser.get("MCP", "enabled", fallback="true").strip().lower()
        if enabled_text in ("false", "0", "no", "off"):
            mcp_enabled = False
        mcp_retries = _read_int(parser, "MCP", "retries", 2, minimum=0)
        mcp_backoff = _read_float(parser, "MCP", "retry_backoff", 1.0, minimum=0.0)
        mcp_call_timeout = _read_float(parser, "MCP", "call_timeout", 60.0, minimum=1.0)
        mcp_connect_timeout = _read_float(
            parser, "MCP", "connect_timeout", 30.0, minimum=1.0
        )

    # [TUI] / [TOOLS] / [CONTEXT] 段均为可选，缺失时用默认值
    tui_flush = _read_float(parser, "TUI", "flush_interval", 0.05, minimum=0.01)
    context_settings = ContextSettings(
        warn_ratio=_read_float(parser, "CONTEXT", "warn_ratio", 0.8, minimum=0.1),
        summary_target_tokens=_read_int(
            parser, "CONTEXT", "summary_target_tokens", 5000, minimum=500
        ),
        summary_max_tokens=_read_int(
            parser, "CONTEXT", "summary_max_tokens", 8000, minimum=1000
        ),
    )
    tool_settings = ToolSettings(
        cli_timeout=_read_float(parser, "TOOLS", "cli_timeout", 30.0, minimum=1.0),
        cli_max_chars=_read_int(parser, "TOOLS", "cli_max_chars", 4000, minimum=200),
        fetch_max_chars=_read_int(parser, "TOOLS", "fetch_max_chars", 8000, minimum=200),
    )

    # [AGENTS_MD] 段为可选
    agents_enabled = True
    agents_filenames = "AGENTS.md,AGENT.md"
    agents_max_chars = 20000
    if parser.has_section("AGENTS_MD"):
        enabled_text = parser.get("AGENTS_MD", "enabled", fallback="true").strip().lower()
        if enabled_text in ("false", "0", "no", "off"):
            agents_enabled = False
        agents_filenames = (
            parser.get("AGENTS_MD", "filenames", fallback=agents_filenames).strip()
            or agents_filenames
        )
        agents_max_chars = _read_int(
            parser, "AGENTS_MD", "max_chars", 20000, minimum=500
        )

    return AppSettings(
        llm=LLMSettings(api_key=api_key, base_url=base_url, model_name=model_name),
        workspace=workspace.resolve(),
        max_tool_rounds=max_tool_rounds,
        search=search,
        mcp=MCPSettings(
            enabled=mcp_enabled,
            retries=mcp_retries,
            retry_backoff=mcp_backoff,
            call_timeout=mcp_call_timeout,
            connect_timeout=mcp_connect_timeout,
        ),
        context_window=context_window,
        context=context_settings,
        tui=TuiSettings(flush_interval=tui_flush),
        tools=tool_settings,
        agents_md=AgentsMdSettings(
            enabled=agents_enabled,
            filenames=agents_filenames,
            max_chars=agents_max_chars,
        ),
    )


DEFAULT_CONFIG_TEMPLATE = """\
; xAgent 配置文件（自动生成，请填写真实值后重新启动）
; 本文件包含密钥，已被 .gitignore 忽略，不会提交到 GitHub

[LLM]
; 必填：DeepSeek 开放平台 (https://platform.deepseek.com) 申请的 API Key
api_key = sk-请把这里替换成你的真实Key
; OpenAI 兼容网关地址（DeepSeek 官方）
base_url = https://api.deepseek.com
; 模型名：deepseek-chat / deepseek-reasoner 等
model_name = deepseek-chat
; 可选：模型上下文窗口（tokens）。留空/0 = 未知，按默认 128k 监控并在界面标注「默认」
; context_window = 131072

[APP]
; 可选：文件工具的默认工作目录。留空 = 使用启动目录
; workspace =
; LLM 与工具的最大交互轮数
max_tool_rounds = 16

[search]
; 可选：百度千帆搜索密钥（searchWeb 工具用）。不需要搜索可整段删除
baidu_qianfan_api_key = 请替换成你的千帆Key（不用搜索可留空）

[MCP]
; MCP 功能总开关
enabled = true
; 工具调用失败重试次数 / 退避基数（秒）
retries = 2
retry_backoff = 1.0
; 单次调用 / 建连超时（秒）
call_timeout = 60
connect_timeout = 30

[CONTEXT]
; 上下文用量达到窗口比例后警告并暂停普通输入，直到 /compact 完成
warn_ratio = 0.8
; /compact 摘要目标长度与输出上限（tokens）
summary_target_tokens = 5000
summary_max_tokens = 8000

[TUI]
; 流式输出刷新间隔（秒）
flush_interval = 0.05

[AGENTS_MD]
; 启动时把项目规则文件作为 system 消息注入会话（一次注入，全程复用）
enabled = true
; 兼容文件名（逗号分隔，按顺序取第一个存在的）
filenames = AGENTS.md,AGENT.md
; 注入内容长度上限（字符），超出截断并标注
max_chars = 20000

[TOOLS]
; RunCli 命令超时（秒）与返回上限（字符）
cli_timeout = 30
cli_max_chars = 4000
; fetchWeb 返回 Markdown 上限（字符）
fetch_max_chars = 8000
"""


def _create_default_config(path: Path) -> None:
    """配置文件不存在时，生成一份带 mock 信息的完整模板。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")


def _read_int(
    parser: configparser.ConfigParser, section: str, key: str, default: int, *,
    minimum: int,
) -> int:
    text = parser.get(section, key, fallback="").strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError as exc:
        raise ConfigError(f"[{section}] {key} 必须是整数，当前为：{text}") from exc
    if value < minimum:
        raise ConfigError(f"[{section}] {key} 不能小于 {minimum}")
    return value


def _read_float(
    parser: configparser.ConfigParser, section: str, key: str, default: float, *,
    minimum: float,
) -> float:
    text = parser.get(section, key, fallback="").strip()
    if not text:
        return default
    try:
        value = float(text)
    except ValueError as exc:
        raise ConfigError(f"[{section}] {key} 必须是数字，当前为：{text}") from exc
    if value < minimum:
        raise ConfigError(f"[{section}] {key} 不能小于 {minimum}")
    return value
