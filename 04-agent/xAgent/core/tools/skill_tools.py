"""技能工具：按需加载技能内容，以及按规范创建新技能。"""

from __future__ import annotations

from core.skills.registry import SkillRegistry
from core.tools.base import Tool


class SkillToolkit:
    """把技能读取能力包装成模型可调用的工具，读取范围限制在技能目录内。"""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def load_skill(self, name: str, filename: str | None = None) -> str:
        name = (name or "").strip()
        if not name:
            return "错误：name 不能为空，请传入要加载的技能名称"
        return self._registry.read(name, filename)

    def create_skill(self, name: str, skillContext: str) -> str:
        return self._registry.create(name, skillContext)


def build_skill_tools(toolkit: SkillToolkit) -> list[Tool]:
    return [
        Tool(
            name="loadSkill",
            description=(
                "加载某个技能的完整说明。只传 name 时返回该技能的 SKILL.md 全文；"
                "再传 filename 时返回该技能目录内指定的附加文件，"
                "filename 支持相对技能目录的路径、项目相对路径或绝对路径。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "技能名称，取自系统提示词中列出的技能名",
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "可选。技能目录内的附加文件路径或文件名，"
                            "例如 references/api.md 或 examples.md"
                        ),
                    },
                },
                "required": ["name"],
            },
            handler=toolkit.load_skill,
        ),
        Tool(
            name="createSkill",
            description=(
                "根据用户要求创建一个新技能：在 .agents/skills/<name>/ 下生成 SKILL.md。"
                "仅在用户明确要求新建技能时调用；同名技能已存在时会被拒绝，不会覆盖。"
                "如还需 references/、scripts/ 等目录或辅助文件，"
                "创建完后再用 createDir、createFile 等文件工具补充。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "技能名称，只能由小写字母、数字和连字符组成，"
                            "例如 meeting-minutes"
                        ),
                    },
                    "skillContext": {
                        "type": "string",
                        "description": (
                            "要写入 SKILL.md 的完整内容，通常包含 YAML Frontmatter"
                            "（name、description）和技能正文；缺少 Frontmatter 时由工具自动补齐"
                        ),
                    },
                },
                "required": ["name", "skillContext"],
            },
            handler=toolkit.create_skill,
        ),
    ]
