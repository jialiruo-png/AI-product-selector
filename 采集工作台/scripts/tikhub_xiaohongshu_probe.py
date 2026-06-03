#!/usr/bin/env python3
"""TikHub 小红书(xiaohongshu/xhs)选品 + 内容端点探测脚本（仅探接口、摸字段，小批量）。

目的：与抖音/TikTok 探测脚本配套，搞清楚小红书相关端点的真实返回字段结构，
为「商品打分排序 / 评价情感分析 / 竞品趋势监控」三件事确认数据可得性，
并把小红书种草帖（笔记）作为选品的内容/口碑维度补进来。

关键结论（2026-06-03 真实 key 实测验证）：
  小红书有【两条互补的漏斗】，命名空间分别在 app_v2(商品) 和 web_v3(笔记)：

  ① 商品漏斗（选品打分核心，app_v2 命名空间）
        app_v2/search_products  ✅ 关键词→商品列表，返回 data.data.module.data[] 卡片，
            goods 卡 content 自带：
                id（= sku_id）/ title
                price_info.{price, origin_price, foreign_price}   → 价格
                image[].url                                       → 主图（免费）
                vendor.{vendor_name, seller_id, vendor_link}      → 店铺（竞品维度）
                tag_strategy_map.*                                → 促销/库存标
            页级 next_page + search_id → 翻页。
        → app_v2/get_product_review_overview  ✅ 评分概览（差评率原料，便宜）：
            avgScore / total / scoreToCnt{1..5} / purchaseHistoryCount
        → app_v2/get_product_reviews          ✅ 评论明细（情感/痛点文本，仅 Top-N 调）：
            data.reviews[]；与 TikTok 一样，跨境/冷门商品评论常为空或仅星级。
        → app_v2/get_product_detail           ⚠️ 需 sku_id，长描述价值有限，按需调。

  ② 笔记漏斗（种草/口碑/趋势维度，web_v3 命名空间）
        web_v3/fetch_search_notes  ✅ 关键词→笔记列表，返回 data.data.items[]，
            每条 noteCard 自带：
                displayTitle / cover.urlDefault / type(normal|video)
                user.{nickname, userId}
                interactInfo.{likedCount, collectedCount, commentCount, sharedCount} → 互动热度
            note 级 id + xsecToken（详情/评论必须带 xsecToken）。
        → web_v3/fetch_note_detail   ✅ 笔记正文：noteCard.{title, desc, tagList[], imageList, time}
        → web_v3/fetch_note_comments ✅ 笔记评论：data.comments[]，每条 content / likeCount /
            ipLocation / userInfo / subComments —— 痛点与真实声音的另一来源。

  结论：小红书选品打分(目标1)用 search_products 免费卡片字段即可；
        情感/痛点(目标2)= 商品评论 + 笔记评论双来源，仅在 Top-N 上调；
        趋势/竞品(目标3)= 笔记 interactInfo 热度 + 商品 vendor 店铺，按时间重复搜对比。
        复刻「搜索免费筛 → Top-N 才花钱」的降本结构。

用法（每个端点只调 1 次、最小分页，省额度）：
    python3 采集工作台/scripts/tikhub_xiaohongshu_probe.py "口红"          # 探商品+笔记双漏斗
    python3 采集工作台/scripts/tikhub_xiaohongshu_probe.py "口红" --dump   # 把原始 JSON 落 /tmp 供查字段
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.environ.get("TIKHUB_BASE", "https://api.tikhub.dev")
ROOT = Path(__file__).resolve().parents[2]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def load_api_key() -> str:
    key = os.environ.get("TIKHUB_API_KEY", "").strip()
    if key:
        return key
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("TIKHUB_API_KEY"):
                return line.split("=", 1)[-1].strip().strip('"').strip()
    return ""


API_KEY = load_api_key()


def call(path: str, params: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": UA,
        "Accept": "application/json",
    })
    last = None
    # TikHub 上游对部分端点会间歇性回 400（"Please retry"，不扣费）；重试几次再放弃。
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # noqa: PERF203
            body = exc.read().decode("utf-8", "ignore")[:300]
            last = {"_http_error": exc.code, "_body": body}
            if exc.code == 400 and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            return last
        except Exception as exc:  # noqa: BLE001
            last = {"_error": str(exc)}
            time.sleep(1.5 * (attempt + 1))
    return last if isinstance(last, dict) else {"_error": str(last)}


def _to_int(v) -> int:
    try:
        return int(str(v).replace("+", "").replace(",", "") or 0)
    except Exception:  # noqa: BLE001
        return 0


def probe_products(keyword: str, region_unused, dump: bool) -> None:
    print(f"\n{'='*70}\n[商品漏斗] 小红书选品打分  keyword={keyword!r}\n{'='*70}")

    # 1) 商品搜索（免费拿打分字段）
    print("\n[1] app_v2/search_products（关键词→商品列表，含价格/店铺/主图）")
    s = call("/api/v1/xiaohongshu/app_v2/search_products", {"keyword": keyword, "page": 1})
    print("    code:", s.get("code"), s.get("_http_error", ""))
    if dump:
        Path("/tmp/xhs_probe_products.json").write_text(json.dumps(s, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/xhs_probe_products.json")
    # 真实层级：data.data.module.data[] 卡片，取 goods 卡
    cards = (((s.get("data") or {}).get("data") or {}).get("module") or {}).get("data", []) \
        if isinstance(s.get("data"), dict) else []
    goods = [c for c in cards if "goods" in (c.get("card_name") or "")]
    print(f"    本页商品卡 {len(goods)} 条（next_page={((s.get('data') or {}).get('data') or {}).get('next_page')}）")
    for c in goods[:3]:
        ct = c.get("content", {})
        pi = ct.get("price_info", {})
        print(f"      · sku={ct.get('id')} 价¥{pi.get('price')}(原¥{pi.get('origin_price')}) "
              f"店={ct.get('vendor', {}).get('vendor_name', '')[:12]} | {ct.get('title', '')[:30]}")
    if not goods:
        print("    （无商品卡，后续商品探测跳过）")
        return
    sku = goods[0]["content"]["id"]

    time.sleep(0.5)
    # 2) 评分概览（便宜的差评率原料）
    print("\n[2] app_v2/get_product_review_overview（评分分布/差评率，便宜）")
    ov = call("/api/v1/xiaohongshu/app_v2/get_product_review_overview", {"sku_id": sku})
    print("    code:", ov.get("code"), ov.get("_http_error", ""))
    od = ov.get("data", {}) or {}
    if dump:
        Path("/tmp/xhs_probe_review_overview.json").write_text(json.dumps(ov, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/xhs_probe_review_overview.json")
    print(f"    sku={sku} 评分={od.get('avgScore')!r} 评价数={od.get('total')} "
          f"销量={od.get('purchaseHistoryCount')} 分布={od.get('scoreToCnt')}")

    time.sleep(0.5)
    # 3) 评论明细（情感/痛点文本，仅 Top-N 调）
    print("\n[3] app_v2/get_product_reviews（评论文本→情感/痛点；page 从 0 起）")
    rv = call("/api/v1/xiaohongshu/app_v2/get_product_reviews", {"sku_id": sku, "page": 0})
    print("    code:", rv.get("code"), rv.get("_http_error", ""))
    reviews = (rv.get("data") or {}).get("reviews", []) if isinstance(rv.get("data"), dict) else []
    if dump:
        Path("/tmp/xhs_probe_product_reviews.json").write_text(json.dumps(rv, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/xhs_probe_product_reviews.json")
    print(f"    本页评论 {len(reviews)} 条（跨境/冷门商品常为空或仅星级，同 TikTok）")
    for r in reviews[:3]:
        print(f"      · {(r.get('content') or '（无文字）')[:40]}")


def probe_notes(keyword: str, dump: bool) -> None:
    print(f"\n{'='*70}\n[笔记漏斗] 小红书种草/口碑/趋势  keyword={keyword!r}\n{'='*70}")

    # 1) 笔记搜索（免费拿互动热度）
    print("\n[1] web_v3/fetch_search_notes（关键词→笔记列表，含互动热度）")
    s = call("/api/v1/xiaohongshu/web_v3/fetch_search_notes", {"keyword": keyword, "page": 1})
    print("    code:", s.get("code"), s.get("_http_error", ""))
    if dump:
        Path("/tmp/xhs_probe_search_notes.json").write_text(json.dumps(s, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/xhs_probe_search_notes.json")
    # 真实层级：data.data.items[]
    items = (((s.get("data") or {}).get("data") or {}).get("items", [])) \
        if isinstance(s.get("data"), dict) else []
    notes = [it for it in items if it.get("modelType") == "note" and it.get("noteCard")]
    print(f"    本页笔记 {len(notes)} 条")
    for it in notes[:3]:
        nc = it.get("noteCard", {})
        ii = nc.get("interactInfo", {})
        print(f"      · 赞{ii.get('likedCount')} 藏{ii.get('collectedCount')} 评{ii.get('commentCount')} "
              f"@{nc.get('user', {}).get('nickname', '')[:8]} | {nc.get('displayTitle', '')[:28]}")
    if not notes:
        print("    （无笔记，后续笔记探测跳过）")
        return

    # 选互动最高的一条做后续探测
    def _heat(it):
        ii = it.get("noteCard", {}).get("interactInfo", {})
        return _to_int(ii.get("likedCount")) + _to_int(ii.get("collectedCount"))
    top = max(notes, key=_heat)
    nid = top["id"]
    tok = top.get("xsecToken", "")
    print(f"\n    选互动最高的笔记做后续探测: id={nid} 热度≈{_heat(top)}")

    time.sleep(0.5)
    # 2) 笔记详情（正文 + 话题标签）
    print("\n[2] web_v3/fetch_note_detail（正文/话题标签；需带 xsec_token）")
    d = call("/api/v1/xiaohongshu/web_v3/fetch_note_detail", {"note_id": nid, "xsec_token": tok})
    print("    code:", d.get("code"), d.get("_http_error", ""))
    if dump:
        Path("/tmp/xhs_probe_note_detail.json").write_text(json.dumps(d, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/xhs_probe_note_detail.json")
    ditems = (((d.get("data") or {}).get("data") or {}).get("items", [])) \
        if isinstance(d.get("data"), dict) else []
    nc = ditems[0].get("noteCard", {}) if ditems else {}
    tags = [t.get("name") for t in nc.get("tagList", [])]
    print(f"    标题: {nc.get('title', '')[:40]}")
    print(f"    正文: {(nc.get('desc') or '')[:60]}")
    print(f"    话题标签: {tags[:6]}")

    time.sleep(0.5)
    # 3) 笔记评论（真实声音/痛点的另一来源）
    print("\n[3] web_v3/fetch_note_comments（评论→真实声音/痛点；需带 xsec_token）")
    c = call("/api/v1/xiaohongshu/web_v3/fetch_note_comments", {"note_id": nid, "xsec_token": tok})
    print("    code:", c.get("code"), c.get("_http_error", ""))
    if dump:
        Path("/tmp/xhs_probe_note_comments.json").write_text(json.dumps(c, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/xhs_probe_note_comments.json")
    comments = (((c.get("data") or {}).get("data") or {}).get("comments", [])) \
        if isinstance(c.get("data"), dict) else []
    print(f"    本页评论 {len(comments)} 条 "
          f"has_more={(((c.get('data') or {}).get('data') or {}).get('hasMore'))}")
    for cm in comments[:3]:
        print(f"      · 赞{cm.get('likeCount')} [{cm.get('ipLocation')}] {(cm.get('content') or '')[:36]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword", nargs="?", default="口红")
    ap.add_argument("--dump", action="store_true", help="把原始 JSON 落 /tmp 供细看字段")
    args = ap.parse_args()

    if not API_KEY:
        print("未找到 key，请在项目根 .env 写入 TIKHUB_API_KEY=你的真实key")
        return 1
    print(f"key 前缀 {API_KEY[:6]}... 长度 {len(API_KEY)}")

    # 账户连通性（不扣费）
    info = call("/api/v1/tikhub/user/get_user_info")
    print("账户 code:", info.get("code"), "| 名称:",
          info.get("api_key_data", {}).get("api_key_name"))

    probe_products(args.keyword, None, args.dump)
    probe_notes(args.keyword, args.dump)
    print("\n提示：小红书选品=商品漏斗(app_v2/search_products)做打分；"
          "笔记漏斗(web_v3/fetch_search_notes)做种草热度与口碑。详见脚本头部注释。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
