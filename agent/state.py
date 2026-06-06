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

    # ---- 落库（B3）----
    db_path: str          # sqlite 路径；None 时落到 db.DEFAULT_DB
    run_id: int           # Persist 节点新建 run 后透传，便于趋势复盘
    review_raw: list      # [{product_id, reviews, analysis}]，CompetitorAnalyzer 收集供落库

    # ---- 证据引用（形如 KnowledgeEvidenceRef）----
    evidence_refs: list  # list[dict]: {refId,layer,sourceId,quoteOrSummary,confidence,status}

    # ---- 汇总产物 ----
    briefings: dict[str, str]
    report: str

    # ---- 可观测性 ----
    messages: list
    _trace: list  # list[dict]: {node, ms, note}


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
