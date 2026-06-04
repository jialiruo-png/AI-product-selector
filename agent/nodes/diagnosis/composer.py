"""Composer —— 报告组装节点。

把 Checker / Attributor / Advisor 的产物组装成商家可读的 markdown 报告。
每条结论后挂可点的 [refId]，文末列证据表。
开篇用 LLM 写一段"老板视角"通顺摘要（mock 时走模板兜底）。
"""
from __future__ import annotations

from agent.llm import chat_text, has_llm

from ..base import BaseNode


def _format_anomaly_line(anomaly: dict) -> str:
    metric = anomaly["metric"]
    cur = anomaly["current"]
    baseline = anomaly["baseline"]
    dev_baseline = anomaly["deviation_vs_baseline_pct"]
    severity = anomaly["severity"]
    refs = anomaly.get("evidence_refs") or []
    refs_inline = " ".join(f"[{r}]" for r in refs[:2])
    sev_tag = "🔴" if severity == "high" else "🟡"
    return f"- {sev_tag} **{metric}** 当前 {cur} / 基线 {baseline} / 偏离 {dev_baseline}% {refs_inline}"


def _format_root_cause(chain: dict) -> str:
    metric = chain.get("anomaly_metric", "")
    candidates = chain.get("candidates") or []
    primary_idx = chain.get("primary_root_cause_index", 0)
    if not candidates:
        return f"- **{metric}**：暂无足够数据归因\n"

    lines = [f"### 异常指标：{metric}"]
    for i, c in enumerate(candidates):
        marker = "🎯" if i == primary_idx else "  "
        conf = c.get("confidence", 0)
        cv = c.get("cross_validation", "")
        refs = c.get("evidence_refs") or []
        refs_inline = " ".join(f"[{r}]" for r in refs[:2])
        cv_text = f"（{cv}）" if cv else ""
        # 如果是主因且有 LLM 增强的"商家视角"翻译，优先用通俗版本
        body = c.get("root_cause_plain") if i == primary_idx else None
        body = body or c["root_cause"]
        lines.append(f"{marker} **{body}** · 置信度 {conf}{cv_text} {refs_inline}")
        # 主因带"商家自己怎么验证"
        if i == primary_idx and c.get("what_to_check"):
            lines.append(f"     👉 你可以这样验证：{c['what_to_check']}")
    return "\n".join(lines)


def _format_action(action: dict) -> str:
    title = action.get("title", "")
    elig = action.get("eligibility") or {}
    impact = action.get("expected_impact", "")
    cost = action.get("cost_benefit", "")
    url = (action.get("resource") or {}).get("url", "")
    refs = action.get("evidence_refs") or []
    refs_inline = " ".join(f"[{r}]" for r in refs[:1])
    why = action.get("why_worth_it", "")

    cost_tag = {"high": "【高性价比】", "medium": "【中等】", "low": "【需观察】"}.get(cost, "")
    elig_note = "✅" if elig.get("met") else f"⚠️ {elig.get('details', '')}"
    why_line = f"\n  - 💡 为什么做：{why}" if why else ""
    return (
        f"- {cost_tag} **{title}** {refs_inline}\n"
        f"  - 资源：`{url}`\n"
        f"  - 准入：{elig_note}\n"
        f"  - 预期：{impact}{why_line}"
    )


def _format_evidence_table(refs: list[dict]) -> str:
    if not refs:
        return ""
    rows = ["", "## 📚 证据引用表", "| refId | 层 | 来源 | 摘要 |", "|---|---|---|---|"]
    for r in refs[:30]:  # 控量
        ref_id = r.get("refId", "")
        layer = r.get("layer", "")
        # 不同 layer 用不同 source 字段
        source = (
            r.get("sourceId") or r.get("pageId") or r.get("imageId")
            or r.get("strategyActionId") or r.get("semanticUnitId")
            or r.get("skillRunId") or "-"
        )
        summary = (r.get("quoteOrSummary") or "")[:60]
        rows.append(f"| {ref_id} | {layer} | {source} | {summary} |")
    if len(refs) > 30:
        rows.append(f"| ... | ... | ... | （共 {len(refs)} 条，仅展示前 30 条） |")
    return "\n".join(rows)


def _shop_header(profile: dict, summary: str) -> str:
    name = profile.get("shop_name") or profile.get("shop_id") or "未知店铺"
    category = profile.get("category", "")
    level = profile.get("shop_level", "")
    exp_score = profile.get("exp_score", "?")
    return (
        f"# 📋 经营诊断报告 · {name}\n\n"
        f"> 类目：{category} · 等级：{level} · 体验分：{exp_score}\n\n"
        f"## 🎯 核心问题\n\n**{summary}**\n"
    )


_LLM_OPENING_SYSTEM = """你是抖音电商资深运营顾问，给一个店铺老板看的经营诊断报告写一段开篇摘要。

要求：
- 100-150 字之间，一段话，不分段
- 老板视角，"你的店本周..."句式开头
- 必须串起：核心问题 → 1-2 条主要根因 → 1-2 条最值得做的动作
- 用大白话，不用"漏斗/CR/ROI"等术语
- 结尾用激励语气，避免悲观
"""


def _llm_opening(profile: dict, summary: str, anomalies: list[dict],
                 chains: list[dict], actions: list[dict],
                 top_n: list[int]) -> str:
    """开篇 LLM 摘要。无 LLM 时返回空（不写这段）。"""
    if not has_llm():
        return ""

    # 拼一份精简 context，避免塞太多 token
    name = profile.get("shop_name", "店铺")
    top_anomaly = anomalies[0] if anomalies else None
    primary_causes = []
    for chain in chains[:2]:
        cands = chain.get("candidates") or []
        idx = chain.get("primary_root_cause_index", 0)
        if idx < len(cands):
            primary = cands[idx]
            primary_causes.append(
                primary.get("root_cause_plain") or primary.get("root_cause", "")
            )

    top_actions = []
    for idx in top_n[:3]:
        if idx < len(actions):
            top_actions.append(actions[idx]["title"])

    user_payload = (
        f"店名：{name}\n"
        f"核心问题：{summary}\n"
        f"主要根因：\n" + "\n".join(f"- {c}" for c in primary_causes) + "\n"
        f"建议优先动作：\n" + "\n".join(f"- {a}" for a in top_actions)
    )
    return chat_text(
        system=_LLM_OPENING_SYSTEM,
        user=user_payload,
        max_tokens=400,
        temperature=0.5,
        mock_fallback="",
    )


class Composer(BaseNode):
    """报告组装：把诊断/归因/建议组装成商家可读 markdown。"""

    name = "composer"

    async def run(self, state: dict) -> dict:
        profile = state.get("shop_profile") or {}
        summary = state.get("diagnosis_summary") or "(无核心问题)"
        anomalies = state.get("anomalies") or []
        overlays = state.get("matched_overlays") or []
        chains = state.get("root_cause_chains") or []
        non_data_signals = state.get("non_data_signals") or []
        actions = state.get("actions") or []
        top_n = state.get("top_n_for_user") or list(range(min(5, len(actions))))
        refs = state.get("evidence_refs") or []
        completeness = state.get("data_completeness", 0)

        parts: list[str] = []

        # 头部
        parts.append(_shop_header(profile, summary))

        # 命中 overlay
        if overlays:
            parts.append(
                f"\n> 🏷️ 适用画像：{' / '.join(overlays)} · 数据完整度 {int(completeness * 100)}%\n"
            )

        # LLM 开篇摘要（老板视角通俗版）
        opening = _llm_opening(profile, summary, anomalies, chains, actions, top_n)
        if opening:
            parts.append(f"\n## 📝 一句话讲清楚\n\n{opening}\n")

        # 异常清单
        if anomalies:
            parts.append("\n## ⚠️ 异常指标清单\n")
            for a in anomalies:
                parts.append(_format_anomaly_line(a))
        else:
            parts.append("\n## ✅ 异常指标清单\n\n暂无显著异常。\n")

        # 根因链
        if chains:
            parts.append("\n## 🔎 为什么会这样（根因链）\n")
            for chain in chains:
                parts.append(_format_root_cause(chain))
                parts.append("")

        # 非数据信号
        if non_data_signals:
            parts.append("\n## 📡 非数据信号（平台规则/玩法变动）\n")
            for sig in non_data_signals:
                parts.append(f"- {sig['signal']} `[{sig['source_ref_id']}]`")

        # TOP 行动建议
        if top_n:
            parts.append("\n## 🚀 本周建议（按性价比 × 置信度排序）\n")
            for idx in top_n:
                if idx < len(actions):
                    parts.append(_format_action(actions[idx]))
                    parts.append("")

        # 证据表
        parts.append(_format_evidence_table(refs))

        report = "\n".join(parts)

        note = (
            f"report {len(report)} chars · "
            f"anomalies={len(anomalies)} chains={len(chains)} "
            f"actions={len(actions)} refs={len(refs)}"
        )

        return {
            "report": report,
            "_trace": [self._trace_entry(note)],
        }
