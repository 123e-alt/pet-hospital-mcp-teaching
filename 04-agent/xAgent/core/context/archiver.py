"""上下文归档：把压缩前的完整会话保存为 JSONL，并提供本地关键词检索。

归档目录约定：``<启动目录>/.agents/context/``，与技能目录 ``.agents/skills/``
并列，跟随启动目录。每个归档一个文件，文件名即归档编号（如
``20261104-153000.jsonl``）。

文件格式（JSONL，每行一个 JSON 对象）::

    {"type": "meta", "archive_id": "...", "created_at": "...", ...}
    {"type": "message", "index": 0, "role": "system", "content": "..."}
    {"type": "message", "index": 1, "role": "user", "content": "..."}
    {"type": "message", "index": 2, "role": "assistant", "content": null,
     "tool_calls": [...]}
    {"type": "message", "index": 3, "role": "tool", "tool_call_id": "...",
     "content": "..."}

检索为纯 Python 全文关键词匹配（大小写不敏感），不使用向量数据库。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

ARCHIVE_SUFFIX = ".jsonl"

# 检索片段的展示窗口：命中点前 80 / 后 240 字符
_FRAGMENT_BEFORE = 80
_FRAGMENT_AFTER = 240


@dataclass(frozen=True)
class ArchiveInfo:
    """一个归档文件的描述信息。"""

    id: str
    path: Path
    message_count: int
    size_bytes: int


class ContextArchiver:
    """负责归档的保存、列举与检索。"""

    def __init__(self, context_dir: Path) -> None:
        self._dir = context_dir

    @property
    def context_dir(self) -> Path:
        return self._dir

    # ---------- 保存 ----------

    def save(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        model_name: str,
        token_usage: int,
    ) -> ArchiveInfo:
        """保存当前会话为归档文件。

        任何磁盘 IO 失败都会抛出 OSError，由调用方中止压缩流程
        （保证「归档成功后才压缩」的顺序）。
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        base_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_id = base_id
        path = self._dir / f"{archive_id}{ARCHIVE_SUFFIX}"
        counter = 1
        while path.exists():  # 同一秒内多次压缩时避免覆盖：追加序号（-2、-3…）
            counter += 1
            archive_id = f"{base_id}-{counter}"
            path = self._dir / f"{archive_id}{ARCHIVE_SUFFIX}"

        meta = {
            "type": "meta",
            "archive_id": archive_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "model": model_name,
            "token_usage_before_compaction": token_usage,
            "message_count": len(messages),
        }
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for index, message in enumerate(messages):
                record: dict[str, Any] = {
                    "type": "message",
                    "index": index,
                    "role": message.get("role"),
                    "content": message.get("content"),
                }
                if message.get("tool_calls"):
                    record["tool_calls"] = message["tool_calls"]
                if message.get("tool_call_id"):
                    record["tool_call_id"] = message["tool_call_id"]
                if message.get("name"):
                    record["name"] = message["name"]
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return ArchiveInfo(archive_id, path, len(messages), path.stat().st_size)

    # ---------- 列举 ----------

    def list_archives(self) -> list[ArchiveInfo]:
        """列出全部归档，按编号（即时间）倒序——最新的在前。"""
        if not self._dir.is_dir():
            return []
        infos: list[ArchiveInfo] = []
        for path in self._dir.glob(f"*{ARCHIVE_SUFFIX}"):
            count = 0
            try:
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        if f'"type": "message"' in line or '"type":"message"' in line:
                            count += 1
            except OSError:
                continue
            infos.append(ArchiveInfo(path.stem, path, count, path.stat().st_size))
        infos.sort(key=lambda info: info.id, reverse=True)
        return infos

    # ---------- 检索 ----------

    def search(
        self,
        text: str,
        archive_id: str | None = None,
        *,
        max_results: int = 10,
        max_chars: int = 4000,
    ) -> str:
        """在归档中做关键词全文检索，返回带出处的片段文本。

        匹配规则：先按完整短语匹配；若全局无命中且关键词含多个词，
        再按「所有词同时出现（AND）」匹配一次。
        """
        text = (text or "").strip()
        if not text:
            return "错误：检索关键词不能为空"

        archives = self._resolve(archive_id)
        if archive_id and not archives:
            known = "、".join(info.id for info in self.list_archives()) or "（无）"
            return f"错误：找不到归档「{archive_id}」。可用的归档编号：{known}"

        lowered = text.lower()
        terms = lowered.split()
        use_terms = len(terms) > 1

        blocks: list[str] = []
        matched = 0
        used_chars = 0
        truncated = False

        for info in archives:
            for record in self._load_messages(info.path):
                haystack = _haystack(record)
                if not haystack:
                    continue
                hay_lower = haystack.lower()
                if lowered in hay_lower:
                    hit_at = hay_lower.find(lowered)
                    needle = lowered
                elif use_terms and all(t in hay_lower for t in terms):
                    hit_at = min(
                        (hay_lower.find(t) for t in terms if t in hay_lower),
                        default=-1,
                    )
                    needle = ""
                else:
                    continue

                matched += 1
                fragment = _fragment(haystack, hit_at, needle)
                role = record.get("role") or "?"
                suffix = f"({record['name']})" if record.get("name") else ""
                block = f"[{info.id}] #{record.get('index', '?')} {role}{suffix}\n{fragment}"
                if len(blocks) >= max_results or used_chars + len(block) > max_chars:
                    truncated = True
                    break
                blocks.append(block)
                used_chars += len(block)
            if truncated:
                break

        return self._render(text, matched, blocks, truncated, archives)

    # ---------- 内部 ----------

    def _resolve(self, archive_id: str | None) -> list[ArchiveInfo]:
        if archive_id:
            path = self._dir / f"{archive_id}{ARCHIVE_SUFFIX}"
            if not path.is_file():
                return []
            return [ArchiveInfo(path.stem, path, 0, path.stat().st_size)]
        return self.list_archives()

    @staticmethod
    def _load_messages(path: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if record.get("type") == "message":
                        records.append(record)
        except OSError:
            pass
        return records

    def _render(
        self,
        text: str,
        matched: int,
        blocks: list[str],
        truncated: bool,
        archives: list[ArchiveInfo],
    ) -> str:
        if matched == 0:
            known = "、".join(f"{a.id}({a.message_count}条)" for a in archives) or "（无）"
            return (
                f"未找到与「{text}」匹配的内容。当前可检索的归档：{known}。"
                "可尝试其他关键词，或省略 id 在全部归档中检索。"
            )
        header = (
            f"检索「{text}」→ 命中 {matched} 处"
            f"{'（已截断，建议用更具体的关键词或指定 id）' if truncated else ''}，"
            f"归档目录：{self._dir}"
        )
        footer = "以上片段来自原始上下文归档，可用 id 参数限定单个归档查看完整上下文。"
        return "\n\n".join([header, *blocks, footer])


def _haystack(record: dict[str, Any]) -> str:
    """把一条归档消息拼成可检索的纯文本。"""
    parts: list[str] = []
    content = record.get("content")
    if isinstance(content, str) and content:
        parts.append(content)
    for call in record.get("tool_calls") or ():
        function = call.get("function", {})
        if function.get("name"):
            parts.append(str(function["name"]))
        if function.get("arguments"):
            parts.append(str(function["arguments"]))
    if record.get("name"):
        parts.append(str(record["name"]))
    return "\n".join(parts)


def _fragment(haystack: str, hit_at: int, needle: str) -> str:
    """取命中点附近的展示片段，压平换行。"""
    if hit_at < 0:
        hit_at = 0
    start = max(0, hit_at - _FRAGMENT_BEFORE)
    end = min(len(haystack), hit_at + _FRAGMENT_AFTER)
    snippet = haystack[start:end].replace("\n", " ⏎ ")
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(haystack) else ""
    return f"{prefix}{snippet}{suffix}"
