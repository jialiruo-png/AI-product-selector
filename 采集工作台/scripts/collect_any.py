#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "采集工作台" / "素材库"
COLLECT = ROOT / "采集工作台" / "collect"
INLINE_IMAGES = ROOT / "采集工作台" / "scripts" / "inline_markdown_images.py"
SCORE_FILENAME = "00-候选评分表.md"


def run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout


def run_opencli(cmd: list[str], timeout: int = 120, retries: int = 1) -> tuple[int, str]:
    full_cmd = ["opencli", *cmd]
    code, text = run(full_cmd, timeout=timeout)
    for _ in range(retries):
        if code == 0:
            break
        if "BROWSER_CONNECT" not in text and "Failed to start opencli daemon" not in text:
            break
        run(["opencli", "doctor"], timeout=30)
        time.sleep(2)
        code, text = run(full_cmd, timeout=timeout)
    return code, text


def slug(text: str, max_len: int = 48) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", text.strip(), flags=re.UNICODE).strip("-._")
    return (text or "素材")[:max_len]


def is_url(text: str) -> bool:
    return text.startswith(("http://", "https://"))


def all_urls(items: list[str]) -> bool:
    return bool(items) and all(is_url(item) for item in items)


def split_inputs(raw: str) -> list[str]:
    parts: list[str] = []
    for line in raw.replace("\r", "\n").split("\n"):
        line = line.strip()
        if line:
            parts.append(line)
    return parts


def output_dir(platform: str, query: str, custom_name: str = "") -> Path:
    name = custom_name.strip() or f"{dt.date.today().isoformat()}-{platform}-{slug(query)}"
    base = LIBRARY / slug(name, 80)
    if not base.exists():
        return base
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return LIBRARY / f"{base.name}-{stamp}"


def write_md(path: Path, title: str, meta: dict[str, object], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title.strip() or path.stem}", ""]
    for key, value in meta.items():
        if value not in (None, ""):
            lines.append(f"- {key}: {value}")
    lines.extend(["", "---", "", body.strip(), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def unique_path(out: Path, title: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    base = out / f"{stamp} - {slug(title, 80)}.md"
    if not base.exists():
        return base
    for i in range(2, 100):
        candidate = out / f"{stamp} - {slug(title, 72)}-{i}.md"
        if not candidate.exists():
            return candidate
    return out / f"{stamp} - {slug(title, 64)}-{os.getpid()}.md"


def count_md(out: Path) -> int:
    return len(list(out.glob("*.md"))) if out.exists() else 0


def count_article_md(out: Path) -> int:
    if not out.exists():
        return 0
    return len([p for p in out.glob("*.md") if p.name != SCORE_FILENAME])


def count_embedded_images(out: Path) -> int:
    if not out.exists():
        return 0
    total = 0
    for md_path in out.glob("*.md"):
        text = md_path.read_text(encoding="utf-8", errors="replace")
        total += text.count("](data:image/")
    return total


def inline_markdown_images(out: Path) -> None:
    if INLINE_IMAGES.exists():
        run([str(INLINE_IMAGES), str(out)], timeout=120)


def parse_count(value: object) -> int:
    if value in (None, ""):
        return 0
    text = str(value).strip().lower().replace(",", "")
    text = text.replace("赞同", "").replace("点赞", "").replace("收藏", "").replace("评论", "")
    multiplier = 1.0
    if text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    elif text.endswith("k"):
        multiplier = 1000.0
        text = text[:-1]
    elif text.endswith("w"):
        multiplier = 10000.0
        text = text[:-1]
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return 0
    return int(float(match.group(0)) * multiplier)


def first_present(item: dict[str, object], keys: list[str], default: object = "") -> object:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return default


def text_relevance(query: str, *parts: object) -> int:
    text = " ".join(str(part or "") for part in parts).lower()
    normalized_query = query.lower().strip()
    if not normalized_query:
        return 0
    score = 0
    if normalized_query in text:
        score += 18
    tokens = [t for t in re.split(r"[\s,，。:：/|]+", normalized_query) if t]
    if len(tokens) <= 1 and len(normalized_query) >= 4:
        tokens = [normalized_query[i : i + 2] for i in range(0, len(normalized_query) - 1, 2)]
    matched = sum(1 for token in tokens if token and token in text)
    if tokens:
        score += round(7 * matched / len(tokens))
    return min(score, 25)


def freshness_score(value: object) -> int:
    if value in (None, ""):
        return 5
    text = str(value)
    year_match = re.search(r"(20\d{2})", text)
    if not year_match:
        return 6
    year = int(year_match.group(1))
    current = dt.date.today().year
    if year >= current:
        return 10
    if year == current - 1:
        return 8
    if year == current - 2:
        return 6
    return 4


def risk_penalty(title: object, summary: object = "") -> int:
    text = f"{title or ''} {summary or ''}"
    penalty = 0
    high_risk = ["招生", "报名", "训练营", "体验营", "割韭菜", "暴富", "副业", "带货"]
    medium_risk = ["不学就", "淘汰", "焦虑", "逆袭", "速成", "收割", "私域"]
    for word in high_risk:
        if word in text:
            penalty += 6
    for word in medium_risk:
        if word in text:
            penalty += 3
    return min(penalty, 15)


def raw_heat(platform: str, item: dict[str, object], rank: int, total: int) -> float:
    if platform == "xiaohongshu":
        return (
            parse_count(first_present(item, ["likes", "like", "liked_count", "点赞"]))
            + parse_count(first_present(item, ["collects", "favorites", "collected_count", "收藏"])) * 1.5
            + parse_count(first_present(item, ["comments", "comment_count", "评论"])) * 2
        )
    if platform == "zhihu":
        return (
            parse_count(first_present(item, ["votes", "voteup_count", "likes", "赞同"]))
            + parse_count(first_present(item, ["comments", "comment_count", "评论"])) * 2
            + parse_count(first_present(item, ["favorites", "收藏"])) * 1.5
        )
    if platform == "github":
        return (
            parse_count(first_present(item, ["stargazersCount", "stars", "star"]))
            + parse_count(first_present(item, ["forksCount", "forks", "fork"])) * 2
        )
    return max(total - rank + 1, 1)


def enrich_scores(platform: str, query: str, candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    if not candidates:
        return []
    total = len(candidates)
    for index, item in enumerate(candidates, start=1):
        item["rank"] = item.get("rank") or index
        item["raw_heat"] = raw_heat(platform, item, index, total)
    max_heat = max(float(item.get("raw_heat") or 0) for item in candidates) or 1.0
    for item in candidates:
        heat = round(60 * math.log1p(float(item.get("raw_heat") or 0)) / math.log1p(max_heat))
        relevance = text_relevance(query, item.get("title"), item.get("summary"), item.get("tags"))
        fresh = freshness_score(first_present(item, ["published_at", "updatedAt", "updated_at", "time", "date"]))
        penalty = risk_penalty(item.get("title"), item.get("summary"))
        total_score = max(0, min(100, heat + relevance + fresh - penalty))
        item["heat_score"] = heat
        item["relevance_score"] = relevance
        item["freshness_score"] = fresh
        item["risk_penalty"] = penalty
        item["metadata_score"] = total_score
    return sorted(candidates, key=lambda x: (int(x.get("metadata_score") or 0), float(x.get("raw_heat") or 0)), reverse=True)


def candidate_reason(item: dict[str, object], selected: bool) -> str:
    heat = item.get("heat_score", 0)
    relevance = item.get("relevance_score", 0)
    penalty = item.get("risk_penalty", 0)
    if selected:
        return f"入选：热度分 {heat}，相关性分 {relevance}，风险扣分 {penalty}。"
    return f"未入选：综合得分 {item.get('metadata_score', 0)}，未进入下载数量范围。"


def write_candidate_table(
    out: Path,
    platform: str,
    query: str,
    candidate_limit: int,
    download_limit: int,
    candidates: list[dict[str, object]],
    selected_urls: set[str],
) -> None:
    if not candidates:
        return
    out.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 候选评分表：{query}",
        "",
        f"- 平台: {platform}",
        f"- 候选数量: {candidate_limit}",
        f"- 下载数量: {download_limit}",
        f"- 生成时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| 状态 | 综合分 | 热度分 | 相关性 | 时间分 | 风险扣分 | 标题 | 平台数据 | 链接 | 理由 |",
        "|---|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for item in candidates:
        url = str(item.get("url") or "")
        selected = url in selected_urls
        status = "下载" if selected else "跳过"
        title = str(item.get("title") or "未命名").replace("|", "\\|")
        metrics = []
        for label, keys in [
            ("点赞", ["likes", "like", "liked_count", "点赞"]),
            ("收藏", ["collects", "favorites", "collected_count", "收藏"]),
            ("评论", ["comments", "comment_count", "评论"]),
            ("赞同", ["votes", "voteup_count", "赞同"]),
            ("stars", ["stargazersCount", "stars"]),
            ("forks", ["forksCount", "forks"]),
            ("排名", ["rank"]),
        ]:
            value = first_present(item, keys)
            if value not in (None, ""):
                metrics.append(f"{label}:{value}")
        reason = candidate_reason(item, selected).replace("|", "\\|")
        lines.append(
            f"| {status} | {item.get('metadata_score', 0)} | {item.get('heat_score', 0)} | "
            f"{item.get('relevance_score', 0)} | {item.get('freshness_score', 0)} | "
            f"{item.get('risk_penalty', 0)} | {title} | {'; '.join(metrics)} | {url} | {reason} |"
        )
    (out / SCORE_FILENAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def dedupe_candidates(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    out: list[dict[str, object]] = []
    for item in candidates:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def list_media_files(media_dir: Path, md_path: Path) -> list[Path]:
    if not media_dir.exists():
        return []
    suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".m4v"}
    files = [p for p in media_dir.rglob("*") if p.is_file() and p.suffix.lower() in suffixes]
    return sorted(files)


def image_data_uri(path: Path) -> str | None:
    data_bytes = path.read_bytes()
    if data_bytes.startswith(b"\xff\xd8"):
        mime = "image/jpeg"
    elif data_bytes.startswith(b"\x89PNG"):
        mime = "image/png"
    elif data_bytes.startswith(b"RIFF") and b"WEBP" in data_bytes[:20]:
        mime = "image/webp"
    elif data_bytes.startswith(b"GIF"):
        mime = "image/gif"
    else:
        mime_by_suffix = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        mime = mime_by_suffix.get(path.suffix.lower())
    if not mime or not data_bytes:
        return None
    data = base64.b64encode(data_bytes).decode("ascii")
    return f"data:{mime};base64,{data}"


def image_data_uri_from_url(url: str, timeout: int = 20) -> str | None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.xiaohongshu.com/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    except Exception:
        return None
    if not content:
        return None
    if content_type not in {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}:
        if content.startswith(b"\xff\xd8"):
            content_type = "image/jpeg"
        elif content.startswith(b"\x89PNG"):
            content_type = "image/png"
        elif content.startswith(b"RIFF") and b"WEBP" in content[:20]:
            content_type = "image/webp"
        elif content.startswith(b"GIF"):
            content_type = "image/gif"
        else:
            return None
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    data = base64.b64encode(content).decode("ascii")
    return f"data:{content_type};base64,{data}"


def normalize_image_key(url: str) -> str:
    clean = url.replace("\\u002F", "/")
    clean = clean.split("?")[0]
    clean = clean.split("!")[0]
    return clean.rstrip("/")


def extract_json_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if stripped.startswith(("{", "[")):
        return stripped
    start_positions = [pos for pos in [stripped.find("{"), stripped.find("[")] if pos >= 0]
    if not start_positions:
        return stripped
    return stripped[min(start_positions):]


def xhs_extract_image_urls(url: str, session: str) -> list[str]:
    js = r'''
(() => {
  const seen = new Set();
  const urls = [];
  const add = (u) => {
    if (!u || typeof u !== "string") return;
    u = u.replace(/\\u002F/g, "/");
    if (!/^https?:\/\//.test(u)) return;
    if (!/(xhscdn|xiaohongshu|sns-webpic|ci\.xiaohongshu)/.test(u)) return;
    if (/(avatar|static|icon|logo|emoji|picasso-static)/.test(u)) return;
    if (!/(notes_pre_post|spectrum|sns-webpic|ci\.xiaohongshu|imageView2|format\/webp|format\/jpg)/.test(u)) return;
    const key = u.split("?")[0].split("!")[0];
    if (seen.has(key)) return;
    seen.add(key);
    urls.push(u);
  };
  const walk = (x, depth = 0) => {
    if (!x || depth > 9) return;
    if (typeof x === "string") { add(x); return; }
    if (Array.isArray(x)) { x.forEach(v => walk(v, depth + 1)); return; }
    if (typeof x === "object") {
      for (const [k, v] of Object.entries(x)) {
        if (/image|img|url|cover|trace|file|info|list|note/i.test(k) || typeof v === "string" || Array.isArray(v)) {
          walk(v, depth + 1);
        }
      }
    }
  };
  walk(window.__INITIAL_STATE__);
  Array.from(document.images).forEach(img => add(img.currentSrc || img.src || img.getAttribute("data-src") || ""));
  return JSON.stringify(urls);
})()
'''
    run_opencli(["browser", session, "open", url], timeout=60, retries=1)
    run_opencli(["browser", session, "wait", "time", "2"], timeout=15, retries=0)
    urls: list[str] = []
    seen: set[str] = set()
    for _ in range(8):
        code, text = run_opencli(["browser", session, "eval", js], timeout=40, retries=1)
        if code == 0:
            try:
                batch = json.loads(extract_json_text(text))
            except Exception:
                batch = []
            for image_url in batch:
                key = normalize_image_key(str(image_url))
                if key and key not in seen:
                    seen.add(key)
                    urls.append(str(image_url))
        run_opencli(["browser", session, "keys", "ArrowRight"], timeout=15, retries=0)
        run_opencli(["browser", session, "wait", "time", "1"], timeout=15, retries=0)
    run_opencli(["browser", session, "close"], timeout=15, retries=0)
    return urls


def xhs_supplement_image_data_uris(url: str, existing_files: list[Path]) -> list[str]:
    session = f"xhsimg{os.getpid()}{int(time.time())}"
    image_urls = xhs_extract_image_urls(url, session)
    existing_keys = {normalize_image_key(path.stem) for path in existing_files}
    uris: list[str] = []
    seen: set[str] = set()
    for image_url in image_urls:
        key = normalize_image_key(image_url)
        if not key or key in seen:
            continue
        seen.add(key)
        uri = image_data_uri_from_url(image_url)
        if uri:
            uris.append(uri)
    return uris


def search_weixin_candidates(query: str, candidate_limit: int) -> list[dict[str, object]]:
    code, text = run_opencli(["weixin", "search", query, "--limit", str(candidate_limit), "-f", "json"], timeout=120, retries=2)
    if code != 0:
        return []
    data = json.loads(text or "[]")
    candidates = []
    for index, item in enumerate(data, start=1):
        candidates.append({
            "platform": "weixin",
            "rank": index,
            "title": first_present(item, ["title", "name"], "微信公众号文章"),
            "url": first_present(item, ["url", "link"]),
            "author": first_present(item, ["author", "account", "source", "公众号"]),
            "summary": first_present(item, ["summary", "digest", "description", "content"]),
            "published_at": first_present(item, ["date", "time", "published_at"]),
        })
    return dedupe_candidates(candidates)


def collect_weixin(raw: str, limit: int, name: str, candidate_limit: int) -> tuple[int, str, Path]:
    items = split_inputs(raw)
    first = items[0]
    out_name = name or f"微信-{slug(first)}"
    candidates: list[dict[str, object]] = []
    if not all_urls(items):
        candidates = enrich_scores("weixin", first, search_weixin_candidates(first, candidate_limit))
    collect_input = raw if all_urls(items) else first
    code, output = run([str(COLLECT), collect_input, "--limit", str(limit), "--name", out_name], timeout=300)
    match = re.search(r"输出目录：(.+)", output)
    out = Path(match.group(1).strip()) if match else output_dir("微信", first, out_name)
    if candidates:
        selected_urls = {str(item.get("url")) for item in candidates[:limit] if item.get("url")}
        write_candidate_table(out, "公众号", first, candidate_limit, limit, candidates, selected_urls)
    return code, output, out


def xiaohongshu_search_candidates(query: str, candidate_limit: int) -> list[dict[str, object]]:
    code, text = run_opencli(["xiaohongshu", "search", query, "--limit", str(candidate_limit), "-f", "json"], timeout=120, retries=2)
    if code != 0:
        raise RuntimeError(text)
    data = json.loads(text or "[]")
    candidates: list[dict[str, object]] = []
    for index, item in enumerate(data, start=1):
        url = str(first_present(item, ["url", "link"]))
        candidate = {
            "platform": "xiaohongshu",
            "rank": index,
            "title": first_present(item, ["title", "name"], "小红书笔记"),
            "url": url,
            "author": first_present(item, ["author", "nickname", "user"]),
            "summary": first_present(item, ["content", "summary", "desc", "description"]),
            "likes": first_present(item, ["likes", "like", "liked_count", "点赞"]),
            "collects": first_present(item, ["collects", "favorites", "collected_count", "收藏"]),
            "comments": first_present(item, ["comments", "comment_count", "评论"]),
            "tags": first_present(item, ["tags"]),
        }
        candidates.append(candidate)
    return dedupe_candidates(candidates)


def collect_xiaohongshu(raw: str, limit: int, name: str, candidate_limit: int) -> tuple[int, str, Path]:
    items = split_inputs(raw)
    query = items[0]
    out = output_dir("小红书", query, name)
    out.mkdir(parents=True, exist_ok=True)

    candidates: list[dict[str, object]] = []
    if all_urls(items):
        urls = items[:limit]
    else:
        try:
            candidates = enrich_scores("xiaohongshu", query, xiaohongshu_search_candidates(query, candidate_limit))
        except Exception as exc:
            return 1, f"小红书候选搜索失败：{exc}", out
        urls = [str(item.get("url", "")) for item in candidates if item.get("url")][:limit]
        write_candidate_table(out, "小红书", query, candidate_limit, limit, candidates, set(urls))

    for url in urls:
        code, text = run_opencli(["xiaohongshu", "note", url, "-f", "json"], timeout=120, retries=2)
        if code != 0:
            continue
        fields = {str(item.get("field")): item.get("value", "") for item in json.loads(text or "[]")}
        title = str(fields.get("title") or "小红书笔记")
        media_dir = out / f"{slug(title, 48)}-media"
        media_dir.mkdir(parents=True, exist_ok=True)
        run_opencli(["xiaohongshu", "download", url, "--output", str(media_dir), "-f", "json"], timeout=180, retries=2)

        meta = {
            "平台": "小红书",
            "作者": fields.get("author"),
            "点赞": fields.get("likes"),
            "收藏": fields.get("collects"),
            "评论": fields.get("comments"),
            "标签": fields.get("tags"),
            "来源": url,
        }
        md_path = unique_path(out, title)
        media_files = list_media_files(media_dir, md_path)
        supplement_uris = xhs_supplement_image_data_uris(url, media_files)
        body = str(fields.get("content") or "")
        if media_files or supplement_uris:
            body += "\n\n## 图片/视频\n\n"
            seen_image_hashes: set[str] = set()
            local_image_uris: list[str] = []
            video_lines: list[str] = []
            for media_file in media_files:
                uri = image_data_uri(media_file)
                if uri:
                    local_image_uris.append(uri)
                else:
                    video_lines.append(f"- 视频文件未内嵌：{media_file.name}\n")
            # If the browser-state supplement finds at least as many images as
            # OpenCLI's DOM downloader, prefer it to avoid duplicate low/high
            # quality variants of the same carousel image.
            image_uris = supplement_uris if len(supplement_uris) >= len(local_image_uris) else local_image_uris
            for uri in image_uris:
                digest = hashlib.sha1(uri.encode("ascii", errors="ignore")).hexdigest()
                if digest not in seen_image_hashes:
                    seen_image_hashes.add(digest)
                    body += f"![]({uri})\n\n"
            for line in video_lines:
                body += line
        write_md(md_path, title, meta, body)
        shutil.rmtree(media_dir, ignore_errors=True)

    return (0 if count_article_md(out) else 1), f"采集完成：{count_article_md(out)} 篇小红书笔记\n输出目录：{out}\n", out


def zhihu_id_from_url(url: str) -> tuple[str, str]:
    if "zhuanlan.zhihu.com/p/" in url:
        return "article", url
    match = re.search(r"zhihu\.com/question/(\d+)", url)
    if match:
        return "question", match.group(1)
    return "unknown", url


def zhihu_search_candidates(query: str, candidate_limit: int) -> list[dict[str, object]]:
    code, text = run_opencli(["zhihu", "search", query, "--limit", str(candidate_limit), "-f", "json"], timeout=120, retries=2)
    if code != 0:
        raise RuntimeError(text)
    data = json.loads(text or "[]")
    candidates = []
    for index, item in enumerate(data, start=1):
        candidates.append({
            "platform": "zhihu",
            "rank": index,
            "title": first_present(item, ["title", "question_title"], "知乎素材"),
            "url": first_present(item, ["url", "link"]),
            "type": first_present(item, ["type"]),
            "author": first_present(item, ["author", "author_name"]),
            "summary": first_present(item, ["summary", "excerpt", "content", "description"]),
            "votes": first_present(item, ["votes", "voteup_count", "赞同"]),
            "comments": first_present(item, ["comments", "comment_count", "评论"]),
            "favorites": first_present(item, ["favorites", "收藏"]),
            "published_at": first_present(item, ["date", "time", "published_at"]),
        })
    return dedupe_candidates(candidates)


def collect_zhihu(raw: str, limit: int, name: str, candidate_limit: int) -> tuple[int, str, Path]:
    items = split_inputs(raw)
    query = items[0]
    out = output_dir("知乎", query, name)
    out.mkdir(parents=True, exist_ok=True)

    candidates: list[dict[str, object]] = []
    if all_urls(items):
        results = [{"url": item, "title": item, "type": zhihu_id_from_url(item)[0]} for item in items[:limit]]
    else:
        try:
            candidates = enrich_scores("zhihu", query, zhihu_search_candidates(query, candidate_limit))
        except Exception as exc:
            return 1, f"知乎候选搜索失败：{exc}", out
        results = candidates[:limit]
        write_candidate_table(out, "知乎", query, candidate_limit, limit, candidates, {str(item.get("url")) for item in results})

    for item in results:
        url = str(item.get("url", ""))
        typ = str(item.get("type", ""))
        title = str(item.get("title", "知乎素材"))
        if "zhuanlan.zhihu.com/p/" in url or typ == "article":
            code, text = run_opencli(["zhihu", "download", "--url", url, "--output", str(out), "--download-images", "true", "-f", "json"], timeout=180, retries=2)
            if code == 0 and count_md(out):
                inline_markdown_images(out)
                continue
        kind, target = zhihu_id_from_url(url)
        if kind == "question":
            code, text = run_opencli(["zhihu", "question", target, "--limit", "3", "-f", "json"], timeout=120, retries=2)
            if code != 0:
                continue
            answers = json.loads(text or "[]")
            body = "\n\n".join(
                f"## 回答 {a.get('rank', '')}：{a.get('author', '')}\n\n赞同：{a.get('votes', '')}\n\n{a.get('content', '')}"
                for a in answers
            )
            write_md(unique_path(out, title), title, {"平台": "知乎", "类型": "question", "来源": url}, body)
            inline_markdown_images(out)
        else:
            write_md(unique_path(out, title), title, {"平台": "知乎", "类型": typ, "作者": item.get("author"), "赞同": item.get("votes"), "来源": url}, "")

    return (0 if count_article_md(out) else 1), f"采集完成：{count_article_md(out)} 篇知乎素材\n输出目录：{out}\n", out


def github_repo_from_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if "github.com" in parsed.netloc and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return None


def github_search_candidates(query: str, candidate_limit: int) -> list[dict[str, object]]:
    code, text = run([
        "gh", "search", "repos", query,
        "--limit", str(candidate_limit),
        "--json", "fullName,description,stargazersCount,forksCount,url,updatedAt,language",
    ], timeout=120)
    if code != 0 and "Unknown JSON field" in text:
        code, text = run([
            "gh", "search", "repos", query,
            "--limit", str(candidate_limit),
            "--json", "fullName,description,stargazersCount,url,updatedAt,language",
        ], timeout=120)
    if code != 0:
        raise RuntimeError(text)
    data = json.loads(text or "[]")
    candidates = []
    for index, item in enumerate(data, start=1):
        candidates.append({
            "platform": "github",
            "rank": index,
            "title": first_present(item, ["fullName"], "GitHub 仓库"),
            "url": first_present(item, ["url"]),
            "summary": first_present(item, ["description"]),
            "stargazersCount": first_present(item, ["stargazersCount"]),
            "forksCount": first_present(item, ["forksCount"]),
            "updatedAt": first_present(item, ["updatedAt"]),
            "language": first_present(item, ["language"]),
        })
    return dedupe_candidates(candidates)


def collect_github(raw: str, limit: int, name: str, candidate_limit: int) -> tuple[int, str, Path]:
    items = split_inputs(raw)
    query = items[0]
    out = output_dir("GitHub", query, name)
    out.mkdir(parents=True, exist_ok=True)

    repos: list[str] = []
    candidates: list[dict[str, object]] = []
    if all_urls(items):
        repos = [repo for item in items if (repo := github_repo_from_url(item))][:limit]
    else:
        try:
            candidates = enrich_scores("github", query, github_search_candidates(query, candidate_limit))
        except Exception as exc:
            return 1, f"GitHub 候选搜索失败：{exc}", out
        selected = candidates[:limit]
        repos = [str(item.get("title")) for item in selected if item.get("title")]
        write_candidate_table(out, "GitHub", query, candidate_limit, limit, candidates, {str(item.get("url")) for item in selected})

    for repo in repos:
        code, text = run(["gh", "repo", "view", repo], timeout=120)
        if code != 0:
            continue
        write_md(unique_path(out, repo.replace("/", "-")), repo, {"平台": "GitHub", "仓库": repo, "来源": f"https://github.com/{repo}"}, text)

    return (0 if count_article_md(out) else 1), f"采集完成：{count_article_md(out)} 个 GitHub 仓库素材\n输出目录：{out}\n", out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一素材采集：微信、小红书、知乎、GitHub。")
    parser.add_argument("--platform", required=True, choices=["weixin", "xiaohongshu", "zhihu", "github"])
    parser.add_argument("--input", required=True, help="关键词，或多行链接。")
    parser.add_argument("--limit", type=int, default=3, help="最终下载数量。")
    parser.add_argument("--candidate-limit", type=int, default=10, help="关键词模式下先查看的候选数量。")
    parser.add_argument("--name", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    LIBRARY.mkdir(parents=True, exist_ok=True)
    limit = max(1, args.limit)
    candidate_limit = max(limit, args.candidate_limit)
    if args.platform == "weixin":
        code, output, out = collect_weixin(args.input, limit, args.name, candidate_limit)
    elif args.platform == "xiaohongshu":
        code, output, out = collect_xiaohongshu(args.input, limit, args.name, candidate_limit)
    elif args.platform == "zhihu":
        code, output, out = collect_zhihu(args.input, limit, args.name, candidate_limit)
    else:
        code, output, out = collect_github(args.input, limit, args.name, candidate_limit)

    print(output.strip())
    inline_markdown_images(out)
    print(f"输出目录：{out}")
    print(f"成功文件：{count_article_md(out)}")
    if (out / SCORE_FILENAME).exists():
        print(f"候选评分表：{out / SCORE_FILENAME}")
    print(f"内嵌图片：{count_embedded_images(out)}")
    if count_article_md(out) == 0:
        shutil.rmtree(out, ignore_errors=True)
        print("失败原因：没有成功保存 Markdown。")
        return code or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
