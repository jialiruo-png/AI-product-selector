"""节点基类（商机洞察子图）。

每个具体节点继承 BaseNode，实现 async run(state) -> 增量状态更新 dict
（LangGraph merge 风格：只返回本节点写入/改动的键）。

约定：
    - run() 必须返回 partial dict，至少含 "_trace": [self._trace_entry(...)]。
    - 凡产出证据的节点，附带 "evidence_refs": [...]（会与已有 list 合并由 graph 层处理；
      MVP 下我们在节点内读 state 旧值再拼接，保证幂等可见）。
"""
from __future__ import annotations

import os
import time
from typing import Any


def is_mock() -> bool:
    """是否运行在 mock 模式（AGENT_MOCK=1）。"""
    return os.getenv("AGENT_MOCK", "") in ("1", "true", "True", "yes")


class BaseNode:
    """所有节点的抽象基类。"""

    name: str = "base"

    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    async def run(self, state: dict) -> dict:  # pragma: no cover - 抽象
        raise NotImplementedError(f"{type(self).__name__} 未实现 run()")

    # ---- 可观测性：trace 条目 ----
    def _trace_entry(self, note: str = "") -> dict:
        """返回一条 trace dict {node, ms, note}。

        ms 用 perf_counter 自节点实例化以来的毫秒数；不依赖 wall-clock，
        测试与 mock 下稳定可用。
        """
        ms = round((time.perf_counter() - self._t0) * 1000, 2)
        return {"node": self.name, "ms": ms, "note": note}

    # ---- 证据引用合并辅助 ----
    @staticmethod
    def _merge_refs(state: dict, new_refs: list[dict]) -> list[dict]:
        """把 new_refs 追加到 state 已有 evidence_refs 之后，返回完整 list。"""
        existing = list(state.get("evidence_refs") or [])
        existing.extend(new_refs or [])
        return existing


# 工具注册表导入：契约要求 `from agent.tools import TOOL_REGISTRY`，
# 但 tools 包当前未在 __init__ 重导出，故回退到 agent.tools.base（不修改 tools/）。
try:  # pragma: no cover
    from agent.tools import TOOL_REGISTRY  # type: ignore
except Exception:  # noqa: BLE001
    from agent.tools.base import TOOL_REGISTRY  # type: ignore


def get_tool(name: str):
    """安全取工具，未注册时返回 None（mock/缺省下不崩）。"""
    return TOOL_REGISTRY.get(name)
