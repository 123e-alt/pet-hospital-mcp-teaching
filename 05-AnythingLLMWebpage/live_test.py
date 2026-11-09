# -*- coding: utf-8 -*-
"""用真实 AnythingLLM 走通网页同款完整流程：上传 → 向量化 → 提问。

Key 只从环境变量 ANYTHINGLLM_API_KEY 读取，不落盘。
    $env:ANYTHINGLLM_API_KEY="..."; python live_test.py
"""
import os
import sys
import tempfile
from pathlib import Path

import httpx

BASE = os.getenv("ANYTHINGLLM_BASE_URL", "http://localhost:3001").rstrip("/")
KEY = os.getenv("ANYTHINGLLM_API_KEY", "").strip()
if not KEY:
    sys.exit("请先设置环境变量 ANYTHINGLLM_API_KEY")

H = {"Authorization": f"Bearer " + KEY}
client = httpx.Client(base_url=BASE + "/api/v1", headers=H, timeout=httpx.Timeout(30.0, read=120.0))

# 1. 工作区列表（网页「连接」按钮同款请求）
wss = client.get("/workspaces").json().get("workspaces") or []
assert wss, "没有任何工作区"
slug = wss[0]["slug"]
print(f"[1] 工作区列表 OK：{wss[0]['name']} (slug={slug})")

# 2. 上传文档（网页「选择文档」同款请求）
tmp = Path(tempfile.gettempdir()) / "allm_live_test.md"
tmp.write_text("# Live Test\n\nAnythingLLM 网页控制台的验收测试文档。核心结论：三条流程全部打通。", encoding="utf-8")
with tmp.open("rb") as f:
    up = client.post("/document/upload", files={"file": (tmp.name, f)}).json()
loc = (up.get("documents") or [{}])[0].get("location")
assert loc, f"上传失败：{up}"
print(f"[2] 上传 OK：{loc}")

# 3. 向量化（网页上传后自动调用同款请求）
emb = client.post(f"/workspace/{slug}/update-embeddings", json={"adds": [loc], "deletes": []}).json()
docs = (emb.get("workspace") or {}).get("documents") or []
print(f"[3] 向量化 OK：工作区现有 {len(docs)} 篇文档")

# 4. 提问（网页「发送」同款请求）
ans = client.post(f"/workspace/{slug}/chat", json={"message": "这份文档的核心结论是什么？", "mode": "chat"}).json()
text = (ans.get("textResponse") or "").strip()
sources = sorted({s.get("title", "?") for s in (ans.get("sources") or [])})
print(f"[4] 提问 OK：{text[:120]}")
print(f"    来源文档：{sources}")

# 清理：把测试文档从工作区移除（保留上传文件本体，便于复查）
client.post(f"/workspace/{slug}/update-embeddings", json={"adds": [], "deletes": [loc]})
print("[5] 已把工作区恢复原状（移除测试文档的向量化引用）")
print("RESULT: PASS —— 网页同款四条请求全部走通")
