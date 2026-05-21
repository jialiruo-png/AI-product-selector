#!/usr/bin/env python3
"""
Topic fetch agent for the local course-building workspace.

Given a topic, this script:
1. Builds search queries.
2. Uses local web-fetcher (`wf`) to fetch search-result markdown.
3. Extracts candidate URLs from those search results.
4. Filters and deduplicates URLs.
5. Fetches selected pages into local Markdown files.

It is intentionally conservative: serial execution, configurable delay,
no login bypass, no captcha bypass, and no high-frequency crawling.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_WF = ROOT_DIR / "web-fetcher" / ".venv" / "bin" / "wf"
WORKBENCH_DIR = ROOT_DIR / "采集工作台"


URL_RE = re.compile(r"https?://[^\s<>\")\]]+")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)]+)\)")
BING_RESULT_RE = re.compile(r'<li[^>]+class="[^"]*\bb_algo\b[^"]*"[\s\S]*?<a[^>]+href="([^"]+)"', re.I)
DDG_RESULT_RE = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"', re.I)


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def safe_slug(text: str, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", text.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("-._")
    if not cleaned:
        cleaned = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return cleaned[:max_len]


def build_search_url(query: str, engine: str, num: int = 10) -> str:
    count = max(1, min(num, 10))
    if engine == "google":
        params = urllib.parse.urlencode({"q": query, "num": count, "hl": "zh-CN"})
        return f"https://www.google.com/search?{params}"
    if engine == "duckduckgo":
        params = urllib.parse.urlencode({"q": query, "kl": "cn-zh"})
        return f"https://duckduckgo.com/html/?{params}"

    params = urllib.parse.urlencode({"q": query, "count": count, "setlang": "zh-CN"})
    return f"https://www.bing.com/search?{params}"


def build_queries(topic: str, source: str, extra_queries: list[str]) -> list[str]:
    queries: list[str] = []

    if source in ("wechat", "all"):
        queries.extend([
            f"site:mp.weixin.qq.com/s {topic}",
            f"site:mp.weixin.qq.com {topic} 人工智能教育",
        ])

    if source in ("web", "all"):
        queries.extend([
            f"{topic} 人工智能教育 课程",
            f"{topic} 机器学习 启蒙 课程",
            f"{topic} AI 通识 教育",
            f"{topic} filetype:pdf",
            f"site:github.com {topic} AI 教育",
            f"site:datawhalechina.github.io {topic}",
            f"site:edu.cn {topic} 人工智能 教育",
            f"site:moe.gov.cn {topic} 人工智能 教育",
        ])

    queries.extend(extra_queries)

    seen = set()
    result = []
    for query in queries:
        query = query.strip()
        if query and query not in seen:
            seen.add(query)
            result.append(query)
    return result


def run_command(cmd: list[str], cwd: Path, log_file: Path, timeout: int | None = None) -> tuple[int, str]:
    with log_file.open("a", encoding="utf-8") as log:
        log.write("\n$ " + " ".join(cmd) + "\n")
        log.flush()
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        log.write(proc.stdout)
        log.flush()
        return proc.returncode, proc.stdout


def normalize_candidate_url(raw_url: str) -> str | None:
    url = raw_url.strip().rstrip(".,;:，。；：")
    url = urllib.parse.unquote(url)

    parsed = urllib.parse.urlparse(url)

    # Google redirect URLs often look like /url?q=<target>.
    if "google." in parsed.netloc and parsed.path == "/url":
        target = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
        if target:
            url = target
            parsed = urllib.parse.urlparse(url)

    # DuckDuckGo redirect URLs often use /l/?uddg=<target>.
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            url = urllib.parse.unquote(target)
            parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None

    blocked_hosts = (
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
        "google.com",
        "www.google.com",
        "google.com.hk",
        "www.google.com.hk",
        "accounts.google.com",
        "support.google.com",
        "policies.google.com",
        "maps.google.com",
        "translate.google.com",
        "webcache.googleusercontent.com",
        "csp.withgoogle.com",
        "www.gstatic.com",
        "gstatic.com",
        "www.bing.com",
        "bing.com",
        "cn.bing.com",
        "duckduckgo.com",
        "www.duckduckgo.com",
        "poki.com",
        "www.poki.com",
        "4399.com",
        "www.4399.com",
        "xiaoyouxi.2345.com",
    )
    host = parsed.netloc.lower()
    if host in blocked_hosts or host.endswith(".google.com") or host.endswith(".gstatic.com"):
        return None

    asset_suffixes = (
        ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
        ".ico", ".woff", ".woff2", ".ttf", ".map",
    )
    if parsed.path.lower().endswith(asset_suffixes):
        return None

    if parsed.path.startswith("/search") or parsed.path.startswith("/images/search"):
        return None

    low_url = url.lower()
    low_path = parsed.path.lower()
    noisy_fragments = (
        "zidian", "youxi", "game", "games", "baike.baidu.com/item/小",
        "/zh/类别", "category",
    )
    if any(fragment in low_url or fragment in low_path for fragment in noisy_fragments):
        return None

    cleaned = urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        "",
        parsed.query,
        "",
    ))
    return cleaned


def extract_urls(markdown: str) -> list[str]:
    candidates = []
    candidates.extend(MD_LINK_RE.findall(markdown))
    candidates.extend(URL_RE.findall(markdown))

    seen = set()
    urls = []
    for item in candidates:
        normalized = normalize_candidate_url(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def fetch_url_text(url: str, timeout: int, log_file: Path) -> tuple[int, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset, errors="replace")
            return 0, body
    except Exception as exc:
        with log_file.open("a", encoding="utf-8") as log:
            log.write(f"\n[direct-search-error] {url}\n{type(exc).__name__}: {exc}\n")
        return 1, ""


def extract_search_result_urls(html: str, engine: str) -> list[str]:
    if engine == "bing":
        raw_urls = BING_RESULT_RE.findall(html)
    elif engine == "duckduckgo":
        raw_urls = DDG_RESULT_RE.findall(html)
    else:
        raw_urls = []

    if not raw_urls:
        raw_urls = extract_urls(html)

    seen = set()
    urls = []
    for raw in raw_urls:
        normalized = normalize_candidate_url(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def domain_matches(url: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(pattern.lower() in host for pattern in patterns)


def filter_urls(
    urls: list[str],
    source: str,
    include_domains: list[str],
    exclude_domains: list[str],
) -> list[str]:
    filtered = []
    for url in urls:
        host = urllib.parse.urlparse(url).netloc.lower()

        if source == "wechat" and "mp.weixin.qq.com" not in host:
            continue

        if include_domains and not domain_matches(url, include_domains):
            continue

        if exclude_domains and domain_matches(url, exclude_domains):
            continue

        filtered.append(url)
    return filtered


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def fetch_search_results(
    wf_bin: Path,
    queries: list[str],
    search_engine: str,
    search_dir: Path,
    log_file: Path,
    timeout: int,
) -> list[str]:
    all_urls: list[str] = []
    search_dir.mkdir(parents=True, exist_ok=True)

    for index, query in enumerate(queries, 1):
        search_url = build_search_url(query, search_engine)
        print(f"[search {index}/{len(queries)}] {search_engine}: {query}")
        output = ""
        code = 1

        if search_engine in ("bing", "duckduckgo"):
            code, output = fetch_url_text(search_url, timeout, log_file)
        else:
            code, output = run_command(
                [str(wf_bin), search_url, "--stdout", "--lite", "--timeout", str(timeout)],
                cwd=ROOT_DIR / "web-fetcher",
                log_file=log_file,
                timeout=timeout + 30,
            )

        query_file = search_dir / f"{index:02d}-{safe_slug(query)}.md"
        query_file.write_text(output, encoding="utf-8")

        if code != 0:
            print(f"  search failed, see log: {log_file}")
            continue

        if search_engine in ("bing", "duckduckgo"):
            all_urls.extend(extract_search_result_urls(output, search_engine))
        else:
            all_urls.extend(extract_urls(output))

    return all_urls


def fetch_articles(
    wf_bin: Path,
    urls: list[str],
    output_dir: Path,
    log_file: Path,
    delay: float,
    timeout: int,
    download_assets: bool,
    assets_root: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(urls)

    for index, url in enumerate(urls, 1):
        print(f"[fetch {index}/{total}] {url}")
        cmd = [str(wf_bin), url, "-o", str(output_dir), "--timeout", str(timeout)]
        if download_assets:
            cmd.extend(["--download-assets", "--assets-root", assets_root])
        code, _ = run_command(
            cmd,
            cwd=ROOT_DIR / "web-fetcher",
            log_file=log_file,
            timeout=timeout + 60,
        )
        if code != 0:
            print(f"  failed, see log: {log_file}")

        if index < total and delay > 0:
            time.sleep(delay)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search a topic, discover pages, and save fetched content as local Markdown."
    )
    parser.add_argument("topic", help="采集主题，例如：小学生 AI 启蒙 图像识别")
    parser.add_argument(
        "--source",
        choices=["web", "wechat", "all"],
        default="web",
        help="采集来源：web=普通网页，wechat=公众号搜索，all=两者都搜。默认 web。",
    )
    parser.add_argument(
        "--search-engine",
        choices=["bing", "google", "duckduckgo"],
        default="bing",
        help="搜索源，默认 bing。Google 容易触发验证码时可切回 bing。",
    )
    parser.add_argument("--limit", type=int, default=10, help="最多抓取正文页数，默认 10。")
    parser.add_argument("--delay", type=float, default=3.0, help="正文抓取间隔秒数，默认 3。")
    parser.add_argument("--timeout", type=int, default=60, help="单次 wf 超时秒数，默认 60。")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="额外搜索词，可重复传入。例如 --query 'AI启蒙 机器学习 小学生'",
    )
    parser.add_argument(
        "--include-domain",
        action="append",
        default=[],
        help="只保留包含该域名片段的链接，可重复传入。",
    )
    parser.add_argument(
        "--exclude-domain",
        action="append",
        default=[],
        help="排除包含该域名片段的链接，可重复传入。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只搜索和生成链接清单，不抓正文。")
    parser.add_argument(
        "--download-assets",
        action="store_true",
        help="下载图片到本地 assets 目录，并重写 Markdown 图片路径。",
    )
    parser.add_argument("--assets-root", default="assets", help="图片目录名，默认 assets。")
    parser.add_argument("--wf-bin", type=Path, default=DEFAULT_WF, help="wf 可执行文件路径。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wf_bin = args.wf_bin.resolve()
    if not wf_bin.exists():
        print(f"错误：找不到 wf：{wf_bin}", file=sys.stderr)
        return 1

    topic_slug = safe_slug(args.topic)
    run_dir = WORKBENCH_DIR / "topics" / f"{dt.datetime.now().strftime('%Y%m%d')}-{topic_slug}"
    search_dir = run_dir / "search-results"
    articles_dir = run_dir / "articles"
    log_file = run_dir / "agent.log"

    run_dir.mkdir(parents=True, exist_ok=True)
    queries = build_queries(args.topic, args.source, args.query)

    write_lines(run_dir / "queries.txt", queries)
    (run_dir / "topic.md").write_text(
        f"# {args.topic}\n\n"
        f"- 创建时间: {dt.datetime.now().isoformat(timespec='seconds')}\n"
        f"- 来源模式: {args.source}\n"
        f"- 搜索源: {args.search_engine}\n"
        f"- 最大抓取数: {args.limit}\n"
        f"- 抓取间隔: {args.delay}s\n",
        encoding="utf-8",
    )

    print(f"主题：{args.topic}")
    print(f"工作目录：{run_dir}")
    print(f"搜索源：{args.search_engine}")
    print(f"搜索词数量：{len(queries)}")

    discovered = fetch_search_results(wf_bin, queries, args.search_engine, search_dir, log_file, args.timeout)
    discovered = filter_urls(discovered, args.source, args.include_domain, args.exclude_domain)

    deduped = []
    seen = set()
    for url in discovered:
        if url not in seen:
            seen.add(url)
            deduped.append(url)

    selected = deduped[: max(0, args.limit)]
    write_lines(run_dir / "discovered_links.txt", deduped)
    write_lines(run_dir / "fetch_queue.txt", selected)

    print(f"发现链接：{len(deduped)}")
    print(f"计划抓取：{len(selected)}")

    if args.dry_run:
        print(f"dry-run 完成，链接清单见：{run_dir / 'fetch_queue.txt'}")
        return 0

    if not selected:
        print("没有可抓取链接。可以换关键词，或增加 --query。")
        return 0

    fetch_articles(
        wf_bin,
        selected,
        articles_dir,
        log_file,
        args.delay,
        args.timeout,
        args.download_assets,
        args.assets_root,
    )
    print(f"完成。正文 Markdown 输出在：{articles_dir}")
    print(f"日志：{log_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
