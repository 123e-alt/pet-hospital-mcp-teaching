# chat-stream-tool-fileOps.py 项目说明

## 一、文件简介

`chat-stream-tool-fileOps.py` 是一个基于 OpenAI SDK 的**流式（stream）对话式本地文件系统操作助手**。程序在无限对话循环中运行，通过 **Function Calling（工具调用）** 机制，让大模型按需调用本地工具完成文件与目录的查询、创建、编辑、删除、重命名等操作。

核心设计要点：

- **配置外置**：从 `config.ini` 读取 `api_key`、`base_url`、`model_name`，并据此初始化 OpenAI 客户端。
- **流式输出**：`client.chat.completions.create(..., stream=True)`，`content` 逐块实时打印；`tool_calls` 按 `index` 聚合 `id` / `name` / `arguments`。
- **工具循环（Agent Loop）**：模型返回 `tool_calls` 时执行工具、把结果以 `role=tool` 消息写回 `messages`，然后再次请求模型，直至模型给出最终自然语言回复。
- **文本安全校验**：内置 `TEXT_EXTENSIONS` / `NON_TEXT_EXTENSIONS` 白黑名单，并对未知扩展名读取前 8KB 探测控制字符，判断是否为纯文本，避免读写二进制文件。
- **破坏性操作护栏**：`deleteDir` / `deleteFile` / `rename` 默认只返回**预览**，必须显式传入 `confirm=true` 才真正执行；`rename` 采用两阶段重命名并在失败时回滚。
- **健壮性处理**：`run_command` 自动兼容 UTF-8 / GBK 解码；`readFile` 编码回退（utf-8 → gbk → gb2312 → latin-1）并对超过 100KB 的内容截断；`readDir` 相关遍历捕获 `PermissionError`。

整体架构见同目录下的 `fileOps_arch.mmd`（Mermaid 格式），共分五层：配置与初始化层、程序入口主循环层、工具调度层、公共辅助函数层、工具实现层（含外部依赖）。

## 二、工具列表

| 工具名 | 简述 |
| --- | --- |
| `getDate` | 获取当前电脑的日期和时间（调用 `date /t`、`time /t`）。 |
| `isLeapYear` | 判断指定年份是否为闰年（4/100/400 规则）。 |
| `getCWD` | 获取当前工作目录（`os.getcwd()`）。 |
| `listDir` | 列出指定目录下所有文件和子目录，返回类型、大小、修改时间，支持递归。 |
| `getFileType` | 获取路径的类型信息：扩展名、是否纯文本、大小、修改时间。 |
| `readFile` | 读取指定纯文本文件内容，自动编码回退，超长内容截断前 100KB。 |
| `createFile` | 在指定目录下创建新的纯文本文件，目录不存在会自动创建，文件已存在则报错。 |
| `editFile` | 编辑纯文本文件内容，支持 `overwrite`（覆盖）与 `append`（追加）。 |
| `createDir` | 创建新目录，父目录不存在时一并创建。 |
| `deleteDir` | 删除目录及其全部内容，默认仅预览，需 `confirm=true` 才执行。 |
| `deleteFile` | 删除指定文件，默认仅预览，需 `confirm=true` 才执行。 |
| `rename` | 重命名文件或目录（可跨目录移动），默认仅预览，需 `confirm=true` 才执行。 |

## 三、使用示例

### 1. 准备配置

在脚本同目录创建 `config.ini`：

```ini
[LLM]
api_key = sk-xxxxxxxxxxxxxxxx
base_url = https://api.openai.com/v1
model_name = gpt-4o-mini
```

### 2. 启动程序

```bash
python chat-stream-tool-fileOps.py
```

启动后进入无限对话模式，按 `Ctrl+C` 退出：

```
=== 已开启带文件操作工具的无限对话模式，按 Ctrl+C 强行退出 ===
你: 看看当前目录下有哪些文件
AI: 
[调用工具] listDir({"path": ".", "recursive": false})
[工具返回] 目录：C:\Users\qq\Desktop\作业\Practice02（共 6 项）
[文件] chat-stream-tool-fileOps.py | 大小: 23224 | 修改时间: 2026-10-20 11:29
...
AI: 当前目录下共有 6 个文件、1 个子目录，主要包括脚本文件与配置文件……
```

### 3. 典型对话示例

**示例 A：读取并总结文本文件**

```
你: 读一下 config.ini 的内容，告诉我用的哪个模型
AI:
[调用工具] readFile({"path": "config.ini"})
[工具返回] [LLM]
api_key = ...
model_name = gpt-4o-mini
AI: 配置文件里使用的模型是 gpt-4o-mini。
```

**示例 B：创建目录与文件**

```
你: 在 notes 目录下新建 todo.md，内容写"待办：整理架构图"
AI:
[调用工具] createFile({"dir_path": "notes", "filename": "todo.md", "content": "待办：整理架构图"})
[工具返回] 成功创建文件：C:\...\Practice02\notes\todo.md
AI: 已在 notes 目录下创建 todo.md 并写入待办内容。
```

**示例 C：破坏性操作需二次确认**

```
你: 把 draft 目录删掉
AI:
[调用工具] deleteDir({"path": "draft"})
[工具返回] ⚠️ 即将删除目录及其全部内容：C:\...\draft
共 3 项，预览前 20 项：
C:\...\draft\a.txt
C:\...\draft\b.txt
C:\...\draft\sub
若确认删除，请调用时传入 confirm=True
AI: 我确认到该目录下有 3 项内容，是否确认删除？

你: 确认删除
AI:
[调用工具] deleteDir({"path": "draft", "confirm": true})
[工具返回] 成功删除目录：C:\...\draft
AI: draft 目录已删除。
```

**示例 D：重命名与移动**

```
你: 把 fileOps_arch.mmd 移动改名成 docs/arch.mmd
AI:
[调用工具] rename({"old_path": "fileOps_arch.mmd", "new_path": "docs/arch.mmd"})
[工具返回] ⚠️ 即将重命名：C:\...\fileOps_arch.mmd → docs\arch.mmd
若确认执行，请调用时传入 confirm=True
AI: 是否确认执行该重命名操作？
```

### 4. 注意事项

- 所有相对路径都会通过 `resolve_path` 转为绝对路径，以当前脚本运行的工作目录为基准。
- `readFile` / `editFile` 仅支持纯文本格式；图片、二进制程序等会返回错误提示。
- `deleteDir`、`deleteFile`、`rename` 必须先看到预览，用户明确表示"确认/执行"后再传 `confirm=true`。
- Windows 下路径分隔符与命令（`date /t`、`time /t`）已做适配；`rename` 使用临时名两阶段重命名，规避 Windows 同名冲突。
