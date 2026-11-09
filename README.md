# LLM 工程实践仓库

围绕 **MCP（Model Context Protocol）** 与 **Agent 工程化** 的四个评分维度项目：宠物医院 MCP（A）、AnythingLLM MCP（B）、AnythingLLM Webpage（C）、定制 Agent xAgent（D）。

## 项目地图

| 维度 | 模块 | 目录 | 技术 / 传输 | 作用 |
| --- | --- | --- | --- | --- |
| A | **PetHospitalMCP** | [01-PetHospitalMCP/](01-PetHospitalMCP/) | Go · SSE（端口 8081） | 宠物医院管理系统：REST API + 网页 + 22 个 MCP 工具（档案 CRUD、病历、收费、检索等），含结构化错误码 / 超时 / 调用日志 |
| B | **AnythingLLMMCP** | [02-AnythingLLMMCP/](02-AnythingLLMMCP/) | Python · Streamable HTTP（端口 8000） | AnythingLLM 的 MCP 封装：6 个工具覆盖工作区管理、文档上传/向量化、对话问答 |
| C | **AnythingLLMWebpage** | [05-AnythingLLMWebpage/](05-AnythingLLMWebpage/) | 纯前端单页（零依赖） | 直连 AnythingLLM `/api/v1/*`：工作区切换、上传并向量化、提问展示回答；密钥运行时输入零硬编码 |
| D | **xAgent** | [04-agent/xAgent/](04-agent/xAgent/) | Python · Textual TUI | 分层定制 Agent：工具主循环、18 个本地工具、技能系统、MCP 客户端、AGENTS.md、会话持久化、上下文压缩 |
| — | **AnythingLLMServer** | [03-AnythingLLMServer/](03-AnythingLLMServer/) | 独立软件（指引） | AnythingLLM 本体的安装配置说明（B/C 的上游前置条件，本体不在仓库内） |
| — | 练习代码 | [04-agent/Practice01·02/](04-agent/) | Python | 早期练习脚本（非交付模块，见各文件头注释） |

## 模块关系

```text
                 ┌──SSE──> 01-PetHospitalMCP（Go，:8081，A）
LLM 客户端/xAgent ┤
                 └──HTTP──> 02-AnythingLLMMCP（Python，:8000，B）
                                    │ /api/v1
浏览器 ──HTTP──> 05-AnythingLLMWebpage（C）──┴──> AnythingLLM 本体（独立安装，:3001）
xAgent（D，04-agent/xAgent）──OpenAI 兼容 API──> DeepSeek
```

## 环境依赖

| 模块 | 依赖 |
| --- | --- |
| 01 | Go ≥ 1.23（`go build`，无第三方服务依赖） |
| 02 / 05 | Python ≥ 3.11 + `pip install -r requirements.txt`；上游需运行中的 AnythingLLM（见 03） |
| 04-agent/xAgent | Python ≥ 3.11 + `pip install -r requirements.txt`（textual、openai、mcp 等）+ DeepSeek API Key |

## 配置方式与密钥

- **密钥一律不入库**：`.gitignore` 已忽略 `config.ini`、`.env`、`.mcp.json` 等；仓库只提交模板（`04-agent/xAgent/config.example.ini`，首次运行 xAgent 还会自动生成 `config.ini` 模板）。
- xAgent：复制 `config.example.ini` 为 `config.ini` 填 DeepSeek Key；MCP 服务在启动目录或源码目录的 `.mcp.json` 配置。
- 02 / 05：AnythingLLM Key 经环境变量 `ANYTHINGLLM_API_KEY`（02）或页面密码框运行时输入（05），均不写入代码。

## 分步启动

1. **A**：`cd 01-PetHospitalMCP && go run . --mode mcp`（详见其 README，含客户端接入 JSON）
2. **B**：先按 [03](03-AnythingLLMServer/) 装好 AnythingLLM 并拿到 API Key → `cd 02-AnythingLLMMCP && set ANYTHINGLLM_API_KEY=... && python server.py`
3. **C**：`cd 05-AnythingLLMWebpage && python -m http.server 8080`，浏览器打开后填地址与 Key
4. **D**：`cd 04-agent\xAgent && python main.py`（配置缺失会自动生成模板并提示）

各模块的详细安装、示例调用与失败场景见对应目录 README（E2）。

## 验证步骤（E4）

- 01：`go test ./...`（工具注册 / 参数校验 / 错误码 / 超时护栏）
- 04-agent：`python test_v2_features.py`（69 项：工具 / 技能 / MCP / 会话 / 压缩 / AGENTS.md / TUI）
- 02：缺 Key 启动即报清晰错误（退出码 1）；AnythingLLM 离线时工具仍可被枚举

## 许可证

见 [LICENSE](LICENSE)。
