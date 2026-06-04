"""副窗口任务 B（CLAUDE.md §11.3）：抖店中小商家经营诊断 Agent 演示。

启动：
    streamlit run demo/streamlit_app.py

数据来源：agent/mocks/shops/case_*.json
后端：实时调用 agent.graph.run_diagnosis（4 节点子图：checker → attributor → advisor → composer）。
mock 模式：模块加载时即设 AGENT_MOCK=1，所有节点走 mock 分支，无需 DashScope / TikHub key。
"""

import os

# 必须在 import agent.* 之前设置，确保所有节点和工具走 mock 分支
os.environ.setdefault("AGENT_MOCK", "1")

import asyncio
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.graph import run_diagnosis  # noqa: E402

st.set_page_config(page_title="抖店中小商家经营诊断 Agent", layout="wide")

MOCKS_DIR = ROOT / "agent" / "mocks" / "shops"
case_files = sorted(MOCKS_DIR.glob("case_*.json"))

if not case_files:
    st.error(f"未找到 mock 数据：{MOCKS_DIR}（请先跑副窗口任务 A）")
    st.stop()


def case_label(p: Path) -> str:
    d = json.loads(p.read_text())
    return f"{p.stem} · {d.get('_case_name', '')}"


@st.cache_data(show_spinner=False)
def run_diagnosis_cached(case_id: str, user_query: str, window: str) -> dict:
    """按 (case_id, user_query, window) 缓存诊断结果，避免反复点按钮重跑。"""
    return asyncio.run(
        run_diagnosis(
            {"shop_id": case_id, "user_query": user_query, "window": window}
        )
    )


# ---------- 左侧栏 ----------
st.sidebar.header("演示案例")
selected = st.sidebar.selectbox(
    "选择诊断 case", case_files, format_func=case_label
)
data = json.loads(selected.read_text())

st.sidebar.markdown("---")
st.sidebar.markdown(f"**场景一句话**\n\n{data.get('_scenario_summary', '—')}")
st.sidebar.markdown(
    f"**期望命中 overlay**\n\n{', '.join(data.get('_overlay_hints', [])) or '—'}"
)
user_query = st.sidebar.text_input(
    "用户原始问题", value="我店铺最近 GMV 跌了"
)
window = st.sidebar.selectbox("诊断窗口", ["7d", "30d"], index=0)

st.sidebar.markdown("---")
st.sidebar.caption(
    "实时调用 `agent.graph.run_diagnosis`\n\n"
    "后端：MiniGraph · 模式：AGENT_MOCK=1"
)

# ---------- 顶部 ----------
st.title("抖店中小商家经营诊断 Agent")
st.caption(
    "V1 演示 · mock 数据 · 实时调用经营诊断子图（checker → attributor → advisor → composer）"
)

# ---------- 两列：商家画像 + 诊断报告 ----------
col1, col2 = st.columns([1, 2], gap="large")

with col1:
    st.subheader("商家画像")
    profile = data.get("shop_profile", {}) or {}
    monthly_gmv = profile.get("monthly_gmv", 0) or 0
    monthly_gmv_prev = profile.get("monthly_gmv_prev", 0) or 0
    st.markdown(
        f"""
- **店铺**：{profile.get('shop_name', '—')}
- **类目**：{profile.get('category', '—')}
- **入驻**：{profile.get('entry_days', 0)} 天 · {profile.get('shop_level', '—')}
- **体验分**：{profile.get('exp_score', 0)}（准入线 {profile.get('exp_score_threshold', 4.5)}）
- **月销**：{monthly_gmv:,} 元（上月 {monthly_gmv_prev:,}）
- **阶段**：{profile.get('stage', '—')}
"""
    )
    with st.expander("流量来源拆分"):
        st.json(profile.get("dau_gmv_share") or {})
    with st.expander("完整 shop_profile"):
        st.json(profile)
    with st.expander("查看本 case 全量输入数据"):
        st.json(data)

with col2:
    st.subheader("AI 诊断报告")
    run_btn = st.button(
        "跑一次诊断", type="primary", use_container_width=True
    )

    if run_btn:
        with st.spinner(
            "Agent 思考中…（checker → attributor → advisor → composer）"
        ):
            final_state = run_diagnosis_cached(
                selected.stem, user_query or "诊断", window
            )
        st.session_state["last_result"] = final_state
        st.session_state["last_case_id"] = selected.stem

    # 仅当结果对应当前选中的 case 时才显示，换 case 后清空
    same_case = st.session_state.get("last_case_id") == selected.stem
    result = st.session_state.get("last_result") if same_case else None

    if result is None:
        st.info("点上方按钮跑一次诊断（实时调用 agent.graph.run_diagnosis，mock 模式）。")
    else:
        # 顶部 4 个 metrics
        m_cols = st.columns(4)
        m_cols[0].metric(
            "数据完整度",
            f"{(result.get('data_completeness') or 0) * 100:.0f}%",
        )
        m_cols[1].metric(
            "命中 overlay",
            " / ".join(result.get("matched_overlays") or []) or "—",
        )
        m_cols[2].metric(
            "节点执行", len(result.get("_trace") or [])
        )
        m_cols[3].metric(
            "证据引用", len(result.get("evidence_refs") or [])
        )

        st.markdown("---")
        # 直接渲染 composer 生成的完整 markdown 报告——商家最终看到的形态
        st.markdown(result.get("report") or "(空报告)")

        # ---------- 结构化下钻区（给追问用） ----------
        st.markdown("---")
        st.caption("以下为结构化下钻视图，供面试追问。商家端只看上方报告。")

        with st.expander("🔍 异常清单（anomalies, 表格视图）"):
            anomalies = result.get("anomalies") or []
            if anomalies:
                rows = [
                    {
                        "指标": a.get("metric"),
                        "当前": a.get("current"),
                        "上 7 天": a.get("prev"),
                        "类目基线": a.get("baseline"),
                        "偏离基线": f"{a.get('deviation_vs_baseline_pct', 0):+.1f}%",
                        "偏离上周": f"{a.get('deviation_vs_prev_pct', 0):+.1f}%",
                        "严重度": a.get("severity"),
                        "证据数": len(a.get("evidence_refs") or []),
                    }
                    for a in anomalies
                ]
                st.dataframe(rows, hide_index=True, use_container_width=True)
            else:
                st.info("无异常")

        with st.expander("🧩 根因链（root_cause_chains）"):
            chains = result.get("root_cause_chains") or []
            for chain in chains:
                st.markdown(
                    f"**异常 {chain.get('anomaly_metric', '?')}** · "
                    f"主因索引 #{chain.get('primary_root_cause_index', 0)}"
                )
                rows = [
                    {
                        "根因": c.get("root_cause"),
                        "维度": c.get("dimension"),
                        "置信度": c.get("confidence"),
                        "交叉验证": c.get("cross_validation") or "—",
                    }
                    for c in (chain.get("candidates") or [])
                ]
                if rows:
                    st.dataframe(rows, hide_index=True, use_container_width=True)
            if not chains:
                st.info("无根因链")

        with st.expander("📡 非数据信号（non_data_signals）"):
            sigs = result.get("non_data_signals") or []
            for sig in sigs:
                affects = ", ".join(sig.get("affects_metrics") or [])
                st.warning(
                    f"**{sig.get('signal', '')}**\n\n影响指标：{affects or '—'}"
                )
            if not sigs:
                st.info("无非数据信号")

        with st.expander("🚀 行动建议（actions, 表格视图）"):
            actions = result.get("actions") or []
            if actions:
                rows = [
                    {
                        "id": a.get("action_id"),
                        "标题": a.get("title"),
                        "对应根因": (a.get("linked_root_cause") or "")[:40],
                        "资源 URL": (a.get("resource") or {}).get("url"),
                        "性价比": a.get("cost_benefit"),
                        "置信度": a.get("confidence"),
                        "门槛达成": "✓" if (a.get("eligibility") or {}).get("met") else "✗",
                    }
                    for a in actions
                ]
                st.dataframe(rows, hide_index=True, use_container_width=True)
            else:
                st.info("无建议")

        with st.expander("📚 证据引用表（evidence_refs）"):
            refs = result.get("evidence_refs") or []
            rows = [
                {
                    "refId": r.get("refId"),
                    "layer": r.get("layer"),
                    "sourceId": r.get("sourceId"),
                    "摘要": (r.get("quoteOrSummary") or "")[:80],
                    "置信度": r.get("confidence"),
                }
                for r in refs
            ]
            if rows:
                st.dataframe(rows, hide_index=True, use_container_width=True)

        with st.expander("⚙️ 节点 trace（_trace）"):
            trace = result.get("_trace") or []
            trace_rows = [
                {
                    "node": t.get("node"),
                    "ms": t.get("ms"),
                    "note": t.get("note", ""),
                }
                for t in trace
                if isinstance(t, dict)
            ]
            if trace_rows:
                st.dataframe(
                    trace_rows, hide_index=True, use_container_width=True
                )

        with st.expander("🛠️ 完整 final_state（debug）"):
            st.json(result)
