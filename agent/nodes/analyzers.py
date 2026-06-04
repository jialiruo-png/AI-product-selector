"""四路分析节点（可并行）：
    - SocialAnalyzer    (Step2 社媒人群)
    - PriceAnalyzer     (Step3 价格带)
    - HotItemAnalyzer   (Step4 爆款 + 主图)
    - CompetitorAnalyzer(Step5 竞品 + 口碑)

每个节点写自己的 raw_data 字段并附带 evidence_refs。
对 mock / 空数据健壮：工具缺失或返回 ok=False 时降级，不抛异常。
"""
from __future__ import annotations

from typing import Any

from agent.state import new_evidence_ref

from .base import BaseNode, get_tool


def _orig(p: dict) -> dict:
    """取商品的原始字段视图。

    rank_products 会把原始商品重塑（price/sold 归零、嵌套到 "raw"，并把
    seller_info/brand_info 拍平为 shop/brand）。为让下游统一读到真实值，
    优先返回其 "raw"，否则返回本身。
    """
    if isinstance(p, dict) and isinstance(p.get("raw"), dict):
        return p["raw"]
    return p if isinstance(p, dict) else {}


def _pick(p: dict, *keys, default=None):
    """从商品多层视图里取第一个非空值。

    取值优先级：rank 后的顶层扁平值（如真实数据的 price/sold/rating，rank 已算好）
    → raw 视图里的同名值（mock 数据扁平值在此）。两级覆盖 mock 与真实两种形态。
    """
    if not isinstance(p, dict):
        return default
    for k in keys:
        v = p.get(k)
        if v not in (None, "", 0, 0.0):
            return v
    o = _orig(p)
    if o is not p:
        for k in keys:
            v = o.get(k)
            if v not in (None, "", 0, 0.0):
                return v
    return default


def _sold_nested(p: dict):
    """真实数据销量在 raw.sold_info.sold_count，做兜底取值。"""
    si = _orig(p).get("sold_info") or {}
    return si.get("sold_count") if isinstance(si, dict) else None


def _rating_nested(p: dict):
    """真实数据评分在 raw.rate_info.score，做兜底取值。"""
    ri = _orig(p).get("rate_info") or {}
    return ri.get("score") if isinstance(ri, dict) else None


# --------------------------------------------------------------------------- #
# Step2 社媒人群
# --------------------------------------------------------------------------- #
class SocialAnalyzer(BaseNode):
    """社媒人群洞察。可并行。"""

    name = "social_analyzer"

    async def run(self, state: dict) -> dict:
        # TODO: wire real LLM / 社媒采集工具。当前 MOCK。
        social_data = {
            "personas": [
                {"name": "学生党", "need": "平价"},
                {"name": "精致妈妈", "need": "安全成分"},
            ],
            "koc_kol": [],
        }
        refs = [new_evidence_ref(
            layer="social",
            source_id=None,
            summary="社媒人群画像（mock）：学生党/精致妈妈",
            confidence=0.5,
        )]
        return {
            "social_data": social_data,
            "evidence_refs": self._merge_refs(state, refs),
            "_trace": [self._trace_entry(f"产出 {len(social_data['personas'])} 个人群")],
        }


# --------------------------------------------------------------------------- #
# Step3 价格带
# --------------------------------------------------------------------------- #
def _safe_price(p: dict) -> float:
    # 顶层 price（rank 真实数据已算好）优先，回退 raw；
    # 再回退真实嵌套字段 product_price_info.sale_price_decimal。
    val = _pick(p, "price")
    if val is None:
        ppi = _orig(p).get("product_price_info") or {}
        val = ppi.get("sale_price_decimal") or ppi.get("single_product_price_decimal")
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _compute_bands(products: list[dict]) -> tuple[list[dict], dict]:
    """按价格分箱，返回 (bands, gap_band)。

    bands: [{range:[lo,hi], count, share}], gap_band: 商品数最少的非空/空档位。
    """
    prices = [_safe_price(p) for p in products if _safe_price(p) > 0]
    if not prices:
        return [], {}

    lo, hi = min(prices), max(prices)
    if hi <= lo:
        # 全同价，单一档
        return ([{"range": [lo, hi], "count": len(prices), "share": 1.0}],
                {})

    n_bins = 5
    width = (hi - lo) / n_bins
    bands: list[dict] = []
    for i in range(n_bins):
        b_lo = lo + i * width
        b_hi = lo + (i + 1) * width if i < n_bins - 1 else hi
        cnt = sum(1 for pr in prices if b_lo <= pr <= b_hi) if i == 0 \
            else sum(1 for pr in prices if b_lo < pr <= b_hi)
        bands.append({
            "range": [round(b_lo, 2), round(b_hi, 2)],
            "count": cnt,
            "share": round(cnt / len(prices), 3),
        })
    # gap = 供给最少的价格带（机会带）
    gap = min(bands, key=lambda b: b["count"])
    return bands, gap


class PriceAnalyzer(BaseNode):
    """价格带分布 + 机会带。会写入共享 products（打分后）。"""

    name = "price_analyzer"

    async def run(self, state: dict) -> dict:
        keyword = state.get("keyword") or ""
        region = state.get("region") or "CN"
        topn = int(state.get("topn") or 20)

        scored: list[dict] = []
        search = get_tool("search_products")
        ranker = get_tool("rank_products")
        if search is not None:
            res = search.run(keyword=keyword, region=region, limit=topn)
            products = res.get("products", []) if isinstance(res, dict) and res.get("ok") else []
            if products and ranker is not None:
                ranked = ranker.run(products=products, source=state.get("source"))
                scored = ranked.get("scored", []) if isinstance(ranked, dict) and ranked.get("ok") else products
            else:
                scored = products

        bands, gap = _compute_bands(scored)

        refs = []
        for p in scored[:topn]:
            pid = p.get("product_id")
            if pid is None:
                continue
            refs.append(new_evidence_ref(
                layer="raw",
                source_id=pid,
                summary=f"商品 {p.get('title', '')[:30]} 价格 {_safe_price(p)}",
                confidence=0.8,
            ))

        price_data = {"bands": bands, "gap_band": gap}
        note = f"商品 {len(scored)} 件，价格带 {len(bands)} 档"
        return {
            "price_data": price_data,
            "products": scored,
            "evidence_refs": self._merge_refs(state, refs),
            "_trace": [self._trace_entry(note)],
        }


# --------------------------------------------------------------------------- #
# Step4 爆款 + 主图
# --------------------------------------------------------------------------- #
def _first_image(p: dict) -> str:
    # image 是嵌套结构，真实数据在 raw.image.url_list
    img = _orig(p).get("image") or p.get("image") or {}
    url_list = img.get("url_list") if isinstance(img, dict) else None
    if url_list:
        return url_list[0]
    return ""


class HotItemAnalyzer(BaseNode):
    """爆款元素：取 Top3 商品的主图 + 价格/销量。"""

    name = "hot_item_analyzer"

    async def run(self, state: dict) -> dict:
        products = list(state.get("products") or [])
        # 若共享池为空，自行采集
        if not products:
            search = get_tool("search_products")
            if search is not None:
                res = search.run(
                    keyword=state.get("keyword") or "",
                    region=state.get("region") or "CN",
                    limit=int(state.get("topn") or 20),
                )
                if isinstance(res, dict) and res.get("ok"):
                    products = res.get("products", [])

        hot_items: list[dict] = []
        refs = []
        for p in products[:3]:
            item = {
                "product_id": _pick(p, "product_id"),
                "title": _pick(p, "title"),
                "image": _first_image(p),
                "price": _safe_price(p),
                "sold": _pick(p, "sold", default=_sold_nested(p)),
                "elements": ["颜色", "材质"],  # TODO: wire real 主图视觉解析
            }
            hot_items.append(item)
            if item["product_id"] is not None:
                refs.append(new_evidence_ref(
                    layer="hot",
                    source_id=item["product_id"],
                    summary=f"爆款 {str(item['title'])[:30]} 销量 {item['sold']}",
                    confidence=0.7,
                ))

        return {
            "hot_data": {"hot_items": hot_items},
            "evidence_refs": self._merge_refs(state, refs),
            "_trace": [self._trace_entry(f"产出 {len(hot_items)} 个爆款")],
        }


# --------------------------------------------------------------------------- #
# Step5 竞品 + 口碑
# --------------------------------------------------------------------------- #
class CompetitorAnalyzer(BaseNode):
    """竞品表 + 评价词云（pain_points / highlights）。"""

    name = "competitor_analyzer"

    async def run(self, state: dict) -> dict:
        products = list(state.get("products") or [])
        region = state.get("region") or "CN"

        # 并行运行时 PriceAnalyzer 可能尚未写入共享 products，自取兜底
        if not products:
            search = get_tool("search_products")
            ranker = get_tool("rank_products")
            kw = (state.get("keywords") or [state.get("keyword")])[0]
            if search is not None and kw:
                res = search.run(keyword=kw, source=state.get("source"),
                                 region=region, limit=state.get("topn") or 5)
                if isinstance(res, dict) and res.get("ok"):
                    products = res.get("products", [])
                    if products and ranker is not None:
                        ranked = ranker.run(products=products, source=state.get("source"))
                        if isinstance(ranked, dict) and ranked.get("ok"):
                            products = ranked.get("scored", products)

        competitors: list[dict] = []
        for p in products[:5]:
            o = _orig(p)
            seller = o.get("seller_info") or {}
            brand = o.get("brand_info") or {}
            competitors.append({
                "product_id": _pick(p, "product_id"),
                "title": _pick(p, "title"),
                # 兼容 rank 拍平后的 shop/brand
                "shop_name": p.get("shop") or seller.get("shop_name"),
                "brand_name": p.get("brand") or brand.get("brand_name"),
                "price": _safe_price(p),
                "sold": _pick(p, "sold", default=_sold_nested(p)),
                "rating": _pick(p, "rating", default=_rating_nested(p)),
                "review_count": _pick(p, "review_count"),
            })

        # 对 Top1~2 拉评论并做情感/痛点分析
        fetch = get_tool("fetch_reviews")
        analyze = get_tool("analyze_reviews")
        review_insights: dict[str, Any] = {
            "sentiment": {},
            "pain_points": [],
            "highlights": [],
            "word_cloud": [],
        }
        refs = []
        if fetch is not None and analyze is not None:
            for p in products[:2]:
                pid = p.get("product_id")
                if pid is None:
                    continue
                rv = fetch.run(product_id=pid, region=region, source=state.get("source"))
                reviews = rv.get("reviews", []) if isinstance(rv, dict) and rv.get("ok") else []
                if not reviews:
                    continue
                an = analyze.run(reviews=reviews)
                if not (isinstance(an, dict) and an.get("ok")):
                    continue
                # 合并情感（以最后一次为准；MVP 简单聚合）
                review_insights["sentiment"] = an.get("sentiment", {})
                pps = an.get("pain_points", []) or []
                hls = an.get("highlights", []) or []
                review_insights["pain_points"].extend(pps)
                review_insights["highlights"].extend(hls)
                for pp in pps:
                    label = pp.get("label") if isinstance(pp, dict) else str(pp)
                    refs.append(new_evidence_ref(
                        layer="competitor",
                        source_id=pid,
                        summary=f"痛点：{label}",
                        confidence=0.75,
                    ))

        # 评价词云：痛点 label + highlights
        word_cloud = []
        for pp in review_insights["pain_points"]:
            label = pp.get("label") if isinstance(pp, dict) else str(pp)
            freq = pp.get("freq", 1) if isinstance(pp, dict) else 1
            word_cloud.append({"word": label, "weight": freq, "type": "pain"})
        for hl in review_insights["highlights"]:
            word_cloud.append({"word": str(hl), "weight": 1, "type": "highlight"})
        review_insights["word_cloud"] = word_cloud

        competitor_data = {
            "competitors": competitors,
            "review_insights": review_insights,
        }
        note = f"竞品 {len(competitors)} 个，词云 {len(word_cloud)} 词"
        return {
            "competitor_data": competitor_data,
            "evidence_refs": self._merge_refs(state, refs),
            "_trace": [self._trace_entry(note)],
        }
