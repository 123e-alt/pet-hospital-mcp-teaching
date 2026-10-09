# AnythingLLM Server 安装与配置指引

[AnythingLLM](https://anythingllm.com/) 是 Mintplex-Labs 出品的本地 RAG（检索增强生成）平台，可管理文档工作区并提供问答 API。它是**独立软件**，需要单独安装运行；本目录仅提供指引，不包含其本体。

## 1. 安装

任选一种方式：

- **桌面版（最简单）**：访问 https://anythingllm.com/desktop 下载对应系统的安装包，安装后启动应用。
- **Docker**：

  ```bash
  docker pull mintplexlabs/anythingllm
  docker run -d -p 3001:3001 \
    -v anythingllm_storage:/app/server/storage \
    --name anythingllm mintplexlabs/anythingllm
  ```

默认服务地址：`http://localhost:3001`，API 文档：http://localhost:3001/api/docs/

## 2. 创建工作区并上传文档

1. 打开 http://localhost:3001
2. 新建一个工作区（Workspace）
3. 进入工作区，点击上传图标，把要问答的文档拖入（PDF、TXT、Markdown 等均可），等待索引完成

## 3. 生成 API Key

1. 点击左下角设置图标 → **API Keys**
2. 创建一个新的 API Key 并复制保存（形如 `XXXXXX-XXXXXX-XXXXXX-XXXXXX`，只显示一次）

## 4. 与 02-AnythingLLMMCP 衔接

把 API Key 写入环境变量，再启动 Python MCP：

**PowerShell（Windows）**：

```powershell
$env:ANYTHINGLLM_API_KEY = "你的 API Key"
cd ../02-AnythingLLMMCP
pip install -r requirements.txt
python server.py
```

**macOS / Linux**：

```bash
export ANYTHINGLLM_API_KEY="你的 API Key"
cd ../02-AnythingLLMMCP
pip install -r requirements.txt
python server.py
```

可用环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ANYTHINGLLM_BASE_URL` | `http://localhost:3001` | AnythingLLM 服务地址 |
| `ANYTHINGLLM_API_KEY` | 无（必填） | 上一步生成的 API Key |
| `MCP_HOST` | `127.0.0.1` | MCP 监听地址 |
| `MCP_PORT` | `8000` | MCP 监听端口 |

启动后 MCP 端点为 `http://127.0.0.1:8000/mcp`，工具 `ask_anythingllm(question)` 会向第一个工作区提问并返回基于其文档的 AI 回答。
