"""工具协议层（PRD 5.1）对外入口。

import 本包即触发 tikhub_tools 内所有工具的自动注册，
之后可通过 TOOL_REGISTRY 按 name 取用，或直接导入工具实例。
"""
from __future__ import annotations

from .base import BaseTool, TOOL_REGISTRY, register
from .tikhub_tools import (
    SearchProductsTool,
    RankProductsTool,
    FetchReviewsTool,
    AnalyzeReviewsTool,
    SnapshotWriteTool,
    TrendQueryTool,
    search_products,
    rank_products,
    fetch_reviews,
    analyze_reviews,
    snapshot_write,
    trend_query,
)

__all__ = [
    "BaseTool",
    "TOOL_REGISTRY",
    "register",
    # 类
    "SearchProductsTool",
    "RankProductsTool",
    "FetchReviewsTool",
    "AnalyzeReviewsTool",
    "SnapshotWriteTool",
    "TrendQueryTool",
    # 实例
    "search_products",
    "rank_products",
    "fetch_reviews",
    "analyze_reviews",
    "snapshot_write",
    "trend_query",
]
