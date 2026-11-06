import configparser
import json
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

from openai import OpenAI

# 1. 读取 config.ini 配置信息
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

api_key = config.get('LLM', 'api_key')
base_url = config.get('LLM', 'base_url')
model_name = config.get('LLM', 'model_name')

# 2. 初始化 OpenAI 客户端
client = OpenAI(api_key=api_key, base_url=base_url)


# ==================== 辅助函数 ====================

def run_command(command):
    """执行本地命令并返回输出文本（自动兼容 UTF-8 / GBK 编码）"""
    raw = subprocess.run(command, shell=True, capture_output=True).stdout
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore").strip()


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


def is_text_file(path):
    """判断文件是否为纯文本格式"""
    ext = Path(path).suffix.lower()
    if ext in NON_TEXT_EXTENSIONS:
        return False
    if ext in TEXT_EXTENSIONS:
        return True
    # 无扩展名或未知扩展名：尝试解码前 8KB，若无控制字符则判为纯文本
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        text = chunk.decode("utf-8")
        # 排除含 NUL 字节等控制字符的情况（允许换行/回车/Tab）
        control_chars = set(chr(c) for c in range(32) if c not in (9, 10, 13)) | {chr(127)}
        return not any(c in control_chars for c in text)
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return False


def resolve_path(path):
    """把相对路径转成绝对路径，避免歧义"""
    return Path(path).resolve()


# ==================== 原有 function call 工具 ====================

def get_date():
    date_text = run_command("date /t")
    time_text = run_command("time /t")
    return f"当前日期：{date_text}，当前时间：{time_text}"


def is_leap_year(year):
    year = int(year)
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return f"{year} 年是闰年。"
    return f"{year} 年不是闰年（平年）。"


# ==================== 新增：文件操作工具 ====================

def get_cwd():
    """1. 获取当前工作目录"""
    return os.getcwd()


def list_dir(path=".", recursive=False):
    """2. 列出指定目录下所有文件和子目录"""
    target = resolve_path(path)
    if not target.exists():
        return f"错误：目录不存在 - {target}"
    if not target.is_dir():
        return f"错误：不是目录 - {target}"

    entries = []
    try:
        if recursive:
            iterator = target.rglob("*")
        else:
            iterator = target.iterdir()

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


def get_file_type(path):
    """3. 获取指定文件的文件类型"""
    target = resolve_path(path)
    if not target.exists():
        return f"错误：路径不存在 - {target}"

    if target.is_dir():
        return f"类型：目录 | 路径：{target}"

    ext = target.suffix.lower()
    is_text = is_text_file(target)
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


def read_file(path, encoding="utf-8"):
    """4. 获取指定文件的内容（仅支持纯文本格式文件）"""
    target = resolve_path(path)
    if not target.exists():
        return f"错误：文件不存在 - {target}"
    if not target.is_file():
        return f"错误：不是文件 - {target}"
    if not is_text_file(target):
        return f"错误：非纯文本文件，无法读取内容 - {target}"

    # 优先用指定编码，UTF-8 失败回退 GBK
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


def create_file(dir_path, filename, content=""):
    """5. 根据指定的目录和文件名创建新文件"""
    dir_abs = resolve_path(dir_path)
    dir_abs.mkdir(parents=True, exist_ok=True)  # 自动创建父目录

    file_path = dir_abs / filename
    if file_path.exists():
        return f"错误：文件已存在 - {file_path}"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"成功创建文件：{file_path}"


def edit_file(path, content, mode="overwrite"):
    """6. 编辑指定文件的内容（仅支持纯文本格式文件）"""
    target = resolve_path(path)
    if not target.exists():
        return f"错误：文件不存在 - {target}。若需新建，请使用 createFile。"
    if not target.is_file():
        return f"错误：不是文件 - {target}"
    if not is_text_file(target):
        return f"错误：非纯文本文件，无法编辑 - {target}"

    if mode == "append":
        with open(target, "a", encoding="utf-8") as f:
            f.write(content)
        return f"成功追加内容到文件：{target}"
    elif mode == "overwrite":
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"成功覆盖文件内容：{target}"
    else:
        return f"错误：不支持的 mode={mode}，仅支持 overwrite / append"


def create_dir(path):
    """7. 创建新目录"""
    target = resolve_path(path)
    if target.exists():
        if target.is_dir():
            return f"目录已存在：{target}"
        else:
            return f"错误：同名路径是文件，无法创建目录 - {target}"

    target.mkdir(parents=True, exist_ok=False)
    return f"成功创建目录：{target}"


def delete_dir(path, confirm=False):
    """8. 删除目录（非空）——必须传 confirm=True 才执行"""
    target = resolve_path(path)
    if not target.exists():
        return f"错误：目录不存在 - {target}"
    if not target.is_dir():
        return f"错误：不是目录 - {target}"

    if not confirm:
        # 安全护栏：列出将被删除的内容，要求确认
        items = list(target.rglob("*"))
        preview = "\n".join([str(p) for p in items[:20]]) + ("..." if len(items) > 20 else "")
        return (
            f"⚠️ 即将删除目录及其全部内容：{target}\n"
            f"共 {len(items)} 项，预览前 20 项：\n{preview}\n"
            f"若确认删除，请调用时传入 confirm=True"
        )

    shutil.rmtree(target)
    return f"成功删除目录：{target}"


def delete_file(path, confirm=False):
    """9. 删除文件——必须传 confirm=True 才执行"""
    target = resolve_path(path)
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


def rename(old_path, new_path, confirm=False):
    """10. 重命名文件和目录——必须传 confirm=True 才执行"""
    old = resolve_path(old_path)
    new = Path(new_path)

    if not old.exists():
        return f"错误：源路径不存在 - {old}"
    if old == new:
        return f"错误：新旧路径相同"

    if not confirm:
        return (
            f"⚠️ 即将重命名：{old} → {new}\n"
            f"若确认执行，请调用时传入 confirm=True"
        )

    # 处理目标存在的情况
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
    except OSError as e:
        # 回滚
        if tmp.exists():
            try:
                tmp.rename(old)
            except OSError:
                pass
        return f"错误：重命名失败 - {e}"

    return f"成功重命名：{old} → {new}"


# ==================== 工具映射 & function call schema ====================

TOOL_FUNCTIONS = {
    # 原有
    "getDate": get_date,
    "isLeapYear": is_leap_year,
    # 新增：文件操作
    "getCWD": get_cwd,
    "listDir": list_dir,
    "getFileType": get_file_type,
    "readFile": read_file,
    "createFile": create_file,
    "editFile": edit_file,
    "createDir": create_dir,
    "deleteDir": delete_dir,
    "deleteFile": delete_file,
    "rename": rename,
}

tools = [
    # 原有工具
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间。当用户询问今天几号、现在几点、当前日期或时间时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断某一年是否为闰年。当用户询问某一年是不是闰年时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "要判断的年份，例如 2024。"}
                },
                "required": ["year"],
            },
        },
    },
    # 新增：文件操作工具
    {
        "type": "function",
        "function": {
            "name": "getCWD",
            "description": "获取当前工作目录（当前脚本运行时的工作目录）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listDir",
            "description": "列出指定目录下所有文件和子目录，返回每项的类型（文件/目录）、大小、修改时间。",
            "parameters": {
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
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getFileType",
            "description": "获取指定文件或目录的类型信息：扩展名、是否纯文本、大小、修改时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件或目录的路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "readFile",
            "description": "读取指定纯文本文件的内容。非纯文本文件（如图片、二进制程序）无法读取，会返回错误提示。",
            "parameters": {
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
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createFile",
            "description": "在指定目录下创建新的纯文本文件。若目录不存在会自动创建；若文件已存在会返回错误。",
            "parameters": {
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
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editFile",
            "description": "编辑指定纯文本文件的内容。mode 为 overwrite 时覆盖原内容，为 append 时追加到末尾。",
            "parameters": {
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
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createDir",
            "description": "创建新目录，若父目录不存在会一并创建。若目录已存在则返回提示。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要创建的目录路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteDir",
            "description": "删除目录（包含所有子文件和子目录）。默认只返回预览，必须传入 confirm=true 才真正执行。",
            "parameters": {
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
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteFile",
            "description": "删除指定文件。默认只返回预览，必须传入 confirm=true 才真正执行。",
            "parameters": {
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
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename",
            "description": "重命名文件或目录（可跨目录移动）。默认只返回预览，必须传入 confirm=true 才真正执行。",
            "parameters": {
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
        },
    },
]


def run_tool(name, arguments):
    """执行工具，并把结果转成字符串返回给 LLM"""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"未知的工具：{name}"
    kwargs = json.loads(arguments) if arguments else {}
    return str(func(**kwargs))


# ==================== 主循环 ====================
messages = [
    {
        "role": "system",
        "content": (
            "你是一个可以操作本地文件系统的AI助手。"
            "你可以通过调用工具来获取文件信息、创建/编辑/删除/重命名文件和目录。"
            "删除、重命名等破坏性操作需要先获取预览（默认返回），"
            "只有当用户明确要求执行时才传入 confirm=True 实际执行。"
        ),
    }
]

print("=== 已开启带文件操作工具的无限对话模式，按 Ctrl+C 强行退出 ===")

while True:
    try:
        user_input = input("你: ")
        messages.append({"role": "user", "content": user_input})

        while True:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools,
                stream=True,
            )

            ai_reply = ""
            tool_calls = {}
            print("AI: ", end="")
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    print(delta.content, end="", flush=True)
                    ai_reply += delta.content
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        item = tool_calls.setdefault(
                            tc.index, {"id": "", "name": "", "arguments": ""}
                        )
                        if tc.id:
                            item["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                item["name"] += tc.function.name
                            if tc.function.arguments:
                                item["arguments"] += tc.function.arguments

            if tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": ai_reply or None,
                    "tool_calls": [
                        {
                            "id": item["id"],
                            "type": "function",
                            "function": {"name": item["name"], "arguments": item["arguments"]},
                        }
                        for _, item in sorted(tool_calls.items())
                    ],
                })

                for _, item in sorted(tool_calls.items()):
                    print()
                    print(f"[调用工具] {item['name']}({item['arguments']})")
                    result = run_tool(item["name"], item["arguments"])
                    print(f"[工具返回] {result}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": item["id"],
                        "content": result,
                    })
                continue

            print()
            messages.append({"role": "assistant", "content": ai_reply})
            break

    except KeyboardInterrupt:
        print("\n已退出对话，再见！")
        break
