#!/usr/bin/env python3
"""TikHub 抖音/TikTok 电商端点探测脚本（仅探接口、摸字段，小批量）。

目的：在写正式采集前，搞清楚 TikHub 电商相关端点的真实返回字段结构，
为「商品打分排序 / 评价情感分析 / 竞品趋势监控」三件事确认数据可得性。

关键结论（2026-06-03 真实 key 实测验证）：
  - 抖音(douyin)命名空间【没有】关键词→商品搜索，也没有独立商品详情；
    其电商端点(fetch_product_review_list / _score / _sku_list / live_room_product)
    全部需要你【已持有】 product_id+shop_id 或 room_id+author_id —— 无法从关键词冷启动选品。
  - TikTok(tiktok shop)命名空间有完整漏斗，且【打分所需字段全在免费搜索端】：
        fetch_search_products_list  ✅ 关键词→商品列表，每条自带：
            product_id / title / image.url_list（图片，免费）
            product_price_info.sale_price_decimal      → 价格
            rate_info.score + rate_info.review_count   → 评分 + 评论数
            sold_info.sold_count                       → 销量
            seller_info / brand_info                   → 店铺/品牌（竞品维度）
            has_more + load_more_params + page_token   → 翻页
        → fetch_product_reviews_v2  ✅ 评论→情感/痛点，注意 page_start 从【1】开始(0 返回空)；
            返回 data.data.data.product_reviews[]，每条 review_rating(1-5)/review_text/
            review_time/is_verified_purchase/review_images/review_country。
            （多数评论 review_text 为空、仅星级；约 1/3 带文字。）
        → fetch_product_detail_v3   ⚠️ 只回页面渲染 config(components_map)，无干净长描述字段，
            对选品价值低；v1/fetch_product_detail 受 region 限制常回 error_code。

  结论：选品打分(目标1)【完全用免费搜索端即可】，无需付费详情；
        评论情感(目标2)只在 Top-N 高分商品上调 reviews；
        正好复刻小红书「搜索免费筛 → Top-N 才花钱」的降本结构。

用法（每个端点只调 1 次、最小 count，省额度）：
    python3 采集工作台/scripts/tikhub_douyin_probe.py "labubu"        # 探 TikTok 漏斗
    python3 采集工作台/scripts/tikhub_douyin_probe.py --dump          # 把原始 JSON 落 /tmp 供查字段
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
    # TikHub 上游对部分电商端点会间歇性回 400（"Please retry"，不扣费）；重试几次再放弃。
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


def shape(obj, depth=0, max_depth=3, max_keys=40):
    """递归打印 JSON 的键结构 + 示例值，便于摸字段，不打印超长内容。"""
    pad = "  " * depth
    if depth > max_depth:
        return ["%s…" % pad]
    out = []
    if isinstance(obj, dict):
        for i, (k, v) in enumerate(obj.items()):
            if i >= max_keys:
                out.append(f"{pad}… (+{len(obj)-max_keys} more keys)")
                break
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{k}:")
                out += shape(v, depth + 1, max_depth, max_keys)
            else:
                sv = repr(v)
                if len(sv) > 70:
                    sv = sv[:70] + "…"
                out.append(f"{pad}{k} = {sv}")
    elif isinstance(obj, list):
        out.append(f"{pad}[list len={len(obj)}] first item ->")
        if obj:
            out += shape(obj[0], depth + 1, max_depth, max_keys)
    return out


def probe_tiktok_funnel(keyword: str, region: str, dump: bool) -> None:
    print(f"\n{'='*70}\nTikTok 电商漏斗探测  keyword={keyword!r} region={region}\n{'='*70}")

    # 1) 商品搜索（免费拿到打分全字段）
    print("\n[1] fetch_search_products_list（关键词→商品列表，含价格/销量/评分）")
    s = call("/api/v1/tiktok/shop/web/fetch_search_products_list",
             {"search_word": keyword, "offset": 0, "region": region})
    print("    code:", s.get("code"), s.get("_http_error", ""))
    if s.get("_http_error") == 400:
        print("    （400 多为 TikHub 上游临时故障，不扣费，重试即可）")
    if dump:
        Path("/tmp/dy_probe_search.json").write_text(json.dumps(s, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/dy_probe_search.json")
    # 真实层级：data.data.data.products[]
    products = (((s.get("data") or {}).get("data") or {}).get("data") or {}).get("products", []) \
        if isinstance(s.get("data"), dict) else []
    print(f"    本页商品 {len(products)} 条")
    for p in products[:3]:
        print(f"      · pid={p.get('product_id')} "
              f"价${p.get('product_price_info',{}).get('sale_price_decimal')} "
              f"销{p.get('sold_info',{}).get('sold_count')} "
              f"评{p.get('rate_info',{}).get('score')}({p.get('rate_info',{}).get('review_count')}) "
              f"| {p.get('title','')[:30]}")
    if not products:
        print("    （无商品，后续探测跳过）")
        return

    # 选评论数最多的一条做后续探测
    def _rc(p):
        try:
            return int(p.get("rate_info", {}).get("review_count", "0") or 0)
        except Exception:  # noqa: BLE001
            return 0
    top = max(products, key=_rc)
    pid = top["product_id"]
    print(f"\n    选评论最多的商品做后续探测: pid={pid} review_count={_rc(top)}")

    time.sleep(0.5)
    # 2) 商品评论（情感/痛点原料）—— 注意 page_start 从 1 开始
    print("\n[2] fetch_product_reviews_v2（评论→情感/痛点；page_start 从 1 起）")
    rev = call("/api/v1/tiktok/shop/web/fetch_product_reviews_v2",
               {"product_id": pid, "page_start": 1, "region": region})
    print("    code:", rev.get("code"), rev.get("_http_error", ""))
    if dump:
        Path("/tmp/dy_probe_reviews.json").write_text(json.dumps(rev, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/dy_probe_reviews.json")
    rdata = (((rev.get("data") or {}).get("data") or {}).get("data") or {}) \
        if isinstance(rev.get("data"), dict) else {}
    reviews = rdata.get("product_reviews", [])
    print(f"    total_reviews={rdata.get('total_reviews')} has_more={rdata.get('has_more')} 本页 {len(reviews)} 条")
    withtext = sum(1 for r in reviews if (r.get("review_text") or "").strip())
    print(f"    本页带文字评论 {withtext}/{len(reviews)} 条（其余仅星级）")
    for r in reviews[:3]:
        print(f"      ★{r.get('review_rating')} {(r.get('review_text') or '（无文字）')[:40]}")

    time.sleep(0.5)
    # 3) 商品详情（确认对选品价值低）
    print("\n[3] fetch_product_detail_v3（确认无干净长描述，选品价值低）")
    det = call("/api/v1/tiktok/shop/web/fetch_product_detail_v3",
               {"product_id": pid, "region": region})
    print("    code:", det.get("code"), det.get("_http_error", ""))
    if dump:
        Path("/tmp/dy_probe_detail.json").write_text(json.dumps(det, ensure_ascii=False, indent=2))
        print("    raw -> /tmp/dy_probe_detail.json")
    pd = (((det.get("data") or {}).get("data") or {}).get("product_data") or {}) \
        if isinstance(det.get("data"), dict) else {}
    print(f"    product_data 顶层键: {list(pd.keys()) if isinstance(pd, dict) else type(pd).__name__}"
          " （多为页面渲染 config，非干净描述字段）")


def _find_first_product_id(data) -> str:
    """在未知结构里宽松搜出第一个像 product_id 的值。"""
    found = []

    def walk(o):
        if found:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if found:
                    return
                if k.lower() in ("product_id", "productid", "id") and isinstance(v, (str, int)) and str(v).isdigit() and len(str(v)) >= 8:
                    found.append(str(v))
                    return
                walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)
    walk(data)
    return found[0] if found else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword", nargs="?", default="phone case")
    ap.add_argument("--region", default="US")
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

    probe_tiktok_funnel(args.keyword, args.region, args.dump)
    print("\n提示：抖音(douyin)无关键词商品搜索，商品类端点需已知 product_id/room_id；"
          "选品漏斗建议走 TikTok shop 命名空间。详见脚本头部注释。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
