"""具体工具实现（PRD 5.1 工具协议层）。

每个工具都支持 mock 开关：
    - 默认从环境变量 AGENT_MOCK 读取（"1"/"true"/"yes"/"on" => True）。
    - mock=True 时返回确定性假数据，绝不触网 / 不调 LLM，整条 graph 可离线跑通。

依赖的采集脚本目录名含中文（采集工作台/scripts），用 sys.path.insert 接入；
其中 _tikhub_client / analyze 这类"需要 key"的模块在 _run 内部惰性 import，
保证 mock 模式下永远不需要任何 API key。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# 采集脚本目录（非 ASCII 名）入 sys.path —— score / db 纯本地，可在模块顶层 import
_SCRIPTS = Path(__file__).resolve().parents[2] / "采集工作台" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import score  # noqa: E402  纯函数，无网络
import db      # noqa: E402  纯 sqlite

from .base import BaseTool, register  # noqa: E402


def _mock_default() -> bool:
    return os.environ.get("AGENT_MOCK", "").strip().lower() in {"1", "true", "yes", "on"}


def _load_client():
    """惰性创建 TikHubClient；同时加载项目根 .env。失败抛异常由 run() 兜底。"""
    import _tikhub_client as tk  # 需要 TIKHUB_API_KEY
    root = _SCRIPTS.parents[1]  # 项目根
    tk.load_env(root)
    return tk


# ============================ search_products ============================
class SearchProductsTool(BaseTool):
    name = "search_products"
    description = "按关键词搜索电商平台（默认 TikTok Shop）商品，返回原始商品列表。"
    input_schema = {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键词"},
            "source": {"type": "string", "default": "tiktok", "description": "平台来源"},
            "region": {"type": "string", "default": "US", "description": "地区代码"},
            "limit": {"type": "integer", "default": 20, "description": "返回条数上限"},
        },
        "required": ["keyword"],
    }
    output_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "products": {"type": "array"}},
    }

    def __init__(self, mock: bool | None = None):
        self.mock = _mock_default() if mock is None else mock

    def _run(self, *, keyword: str, source: str = "tiktok",
             region: str = "US", limit: int = 20) -> dict:
        if self.mock:
            return {"ok": True, "products": [
                {
                    "product_id": f"mock-{i}",
                    "title": f"{keyword} 商品{i}",
                    "price": 9.9 + i,
                    "sold": 1000 - i * 50,
                    "rating": 4.5,
                    "review_count": 20 + i,
                    "image": {"url_list": [f"https://img/mock{i}.jpg"]},
                    "seller_info": {"shop_name": f"店铺{i}"},
                    "brand_info": {"brand_name": f"品牌{i % 3}"},
                }
                for i in range(limit)
            ]}

        tk = _load_client()
        cli = tk.TikHubClient()
        s = cli.call(
            "/api/v1/tiktok/shop/web/fetch_search_products_list",
            {"search_word": keyword, "offset": 0, "region": region},
        )
        products = tk.dig(s, "data.data.data.products", []) or []
        return {"ok": True, "products": products[:limit]}


# ============================ rank_products ============================
class RankProductsTool(BaseTool):
    name = "rank_products"
    description = "对商品列表打分排序（销量/评分/评论数/价格分位加权），返回降序 scored 列表。"
    input_schema = {
        "type": "object",
        "properties": {
            "products": {"type": "array", "description": "search_products 的原始商品列表"},
            "source": {"type": "string", "default": "tiktok"},
        },
        "required": ["products"],
    }
    output_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "scored": {"type": "array"}},
    }

    def __init__(self, mock: bool | None = None):
        # score.py 纯本地无网络，mock 与否都走真实打分
        self.mock = _mock_default() if mock is None else mock

    def _run(self, *, products: list, source: str = "tiktok") -> dict:
        scored = score.score_tiktok_products(products or [])
        return {"ok": True, "scored": scored}


# ============================ fetch_reviews ============================
class FetchReviewsTool(BaseTool):
    name = "fetch_reviews"
    description = "拉取指定商品的用户评论，返回 [{rating, text}] 形态的评论列表。"
    input_schema = {
        "type": "object",
        "properties": {
            "product_id": {"type": "string", "description": "商品 ID"},
            "region": {"type": "string", "default": "US"},
            "source": {"type": "string", "default": "tiktok"},
        },
        "required": ["product_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "reviews": {"type": "array"}},
    }

    def __init__(self, mock: bool | None = None):
        self.mock = _mock_default() if mock is None else mock

    def _run(self, *, product_id: str, region: str = "US",
             source: str = "tiktok") -> dict:
        if self.mock:
            return {"ok": True, "reviews": [
                {"rating": 5, "text": "很喜欢 质量好"},
                {"rating": 2, "text": "物流太慢 包装破损"},
                {"rating": 4, "text": "性价比不错"},
            ]}

        tk = _load_client()
        cli = tk.TikHubClient()
        # 注意：page_start 从 1 开始（0 返回空）
        s = cli.call(
            "/api/v1/tiktok/shop/web/fetch_product_reviews_v2",
            {"product_id": product_id, "page_start": 1, "region": region},
        )
        raw = tk.dig(s, "data.data.data.product_reviews", []) or []
        reviews = []
        for r in raw:
            if not isinstance(r, dict):
                continue
            reviews.append({
                "rating": r.get("rating") or r.get("review_rating") or r.get("star"),
                "text": (r.get("review_text") or r.get("text")
                         or r.get("content") or "").strip(),
                "review_id": r.get("review_id") or r.get("id"),
                "raw": r,
            })
        return {"ok": True, "reviews": reviews}


# ============================ analyze_reviews ============================
class AnalyzeReviewsTool(BaseTool):
    name = "analyze_reviews"
    description = "对评论做情感与痛点分析，返回 {sentiment, pain_points, highlights}。"
    input_schema = {
        "type": "object",
        "properties": {
            "reviews": {"type": "array", "description": "[{rating?, text}] 评论列表"},
        },
        "required": ["reviews"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "sentiment": {"type": "object"},
            "pain_points": {"type": "array"},
            "highlights": {"type": "array"},
        },
    }

    def __init__(self, mock: bool | None = None):
        self.mock = _mock_default() if mock is None else mock

    def _run(self, *, reviews: list) -> dict:
        if self.mock:
            return {
                "ok": True,
                "sentiment": {"positive": 2, "neutral": 0, "negative": 1},
                "pain_points": [
                    {"label": "物流慢", "freq": 1, "example": "物流太慢"},
                    {"label": "包装破损", "freq": 1, "example": "包装破损"},
                ],
                "highlights": [
                    {"label": "质量好", "freq": 1, "example": "质量好"},
                ],
            }

        _load_client()  # 确保项目根 .env 已加载（DASHSCOPE_API_KEY / LLM_*）
        import analyze  # 需要 DASHSCOPE_API_KEY；惰性 import
        # JSON 抽取类任务优先用非思考模型（LLM_MODEL_EXTRACT），避免 V4 思考模式
        # 撞 analyze.py 写死的 max_tokens=2048 导致输出被截断、痛点全空。
        extract_model = os.environ.get("LLM_MODEL_EXTRACT", "").strip() or None
        try:
            result = analyze.analyze_reviews(reviews or [], model=extract_model)
        except RuntimeError as exc:  # 缺 key / 缺包等运行期错误 -> 优雅降级
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "sentiment": result.get("sentiment", {}),
            "pain_points": result.get("pain_points", []),
            "highlights": result.get("highlights", []),
            "_stats": result.get("_stats", {}),
        }


# ============================ snapshot_write ============================
class SnapshotWriteTool(BaseTool):
    name = "snapshot_write"
    description = "把一次选品结果落库（runs + products [+ pain_points]），返回 run_id。"
    input_schema = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "default": "tiktok"},
            "keyword": {"type": "string"},
            "region": {"type": "string", "default": "US"},
            "scored": {"type": "array", "description": "rank_products 输出"},
            "analysis": {"type": "object", "description": "可选：analyze_reviews 输出"},
            "target_id": {"type": "string", "description": "analysis 关联的商品 ID"},
            "db_path": {"type": "string", "description": "可选：sqlite 路径"},
        },
        "required": ["keyword"],
    }
    output_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "run_id": {"type": "integer"}},
    }

    def __init__(self, mock: bool | None = None):
        self.mock = _mock_default() if mock is None else mock

    def _run(self, *, keyword: str, source: str = "tiktok", region: str = "US",
             scored: list | None = None, analysis: dict | None = None,
             target_id: str | None = None, db_path: str | None = None) -> dict:
        if self.mock:
            return {"ok": True, "run_id": 1}

        con = db.connect(db_path or db.DEFAULT_DB)
        run_id = db.start_run(con, source, keyword, region=region)
        if scored:
            db.save_tiktok_products(con, run_id, scored)
        if analysis and target_id:
            db.save_pain_points(con, run_id, source, target_id, analysis)
        return {"ok": True, "run_id": run_id}


# ============================ trend_query ============================
class TrendQueryTool(BaseTool):
    name = "trend_query"
    description = "查询同一商品在历次快照中的价格/销量/评分/评论数/得分趋势。"
    input_schema = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "default": "tiktok"},
            "source_id": {"type": "string", "description": "商品 ID"},
            "db_path": {"type": "string", "description": "可选：sqlite 路径"},
        },
        "required": ["source_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "history": {"type": "array"}},
    }

    def __init__(self, mock: bool | None = None):
        self.mock = _mock_default() if mock is None else mock

    def _run(self, *, source_id: str, source: str = "tiktok",
             db_path: str | None = None) -> dict:
        if self.mock:
            return {"ok": True, "history": []}

        con = db.connect(db_path or db.DEFAULT_DB)
        history = db.trend(con, source, source_id)
        return {"ok": True, "history": history}


# ---- 实例化并自动注册 ----
search_products = register(SearchProductsTool())
rank_products = register(RankProductsTool())
fetch_reviews = register(FetchReviewsTool())
analyze_reviews = register(AnalyzeReviewsTool())
snapshot_write = register(SnapshotWriteTool())
trend_query = register(TrendQueryTool())
