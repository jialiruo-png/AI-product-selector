#!/usr/bin/env python3
"""TikHub API 连通性探测脚本（仅测试用）。

依次验证：账户信息、小红书搜索、小红书图文详情、图片下载。
key 从环境变量 TIKHUB_API_KEY 或项目根 .env 读取。
用法：
    python3 采集工作台/scripts/tikhub_probe.py "AI教育"
"""
from __future__ import annotations

import os
import sys
import json
import urllib.parse
import urllib.request
from pathlib import Path


# 中国大陆用 .dev，海外可改为 .io
BASE = os.environ.get("TIKHUB_BASE", "https://api.tikhub.dev")
ROOT = Path(__file__).resolve().parents[2]


def load_api_key() -> str:
    """从环境变量或项目根 .env 读取 TIKHUB_API_KEY。"""
    key = os.environ.get("TIKHUB_API_KEY", "").strip()
    if key:
        return key
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("TIKHUB_API_KEY"):
                return line.split("=", 1)[-1].strip().strip('"').strip()
    return ""


def call(path: str, params: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


API_KEY = load_api_key()


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "AI教育"
    if not API_KEY:
        print("未找到 key，请在项目根 .env 写入 TIKHUB_API_KEY=你的真实key")
        return 1
    print(f"key 前缀 {API_KEY[:6]}... 长度 {len(API_KEY)}\n")

    # 1. 账户信息
    info = call("/api/v1/tikhub/user/get_user_info")
    print("1) 账户信息 code:", info.get("code"),
          "| 名称:", info.get("api_key_data", {}).get("api_key_name"))

    # 2. 小红书搜索（App 端，web_v3 上游易故障）
    s = call("/api/v1/xiaohongshu/app/search_notes",
             {"keyword": keyword, "page": 1, "sort": "general", "noteType": "_0"})
    items = [it["note"] for it in s.get("data", {}).get("data", {}).get("items", [])
             if it.get("model_type") == "note" and it.get("note", {}).get("id")]
    print(f"2) 小红书搜索 code: {s.get('code')} | 命中 {len(items)} 条")
    if not items:
        return 1

    first = items[0]
    note_id, xsec = first["id"], first["xsec_token"]
    title = first.get("title", "")
    print(f"   首条: {title}  note_id={note_id}")

    # 3. 图文详情
    detail = call("/api/v1/xiaohongshu/web_v3/fetch_note_detail",
                  {"note_id": note_id, "xsec_token": xsec})
    nc = detail.get("data", {}).get("data", {}).get("items", [{}])[0].get("noteCard", {})
    imgs = nc.get("imageList", [])
    print(f"3) 图文详情 code: {detail.get('code')} | 正文 {len(nc.get('desc',''))} 字 | 图片 {len(imgs)} 张")
    print(f"   标签: {[t.get('name') for t in nc.get('tagList', [])]}")
    print(f"   互动: {nc.get('interactInfo')}")

    # 4. 图片下载
    if imgs:
        img_url = imgs[0].get("urlDefault") or imgs[0].get("infoList", [{}])[-1].get("url")
        with urllib.request.urlopen(img_url, timeout=30) as r:
            blob = r.read()
        print(f"4) 图片下载 {len(blob)} 字节 | {r.headers.get('content-type')}")

    print("\n全链路连通 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
