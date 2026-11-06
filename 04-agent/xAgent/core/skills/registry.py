"""Skill 发现与按需读取。

发现阶段只解析 SKILL.md 的 Frontmatter（name / description），
正文与附加文件只有在 LLM 调用 loadSkill 时才会被读取。
"""

from __future__ import annotations

import re
from pathlib import Path

from core.skills.frontmatter import (
    FrontmatterError,
    parse_frontmatter,
    read_frontmatter,
)
from core.skills.models import Skill

SKILL_FILENAME = "SKILL.md"
MAX_FILE_CHARS = 100_000  # 单次加载的字符上限，避免撑爆上下文
MAX_LISTED_FILES = 20  # 出错时最多列出的候选文件数
MAX_DESCRIPTION_CHARS = 120  # 自动推导 description 时的长度上限
SKILL_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class SkillRegistry:
    """技能集合；同时负责把文件名解析到技能目录内的真实路径。"""

    def __init__(
        self,
        skills: tuple[Skill, ...] = (),
        project_root: Path | None = None,
        skills_root: Path | None = None,
    ) -> None:
        self._skills = skills
        self._project_root = (project_root or Path.cwd()).resolve()
        self._skills_root = (
            Path(skills_root).expanduser().resolve()
            if skills_root
            else self._project_root / ".agents" / "skills"
        )
        self._by_name = {skill.name: skill for skill in skills}

    # ---------- 发现 ----------

    @classmethod
    def discover(
        cls, skills_root: str | Path, project_root: str | Path | None = None
    ) -> "SkillRegistry":
        """扫描 skills 目录下的一级子目录，只解析 Frontmatter。

        project_root 用于解析 loadSkill 的项目相对路径，默认与 skills_root 一致。
        """
        root = Path(skills_root).expanduser().resolve()
        base = Path(project_root).expanduser().resolve() if project_root else root
        if not root.is_dir():
            return cls((), base, root)

        found: list[Skill] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            skill_file = entry / SKILL_FILENAME
            if not skill_file.is_file():
                continue

            try:
                metadata = read_frontmatter(skill_file)
            except (FrontmatterError, OSError):
                continue

            name = metadata.get("name", "").strip()
            description = " ".join(metadata.get("description", "").split())
            if not name or not description or name in {s.name for s in found}:
                continue

            found.append(
                Skill(name=name, description=description, directory=entry.resolve())
            )

        return cls(tuple(found), base, root)

    # ---------- 查询 ----------

    def __len__(self) -> int:
        return len(self._skills)

    def __iter__(self):
        return iter(self._skills)

    def get(self, name: str) -> Skill | None:
        return self._by_name.get(name.strip())

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(skill.name for skill in self._skills)

    # ---------- 按需读取 ----------

    def read(self, name: str, filename: str | None = None) -> str:
        """读取技能主文件或附加文件，返回可直接回写给模型的文本。"""
        skill = self.get(name or "")
        if skill is None:
            return self._unknown_skill_message(name)

        target_name = (filename or "").strip()
        if not target_name:
            return self._read_main(skill)

        path = self._locate(skill, target_name)
        if isinstance(path, str):
            return path
        return self._read_attached(skill, path)

    # ---------- 创建 ----------

    def create(self, name: str, context: str) -> str:
        """按 Agent Skills 规范创建新技能，返回可直接回写给模型的文本。

        已存在同名技能时不覆盖；创建成功后立即注册，本回合即可 loadSkill。
        """
        name = (name or "").strip()
        if not SKILL_NAME_PATTERN.fullmatch(name):
            return (
                f"错误：技能名「{name}」不符合命名规范。"
                "只允许小写字母、数字与连字符，例如 meeting-minutes"
            )

        context = (context or "").strip()
        if not context:
            return "错误：skillContext 不能为空，请提供 SKILL.md 的完整内容"

        directory = self._skills_root / name
        existing = self.get(name)
        if existing is not None:
            if existing.directory.is_dir():
                return self._exists_message(name)
            # 技能目录已被删除：注册表里的记录已失效，允许重建
            self._skills = tuple(s for s in self._skills if s.name != name)
            self._by_name.pop(name, None)
        if (directory / SKILL_FILENAME).exists():
            return self._exists_message(name)

        metadata, body = parse_frontmatter(context)
        if not body.strip():
            return "错误：skillContext 只有 Frontmatter，缺少技能正文"

        description = " ".join(metadata.get("description", "").split())
        if not description:
            description = _derive_description(body, name)

        document = (
            _render_frontmatter(name, description, metadata)
            + "\n"
            + body.strip("\n")
            + "\n"
        )

        try:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / SKILL_FILENAME).write_text(document, encoding="utf-8")
        except OSError as exc:
            return f"错误：创建技能「{name}」失败 - {exc}"

        skill = Skill(
            name=name, description=description, directory=directory.resolve()
        )
        self._skills = self._skills + (skill,)
        self._by_name[name] = skill
        return (
            f"已创建技能「{name}」。\n"
            f"目录：{directory}\n"
            f"文件：{directory / SKILL_FILENAME}\n"
            f"description：{description}\n"
            "已完成规范校验并注册，可直接用 loadSkill 加载；"
            "若还需 references/、scripts/ 等目录或辅助文件，"
            "请继续用 createDir、createFile 等文件工具创建。"
        )

    def _exists_message(self, name: str) -> str:
        return (
            f"错误：技能「{name}」已存在（{self._skills_root / name}），"
            "为避免覆盖原有内容，本次未做任何修改。"
            "如需替换，请先删除该技能目录后重试。"
        )

    # ---------- 内部实现 ----------

    def _read_main(self, skill: Skill) -> str:
        try:
            content = _read_text(skill.skill_file)
        except OSError as exc:
            return f"错误：读取技能「{skill.name}」的 SKILL.md 失败 - {exc}"
        return (
            f"技能：{skill.name}\n"
            f"文件：{skill.skill_file}\n\n"
            f"{_clip(content)}"
        )

    def _read_attached(self, skill: Skill, path: Path) -> str:
        try:
            content = _read_text(path)
        except OSError as exc:
            return f"错误：读取文件失败 - {exc}"
        relative = path.relative_to(skill.directory).as_posix()
        return (
            f"技能：{skill.name}\n"
            f"文件：{relative}\n\n"
            f"{_clip(content)}"
        )

    def _locate(self, skill: Skill, filename: str) -> Path | str:
        """精确匹配优先，其次递归按文件名搜索；返回 Path 或错误/候选文本。"""
        raw = Path(filename).expanduser()

        candidates: list[Path] = []
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.append(skill.directory / raw)  # 相对技能目录
            candidates.append(self._project_root / raw)  # 相对项目根目录

        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved.is_file() and _is_within(resolved, skill.directory):
                return resolved

        # 只给了文件名时才递归查找；带目录的路径必须先精确命中，
        # 否则会拿技能自身的同名文件冒充，造成歧义。
        if raw.parent != Path("."):
            return self._missing_file(skill, filename)

        matches: list[Path] = []
        for item in skill.directory.rglob("*"):
            if item.is_file() and item.name == raw.name:
                matches.append(item)
        matches = sorted({match.resolve() for match in matches})

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            listed = "\n".join(
                f"- {match.relative_to(skill.directory).as_posix()}"
                for match in matches[:MAX_LISTED_FILES]
            )
            return (
                f"技能「{skill.name}」中存在多个名为 {raw.name} 的文件，"
                f"请用 filename 指定完整路径：\n{listed}"
            )

        return self._missing_file(skill, filename)

    def _missing_file(self, skill: Skill, filename: str) -> str:
        return (
            f"错误：技能「{skill.name}」目录内找不到文件 {filename}。\n"
            f"可读取的文件：\n{self._list_files(skill)}"
        )

    def _list_files(self, skill: Skill) -> str:
        files = sorted(
            path.relative_to(skill.directory).as_posix()
            for path in skill.directory.rglob("*")
            if path.is_file()
        )
        if not files:
            return "（该技能目录为空）"
        listed = "\n".join(f"- {name}" for name in files[:MAX_LISTED_FILES])
        if len(files) > MAX_LISTED_FILES:
            listed += f"\n…（共 {len(files)} 个文件，仅列出前 {MAX_LISTED_FILES} 个）"
        return listed

    def _unknown_skill_message(self, name: str) -> str:
        names = "、".join(self.names) if self._skills else "（暂无已发现的技能）"
        return f"错误：未找到技能「{name}」。当前可用技能：{names}"


def _derive_description(body: str, name: str) -> str:
    """从正文首个非空行推导 description，去掉 Markdown 标题标记。"""
    for line in body.splitlines():
        text = " ".join(line.strip().lstrip("#").split())
        if text:
            if len(text) > MAX_DESCRIPTION_CHARS:
                text = text[:MAX_DESCRIPTION_CHARS].rstrip() + "…"
            return text
    return f"{name} 技能"


def _render_frontmatter(name: str, description: str, metadata: dict[str, str]) -> str:
    """按 name、description 在前的顺序重建 Frontmatter，保留其余自定义字段。"""
    fields: dict[str, str] = {"name": name, "description": description}
    for key, value in metadata.items():
        if key not in fields:
            fields[key] = " ".join(value.split())

    lines = ["---"]
    lines.extend(f"{key}: {_yaml_scalar(value)}" for key, value in fields.items())
    lines.append("---")
    return "\n".join(lines)


def _yaml_scalar(value: str) -> str:
    """必要时用双引号包裹，避免 description 中的冒号、井号破坏 YAML 结构。"""
    needs_quote = (
        not value
        or value != value.strip()
        or any(token in value for token in (": ", " #"))
        or value[0] in "-?:,[]{}#&*!|>'\"%@`"
    )
    if not needs_quote:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _is_within(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _read_text(path: Path) -> str:
    """按 UTF-8（含 BOM）→ GBK 顺序解码，避免中文技能文件乱码。"""
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _clip(text: str) -> str:
    if len(text) <= MAX_FILE_CHARS:
        return text
    return (
        text[:MAX_FILE_CHARS]
        + f"\n\n…（文件过长，已截断到前 {MAX_FILE_CHARS} 字符）"
    )
