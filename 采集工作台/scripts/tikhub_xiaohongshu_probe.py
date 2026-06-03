#!/usr/bin/env python3
"""TikHub 小红书选品 + 内容端点探测脚本（仅探接口、摸字段，小批量）。

两条互补漏斗：
  ① 商品漏斗 (app_v2)：search_products → get_product_review_overview → get_product_reviews
  ② 笔记漏斗 (web_v3)：fetch_search_notes → fetch_note_detail → fetch_note_comments
详见 docs/tikhub_接入说明.md 第三节。

用法：
    python3 采集工作台/scripts/tikhub_xiaohongshu_probe.py "口红"
    python3 采集工作台/scripts/tikhub_xiaohongshu_probe.py "口红" --dump
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from _tikhub_client import TikHubClient, TikHubError, dig, load_env

ROOT = Path(__file__).resolve().parents[2]


def _to_int(v) -> int:
    try:
        return int(str(v or 0).replace("+", "").replace(",", ""))
    except Exception:  # noqa: BLE001
        return 0


def probe_products(cli: TikHubClient, keyword: str, dump: bool) -> None:
    print(f"\n{'='*70}\n[商品漏斗] 小红书选品打分  keyword={keyword!r}\n{'='*70}")

    print("\n[1] app_v2/search_products（关键词→商品列表，含价格/店铺/主图）")
    s = cli.call("/api/v1/xiaohongshu/app_v2/search_products", {"keyword": keyword, "page": 1})
    if dump:
        Path("/tmp/xhs_probe_products.json").write_text(json.dumps(s, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/xhs_probe_products.json")
    cards = dig(s, "data.data.module.data") or []
    goods = [c for c in cards if "goods" in (c.get("card_name") or "")]
    print(f"    code={s.get('code')} 商品卡 {len(goods)} 条 next_page={dig(s, 'data.data.next_page')}")
    for c in goods[:3]:
        ct = c.get("content", {})
        pi = ct.get("price_info", {})
        print(f"      · sku={ct.get('id')} 价¥{pi.get('price')}(原¥{pi.get('origin_price')}) "
              f"店={(dig(ct, 'vendor.vendor_name') or '')[:12]} | {(ct.get('title') or '')[:30]}")
    if not goods:
        print("    （无商品卡，跳过 overview/reviews）")
        return
    sku = goods[0]["content"]["id"]

    time.sleep(0.5)
    print("\n[2] app_v2/get_product_review_overview（评分分布/差评率）")
    ov = cli.call("/api/v1/xiaohongshu/app_v2/get_product_review_overview", {"sku_id": sku})
    if dump:
        Path("/tmp/xhs_probe_review_overview.json").write_text(json.dumps(ov, ensure_ascii=False, indent=2))
    od = ov.get("data") or {}
    print(f"    sku={sku} 评分={od.get('avgScore')!r} 评价数={od.get('total')} "
          f"销量={od.get('purchaseHistoryCount')} 分布={od.get('scoreToCnt')}")

    time.sleep(0.5)
    print("\n[3] app_v2/get_product_reviews（评论→情感/痛点；page 从 0 起）")
    rv = cli.call("/api/v1/xiaohongshu/app_v2/get_product_reviews", {"sku_id": sku, "page": 0})
    if dump:
        Path("/tmp/xhs_probe_product_reviews.json").write_text(json.dumps(rv, ensure_ascii=False, indent=2))
    reviews = dig(rv, "data.reviews") or []
    print(f"    本页评论 {len(reviews)} 条（跨境/冷门常空）")
    for r in reviews[:3]:
        print(f"      · {(r.get('content') or '（无文字）')[:40]}")


def probe_notes(cli: TikHubClient, keyword: str, dump: bool) -> None:
    print(f"\n{'='*70}\n[笔记漏斗] 小红书种草/口碑/趋势  keyword={keyword!r}\n{'='*70}")

    print("\n[1] web_v3/fetch_search_notes（关键词→笔记列表，含互动热度）")
    s = cli.call("/api/v1/xiaohongshu/web_v3/fetch_search_notes", {"keyword": keyword, "page": 1})
    if dump:
        Path("/tmp/xhs_probe_search_notes.json").write_text(json.dumps(s, ensure_ascii=False, indent=2))
    items = dig(s, "data.data.items") or []
    notes = [it for it in items if it.get("modelType") == "note" and it.get("noteCard")]
    print(f"    code={s.get('code')} 笔记 {len(notes)} 条")
    for it in notes[:3]:
        nc = it.get("noteCard", {})
        ii = nc.get("interactInfo", {})
        print(f"      · 赞{ii.get('likedCount')} 藏{ii.get('collectedCount')} 评{ii.get('commentCount')} "
              f"@{(dig(nc, 'user.nickname') or '')[:8]} | {(nc.get('displayTitle') or '')[:28]}")
    if not notes:
        print("    （无笔记，跳过 detail/comments）")
        return

    def _heat(it: dict) -> int:
        ii = it.get("noteCard", {}).get("interactInfo", {})
        return _to_int(ii.get("likedCount")) + _to_int(ii.get("collectedCount"))
    top = max(notes, key=_heat)
    nid, tok = top["id"], top.get("xsecToken", "")
    print(f"\n    选互动最高的笔记: id={nid} 热度≈{_heat(top)}")

    time.sleep(0.5)
    print("\n[2] web_v3/fetch_note_detail（正文/话题标签；需带 xsec_token）")
    d = cli.call("/api/v1/xiaohongshu/web_v3/fetch_note_detail", {"note_id": nid, "xsec_token": tok})
    if dump:
        Path("/tmp/xhs_probe_note_detail.json").write_text(json.dumps(d, ensure_ascii=False, indent=2))
    nc = dig(d, "data.data.items.0.noteCard") or {}
    tags = [t.get("name") for t in (nc.get("tagList") or [])]
    print(f"    标题: {(nc.get('title') or '')[:40]}")
    print(f"    正文: {(nc.get('desc') or '')[:60]}")
    print(f"    话题: {tags[:6]}")

    time.sleep(0.5)
    print("\n[3] web_v3/fetch_note_comments（评论→真实声音/痛点）")
    c = cli.call("/api/v1/xiaohongshu/web_v3/fetch_note_comments", {"note_id": nid, "xsec_token": tok})
    if dump:
        Path("/tmp/xhs_probe_note_comments.json").write_text(json.dumps(c, ensure_ascii=False, indent=2))
    comments = dig(c, "data.data.comments") or []
    print(f"    本页评论 {len(comments)} 条 has_more={dig(c, 'data.data.hasMore')}")
    for cm in comments[:3]:
        print(f"      · 赞{cm.get('likeCount')} [{cm.get('ipLocation')}] {(cm.get('content') or '')[:36]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword", nargs="?", default="口红")
    ap.add_argument("--dump", action="store_true", help="原始 JSON 落 /tmp")
    args = ap.parse_args()
    load_env(ROOT)
    try:
        cli = TikHubClient()
        info = cli.ping()
        print(f"账户 code: {info.get('code')} | 名称: {dig(info, 'api_key_data.api_key_name')}")
        probe_products(cli, args.keyword, args.dump)
        probe_notes(cli, args.keyword, args.dump)
    except TikHubError as exc:
        print(f"[error] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
