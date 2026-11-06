"""命令行工具：RunCli —— 以 shell=False 的列表方式调用本机已安装的 CLI。

设计要点：
- 程序名与参数拼成列表传给 subprocess.run，全程不拼接 Shell 命令字符串；
- 工作目录固定为 Agent 的 workspace，与文件工具保持一致；
- 超时后终止进程，并把已产生的输出一并回写，便于模型判断；
- stdout / stderr 各自截断并标注，避免大量终端输出撑爆上下文。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from core.tools.base import Tool

CLI_TIMEOUT = 30  # 单条命令的执行超时（秒）
MAX_STREAM_CHARS = 4000  # stdout / stderr 各自的返回上限


def _decode(raw: bytes) -> str:
    """按 UTF-8 → GBK 的顺序解码；都无法解码时用替换字符兜底。"""
    if not raw:
        return ""
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class CliToolkit:
    """命令在当前用户权限下执行，工作目录为 workspace。

    timeout / max_chars 来自 config.ini 的 [TOOLS] 段（缺省用模块常量）。
    """

    def __init__(
        self,
        workspace: Path | None = None,
        *,
        timeout: float = CLI_TIMEOUT,
        max_chars: int = MAX_STREAM_CHARS,
    ) -> None:
        self.workspace = (workspace or Path.cwd()).resolve()
        self._timeout = timeout
        self._max_chars = max_chars

    def _clip(self, text: str, label: str) -> str:
        """截断超长输出，并明确标注被截断。"""
        if len(text) <= self._max_chars:
            return text
        return (
            text[: self._max_chars]
            + f"\n…（{label} 过长已截断，原始长度 {len(text)} 字符，仅展示前 {self._max_chars} 字符）"
        )

    @property
    def timeout(self) -> float:
        """单条命令超时（秒），供工具描述文案使用。"""
        return self._timeout

    def run_cli(self, command: str, args: list[str] | None = None) -> str:
        command = (command or "").strip()
        if not command:
            return "错误：command 不能为空，请传入要执行的程序名，例如 git"

        if args is None:
            args = []
        if not isinstance(args, list):
            return "错误：args 必须是字符串数组，例如 [\"--version\"]"

        argv = [command, *(str(item) for item in args)]
        display = subprocess.list2cmdline(argv)

        try:
            completed = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                cwd=str(self.workspace),
                timeout=self._timeout,
            )
        except FileNotFoundError:
            return (
                f"错误：找不到命令 '{command}'。"
                f"请确认该程序已安装，并且位于 PATH 中。"
            )
        except PermissionError:
            return f"错误：当前用户没有执行 '{command}' 的权限。"
        except subprocess.TimeoutExpired as exc:
            timeout_stdout = self._clip(_decode(exc.stdout or b""), "stdout") or "(空)"
            timeout_stderr = self._clip(_decode(exc.stderr or b""), "stderr") or "(空)"
            return "\n".join([
                f"命令：{display}",
                f"错误：执行超时（超过 {self._timeout:g} 秒），进程已被终止。",
                "",
                "--- 超时前的 stdout ---",
                timeout_stdout,
                "",
                "--- 超时前的 stderr ---",
                timeout_stderr,
            ])
        except OSError as exc:
            return f"错误：无法执行 '{command}'（{type(exc).__name__}）：{exc}"

        stdout = _decode(completed.stdout)
        stderr = _decode(completed.stderr)
        exit_note = "（成功）" if completed.returncode == 0 else "（失败）"

        return "\n".join([
            f"命令：{display}",
            f"退出码：{completed.returncode} {exit_note}",
            "",
            "--- stdout ---",
            self._clip(stdout, "stdout") or "(空)",
            "",
            "--- stderr ---",
            self._clip(stderr, "stderr") or "(空)",
        ])


def build_cli_tools(cli_toolkit: CliToolkit) -> list[Tool]:
    """构造命令行工具。"""
    return [
        Tool(
            name="RunCli",
            description=(
                "调用本机已安装的命令行程序（CLI），例如 git、python、pip、node、curl。"
                "返回标准输出、标准错误和退出码，便于判断执行结果。"
                "command 必须是不带参数的单个程序名；参数放在 args 数组中，"
                "例如 {\"command\": \"git\", \"args\": [\"-C\", \".\", \"status\", \"--short\"]}。"
                f"命令在 Agent 的工作目录下执行，超时时间 {cli_toolkit.timeout:g} 秒。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的程序名，例如 git、python、pip、node、npm",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "传给程序的参数列表，每个元素是一个独立参数；无参数时传空数组",
                    },
                },
                "required": ["command"],
            },
            handler=cli_toolkit.run_cli,
        )
    ]
