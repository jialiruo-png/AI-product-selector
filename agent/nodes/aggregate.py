"""汇总/收敛节点：
    - Collector : 合并四路 raw_data，确保都存在（no-op 聚合）。
    - Curator   : relevance/threshold 过滤，写 curated_* (port curator.py)。
    - Briefing  : MOCK LLM，基于 curated 数据产出四路简报。
    - Editor    : 装配最终 markdown report。
"""
from __future__ import annotations

from typing import Any

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
class Briefing(BaseNode):
    """四路简报（MOCK LLM，真实 f-string 摘要）。"""

    name = "briefing"

    async def run(self, state: dict) -> dict:
        social = state.get("curated_social_data") or state.get("social_data") or {}
        price = state.get("curated_price_data") or state.get("price_data") or {}
        hot = state.get("curated_hot_data") or state.get("hot_data") or {}
        comp = state.get("curated_competitor_data") or state.get("competitor_data") or {}

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

        # TODO: wire real LLM —— 用上述结构化数据生成自然语言简报。
        briefings = {
            "social": social_b,
            "price": price_b,
            "hot": hot_b,
            "competitor": comp_b,
        }
        return {
            "briefings": briefings,
            "_trace": [self._trace_entry("生成四路简报")],
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
