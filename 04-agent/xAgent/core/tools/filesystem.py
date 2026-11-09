"""文件系统工具集：业务实现与界面完全解耦。"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from core.tools.base import Tool

# 纯文本扩展名列表（用于判断 readFile/editFile 的可用性）
TEXT_EXTENSIONS = {
    ".txt", ".py", ".md", ".json", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".log", ".csv", ".html", ".htm", ".css", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".cpp", ".c", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php",
    ".sh", ".bat", ".ps1", ".xml", ".sql", ".gradle", ".properties", ".toml",
    ".rst", ".org", ".mmd", ".mermaid", ".vue", ".tsv",
}

# 常见二进制/非文本扩展名（遇到直接判定为非文本）
NON_TEXT_EXTENSIONS = {
    ".bin", ".exe", ".dll", ".sys", ".so", ".dylib",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".wav", ".flac",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".class", ".jar", ".war", ".ear",
    ".pyc", ".pyo", ".db", ".sqlite", ".sqlite3",
}


class FileSystemToolkit:
    """所有文件操作均以 ``workspace`` 为相对路径基准目录。"""

    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = (workspace or Path.cwd()).resolve()

    # ---------- 路径与文本判定 ----------

    def _resolve(self, path: str) -> Path:
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = self.workspace / target
        resolved = target.resolve()
        # 路径边界保护：禁止 ../ 或绝对路径逃逸出工作目录
        if resolved != self.workspace and self.workspace not in resolved.parents:
            raise ValueError(f"路径越界：{path} 超出工作目录 {self.workspace}")
        return resolved

    @staticmethod
    def _is_text_file(path: Path) -> bool:
        ext = path.suffix.lower()
        if ext in NON_TEXT_EXTENSIONS:
            return False
        if ext in TEXT_EXTENSIONS:
            return True
        # 无扩展名或未知扩展名：尝试解码前 8KB，若无控制字符则判为纯文本
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
            text = chunk.decode("utf-8")
            control_chars = set(chr(c) for c in range(32) if c not in (9, 10, 13)) | {chr(127)}
            return not any(c in control_chars for c in text)
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            return False

    # ---------- 查询类工具 ----------

    def get_cwd(self) -> str:
        """获取当前工作目录（workspace 根目录）。"""
        return str(self.workspace)

    def list_dir(self, path: str = ".", recursive: bool = False) -> str:
        """列出指定目录下所有文件和子目录。"""
        target = self._resolve(path)
        if not target.exists():
            return f"错误：目录不存在 - {target}"
        if not target.is_dir():
            return f"错误：不是目录 - {target}"

        entries = []
        try:
            iterator = target.rglob("*") if recursive else target.iterdir()
            for item in iterator:
                try:
                    rel = item.relative_to(target)
                    entry_type = "目录" if item.is_dir() else "文件"
                    size = item.stat().st_size if item.is_file() else "-"
                    mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    entries.append(f"[{entry_type}] {rel} | 大小: {size} | 修改时间: {mtime}")
                except PermissionError:
                    entries.append(f"[权限不足] {item}")
        except PermissionError:
            return f"错误：无权限访问目录 - {target}"

        if not entries:
            return f"目录为空：{target}"
        header = f"目录：{target}（共 {len(entries)} 项）"
        return header + "\n" + "\n".join(entries)

    def get_file_type(self, path: str) -> str:
        """获取指定路径的类型信息。"""
        target = self._resolve(path)
        if not target.exists():
            return f"错误：路径不存在 - {target}"
        if target.is_dir():
            return f"类型：目录 | 路径：{target}"

        ext = target.suffix.lower()
        is_text = self._is_text_file(target)
        size = target.stat().st_size
        mtime = datetime.fromtimestamp(target.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return (
            f"类型：文件\n"
            f"扩展名：{ext if ext else '(无)'}\n"
            f"是否纯文本：{'是' if is_text else '否'}\n"
            f"大小：{size} 字节\n"
            f"修改时间：{mtime}\n"
            f"路径：{target}"
        )

    def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """读取指定纯文本文件的内容。"""
        target = self._resolve(path)
        if not target.exists():
            return f"错误：文件不存在 - {target}"
        if not target.is_file():
            return f"错误：不是文件 - {target}"
        if not self._is_text_file(target):
            return f"错误：非纯文本文件，无法读取内容 - {target}"

        try:
            with open(target, "r", encoding=encoding) as f:
                content = f.read()
        except UnicodeDecodeError:
            for fallback in ("gbk", "gb2312", "latin-1"):
                try:
                    with open(target, "r", encoding=fallback) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return f"错误：无法用常见编码解码文件 - {target}"

        # 大文件截断前 100KB，避免输出过长
        if len(content) > 100_000:
            content = content[:100_000] + "\n...（内容过长，已截断前 100KB）"
        return content

    # ---------- 写入类工具 ----------

    def create_file(self, dir_path: str, filename: str, content: str = "") -> str:
        """在指定目录下创建新文件，目录不存在时自动创建。"""
        dir_abs = self._resolve(dir_path)
        dir_abs.mkdir(parents=True, exist_ok=True)

        file_path = dir_abs / filename
        if file_path.exists():
            return f"错误：文件已存在 - {file_path}"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"成功创建文件：{file_path}"

    def edit_file(self, path: str, content: str, mode: str = "overwrite") -> str:
        """编辑纯文本文件内容，支持覆盖与追加。"""
        target = self._resolve(path)
        if not target.exists():
            return f"错误：文件不存在 - {target}。若需新建，请使用 createFile。"
        if not target.is_file():
            return f"错误：不是文件 - {target}"
        if not self._is_text_file(target):
            return f"错误：非纯文本文件，无法编辑 - {target}"

        if mode == "append":
            with open(target, "a", encoding="utf-8") as f:
                f.write(content)
            return f"成功追加内容到文件：{target}"
        if mode == "overwrite":
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            return f"成功覆盖文件内容：{target}"
        return f"错误：不支持的 mode={mode}，仅支持 overwrite / append"

    def create_dir(self, path: str) -> str:
        """创建目录，父目录不存在时一并创建。"""
        target = self._resolve(path)
        if target.exists():
            if target.is_dir():
                return f"目录已存在：{target}"
            return f"错误：同名路径是文件，无法创建目录 - {target}"

        target.mkdir(parents=True, exist_ok=False)
        return f"成功创建目录：{target}"

    # ---------- 破坏性操作（默认仅预览） ----------

    def delete_dir(self, path: str, confirm: bool = False) -> str:
        """删除目录（含全部内容），必须 confirm=True 才执行。"""
        target = self._resolve(path)
        if not target.exists():
            return f"错误：目录不存在 - {target}"
        if not target.is_dir():
            return f"错误：不是目录 - {target}"

        if not confirm:
            items = list(target.rglob("*"))
            preview = "\n".join([str(p) for p in items[:20]]) + ("..." if len(items) > 20 else "")
            return (
                f"⚠️ 即将删除目录及其全部内容：{target}\n"
                f"共 {len(items)} 项，预览前 20 项：\n{preview}\n"
                f"若确认删除，请调用时传入 confirm=True"
            )

        shutil.rmtree(target)
        return f"成功删除目录：{target}"

    def delete_file(self, path: str, confirm: bool = False) -> str:
        """删除文件，必须 confirm=True 才执行。"""
        target = self._resolve(path)
        if not target.exists():
            return f"错误：文件不存在 - {target}"
        if not target.is_file():
            return f"错误：不是文件 - {target}"

        if not confirm:
            size = target.stat().st_size
            return (
                f"⚠️ 即将删除文件：{target}（大小：{size} 字节）\n"
                f"若确认删除，请调用时传入 confirm=True"
            )

        os.remove(target)
        return f"成功删除文件：{target}"

    def rename(self, old_path: str, new_path: str, confirm: bool = False) -> str:
        """重命名文件或目录（可跨目录移动），必须 confirm=True 才执行。"""
        old = self._resolve(old_path)
        new = self._resolve(new_path)

        if not old.exists():
            return f"错误：源路径不存在 - {old}"
        if old == new:
            return "错误：新旧路径相同"

        if not confirm:
            return (
                f"⚠️ 即将重命名：{old} → {new}\n"
                f"若确认执行，请调用时传入 confirm=True"
            )

        if new.exists():
            if new.is_file():
                os.remove(new)
            else:
                shutil.rmtree(new)

        # 两阶段重命名：先临时名再最终名（避免 Windows 冲突）
        tmp = old.parent / f".__rename_tmp_{datetime.now().timestamp()}"
        try:
            old.rename(tmp)
            tmp.rename(new)
        except OSError as exc:
            if tmp.exists():
                try:
                    tmp.rename(old)
                except OSError:
                    pass
            return f"错误：重命名失败 - {exc}"

        return f"成功重命名：{old} → {new}"


def build_filesystem_tools(toolkit: FileSystemToolkit) -> list[Tool]:
    """构造全部文件系统工具及其 schema。"""
    return [
        Tool(
            name="getCWD",
            description="获取当前工作目录（Agent 的相对路径基准目录）。",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=toolkit.get_cwd,
        ),
        Tool(
            name="listDir",
            description="列出指定目录下所有文件和子目录，返回每项的类型（文件/目录）、大小、修改时间。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径，默认为当前目录 '.'",
                        "default": ".",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出所有子目录，默认 false",
                        "default": False,
                    },
                },
                "required": [],
            },
            handler=toolkit.list_dir,
        ),
        Tool(
            name="getFileType",
            description="获取指定文件或目录的类型信息：扩展名、是否纯文本、大小、修改时间。",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "文件或目录的路径"}},
                "required": ["path"],
            },
            handler=toolkit.get_file_type,
        ),
        Tool(
            name="readFile",
            description="读取指定纯文本文件的内容。非纯文本文件（如图片、二进制程序）无法读取，会返回错误提示。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要读取的纯文本文件路径"},
                    "encoding": {
                        "type": "string",
                        "description": "文件编码，默认 utf-8。解码失败时会自动尝试 gbk 等常见编码",
                        "default": "utf-8",
                    },
                },
                "required": ["path"],
            },
            handler=toolkit.read_file,
        ),
        Tool(
            name="createFile",
            description="在指定目录下创建新的纯文本文件。若目录不存在会自动创建；若文件已存在会返回错误。",
            parameters={
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "目标目录路径"},
                    "filename": {"type": "string", "description": "文件名（含扩展名，如 'README.md'）"},
                    "content": {
                        "type": "string",
                        "description": "文件初始内容，默认为空字符串",
                        "default": "",
                    },
                },
                "required": ["dir_path", "filename"],
            },
            handler=toolkit.create_file,
        ),
        Tool(
            name="editFile",
            description="编辑指定纯文本文件的内容。mode 为 overwrite 时覆盖原内容，为 append 时追加到末尾。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要编辑的纯文本文件路径"},
                    "content": {"type": "string", "description": "要写入的文本内容"},
                    "mode": {
                        "type": "string",
                        "enum": ["overwrite", "append"],
                        "description": "写入模式：overwrite=覆盖（默认），append=追加",
                        "default": "overwrite",
                    },
                },
                "required": ["path", "content"],
            },
            handler=toolkit.edit_file,
        ),
        Tool(
            name="createDir",
            description="创建新目录，若父目录不存在会一并创建。若目录已存在则返回提示。",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "要创建的目录路径"}},
                "required": ["path"],
            },
            handler=toolkit.create_dir,
        ),
        Tool(
            name="deleteDir",
            description="删除目录（包含所有子文件和子目录）。默认只返回预览，必须传入 confirm=true 才真正执行。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的目录路径"},
                    "confirm": {
                        "type": "boolean",
                        "description": "必须设为 true 才会实际删除，默认 false",
                        "default": False,
                    },
                },
                "required": ["path"],
            },
            handler=toolkit.delete_dir,
        ),
        Tool(
            name="deleteFile",
            description="删除指定文件。默认只返回预览，必须传入 confirm=true 才真正执行。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的文件路径"},
                    "confirm": {
                        "type": "boolean",
                        "description": "必须设为 true 才会实际删除，默认 false",
                        "default": False,
                    },
                },
                "required": ["path"],
            },
            handler=toolkit.delete_file,
        ),
        Tool(
            name="rename",
            description="重命名文件或目录（可跨目录移动）。默认只返回预览，必须传入 confirm=true 才真正执行。",
            parameters={
                "type": "object",
                "properties": {
                    "old_path": {"type": "string", "description": "原路径"},
                    "new_path": {"type": "string", "description": "新路径（目标若已存在会被覆盖）"},
                    "confirm": {
                        "type": "boolean",
                        "description": "必须设为 true 才会实际执行，默认 false",
                        "default": False,
                    },
                },
                "required": ["old_path", "new_path"],
            },
            handler=toolkit.rename,
        ),
    ]
