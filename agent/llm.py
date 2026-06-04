"""LLM 统一封装：DashScope/千问 OpenAI 兼容端点。

设计原则：
1. 缺 key / AGENT_MOCK=1 / openai 包未装 → 全部走 mock，永不崩
2. 两个对外函数：chat_json(system, user) → dict, chat_text(system, user) → str
3. 自动加载 .env（如果有 python-dotenv），否则依赖 shell 已 export
4. 模型/base_url/api_key 全从环境变量取，与 采集工作台/scripts/analyze.py 共享同一份配置
5. 调用层不知道是真 LLM 还是 mock —— mock 返回会带 `_mock: True` 标记

环境变量：
    DASHSCOPE_API_KEY  阿里云百炼 API key（必填，否则走 mock）
    LLM_MODEL          默认 qwen-plus
    LLM_BASE_URL       默认 https://dashscope.aliyuncs.com/compatible-mode/v1
    AGENT_MOCK         设为 1 强制走 mock（即使有 key）
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---- 自动加载 .env（如有 python-dotenv 则用，否则简单读取）----
def _autoload_env() -> None:
    """优先用 python-dotenv，否则简单解析项目根 .env。"""
    if os.environ.get("DASHSCOPE_API_KEY"):
        return  # 已经在环境里，不重复加载
    project_root = Path(__file__).resolve().parents[1]
    env_file = project_root / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(env_file)
        return
    except ImportError:
        pass
    # 简单 fallback：手动解析 KEY=VALUE
    try:
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except OSError:
        pass


_autoload_env()


DEFAULT_MODEL = "qwen-plus"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _is_mock_forced() -> bool:
    return os.environ.get("AGENT_MOCK", "") in ("1", "true", "True", "yes")


def _api_key() -> str:
    return (os.environ.get("DASHSCOPE_API_KEY") or "").strip()


def _model() -> str:
    return os.environ.get("LLM_MODEL", "").strip() or DEFAULT_MODEL


def _base_url() -> str:
    return os.environ.get("LLM_BASE_URL", "").strip() or DEFAULT_BASE_URL


def has_llm() -> bool:
    """是否能调真 LLM（已加载 key 且未强制 mock 且 openai 已安装）。"""
    if _is_mock_forced():
        return False
    if not _api_key():
        return False
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False


def _client():
    """构造 OpenAI 兼容客户端。调用方需先 has_llm() 确认。"""
    from openai import OpenAI
    return OpenAI(api_key=_api_key(), base_url=_base_url())


def _extract_json(text: str) -> dict:
    """容错解析 LLM 返回的 JSON 文本。"""
    text = (text or "").strip()
    if "```" in text:
        # 剥掉 markdown 围栏
        if "```json" in text:
            text = text.split("```json", 1)[-1]
        text = text.split("```", 1)[0].strip()
        if not text:
            return {"_raw": "(空)"}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text[:500], "_parse_error": True}


def chat_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    mock_fallback: dict | None = None,
) -> dict:
    """LLM 结构化输出：返回 dict。

    mock 模式或调用失败时返回 mock_fallback（默认 {"_mock": True}）。
    system 提示词必须包含 "json" 字样（DashScope 限制），否则会自动追加。
    """
    fallback: dict[str, Any] = dict(mock_fallback or {"_mock": True})

    if not has_llm():
        return fallback

    # DashScope 的 response_format json_object 要求 system 含 "json"
    if "json" not in system.lower():
        system = system + "\n请严格按 JSON 格式输出。"

    try:
        resp = _client().chat.completions.create(
            model=model or _model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = resp.choices[0].message.content or ""
        out = _extract_json(text)
        # 附带 usage 信息以便上层做 token 监控
        usage = getattr(resp, "usage", None)
        if usage is not None:
            out.setdefault("_usage", {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
            })
        return out
    except Exception as exc:  # noqa: BLE001 — LLM 失败不许影响主链路
        logger.warning("chat_json 调用失败，走 fallback：%s", exc)
        return {**fallback, "_llm_error": str(exc)[:200]}


def chat_text(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.5,
    mock_fallback: str = "",
) -> str:
    """LLM 自由文本输出：返回 str。

    mock 模式或调用失败时返回 mock_fallback。
    """
    if not has_llm():
        return mock_fallback

    try:
        resp = _client().chat.completions.create(
            model=model or _model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_text 调用失败，走 fallback：%s", exc)
        return mock_fallback


if __name__ == "__main__":  # pragma: no cover
    # 自检：打印当前 LLM 配置状态
    print(f"has_llm = {has_llm()}")
    print(f"model = {_model()}")
    print(f"base_url = {_base_url()}")
    print(f"api_key_set = {bool(_api_key())}")
    print(f"mock_forced = {_is_mock_forced()}")
    # 跑一次最小调用
    if has_llm():
        out = chat_text(
            system="你是一个简短回复助手。",
            user="用一句话总结：天空为什么是蓝色的？",
            max_tokens=80,
        )
        print(f"\n[LLM 自检输出]\n{out}")
    else:
        print("\n（mock 模式，跳过实际调用）")
