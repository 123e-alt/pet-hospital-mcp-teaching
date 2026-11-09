# xAgent

基于 `../Practice02/chat-stream-tool-fileOps.py` 的分层重构版本：**core 与界面彻底分离**，当前提供 Textual TUI，未来可平级扩展 `web/`、`desktop/`、`mobile/` 等前端。

## 1. 架构总览

```
                    ┌─────────────────────────────┐
                    │           main.py           │  装配/入口（唯一同时 import core 与前端）
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
      ┌───────────────┐                         ┌───────────────┐
      │      tui/     │                         │  web/ desktop/ │
      │   Textual     │                         │  mobile/ ...   │
      │  （当前实现）  │                         │   （未来平级）  │
      └───────┬───────┘                         └───────┬───────┘
              │        AgentEvent 事件流（唯一契约）      │
              └────────────────────┬────────────────────┘
                                   ▼
      ┌──────────────────────────────────────────────────────┐
      │                        core/                         │
      │  config.py ── 配置校验                                │
      │  events.py ── 事件契约                                │
      │  llm/      ── ChatClient 协议 + OpenAI 兼容适配器      │
      │  tools/    ── Tool 抽象 / 注册表 / 文件与日期工具      │
      │  skills/   ── Skill 发现与按需加载                      │
      │  agent/    ── AgentSession 会话循环                    │
      └──────────────────────────────────────────────────────┘
```

依赖方向严格单向：`前端 → core`。core 不 import 任何前端模块，也不 import Textual。

## 2. 目录结构

```
xAgent/
├── main.py                  # 装配入口：读配置 → 构建 session → 启动 TUI
├── config.ini               # 本地真实配置（已被 .gitignore 忽略）
├── config.example.ini       # 可提交的配置模板
├── requirements.txt
├── core/                    # 领域内核（与界面无关）
│   ├── config.py            # AppSettings / LLMSettings / 配置校验
│   ├── events.py            # AgentEvent 事件契约
│   ├── agent/
│   │   ├── prompt.py        # 系统提示词
│   │   ├── session.py       # AgentSession：LLM ↔ 工具循环，产出事件流
│   │   └── session_store.py # 会话持久化（.agents/sessions/*.jsonl，/save /new /resume）
│   ├── llm/
│   │   ├── base.py          # ChatClient 协议、ChatChunk 归一化模型
│   │   └── openai_client.py # OpenAI / DeepSeek 等兼容适配器
│   ├── skills/
│   │   ├── frontmatter.py   # SKILL.md Frontmatter 解析（仅标准库）
│   │   ├── models.py        # Skill 领域模型
│   │   └── registry.py      # 技能发现、按需读取、目录边界校验
│   ├── context/               # 上下文管理（压缩 / 归档 / 监控）
│   │   ├── tokens.py        # token 估算 + ContextMonitor（80% 阈值）
│   │   ├── archiver.py      # 原始上下文归档（.agents/context/*.jsonl）+ 关键词检索
│   │   └── compactor.py     # 压缩专用 Prompt + 摘要生成
│   ├── mcp/                   # MCP Client（连接外部 MCP Server）
│   │   ├── config.py        # .mcp.json 读取与校验
│   │   ├── bootstrap.py     # attach_mcp：加载/连接/注册（main 与 TUI 异步加载共用）
│   │   ├── client.py        # 连接管理、调用转发、重试/重连
│   │   ├── toolkit.py       # 把 MCP 工具转换为 xAgent Tool
│   │   └── log.py           # 滚动文件日志（logs/mcp.log）
│   └── tools/
│       ├── base.py          # Tool / ToolResult 抽象
│       ├── registry.py      # 注册、schema 导出、安全执行
│       ├── filesystem.py    # 文件系统工具集（10 项工具）
│       ├── datetime_tools.py# getDate / isLeapYear
│       ├── web_tools.py     # searchWeb / fetchWeb（联网工具）
│       ├── cli_tools.py     # RunCli（调用本机命令行程序）
│       ├── context_tools.py # recallContext（历史上下文检索）
│       └── skill_tools.py   # loadSkill / createSkill（技能按需加载与创建）
├── tui/                     # Textual 前端
│   ├── app.py               # App：事件流消费、斜杠命令、补全面板、MCP 异步加载
│   ├── app.tcss             # 样式
│   └── widgets/
│       ├── chat_view.py     # 聊天消息渲染组件
│       └── sidebar.py       # 右侧边栏（MCP 服务器与工具、技能）
└── unifypy.json             # 打包配置（改造前基线代码见 ../Practice02/）
```

## 3. 分层规则

| 层 | 职责 | 允许依赖 |
| --- | --- | --- |
| `core/` | 配置、LLM 适配、工具执行、会话编排 | 仅标准库与 openai SDK |
| `tui/` | 界面渲染、输入交互、状态展示 | `core` + textual |
| `main.py` | 读取配置、装配依赖、选择前端 | `core` + 具体前端 |

- 新增前端时，**不得**直接调用 `openai` 或工具函数，只消费 `AgentSession.send()` 的事件流。
- 工具的新增/修改集中在 `core/tools/`，前端无需改动。
- 替换模型供应商只需在 `core/llm/` 增加适配器，实现 `ChatClient.stream_chat()`。

## 4. 事件契约（core → 前端）

| 事件 | 含义 |
| --- | --- |
| `TextDelta` | 模型流式输出的文本片段 |
| `ToolCallStarted` | 模型请求调用工具（参数已聚合） |
| `ToolCallFinished` | 工具执行完成（含 `ok` 状态） |
| `ErrorOccurred` | 本回合可展示的错误 |
| `TurnCompleted` | 本回合正常结束（含最终回复与工具调用次数） |

## 5. Agent Skills 动态加载

**约定**：以程序启动时的工作目录为项目根，技能放在 `<启动目录>/.agents/skills/<技能目录>/SKILL.md`。从不同目录启动会加载各自目录下的技能；**启动目录没有任何技能时，回退加载源码目录（xAgent）的内置技能**。

```markdown
---
name: pdf-tools
description: 读取与填写 PDF 表单
---

# PDF 工具

（完整使用说明，只有模型调用 loadSkill 时才会进入上下文）
```

启动时只解析各 `SKILL.md` 的 Frontmatter，把 `name` / `description` 追加到 System Prompt：

```
You have access to the following skills:
- `pdf-tools`: 读取与填写 PDF 表单
Use the `loadSkill` tool to load the full instructions of a skill when needed.
```

`loadSkill` 行为：

| 入参 | 行为 |
| --- | --- |
| `name` | 返回该技能 `SKILL.md` 全文 |
| `name` + `filename` | 返回指定附加文件，不重复加载 `SKILL.md` |

`filename` 解析顺序：绝对路径 → 相对技能目录 → 相对项目根目录（三者都必须是技能目录内的真实文件）；都不匹配时，仅按文件名在技能目录内递归搜索，唯一命中才返回，多个同名文件则返回候选路径列表，由模型决定。

安全边界：解析后的路径必须位于该技能目录内，`..`、目录穿越与跨技能读取都会被拒绝。未提供 `[search]` 密钥不影响本功能，本功能也不需要任何新增依赖。

`createSkill` 行为（模型可根据用户要求直接建技能）：

| 要点 | 说明 |
| --- | --- |
| 入参 | `name`（小写字母/数字/连字符）、`skillContext`（SKILL.md 完整内容） |
| 落盘位置 | `<启动目录>/.agents/skills/<name>/SKILL.md` |
| Frontmatter | 缺少时自动补齐 `name` / `description`（description 取正文首个非空行），已有则保留其余字段 |
| 重名 | 直接返回「已存在」，**不覆盖**原文件 |
| 后续步骤 | 需要 `references/`、`scripts/` 等目录或辅助文件时，模型继续调用 `createDir` / `createFile` |
| 生效时机 | 创建后立即注册，本回合即可 `loadSkill`；TUI 欢迎区的技能列表仍为启动时快照 |

验证：创建上述目录结构后启动，欢迎区显示「已加载技能：pdf-tools」，状态栏显示「技能 1 个」；对话中输入「用 pdf-tools 技能」即可看到 `⚙ 调用 loadSkill`。

## 6. 运行

```bash
# 1. 安装依赖（本仓库已在 04-agent/.venv 中安装 textual）
pip install -r requirements.txt

# 2. 准备配置：复制模板并填写 api_key（见下文「首次运行自动生成」）
copy config.example.ini config.ini

# 3. 启动 TUI
python main.py
```

**首次运行自动生成配置**：在任意目录启动 xAgent 时若没有 config.ini，会自动在源码目录生成一份**带 mock 信息的完整模板**，并在控制台提示「请填写真实配置后重新启动」（退出码 2）。该模板包含全部配置段（`[LLM] / [APP] / [search] / [MCP] / [CONTEXT] / [TUI] / [TOOLS]`），至少填写 `[LLM] api_key` 后重启即可。

快捷键：`Enter` 发送，`Ctrl+J` 换行（Windows 控制台最可靠；部分终端也支持 `Shift+Enter` / `Ctrl+Enter` / `Alt+Enter`）。输入框支持多行粘贴，`Esc` 取消当前回合，`Ctrl+L` 清空会话，`Ctrl+C` 退出。

## 7. MCP Client（连接外部 MCP Server）

**配置位置**：`<启动目录>/.mcp.json`（跟随 cwd，与 `.agents/skills/` 同级）；**启动目录没有该文件时，回退使用源码目录 `xAgent/.mcp.json`**（与 config.ini 的共享策略一致）。TUI 欢迎区会显示实际使用的配置路径。

```json
{
  "mcpServers": {
    "Bazi-MCP": {
      "type": "streamable_http",
      "url": "https://mcp.api-inference.modelscope.net/3666cae7f5c746/mcp"
    },
    "local-calc": {
      "type": "stdio",
      "command": "node",
      "args": ["calc-mcp-server.js"],
      "env": { "NODE_NO_WARNINGS": "1" }
    }
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `type` | `streamable_http`（远程）或 `stdio`（本地子进程）；填 `sse` 会按 streamable_http 处理 |
| `url` | streamable_http 端点，**不要带反引号** |
| `command` / `args` / `env` | stdio 启动命令；`command` 建议用绝对路径，避免 PATH 解析失败 |

**工具命名**：暴露给 LLM 的名字是 `{server_name}__{tool_name}`，例如 `Bazi-MCP__getChineseCalendar`。不同 server 同名工具不会冲突；同名时会追加 `_2`、`_3` 后缀。

**重试与超时**（`config.ini` 的 `[MCP]` 段，全部可选）：

```ini
[MCP]
enabled = true       ; false = 完全跳过 MCP 初始化
retries = 2          ; 调用失败后的重试次数
retry_backoff = 1.0  ; 线性退避基数（秒），第 n 次重试前等 retry_backoff * n
call_timeout = 60    ; 单次工具调用超时（秒）
connect_timeout = 30 ; 建立连接 / list_tools 超时（秒）
```

**失败降级**：单个 server 连不上只跳过它，其他本地工具（RunCli、fetchWeb、loadSkill 等）照常可用；工具调用失败时按 `retries` 重连并重试，全部失败后把错误文本回写给模型，不中断会话。

**异步加载与边栏**：MCP 在 **TUI 启动后后台连接**（不阻塞首屏）。进入界面时边栏与状态栏显示「MCP 加载中」，连接完成后自动刷新：右侧边栏列出每个已连接 server 及其暴露的全部工具，状态栏显示 `MCP n OK`，欢迎区输出连接结果与配置路径。`/mcp` 可随时查看详情。

**日志**：`xAgent/logs/mcp.log`（滚动 1 MB × 3），记录每次 connect / call / retry / reconnect 的耗时与错误，便于事后排查。

**事件循环约束**：mcp SDK 的 `Client` 内部 TaskGroup 绑定在创建它的 asyncio 事件循环上。连接、调用、关闭必须发生在同一循环内，因此 `main()` 用单个 `asyncio.run(_run(...))` 包住「TUI（内部异步连 MCP）→ `app.run_async()` → 关闭」。若把 MCP 连接放在独立的 `asyncio.run()` 里再启动 TUI，调用时会报 `MCPError: Connection closed`。

## 8. 上下文压缩与历史检索（/compact + recallContext）

使 Agent 能在有限上下文窗口内持续完成长任务。不使用向量数据库，纯本地实现。

### 用量监控与阈值

- 每轮 LLM 响应结束后更新用量：**优先用 API 返回的真实 usage**（DeepSeek 开启 `include_usage`），拿不到时按「CJK 字符≈1 token、其余 4 字符≈1 token」估算。
- 状态栏实时显示 `上下文 已用k/窗口k 百分比`；窗口未在 config.ini 指定时默认 128k 并标注「（默认）」。
- 用量达到窗口 **80%**：聊天区警告一次，并**暂停接受新的普通指令**，直到 `/compact` 完成（`/compact` 本身始终可用）。

### /compact 压缩流程

1. **归档**：当前全部消息（含角色、内容、工具调用参数、工具返回）原样写入 `<启动目录>/.agents/context/<编号>.jsonl`，编号即 `YYYYMMDD-HHMMSS`；**归档成功才会继续**。
2. **摘要**：调用 LLM（**不携带任何工具定义**，期间无法触发 Function Calling）按专用 Prompt 生成约 5,000 tokens 的 Markdown 摘要。
3. **替换**：保留 System Prompt，其余历史替换为一条摘要消息，末尾追加归档说明（编号 + recallContext 提示）。
4. 成功后解除输入限制；失败则保持原上下文不变并报告错误，可重试。

### recallContext 工具

| 参数 | 说明 |
| --- | --- |
| `text`（必填） | 关键词或短语；多词时先按短语匹配，无命中再按「同消息内 AND」匹配 |
| `id`（可选） | 归档编号；省略时在全部归档中检索 |

返回命中片段、归档编号与消息位置，总长度受限（约 4,000 字符 / 10 条），避免检索结果再次占满上下文。归档为 JSONL 全文匹配（大小写不敏感），完整原始内容（含被截断的工具结果）都在归档里。

### 相关配置

```ini
[LLM]
; 模型上下文窗口（tokens），留空 = 默认 128k 并标注「默认」
context_window = 131072

[CONTEXT]
warn_ratio = 0.8             ; 阈值比例（越过后警告并阻断普通输入）
summary_target_tokens = 5000 ; /compact 摘要目标长度（写入压缩提示词）
summary_max_tokens = 8000    ; 摘要生成的输出上限
```

## 9. 扩展新前端

以 `web/` 为例：

1. 新建 `xAgent/web/`，实现自己的界面与事件消费逻辑；
2. 复用 `main.py` 中的 `build_session(settings)` 装配方式（或直接构造 `AgentSession`）；
3. `async for event in session.send(text)` 消费事件，按事件类型渲染；
4. 不修改 `core/`，即可获得与 TUI 完全一致的能力。

## 10. 相对基线的变化

- 原单文件拆分为 `core` + `tui`，函数级实现（文本判定、编码回退、破坏性操作预览、两阶段重命名等）保持不变。
- `confirm=true` 的安全护栏、100KB 截断、UTF-8/GBK 回退等行为与基线一致。
- LLM 调用改为 `AsyncOpenAI`，以适配 Textual 事件循环；流式聚合逻辑与基线一致。
- 相对路径改为以 `workspace`（默认启动目录，可由 `[APP] workspace` 固定）为基准，避免不同启动位置导致路径歧义。
- 工具异常会转成文本回写给模型，不再中断整个会话。

## 11. 斜杠命令与会话持久化

### 斜杠命令

输入 `/` 会弹出**补全引导面板**（继续输入可实时过滤；`↑/↓` 选择、`Enter`/`Tab` 补全、`Esc` 关闭），全部命令也可用 `/help` 查看：

| 命令 | 说明 |
| --- | --- |
| `/help` | 显示全部斜杠命令与说明 |
| `/new` | 新建会话，**自动保存**当前会话历史后再清空 |
| `/resume` | 打开历史会话列表面板：`↑/↓` 选择、`Enter` 恢复、`Esc` 取消 |
| `/save` | 保存当前会话到 `.agents/sessions/` |
| `/compact` | 压缩上下文并归档原始记录（见第 8 节） |
| `/context` | 查看当前上下文用量详情（窗口 / 阈值 / 用量来源 / 阻断状态） |
| `/tools` | 列出当前全部可用工具（含 MCP 工具） |
| `/skills` | 列出已加载的技能 |
| `/mcp` | 查看 MCP 服务器状态与各 server 暴露的工具 |
| `/clear` | 清空屏幕与会话历史（同 `Ctrl+L`） |
| `/quit` | 退出 xAgent |

### 会话持久化格式

会话保存在 `<启动目录>/.agents/sessions/<编号>.jsonl`（编号即 `YYYYMMDD-HHMMSS`，同秒保存追加 `-2`、`-3` 序号）。JSONL 每行一个 JSON 对象：首行为 meta（编号、时间、模型、消息数、token 用量、首条用户输入预览），其后每行为一条完整 OpenAI 格式消息。保存的是**全部消息（含 system）**，因此恢复时无需重新注入 AGENTS.md 或压缩摘要，直接继续会话；`/resume` 恢复后不回放历史内容，仅提示消息数。

## 12. AGENTS.md 支持（一次注入，全程复用）

- 会话首次加载时，若启动目录存在项目规则文件（默认兼容 `AGENTS.md`、`AGENT.md` 等价命名，按配置顺序取第一个存在的），其内容会作为一条 **system 消息**插入到主 System Prompt 之后（位置固定，前缀稳定，对 LLM 缓存友好）；
- 注入发生在启动时且**只发生一次**，后续所有轮次随历史一起发送，不存在每轮重复注入；文件缺失或为空时静默跳过，不报错；
- 内容超过上限（默认 20000 字符）时**自动截断**并标注，避免撑爆上下文；
- 文件名、开关、长度上限均可在 `config.ini` 的 `[AGENTS_MD]` 段配置（见第 13 节）；
- 注入的消息属于会话历史的一部分，`/save`、`/new` 时随消息列表**持久化到会话事件日志**（`.agents/sessions/*.jsonl`），`/resume` 恢复后继续生效、行为一致，无需也不会重复注入；
- `/compact` 压缩时 AGENTS.md 所在的 system 消息同样不会被摘要替换掉（压缩只替换非 system 消息）。

示例：在启动目录放一个 `AGENTS.md`：

```markdown
# 项目约定
- 所有回复使用中文
- 不要修改 .env 与 config.ini
- 提交信息使用 Conventional Commits
```

启动后该约定立即生效，且在整个会话（含压缩、恢复）中持续有效。

## 13. 配置参考（config.ini 全部段）

除 `[LLM]` 外全部段均可省略，省略时使用与下方相同的默认值；首次运行会自动生成含全部段的模板。

```ini
[LLM]
api_key = sk-...              ; 必填
base_url = https://api.deepseek.com
model_name = deepseek-chat
; context_window = 131072     ; 留空 = 默认 128k（界面标注「默认」）

[APP]
; workspace =                 ; 留空 = 启动目录
max_tool_rounds = 16

[search]
baidu_qianfan_api_key =       ; searchWeb 用，不用搜索可留空/删除本段

[MCP]
enabled = true
retries = 2
retry_backoff = 1.0
call_timeout = 60
connect_timeout = 30

[CONTEXT]
warn_ratio = 0.8              ; 上下文用量阈值（达到后阻断普通输入）
summary_target_tokens = 5000  ; /compact 摘要目标长度
summary_max_tokens = 8000     ; 摘要输出上限

[TUI]
flush_interval = 0.05         ; 流式输出刷新间隔（秒）

[AGENTS_MD]
enabled = true                ; 项目规则文件注入总开关
filenames = AGENTS.md,AGENT.md ; 兼容文件名（逗号分隔，取第一个存在的）
max_chars = 20000             ; 注入内容长度上限（字符），超出截断并标注

[TOOLS]
cli_timeout = 30              ; RunCli 单条命令超时（秒）
cli_max_chars = 4000          ; RunCli stdout/stderr 返回上限（字符）
fetch_max_chars = 8000        ; fetchWeb 返回 Markdown 上限（字符）
```
