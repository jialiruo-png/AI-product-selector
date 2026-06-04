"""汇总/收敛节点：
    - Collector : 合并四路 raw_data，确保都存在（no-op 聚合）。
    - Curator   : relevance/threshold 过滤，写 curated_* (port curator.py)。
    - Briefing  : MOCK LLM，基于 curated 数据产出四路简报。
    - Editor    : 装配最终 markdown report。
"""
from __future__ import annotations

import json
from typing import Any

from agent import llm
from agent.state import new_evidence_ref

from .base import BaseNode


_DATA_FIELDS = ("social_data", "price_data", "hot_data", "competitor_data")


# --------------------------------------------------------------------------- #
# Collector
# --------------------------------------------------------------------------- #
class Collector(BaseNode):
    """合并四路 raw_data，缺失的补空 dict。"""

    name = "collector"

    async def run(self, state: dict) -> dict:
        out: dict[str, Any] = {}
        present = []
        for f in _DATA_FIELDS:
            val = state.get(f)
            if val:
                present.append(f)
            else:
                out[f] = {}  # 确保存在，下游不 KeyError
        note = f"已收集 {len(present)}/{len(_DATA_FIELDS)} 路数据"
        out["_trace"] = [self._trace_entry(note)]
        return out


# --------------------------------------------------------------------------- #
# Curator —— port 自 company-research-agent/backend/nodes/curator.py
# --------------------------------------------------------------------------- #
class Curator(BaseNode):
    """对四路数据做相关性/阈值过滤，写入 curated_* 字段。

    MVP：pass-through，但丢弃空 dict / 空列表项。沿用 curator.py 的
    "按字段循环 + 阈值过滤 + 记 message" 思路。
    """

    name = "curator"
    relevance_threshold = 0.4

    def _curate_one(self, field: str, data: dict) -> dict:
        """对单路数据做轻量净化：丢空、按 score 过滤列表项。"""
        if not data:
            return {}
        curated: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, list):
                kept = []
                for item in v:
                    if not item:
                        continue
                    # 若 item 带 score，低于阈值丢弃
                    if isinstance(item, dict) and "score" in item:
                        try:
                            if float(item["score"]) < self.relevance_threshold:
                                continue
                        except (TypeError, ValueError):
                            pass
                    kept.append(item)
                curated[k] = kept
            elif isinstance(v, dict):
                curated[k] = v if v else {}
            else:
                curated[k] = v
        return curated

    async def run(self, state: dict) -> dict:
        out: dict[str, Any] = {}
        msgs = []
        for f in _DATA_FIELDS:
            data = state.get(f) or {}
            curated = self._curate_one(f, data)
            out[f"curated_{f}"] = curated
            msgs.append(f"{f}: {'有数据' if curated else '空'}")

        refs = [new_evidence_ref(
            layer="curated",
            source_id=None,
            summary="已完成四路数据净化（curated）",
            confidence=0.6,
        )]
        out["evidence_refs"] = self._merge_refs(state, refs)
        out["messages"] = list(state.get("messages") or []) + ["[curator] " + "; ".join(msgs)]
        out["_trace"] = [self._trace_entry("; ".join(msgs))]
        return out


# --------------------------------------------------------------------------- #
# Briefing —— MOCK LLM，基于 curated 数据生成简报
# --------------------------------------------------------------------------- #
_BRIEF_SYSTEM = """你是电商选品分析师。给定四路结构化洞察数据（人群/价格/爆款/竞品）的事实，
为每一路写一句话简报，要有洞察、可执行，像给老板的决策摘要。只输出 JSON：
{"social": "...", "price": "...", "hot": "...", "competitor": "..."}
严格约束：
- 每段 <=60 字，中文，不要罗列、不要 markdown。
- 只能使用我给的事实（人群名/价格区间/商品名/痛点等），数字必须照抄，禁止编造任何未提供的数据。
- 缺数据的那一路原样输出"暂无XX数据"。
- 比起复述事实，更要点出"机会"或"该怎么做"（如机会带说明可切入、痛点说明可差异化）。"""


class Briefing(BaseNode):
    """四路简报。优先用 LLM 把结构化事实写成洞察句；缺 key / 失败回退 f-string 摘要。"""

    name = "briefing"

    @staticmethod
    def _fallback(social, price, hot, comp) -> dict:
        """确定性 f-string 摘要（mock / 缺 key / LLM 失败时用，永不崩）。"""
        # --- social ---
        personas = social.get("personas") or []
        if personas:
            names = "、".join(str(p.get("name", "")) for p in personas)
            needs = "、".join(str(p.get("need", "")) for p in personas if p.get("need"))
            social_b = f"核心人群：{names}。主要诉求：{needs or '未知'}。"
        else:
            social_b = "暂无社媒人群数据。"

        # --- price ---
        bands = price.get("bands") or []
        gap = price.get("gap_band") or {}
        if bands:
            gap_rng = gap.get("range")
            gap_txt = f"机会带 {gap_rng[0]}~{gap_rng[1]}（供给最少）" if gap_rng else "暂无明显机会带"
            price_b = f"共 {len(bands)} 个价格带。{gap_txt}。"
        else:
            price_b = "暂无价格带数据。"

        # --- hot ---
        hot_items = hot.get("hot_items") or []
        if hot_items:
            titles = "；".join(str(h.get("title", ""))[:20] for h in hot_items)
            hot_b = f"Top{len(hot_items)} 爆款：{titles}。共性元素：颜色/材质。"
        else:
            hot_b = "暂无爆款数据。"

        # --- competitor ---
        competitors = comp.get("competitors") or []
        ri = comp.get("review_insights") or {}
        pps = ri.get("pain_points") or []
        if competitors:
            pp_labels = "、".join(
                str(p.get("label") if isinstance(p, dict) else p) for p in pps[:3]
            )
            comp_b = (
                f"竞品 {len(competitors)} 个。"
                f"{('主要痛点：' + pp_labels + '。') if pp_labels else '暂无明显痛点。'}"
            )
        else:
            comp_b = "暂无竞品数据。"

        return {"social": social_b, "price": price_b, "hot": hot_b, "competitor": comp_b}

    @staticmethod
    def _facts(social, price, hot, comp) -> dict:
        """抽取喂给 LLM 的纯事实（结构化、去冗余），避免模型看到噪声乱编。"""
        gap = (price.get("gap_band") or {}).get("range")
        pps = ((comp.get("review_insights") or {}).get("pain_points")) or []
        return {
            "人群": [
                {"name": p.get("name"), "need": p.get("need"), "scene": p.get("scene")}
                for p in (social.get("personas") or [])
            ],
            "价格带数量": len(price.get("bands") or []),
            "机会带区间": gap,
            "爆款商品": [str(h.get("title", ""))[:40] for h in (hot.get("hot_items") or [])],
            "竞品数量": len(comp.get("competitors") or []),
            "竞品痛点": [
                (p.get("label") if isinstance(p, dict) else str(p)) for p in pps[:5]
            ],
        }

    def _llm_briefings(self, facts: dict, fallback: dict) -> dict | None:
        user = "事实数据（JSON）：\n" + json.dumps(facts, ensure_ascii=False)
        data = llm.chat_json(_BRIEF_SYSTEM, user, max_tokens=600)
        if not isinstance(data, dict):
            return None
        # 四个键都得有内容，缺的用 fallback 补，保证下游 Editor 不出现空段
        out = {}
        for k in ("social", "price", "hot", "competitor"):
            v = data.get(k)
            out[k] = str(v).strip() if isinstance(v, str) and v.strip() else fallback[k]
        return out

    async def run(self, state: dict) -> dict:
        social = state.get("curated_social_data") or state.get("social_data") or {}
        price = state.get("curated_price_data") or state.get("price_data") or {}
        hot = state.get("curated_hot_data") or state.get("hot_data") or {}
        comp = state.get("curated_competitor_data") or state.get("competitor_data") or {}

        fallback = self._fallback(social, price, hot, comp)
        briefings = self._llm_briefings(self._facts(social, price, hot, comp), fallback)
        if briefings:
            note = "生成四路简报（LLM）"
        else:
            briefings = fallback
            note = "生成四路简报（mock 回退）"

        return {
            "briefings": briefings,
            "_trace": [self._trace_entry(note)],
        }


# --------------------------------------------------------------------------- #
# Editor —— 装配 markdown report
# --------------------------------------------------------------------------- #
class Editor(BaseNode):
    """汇总 briefings -> 最终 markdown 报告。"""

    name = "editor"

    async def run(self, state: dict) -> dict:
        b = state.get("briefings") or {}
        keyword = state.get("keyword") or ""
        category = state.get("category") or ""
        refs = state.get("evidence_refs") or []

        # 风险：从竞品痛点粗提
        comp = state.get("curated_competitor_data") or state.get("competitor_data") or {}
        pps = (comp.get("review_insights") or {}).get("pain_points") or []
        if pps:
            risk = "、".join(
                str(p.get("label") if isinstance(p, dict) else p) for p in pps[:3]
            )
            risk_line = f"竞品已暴露痛点（{risk}），进入前需在这些维度做差异化。"
        else:
            risk_line = "暂未发现显著负面口碑风险，仍需持续监控。"

        title = f"# {category + ' · ' if category else ''}{keyword} 商机洞察报告".strip()
        md = "\n".join([
            title,
            "",
            "## 人群",
            b.get("social", "暂无"),
            "",
            "## 价格",
            b.get("price", "暂无"),
            "",
            "## 爆款",
            b.get("hot", "暂无"),
            "",
            "## 竞品",
            b.get("competitor", "暂无"),
            "",
            "## 风险",
            risk_line,
            "",
            "---",
            f"> 证据引用：共 {len(refs)} 条。",
        ])
        return {
            "report": md,
            "_trace": [self._trace_entry(f"报告生成，引用 {len(refs)} 条")],
        }
