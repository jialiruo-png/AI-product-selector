"""商机洞察子图 wiring。

图形结构::

    keyword_planner (entry)
       -> [social_analyzer, price_analyzer, hot_item_analyzer, competitor_analyzer]  (4 并行)
       -> collector  (fan-in)
       -> curator -> briefing -> editor (finish)

本模块提供两套后端：

1. 真实 LangGraph ``StateGraph`` —— 若 ``langgraph`` 已安装。list 型字段
   （``_trace`` / ``evidence_refs`` / ``messages``）通过 ``Annotated`` reducer
   做并发安全的拼接合并。
2. ``MiniGraph`` —— 纯 asyncio fallback，无第三方依赖，默认首选（可靠、好调试）。

两套后端统一通过 ``async def run_insight(initial_state) -> dict`` 暴露给调用方。
通过环境变量 ``AGENT_USE_LANGGRAPH=1`` 切换到 LangGraph 后端。
"""
from __future__ import annotations

import asyncio
import operator
import os
from typing import Annotated, Any, TypedDict

from agent.nodes import (
    Briefing,
    Collector,
    CompetitorAnalyzer,
    Curator,
    Editor,
    HotItemAnalyzer,
    KeywordPlanner,
    PriceAnalyzer,
    SocialAnalyzer,
)

# 需要"拼接合并"的 list 型字段（并行节点各写一份，须 concat 而非 last-writer-wins）。
_LIST_MERGE_KEYS = ("_trace", "evidence_refs", "messages")

# 四路并行分析节点的属性名。
_ANALYZER_KEYS = (
    "social_analyzer",
    "price_analyzer",
    "hot_item_analyzer",
    "competitor_analyzer",
)


def _init_nodes() -> dict[str, Any]:
    """实例化全部节点，返回 {属性名: 节点实例}。两套后端共用。"""
    return {
        "keyword_planner": KeywordPlanner(),
        "social_analyzer": SocialAnalyzer(),
        "price_analyzer": PriceAnalyzer(),
        "hot_item_analyzer": HotItemAnalyzer(),
        "competitor_analyzer": CompetitorAnalyzer(),
        "collector": Collector(),
        "curator": Curator(),
        "briefing": Briefing(),
        "editor": Editor(),
    }


def _merge_partial(base: dict, partial: dict) -> None:
    """把 partial 合并进 base（原地）。

    - ``_LIST_MERGE_KEYS`` 中的键：若两边都是 list 则拼接（concat）。
    - ``products``：仅当值为 list 且 base 已有 list 时拼接；否则 last-writer-wins。
      （实际只有 PriceAnalyzer 写 products，不会真正冲突，这里保守处理。）
    - 其余键：last-writer-wins。
    """
    for k, v in partial.items():
        if k in _LIST_MERGE_KEYS:
            old = base.get(k)
            if isinstance(old, list) and isinstance(v, list):
                base[k] = old + v
            else:
                base[k] = v
        else:
            base[k] = v


# --------------------------------------------------------------------------- #
# MiniGraph —— 纯 asyncio fallback 运行器
# --------------------------------------------------------------------------- #
class MiniGraph:
    """无依赖的子图运行器，行为等价于上面描述的 LangGraph 结构。

    执行顺序::
        keyword_planner
          -> gather(social, price, hot_item, competitor)   # 真并行
          -> collector -> curator -> briefing -> editor
    """

    backend = "MiniGraph"

    def __init__(self) -> None:
        self.nodes = _init_nodes()

    async def run(self, initial_state: dict) -> dict:
        state: dict[str, Any] = dict(initial_state or {})

        # 1) 入口：keyword_planner
        _merge_partial(state, await self.nodes["keyword_planner"].run(state))

        # 2) 四路并行分析。各 analyzer 读同一份 pre-fan-out 快照，
        #    只返回"自己"那部分（含各自 evidence_refs），随后我们拼接合并。
        snapshot = dict(state)
        analyzers = [self.nodes[k] for k in _ANALYZER_KEYS]
        results = await asyncio.gather(*(a.run(snapshot) for a in analyzers))
        for partial in results:
            _merge_partial(state, partial)

        # 3) fan-in 之后顺序执行
        for key in ("collector", "curator", "briefing", "editor"):
            _merge_partial(state, await self.nodes[key].run(state))

        return state


# --------------------------------------------------------------------------- #
# LangGraph 后端构建（可选）
# --------------------------------------------------------------------------- #
# langgraph 用 get_type_hints 解析 _GraphState 的注解；因 ``from __future__ import
# annotations`` 注解全为字符串(forward ref)，求值时需 Annotated / operator / list
# 在模块全局可见 —— 故本类与相关 import 必须放在模块级，不能塞进函数内。
class _GraphState(TypedDict, total=False):
    keyword: str
    category: str
    region: str
    topn: int
    keywords: list
    social_data: dict
    curated_social_data: dict
    price_data: dict
    curated_price_data: dict
    hot_data: dict
    curated_hot_data: dict
    competitor_data: dict
    curated_competitor_data: dict
    products: list
    briefings: dict
    report: str
    # 并发拼接字段：operator.add => 拼接（concat），其余字段默认 last-writer-wins。
    evidence_refs: Annotated[list, operator.add]
    messages: Annotated[list, operator.add]
    _trace: Annotated[list, operator.add]


def _build_langgraph_app():
    """构建并编译真实 LangGraph 应用。

    若 ``langgraph`` 未安装会抛 ImportError，由 build_graph 捕获后回退。
    返回一个带统一 ``async def ainvoke(state) -> dict`` 接口的包装对象。
    """
    from langgraph.graph import StateGraph

    nodes = _init_nodes()
    wf = StateGraph(_GraphState)

    for label, inst in nodes.items():
        wf.add_node(label, inst.run)

    wf.set_entry_point("keyword_planner")
    wf.set_finish_point("editor")

    for label in _ANALYZER_KEYS:
        wf.add_edge("keyword_planner", label)
        wf.add_edge(label, "collector")

    wf.add_edge("collector", "curator")
    wf.add_edge("curator", "briefing")
    wf.add_edge("briefing", "editor")

    compiled = wf.compile()

    class _LangGraphApp:
        backend = "langgraph"

        def __init__(self, app):
            self._app = app

        async def ainvoke(self, state: dict) -> dict:
            return await self._app.ainvoke(state)

    return _LangGraphApp(compiled)


# --------------------------------------------------------------------------- #
# 统一构建入口
# --------------------------------------------------------------------------- #
def _want_langgraph(use_langgraph: bool | None) -> bool:
    """决定是否尝试 LangGraph：显式参数优先，否则看 AGENT_USE_LANGGRAPH。"""
    if use_langgraph is not None:
        return use_langgraph
    return os.getenv("AGENT_USE_LANGGRAPH", "") in ("1", "true", "True", "yes")


def build_graph(use_langgraph: bool | None = None):
    """构建子图运行后端。

    返回对象统一具备 ``async def ainvoke(state)`` 或 ``async def run(state)``；
    调用方应优先用 ``run_insight``，无需关心具体后端。

    默认（``use_langgraph=None`` 且未设环境变量）：返回 MiniGraph —— 可靠、无依赖。
    设置 ``AGENT_USE_LANGGRAPH=1`` 或显式传 ``True``：尝试 LangGraph，
    若未安装则优雅回退到 MiniGraph（不崩）。
    """
    if _want_langgraph(use_langgraph):
        try:
            return _build_langgraph_app()
        except ImportError:
            # langgraph 未安装 —— 回退
            return MiniGraph()
    return MiniGraph()


async def run_insight(initial_state: dict, use_langgraph: bool | None = None) -> dict:
    """运行商机洞察子图，返回最终合并后的 state dict。

    统一入口：屏蔽后端差异（LangGraph / MiniGraph）。
    """
    app = build_graph(use_langgraph=use_langgraph)
    if hasattr(app, "ainvoke"):
        return await app.ainvoke(initial_state)
    return await app.run(initial_state)
