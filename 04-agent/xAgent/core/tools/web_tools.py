"""联网工具：searchWeb（百度千帆搜索）+ fetchWeb（网页正文提取）。

searchWeb 仅在配置了 [search] baidu_qianfan_api_key 时有效；
fetchWeb 不依赖任何密钥，用本地 curl.exe 抓取 HTML 再交给 trafilatura 抽正文。
两个工具的异常都捕获后转为清晰文本返回给 LLM，不抛出。
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any

import trafilatura

from core.tools.base import Tool

SEARCH_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/web_search"
SEARCH_TIMEOUT = 15  # 秒
CURL_TIMEOUT = 15  # 秒
MAX_RESULTS = 10  # 返回给 LLM 的最大结果条数
MAX_MARKDOWN_LEN = 8000  # fetchWeb 最终返回的 Markdown 上限，避免撑爆 context


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _baidu_char_count(text: str) -> int:
    """按百度千帆规则计数：中文 2、ASCII 1，用于截断 query。"""
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


def _truncate_query(query: str) -> str:
    """百度千帆限制：计数 ≤72，超限则截断。"""
    if _baidu_char_count(query) <= 72:
        return query
    count = 0
    for i, ch in enumerate(query):
        count += 2 if ord(ch) > 127 else 1
        if count > 72:
            return query[:i]
    return query


def _http_post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    """用标准库做一次性 POST JSON，失败时抛出带上下文的异常。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} 调用百度搜索失败：{detail[:500]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络错误（百度搜索）：{exc.reason}") from exc

    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"百度搜索返回了非 JSON 内容：{exc}") from exc


# ---------------------------------------------------------------------------
# WebToolkit（持有密钥，模式与 FileSystemToolkit 一致）
# ---------------------------------------------------------------------------

class WebToolkit:
    def __init__(
        self,
        baidu_qianfan_api_key: str | None,
        *,
        fetch_max_chars: int = MAX_MARKDOWN_LEN,
    ) -> None:
        self._baidu_key = baidu_qianfan_api_key
        # fetchWeb 返回上限，来自 config.ini 的 [TOOLS] fetch_max_chars
        self._fetch_max_chars = fetch_max_chars

    # ---------- searchWeb ----------

    def search_web(self, query: str) -> str:
        if not self._baidu_key:
            return (
                "错误：searchWeb 需要百度千帆 API Key。"
                "请在 config.ini 的 [search] 段填写 baidu_qianfan_api_key。"
            )

        query = query.strip()
        if not query:
            return "错误：query 不能为空"

        original_len = len(query)
        query = _truncate_query(query)
        truncated_note = (
            f"（注：query 超长已截断到前 {len(query)} 个字符）"
            if len(query) < original_len
            else ""
        )

        payload = {
            "messages": [{"role": "user", "content": query}],
            "search_source": "baidu_search_v2",
            "edition": "standard",
            "resource_type_filter": [
                {"type": "web", "top_k": MAX_RESULTS},
            ],
            "query_policy": {"enable_rewrite": True},
        }
        headers = {
            "Authorization": f"Bearer {self._baidu_key}",
            "Content-Type": "application/json",
        }

        try:
            data = _http_post_json(SEARCH_ENDPOINT, payload, headers)
        except RuntimeError as exc:
            return f"searchWeb 调用失败：{exc}"
        except Exception as exc:
            return f"searchWeb 发生未知错误（{type(exc).__name__}）：{exc}"

        if "code" in data and data.get("code"):
            return (
                f"百度搜索 API 报错：code={data.get('code')} "
                f"message={data.get('message', '未知错误')}"
            )

        refs = data.get("references") or []
        if not refs:
            return f"搜索「{query}」未返回任何结果。{truncated_note}".strip()

        lines = [f"共找到 {len(refs)} 条结果：{truncated_note}".strip(), ""]
        for idx, ref in enumerate(refs[:MAX_RESULTS], start=1):
            title = (ref.get("title") or "(无标题)").strip()
            url = ref.get("url") or ""
            snippet = (ref.get("snippet") or ref.get("content") or "").strip()
            date = ref.get("date") or ""
            lines.append(f"{idx}. {title}")
            if date:
                lines.append(f"   发布时间：{date}")
            lines.append(f"   来源：{url}")
            if snippet:
                snippet_short = snippet[:300] + ("…" if len(snippet) > 300 else "")
                lines.append(f"   摘要：{snippet_short}")
            lines.append("")
        return "\n".join(lines).rstrip()

    # ---------- fetchWeb ----------

    def fetch_web(self, url: str) -> str:
        # 简单 URL 校验
        if not url or not re.match(r"^https?://", url, re.IGNORECASE):
            return "错误：fetchWeb 需要完整的 http:// 或 https:// URL"

        # 用 Windows 自带 curl.exe（避免 PowerShell 中 curl 是 Invoke-WebRequest 别名）
        # 列表传参，禁止 shell=True；-sL 静默跟随重定向；--max-time 超时
        try:
            result = subprocess.run(
                ["curl.exe", "-sL", "--max-time", str(CURL_TIMEOUT),
                 "--connect-timeout", "10",
                 "-A", ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"),
                 url],
                capture_output=True,
                timeout=CURL_TIMEOUT + 5,  # subprocess 层也设一次兜底超时
                check=False,
            )
        except FileNotFoundError:
            return "错误：找不到 curl.exe。请确认 Windows 自带的 curl 已安装。"
        except subprocess.TimeoutExpired:
            return f"错误：fetchWeb 抓取超时（>{CURL_TIMEOUT}s）：{url}"
        except Exception as exc:
            return f"fetchWeb 执行 curl 失败（{type(exc).__name__}）：{exc}"

        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            return (
                f"curl.exe 返回错误码 {result.returncode}："
                f"{err[:300] or '未知错误'}"
            )

        html = result.stdout
        if not html:
            return f"错误：fetchWeb 抓取到空内容：{url}"

        # trafilatura 需要 str
        try:
            html_text = html.decode("utf-8")
        except UnicodeDecodeError:
            # 常见中文站点用 gbk / gb2312，回退解码
            for enc in ("gbk", "gb2312", "latin-1"):
                try:
                    html_text = html.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return "错误：HTML 编码无法识别"

        try:
            markdown = trafilatura.extract(
                html_text,
                output_format="markdown",
                include_links=True,
                include_images=False,
                favor_precision=True,
                deduplicate=True,
            )
        except Exception as exc:
            return f"错误：trafilatura 解析失败（{type(exc).__name__}）：{exc}"

        if not markdown:
            return (
                f"错误：trafilatura 未能提取到可读正文。"
                f"可能页面是纯 JS 渲染或正文在 iframe 中。URL：{url}"
            )

        markdown = markdown.strip()
        if len(markdown) > self._fetch_max_chars:
            markdown = markdown[: self._fetch_max_chars] + (
                f"\n\n…（正文过长，已截断到前 {self._fetch_max_chars} 字符）"
            )

        return f"来源：{url}\n\n{markdown}"


def build_web_tools(web_toolkit: WebToolkit) -> list[Tool]:
    """构造联网工具。fetchWeb 始终可用，searchWeb 在密钥缺失时返回提示。"""
    return [
        Tool(
            name="searchWeb",
            description=(
                "联网搜索实时信息。输入一个中文或英文问题，"
                "返回若干条搜索结果，每条包含标题、来源 URL、发布时间、摘要。"
                "适用于需要最新资讯、实时数据、外部事实核实等场景。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的关键词或完整问题，例如 '2026 年最新版 Python 3.14 新特性'",
                    }
                },
                "required": ["query"],
            },
            handler=web_toolkit.search_web,
        ),
        Tool(
            name="fetchWeb",
            description=(
                "抓取指定网页的正文并转为 Markdown 返回。"
                "自动剥离导航栏、广告、页脚，保留标题、段落、列表、表格、链接。"
                "输入必须是完整的 http:// 或 https:// URL。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要抓取的网页完整 URL，例如 'https://docs.python.org/3/whatsnew/3.14.html'",
                    }
                },
                "required": ["url"],
            },
            handler=web_toolkit.fetch_web,
        ),
    ]
