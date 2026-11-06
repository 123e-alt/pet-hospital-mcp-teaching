"""聊天区组件：只负责消息渲染，不感知 Agent 内部实现。"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static


class ChatView(VerticalScroll):
    """按消息块累积展示对话内容，支持助手消息流式追加。"""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._streaming: Static | None = None
        self._stream_buffer = ""

    # ---------- 对外渲染 API ----------

    def add_system(self, text: str) -> None:
        self._mount_message("system", text)

    def add_user(self, text: str) -> None:
        self._mount_message("user", f"你 › {text}")

    def append_assistant(self, text: str) -> None:
        """追加助手文本；首次调用时创建当前流式消息块。"""
        self._stream_buffer += text
        if self._streaming is None:
            self._streaming = Static("", markup=False, classes="message assistant")
            self.mount(self._streaming)
        self._streaming.update(self._stream_buffer)
        self.call_after_refresh(self.scroll_end, animate=False)

    def end_assistant(self) -> None:
        """结束当前流式消息块，后续文本将开启新的段落。"""
        self._streaming = None
        self._stream_buffer = ""

    def add_tool_call(self, name: str, arguments: str) -> None:
        self.end_assistant()
        self._mount_message("tool-call", f"⚙ 调用 {name}({_preview(arguments, 400)})")

    def add_tool_result(self, result: str, ok: bool) -> None:
        marker = "↳ 返回" if ok else "↳ 失败"
        role = "tool-result" if ok else "tool-error"
        self._mount_message(role, f"{marker}: {_preview(result, 1200)}")

    def add_error(self, message: str) -> None:
        self.end_assistant()
        self._mount_message("error", f"✖ {message}")

    # ---------- 内部实现 ----------

    def _mount_message(self, role: str, text: str) -> None:
        self.mount(Static(text, markup=False, classes=f"message {role}"))
        self.call_after_refresh(self.scroll_end, animate=False)


def _preview(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"…（已省略 {len(text) - limit} 字符）"
