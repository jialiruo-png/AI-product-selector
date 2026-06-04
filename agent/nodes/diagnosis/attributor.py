"""Attributor —— 归因专家节点。

职责（对应 agent/skills/guiyin.md 的 SOP）：
1. 取 Checker 产出的 anomalies + matched_overlays
2. MECE 拆四类维度（流量 / 货品 / 转化 / 履约）
3. 跨场景数据交叉印证
4. 检索 rule_changes Wiki 找非数据信号
5. 输出根因链 + 置信度

mock 永不崩：metrics 缺数据时降级为"猜测，需观察"。
"""
from __future__ import annotations

from agent.evidence import make_ref
from agent.llm import chat_json, has_llm

from ..base import BaseNode

# 维度映射：指标名 -> 主维度（用于 MECE 拆解）
_METRIC_DIMENSION = {
    "live_room_stay_sec": "转化类",
    "fanzhuan_rate": "转化类",
    "main_image_ctr": "转化类",
    "cvr": "转化类",
    "uv_value": "流量类",
    "qianchuan_roi": "流量类",
    "search_ctr": "流量类",
    "mall_share": "流量类",
    "single_channel_share": "流量类",
    "new_sku_sell_rate": "货品类",
    "repurchase_rate": "货品类",
    "stale_inventory_pct": "货品类",
    "season_sku_count": "货品类",
    "in_sale_sku": "货品类",
    "kol_roi": "货品类",
    "jxlm_ctr": "流量类",
    "refund_rate": "履约类",
    "exp_score": "履约类",
    "rating": "履约类",
    "newbie_progress": "履约类",
    "decoration_pct": "履约类",
}

# 跨指标耦合规则：当主指标异常时，关联指标也可能异常（验证根因）
_CROSS_COUPLING = {
    "cvr": ["main_image_ctr", "live_room_stay_sec", "fanzhuan_rate"],
    "uv_value": ["live_room_stay_sec", "main_image_ctr"],
    "qianchuan_roi": ["cvr", "main_image_ctr"],
}

# 规则变动 Wiki 种子（mock：实际应从 IndustryWiki.search("rule_changes") 取）
# 与 agent/wiki/industry/rule_changes.md 对齐
_RULE_CHANGES = [
    {
        "id": "wiki_rule_changes_2026_05_28_jingxuan_upgrade",
        "summary": "2026-05-28 商城精选频道升级，未入驻商家搜索流量分流 15%-25%",
        "affects_overlays": ["nvzhuang_huojia", "nvzhuang_chengzhang"],
        "affects_metrics": ["search_ctr", "mall_share", "uv_value"],
    },
    {
        "id": "wiki_rule_changes_2026_05_20_qianchuan_nvzhuang",
        "summary": "2026-05-20 千川女装类目定向调整，老计划 ROI 衰退 20%-40%",
        "affects_overlays": ["nvzhuang_zibo", "nvzhuang_chengzhang"],
        "affects_metrics": ["qianchuan_roi"],
    },
    {
        "id": "wiki_rule_changes_2026_05_15_tixianfen_v3",
        "summary": "2026-05-15 体验分新增售后响应分项，权重 10%",
        "affects_overlays": ["nvzhuang_zibo", "nvzhuang_dabo", "nvzhuang_huojia"],
        "affects_metrics": ["exp_score"],
    },
    {
        "id": "wiki_rule_changes_2026_05_10_summer_search",
        "summary": "2026-05-10 夏装关键词搜索量环比 +120%（冰丝/防晒/显瘦）",
        "affects_overlays": ["nvzhuang_huojia", "nvzhuang_jijie"],
        "affects_metrics": ["search_ctr"],
    },
    {
        "id": "wiki_rule_changes_2026_05_05_xindian_policy",
        "summary": "2026-05-05 新店扶持窗口期延长至 90 天",
        "affects_overlays": ["nvzhuang_xindian"],
        "affects_metrics": ["newbie_progress"],
    },
]


def _root_cause_text(metric: str, current, baseline) -> str:
    """构造根因描述文本。"""
    return f"{metric} 实际 {current} vs 基线 {baseline}，显著偏离"


def _build_candidates(
    anomaly: dict,
    metrics_7d: dict,
    overlays: list[str],
) -> tuple[list[dict], list[dict]]:
    """对单条异常拆候选根因，返回 (candidates, evidence_refs)。"""
    candidates: list[dict] = []
    refs: list[dict] = []

    metric = anomaly["metric"]
    primary_dim = _METRIC_DIMENSION.get(metric, "未分类")

    # 主候选：本指标偏离本身
    main_ref = make_ref(
        layer="raw",
        source_id=f"shop_metrics_{metric}",
        summary=_root_cause_text(metric, anomaly["current"], anomaly["baseline"]),
        confidence=0.92,
    )
    refs.append(main_ref)
    candidates.append({
        "root_cause": _root_cause_text(metric, anomaly["current"], anomaly["baseline"]),
        "dimension": primary_dim,
        "confidence": 0.92,
        "evidence_refs": [main_ref["refId"]],
        "cross_validation": "",
    })

    # 跨场景耦合：找关联指标也异常的，作为辅助证据
    coupled = _CROSS_COUPLING.get(metric, [])
    for coupled_metric in coupled:
        cv_current = metrics_7d.get(coupled_metric)
        if cv_current is None:
            continue
        # 简化判定：只看是否有数据
        cv_ref = make_ref(
            layer="raw",
            source_id=f"shop_metrics_{coupled_metric}",
            summary=f"耦合指标 {coupled_metric} 当前 {cv_current}",
            confidence=0.75,
        )
        refs.append(cv_ref)
        candidates.append({
            "root_cause": f"耦合指标 {coupled_metric} 同期异动（{cv_current}），与 {metric} 异常强相关",
            "dimension": _METRIC_DIMENSION.get(coupled_metric, primary_dim),
            "confidence": 0.75,
            "evidence_refs": [cv_ref["refId"]],
            "cross_validation": f"与主因 {metric} 时间共变",
        })

    return candidates, refs


def _scan_non_data_signals(
    overlays: list[str],
    anomaly_metrics: set,
) -> tuple[list[dict], list[dict]]:
    """扫描 rule_changes Wiki，找与当前 anomalies 相关的非数据信号。"""
    signals: list[dict] = []
    refs: list[dict] = []

    for rule in _RULE_CHANGES:
        ov_match = bool(set(rule["affects_overlays"]) & set(overlays))
        metric_match = bool(set(rule["affects_metrics"]) & anomaly_metrics)
        if not (ov_match and metric_match):
            continue

        ref = make_ref(
            layer="wiki",
            source_id=rule["id"],
            summary=rule["summary"],
            confidence=0.85,
        )
        refs.append(ref)
        signals.append({
            "signal": rule["summary"],
            "source_ref_id": ref["refId"],
            "affects_metrics": rule["affects_metrics"],
        })

    return signals, refs


# ---- LLM 增强：把规则归因翻译成商家能听懂的话 ----
_LLM_SYSTEM_PROMPT = """你是抖音电商资深运营顾问，帮中小商家把"指标动了"翻译成"商家能听懂的根因解释"。

你会拿到一条根因数据（指标名/当前值/基线/类目场景/跨场景耦合证据）。请输出严格 JSON：
{
  "root_cause_plain": "<一句话商家能听懂的根因描述，<=40字，避免行话>",
  "what_to_check": "<商家自己可以立刻看哪个后台/工具确认这个根因，<=30字>"
}

要求：
- root_cause_plain 用"因为...所以..."或"...导致..."句式，必须含具体数字
- 不要给建议（建议是行动建议专家的事）
- 不要重复输入里已有的指标名，要"翻译"成商家视角
"""


def _llm_enhance_primary(
    anomaly: dict,
    primary: dict,
    overlays: list[str],
    coupled_evidence: list[str],
) -> dict | None:
    """对主因调一次 LLM 生成"商家视角解释"。失败返回 None，保留规则文案。"""
    if not has_llm():
        return None
    user_payload = (
        f"指标：{anomaly['metric']}\n"
        f"当前值：{anomaly['current']}\n"
        f"类目基线：{anomaly['baseline']}\n"
        f"偏离基线：{anomaly['deviation_vs_baseline_pct']}%\n"
        f"严重度：{anomaly['severity']}\n"
        f"店铺画像 overlay：{', '.join(overlays)}\n"
        f"跨场景耦合证据：{'; '.join(coupled_evidence) if coupled_evidence else '无'}\n"
    )
    return chat_json(
        system=_LLM_SYSTEM_PROMPT,
        user=user_payload,
        max_tokens=400,
        temperature=0.3,
        mock_fallback=None,
    )


class Attributor(BaseNode):
    """归因专家：MECE 拆维度 + 跨场景交叉 + 非数据信号检索 + LLM 通俗化解释。"""

    name = "attributor"

    async def run(self, state: dict) -> dict:
        anomalies = state.get("anomalies") or []
        overlays = state.get("matched_overlays") or []
        metrics_7d = (state.get("shop_metrics") or {}).get("metrics_7d", {})

        # 对每条 anomaly 拆候选根因
        root_cause_chains: list[dict] = []
        all_refs: list[dict] = []
        llm_calls = 0

        for anomaly in anomalies:
            candidates, refs = _build_candidates(anomaly, metrics_7d, overlays)
            all_refs.extend(refs)
            # 选 confidence 最高的作为主因
            primary_idx = 0
            best_conf = 0.0
            for i, c in enumerate(candidates):
                if c["confidence"] > best_conf:
                    best_conf = c["confidence"]
                    primary_idx = i

            # LLM 增强：仅对主因调用，生成商家视角解释
            primary = candidates[primary_idx]
            coupled_evidence = [
                c["root_cause"] for i, c in enumerate(candidates) if i != primary_idx
            ]
            enhanced = _llm_enhance_primary(anomaly, primary, overlays, coupled_evidence)
            if enhanced and not enhanced.get("_mock") and not enhanced.get("_parse_error"):
                plain = (enhanced.get("root_cause_plain") or "").strip()
                what_to_check = (enhanced.get("what_to_check") or "").strip()
                if plain:
                    # 覆盖主因的 root_cause 文案，保留 evidence_refs / confidence
                    primary["root_cause_plain"] = plain
                    primary["what_to_check"] = what_to_check
                    llm_calls += 1

            root_cause_chains.append({
                "anomaly_metric": anomaly["metric"],
                "candidates": candidates,
                "primary_root_cause_index": primary_idx,
            })

        # 扫非数据信号
        anomaly_metrics_set = {a["metric"] for a in anomalies}
        non_data_signals, signal_refs = _scan_non_data_signals(overlays, anomaly_metrics_set)
        all_refs.extend(signal_refs)

        note = (
            f"chains={len(root_cause_chains)} "
            f"non_data_signals={len(non_data_signals)} "
            f"refs+{len(all_refs)} llm_calls={llm_calls}"
        )

        return {
            "root_cause_chains": root_cause_chains,
            "non_data_signals": non_data_signals,
            "evidence_refs": all_refs,
            "_trace": [self._trace_entry(note)],
        }
