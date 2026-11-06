"""Skill 领域模型：只描述一个已发现的技能，不涉及扫描与读取。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    """一个技能目录：name / description 来自 SKILL.md 的 Frontmatter。"""

    name: str
    description: str
    directory: Path

    @property
    def skill_file(self) -> Path:
        """技能主文件固定为目录下的 SKILL.md。"""
        return self.directory / "SKILL.md"
