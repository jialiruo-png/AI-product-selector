"""TikHub HTTP 客户端 + .env 加载 + 嵌套字典访问。被 probe / collect / select 共用。"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DEFAULT = "https://api.tikhub.dev"
# 没有 UA 时 Cloudflare 会回 403
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class TikHubError(Exception):
    pass


def load_env(root: Path) -> None:
    """读取项目根 .env 写入 os.environ；已存在的环境变量不覆盖。"""
    env = root / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def dig(obj, path: str, default=None):
    """按 'a.b.0.c' 形式从嵌套结构里取值，任意一层缺失返回 default。"""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return default
        if part.isdigit() and isinstance(cur, list):
            i = int(part)
            cur = cur[i] if 0 <= i < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return default
    return cur if cur is not None else default


class TikHubClient:
    def __init__(self, api_key: str | None = None, base: str | None = None):
        self.api_key = (api_key or os.environ.get("TIKHUB_API_KEY", "")).strip()
        if not self.api_key:
            raise TikHubError("缺少 TIKHUB_API_KEY，请在项目根 .env 设置")
        self.base = (base or os.environ.get("TIKHUB_BASE", BASE_DEFAULT)).rstrip("/")

    def call(self, path: str, params: dict | None = None, *,
             retries: int = 3, timeout: int = 60) -> dict:
        """成功返回原始响应 dict；失败抛 TikHubError。
        部分电商端点上游会间歇性回 400 'Please retry'（不扣费），自动重试。"""
        url = f"{self.base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": UA,
            "Accept": "application/json",
        })
        last_err: TikHubError | None = None
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "ignore")[:300]
                last_err = TikHubError(f"HTTP {exc.code} on {path}: {body}")
                if exc.code == 400 and attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise last_err
            except Exception as exc:  # noqa: BLE001
                last_err = TikHubError(f"{type(exc).__name__} on {path}: {exc}")
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise last_err
        raise last_err or TikHubError("unknown error")

    def ping(self) -> dict:
        return self.call("/api/v1/tikhub/user/get_user_info")
