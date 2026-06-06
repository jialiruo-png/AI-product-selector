"""核价 Agent（◐ 档，纯本地利润核算）。

PRD D1：商家成本数据 → 利润核算表。**不依赖任何平台 API / 网络 / LLM**，
是「框架可横向长出新专家」的最小证明——同一套 BaseNode/SellerWiki/证据引用
协议，换一份 Skill MD + 一个本地节点就成立一个新专家。

成本来源（优先级）：
    1. state["cost"]（dict）——直接喂数据，无 Wiki 也能跑 / mock 友好。
    2. SellerWiki：按 state["seller_id"] + cost_key 取商家私域成本页。
    3. 都没有 → 确定性示例成本（保证永不崩，演示可见）。
"""
from __future__ import annotations

from typing import Any

from agent.skills.loader import load_skill_prompt
from agent.state import new_evidence_ref

from .base import BaseNode

# C1：保持「配置即技能」一致性——核价角色/SOP 从 hejia.md 读（改 MD 行为跟着变）。
# 核算本身是确定性 f-string，不调 LLM；前缀留作未来 LLM 建议位。
_SKILL_PREFIX = load_skill_prompt("核价")

# 成本页字段别名（兼容中英文 / 不同录入习惯）。取第一个非空。
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "售价": ("售价", "price", "sale_price", "零售价"),
    "进货成本": ("进货成本", "成本", "cost", "采购成本", "货值"),
    "物流": ("物流", "运费", "shipping", "freight"),
    "佣金率": ("佣金率", "平台佣金率", "commission_rate", "take_rate"),
    "营销费": ("营销费", "推广费", "marketing", "ad_cost", "广告费"),
    "其他": ("其他", "其他费用", "misc", "other"),
}


def _pick_num(cost: dict, canonical: str) -> float:
    """从成本 dict 按别名取数值，缺失/非数返回 0.0。"""
    for k in _FIELD_ALIASES.get(canonical, (canonical,)):
        if k in cost and cost[k] not in (None, ""):
            try:
                return float(cost[k])
            except (TypeError, ValueError):
                continue
    return 0.0


def compute_profit(cost: dict) -> dict:
    """纯函数利润核算。给定成本 dict，返回核算结果（永不抛）。

    入参（任一别名即可，缺失补 0）：
        售价 / 进货成本 / 物流 / 佣金率 / 营销费 / 其他
    返回:
        {ok, 售价, 毛利, 平台佣金, 净利, 净利率, 保本售价, 加价倍率, ...}
        售价 <= 0 时返回 {ok: False, error}。
    """
    try:
        if not isinstance(cost, dict):
            return {"ok": False, "error": "成本数据格式错误（需 dict）"}

        price = _pick_num(cost, "售价")
        purchase = _pick_num(cost, "进货成本")
        shipping = _pick_num(cost, "物流")
        rate = _pick_num(cost, "佣金率")
        marketing = _pick_num(cost, "营销费")
        other = _pick_num(cost, "其他")

        # 佣金率若写成百分数（如 5 表示 5%），> 1 时按百分比折算。
        if rate > 1:
            rate = rate / 100.0

        if price <= 0:
            return {"ok": False, "error": "售价必须 > 0 才能核算（请录入售价）"}

        commission = round(price * rate, 2)
        gross = round(price - purchase - shipping, 2)        # 毛利
        net = round(gross - commission - marketing - other, 2)  # 净利
        net_rate = round(net / price, 4) if price else 0.0

        # 保本售价：净利 = 0 反解 price。
        # net = price*(1-rate) - purchase - shipping - marketing - other = 0
        denom = 1 - rate
        fixed = purchase + shipping + marketing + other
        breakeven = round(fixed / denom, 2) if denom > 0 else None

        markup = round(price / purchase, 2) if purchase > 0 else None  # 加价倍率

        return {
            "ok": True,
            "售价": round(price, 2),
            "进货成本": round(purchase, 2),
            "物流": round(shipping, 2),
            "佣金率": rate,
            "平台佣金": commission,
            "营销费": round(marketing, 2),
            "其他": round(other, 2),
            "毛利": gross,
            "净利": net,
            "净利率": net_rate,
            "保本售价": breakeven,
            "加价倍率": markup,
        }
    except Exception as exc:  # noqa: BLE001 — 核价层兜底，绝不上抛
        return {"ok": False, "error": str(exc)}


def _mock_cost() -> dict:
    """无 Wiki / 无入参时的确定性示例成本（保证永不崩、演示可见）。"""
    return {"售价": 99.0, "进货成本": 30.0, "物流": 8.0,
            "佣金率": 0.05, "营销费": 10.0, "其他": 2.0}


def _format_report(sku: str, calc: dict) -> str:
    """把核算结果渲染成一段中文利润表（确定性 markdown，不依赖 LLM）。"""
    if not calc.get("ok"):
        return f"# {sku} 利润核算\n\n核算失败：{calc.get('error', '未知错误')}"

    net_rate_pct = f"{calc['净利率'] * 100:.1f}%"
    breakeven = calc.get("保本售价")
    breakeven_txt = f"{breakeven} 元" if breakeven is not None else "—（佣金率≥100%，无解）"
    markup = calc.get("加价倍率")
    markup_txt = f"{markup} 倍" if markup is not None else "—（无进货成本）"
    verdict = "✅ 盈利" if calc["净利"] > 0 else ("⚠️ 保本" if calc["净利"] == 0 else "❌ 亏损")

    return (
        f"# {sku} 利润核算\n\n"
        f"| 项目 | 金额(元) |\n"
        f"| --- | --- |\n"
        f"| 售价 | {calc['售价']} |\n"
        f"| 进货成本 | {calc['进货成本']} |\n"
        f"| 物流 | {calc['物流']} |\n"
        f"| 平台佣金（{calc['佣金率'] * 100:.1f}%） | {calc['平台佣金']} |\n"
        f"| 营销费 | {calc['营销费']} |\n"
        f"| 其他 | {calc['其他']} |\n"
        f"| **毛利** | **{calc['毛利']}** |\n"
        f"| **净利** | **{calc['净利']}** |\n\n"
        f"- 净利率：**{net_rate_pct}**　{verdict}\n"
        f"- 保本售价：{breakeven_txt}\n"
        f"- 加价倍率：{markup_txt}\n"
    )


class PricingNode(BaseNode):
    """核价节点：成本（state.cost / SellerWiki）→ compute_profit → 利润表。

    可独立调用（HubAgent.handle 直接 await node.run(state)），不进洞察子图。
    """

    name = "pricing"

    @staticmethod
    def _resolve_cost(state: dict) -> tuple[str, dict, str]:
        """解析成本来源，返回 (sku, cost_dict, source_note)。"""
        sku = str(state.get("sku") or state.get("keyword") or "新品")

        # 1) state 直接带 cost
        cost = state.get("cost")
        if isinstance(cost, dict) and cost:
            return sku, cost, "state.cost"

        # 2) SellerWiki：seller_id + cost_key（默认 "成本:<sku>"）
        seller_id = state.get("seller_id")
        wiki = state.get("_seller_wiki")  # 测试 / Hub 注入实例
        if seller_id and wiki is not None:
            cost_key = state.get("cost_key") or f"成本:{sku}"
            page = None
            try:
                page = wiki.get(seller_id, cost_key)
            except Exception:  # noqa: BLE001 — Wiki 不可用不致命
                page = None
            if isinstance(page, dict):
                return sku, page, f"SellerWiki[{seller_id}/{cost_key}]"

        # 3) 兜底示例成本
        return sku, _mock_cost(), "示例成本（mock 回退）"

    async def run(self, state: dict) -> dict:
        sku, cost, src = self._resolve_cost(state)
        calc = compute_profit(cost)
        report = _format_report(sku, calc)

        summary = (f"{sku} 净利 {calc.get('净利')} 元（净利率 "
                   f"{(calc.get('净利率') or 0) * 100:.1f}%）"
                   if calc.get("ok") else f"{sku} 核算失败：{calc.get('error')}")
        refs: list[dict] = [new_evidence_ref(
            layer="strategy_action",
            source_id=sku,
            summary=f"核价：{summary}（来源 {src}）",
            confidence=0.9 if calc.get("ok") else 0.3,
        )]

        return {
            "pricing_data": calc,
            "pricing_report": report,
            "evidence_refs": self._merge_refs(state, refs),
            "_trace": [self._trace_entry(f"核价完成（{src}）：{summary}")],
        }
