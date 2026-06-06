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
from agent.skills.loader import load_skill_prompt
from agent.state import new_evidence_ref
from agent.wiki import IndustryWiki

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

    # C2.1：行业 Wiki 的打分口径 / 价格带诊断作为 layer="wiki" 证据注入报告。
    # 取这两页（key 即 IndustryWiki 种子键），无则跳过。
    _WIKI_KEYS = ("打分口径", "价格带诊断")

    def _wiki_refs(self) -> list[dict]:
        """把行业 Wiki 知识构造成 layer='wiki' 证据（满足"≥1 条 wiki layer"）。"""
        refs: list[dict] = []
        try:
            wiki = IndustryWiki()
        except Exception:  # noqa: BLE001 — Wiki 不可用不致命
            return refs
        for key in self._WIKI_KEYS:
            page = wiki.get(key)
            if not page:
                continue
            summary = f"{page.get('title', key)}：{page.get('summary', '')}".strip("：")
            refs.append(new_evidence_ref(
                layer="wiki",
                source_id=page.get("key") or key,
                summary=summary,
                confidence=0.9,
            ))
        return refs

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
        # C2.1：追加行业 Wiki 打分口径 / 价格带诊断作为 layer="wiki" 证据
        refs.extend(self._wiki_refs())
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

# C1：简报是四路洞察的汇总收口，注入 koubei_zhenduan.md 的诊断角色/SOP 前缀（改 MD 行为跟着变）。
_BRIEF_SKILL_PREFIX = load_skill_prompt("口碑诊断")


def _brief_system() -> str:
    return (f"{_BRIEF_SKILL_PREFIX}\n\n{_BRIEF_SYSTEM}"
            if _BRIEF_SKILL_PREFIX else _BRIEF_SYSTEM)


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
        data = llm.chat_json(_brief_system(), user, max_tokens=600)
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
    """汇总 briefings -> 最终 markdown 报告。

    C2.2：每个小节结论挂可点 [refId]，文末列证据表（refId/layer/sourceId/quote），
    其中含 ≥1 条 wiki layer（来自 Curator 注入）+ N 条 raw layer。
    """

    name = "editor"

    # 证据表最多列多少条；超出在表尾注明截断（不静默丢）。
    _EVIDENCE_TABLE_MAX = 60

    @staticmethod
    def _dedupe(refs: list[dict]) -> list[dict]:
        """按 refId 去重保序。

        并行 fan-in 下各 analyzer 的 _merge_refs 会把快照已有证据连同自己的一起返回，
        再被 graph reducer concat 一次 → 同一 refId 出现多份。报告/证据表按 refId 去重，
        保证每条证据只展示一次（不动 graph 层 reducer，是最小且安全的口径修正）。
        """
        seen: set = set()
        out: list[dict] = []
        for r in refs:
            if not isinstance(r, dict):
                continue
            rid = r.get("refId")
            if rid in seen:
                continue
            seen.add(rid)
            out.append(r)
        return out

    @staticmethod
    def _first_ref_id(refs: list[dict], layer: str) -> str | None:
        """取该 layer 第一条证据的 refId；无则 None（不硬造）。"""
        for r in refs:
            if isinstance(r, dict) and r.get("layer") == layer and r.get("refId"):
                return r["refId"]
        return None

    @staticmethod
    def _tag(ref_id: str | None) -> str:
        """把 refId 渲染成可点角标 ` [ref-x]`；无则空串。"""
        return f" [{ref_id}]" if ref_id else ""

    def _evidence_table(self, refs: list[dict]) -> list[str]:
        """渲染文末证据表（markdown）。超过上限按 refId 顺序取前 N，表尾标注截断。"""
        lines = [
            "## 证据表",
            "",
            "| refId | layer | sourceId | 引文 / 摘要 |",
            "| --- | --- | --- | --- |",
        ]
        shown = refs[: self._EVIDENCE_TABLE_MAX]
        for r in shown:
            if not isinstance(r, dict):
                continue
            quote = str(r.get("quoteOrSummary", "")).replace("|", "/").replace("\n", " ")
            src = r.get("sourceId")
            src = "—" if src in (None, "") else str(src)
            lines.append(
                f"| {r.get('refId', '')} | {r.get('layer', '')} | {src} | {quote} |"
            )
        if len(refs) > len(shown):
            lines.append("")
            lines.append(f"> （证据表仅列前 {len(shown)} 条，共 {len(refs)} 条，其余略。）")
        return lines

    async def run(self, state: dict) -> dict:
        b = state.get("briefings") or {}
        keyword = state.get("keyword") or ""
        category = state.get("category") or ""
        # 按 refId 去重后再统计/渲染（并行 fan-in 会产生重复条目）
        refs = self._dedupe(state.get("evidence_refs") or [])

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

        # 每小节挑该维度的代表证据 refId 挂到标题后（可点回查证据表）
        social_tag = self._tag(self._first_ref_id(refs, "social"))
        # 价格小节同时挂 raw（商品价格）与 wiki（打分口径）两类证据
        price_tag = (self._tag(self._first_ref_id(refs, "raw"))
                     + self._tag(self._first_ref_id(refs, "wiki")))
        hot_tag = self._tag(self._first_ref_id(refs, "hot"))
        comp_tag = self._tag(self._first_ref_id(refs, "competitor"))

        title = f"# {category + ' · ' if category else ''}{keyword} 商机洞察报告".strip()
        md_lines = [
            title,
            "",
            f"## 人群{social_tag}",
            b.get("social", "暂无"),
            "",
            f"## 价格{price_tag}",
            b.get("price", "暂无"),
            "",
            f"## 爆款{hot_tag}",
            b.get("hot", "暂无"),
            "",
            f"## 竞品{comp_tag}",
            b.get("competitor", "暂无"),
            "",
            f"## 风险{comp_tag}",
            risk_line,
            "",
            "---",
            f"> 证据引用：共 {len(refs)} 条。",
            "",
        ]
        md_lines.extend(self._evidence_table(refs))
        md = "\n".join(md_lines)
        return {
            "report": md,
            "_trace": [self._trace_entry(f"报告生成，引用 {len(refs)} 条")],
        }
