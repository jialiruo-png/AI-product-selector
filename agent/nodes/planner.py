"""KeywordPlanner —— 入口/grounding 节点。

接收 keyword + category，产出 10~20 个精准词（keywords），
作为贯穿所有 analyzer 的全局状态。
"""
from __future__ import annotations

from .base import BaseNode


class KeywordPlanner(BaseNode):
    """精准词规划。对应 company-research 的 grounding/入口节点。"""

    name = "keyword_planner"

    async def run(self, state: dict) -> dict:
        keyword = (state.get("keyword") or "").strip()
        category = (state.get("category") or "").strip()

        # TODO: wire real LLM —— 用 keyword+category 生成 10~20 精准词。
        # 目前为 MOCK：基于 keyword 拼出一组语义扩展词。
        if not keyword:
            keywords: list[str] = []
            note = "缺少 keyword，产出空精准词"
        else:
            base = [
                keyword,
                f"{keyword}推荐",
                f"{keyword}测评",
                f"平价{keyword}",
                f"{keyword}套装",
            ]
            if category:
                base.append(f"{category}{keyword}")
            # 去重保序
            seen = set()
            keywords = [k for k in base if not (k in seen or seen.add(k))]
            note = f"产出 {len(keywords)} 个精准词"

        return {
            "keywords": keywords,
            "_trace": [self._trace_entry(note)],
        }
