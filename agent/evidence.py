"""统一证据引用接口（PRD 9.1 KnowledgeEvidenceRef 的工程落地）。

"必须有 evidence ref" 不是一句口号，而是一份强制约束的契约：
每条 AI 输出都必须挂一个或多个 KnowledgeEvidenceRef。
MVP 主用 raw / wiki 两个 layer，其余 layer 枚举先占位（融合方案 第 6 节）。
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Literal

Layer = Literal["raw", "wiki", "image", "semantic_unit", "strategy_action", "skill_run"]
Status = Literal["candidate", "confirmed", "rejected", "superseded"]


@dataclass
class KnowledgeEvidenceRef:
    refId: str
    layer: Layer
    quoteOrSummary: str
    confidence: float = 0.8
    status: Status = "candidate"
    # 来源 6 选 1（按 layer 取其一），其余留空
    sourceId: str | None = None        # 行业 Wiki 来源
    pageId: str | None = None          # 商家 Wiki 页
    imageId: str | None = None         # 视觉证据
    semanticUnitId: str | None = None  # 语义规则
    strategyActionId: str | None = None  # 策略动作卡
    skillRunId: str | None = None      # Skill 执行产物

    def to_dict(self) -> dict:
        return asdict(self)


# layer -> 该 layer 对应的来源字段名
_LAYER_SOURCE_FIELD: dict[str, str] = {
    "raw": "sourceId",
    "wiki": "pageId",
    "image": "imageId",
    "semantic_unit": "semanticUnitId",
    "strategy_action": "strategyActionId",
    "skill_run": "skillRunId",
}


def make_ref(
    layer: Layer,
    source_id: str,
    summary: str,
    confidence: float = 0.8,
    status: Status = "candidate",
) -> dict:
    """构造一条证据引用 dict。source_id 自动落到该 layer 对应的来源字段。"""
    ref = KnowledgeEvidenceRef(
        refId=f"ev_{uuid.uuid4().hex[:12]}",
        layer=layer,
        quoteOrSummary=summary,
        confidence=confidence,
        status=status,
    )
    field_name = _LAYER_SOURCE_FIELD.get(layer, "sourceId")
    setattr(ref, field_name, source_id)
    return ref.to_dict()


class EvidenceStore:
    """内存证据库：收集本次 Agent 运行产出的全部 KnowledgeEvidenceRef。"""

    def __init__(self) -> None:
        self._refs: list[dict] = []

    def add(self, ref: dict) -> dict:
        self._refs.append(ref)
        return ref

    def all(self) -> list[dict]:
        return list(self._refs)

    def by_layer(self, layer: Layer) -> list[dict]:
        return [r for r in self._refs if r.get("layer") == layer]

    def mark_superseded(self, ref_ids: list[str]) -> int:
        """Wiki 更新/冲突裁决后，把引用过旧证据的记录批量标记 superseded。"""
        targets = set(ref_ids)
        n = 0
        for r in self._refs:
            if r.get("refId") in targets:
                r["status"] = "superseded"
                n += 1
        return n
