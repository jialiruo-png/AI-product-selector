"""Review 状态机（PRD 1.4：人审边界明确）。

AI 永远不直接改写商家关键数据。高敏感动作（改价/退款/上下架）必须
经过状态机。MVP 主用于「建议转任务」（融合方案 第 7 节）：
洞察报告里的行动建议 → 商家点「采纳」才落任务。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class ReviewStatus(str, Enum):
    Candidate = "Candidate"          # AI 输出候选方案
    PendingReview = "PendingReview"  # 等待商家/小二审阅
    Approved = "Approved"            # 人工通过
    Executed = "Executed"            # 执行并记录审计日志
    Rejected = "Rejected"            # 驳回 + 反馈给 AI 学习


# 合法状态转移图
_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
    ReviewStatus.Candidate: {ReviewStatus.PendingReview, ReviewStatus.Approved, ReviewStatus.Rejected},
    ReviewStatus.PendingReview: {ReviewStatus.Approved, ReviewStatus.Rejected},
    ReviewStatus.Approved: {ReviewStatus.Executed, ReviewStatus.Rejected},
    ReviewStatus.Executed: set(),
    ReviewStatus.Rejected: set(),
}


@dataclass
class ReviewItem:
    id: str
    payload: dict
    status: ReviewStatus = ReviewStatus.Candidate
    feedback: str | None = None


class IllegalTransition(Exception):
    """非法状态转移。"""


class ReviewQueue:
    """审批队列 + 审计日志。"""

    def __init__(self) -> None:
        self.items: dict[str, ReviewItem] = {}
        self.audit_log: list[dict] = []

    def submit(self, payload: dict) -> ReviewItem:
        """AI 提交候选方案，进入队列（Candidate）。"""
        item = ReviewItem(id=f"rv_{uuid.uuid4().hex[:12]}", payload=payload)
        self.items[item.id] = item
        self._log(item.id, None, item.status, "submit")
        return item

    def _resolve(self, item: ReviewItem | str) -> ReviewItem:
        if isinstance(item, ReviewItem):
            return item
        found = self.items.get(item)
        if found is None:
            raise KeyError(f"unknown review item: {item}")
        return found

    def _transition(self, item: ReviewItem | str, to: ReviewStatus, action: str,
                    feedback: str | None = None) -> ReviewItem:
        it = self._resolve(item)
        if to not in _TRANSITIONS[it.status]:
            raise IllegalTransition(f"{it.status.value} -> {to.value} 非法")
        frm = it.status
        it.status = to
        if feedback is not None:
            it.feedback = feedback
        self._log(it.id, frm, to, action, feedback)
        return it

    def approve(self, item: ReviewItem | str) -> ReviewItem:
        return self._transition(item, ReviewStatus.Approved, "approve")

    def reject(self, item: ReviewItem | str, feedback: str | None = None) -> ReviewItem:
        return self._transition(item, ReviewStatus.Rejected, "reject", feedback)

    def execute(self, item: ReviewItem | str) -> ReviewItem:
        return self._transition(item, ReviewStatus.Executed, "execute")

    def _log(self, item_id: str, frm: ReviewStatus | None, to: ReviewStatus,
             action: str, feedback: str | None = None) -> None:
        self.audit_log.append({
            "ts": time.time(),
            "item_id": item_id,
            "action": action,
            "from": frm.value if frm else None,
            "to": to.value,
            "feedback": feedback,
        })
