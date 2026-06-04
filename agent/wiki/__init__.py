"""双层 Wiki（PRD 1.3 / 融合方案 第 6 节务实裁剪版）。

WikiResolver 在只读行业 Wiki 之上叠加商家私有 overlay：
有商家页则商家覆盖，否则回落行业默认。6 种语义关系冲突治理
（supports/refines/scope_differs/contradicts/supersedes/duplicates）
在 V1.5 才做真实分类，此处先占位。
"""
from __future__ import annotations

from typing import Literal

from .industry import IndustryWiki
from .seller import SellerWiki

ConflictRelation = Literal[
    "supports",
    "refines",
    "scope_differs",
    "contradicts",
    "supersedes",
    "duplicates",
]

__all__ = ["IndustryWiki", "SellerWiki", "WikiResolver", "ConflictRelation"]


class WikiResolver:
    """分层解析：商家 overlay 覆盖行业默认。"""

    def __init__(
        self,
        industry: IndustryWiki | None = None,
        seller: SellerWiki | None = None,
    ) -> None:
        self.industry = industry or IndustryWiki()
        self.seller = seller or SellerWiki()

    def resolve(self, key: str, seller_id: str | None = None) -> dict | None:
        """商家页优先，回落行业页。返回命中页（附 _layer 标注来源层）。"""
        if seller_id:
            page = self.seller.get(seller_id, key)
            if page is not None:
                return {**page, "_layer": "seller"}
        ind = self.industry.get(key)
        if ind is not None:
            return {**ind, "_layer": "industry"}
        return None

    def search(self, q: str, seller_id: str | None = None) -> list[dict]:
        results: list[dict] = []
        if seller_id:
            results += [{**p, "_layer": "seller"} for p in self.seller.search(seller_id, q)]
        results += [{**p, "_layer": "industry"} for p in self.industry.search(q)]
        return results

    def conflict_relation(self, a: dict, b: dict) -> ConflictRelation:
        """判定两条知识的语义关系（6 种之一）。

        # TODO V1.5: real semantic classification (LLM/SemanticUnit 治理)
        MVP 仅做启发式：标题/键相同 -> duplicates，否则 -> refines。
        """
        a_key = str(a.get("key") or a.get("title") or "")
        b_key = str(b.get("key") or b.get("title") or "")
        if a_key and a_key == b_key:
            return "duplicates"
        return "refines"
