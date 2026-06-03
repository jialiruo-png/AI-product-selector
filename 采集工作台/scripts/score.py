"""选品打分：把 search 接口的返回排成 Top-N。

三个入口函数：
    score_tiktok_products(products, weights=None)
        输入 fetch_search_products_list 的 data.data.data.products[]
    score_xhs_products(cards, overviews=None, weights=None)
        输入 app_v2/search_products 的 goods 卡列表 + 可选评分概览
    score_xhs_notes(notes, weights=None)
        输入 web_v3/fetch_search_notes 的 noteCard 列表

权重写死在文件顶部，可通过 weights={...} 覆盖；总和不必=1。
每条字段先在本批次内做 min-max 归一化再加权，避免量纲差异。
"""
from __future__ import annotations

import math

TIKTOK_WEIGHTS = {
    "sold": 0.40,        # 销量（log 后归一）
    "rating": 0.25,      # 评分 4.0-5.0 → 0-1
    "reviews": 0.20,     # 评论数（log 后归一）
    "price_rank": 0.15,  # 价格分位，越便宜越高
}

XHS_PRODUCT_WEIGHTS = {
    "price_rank": 0.30,
    "discount": 0.30,
    "rating": 0.40,      # 来自 overview.avgScore；缺则用 0.5
}

XHS_NOTE_WEIGHTS = {
    "likes": 0.40,
    "collects": 0.30,
    "comments": 0.20,
    "shares": 0.10,
}


def _to_int(v) -> int:
    try:
        return int(str(v or 0).replace("+", "").replace(",", ""))
    except Exception:  # noqa: BLE001
        return 0


def _to_float(v) -> float:
    try:
        return float(v or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _rating_to_unit(score: float) -> float:
    """评分 4.0-5.0 映射到 0-1；<4 视为 0，>5 截断到 1。"""
    return max(0.0, min(1.0, (score - 4.0) / 1.0))


def score_tiktok_products(products: list[dict], weights: dict | None = None) -> list[dict]:
    w = {**TIKTOK_WEIGHTS, **(weights or {})}
    if not products:
        return []
    sold = [_to_int(((p.get("sold_info") or {}).get("sold_count"))) for p in products]
    rating_raw = [_to_float(((p.get("rate_info") or {}).get("score"))) for p in products]
    reviews = [_to_int(((p.get("rate_info") or {}).get("review_count"))) for p in products]
    price = [_to_float(((p.get("product_price_info") or {}).get("sale_price_decimal")))
             for p in products]

    sold_n = _minmax([math.log1p(x) for x in sold])
    rev_n = _minmax([math.log1p(x) for x in reviews])
    price_n = [1 - x for x in _minmax(price)]
    rating_n = [_rating_to_unit(x) for x in rating_raw]

    out = []
    for i, p in enumerate(products):
        s = (w["sold"] * sold_n[i]
             + w["rating"] * rating_n[i]
             + w["reviews"] * rev_n[i]
             + w["price_rank"] * price_n[i])
        out.append({
            "product_id": p.get("product_id"),
            "title": p.get("title"),
            "score": round(s, 4),
            "price": price[i],
            "sold": sold[i],
            "rating": rating_raw[i],
            "review_count": reviews[i],
            "shop": ((p.get("seller_info") or {}).get("shop_name")),
            "brand": ((p.get("brand_info") or {}).get("brand_name")),
            "raw": p,
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def score_xhs_products(cards: list[dict], overviews: dict | None = None,
                       weights: dict | None = None) -> list[dict]:
    w = {**XHS_PRODUCT_WEIGHTS, **(weights or {})}
    if not cards:
        return []
    overviews = overviews or {}
    prices, discounts, ratings = [], [], []
    for c in cards:
        ct = c.get("content", {})
        pi = ct.get("price_info", {})
        p = _to_float(pi.get("price"))
        op = _to_float(pi.get("origin_price")) or p
        prices.append(p)
        discounts.append(1 - p / op if op else 0)
        ov = overviews.get(str(ct.get("id")), {}) or {}
        avg = _to_float(ov.get("avgScore"))
        ratings.append(_rating_to_unit(avg) if avg else 0.5)

    price_n = [1 - x for x in _minmax(prices)]
    disc_n = _minmax(discounts)

    out = []
    for i, c in enumerate(cards):
        ct = c.get("content", {})
        s = (w["price_rank"] * price_n[i]
             + w["discount"] * disc_n[i]
             + w["rating"] * ratings[i])
        out.append({
            "sku_id": ct.get("id"),
            "title": ct.get("title"),
            "score": round(s, 4),
            "price": prices[i],
            "discount": round(discounts[i], 3),
            "rating": round(ratings[i], 3),
            "vendor": ((ct.get("vendor") or {}).get("vendor_name")),
            "raw": c,
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def score_xhs_notes(notes: list[dict], weights: dict | None = None) -> list[dict]:
    w = {**XHS_NOTE_WEIGHTS, **(weights or {})}
    if not notes:
        return []
    def _ii(it: dict, k: str) -> int:
        return _to_int(((it.get("noteCard") or {}).get("interactInfo") or {}).get(k))

    likes = [_ii(n, "likedCount") for n in notes]
    coll = [_ii(n, "collectedCount") for n in notes]
    cmt = [_ii(n, "commentCount") for n in notes]
    sh = [_ii(n, "sharedCount") for n in notes]

    likes_n = _minmax([math.log1p(x) for x in likes])
    coll_n = _minmax([math.log1p(x) for x in coll])
    cmt_n = _minmax([math.log1p(x) for x in cmt])
    sh_n = _minmax([math.log1p(x) for x in sh])

    out = []
    for i, n in enumerate(notes):
        nc = n.get("noteCard", {})
        s = (w["likes"] * likes_n[i] + w["collects"] * coll_n[i]
             + w["comments"] * cmt_n[i] + w["shares"] * sh_n[i])
        out.append({
            "note_id": n.get("id"),
            "xsec_token": n.get("xsecToken"),
            "title": nc.get("displayTitle"),
            "user": ((nc.get("user") or {}).get("nickname")),
            "score": round(s, 4),
            "likes": likes[i],
            "collects": coll[i],
            "comments": cmt[i],
            "shares": sh[i],
            "raw": n,
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out
