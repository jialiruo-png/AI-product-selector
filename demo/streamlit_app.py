"""副窗口任务 B（CLAUDE.md §11.3）：抖店中小商家经营诊断 Agent 演示。

启动：
    streamlit run demo/streamlit_app.py

后端：实时调用 agent.graph.run_diagnosis，mock 模式。
设计：中性配色、Altair 图表、去 emoji 装饰、隐藏 Streamlit chrome。
"""

import os

os.environ.setdefault("AGENT_MOCK", "1")

import asyncio
import json
import re
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.graph import run_diagnosis  # noqa: E402

st.set_page_config(
    page_title="经营诊断 · 中小商家版",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- 全局样式 ----------
st.markdown(
    """
<style>
#MainMenu, header, footer, [data-testid="stToolbar"] { visibility: hidden; height: 0; }

html, body, button, input, select, textarea, [class*="st-"] {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Segoe UI", sans-serif;
}

.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1380px; }

h1 { font-size: 1.55rem; font-weight: 600; letter-spacing: -0.01em; color: #1a1a1a; margin-bottom: 0.2rem; }
h2 { font-size: 1.15rem; font-weight: 600; color: #2a2a2a; margin-top: 1.6rem; margin-bottom: 0.6rem; }
h3 { font-size: 0.98rem; font-weight: 600; color: #3a3a3a; margin-top: 1.2rem; }
h4 { font-size: 0.9rem;  font-weight: 600; color: #4a4a4a; }

p, li { color: #333; }

.stButton > button {
    background-color: #1f1f1f;
    color: #fff;
    border: 1px solid #1f1f1f;
    border-radius: 4px;
    font-weight: 500;
    padding: 0.45rem 1.4rem;
    transition: background-color 0.15s ease;
}
.stButton > button:hover { background-color: #3a3a3a; border-color: #3a3a3a; color: #fff; }
.stButton > button:focus, .stButton > button:active { box-shadow: none !important; outline: none !important; }

[data-testid="stExpander"] details {
    border: 1px solid #ececec;
    border-radius: 4px;
    background: #fdfdfd;
}
[data-testid="stExpander"] summary { font-weight: 500; color: #333; padding: 0.55rem 1rem; }

blockquote {
    border-left: 3px solid #d4d4d4;
    color: #555;
    padding: 0.15rem 0 0.15rem 1rem;
    margin: 0.6rem 0;
    background: transparent;
}

.metric-card {
    border: 1px solid #e8e8e8;
    border-radius: 4px;
    padding: 0.85rem 1rem;
    background: #fff;
    height: 100%;
}
.metric-card .label {
    font-size: 0.72rem; color: #888; text-transform: uppercase;
    letter-spacing: 0.06em; margin-bottom: 0.35rem;
}
.metric-card .value {
    font-size: 1.35rem; font-weight: 600; color: #1a1a1a; line-height: 1.2;
}

.signal-card {
    border-left: 3px solid #999;
    padding: 0.6rem 0.95rem;
    background: #fafafa;
    margin: 0.4rem 0;
    font-size: 0.92rem;
    color: #333;
    border-radius: 0 4px 4px 0;
}
.signal-card .signal-meta { color: #888; font-size: 0.8rem; margin-top: 0.25rem; }

.muted-hint { color: #999; padding: 2rem 0 0; font-size: 0.92rem; }
.subtitle    { color: #888; font-size: 0.88rem; margin-top: -0.2rem; }

.stMarkdown { line-height: 1.7; }

[data-testid="stDataFrame"] { border: 1px solid #ececec; border-radius: 4px; }

[data-testid="stSidebar"] { background: #fafafa; border-right: 1px solid #ececec; }
[data-testid="stSidebar"] .stMarkdown { font-size: 0.9rem; }
[data-testid="stSidebar"] h3 { font-size: 0.95rem; color: #1a1a1a; }

hr { border: none; border-top: 1px solid #ececec; margin: 1.4rem 0; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------- emoji 清除（让 composer 报告去掉装饰，仅保留语义） ----------
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F6FF"   # 各类 pictographs / transport
    "\U0001F7E0-\U0001F7FF"   # Geometric Shapes Extended（🟡 🟢 🟠 等）
    "\U0001F900-\U0001F9FF"   # supplemental symbols
    "\U0001FA00-\U0001FAFF"   # symbols and pictographs extended-A
    "☀-➿"           # misc symbols / dingbats
    "️"                  # variation selector-16
    "]+",
    flags=re.UNICODE,
)


def strip_emoji(text: str) -> str:
    if not text:
        return text
    out = EMOJI_RE.sub("", text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"^([#\-\*>]+) +", r"\1 ", out, flags=re.MULTILINE)
    return out


# ---------- 数据加载 ----------
MOCKS_DIR = ROOT / "agent" / "mocks" / "shops"
case_files = sorted(MOCKS_DIR.glob("case_*.json"))

if not case_files:
    st.error(f"未找到 mock 数据：{MOCKS_DIR}")
    st.stop()


def case_label(p: Path) -> str:
    d = json.loads(p.read_text())
    return f"{p.stem.replace('case_', 'Case ')}　{d.get('_case_name', '')}"


@st.cache_data(show_spinner=False)
def run_diagnosis_cached(case_id: str, user_query: str, window: str) -> dict:
    return asyncio.run(
        run_diagnosis(
            {"shop_id": case_id, "user_query": user_query, "window": window}
        )
    )


# ---------- 左侧栏 ----------
with st.sidebar:
    st.markdown("### 诊断对象")
    selected = st.selectbox(
        "选择案例",
        case_files,
        format_func=case_label,
        label_visibility="collapsed",
    )
    data = json.loads(selected.read_text())
    st.markdown(f"**场景**　{data.get('_scenario_summary', '—')}")
    st.markdown(
        f"**预期画像**　{' / '.join(data.get('_overlay_hints', [])) or '—'}"
    )
    st.markdown("---")
    user_query = st.text_input("诊断问题", value="我店铺最近 GMV 跌了")
    window = st.selectbox("窗口", ["7d", "30d"], index=0)


# ---------- 顶部标题 ----------
st.markdown("# 经营诊断 · 中小商家版")
st.markdown(
    "<div class='subtitle'>V1 演示　·　女装类目　·　mock 数据</div>",
    unsafe_allow_html=True,
)
st.markdown("")

# ---------- 主体 ----------
col_profile, col_report = st.columns([1, 2.2], gap="large")

with col_profile:
    st.markdown("### 商家画像")
    profile = data.get("shop_profile") or {}
    monthly_gmv = profile.get("monthly_gmv", 0) or 0
    monthly_gmv_prev = profile.get("monthly_gmv_prev", 0) or 0
    st.markdown(
        f"""
- **店铺**　{profile.get('shop_name', '—')}
- **类目**　{profile.get('category', '—')}
- **入驻**　{profile.get('entry_days', 0)} 天 · 等级 {profile.get('shop_level', '—')}
- **体验分**　{profile.get('exp_score', 0)}　（准入线 {profile.get('exp_score_threshold', 4.5)}）
- **月销**　{monthly_gmv:,} 元　（上月 {monthly_gmv_prev:,}）
- **阶段**　{profile.get('stage', '—')}
"""
    )

    share = profile.get("dau_gmv_share") or {}
    if share:
        st.markdown("#### 流量来源")
        share_df = pd.DataFrame(
            [{"渠道": k, "占比": v} for k, v in share.items() if isinstance(v, (int, float))]
        ).sort_values("占比", ascending=True)
        if not share_df.empty:
            traffic_chart = (
                alt.Chart(share_df)
                .mark_bar(color="#5a5a5a", cornerRadius=2, size=14)
                .encode(
                    x=alt.X(
                        "占比:Q",
                        axis=alt.Axis(
                            format=".0%",
                            grid=False,
                            title=None,
                            labelColor="#888",
                        ),
                    ),
                    y=alt.Y(
                        "渠道:N",
                        sort="-x",
                        axis=alt.Axis(title=None, labelColor="#333"),
                    ),
                    tooltip=[alt.Tooltip("渠道:N"), alt.Tooltip("占比:Q", format=".1%")],
                )
                .properties(height=max(110, 28 * len(share_df)))
                .configure_view(strokeWidth=0)
                .configure_axis(domainColor="#dcdcdc", tickColor="#dcdcdc")
            )
            st.altair_chart(traffic_chart, use_container_width=True)

    with st.expander("完整画像数据"):
        st.json(profile)
    with st.expander("本案例全量输入"):
        st.json(data)

with col_report:
    head_l, head_r = st.columns([2.5, 1])
    head_l.markdown("### 诊断报告")
    run_btn = head_r.button("生成报告", use_container_width=True)

    if run_btn:
        with st.spinner("正在分析…"):
            final_state = run_diagnosis_cached(
                selected.stem, user_query or "诊断", window
            )
        st.session_state["last_result"] = final_state
        st.session_state["last_case_id"] = selected.stem

    same_case = st.session_state.get("last_case_id") == selected.stem
    result = st.session_state.get("last_result") if same_case else None

    if result is None:
        st.markdown(
            "<div class='muted-hint'>选择左侧案例后点击「生成报告」即可查看完整诊断。</div>",
            unsafe_allow_html=True,
        )
    else:
        # 顶部 4 个 metric（自定义卡片，无色块）
        completeness = (result.get("data_completeness") or 0) * 100
        overlays = " / ".join(result.get("matched_overlays") or []) or "—"
        nodes = len(result.get("_trace") or [])
        refs_n = len(result.get("evidence_refs") or [])

        mc1, mc2, mc3, mc4 = st.columns(4)
        for col, label, val in (
            (mc1, "数据完整度", f"{completeness:.0f}%"),
            (mc2, "命中画像", overlays),
            (mc3, "节点执行", str(nodes)),
            (mc4, "证据条目", str(refs_n)),
        ):
            col.markdown(
                f"<div class='metric-card'><div class='label'>{label}</div>"
                f"<div class='value'>{val}</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("")

        # 主报告：去除 emoji 装饰后渲染
        st.markdown(strip_emoji(result.get("report") or "(空报告)"))

        st.markdown("---")
        st.markdown(
            "<div class='subtitle'>下方为结构化下钻视图，可在追问时展开。</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")

        # ---------- 异常指标可视化（Altair 横向条形图） ----------
        anomalies = result.get("anomalies") or []
        if anomalies:
            with st.expander("异常指标可视化"):
                an_df = pd.DataFrame(
                    [
                        {
                            "指标": a.get("metric"),
                            "偏离基线": a.get("deviation_vs_baseline_pct", 0),
                            "严重度": a.get("severity") or "low",
                            "当前": a.get("current"),
                            "基线": a.get("baseline"),
                        }
                        for a in anomalies
                    ]
                ).sort_values("偏离基线")

                severity_scale = alt.Scale(
                    domain=["high", "medium", "low"],
                    range=["#8c4a3c", "#b8895a", "#a0a59c"],
                )

                anomaly_chart = (
                    alt.Chart(an_df)
                    .mark_bar(cornerRadius=3, size=18)
                    .encode(
                        x=alt.X(
                            "偏离基线:Q",
                            axis=alt.Axis(
                                format="+.0f",
                                title="偏离类目基线 (%)",
                                titleColor="#666",
                                titleFontSize=11,
                                grid=True,
                                gridColor="#f0f0f0",
                                labelColor="#666",
                            ),
                        ),
                        y=alt.Y(
                            "指标:N",
                            sort=alt.SortField("偏离基线", order="ascending"),
                            axis=alt.Axis(
                                title=None, labelColor="#333", labelFontSize=12
                            ),
                        ),
                        color=alt.Color(
                            "严重度:N",
                            scale=severity_scale,
                            legend=alt.Legend(
                                title=None, orient="bottom", labelColor="#666"
                            ),
                        ),
                        tooltip=[
                            "指标",
                            alt.Tooltip("当前:Q"),
                            alt.Tooltip("基线:Q"),
                            alt.Tooltip("偏离基线:Q", format="+.1f"),
                            "严重度",
                        ],
                    )
                    .properties(height=max(180, 38 * len(an_df)))
                    .configure_view(strokeWidth=0)
                    .configure_axis(domainColor="#dcdcdc", tickColor="#dcdcdc")
                )
                st.altair_chart(anomaly_chart, use_container_width=True)

        # ---------- 根因链 ----------
        chains = result.get("root_cause_chains") or []
        if chains:
            with st.expander("根因链下钻"):
                for chain in chains:
                    primary_idx = chain.get("primary_root_cause_index", 0)
                    st.markdown(
                        f"**{chain.get('anomaly_metric', '?')}**　"
                        f"<span style='color:#888;font-size:0.85rem;'>主因 #{primary_idx}</span>",
                        unsafe_allow_html=True,
                    )
                    cand_df = pd.DataFrame(
                        [
                            {
                                "根因": c.get("root_cause"),
                                "维度": c.get("dimension"),
                                "置信度": c.get("confidence"),
                                "交叉验证": c.get("cross_validation") or "—",
                            }
                            for c in (chain.get("candidates") or [])
                        ]
                    )
                    if not cand_df.empty:
                        st.dataframe(
                            cand_df, hide_index=True, use_container_width=True
                        )
                    st.markdown("")

        # ---------- 非数据信号（边线卡片，不用色块） ----------
        sigs = result.get("non_data_signals") or []
        if sigs:
            with st.expander("非数据信号"):
                for sig in sigs:
                    affects = ", ".join(sig.get("affects_metrics") or []) or "—"
                    st.markdown(
                        f"<div class='signal-card'>{sig.get('signal', '')}"
                        f"<div class='signal-meta'>影响指标：{affects}</div></div>",
                        unsafe_allow_html=True,
                    )

        # ---------- 行动建议 ----------
        actions = result.get("actions") or []
        if actions:
            with st.expander("行动建议清单"):
                act_df = pd.DataFrame(
                    [
                        {
                            "ID": a.get("action_id"),
                            "建议": a.get("title"),
                            "对应根因": (a.get("linked_root_cause") or "")[:50],
                            "资源 URL": (a.get("resource") or {}).get("url"),
                            "性价比": a.get("cost_benefit"),
                            "置信度": a.get("confidence"),
                            "门槛": "达成"
                            if (a.get("eligibility") or {}).get("met")
                            else "未达成",
                        }
                        for a in actions
                    ]
                )
                st.dataframe(
                    act_df,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "资源 URL": st.column_config.LinkColumn(
                            "资源 URL", display_text="打开"
                        ),
                    },
                )

        # ---------- 证据引用 ----------
        refs_list = result.get("evidence_refs") or []
        if refs_list:
            with st.expander("证据引用"):
                ref_df = pd.DataFrame(
                    [
                        {
                            "refId": r.get("refId"),
                            "层": r.get("layer"),
                            "来源": r.get("sourceId"),
                            "摘要": (r.get("quoteOrSummary") or "")[:80],
                            "置信度": r.get("confidence"),
                        }
                        for r in refs_list
                    ]
                )
                st.dataframe(
                    ref_df, hide_index=True, use_container_width=True
                )

        # ---------- 节点执行轨迹 ----------
        trace = result.get("_trace") or []
        trace_df = pd.DataFrame(
            [
                {
                    "节点": t.get("node"),
                    "耗时(ms)": t.get("ms"),
                    "备注": t.get("note", ""),
                }
                for t in trace
                if isinstance(t, dict)
            ]
        )
        if not trace_df.empty:
            with st.expander("节点执行轨迹"):
                st.dataframe(
                    trace_df, hide_index=True, use_container_width=True
                )

        with st.expander("完整 final_state（调试）"):
            st.json(result)
