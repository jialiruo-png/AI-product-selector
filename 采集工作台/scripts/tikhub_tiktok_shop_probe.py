#!/usr/bin/env python3
"""TikHub TikTok Shop 端点探测脚本（仅探接口、摸字段，小批量）。

为什么没有 douyin 脚本：抖音 (`/douyin/`) 命名空间无关键词→商品搜索，也无独立商品详情，
电商端点全要求已持有 product_id+shop_id 或 room_id+author_id，无法冷启动选品。
选品入口完全走 TikTok Shop (`/tiktok/shop/web/`)。详见 docs/tikhub_接入说明.md 第二节。

用法：
    python3 采集工作台/scripts/tikhub_tiktok_shop_probe.py "labubu"
    python3 采集工作台/scripts/tikhub_tiktok_shop_probe.py "labubu" --dump   # 原始 JSON 落 /tmp
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from _tikhub_client import TikHubClient, TikHubError, dig, load_env

ROOT = Path(__file__).resolve().parents[2]


def probe(keyword: str, region: str, dump: bool) -> None:
    load_env(ROOT)
    cli = TikHubClient()
    info = cli.ping()
    print(f"账户 code: {info.get('code')} | 名称: {dig(info, 'api_key_data.api_key_name')}")

    print(f"\n{'='*70}\nTikTok Shop 选品漏斗  keyword={keyword!r} region={region}\n{'='*70}")

    print("\n[1] fetch_search_products_list（关键词→商品列表，含价格/销量/评分）")
    s = cli.call("/api/v1/tiktok/shop/web/fetch_search_products_list",
                 {"search_word": keyword, "offset": 0, "region": region})
    if dump:
        Path("/tmp/tt_probe_search.json").write_text(json.dumps(s, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/tt_probe_search.json")
    products = dig(s, "data.data.data.products") or []
    print(f"    code={s.get('code')} 本页商品 {len(products)} 条")
    for p in products[:3]:
        print(f"      · pid={p.get('product_id')} "
              f"价${dig(p, 'product_price_info.sale_price_decimal')} "
              f"销{dig(p, 'sold_info.sold_count')} "
              f"评{dig(p, 'rate_info.score')}({dig(p, 'rate_info.review_count')}) "
              f"| {(p.get('title') or '')[:30]}")
    if not products:
        print("    （无商品，后续探测跳过）")
        return

    def _rc(p: dict) -> int:
        try:
            return int(dig(p, "rate_info.review_count") or 0)
        except Exception:  # noqa: BLE001
            return 0
    top = max(products, key=_rc)
    pid = top["product_id"]
    print(f"\n    选评论最多的商品做评论探测: pid={pid} review_count={_rc(top)}")

    time.sleep(0.5)
    print("\n[2] fetch_product_reviews_v2（评论→情感/痛点；page_start 从 1 起）")
    rev = cli.call("/api/v1/tiktok/shop/web/fetch_product_reviews_v2",
                   {"product_id": pid, "page_start": 1, "region": region})
    if dump:
        Path("/tmp/tt_probe_reviews.json").write_text(json.dumps(rev, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/tt_probe_reviews.json")
    rdata = dig(rev, "data.data.data") or {}
    reviews = rdata.get("product_reviews", [])
    withtext = sum(1 for r in reviews if (r.get("review_text") or "").strip())
    print(f"    total={rdata.get('total_reviews')} has_more={rdata.get('has_more')} "
          f"本页 {len(reviews)} 条（{withtext} 条带文字）")
    for r in reviews[:3]:
        print(f"      ★{r.get('review_rating')} {(r.get('review_text') or '（无文字）')[:40]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword", nargs="?", default="phone case")
    ap.add_argument("--region", default="US")
    ap.add_argument("--dump", action="store_true", help="原始 JSON 落 /tmp 供细看字段")
    args = ap.parse_args()
    try:
        probe(args.keyword, args.region, args.dump)
    except TikHubError as exc:
        print(f"[error] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
