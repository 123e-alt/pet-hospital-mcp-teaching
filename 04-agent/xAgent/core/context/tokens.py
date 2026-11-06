"""Token 估算与上下文窗口监控（纯标准库，不依赖任何分词框架）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

# 配置未指定窗口、API 也不提供窗口信息时的默认上下文窗口：128k
DEFAULT_CONTEXT_WINDOW = 131072

# 用量达到窗口该比例后：显示警告 + 暂停接受新的普通提示词，直到 /compact 完成
USAGE_WARN_RATIO = 0.8

# 每条消息的固定开销（role、分隔符等），经验值
_PER_MESSAGE_OVERHEAD = 4


def estimate_tokens(text: str) -> int:
    """粗略估算一段文本的 token 数。

    经验规则：中日韩字符约 1 token/字，其余字符约 4 字符/token。
    仅作为 API 未返回 usage 时的兜底估算，不追求精确。
    """
    if not text:
        return 0
    cjk = 0
    for ch in text:
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F or 0xFF00 <= code <= 0xFFEF:
            cjk += 1
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def estimate_messages_tokens(messages: Sequence[dict[str, Any]]) -> int:
    """估算一组 OpenAI 格式消息的总 token 数（System / 历史 / 工具消息都计入）。

    注意：不包含工具 schema 的开销（API 的 prompt_tokens 会包含它，
    估算值因此略偏小，仅在拿不到 API usage 时作为兜底）。
    """
    total = 0
    for message in messages:
        total += _PER_MESSAGE_OVERHEAD
        total += estimate_tokens(message.get("content") or "")
        for call in message.get("tool_calls") or ():
            function = call.get("function", {})
            total += estimate_tokens(function.get("name") or "")
            total += estimate_tokens(function.get("arguments") or "")
    return total


@dataclass
class ContextMonitor:
    """跟踪当前会话的上下文 token 用量，并在超过阈值时给出状态。

    用量来源优先级：
    1. ``source="api"``——LLM 响应携带的真实 usage（首选）；
    2. ``source="estimated"``——按消息文本估算（兜底）。
    """

    window: int = DEFAULT_CONTEXT_WINDOW
    # 窗口大小是否来自默认值（True 时 TUI 显示「默认」提示）
    window_is_default: bool = True
    threshold: float = USAGE_WARN_RATIO
    usage: int = 0
    source: str = "estimated"
    # 是否已向用户展示过阈值警告（压缩成功后复位）
    warned: bool = False

    def update(self, tokens: int, *, source: str) -> None:
        self.usage = max(0, tokens)
        self.source = source

    def estimate_from_messages(self, messages: Sequence[dict[str, Any]]) -> None:
        self.update(estimate_messages_tokens(messages), source="estimated")

    @property
    def percent(self) -> int:
        if self.window <= 0:
            return 0
        return round(self.usage / self.window * 100)

    @property
    def blocked(self) -> bool:
        """用量达到阈值：暂停接受新的普通提示词。"""
        return self.window > 0 and self.usage >= self.window * self.threshold

    def label(self) -> str:
        """生成 TUI 状态栏用的「已用k/窗口k 百分比」文本。"""

        def fmt(tokens: int) -> str:
            k = tokens / 1024
            return f"{k:.1f}k" if k < 100 else f"{k:.0f}k"

        default_mark = "（默认）" if self.window_is_default else ""
        return f"上下文 {fmt(self.usage)}/{fmt(self.window)}{default_mark} {self.percent}%"
