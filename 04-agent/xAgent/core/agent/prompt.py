"""系统提示词集中管理，供所有前端复用同一套 Agent 行为。"""

from __future__ import annotations

from typing import Sequence

from core.skills.models import Skill

SYSTEM_PROMPT = (
    "你是一个可以操作本地文件系统的AI助手。"
    "你可以通过调用工具来获取文件信息、创建/编辑/删除/重命名文件和目录。"
    "删除、重命名等破坏性操作需要先获取预览（默认返回），"
    "只有当用户明确要求执行时才传入 confirm=True 实际执行。"
)

SKILL_SECTION_HEADER = "You have access to the following skills:"

SKILL_SECTION_FOOTER = (
    "Use the `loadSkill` tool to load the full instructions of a skill when needed. "
    "You can also load additional files referenced by a skill."
)


def build_system_prompt(skills: Sequence[Skill] = ()) -> str:
    """在基础提示词后追加技能清单；没有技能时保持原样。"""
    if not skills:
        return SYSTEM_PROMPT

    lines = [SYSTEM_PROMPT, "", SKILL_SECTION_HEADER]
    lines.extend(f"- `{skill.name}`: {skill.description}" for skill in skills)
    lines.extend(["", SKILL_SECTION_FOOTER])
    return "\n".join(lines)
