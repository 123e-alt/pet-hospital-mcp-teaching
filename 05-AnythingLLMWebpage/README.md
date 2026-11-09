# AnythingLLM Web 控制台

纯前端单页（`index.html`，零依赖、零构建），直接调用 AnythingLLM `/api/v1/*` REST API，完成「工作区切换 → 文档上传并向量化 → 提问并展示回答」完整闭环。

AnythingLLM 本体安装见 [../03-AnythingLLMServer/README.md](../03-AnythingLLMServer/README.md)。

## 启动

任选一个静态服务方式（不要用 `file://` 直接双击，浏览器会拦 `fetch`）：

```bash
# 方式一：Python
cd 05-AnythingLLMWebpage
python -m http.server 8080
# 打开 http://localhost:8080

# 方式二：VS Code Live Server 插件，右键 index.html -> Open with Live Server
```

页面顶部填入：

1. **服务地址**：默认 `http://localhost:3001`
2. **API Key**：AnythingLLM 设置页 → API Keys 生成（密码框输入）
3. 点 **连接**，成功后自动列出工作区并选中第一个

## 功能与 API 对照

| 页面功能 | 端点 | 方法 / 请求体 |
| --- | --- | --- |
| 连接并列出工作区 | `/api/v1/workspaces` | GET，头 `Authorization: Bearer <key>` |
| 切换工作区 | `/api/v1/workspace/{slug}` | GET（读取该工作区已向量化文档列表） |
| 上传文档 | `/api/v1/document/upload` | POST，multipart 字段 `file` |
| 向量化到工作区 | `/api/v1/workspace/{slug}/update-embeddings` | POST，`{"adds":[location],"deletes":[]}` |
| 提问 | `/api/v1/workspace/{slug}/chat` | POST，`{"message": q, "mode":"chat"}` |

工作区列表、文档列表、回答与来源全部来自接口返回，无任何写死数据。

## 三态设计

每个异步操作都有 **加载 / 成功 / 失败** 三态：

- 加载：连接时「加载工作区…」、提问时「思考中…」、上传时「上传中… → 向量化中…」
- 成功：绿色状态文字（「已连接」「已上传并向量化」），回答以气泡展示并附来源文档
- 失败：红色具体原因（401 鉴权失败 / 无法连接 / HTTP 状态码 + 服务端摘要）

## 安全说明（C4）

- **密钥零硬编码**：源码中没有任何 Key；运行时由用户在密码框输入，只存内存变量，勾选「本会话记住」时放 `sessionStorage`（关标签页即清），绝不写 `localStorage`。
- **防 XSS**：所有接口返回内容（工作区名、文档名、回答、来源标题）一律经 `textContent` 写入 DOM，不使用 `innerHTML` 拼接，模型回答里的 `<script>` 等只会作为纯文本显示。

## 失败场景

| 场景 | 页面表现 | 处理 |
| --- | --- | --- |
| AnythingLLM 未启动 / 地址错 | 「无法连接 AnythingLLM…」 | 启动服务、核对地址 |
| API Key 错误 | 「鉴权失败（401）」 | 重新生成 Key |
| 浏览器 CORS 拦截 | 「无法连接…（CORS 限制见 README）」 | AnythingLLM 默认允许跨域；若改过反向代理，请放开 `Access-Control-Allow-Origin`，或把本页挂到同一源下 |
| 未选工作区就提问/上传 | 「请先选择工作区」 | 左侧点击任一工作区 |
| 文档未向量化就提问 | 回答检索不到该文档 | 上传流程已自动向量化，稍等索引完成再提问 |

## 移动端

`<meta viewport>` + 760px 媒体查询：自动切换单列布局、输入框全宽、聊窗降高，窄屏不崩。
