"""Hub Agent —— 路由层（PRD 1.1）。

MVP 用关键词/规则做意图识别（非 LLM），把商家自然语言路由到对应专家，
并沿 Skill MD 的 next_skill 串成 Skill 链。

意图档位（路由优先级 = 列表顺序）：
- P0 经营诊断（贾丽婼诊断子图）：在运营商家 GMV/成交诊断
- P1 ◐ 本地可执行专家（甘华梁）：核价 / 客服，直接走 agent/nodes 下的本地节点
- P2 ○ 未来档专家：罗盘归因 / 经营OKR / 直播 / 短视频，仅返回路由计划
- P3 ● 洞察档（甘华梁冷启动子图）：选品 / 关键词 / 竞品 / 爆款策划 / 口碑诊断
- 兜底：选品链
"""
from __future__ import annotations

import re
from typing import Any

from agent.skills.loader import load_skills, skill_chain

# 意图 -> (起始 Skill, 触发关键词)。规则按列表顺序匹配，先命中先生效。
# 经营诊断意图（贾丽婼）排在最前——明确针对"在运营商家"场景，避免被"诊断"
# 字眼误路由到甘华梁的"口碑诊断"链。
_INTENT_RULES: list[tuple[str, str, list[str]]] = [
    ("经营诊断", "经营诊断", [
        "卖不动", "卖不好", "gmv 跌", "gmv跌", "成交跌", "店铺诊断",
        "经营诊断", "经营报告", "店铺体检", "为什么没卖好", "为什么跌",
        "复盘", "我的店", "店铺", "诊断我", "体验分", "退款率",
    ]),
    ("口碑诊断", "口碑诊断", ["差评", "口碑", "痛点", "评价", "好评"]),
    ("竞品", "竞品", ["竞品", "对标", "竞争", "对手"]),
    ("爆款策划", "爆款策划", ["爆款", "主图", "卖点", "元素"]),
    ("关键词", "关键词", ["关键词", "词根", "趋势", "需求"]),
    ("选品", "选品", ["选品", "好卖", "卖什么", "商机", "机会"]),
]

# ◐ 本地可执行专家（甘华梁 D1）：不接洞察子图，走 agent/nodes 下的独立本地节点。
# intent -> {expert: 节点标识, tier}。route 命中即返回 {local: True, expert, ...}。
_LOCAL_EXPERTS: dict[str, dict] = {
    "核价": {"expert": "pricing", "tier": "◐"},
    "客服": {"expert": "support", "tier": "◐"},
}

# 本地专家触发词（优先级在经营诊断之后、其他洞察/future 之前）
_LOCAL_KEYWORDS: list[tuple[str, list[str]]] = [
    ("核价", ["核价", "核算", "利润", "成本", "定价", "毛利", "净利"]),
    ("客服", ["客服", "咨询", "退换货", "退货", "退款", "物流", "怎么退"]),
]

# 非 ● 非 ◐ 档专家（不接洞察子图、本期不落地），标 future + tier
_FUTURE_TIERS: dict[str, dict] = {
    "售后": {"status": "future", "tier": "◐"},
    "罗盘": {"status": "future", "tier": "○"},
    "罗盘归因": {"status": "future", "tier": "○"},
    "OKR": {"status": "future", "tier": "○"},
    "经营OKR": {"status": "future", "tier": "○"},
    "直播策划": {"status": "future", "tier": "○"},
    "短视频脚本": {"status": "future", "tier": "○"},
}

_FUTURE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("罗盘归因", ["罗盘", "归因", "gmv", "ctr", "cvr"]),
    ("经营OKR", ["okr", "目标", "拆解", "日任务"]),
    ("直播策划", ["直播", "脚本", "达人"]),
    ("短视频脚本", ["短视频", "视频脚本"]),
]

# ● 洞察档意图集合
_INSIGHT_INTENTS = {r[0] for r in _INTENT_RULES}

_DEFAULT_INTENT = "选品"


class HubAgent:
    def __init__(
        self,
        skills_dir: str | None = None,
        *,
        seller_id: str | None = None,
        seller_wiki: Any = None,
        pricing_cost: dict | None = None,
    ) -> None:
        self.skills = load_skills(skills_dir) if skills_dir else load_skills()
        # ◐ 本地专家上下文：商家租户 ID + 私域 Wiki 实例 + 可选预置成本。
        # 缺省全 None —— 核价/客服各 Node 自有兜底（示例成本 / 转人工），mock 永不崩。
        self._seller_id = seller_id
        self._seller_wiki = seller_wiki
        self._pricing_cost = pricing_cost

    def route(self, query: str) -> dict:
        """规则路由：返回 {intent, ...}。

        优先级：经营诊断（贾丽婼）→ ◐ 本地核价/客服（甘华梁）→ ○ future 档
              → 其他 ● 洞察档（甘华梁冷启动子图）→ 兜底选品。
        把"经营诊断"放在最前，避免被 future 档的"罗盘/gmv"关键词抢路由；
        把"本地核价/客服"放在 future 之前，避免被 future 默认覆盖。
        """
        q = (query or "").lower()

        # P0：经营诊断意图（贾丽婼诊断子图）
        for intent, entry, kws in _INTENT_RULES:
            if intent == "经营诊断" and any(k in q for k in kws):
                return {
                    "intent": intent,
                    "skill_chain": skill_chain(entry, self.skills),
                    "entry": entry,
                }

        # P1：◐ 本地可执行专家（核价/客服）—— 走本地节点，非 future
        for name, kws in _LOCAL_KEYWORDS:
            if any(k in q for k in kws):
                return {"intent": name, "local": True, **_LOCAL_EXPERTS[name]}

        # P2：○ 未来档专家
        for name, kws in _FUTURE_KEYWORDS:
            if any(k in q for k in kws):
                return {"intent": name, **_FUTURE_TIERS[name]}

        # P3：其他 ● 洞察档（甘华梁冷启动子图）
        for intent, entry, kws in _INTENT_RULES:
            if intent == "经营诊断":
                continue  # 已在 P0 处理
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

    async def _handle_local(self, plan: dict, query: str) -> dict:
        """◐ 本地专家（核价/客服）分派：实例化对应 Node 并执行。

        缺成本/缺 FAQ 时各 Node 自有兜底（mock 永不崩），此处只负责构造
        initial_state 并捕获异常，失败仍返回 route 计划 + note。
        """
        expert = plan.get("expert")
        keyword = self._parse_keyword(query)
        try:
            if expert == "pricing":
                from agent.nodes.pricing import PricingNode
                state = {
                    "sku": keyword,
                    "seller_id": self._seller_id,
                    "_seller_wiki": self._seller_wiki,
                    "cost": self._pricing_cost,  # 可由调用方预置；None 则节点兜底
                }
                result = await PricingNode().run(state)
            elif expert == "support":
                from agent.nodes.support import SupportNode
                state = {
                    "seller_id": self._seller_id,
                    "question": query,
                    "_seller_wiki": self._seller_wiki,
                }
                result = await SupportNode().run(state)
            else:
                return {**plan, "note": f"未知本地专家 expert={expert}"}
        except Exception as exc:  # noqa: BLE001 — demo 容错
            return {**plan, "keyword": keyword, "result": None,
                    "note": f"本地专家执行失败，仅返回路由计划：{exc}"}
        return {**plan, "keyword": keyword, "result": result}

    async def handle(self, query: str, shop_id: str | None = None) -> dict:
        """路由后分派：

        - 经营诊断意图（贾丽婼）→ run_diagnosis（线性子图，4 节点）
        - ◐ 本地专家（甘华梁）→ _handle_local（核价/客服本地节点）
        - ● 洞察档（甘华梁）→ run_insight（4 路并行子图，9 节点）
        - ○ future 档：仅返回 route 计划
        """
        plan = self.route(query)

        # 经营诊断意图：分发到诊断子图
        if plan.get("intent") == "经营诊断":
            try:
                from agent.graph import run_diagnosis  # 延迟导入，缺失不影响 demo
            except Exception as exc:  # noqa: BLE001
                return {**plan, "diagnosis": None,
                        "note": f"run_diagnosis 不可用：{exc}"}
            try:
                initial_state = {
                    "shop_id": shop_id or "case_1",
                    "user_query": query,
                    "window": "7d",
                }
                final_state = await run_diagnosis(initial_state)
                return {**plan, "shop_id": initial_state["shop_id"], "diagnosis": final_state}
            except Exception as exc:  # noqa: BLE001
                return {**plan, "diagnosis": None,
                        "note": f"诊断子图执行失败：{exc}"}

        # ◐ 本地可执行专家（核价/客服）
        if plan.get("local"):
            return await self._handle_local(plan, query)

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
    for q in [
        "帮我看看口红有什么好卖的",
        "竞品对标怎么做",
        "这商品差评好多",
        "新品怎么打爆款",
        "今天该看什么罗盘",
        "我店铺最近 GMV 跌了",
        "帮我算下这件商品的核价",
        "买家问怎么退货",
    ]:
        print(q, "->", h.route(q))
