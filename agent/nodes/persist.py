"""落库节点（B3）：把一次选品结果写进 SQLite，供趋势复盘。

位置：fan-in 之后、Briefing 之前（此时 PriceAnalyzer 的 products 与
CompetitorAnalyzer 的 review_raw 都已合并就绪），单点串行落库，无并行竞态。

落库内容（经已注册 snapshot_write 工具，复用 db.py，不直接 import db）：
    - runs            ：本次跑的元信息（新建一条，拿到 run_id）
    - products        ：打分后的商品快照
    - reviews         ：Top 商品原始评论（按商品 id）
    - pain_points     ：评论痛点 / 亮点（按商品 id）

铁律：mock 模式（AGENT_MOCK=1 / --mock）或缺商品数据时直接跳过，不触库、不崩。
"""
from __future__ import annotations

from typing import Any

from agent.state import new_evidence_ref

from .base import BaseNode, get_tool, is_mock


class Persist(BaseNode):
    """把 products + reviews + pain_points 落库，并把 run_id 透传进 state。"""

    name = "persist"

    async def run(self, state: dict) -> dict:
        products = list(state.get("products") or [])
        review_raw = list(state.get("review_raw") or [])
        keyword = state.get("keyword") or ""
        region = state.get("region") or "CN"
        db_path = state.get("db_path")  # None => snapshot_write 内部用 db.DEFAULT_DB

        snapshot = get_tool("snapshot_write")

        # mock / 缺工具 / 缺商品：不落库（mock 永不崩）
        if is_mock() or snapshot is None or not products:
            reason = "mock 跳过落库" if is_mock() else (
                "无 snapshot_write 工具" if snapshot is None else "无商品可落库")
            return {"_trace": [self._trace_entry(reason)]}

        # 1) 新建 run + 落商品，拿 run_id
        res = snapshot.run(keyword=keyword, region=region,
                           scored=products, db_path=db_path)
        if not (isinstance(res, dict) and res.get("ok")):
            return {"_trace": [self._trace_entry("落库失败（商品），已跳过")]}
        run_id = res.get("run_id")

        # 2) 每个有评论的商品：挂同一 run_id，落评论 + 痛点
        rev_n = pp_n = 0
        for item in review_raw:
            if not isinstance(item, dict):
                continue
            pid = item.get("product_id")
            reviews = item.get("reviews") or []
            analysis = item.get("analysis") or {}
            if pid is None or not reviews:
                continue
            r = snapshot.run(keyword=keyword, region=region, run_id=run_id,
                             reviews=reviews, analysis=analysis,
                             target_id=str(pid), db_path=db_path)
            if isinstance(r, dict) and r.get("ok"):
                rev_n += len(reviews)
                pp_n += len(analysis.get("pain_points") or [])

        note = f"落库 run={run_id}：商品 {len(products)} / 评论 {rev_n} / 痛点 {pp_n}"
        refs: list[dict[str, Any]] = [new_evidence_ref(
            layer="db",
            source_id=run_id,
            summary=note,
            confidence=0.9,
        )]
        return {
            "run_id": run_id,
            "evidence_refs": self._merge_refs(state, refs),
            "_trace": [self._trace_entry(note)],
        }
