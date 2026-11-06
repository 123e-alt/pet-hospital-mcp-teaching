"""recallContext：检索 /compact 压缩时归档的原始上下文。

当压缩摘要缺少某些历史细节时，模型可主动调用本工具，用关键词在
``<启动目录>/.agents/context/`` 下的 JSONL 归档中做全文检索。
"""

from __future__ import annotations

from pathlib import Path

from core.context.archiver import ContextArchiver
from core.tools.base import Tool


class RecallContextToolkit:
    """recallContext 工具的实现载体。"""

    def __init__(self, context_dir: Path) -> None:
        self._archiver = ContextArchiver(context_dir)

    def recall_context(self, text: str, id: str | None = None) -> str:
        return self._archiver.search(text, id)


def build_context_tools(toolkit: RecallContextToolkit) -> tuple[Tool, ...]:
    return (
        Tool(
            name="recallContext",
            description=(
                "检索此前上下文压缩时归档的原始会话记录。当压缩摘要中缺少"
                "你需要的细节（如文件路径、函数名、某次工具结果、历史决策）时，"
                "用关键词调用本工具查找原始内容。text 为关键词或短语（必填）；"
                "id 为归档编号如 20261104-153000（可选，省略时在全部归档中检索）。"
                "返回命中片段及其归档编号与位置。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要查找的关键词或短语，例如函数名、文件路径、报错信息",
                    },
                    "id": {
                        "type": "string",
                        "description": "归档编号（可选），限定只在某个归档中检索",
                    },
                },
                "required": ["text"],
            },
            handler=toolkit.recall_context,
        ),
    )
