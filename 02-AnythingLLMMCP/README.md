# AnythingLLM MCP Server

把 [AnythingLLM](https://anythingllm.com/)（本地 RAG 平台）的能力封装成 **MCP（Model Context Protocol）Server**，让任意 MCP 客户端（Claude Desktop、xAgent 等）通过工具调用完成工作区管理、文档上传/向量化、RAG 问答。

AnythingLLM 本体需单独安装，见 [../03-AnythingLLMServer/README.md](../03-AnythingLLMServer/README.md)。

## 工具一览（3 类 6 个）

| 类别 | 工具 | 说明 |
| --- | --- | --- |
| 工作区管理 | `list_workspaces` | 列出所有工作区（名称 / slug） |
| 工作区管理 | `create_workspace(name)` | 新建工作区，返回 slug |
| 文档上传/向量化 | `list_documents` | 列出已上传文档及其路径 |
| 文档上传/向量化 | `upload_document(file_path)` | 上传本地文件（PDF/TXT/MD/DOCX…） |
| 文档上传/向量化 | `add_document_to_workspace(doc_path, workspace?)` | 文档加入工作区并触发 embedding 向量化 |
| 对话/检索问答 | `ask_anythingllm(question, workspace?)` | 基于工作区已索引文档的 RAG 问答，附来源文档 |

所有工具的真实请求都打到 AnythingLLM 的 `/api/v1/*` REST API 上。`workspace` 参数留空时使用 `ANYTHINGLLM_WORKSPACE` 指定的工作区，否则自动取第一个工作区（惰性解析，调用时才连接）。

## 启动

```bash
pip install -r requirements.txt

# Windows PowerShell
$env:ANYTHINGLLM_API_KEY = "你的 API Key"
# macOS / Linux
export ANYTHINGLLM_API_KEY="你的 API Key"

python server.py
```

环境变量（密钥全部经环境变量注入，代码零硬编码）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ANYTHINGLLM_API_KEY` | **必填** | AnythingLLM 设置页 → API Keys 生成；缺失时启动即报错退出 |
| `ANYTHINGLLM_BASE_URL` | `http://localhost:3001` | AnythingLLM 服务地址 |
| `ANYTHINGLLM_WORKSPACE` | 空 = 第一个工作区 | 默认工作区 slug |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `8000` | MCP 监听地址 |

启动后 MCP 端点为 `http://127.0.0.1:8000/mcp`（streamable-http 传输）。

## 客户端接入示例

**Claude Desktop / xAgent `.mcp.json`**：

```json
{
  "mcpServers": {
    "AnythingLLM": {
      "type": "streamable_http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

**调用示例（客户端枚举到工具后）**：

```text
list_workspaces()                                   → 工作区列表：- 财报（slug: finance）
create_workspace(name="读书笔记")                    → 工作区已创建：读书笔记（slug: reading-notes）
upload_document(file_path="D:/docs/report.pdf")     → 已上传：report.pdf → custom-documents/report-….json
add_document_to_workspace(doc_path="custom-documents/report-….json")
                                                    → 文档已向量化到工作区「reading-notes」
ask_anythingllm(question="报告的核心结论是什么？")      → …答案… 来源文档：report.pdf
```

## 失败场景

| 场景 | 表现 | 处理 |
| --- | --- | --- |
| 未设 `ANYTHINGLLM_API_KEY` | 启动即退出，提示如何生成 Key | 设置环境变量后重启 |
| AnythingLLM 未启动 | 调用工具时报「无法连接 AnythingLLM」并给出地址 | 启动 AnythingLLM 后重试 |
| API Key 失效 | 报「鉴权失败（401）」 | 重新生成 Key |
| 没有任何工作区 | 问答/向量化工具报「没有任何工作区」 | 用 `create_workspace` 创建 |
| 文档未向量化就提问 | 答案检索不到该文档 | 先 `add_document_to_workspace` |
| `file_path` 不存在 | 报「文件不存在」 | 检查路径（需绝对路径） |
