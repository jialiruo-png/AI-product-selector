"""副窗口任务 B（CLAUDE.md §11.3）：抖店中小商家经营诊断 Agent 演示 MVP。

数据来源：agent/mocks/shops/case_*.json
启动：streamlit run demo/streamlit_app.py
Day 4 收尾时把"跑一次诊断"占位区换成：
    from agent.run import run
    result = run(case_id, mock=True)
"""

import json
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="抖店中小商家经营诊断 Agent", layout="wide")

MOCKS_DIR = Path(__file__).resolve().parents[1] / "agent" / "mocks" / "shops"
case_files = sorted(MOCKS_DIR.glob("case_*.json"))

if not case_files:
    st.error(f"未找到 mock 数据：{MOCKS_DIR}（请先跑副窗口任务 A）")
    st.stop()


def case_label(p: Path) -> str:
    d = json.loads(p.read_text())
    return f"{p.stem} · {d.get('_case_name', '')}"


st.sidebar.header("演示案例")
selected = st.sidebar.selectbox("选择诊断 case", case_files, format_func=case_label)
data = json.loads(selected.read_text())

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**Overlay 命中**\n\n{', '.join(data.get('_overlay_hints', [])) or '—'}"
)
st.sidebar.markdown(f"**场景一句话**\n\n{data.get('_scenario_summary', '—')}")

st.title("抖店中小商家经营诊断 Agent")
st.caption("V1 演示 · 数据为 mock · Day 4 后接通真实 Agent")

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

with col2:
    st.subheader("AI 诊断报告")
    if st.button("跑一次诊断", type="primary", use_container_width=True):
        st.markdown("#### 核心问题")
        st.warning(data.get("_scenario_summary", "—"))

        st.markdown("#### 异常清单（占位 · Day 3 由 Checker 节点生成）")
        m7 = data.get("metrics_7d") or {}
        mp7 = data.get("metrics_prev_7d") or {}
        base = data.get("category_baseline") or {}
        rows = []
        for k in (
            "cvr",
            "main_image_ctr",
            "qianchuan_roi",
            "live_room_stay_sec",
            "search_ctr",
            "kol_keng_wei_roi",
        ):
            if k in m7 and k in mp7:
                cur, prev = m7[k], mp7[k]
                delta = f"{(cur - prev) / prev:+.1%}" if prev else "—"
                rows.append(
                    {
                        "指标": k,
                        "近 7 天": cur,
                        "上 7 天": prev,
                        "环比": delta,
                        "类目基线": base.get(k, "—"),
                    }
                )
        if rows:
            st.dataframe(rows, hide_index=True, use_container_width=True)
        else:
            st.info("本 case 无可比对指标（如新店冷启动尚未激活交易）")

        st.markdown("#### 归因 + 行动建议")
        st.info(
            "⏳ Day 3 后由 Attributor + Advisor 节点生成（含证据引用 + 资源挂钩）"
        )
    else:
        st.info("点上方按钮触发诊断。Day 4 后接 `agent.run --diagnosis --mock`。")

    with st.expander("查看本 case 全量数据"):
        st.json(data)
