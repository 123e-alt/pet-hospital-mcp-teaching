"""上下文压缩：调用 LLM 生成会话摘要，供 /compact 流程使用。

压缩期间只允许「调用 LLM 生成摘要」这一件事：``summarize_messages``
向 LLM 发起请求时不携带任何工具定义，模型因此无法触发 Function
Calling；归档、替换上下文等操作全部由 xAgent 程序自己完成。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from core.llm.base import ChatClient

# 摘要目标长度（tokens），提示词中告知模型
SUMMARY_TARGET_TOKENS = 5000
# 摘要生成的输出上限，防止单次压缩调用失控
SUMMARY_MAX_TOKENS = 8000
# 序列化历史时单条工具结果的最大长度（完整内容已在归档中，可 recallContext 检索）
TOOL_RESULT_PREVIEW_CHARS = 2000

def build_compaction_prompt(target_tokens: int = SUMMARY_TARGET_TOKENS) -> str:
    """构建压缩系统提示词（摘要目标长度可配置，来自 [CONTEXT] 配置段）。"""
    return f"""你是一名 AI Agent 的上下文管理助手。当前会话即将达到上下文窗口限制，需要将历史对话压缩为一份高质量的工作摘要，以便 Agent 在新的上下文中继续执行任务。

请认真阅读提供的历史上下文，提取对后续工作仍然有价值的信息，并生成一份约 {target_tokens} Tokens 的 Markdown 摘要。

摘要应重点保留以下内容：

1. **用户目标与要求**：用户希望完成什么任务？有哪些必须遵守的约束、偏好和验收条件？
2. **已经完成的工作**：哪些任务已经完成？实现了哪些功能？获得了哪些已经验证的结果？
3. **当前工作状态**：Agent 正在处理什么任务？当前进展到哪一步？是否存在尚未解决的问题？
4. **关键技术信息**：保留重要的文件路径、函数名称、接口定义、配置项、执行命令、错误信息和必要的代码片段。
5. **关键决策与原因**：记录用户和 Agent 已经确定的技术方案，以及重要的设计取舍。
6. **下一步任务**：明确接下来应该执行的操作，以及需要继续验证的事项。

请遵守以下要求：

- 优先保留对后续任务有直接影响的信息，删除寒暄、重复讨论、过时的尝试和无关内容。
- 对已经验证的事实与尚未验证的推测作出明确区分。
- 不要将计划完成的任务描述为已经完成。
- 重要的文件路径、函数名称、配置名称和命令应保留准确原文。
- 对失败的尝试，只保留有助于避免重复错误的信息。
- 如果信息存在冲突，应优先保留用户最新确认的要求，并简要说明仍然存在的冲突。
- 如果某些历史细节无法在摘要中完整保留，可简要说明它们已保存到原始上下文归档中，后续可以通过 recallContext 工具重新检索。
- 使用清晰的 Markdown 结构输出摘要，不要附加解释或无关内容。

**最终目标：使一个从未阅读过原始对话的 Agent，仅凭这份摘要，就能够理解当前任务、继承关键决策，并继续开展工作。**"""


# 默认压缩提示词（保持向后兼容，内部统一走 build_compaction_prompt）
COMPACTION_SYSTEM_PROMPT = build_compaction_prompt()


@dataclass(frozen=True)
class CompactOutcome:
    """一次 /compact 的执行结果。"""

    ok: bool
    archive_id: str | None = None
    message_count: int = 0
    summary_tokens: int = 0
    error: str | None = None


def serialize_messages(messages: Sequence[dict[str, Any]]) -> str:
    """把 OpenAI 格式消息序列化为 LLM 可读的文本。

    工具结果只保留前 TOOL_RESULT_PREVIEW_CHARS 字符——完整内容已经
    保存在归档里，摘要不需要（也不该）全部塞进压缩调用本身。
    """
    lines: list[str] = []
    for message in messages:
        role = message.get("role", "?")
        if role == "tool":
            content = message.get("content") or ""
            if len(content) > TOOL_RESULT_PREVIEW_CHARS:
                content = content[:TOOL_RESULT_PREVIEW_CHARS] + "…[已截断，完整内容见归档]"
            name = message.get("name") or message.get("tool_call_id") or "tool"
            lines.append(f"[tool:{name}] {content}")
            continue

        content = message.get("content") or ""
        calls = [
            f"(调用工具 {call.get('function', {}).get('name')}，参数: "
            f"{call.get('function', {}).get('arguments')})"
            for call in message.get("tool_calls") or ()
        ]
        body = content
        if calls:
            body = (body + "\n" if body else "") + "\n".join(calls)
        lines.append(f"[{role}] {body or '(无文本内容)'}")
    return "\n\n".join(lines)


async def summarize_messages(
    client: ChatClient,
    messages: Sequence[dict[str, Any]],
    *,
    system_prompt: str = COMPACTION_SYSTEM_PROMPT,
    max_tokens: int = SUMMARY_MAX_TOKENS,
) -> str:
    """调用 LLM（不带任何工具）为历史消息生成压缩摘要。"""
    conversation = serialize_messages(messages)
    user_prompt = (
        "以下是本会话的完整历史上下文，请按系统指令生成压缩摘要：\n\n"
        "<conversation>\n"
        f"{conversation}\n"
        "</conversation>"
    )
    parts: list[str] = []
    async for chunk in client.stream_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        tools=(),
        max_tokens=max_tokens,
    ):
        if chunk.content:
            parts.append(chunk.content)
    return "".join(parts).strip()
