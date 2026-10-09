# 🐾 宠物医院 MCP 教学项目

围绕「宠物医院」业务与本地知识库，演示如何用 **MCP（Model Context Protocol）** 把能力接入 LLM。项目分为三个模块：

| # | 模块 | 目录 | 技术 / 传输 | 作用 |
| --- | --- | --- | --- | --- |
| 1 | **PetHospitalMCP** | [01-PetHospitalMCP/](01-PetHospitalMCP/) | Go · SSE | 宠物医院管理系统：REST API + 网页 + 21 个 MCP 工具（档案 CRUD、病历、收费、检索等） |
| 2 | **AnythingLLMMCP** | [02-AnythingLLMMCP/](02-AnythingLLMMCP/) | Python · Streamable HTTP | 把 AnythingLLM 第一个工作区封装成 RAG 问答工具 `ask_anythingllm` |
| 3 | **AnythingLLMServer** | [03-AnythingLLMServer/](03-AnythingLLMServer/) | 独立软件（指引） | AnythingLLM 本体的安装与配置说明（本体需独立安装，不在本仓库内） |

## 模块关系

```text
LLM 客户端 ──SSE──> 01-PetHospitalMCP（Go，宠物医院业务，端口 8081）
LLM 客户端 ──HTTP─> 02-AnythingLLMMCP（Python，端口 8000）
                            │ HTTP API
                            └──────> AnythingLLM 本体（独立安装，端口 3001）
```

## 快速开始

1. 想用宠物医院业务工具：进入 [01-PetHospitalMCP/](01-PetHospitalMCP/)，按其 README 编译运行。
2. 想做知识库问答：先按 [03-AnythingLLMServer/](03-AnythingLLMServer/) 安装并启动 AnythingLLM、拿到 API Key，再进入 [02-AnythingLLMMCP/](02-AnythingLLMMCP/) 运行。

> 各模块的详细安装与使用见对应目录下的 README。

## 许可证

见 [LICENSE](LICENSE)。
