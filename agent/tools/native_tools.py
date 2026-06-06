"""原生平台 API 适配器占位（○ 档，PRD D2）。

设计意图——证明「换数据源，Skill MD / 节点逻辑不变」：
    抖店罗盘 / 千川 / 巨量百应等平台原生 API 未来要接入时，只需在这里把对应
    适配器的 _run() 实现掉，再把它 register() 进 TOOL_REGISTRY 替换同名 TikHub
    工具即可——节点（analyzers/aggregate）按 get_tool("search_products") 取工具，
    工具名一一对应，所以**上层一行不用改**，Skill MD 更一字不动。

与 tikhub_tools 的对应关系（name 一一对应、input_schema 保持一致）：
    search_products / rank_products / fetch_reviews /
    analyze_reviews / snapshot_write / trend_query

重要：本模块**不自动 register**，import 零副作用——
    若在此 register，会覆盖已注册的 TikHub 工具、把洞察子图打挂。
    未来真正切源时，由接入方显式 `for t in NATIVE_TOOLS: register(t)`。
    现在每个 _run() 抛 NotImplementedError("平台侧未来")，仅作接口契约占位。
"""
from __future__ import annotations

from typing import Any

from .base import BaseTool
from .tikhub_tools import (
    AnalyzeReviewsTool,
    FetchReviewsTool,
    RankProductsTool,
    SearchProductsTool,
    SnapshotWriteTool,
    TrendQueryTool,
)

_NOT_READY = "平台侧未来：抖店罗盘/千川/百应 原生 API 未接入"


class _NativeBase(BaseTool):
    """原生适配器占位基类：复用对应 TikHub 工具的 name / schema，body 抛未实现。

    通过 `_mirror` 指向被镜像的 TikHub 工具类，自动同步其 name/description/
    input_schema/output_schema —— 保证「一一对应」由代码而非手抄保证，
    TikHub schema 改了这里跟着变，不会漂移。
    """

    _mirror: type[BaseTool] = BaseTool

    def __init__(self) -> None:
        src = self._mirror
        self.name = src.name
        self.description = f"[原生占位] {src.description}"
        self.input_schema = src.input_schema
        self.output_schema = src.output_schema

    def _run(self, **kwargs: Any) -> dict:
        raise NotImplementedError(f"{_NOT_READY}（{self.name}）")


class NativeSearchProductsTool(_NativeBase):
    _mirror = SearchProductsTool


class NativeRankProductsTool(_NativeBase):
    _mirror = RankProductsTool


class NativeFetchReviewsTool(_NativeBase):
    _mirror = FetchReviewsTool


class NativeAnalyzeReviewsTool(_NativeBase):
    _mirror = AnalyzeReviewsTool


class NativeSnapshotWriteTool(_NativeBase):
    _mirror = SnapshotWriteTool


class NativeTrendQueryTool(_NativeBase):
    _mirror = TrendQueryTool


# 适配器实例清单（**不注册**，仅供未来显式接入 / 一致性自检）。
NATIVE_TOOLS: list[BaseTool] = [
    NativeSearchProductsTool(),
    NativeRankProductsTool(),
    NativeFetchReviewsTool(),
    NativeAnalyzeReviewsTool(),
    NativeSnapshotWriteTool(),
    NativeTrendQueryTool(),
]

# 自检：原生工具名集合必须与 TikHub 工具一一对应（漂移即 import 报错）。
_TIKHUB_NAMES = {
    SearchProductsTool.name, RankProductsTool.name, FetchReviewsTool.name,
    AnalyzeReviewsTool.name, SnapshotWriteTool.name, TrendQueryTool.name,
}
assert {t.name for t in NATIVE_TOOLS} == _TIKHUB_NAMES, (
    "native_tools 与 tikhub_tools 工具名未一一对应"
)
