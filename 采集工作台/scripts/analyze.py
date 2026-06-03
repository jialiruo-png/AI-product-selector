"""LLM 情感与痛点分析：默认调阿里千问（DashScope OpenAI 兼容端点）。

为什么走 OpenAI 兼容：千问 / DeepSeek / 智谱 / Kimi 全部支持 OpenAI 兼容协议，
切其他厂商只改 .env 的 LLM_BASE_URL + LLM_MODEL + key 即可，代码不动。

环境变量：
    DASHSCOPE_API_KEY   阿里云百炼 API key（必填）
    LLM_MODEL           默认 qwen-plus；可换 qwen-turbo / qwen-max / qwen3-*
    LLM_BASE_URL        默认 https://dashscope.aliyuncs.com/compatible-mode/v1
"""
from __future__ import annotations

import json
import os

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment]

DEFAULT_MODEL = "qwen-plus"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# system 里必须出现 "json" 字样，千问 response_format=json_object 才会触发
SYSTEM = """你是电商选品分析助手。给定一组同一商品（或同一关键词）的真实用户评论，输出严格 JSON：
{
  "sentiment": {"positive": <0-1>, "neutral": <0-1>, "negative": <0-1>},
  "pain_points": [{"label": "<痛点短语，<=8字>", "freq": <出现次数>, "example": "<一条原文摘录，<=40字>"}],
  "highlights":  [{"label": "<好评点短语，<=8字>", "freq": <出现次数>, "example": "<一条原文摘录，<=40字>"}]
}
约束：
- 只输出 JSON，不要任何额外文字、不要 markdown 围栏。
- sentiment 三项加和=1，按文本判断；无文字仅星级时按星级估计（≥4=positive，3=neutral，≤2=negative）。
- pain_points 与 highlights 各不超过 8 条；按 freq 降序；label 应是名词性短语而非整句。
- 痛点要具体可执行（如"易碎"/"色差大"），避免空泛（如"不好"）。"""


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if "```" in text:
        text = text.split("```json", 1)[-1].split("```", 1)[0].strip()
        if not text:
            text = "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text[:500]}


def _degraded_by_rating(reviews: list[dict], stats: dict) -> dict:
    """无文字评论时按星级朴素估计，省一次 LLM 调用。"""
    ratings = [r.get("rating") for r in reviews if r.get("rating")]
    if not ratings:
        return {"sentiment": {}, "pain_points": [], "highlights": [],
                "_stats": {**stats, "_note": "无任何评论数据"}}
    pos = sum(1 for x in ratings if x and x >= 4) / len(ratings)
    neu = sum(1 for x in ratings if x == 3) / len(ratings)
    neg = sum(1 for x in ratings if x and x <= 2) / len(ratings)
    return {"sentiment": {"positive": round(pos, 2),
                          "neutral": round(neu, 2),
                          "negative": round(neg, 2)},
            "pain_points": [], "highlights": [],
            "_stats": {**stats, "_note": "仅星级，无文字"}}


def analyze_reviews(reviews: list[dict], *,
                    model: str | None = None,
                    max_reviews: int = 80) -> dict:
    """reviews: [{rating?, text, ...}]。返回 {sentiment, pain_points, highlights, _stats}。"""
    items = [r for r in reviews if (r.get("text") or "").strip()][:max_reviews]
    stats = {"input_count": len(reviews), "with_text": len(items)}
    if not items:
        return _degraded_by_rating(reviews, stats)

    if OpenAI is None:
        raise RuntimeError("缺少 openai 包：pip install -r requirements.txt")
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY，请在项目根 .env 设置（千问 / 阿里云百炼 key）")
    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)

    client = OpenAI(api_key=api_key, base_url=base_url)
    payload = "\n".join(
        f"[{r.get('rating', '?')}★] {(r.get('text') or '').strip()[:200]}"
        for r in items
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": payload},
        ],
        response_format={"type": "json_object"},
        max_tokens=2048,
        temperature=0.3,
    )
    text = resp.choices[0].message.content or ""
    out = _extract_json(text)
    usage = getattr(resp, "usage", None)
    out["_stats"] = {
        **stats,
        "model": model,
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", 0),
    }
    return out
