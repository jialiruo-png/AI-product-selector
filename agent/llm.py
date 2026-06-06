"""统一 LLM 抽象（B1）—— 给 agent 层节点调真实大模型用。

走 OpenAI 兼容协议，复用 .env 里的同一套配置（与 analyze.py 一致）：
    DASHSCOPE_API_KEY   厂商 key（变量名历史遗留，值可以是 DeepSeek key）
    LLM_BASE_URL        OpenAI 兼容端点
    LLM_MODEL           生成类任务模型（精准词 / 人群 / 摘要），默认走思考模式提质
    LLM_MODEL_EXTRACT   JSON 抽取类任务模型，建议非思考模型避免 token 截断

为什么独立成模块而不复用 analyze.py：
    - analyze.py 属 `采集工作台/scripts/`（禁改），且只服务"评论痛点抽取"这一固定场景
      （写死 system prompt + max_tokens=2048）。agent 层需要任意 prompt、可调 max_tokens，
      故在 agent/ 内另起一个轻量通用客户端。

健壮性约定（与全局一致）：
    - mock 模式（AGENT_MOCK=1）或缺 key / 缺包时 available() 返回 False，
      调用方据此回退到 mock 文案，整条 graph 永不崩。
    - chat_*() 调用失败一律返回 None（不抛），调用方回退 mock。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # openai 未装时整层降级到 mock
    OpenAI = None  # type: ignore[assignment]

# DeepSeek 默认端点；.env 里 LLM_BASE_URL 会覆盖
_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-v4-pro"

# 项目根（agent/ 的上一级），用于加载 .env
_ROOT = Path(__file__).resolve().parents[1]

_env_loaded = False


def _load_env_once() -> None:
    """惰性加载项目根 .env（复用采集脚本的 load_env，不覆盖已有环境变量）。"""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    try:
        import sys
        scripts = _ROOT / "采集工作台" / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import _tikhub_client as tk  # type: ignore
        tk.load_env(_ROOT)
    except Exception:  # noqa: BLE001  加载失败不致命，后续 available() 会判 key
        pass


def _is_mock() -> bool:
    return os.getenv("AGENT_MOCK", "").strip().lower() in {"1", "true", "yes", "on"}


def _api_key() -> str:
    _load_env_once()
    return os.environ.get("DASHSCOPE_API_KEY", "").strip()


def available() -> bool:
    """是否可调真实 LLM：非 mock、装了 openai、配了 key。"""
    if _is_mock() or OpenAI is None:
        return False
    return bool(_api_key())


def _client() -> Any:
    base_url = os.environ.get("LLM_BASE_URL", "").strip() or _DEFAULT_BASE_URL
    return OpenAI(api_key=_api_key(), base_url=base_url)


def _gen_model() -> str:
    return os.environ.get("LLM_MODEL", "").strip() or _DEFAULT_MODEL


def _extract_model() -> str:
    # 抽取类优先用 LLM_MODEL_EXTRACT（非思考，防 token 截断），缺省回退生成模型
    return os.environ.get("LLM_MODEL_EXTRACT", "").strip() or _gen_model()


def chat_text(system: str, user: str, *,
              max_tokens: int = 1024, temperature: float = 0.6) -> str | None:
    """自由文本生成（人群洞察 / 简报 / 报告润色）。失败返回 None。"""
    if not available():
        return None
    try:
        resp = _client().chat.completions.create(
            model=_gen_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:  # noqa: BLE001  调用失败 -> 调用方回退 mock
        return None


def _extract_json_text(text: str) -> Any:
    """从模型输出里抠 JSON：去 markdown 围栏后 json.loads，失败返回 None。"""
    text = (text or "").strip()
    if "```" in text:
        # 取第一对围栏内的内容
        body = text.split("```json", 1)[-1] if "```json" in text else text.split("```", 1)[-1]
        text = body.split("```", 1)[0].strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def chat_json(system: str, user: str, *,
              max_tokens: int = 1024, temperature: float = 0.3) -> Any | None:
    """结构化 JSON 抽取（精准词列表 / 结构化人群）。失败或解析失败返回 None。

    用 LLM_MODEL_EXTRACT（非思考模型），并要求 system 里含 'json' 字样以触发
    response_format=json_object（与 analyze.py 同款约束）。
    """
    if not available():
        return None
    try:
        resp = _client().chat.completions.create(
            model=_extract_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return _extract_json_text(resp.choices[0].message.content or "")
    except Exception:  # noqa: BLE001
        return None
