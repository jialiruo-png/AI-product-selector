"""商机洞察子图 (business-opportunity insight subgraph) 包入口。

对外暴露统一运行入口 ``run_insight`` 与构建函数 ``build_graph``。

注意：这里**惰性**导出（PEP 562 ``__getattr__``）。原因是工具层
（``agent.tools``）会在 import 时实例化并在 ``__init__`` 中固化 ``AGENT_MOCK``
开关；若本包在 import 时就连带把 graph/nodes/tools 全部拉起，则 CLI 还来不及
设置 ``AGENT_MOCK=1`` 工具就已被构造成"非 mock"。惰性导出让
``python3 -m agent.run`` 先设好环境变量、再触发首次属性访问时的真正导入。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["build_graph", "run_insight"]

if TYPE_CHECKING:  # 仅供类型检查/IDE，不在运行时触发导入
    from agent.graph import build_graph, run_insight


def __getattr__(name: str):
    if name in __all__:
        from agent import graph

        return getattr(graph, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
