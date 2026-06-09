"""Agent 子图 CLI 入口（统一冷启动选品 / 在运营经营诊断）。

用法 1：商机洞察（甘华梁冷启动选品）::

    python3 -m agent.run "口红" --category 美妆 --region US --topn 5 [--mock] [--db PATH]

用法 2：在运营商家经营诊断（贾丽婼）::

    python3 -m agent.run "我店铺最近 GMV 跌了" --shop-id case_1 --diagnosis [--mock]

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
        description="运行 Agent 子图（冷启动选品 / 经营诊断），输出 markdown 报告。",
    )
    parser.add_argument(
        "query",
        help="核心关键词（冷启动）或自然语言问题（诊断），如 '口红' 或 '我店铺最近 GMV 跌了'",
    )
    # 冷启动选品参数
    parser.add_argument("--category", default="", help="类目（冷启动用），如 美妆")
    parser.add_argument("--region", default="CN", help="地区/市场，如 US / CN")
    parser.add_argument("--topn", type=int, default=20, help="取 TopN 商品（冷启动用，默认 20）")
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite 落库路径（冷启动用，默认 采集工作台/outputs/selector.db；mock 模式不落库）",
    )
    # 诊断子图参数（贾丽婼）
    parser.add_argument(
        "--diagnosis",
        action="store_true",
        help="切换到在运营商家诊断子图（贾丽婼）",
    )
    parser.add_argument(
        "--shop-id",
        default="case_1",
        help="诊断目标店铺 ID，对应 agent/mocks/shops/<shop_id>.json（默认 case_1）",
    )
    parser.add_argument(
        "--window",
        default="7d",
        help="诊断窗口，7d / 30d（默认 7d）",
    )
    # 通用
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
    if args.diagnosis:
        from agent.graph import build_diagnosis_graph, run_diagnosis

        initial_state: dict = {
            "shop_id": args.shop_id,
            "user_query": args.query,
            "window": args.window,
        }
        app = build_diagnosis_graph()
        final_state = asyncio.run(run_diagnosis(initial_state))
        subgraph_name = "diagnosis"
    else:
        from agent.graph import build_graph, run_insight

        initial_state = {
            "keyword": args.query,
            "category": args.category,
            "region": args.region,
            "topn": args.topn,
            "db_path": args.db,
        }
        app = build_graph()
        final_state = asyncio.run(run_insight(initial_state))
        subgraph_name = "insight"

    # ---- 输出最终报告 ----
    report = final_state.get("report") or "(无报告生成)"
    print(report)

    # ---- trace 摘要 ----
    backend = getattr(app, "backend", type(app).__name__)
    trace = final_state.get("_trace") or []
    nodes_run = [t.get("node") for t in trace if isinstance(t, dict)]
    refs = final_state.get("evidence_refs") or []
    print("\n" + "=" * 48)
    print(f"[trace] 子图: {subgraph_name}  · 后端: {backend}")
    print(f"[trace] 节点执行 {len(nodes_run)} 个: {' -> '.join(nodes_run)}")
    print(f"[trace] 证据引用 evidence_refs 共 {len(refs)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
