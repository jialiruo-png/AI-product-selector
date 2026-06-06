"""KeywordPlanner —— 入口/grounding 节点。

接收 keyword + category，产出 10~20 个精准词（keywords），
作为贯穿所有 analyzer 的全局状态。
"""
from __future__ import annotations

from agent import llm
from agent.skills.loader import load_skill_prompt

from .base import BaseNode


# C1：从对应 Skill MD 读取角色/SOP/输出规范，注入 system prompt 前缀（改 MD 行为跟着变）。
# 模块加载时一次性读取，零调用成本；缺 MD 返回 "" → 退回纯硬编码 prompt。
_SKILL_PREFIX = load_skill_prompt("关键词")

_KW_SYSTEM = """你是电商选品关键词专家。给定一个种子词和可选品类，产出一组用于电商搜索/选品的精准长尾词。
只输出 JSON：{"keywords": ["词1", "词2", ...]}
约束：
- 10~16 个词，含种子词本身；覆盖人群、场景、卖点、价格段、规格等不同角度。
- 词要像真实买家会搜的短语，不要整句、不要重复、不要解释。
- 种子词是哪国语言就用哪国语言（英文种子词产出英文词）。"""


def _system() -> str:
    """组合 Skill 前缀 + 节点硬编码 system（JSON 契约由后者锁定，MD 只追加语义）。"""
    return f"{_SKILL_PREFIX}\n\n{_KW_SYSTEM}" if _SKILL_PREFIX else _KW_SYSTEM


def _mock_keywords(keyword: str, category: str) -> list[str]:
    """无 LLM 时的确定性扩展词（保证 mock / 缺 key 永不崩）。"""
    base = [
        keyword,
        f"{keyword}推荐",
        f"{keyword}测评",
        f"平价{keyword}",
        f"{keyword}套装",
    ]
    if category:
        base.append(f"{category}{keyword}")
    seen: set[str] = set()
    return [k for k in base if not (k in seen or seen.add(k))]


class KeywordPlanner(BaseNode):
    """精准词规划。对应 company-research 的 grounding/入口节点。

    优先用真实 LLM 生成长尾词；mock / 缺 key / 调用失败时回退确定性扩展词。
    """

    name = "keyword_planner"

    def _llm_keywords(self, keyword: str, category: str) -> list[str] | None:
        user = f"种子词：{keyword}" + (f"\n品类：{category}" if category else "")
        data = llm.chat_json(_system(), user, max_tokens=512)
        if not isinstance(data, dict):
            return None
        kws = data.get("keywords")
        if not isinstance(kws, list):
            return None
        # 清洗：转字符串、去空、去重保序、确保含种子词
        seen: set[str] = set()
        out: list[str] = []
        for k in [keyword, *kws]:
            s = str(k).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out[:16] or None

    async def run(self, state: dict) -> dict:
        keyword = (state.get("keyword") or "").strip()
        category = (state.get("category") or "").strip()

        if not keyword:
            return {
                "keywords": [],
                "_trace": [self._trace_entry("缺少 keyword，产出空精准词")],
            }

        keywords = self._llm_keywords(keyword, category)
        if keywords:
            note = f"LLM 产出 {len(keywords)} 个精准词"
        else:
            keywords = _mock_keywords(keyword, category)
            note = f"产出 {len(keywords)} 个精准词（mock 回退）"

        return {
            "keywords": keywords,
            "_trace": [self._trace_entry(note)],
        }
