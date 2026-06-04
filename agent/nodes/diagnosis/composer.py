"""Composer —— 报告组装节点。

把 Checker / Attributor / Advisor 的产物组装成商家可读的 markdown 报告。
每条结论后挂可点的 [refId]，文末列证据表。
"""
from __future__ import annotations

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
        lines.append(f"{marker} **{c['root_cause']}** · 置信度 {conf}{cv_text} {refs_inline}")
    return "\n".join(lines)


def _format_action(action: dict) -> str:
    title = action.get("title", "")
    elig = action.get("eligibility") or {}
    impact = action.get("expected_impact", "")
    cost = action.get("cost_benefit", "")
    url = (action.get("resource") or {}).get("url", "")
    refs = action.get("evidence_refs") or []
    refs_inline = " ".join(f"[{r}]" for r in refs[:1])

    cost_tag = {"high": "【高性价比】", "medium": "【中等】", "low": "【需观察】"}.get(cost, "")
    elig_note = "✅" if elig.get("met") else f"⚠️ {elig.get('details', '')}"
    return (
        f"- {cost_tag} **{title}** {refs_inline}\n"
        f"  - 资源：`{url}`\n"
        f"  - 准入：{elig_note}\n"
        f"  - 预期：{impact}"
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
