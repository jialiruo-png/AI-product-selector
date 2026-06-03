#!/usr/bin/env python3
"""通过 TikHub API 批量采集小红书图文详情，保存到素材库。

复用 collect_any.py 的评分/写文件/图片内嵌逻辑，只把数据来源换成 TikHub REST。
key 从环境变量 TIKHUB_API_KEY 或项目根 .env 读取。

用法：
    python3 采集工作台/scripts/tikhub_xhs_collect.py "AI产品经理" --limit 20
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# 复用 collect_any 的成熟工具函数
sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_any import (  # noqa: E402
    LIBRARY,
    ROOT,
    enrich_scores,
    image_data_uri_from_url,
    output_dir,
    parse_count,
    slug,
    unique_path,
    write_candidate_table,
    write_md,
)

BASE = "https://api.tikhub.dev"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 已采集 note_id 缓存（去重，跨次运行零成本跳过重复笔记）
CACHE_FILE = ROOT / "采集工作台" / ".tikhub_seen_notes.json"

# 草稿库：本次搜到但未达标（短正文/求助贴）的笔记落这里，带图，供人工二次筛选
DRAFT_LIBRARY = ROOT / "采集工作台" / "草稿库"

# 预览正文最短字数：低于此值视为水帖/求助贴，丢弃
MIN_DESC_LEN = 40

# 标题问句词：含这些词的多是无干货的提问/求助，丢弃
JUNK_PATTERNS = [
    "求助", "请问", "求个", "求推荐", "有人吗", "有没有人", "可以吗", "行吗",
    "怎么办", "怎么样吗", "好吗", "能转吗", "能做吗", "靠谱吗", "有前途吗",
    "求带", "求指导", "求辅导", "蹲一个", "蹲个", "在线等",
]


def load_seen() -> set[str]:
    if CACHE_FILE.exists():
        try:
            return set(json.loads(CACHE_FILE.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return set()
    return set()


def save_seen(seen: set[str]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")


def is_junk(note: dict, min_desc: int = MIN_DESC_LEN) -> tuple[bool, str]:
    """用免费的搜索预览数据判断是否垃圾笔记。返回 (是否丢弃, 原因)。"""
    title = note.get("title", "") or ""
    desc = note.get("desc", "") or ""
    # 1) 标题问句/求助词
    for pat in JUNK_PATTERNS:
        if pat in title:
            return True, f"标题含求助/问句词「{pat}」"
    # 标题以问号结尾且很短，多是提问帖
    if title.rstrip().endswith(("?", "？")) and len(title) < 15:
        return True, "短问句标题"
    # 2) 预览正文太短
    if len(desc.strip()) < min_desc:
        return True, f"预览正文过短（{len(desc.strip())}<{min_desc}字）"
    return False, ""


def load_api_key() -> str:
    import os

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


def call(path: str, params: dict | None = None, retries: int = 3) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": UA,
        "Accept": "application/json",
    })
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败 {path}: {last_err}")


def search_notes(keyword: str, want: int) -> list[dict]:
    """搜索笔记，必要时翻页凑够 want 条。

    用 App 端 search_notes（web_v3 搜索端点上游故障时仍可用，且一页约 20 条、
    自带 id/xsec_token/互动数）。返回每条的 note 对象。
    """
    collected: list[dict] = []
    seen: set[str] = set()
    for page in range(1, 6):
        resp = call("/api/v1/xiaohongshu/app/search_notes",
                    {"keyword": keyword, "page": page, "sort": "general", "noteType": "_0"})
        if resp.get("code") != 200:
            break
        items = resp.get("data", {}).get("data", {}).get("items", [])
        notes = [it["note"] for it in items
                 if it.get("model_type") == "note" and it.get("note", {}).get("id")]
        new_notes = [n for n in notes if n["id"] not in seen]
        for n in new_notes:
            seen.add(n["id"])
        collected.extend(new_notes)
        print(f"  搜索第 {page} 页：本页 {len(notes)} 条，累计 {len(collected)} 条")
        if len(collected) >= want or not items:
            break
        time.sleep(0.3)
    return collected


def fetch_detail(note_id: str, xsec_token: str) -> dict:
    try:
        resp = call("/api/v1/xiaohongshu/web_v3/fetch_note_detail",
                    {"note_id": note_id, "xsec_token": xsec_token})
    except RuntimeError:
        return {}
    if not isinstance(resp, dict) or resp.get("code") != 200:
        return {}
    data = resp.get("data") or {}
    inner = data.get("data") if isinstance(data, dict) else None
    items = (inner or {}).get("items", []) if isinstance(inner, dict) else []
    if not items:
        return {}
    return items[0].get("noteCard", {}) or {}


def to_candidate(note: dict) -> dict:
    """App 端 note 对象 → 评分用的统一候选 dict。"""
    note_id = note.get("id", "")
    xsec = note.get("xsec_token", "")
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    if xsec:
        url += f"?xsec_token={xsec}&xsec_source=pc_search"
    # 搜索端图片作为详情失败时的兜底
    fallback_imgs = [
        img.get("url") or img.get("url_size_large") or ""
        for img in note.get("images_list", [])
    ]
    return {
        "note_id": note_id,
        "xsec_token": xsec,
        "title": note.get("title", "") or "无标题",
        "url": url,
        "likes": note.get("liked_count", ""),
        "collects": note.get("collected_count", ""),
        "comments": note.get("comments_count", ""),
        "shares": note.get("shared_count", ""),
        "author": note.get("user", {}).get("nickname", ""),
        "desc_preview": note.get("desc", ""),
        "fallback_images": [u for u in fallback_imgs if u],
    }


def build_body(detail: dict, cand: dict, quiet: bool = False) -> str:
    """详情 + 候选 → markdown 正文（含内嵌图片）。

    详情接口成功时用其完整正文/全图；失败时回退到搜索端的预览正文/兜底图片。
    """
    interact = detail.get("interactInfo", {}) or {}
    likes = interact.get("likedCount") or cand.get("likes", "")
    collects = interact.get("collectedCount") or cand.get("collects", "")
    comments = interact.get("commentCount") or cand.get("comments", "")
    shares = interact.get("shareCount") or cand.get("shares", "")
    tags = [t.get("name", "") for t in detail.get("tagList", []) if t.get("name")]

    # 正文：优先详情完整版，否则搜索预览
    desc = detail.get("desc", "") or cand.get("desc_preview", "") or "（无正文）"

    # 图片 URL：优先详情高清图，否则搜索兜底图
    image_urls: list[str] = []
    for img in detail.get("imageList", []) or []:
        u = img.get("urlDefault") or (
            img.get("infoList", [{}])[-1].get("url") if img.get("infoList") else ""
        )
        if u:
            image_urls.append(u)
    if not image_urls:
        image_urls = list(cand.get("fallback_images", []))

    parts: list[str] = []
    parts.append(f"- 作者: {detail.get('user', {}).get('nickname', '') or cand.get('author', '')}")
    parts.append(f"- 互动: 点赞 {likes} / 收藏 {collects} / 评论 {comments} / 分享 {shares}")
    if tags:
        parts.append(f"- 标签: {' '.join('#' + t for t in tags)}")
    parts.append("")
    parts.append("## 正文")
    parts.append("")
    parts.append(desc)
    parts.append("")

    if image_urls:
        parts.append("## 图片")
        parts.append("")
        embedded = 0
        for idx, img_url in enumerate(image_urls, start=1):
            data_uri = image_data_uri_from_url(img_url)
            if data_uri:
                parts.append(f"![图{idx}]({data_uri})")
                parts.append("")
                embedded += 1
        if not quiet:
            print(f"     内嵌图片 {embedded}/{len(image_urls)} 张")
    return "\n".join(parts)


def write_drafts(keyword: str, drafts: list[tuple[dict, str]], seen: set[str]) -> None:
    """把未达标笔记写入草稿库（带图，仅用搜索数据，不调详情）。

    草稿库是「候选待筛池」：目录按关键词累积，已存在则复用同目录追加，
    note_id 进 seen 以便后续运行不重复落盘。
    """
    name = f"{dt.date.today().isoformat()}-小红书-{slug(keyword)}"
    draft_dir = DRAFT_LIBRARY / slug(name, 80)
    draft_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n草稿库（未达标，带图备查）：{draft_dir}")
    for note, reason in drafts:
        cand = to_candidate(note)
        title = cand["title"]
        # 空 detail → build_body 自动回退到搜索预览正文 + 兜底全图
        body = build_body({}, cand, quiet=True)
        meta = {
            "标题": title,
            "作者": cand.get("author", ""),
            "来源": cand["url"],
            "note_id": cand["note_id"],
            "未达标原因": reason,
            "采集方式": "TikHub API（仅搜索·草稿）",
            "抓取时间": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        path = unique_path(draft_dir, title)
        write_md(path, title, meta, body)
        seen.add(cand["note_id"])
        print(f"  · {title[:24]} — {reason}")
        time.sleep(0.2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword")
    ap.add_argument("--limit", type=int, default=20, help="最多保存多少条（筛选后）")
    ap.add_argument("--detail-top", type=int, default=5,
                    help="只对评分最高的前 N 条调详情拿完整长正文（其余用预览+图片）；0=完全不调详情")
    ap.add_argument("--min-desc", type=int, default=MIN_DESC_LEN,
                    help="预览正文最短字数，低于则丢弃")
    ap.add_argument("--name", default="", help="素材库子目录名")
    ap.add_argument("--no-cache", action="store_true", help="忽略去重缓存，强制重抓")
    args = ap.parse_args()

    if not API_KEY:
        print("未找到 key，请在项目根 .env 写入 TIKHUB_API_KEY=你的真实key")
        return 1

    min_desc = args.min_desc

    print(f"关键词：{args.keyword} | 目标 {args.limit} 条 | 详情仅 Top{args.detail_top} | 来源 TikHub\n")

    # 1) 搜索（$0.01/页，自带图片+预览，免费判断价值）
    raw = search_notes(args.keyword, args.limit * 2)  # 多搜些，留筛选余量
    if not raw:
        print("搜索无结果")
        return 1
    print(f"\n搜索返回 {len(raw)} 条，开始筛选…\n")

    # 2) 筛选漏斗：去重 + 丢垃圾（全部用免费搜索数据，不花一分详情钱）
    #    - 重复（已抓过）：零成本跳过，不落盘
    #    - 未达标（短正文/求助贴）：不进素材库，但搜索信息照样落「草稿库」备查
    #    - 达标：进入下一步评分排序
    seen = set() if args.no_cache else load_seen()
    kept: list[dict] = []
    drafts: list[tuple[dict, str]] = []  # (note, 未达标原因)
    dropped = {"重复": 0, "未达标": 0}
    drop_reasons: list[str] = []
    for note in raw:
        nid = note.get("id", "")
        if nid in seen:
            dropped["重复"] += 1
            continue
        junk, reason = is_junk(note, min_desc)
        if junk:
            dropped["未达标"] += 1
            drafts.append((note, reason))
            drop_reasons.append(f"  ✗ {note.get('title','')[:24]} — {reason}")
            continue
        kept.append(note)
    print(f"筛选：跳过重复 {dropped['重复']} 条（不落盘）、"
          f"未达标 {dropped['未达标']} 条（→草稿库）、达标 {len(kept)} 条（→素材库）")
    for r in drop_reasons[:12]:
        print(r)

    # 2.5) 未达标笔记写入草稿库（带图，零详情费用，供人工二次筛选）
    if drafts:
        write_drafts(args.keyword, drafts, seen)

    if not kept:
        print("\n筛选后无达标笔记，已把未达标的落入草稿库，未消耗详情费用。")
        if not args.no_cache:
            save_seen(seen)
        return 0

    candidates = [to_candidate(n) for n in kept]

    # 3) 评分排序（复用 collect_any 评分体系）
    candidates = enrich_scores("xiaohongshu", args.keyword, candidates)
    selected = candidates[: args.limit]
    detail_n = min(args.detail_top, len(selected))
    print(f"\n保留前 {len(selected)} 条入库，其中评分 Top{detail_n} 调详情拿完整正文\n")

    # 4) 输出目录
    name = args.name or f"{dt.date.today().isoformat()}-小红书-{slug(args.keyword)}-{len(selected)}篇"
    out = output_dir("xiaohongshu", args.keyword, name)
    out.mkdir(parents=True, exist_ok=True)
    print(f"输出目录：{out}\n")

    # 5) 写文件：Top-N 调详情，其余只用预览+图片
    selected_urls: set[str] = set()
    downloaded = 0
    detail_calls = 0
    for i, cand in enumerate(selected, start=1):
        use_detail = i <= detail_n
        tag = "完整正文" if use_detail else "预览+图片"
        print(f"[{i}/{len(selected)}][{tag}] {cand['title'][:28]}")
        detail = {}
        if use_detail:
            detail = fetch_detail(cand["note_id"], cand["xsec_token"])
            detail_calls += 1
            if not detail:
                print("     详情失败，回退预览数据")
        title = detail.get("title", "") or cand["title"]
        body = build_body(detail, cand)
        meta = {
            "标题": title,
            "作者": detail.get("user", {}).get("nickname", "") or cand.get("author", ""),
            "来源": cand["url"],
            "note_id": cand["note_id"],
            "采集方式": "TikHub API" + ("（含详情）" if use_detail else "（仅搜索）"),
            "抓取时间": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        path = unique_path(out, title)
        write_md(path, title, meta, body)
        selected_urls.add(cand["url"])
        seen.add(cand["note_id"])
        downloaded += 1
        time.sleep(0.3)

    # 6) 候选评分表 + 保存去重缓存
    write_candidate_table(
        out, "xiaohongshu", args.keyword,
        candidate_limit=len(candidates),
        download_limit=len(selected),
        candidates=candidates,
        selected_urls=selected_urls,
    )
    if not args.no_cache:
        save_seen(seen)

    # 7) 成本小结（搜索是唯一可脚本代替图片/预览的免费红利，详情是唯一花钱补长正文的步骤）
    search_pages = (len(raw) + 19) // 20
    est_cost = search_pages * 0.01 + detail_calls * 0.01
    naive_cost = len(selected) * 0.01 + 0.01  # 旧方案：每条都调详情
    print(f"\n完成：素材库 {downloaded} 条 | 草稿库 {len(drafts)} 条 | 跳过重复 {dropped['重复']} 条")
    print(f"消耗：搜索 {search_pages} 页 + 详情 {detail_calls} 次 ≈ ${est_cost:.2f}"
          f"（旧方案每条都调详情 ${naive_cost:.2f}，省 {round((1 - est_cost / naive_cost) * 100)}%）")
    print(f"素材目录：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
