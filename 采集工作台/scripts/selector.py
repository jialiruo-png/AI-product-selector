#!/usr/bin/env python3
"""选品 pipeline：search → score → 落 SQLite → Top-N 评论 → LLM 痛点分析 → 落 SQLite。

用法：
    # TikTok Shop 选品（默认 region=US，topn=5，跑 LLM 分析）
    python3 采集工作台/scripts/select.py tiktok "labubu" --topn 5 --analyze

    # 小红书商品 + 笔记双漏斗
    python3 采集工作台/scripts/select.py xhs "口红" --topn 5 --analyze

    # 不跑 LLM、只做搜索 + 打分 + 落盘
    python3 采集工作台/scripts/select.py tiktok "phone case"

    # 看某商品历次快照（趋势）
    python3 采集工作台/scripts/select.py trend tiktok <product_id>
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from _tikhub_client import TikHubClient, TikHubError, dig, load_env
import db
import score

ROOT = Path(__file__).resolve().parents[2]


def _print_table(rows: list[dict], cols: list[tuple[str, str, int]]) -> None:
    """cols: [(key, header, width)]"""
    header = " | ".join(h.ljust(w) for _, h, w in cols)
    print(header)
    print("-" * len(header))
    for r in rows:
        line = " | ".join(str(r.get(k, ""))[:w].ljust(w) for k, _, w in cols)
        print(line)


def _fetch_tiktok_reviews(cli: TikHubClient, pid: str, region: str,
                          max_pages: int = 2) -> list[dict]:
    out = []
    for page in range(1, max_pages + 1):
        try:
            r = cli.call("/api/v1/tiktok/shop/web/fetch_product_reviews_v2",
                         {"product_id": pid, "page_start": page, "region": region})
        except TikHubError as exc:
            print(f"    [reviews err page={page}] {exc}")
            break
        items = dig(r, "data.data.data.product_reviews") or []
        for it in items:
            out.append({
                "review_id": it.get("review_id"),
                "rating": it.get("review_rating"),
                "text": it.get("review_text"),
                "ts": it.get("review_time"),
                "raw": it,
            })
        if not dig(r, "data.data.data.has_more"):
            break
        time.sleep(0.4)
    return out


def _fetch_xhs_product_reviews(cli: TikHubClient, sku: str,
                               max_pages: int = 2) -> list[dict]:
    out = []
    for page in range(max_pages):
        try:
            r = cli.call("/api/v1/xiaohongshu/app_v2/get_product_reviews",
                         {"sku_id": sku, "page": page})
        except TikHubError as exc:
            print(f"    [xhs reviews err page={page}] {exc}")
            break
        items = dig(r, "data.reviews") or []
        for it in items:
            out.append({
                "review_id": it.get("review_id") or it.get("id"),
                "rating": it.get("score") or it.get("rating"),
                "text": it.get("content"),
                "ts": it.get("create_time") or it.get("time"),
                "raw": it,
            })
        if not items:
            break
        time.sleep(0.4)
    return out


def _fetch_xhs_note_comments(cli: TikHubClient, nid: str, tok: str) -> list[dict]:
    try:
        r = cli.call("/api/v1/xiaohongshu/web_v3/fetch_note_comments",
                     {"note_id": nid, "xsec_token": tok})
    except TikHubError as exc:
        print(f"    [xhs comments err] {exc}")
        return []
    items = dig(r, "data.data.comments") or []
    return [{
        "review_id": it.get("id"),
        "rating": None,
        "text": it.get("content"),
        "ts": it.get("createTime"),
        "raw": it,
    } for it in items]


def cmd_tiktok(args: argparse.Namespace) -> int:
    cli = TikHubClient()
    print(f"账户: {dig(cli.ping(), 'api_key_data.api_key_name')}")
    print(f"\n[1/4] 搜索 TikTok Shop  keyword={args.keyword!r} region={args.region}")
    s = cli.call("/api/v1/tiktok/shop/web/fetch_search_products_list",
                 {"search_word": args.keyword, "offset": 0, "region": args.region})
    products = dig(s, "data.data.data.products") or []
    if not products:
        print("    （无商品，结束）")
        return 0
    print(f"    本页 {len(products)} 条")

    print("\n[2/4] 打分排序")
    scored = score.score_tiktok_products(products)
    _print_table(scored[:max(args.topn, 5)],
                 [("score", "score", 6), ("product_id", "pid", 22),
                  ("price", "price", 7), ("sold", "sold", 6),
                  ("rating", "rate", 5), ("review_count", "rev", 5),
                  ("title", "title", 40)])

    con = db.connect(args.db)
    run_id = db.start_run(con, "tiktok", args.keyword, region=args.region)
    db.save_tiktok_products(con, run_id, scored)
    print(f"    → 落 SQLite run_id={run_id} {args.db}")

    if not args.analyze:
        print("\n[3/4] 跳过评论拉取（未带 --analyze）")
        print("[4/4] 跳过 LLM 分析")
        return 0

    import analyze as ana
    top = scored[:args.topn]
    print(f"\n[3/4] 拉 Top-{len(top)} 评论")
    for s in top:
        pid = s["product_id"]
        print(f"  · pid={pid} 标题={(s.get('title') or '')[:30]}")
        rvs = _fetch_tiktok_reviews(cli, pid, args.region, max_pages=args.review_pages)
        db.save_reviews(con, "tiktok", pid, rvs)
        print(f"    评论 {len(rvs)} 条入库")

        print("    [4/4] LLM 痛点分析中…")
        try:
            result = ana.analyze_reviews(rvs)
        except Exception as exc:  # noqa: BLE001
            print(f"    分析失败: {exc}")
            continue
        db.save_pain_points(con, run_id, "tiktok", pid, result)
        sent = result.get("sentiment", {})
        print(f"    情感: +{sent.get('positive','-')} ~{sent.get('neutral','-')} -{sent.get('negative','-')}")
        for p in (result.get("pain_points") or [])[:5]:
            print(f"      痛点[{p.get('freq')}] {p.get('label')}  例: {(p.get('example') or '')[:30]}")
        for h in (result.get("highlights") or [])[:5]:
            print(f"      好评[{h.get('freq')}] {h.get('label')}  例: {(h.get('example') or '')[:30]}")
    return 0


def cmd_xhs(args: argparse.Namespace) -> int:
    cli = TikHubClient()
    print(f"账户: {dig(cli.ping(), 'api_key_data.api_key_name')}")
    con = db.connect(args.db)

    # 商品漏斗
    print(f"\n[商品] 搜索  keyword={args.keyword!r}")
    s = cli.call("/api/v1/xiaohongshu/app_v2/search_products",
                 {"keyword": args.keyword, "page": 1})
    cards = dig(s, "data.data.module.data") or []
    goods = [c for c in cards if "goods" in (c.get("card_name") or "")]
    print(f"    商品卡 {len(goods)} 条")

    scored_p: list[dict] = []
    if goods:
        # 拉每个 sku 的评分概览（便宜，给打分用）
        overviews = {}
        for c in goods[: args.topn * 2]:  # 多拉一些，给打分提供 rating
            sku = c.get("content", {}).get("id")
            if not sku:
                continue
            try:
                ov = cli.call("/api/v1/xiaohongshu/app_v2/get_product_review_overview",
                              {"sku_id": sku})
                overviews[str(sku)] = ov.get("data") or {}
            except TikHubError as exc:
                print(f"    [overview err sku={sku}] {exc}")
            time.sleep(0.2)

        scored_p = score.score_xhs_products(goods, overviews=overviews)
        print("\n    打分 Top:")
        _print_table(scored_p[: args.topn],
                     [("score", "score", 6), ("sku_id", "sku", 14),
                      ("price", "price", 7), ("discount", "disc", 5),
                      ("rating", "rate", 5), ("title", "title", 36)])
        run_id = db.start_run(con, "xhs_product", args.keyword)
        db.save_xhs_products(con, run_id, scored_p)
        print(f"    → 落 SQLite run_id={run_id}")

        if args.analyze:
            import analyze as ana
            for s in scored_p[: args.topn]:
                sku = s["sku_id"]
                rvs = _fetch_xhs_product_reviews(cli, sku, max_pages=args.review_pages)
                db.save_reviews(con, "xhs_product", sku, rvs)
                print(f"    sku={sku} 评论 {len(rvs)} 条")
                try:
                    result = ana.analyze_reviews(rvs)
                except Exception as exc:  # noqa: BLE001
                    print(f"      分析失败: {exc}")
                    continue
                db.save_pain_points(con, run_id, "xhs_product", sku, result)
                sent = result.get("sentiment", {})
                print(f"      情感: +{sent.get('positive','-')} ~{sent.get('neutral','-')} -{sent.get('negative','-')}")
                for p in (result.get("pain_points") or [])[:3]:
                    print(f"        痛点[{p.get('freq')}] {p.get('label')}")

    # 笔记漏斗
    print(f"\n[笔记] 搜索  keyword={args.keyword!r}")
    s = cli.call("/api/v1/xiaohongshu/web_v3/fetch_search_notes",
                 {"keyword": args.keyword, "page": 1})
    items = dig(s, "data.data.items") or []
    notes = [it for it in items if it.get("modelType") == "note" and it.get("noteCard")]
    if not notes:
        print("    （无笔记）")
        return 0
    scored_n = score.score_xhs_notes(notes)
    print("    打分 Top:")
    _print_table(scored_n[: args.topn],
                 [("score", "score", 6), ("likes", "赞", 6),
                  ("collects", "藏", 6), ("comments", "评", 5),
                  ("user", "user", 10), ("title", "title", 36)])
    run_id_n = db.start_run(con, "xhs_note", args.keyword)
    db.save_xhs_notes(con, run_id_n, scored_n)
    print(f"    → 落 SQLite run_id={run_id_n}")

    if args.analyze:
        import analyze as ana
        for n in scored_n[: args.topn]:
            comments = _fetch_xhs_note_comments(cli, n["note_id"], n.get("xsec_token") or "")
            db.save_reviews(con, "xhs_note", n["note_id"], comments)
            print(f"    note={n['note_id']} 评论 {len(comments)} 条")
            try:
                result = ana.analyze_reviews(comments)
            except Exception as exc:  # noqa: BLE001
                print(f"      分析失败: {exc}")
                continue
            db.save_pain_points(con, run_id_n, "xhs_note", n["note_id"], result)
            sent = result.get("sentiment", {})
            print(f"      情感: +{sent.get('positive','-')} ~{sent.get('neutral','-')} -{sent.get('negative','-')}")
    return 0


def cmd_trend(args: argparse.Namespace) -> int:
    con = db.connect(args.db)
    rows = db.trend(con, args.source, args.source_id)
    if not rows:
        print(f"无快照: source={args.source} id={args.source_id}")
        return 1
    print(f"\n{args.source} / {args.source_id} 历次快照：")
    _print_table(rows,
                 [("run_id", "run", 5), ("fetched_at", "ts", 12),
                  ("price", "price", 8), ("sold", "sold", 8),
                  ("rating", "rate", 5), ("review_count", "rev", 6),
                  ("score", "score", 6)])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI 选品 pipeline")
    ap.add_argument("--db", default=str(ROOT / "采集工作台/outputs/selector.db"),
                    help="SQLite 路径（默认 采集工作台/outputs/selector.db）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_tt = sub.add_parser("tiktok", help="TikTok Shop 选品")
    p_tt.add_argument("keyword")
    p_tt.add_argument("--region", default="US")
    p_tt.add_argument("--topn", type=int, default=5)
    p_tt.add_argument("--review-pages", type=int, default=2, dest="review_pages")
    p_tt.add_argument("--analyze", action="store_true", help="拉 Top-N 评论 + LLM 痛点分析")
    p_tt.set_defaults(func=cmd_tiktok)

    p_xhs = sub.add_parser("xhs", help="小红书商品 + 笔记双漏斗")
    p_xhs.add_argument("keyword")
    p_xhs.add_argument("--topn", type=int, default=5)
    p_xhs.add_argument("--review-pages", type=int, default=2, dest="review_pages")
    p_xhs.add_argument("--analyze", action="store_true")
    p_xhs.set_defaults(func=cmd_xhs)

    p_tr = sub.add_parser("trend", help="某 source_id 历次快照趋势")
    p_tr.add_argument("source", choices=["tiktok", "xhs_product", "xhs_note"])
    p_tr.add_argument("source_id")
    p_tr.set_defaults(func=cmd_trend)

    args = ap.parse_args(argv)
    load_env(ROOT)
    try:
        return args.func(args)
    except TikHubError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
