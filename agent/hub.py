"""Hub Agent —— 路由层（PRD 1.1）。

MVP 用关键词/规则做意图识别（非 LLM），把商家自然语言路由到对应专家，
并沿 Skill MD 的 next_skill 串成 Skill 链。● 档（洞察类）意图直接驱动
已建好的 P0 商机洞察子图（agent.graph.run_insight）；◐/○ 档专家标 future。
"""
from __future__ import annotations

import re

from agent.skills.loader import load_skills, skill_chain

# 意图 -> (起始 Skill, 触发关键词)。规则按列表顺序匹配，先命中先生效。
_INTENT_RULES: list[tuple[str, str, list[str]]] = [
    ("口碑诊断", "口碑诊断", ["差评", "口碑", "痛点", "评价", "诊断", "好评"]),
    ("竞品", "竞品", ["竞品", "对标", "竞争", "对手"]),
    ("爆款策划", "爆款策划", ["爆款", "主图", "卖点", "元素"]),
    ("关键词", "关键词", ["关键词", "词根", "趋势", "需求"]),
    ("选品", "选品", ["选品", "好卖", "卖什么", "商机", "机会"]),
]

# 非 ● 档专家（不接洞察子图），标 future + tier
_FUTURE_TIERS: dict[str, dict] = {
    "客服": {"status": "future", "tier": "◐"},
    "售后": {"status": "future", "tier": "◐"},
    "核价": {"status": "future", "tier": "◐"},
    "罗盘": {"status": "future", "tier": "○"},
    "罗盘归因": {"status": "future", "tier": "○"},
    "OKR": {"status": "future", "tier": "○"},
    "经营OKR": {"status": "future", "tier": "○"},
    "直播策划": {"status": "future", "tier": "○"},
    "短视频脚本": {"status": "future", "tier": "○"},
}

_FUTURE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("客服", ["客服", "咨询", "退换货"]),
    ("罗盘归因", ["罗盘", "归因", "gmv", "ctr", "cvr"]),
    ("经营OKR", ["okr", "目标", "拆解", "日任务"]),
    ("直播策划", ["直播", "脚本", "达人"]),
    ("短视频脚本", ["短视频", "视频脚本"]),
]

# ● 洞察档意图集合
_INSIGHT_INTENTS = {r[0] for r in _INTENT_RULES}

_DEFAULT_INTENT = "选品"


class HubAgent:
    def __init__(self, skills_dir: str | None = None) -> None:
        self.skills = load_skills(skills_dir) if skills_dir else load_skills()

    def route(self, query: str) -> dict:
        """规则路由：返回 {intent, skill_chain, entry}。

        非 ● 档（客服/罗盘/OKR...）返回 {status:future, tier, intent}。
        """
        q = (query or "").lower()

        # 先看是否命中 ◐/○ 未来档专家
        for name, kws in _FUTURE_KEYWORDS:
            if any(k in q for k in kws):
                return {"intent": name, **_FUTURE_TIERS[name]}

        # ● 洞察档意图匹配
        for intent, entry, kws in _INTENT_RULES:
            if any(k in q for k in kws):
                return {
                    "intent": intent,
                    "skill_chain": skill_chain(entry, self.skills),
                    "entry": entry,
                }

        # 兜底：选品链
        return {
            "intent": _DEFAULT_INTENT,
            "skill_chain": skill_chain(_DEFAULT_INTENT, self.skills),
            "entry": _DEFAULT_INTENT,
        }

    @staticmethod
    def _parse_keyword(query: str) -> str:
        """从自然语言里粗提一个核心词（MVP：去停用词后取最长 token）。"""
        q = query or ""
        # 去掉常见请求性措辞
        for stop in ["帮我", "看看", "分析", "一下", "有什么", "怎么", "我想", "请", "的", "了", "吗", "呢"]:
            q = q.replace(stop, " ")
        tokens = [t for t in re.split(r"[\s，,。.!！?？]+", q) if t.strip()]
        return max(tokens, key=len) if tokens else (query or "").strip()

    async def handle(self, query: str) -> dict:
        """路由后，对 ● 洞察档意图驱动 P0 洞察子图；否则只返回 route 计划。"""
        plan = self.route(query)

        if plan.get("status") == "future" or plan.get("intent") not in _INSIGHT_INTENTS:
            return plan

        keyword = self._parse_keyword(query)
        try:
            from agent.graph import run_insight  # 延迟导入，缺失不影响 demo
        except Exception as exc:  # noqa: BLE001 — demo 容错
            return {**plan, "keyword": keyword, "insight": None,
                    "note": f"run_insight 不可用，仅返回路由计划：{exc}"}

        try:
            initial_state = {
                "keyword": keyword,
                "category": "",
                "region": "US",
                "topn": 5,
            }
            final_state = await run_insight(initial_state)
            return {**plan, "keyword": keyword, "insight": final_state}
        except Exception as exc:  # noqa: BLE001
            return {**plan, "keyword": keyword, "insight": None,
                    "note": f"洞察子图执行失败，仅返回路由计划：{exc}"}


if __name__ == "__main__":  # pragma: no cover
    h = HubAgent()
    for q in ["帮我看看口红有什么好卖的", "竞品对标怎么做", "这商品差评好多", "新品怎么打爆款", "今天该看什么罗盘"]:
        print(q, "->", h.route(q))
