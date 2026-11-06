"""SKILL.md 的 YAML Frontmatter 解析。

发现阶段只逐行读到 Frontmatter 结束标记为止，不读取正文；
解析器只依赖标准库，覆盖 Agent Skills 常见的 `key: value`、引号标量、
`|` / `>` 块标量（含 `-` / `+` 截断标记）与缩进续行。
"""

from __future__ import annotations

import re
from pathlib import Path

_KEY_PATTERN = re.compile(r"^([A-Za-z0-9_.\-]+)\s*:\s*(.*)$")


class FrontmatterError(ValueError):
    """Frontmatter 缺失、未闭合或内容非法。"""


def read_frontmatter(path: str | Path) -> dict[str, str]:
    """只读取文件开头的 Frontmatter，遇到结束标记立即停止。"""
    file_path = Path(path)
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return _read_with_encoding(file_path, encoding)
        except UnicodeDecodeError:
            continue
    raise FrontmatterError(f"无法解码文件：{file_path}")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """解析内存中的 SKILL.md 文本，返回 (元数据, 正文)。

    没有 Frontmatter 或未闭合时，元数据为空、正文即原文，交由调用方补齐。
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("\ufeff"):
        normalized = normalized[1:]
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, normalized

    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return _parse_lines(lines[1:index]), "\n".join(lines[index + 1 :])
    return {}, normalized


def _read_with_encoding(path: Path, encoding: str) -> dict[str, str]:
    lines: list[str] = []
    with path.open("r", encoding=encoding) as handle:
        first = handle.readline()
        if first.strip() != "---":
            raise FrontmatterError("文件未以 YAML Frontmatter（---）开头")

        for line in handle:
            if line.strip() in ("---", "..."):
                return _parse_lines(lines)
            lines.append(line.rstrip("\r\n"))

    raise FrontmatterError("YAML Frontmatter 缺少结束标记（---）")


def _parse_lines(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue

        match = _KEY_PATTERN.match(line)
        if match is None:
            index += 1
            continue

        key, raw_value = match.group(1), match.group(2).strip()
        index += 1
        indented, index = _collect_indented(lines, index)

        if raw_value[:1] in ("|", ">"):
            result[key] = _block_scalar(raw_value, indented)
        elif len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in ("'", '"'):
            result[key] = raw_value[1:-1]
        else:
            parts = ([raw_value] if raw_value else []) + indented
            result[key] = " ".join(part for part in parts if part).strip()

    return result


def _collect_indented(lines: list[str], start: int) -> tuple[list[str], int]:
    """收集从 start 起属于当前值的缩进行，允许中间出现空行。"""
    collected: list[str] = []
    pending_blanks = 0
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            pending_blanks += 1
            index += 1
            continue
        if not line.startswith((" ", "\t")):
            break
        if pending_blanks:
            collected.extend([""] * pending_blanks)
            pending_blanks = 0
        collected.append(line.strip())
        index += 1
    return collected, index


def _block_scalar(indicator: str, indented: list[str]) -> str:
    """处理 `|`（保留换行）与 `>`（折叠为空格）两种块标量。"""
    folded = indicator.startswith(">")
    chomp = indicator[1:2]

    if folded:
        value = " ".join(part for part in indented if part)
    else:
        value = "\n".join(indented)

    if chomp != "+":
        value = value.rstrip("\n")
        if not folded:
            value = value.rstrip()
    return value
