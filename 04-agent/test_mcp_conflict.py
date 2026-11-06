# -*- coding: utf-8 -*-
"""双份 .mcp.json 冲突告警验证。"""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"c:\Users\qq\Desktop\LLM\04-agent\xAgent")

from core.agent.session import AgentSession
from core.mcp.bootstrap import attach_mcp
from core.tools import build_default_registry


class FakeLLM:
    model_name = "fake"
    async def stream_chat(self, messages, tools=(), max_tokens=None):
        yield type("C", (), {"content": "ok", "tool_calls": [], "usage": None})()


def write(path: Path, url: str) -> None:
    path.write_text(json.dumps({"mcpServers": {"Srv": {"type": "streamable_http", "url": url}}}),
                    encoding="utf-8")


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="xagent_conflict_"))
    try:
        cwd_dir = tmp / "cwd"
        src_dir = tmp / "src"
        cwd_dir.mkdir(); src_dir.mkdir()
        write(cwd_dir / ".mcp.json", "http://127.0.0.1:9/a")   # 必失败：快速连接拒绝
        write(src_dir / ".mcp.json", "http://127.0.0.1:9/b")

        sess = AgentSession(llm=FakeLLM(), tools=build_default_registry(tmp))
        _, report = await attach_mcp(
            sess, cwd_dir, retries=0, connect_timeout=5.0,
            fallback_config_path=src_dir / ".mcp.json",
        )
        print("status:", report.status)
        print("note:", report.note)
        ok = report.status == "all_fail" and "两份不同的 .mcp.json" in report.note \
            and str(cwd_dir) in report.note
        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
