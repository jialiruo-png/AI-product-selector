"""商机洞察子图 (business-opportunity insight subgraph) 状态定义。

Ported from `reference/company-research-agent/backend/classes/state.py`.

核心模式（来自 company-research-agent）:
    - "raw field + curated_ field" 成对出现：采集节点写 raw，Curator 写 curated_。
    - briefings/report 为下游汇总产物。
    - messages/_trace 用于可观测性。

本子图把 company-research 的 financial/news/industry/company 四路
映射为商机洞察的 social/price/hot/competitor 四路。
"""
from __future__ import annotations

from typing import Any, TypedDict


class InsightState(TypedDict, total=False):
    """商机洞察子图全局状态。total=False —— 所有字段可选，节点增量合并。"""

    # ---- inputs（入参）----
    keyword: str          # 用户输入的核心词，如 "口红"
    category: str         # 类目，如 "美妆"
    region: str           # 地区/市场，如 "CN"
    topn: int             # 取 TopN 商品

    # ---- 精准词（KeywordPlanner 产出，贯穿所有 analyzer 的全局状态）----
    keywords: list[str]

    # ---- raw + curated 成对字段（四路分析）----
    social_data: dict[str, Any]
    curated_social_data: dict[str, Any]
    price_data: dict[str, Any]
    curated_price_data: dict[str, Any]
    hot_data: dict[str, Any]
    curated_hot_data: dict[str, Any]
    competitor_data: dict[str, Any]
    curated_competitor_data: dict[str, Any]

    # ---- 共享商品池（PriceAnalyzer 打分后写入，下游复用）----
    products: list

    # ---- 证据引用（形如 KnowledgeEvidenceRef）----
    evidence_refs: list  # list[dict]: {refId,layer,sourceId,quoteOrSummary,confidence,status}

    # ---- 汇总产物 ----
    briefings: dict[str, str]
    report: str

    # ---- 可观测性 ----
    messages: list
    _trace: list  # list[dict]: {node, ms, note}


class DiagnosisState(TypedDict, total=False):
    """在运营商家诊断子图状态（贾丽婼 - Day 2 加）。

    与 InsightState 完全独立——主子图（甘华梁冷启动选品）状态不动。
    在 Hub 路由按 diagnosis 意图分发时，run_diagnosis 用这套 state。

    核心字段：
        - shop_profile：店铺画像（CLI 入参或 mock JSON 加载）
        - shop_metrics：经营数据快照（7d / prev_7d / 30d）
        - anomalies：经营诊断专家产出的异常清单
        - matched_overlays：命中的女装 overlay 列表
        - root_cause_chains：归因专家产出的根因链
        - actions：行动建议专家产出的动作清单
        - report：composer 汇总产出的 markdown 报告
    """

    # ---- inputs（入参）----
    shop_id: str           # 店铺 ID，如 "mock_shop_001"
    user_query: str        # 用户原始问题，如 "我店铺最近 GMV 跌了"
    window: str            # 诊断窗口，"7d" / "30d"

    # ---- 店铺画像 + 经营数据（Checker 读 mock JSON 后写入）----
    shop_profile: dict[str, Any]
    shop_metrics: dict[str, Any]      # {metrics_7d, metrics_prev_7d, metrics_30d}

    # ---- Checker（经营诊断专家）产出 ----
    diagnosis_summary: str             # 一句话核心问题
    anomalies: list[dict[str, Any]]    # 异常清单（指标/偏离/严重度/证据）
    matched_overlays: list[str]        # 命中的女装 overlay 名（如 ["nvzhuang_zibo"]）
    data_completeness: float           # 0-1 数据完整度

    # ---- Attributor（归因专家）产出 ----
    root_cause_chains: list[dict[str, Any]]   # 每条异常的根因链
    non_data_signals: list[dict[str, Any]]    # 规则变动等非数据信号

    # ---- Advisor（行动建议专家）产出 ----
    actions: list[dict[str, Any]]             # 可执行动作清单（必须挂资源）
    top_n_for_user: list[int]                 # 推送给用户的 TOP N 动作索引

    # ---- 共享字段（与 InsightState 同名同形）----
    evidence_refs: list                # 与 InsightState 一致的证据引用列表
    report: str                        # composer 汇总 markdown
    messages: list
    _trace: list


# 证据引用计数器（仅用于生成递增 refId，进程内单调）
_REF_COUNTER = {"n": 0}


def new_evidence_ref(
    layer: str,
    source_id: Any,
    summary: str,
    confidence: float = 0.8,
) -> dict:
    """构造一个 KnowledgeEvidenceRef 形状的证据引用 dict。

    Args:
        layer: 证据层，如 "raw" / "social" / "price" / "hot" / "competitor".
        source_id: 来源 ID（如 product_id），允许 None。
        summary: 引文或摘要。
        confidence: 置信度 0~1。

    Returns:
        {refId, layer, sourceId, quoteOrSummary, confidence, status}
    """
    _REF_COUNTER["n"] += 1
    return {
        "refId": f"ref-{_REF_COUNTER['n']}",
        "layer": layer,
        "sourceId": source_id,
        "quoteOrSummary": summary,
        "confidence": confidence,
        "status": "active",
    }
