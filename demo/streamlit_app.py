"""副窗口任务 B（CLAUDE.md §11.3）：抖店中小商家经营诊断 Agent 演示。

启动：
    streamlit run demo/streamlit_app.py

后端：实时调用 agent.graph.run_diagnosis，mock 模式。
设计：中性配色、中文术语、Altair 图表、去 emoji / 去工程标签。
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

# ============================================================
#                       全局样式
# ============================================================
st.markdown(
    """
<style>
#MainMenu, header, footer, [data-testid="stToolbar"] { visibility: hidden; height: 0; }

html, body, button, input, select, textarea, [class*="st-"] {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Segoe UI", sans-serif;
}

.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1380px; }

h1 { font-size: 1.55rem; font-weight: 600; letter-spacing: -0.01em; color: #1a1a1a; margin: 0 0 0.2rem 0; }
h2 { font-size: 1.15rem; font-weight: 600; color: #2a2a2a; margin: 1.6rem 0 0.6rem 0; }
h3 { font-size: 0.98rem; font-weight: 600; color: #3a3a3a; margin: 1.2rem 0 0.4rem 0; }
h4 { font-size: 0.9rem;  font-weight: 600; color: #4a4a4a; margin: 0.8rem 0 0.3rem 0; }

p, li { color: #333; }

/* ---------- 按钮：白底黑字描边，hover 反色 ---------- */
.stButton > button {
    background-color: #ffffff !important;
    color: #1a1a1a !important;
    border: 1px solid #1a1a1a !important;
    border-radius: 4px;
    font-weight: 500;
    padding: 0.45rem 1.4rem;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    background-color: #1a1a1a !important;
    color: #ffffff !important;
    border-color: #1a1a1a !important;
}
.stButton > button:focus, .stButton > button:active {
    box-shadow: none !important;
    outline: none !important;
    background-color: #1a1a1a !important;
    color: #ffffff !important;
}
.stButton > button p, .stButton > button span, .stButton > button div {
    color: inherit !important;
    margin: 0;
}

/* ---------- expander ---------- */
[data-testid="stExpander"] details {
    border: 1px solid #ececec;
    border-radius: 4px;
    background: #fdfdfd;
}
[data-testid="stExpander"] summary {
    font-weight: 500;
    color: #333;
    padding: 0.55rem 1rem;
}

/* ---------- blockquote 改左边竖线，不用色块 ---------- */
blockquote {
    border-left: 3px solid #d4d4d4;
    color: #555;
    padding: 0.15rem 0 0.15rem 1rem;
    margin: 0.6rem 0;
    background: transparent;
}

/* ---------- 自定义 metric 卡片：等高、纯灰白 ---------- */
.metric-card {
    border: 1px solid #e8e8e8;
    border-radius: 4px;
    padding: 0.85rem 1rem;
    background: #fff;
    min-height: 92px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.metric-card .label {
    font-size: 0.72rem;
    color: #888;
    letter-spacing: 0.02em;
    margin-bottom: 0.35rem;
}
.metric-card .value {
    font-size: 1.35rem;
    font-weight: 600;
    color: #1a1a1a;
    line-height: 1.2;
}
.metric-card .sub {
    font-size: 0.78rem;
    color: #888;
    margin-top: 0.25rem;
}

/* ---------- 通用引用 / 信号卡 ---------- */
.signal-card {
    border-left: 3px solid #999;
    padding: 0.6rem 0.95rem;
    background: #fafafa;
    margin: 0.4rem 0;
    font-size: 0.92rem;
    color: #333;
    border-radius: 0 4px 4px 0;
}
.signal-card .signal-meta {
    color: #888;
    font-size: 0.8rem;
    margin-top: 0.25rem;
}

.wiki-item {
    border: 1px solid #ececec;
    border-radius: 4px;
    padding: 0.55rem 0.9rem;
    background: #fcfcfc;
    margin: 0.35rem 0;
    font-size: 0.88rem;
    color: #333;
}
.wiki-item .wiki-tag {
    display: inline-block;
    font-size: 0.72rem;
    color: #666;
    background: #f0f0f0;
    padding: 0.05rem 0.5rem;
    border-radius: 2px;
    margin-right: 0.5rem;
}

.muted-hint { color: #999; padding: 2rem 0 0; font-size: 0.92rem; }
.subtitle   { color: #888; font-size: 0.88rem; margin-top: -0.2rem; }

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

# ============================================================
#                  文本清理（emoji + 工程标签）
# ============================================================
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F6FF"
    "\U0001F7E0-\U0001F7FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "☀-➿"
    "️"
    "]+",
    flags=re.UNICODE,
)

EVIDENCE_MARK_RE = re.compile(r"\s*\[ev_[a-f0-9]+\]")

# §9.1 去 jargon：composer.py / attributor.py 仍输出"当前/基线/偏离/置信度"，渲染层替换为商家话。
_ANOMALY_LINE_RE = re.compile(r"当前\s*([^/]+?)\s*/\s*基线\s*([^/]+?)\s*/\s*偏离\s*([\-+]?[\d.]+)\s*%")
_CONFIDENCE_TAIL_RE = re.compile(r"\s*[·•・]\s*置信度\s*[\d.]+")
_ROOT_CAUSE_HEAD_RE = re.compile(r"^###\s*异常指标：\s*(.+)$", re.MULTILINE)
# attributor.py 把 root cause 写成「X（cur）显著偏离类目基线（base）」/「X 同期异动（cur），存在相关性」
_ROOT_CAUSE_DEVIATE_RE = re.compile(r"(\S+?)（([^）]+)）显著偏离类目基线（([^）]+)）")
_ROOT_CAUSE_COVAR_RE = re.compile(r"(\S+?)同期异动（([^）]+)），存在相关性")
_BASELINE_BARE_RE = re.compile(r"类目基线")
_DEVIATE_BARE_RE = re.compile(r"偏离基线")


def clean_report(text: str) -> str:
    """商家可读化：去 emoji 装饰、去工程哈希标签、把 jargon 替换成老板话。"""
    if not text:
        return text
    out = EMOJI_RE.sub("", text)
    out = EVIDENCE_MARK_RE.sub("", out)
    # §9.1 第 2 条「拟人化对比」：当前/基线/偏离 → 你的/同行/差距
    out = _ANOMALY_LINE_RE.sub(r"你的 \1 · 同行 \2 · 差距 \3%", out)
    # §9.1 第 3/4 条精神：商家不在意置信度，整段删掉
    out = _CONFIDENCE_TAIL_RE.sub("", out)
    out = out.replace("按性价比 × 置信度排序", "按投入产出排序")
    out = out.replace("性价比 × 置信度", "投入产出")
    # 根因文本里 attributor.py 写的 jargon
    out = _ROOT_CAUSE_DEVIATE_RE.sub(r"\1 你做到 \2 · 同行 \3", out)
    out = _ROOT_CAUSE_COVAR_RE.sub(r"\1 同时也在变（你: \2），可能是连带原因", out)
    out = _BASELINE_BARE_RE.sub("同行水平", out)
    out = _DEVIATE_BARE_RE.sub("差距", out)
    # 标题人话化
    out = _ROOT_CAUSE_HEAD_RE.sub(r"### \1 偏弱（需要关注）", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"^([#\-\*>]+) +", r"\1 ", out, flags=re.MULTILINE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = translate_overlays_in_text(out)
    return out.strip() + "\n"


# ============================================================
#                  字段中文化（demo 层本地表）
# ============================================================
METRIC_ZH = {
    "gmv": "成交金额", "uv": "访客数",
    "cvr": "每 100 人下单数（转化率）",
    "aov": "客单价",
    "refund_rate": "每 100 单退款数（退款率）",
    "exp_score": "体验分", "rating": "评价分",
    "monthly_gmv": "月销 GMV",
    "live_room_stay_sec": "直播间停留秒数",
    "fanzhuan_rate": "转粉率",
    "uv_value": "访客价值", "main_image_ctr": "主图点击率",
    "qianchuan_roi": "千川每花 100 元换回（投产比）",
    "search_ctr": "搜索点击率", "search_exposure": "搜索曝光",
    "mall_share": "商城频道占比",
    "kol_roi": "达人坑位 ROI", "kol_keng_wei_roi": "达人坑位 ROI",
    "kol_collab_count": "达人合作数", "kol_commission_rate": "达人佣金率",
    "jxlm_ctr": "精选联盟点击率", "jingxuan_lianmeng_ctr": "精选联盟点击率",
    "single_channel_share": "单渠道流量占比",
    "new_sku_sell_rate": "新品动销率", "repurchase_rate": "复购率",
    "in_sale_sku": "在售商品数", "newbie_progress": "新手任务完成度",
    "decoration_pct": "店铺装修完整度",
    "stale_inventory_pct": "滞销库存占比", "season_sku_count": "应季 SKU 数",
}
SEVERITY_ZH = {"high": "高", "medium": "中", "low": "低"}
COST_ZH = {"high": "高", "medium": "中", "low": "低"}
RESOURCE_TYPE_ZH = {
    "activity": "平台活动",
    "tool": "官方工具",
    "template": "话术 / 模板",
    "task": "任务清单",
}
OVERLAY_ZH = {
    "nvzhuang_zibo": "女装自播店",
    "nvzhuang_dabo": "女装达播店",
    "nvzhuang_huojia": "女装货架店",
    "nvzhuang_xindian": "女装新店冷启动",
    "nvzhuang_chengzhang": "女装成长期",
    "nvzhuang_jijie": "女装季节切换",
}


def metric_zh(key):
    if not key:
        return "—"
    return METRIC_ZH.get(key, key)


def overlay_zh(key):
    if not key:
        return "—"
    return OVERLAY_ZH.get(key, key)


def translate_overlays_in_text(text: str) -> str:
    if not text:
        return text
    for k, v in OVERLAY_ZH.items():
        text = text.replace(k, v)
    return text


# ============================================================
#                       数据加载
# ============================================================
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


def wiki_category(quote: str) -> str:
    """按 quote 内容粗分 Wiki 引用类别（sourceId 在主窗口当前实现里为 None）。"""
    q = quote or ""
    if "类目基线" in q or "基线" in q:
        return "类目基线"
    if "规则" in q or "频道升级" in q or "类目定向" in q or "调整" in q or "频道" in q:
        return "规则变动"
    if "活动" in q or "扶持" in q or "专场" in q or "预热" in q:
        return "平台活动"
    if "模板" in q or "工具" in q or "话术" in q or "申请" in q:
        return "工具 / 模板"
    return "其他"


# ============================================================
#                       左侧栏
# ============================================================
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
        f"**预期画像**　{' / '.join(overlay_zh(o) for o in data.get('_overlay_hints', [])) or '—'}"
    )
    st.markdown("---")
    user_query = st.text_input("诊断问题", value="我店铺最近 GMV 跌了")
    window = st.selectbox("窗口", ["7d", "30d"], index=0)


# ============================================================
#                       顶部标题
# ============================================================
st.markdown("# 经营诊断 · 中小商家版")
st.markdown(
    "<div class='subtitle'>V1 演示　·　女装类目　·　老板视角（去专业词）</div>",
    unsafe_allow_html=True,
)
st.markdown("")

# ============================================================
#                  商家画像 + 诊断报告 两栏
# ============================================================
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
- **入驻**　{profile.get('entry_days', 0)} 天　·　等级 {profile.get('shop_level', '—')}
- **体验分**　{profile.get('exp_score', 0)}　（准入线 {profile.get('exp_score_threshold', 4.5)}）
- **月销**　{monthly_gmv:,} 元　（上月 {monthly_gmv_prev:,}）
- **阶段**　{profile.get('stage', '—')}
"""
    )

    share = profile.get("dau_gmv_share") or {}
    if share:
        st.markdown("#### 流量来源")
        share_df = pd.DataFrame(
            [
                {"渠道": k, "占比": v}
                for k, v in share.items()
                if isinstance(v, (int, float))
            ]
        ).sort_values("占比", ascending=True)
        if not share_df.empty:
            traffic_chart = (
                alt.Chart(share_df)
                .mark_bar(color="#5a5a5a", cornerRadius=2, size=14)
                .encode(
                    x=alt.X(
                        "占比:Q",
                        axis=alt.Axis(
                            format=".0%", grid=False, title=None,
                            labelColor="#888",
                        ),
                    ),
                    y=alt.Y(
                        "渠道:N", sort="-x",
                        axis=alt.Axis(title=None, labelColor="#333"),
                    ),
                    tooltip=[
                        alt.Tooltip("渠道:N"),
                        alt.Tooltip("占比:Q", format=".1%"),
                    ],
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
        # ---------- 顶部 4 个 metric（凸显 Wiki） ----------
        completeness = (result.get("data_completeness") or 0) * 100
        overlays = (
            " / ".join(overlay_zh(o) for o in (result.get("matched_overlays") or []))
            or "—"
        )
        evidence_refs = result.get("evidence_refs") or []
        raw_n = sum(1 for r in evidence_refs if r.get("layer") == "raw")
        wiki_n = sum(1 for r in evidence_refs if r.get("layer") == "wiki")

        mc1, mc2, mc3, mc4 = st.columns(4)
        for col, label, val, sub in (
            (mc1, "数据完整度", f"{completeness:.0f}%", "店铺数据覆盖率"),
            (mc2, "命中商家画像", overlays, "类目 overlay 自动匹配"),
            (mc3, "数据证据", str(raw_n), "来自经营指标 / 罗盘"),
            (mc4, "知识引用", str(wiki_n), "来自行业 Wiki / 规则库"),
        ):
            col.markdown(
                f"<div class='metric-card'><div class='label'>{label}</div>"
                f"<div class='value'>{val}</div>"
                f"<div class='sub'>{sub}</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("")

        # ---------- 主报告（去 emoji + 去 [ev_xxx] 工程标签） ----------
        st.markdown(clean_report(result.get("report") or "(空报告)"))

        st.markdown("---")
        st.markdown(
            "<div class='subtitle'>以下为结构化下钻视图，可在追问时展开。</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")

        # ---------- 异常指标可视化 ----------
        anomalies = result.get("anomalies") or []
        if anomalies:
            with st.expander("异常指标可视化"):
                an_df = pd.DataFrame(
                    [
                        {
                            "指标": metric_zh(a.get("metric")),
                            "指标 key": a.get("metric"),
                            "差距 (%)": a.get("deviation_vs_baseline_pct", 0),
                            "_severity_key": a.get("severity") or "low",
                            "你的": a.get("current"),
                            "同行做到": a.get("baseline"),
                        }
                        for a in anomalies
                    ]
                ).sort_values("差距 (%)")

                anomaly_chart = (
                    alt.Chart(an_df)
                    .mark_bar(cornerRadius=3, size=18, color="#8c4a3c")
                    .encode(
                        x=alt.X(
                            "差距 (%):Q",
                            axis=alt.Axis(
                                format="+.0f",
                                title="你和同行的差距 (%)",
                                titleColor="#666",
                                titleFontSize=11,
                                grid=True,
                                gridColor="#f0f0f0",
                                labelColor="#666",
                            ),
                        ),
                        y=alt.Y(
                            "指标:N",
                            sort=alt.SortField("差距 (%)", order="ascending"),
                            axis=alt.Axis(
                                title=None, labelColor="#333", labelFontSize=12,
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip("指标:N"),
                            alt.Tooltip("你的:Q"),
                            alt.Tooltip("同行做到:Q"),
                            alt.Tooltip("差距 (%):Q", format="+.1f"),
                        ],
                    )
                    .properties(height=max(180, 38 * len(an_df)))
                    .configure_view(strokeWidth=0)
                    .configure_axis(domainColor="#dcdcdc", tickColor="#dcdcdc")
                )
                st.altair_chart(anomaly_chart, use_container_width=True)

        # ---------- 根因链下钻 ----------
        chains = result.get("root_cause_chains") or []
        if chains:
            with st.expander("根因链下钻"):
                for chain in chains:
                    primary_idx = chain.get("primary_root_cause_index", 0)
                    metric_name = metric_zh(chain.get("anomaly_metric"))
                    st.markdown(
                        f"**{metric_name}**　"
                        f"<span style='color:#888;font-size:0.85rem;'>主因 #{primary_idx + 1}</span>",
                        unsafe_allow_html=True,
                    )
                    cand_df = pd.DataFrame(
                        [
                            {
                                "根因": c.get("root_cause"),
                                "类别": c.get("dimension"),
                                "另外查到的线索": c.get("cross_validation") or "—",
                            }
                            for c in (chain.get("candidates") or [])
                        ]
                    )
                    if not cand_df.empty:
                        st.dataframe(
                            cand_df,
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "根因": st.column_config.TextColumn(width="large"),
                                "类别": st.column_config.TextColumn(width="small"),
                                "另外查到的线索": st.column_config.TextColumn(width="medium"),
                            },
                        )
                    st.markdown("")

        # ---------- 非数据信号 ----------
        sigs = result.get("non_data_signals") or []
        if sigs:
            with st.expander("非数据信号（规则 / 玩法变动）"):
                for sig in sigs:
                    affects_keys = sig.get("affects_metrics") or []
                    affects = "、".join(metric_zh(k) for k in affects_keys) or "—"
                    st.markdown(
                        f"<div class='signal-card'>{sig.get('signal', '')}"
                        f"<div class='signal-meta'>影响指标：{affects}</div></div>",
                        unsafe_allow_html=True,
                    )

        # ---------- 行动建议（商家友好版） ----------
        actions = result.get("actions") or []
        if actions:
            with st.expander("行动建议清单"):
                act_df = pd.DataFrame(
                    [
                        {
                            "建议": a.get("title"),
                            "资源类型": RESOURCE_TYPE_ZH.get(
                                (a.get("resource") or {}).get("type"),
                                (a.get("resource") or {}).get("type") or "—",
                            ),
                            "投入产出": COST_ZH.get(a.get("cost_benefit"), "—"),
                            "你够格吗": "够"
                            if (a.get("eligibility") or {}).get("met")
                            else "差一点",
                            "立刻去做": (a.get("resource") or {}).get("url"),
                        }
                        for a in actions
                    ]
                )
                st.dataframe(
                    act_df,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "建议": st.column_config.TextColumn(width="large"),
                        "资源类型": st.column_config.TextColumn(width="small"),
                        "投入产出": st.column_config.TextColumn(width="small"),
                        "你够格吗": st.column_config.TextColumn(width="small"),
                        "立刻去做": st.column_config.LinkColumn(
                            "立刻去做", display_text="打开", width="small"
                        ),
                    },
                )

        # ---------- Wiki 命中条目（凸显双层知识检索） ----------
        wiki_refs = [r for r in evidence_refs if r.get("layer") == "wiki"]
        if wiki_refs:
            with st.expander(f"Wiki 命中条目（{len(wiki_refs)} 条 · 双层知识检索）"):
                grouped: dict[str, list[str]] = {}
                for r in wiki_refs:
                    cat = wiki_category(r.get("quoteOrSummary") or "")
                    grouped.setdefault(cat, []).append(r.get("quoteOrSummary") or "")
                for cat in ("类目基线", "规则变动", "平台活动", "工具 / 模板", "其他"):
                    quotes = grouped.get(cat) or []
                    if not quotes:
                        continue
                    st.markdown(f"**{cat}**（{len(quotes)} 条）")
                    for q in quotes:
                        st.markdown(
                            f"<div class='wiki-item'>"
                            f"<span class='wiki-tag'>{cat}</span>{q}</div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown("")

        # ---------- 节点执行轨迹 ----------
        NODE_ZH = {
            "checker": "体检（异常识别）",
            "attributor": "归因（根因拆解）",
            "advisor": "建议（资源挂钩）",
            "composer": "组装（生成报告）",
        }
        trace = result.get("_trace") or []
        trace_df = pd.DataFrame(
            [
                {
                    "节点": NODE_ZH.get(t.get("node"), t.get("node")),
                    "耗时 (ms)": t.get("ms"),
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
