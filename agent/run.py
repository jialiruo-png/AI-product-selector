"""商机洞察子图 CLI 入口。

用法::

    python3 -m agent.run "口红" --category 美妆 --region US --topn 5 [--mock]

``--mock`` 会在导入 nodes/tools 之前设置 ``AGENT_MOCK=1``，确保各节点走
mock 分支（不打真实接口）。运行完成后打印最终 markdown 报告 + 简要 trace 摘要。
"""
from __future__ import annotations

import argparse
import asyncio
import os


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agent.run",
        description="运行商机洞察子图，输出 markdown 报告。",
    )
    parser.add_argument("keyword", help="核心关键词，如 口红")
    parser.add_argument("--category", default="", help="类目，如 美妆")
    parser.add_argument("--region", default="CN", help="地区/市场，如 US / CN")
    parser.add_argument("--topn", type=int, default=20, help="取 TopN 商品（默认 20）")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="开启 mock 模式（设置 AGENT_MOCK=1，不打真实接口）",
    )
    parser.add_argument(
        "--langgraph",
        action="store_true",
        help="强制尝试 LangGraph 后端（未安装则回退 MiniGraph）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # 必须在导入 nodes/tools 之前设置环境变量。
    if args.mock:
        os.environ["AGENT_MOCK"] = "1"
    if args.langgraph:
        os.environ["AGENT_USE_LANGGRAPH"] = "1"

    # 延迟导入：保证上面的环境变量先生效。
    from agent.graph import build_graph, run_insight

    initial_state: dict = {
        "keyword": args.keyword,
        "category": args.category,
        "region": args.region,
        "topn": args.topn,
    }

    final_state = asyncio.run(run_insight(initial_state))

    # ---- 输出最终报告 ----
    report = final_state.get("report") or "(无报告生成)"
    print(report)

    # ---- trace 摘要 ----
    backend = type(build_graph()).__name__
    trace = final_state.get("_trace") or []
    nodes_run = [t.get("node") for t in trace if isinstance(t, dict)]
    refs = final_state.get("evidence_refs") or []
    print("\n" + "=" * 48)
    print(f"[trace] 后端: {backend}")
    print(f"[trace] 节点执行 {len(nodes_run)} 个: {' -> '.join(nodes_run)}")
    print(f"[trace] 证据引用 evidence_refs 共 {len(refs)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
