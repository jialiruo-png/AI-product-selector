"""Skill MD 加载器（PRD 1.2 / 第 5 节：配置即技能）。

把一份 Markdown 专家定义解析为 Skill 对象。解析基于
markdown 二级标题（`## N.xxx`）切块，宽松容错——业务可随意调整
小标题文案，只要保留 `# Skill: X` 与六个 `## N.` 段即可。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent


@dataclass
class Skill:
    name: str
    role: str = ""
    goal: str = ""
    sop_steps: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    input_schema_text: str = ""
    output_spec: str = ""
    next_skill: str | None = None
    source_path: str | None = None


# `## 1.角色定义` / `## 1. 角色定义` 都能命中
_HEADING_RE = re.compile(r"^##\s*\d+\s*[\.、]?\s*(.+?)\s*$", re.MULTILINE)
_TITLE_RE = re.compile(r"^#\s*Skill\s*[:：]\s*(.+?)\s*$", re.MULTILINE)
_NEXT_RE = re.compile(r"next_skill\s*[:：]\s*\"?([^\"\n|]+)")


def _split_sections(text: str) -> dict[str, str]:
    """按 `## N.标题` 切块，返回 {标题关键词: 正文}。"""
    sections: dict[str, str] = {}
    matches = list(_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        title = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[title] = text[start:end].strip()
    return sections


def _find_section(sections: dict[str, str], *keywords: str) -> str:
    for title, body in sections.items():
        if any(k in title for k in keywords):
            return body
    return ""


def _bullet_lines(body: str) -> list[str]:
    """提取列表/编号行，去掉前缀符号。"""
    out: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^(\d+[\.、)]|[-*•])\s*", "", line).strip()
        if line:
            out.append(line)
    return out


def _tool_names(body: str) -> list[str]:
    """从工具依赖段提取工具名：取每行冒号前的首个 token。"""
    tools: list[str] = []
    for line in _bullet_lines(body):
        head = re.split(r"[:：]", line, 1)[0].strip()
        # 取第一个连字/字母数字 token，兼容 "tikhub.search_products / score.rank"
        token = re.split(r"[\s/、,，]", head, 1)[0].strip(" `")
        if token:
            tools.append(token)
    return tools


def parse_skill(text: str, source_path: str | None = None) -> Skill:
    title_m = _TITLE_RE.search(text)
    name = title_m.group(1).strip() if title_m else (
        Path(source_path).stem if source_path else "未命名"
    )
    sections = _split_sections(text)

    role = _find_section(sections, "角色")
    goal = _find_section(sections, "核心目标", "目标")
    sop_body = _find_section(sections, "SOP", "作业流程", "流程")
    tools_body = _find_section(sections, "工具依赖", "工具")
    input_text = _find_section(sections, "输入")
    output_body = _find_section(sections, "输出")

    next_skill = None
    nm = _NEXT_RE.search(output_body) or _NEXT_RE.search(text)
    if nm:
        next_skill = nm.group(1).strip().strip('"').strip()

    return Skill(
        name=name,
        role=role,
        goal=goal,
        sop_steps=_bullet_lines(sop_body),
        tools=_tool_names(tools_body),
        input_schema_text=input_text,
        output_spec=output_body,
        next_skill=next_skill,
        source_path=source_path,
    )


def load_skills(dir: str | Path = SKILLS_DIR) -> dict[str, Skill]:
    """加载目录下全部 Skill MD（跳过 README），返回 {name: Skill}。"""
    d = Path(dir)
    skills: dict[str, Skill] = {}
    for md in sorted(d.glob("*.md")):
        if md.stem.lower() == "readme":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        skill = parse_skill(text, source_path=str(md))
        skills[skill.name] = skill
    return skills


def skill_chain(start: str, skills: dict[str, Skill]) -> list[str]:
    """沿 next_skill 串联，返回从 start 起的技能名链（防环）。"""
    chain: list[str] = []
    cur: str | None = start
    seen: set[str] = set()
    while cur and cur not in seen:
        chain.append(cur)
        seen.add(cur)
        skill = skills.get(cur)
        if not skill:
            break  # 链尾可能是 "洞察报告" 等占位终点，无对应 MD
        cur = skill.next_skill
    return chain


if __name__ == "__main__":  # pragma: no cover
    s = load_skills()
    print("loaded:", sorted(s))
    print("chain:", skill_chain("选品", s))
