"""会话持久化：把聊天历史保存为 JSONL 文件，供 /save、/new、/resume 使用。

目录约定：``<启动目录>/.agents/sessions/``，与 ``.agents/context/``、
``.agents/skills/`` 并列，跟随启动目录。每个会话一个文件，文件名即
会话编号（如 ``20261104-160000.jsonl``）。

文件格式（JSONL，每行一个 JSON 对象）::

    {"type": "meta", "session_id": "...", "created_at": "...",
     "model": "...", "message_count": 12, "token_usage": 3400,
     "preview": "第一句用户输入…"}
    {"type": "message", "index": 0, "message": {...OpenAI 消息原样...}}
    ...

保存的是完整 OpenAI 格式消息列表（含 system 注入与压缩摘要），
恢复时无需任何转换即可继续会话——包括 AGENTS.md 的「一次注入」
内容也随历史一起持久化与复用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

SESSION_SUFFIX = ".jsonl"

# 会话列表里展示的首条用户输入预览长度（字符）
PREVIEW_MAX_CHARS = 60


@dataclass(frozen=True)
class SessionInfo:
    """一个已保存会话的描述信息。"""

    id: str
    path: Path
    created_at: str
    model: str
    message_count: int
    token_usage: int
    preview: str


class SessionStore:
    """负责会话的保存、列举与恢复。"""

    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir

    @property
    def sessions_dir(self) -> Path:
        return self._dir

    # ---------- 保存 ----------

    def save(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        model_name: str,
        token_usage: int = 0,
    ) -> SessionInfo:
        """把当前消息列表保存为新会话文件。

        磁盘 IO 失败会抛出 OSError，由调用方提示用户。
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        base_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = base_id
        path = self._dir / f"{session_id}{SESSION_SUFFIX}"
        counter = 1
        while path.exists():  # 同一秒内多次保存时避免覆盖：追加序号（-2、-3…）
            counter += 1
            session_id = f"{base_id}-{counter}"
            path = self._dir / f"{session_id}{SESSION_SUFFIX}"

        meta = {
            "type": "meta",
            "session_id": session_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "model": model_name,
            "message_count": len(messages),
            "token_usage": token_usage,
            "preview": _preview_of(messages),
        }
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for index, message in enumerate(messages):
                record = {"type": "message", "index": index, "message": message}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return SessionInfo(
            id=session_id,
            path=path,
            created_at=meta["created_at"],
            model=model_name,
            message_count=len(messages),
            token_usage=token_usage,
            preview=meta["preview"],
        )

    # ---------- 列举 ----------

    def list_sessions(self) -> list[SessionInfo]:
        """列出全部已保存会话，按编号（即时间）倒序——最新的在前。"""
        if not self._dir.is_dir():
            return []
        infos: list[SessionInfo] = []
        for path in self._dir.glob(f"*{SESSION_SUFFIX}"):
            info = self._read_meta(path)
            if info is not None:
                infos.append(info)
        infos.sort(key=lambda info: info.id, reverse=True)
        return infos

    # ---------- 恢复 ----------

    def load(self, session_id: str) -> list[dict[str, Any]]:
        """按编号恢复一个会话，返回完整的 OpenAI 格式消息列表。

        找不到会话时抛出 FileNotFoundError。
        """
        path = self._dir / f"{session_id}{SESSION_SUFFIX}"
        if not path.is_file():
            raise FileNotFoundError(f"找不到会话「{session_id}」：{path}")

        messages: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 跳过损坏行，尽量恢复其余内容
                if record.get("type") == "message":
                    message = record.get("message")
                    if isinstance(message, dict):
                        messages.append(message)
        return messages

    # ---------- 内部 ----------

    def _read_meta(self, path: Path) -> SessionInfo | None:
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    meta = json.loads(line)
                    if meta.get("type") != "meta":
                        break
                    return SessionInfo(
                        id=meta.get("session_id") or path.stem,
                        path=path,
                        created_at=meta.get("created_at", ""),
                        model=meta.get("model", ""),
                        message_count=int(meta.get("message_count", 0)),
                        token_usage=int(meta.get("token_usage", 0)),
                        preview=meta.get("preview", ""),
                    )
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return None
        return None


def _preview_of(messages: Sequence[dict[str, Any]]) -> str:
    """取第一条用户输入作为会话列表预览，压平换行并截断。"""
    preview = ""
    for message in messages:
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                preview = content
                break
    preview = preview.replace("\r", " ").replace("\n", " ").strip()
    if len(preview) > PREVIEW_MAX_CHARS:
        preview = preview[:PREVIEW_MAX_CHARS] + "…"
    return preview
