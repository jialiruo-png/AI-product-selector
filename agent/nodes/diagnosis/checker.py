"""Checker —— 经营诊断专家节点（诊断子图入口）。

职责（对应 agent/skills/jingying_zhenduan.md 的 SOP）：
1. 取数：读 mock 商家 JSON 拿 shop_profile + shop_metrics
2. 类目归属：判定命中哪几个女装 overlay
3. 基线对照：从 IndustryWiki / category_baseline 取基线
4. 异常识别：偏离 ≥ 20% 标记为异常
5. 严重度评级 + 路由决策

mock 永不崩：缺 shop_id 或 mock JSON 不存在时降级到通用 fallback。
"""
from __future__ import annotations

import json
from pathlib import Path

from agent.evidence import make_ref

from ..base import BaseNode, is_mock

# mock 商家数据目录
_MOCK_DIR = Path(__file__).resolve().parents[2] / "mocks" / "shops"

# 异常阈值（偏离比例）
_HIGH_SEVERITY = 0.50
_MED_SEVERITY = 0.20


def _load_mock_shop(shop_id: str) -> dict:
    """加载 mock 商家数据。case_1..5 的 shop_id 都映射到对应 JSON。"""
    # 优先尝试 case_<id>.json，然后尝试 shop_id 直接命名
    candidates = [
        _MOCK_DIR / f"{shop_id}.json",
        _MOCK_DIR / f"case_{shop_id.replace('mock_shop_00', '')}.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
    return {}


def _classify_overlays(profile: dict, metrics_7d: dict) -> list[str]:
    """根据店铺画像 + 7d 数据，判定命中哪几个女装 overlay。"""
    overlays: list[str] = []
    category = (profile.get("category") or "").lower()
    if "女装" not in category:
        # 非女装直接返回货架兜底
        return ["nvzhuang_huojia"]

    entry_days = profile.get("entry_days", 999)
    monthly_gmv = profile.get("monthly_gmv", 0)
    share = profile.get("dau_gmv_share", {}) or {}
    live_share = share.get("live", 0)
    kol_share = share.get("kol_live", 0) or share.get("dabo", 0)
    huojia_share = (share.get("search", 0) or 0) + (share.get("mall", 0) or 0)

    # 阶段维度
    if entry_days <= 90:
        overlays.append("nvzhuang_xindian")
    elif 300_000 <= monthly_gmv <= 3_000_000:
        overlays.append("nvzhuang_chengzhang")

    # 模式维度
    if live_share >= 0.6:
        overlays.append("nvzhuang_zibo")
    elif kol_share >= 0.5:
        overlays.append("nvzhuang_dabo")
    elif huojia_share >= 0.6:
        overlays.append("nvzhuang_huojia")

    # 季节维度（mock：8 月作为夏秋切换窗口示意）
    if profile.get("season_alert_flag"):
        overlays.append("nvzhuang_jijie")

    return overlays or ["nvzhuang_huojia"]


# 字段别名映射：副窗口 mock JSON 用的真实抖店字段名 -> 内部基线 key
# 适配多种命名约定，让基线检查更鲁棒
_METRIC_ALIASES = {
    # 达播店字段（副窗口用了完整中文拼音，更贴近真实业务）
    "kol_keng_wei_roi": "kol_roi",
    "jingxuan_lianmeng_ctr": "jxlm_ctr",
    # 新店店字段（副窗口放在 newbie_progress 子对象）
    "online_sku_count": "in_sale_sku",
    "newbie_task_completion_rate": "newbie_progress",
    # 自播店字段同义（副窗口可能用别名）
    "live_avg_stay_sec": "live_room_stay_sec",
    "live_fans_conversion_rate": "fanzhuan_rate",
}


def _normalize_metrics(raw: dict, extras: dict | None = None) -> dict:
    """字段别名归一化 + 合并 newbie_progress / kol_metrics 等子对象。

    返回单层扁平 dict，key 全部是 _BASELINE 期望的名字。
    """
    out: dict = {}
    # 主表
    for k, v in (raw or {}).items():
        k2 = _METRIC_ALIASES.get(k, k)
        out[k2] = v
    # 合并 extras（如 newbie_progress、kol_metrics、sku_inventory 等子对象）
    for sub in (extras or {}).values():
        if not isinstance(sub, dict):
            continue
        for k, v in sub.items():
            k2 = _METRIC_ALIASES.get(k, k)
            if isinstance(v, (int, float)):
                out.setdefault(k2, v)  # 已有同名以主表为准
    return out


# 类目基线（与 agent/wiki/industry/category_baseline.md 对齐的最小子集）
_BASELINE = {
    "nvzhuang_zibo": {
        "cvr": 0.024,
        "live_room_stay_sec": 60,
        "fanzhuan_rate": 0.03,
        "uv_value": 8.0,
        "main_image_ctr": 0.075,
        "qianchuan_roi": 1.8,
        "refund_rate": 0.075,
        "exp_score": 4.6,
    },
    "nvzhuang_dabo": {
        "kol_roi": 2.0,
        "jxlm_ctr": 0.035,
        "cvr": 0.026,
        "exp_score": 4.7,
    },
    "nvzhuang_huojia": {
        "search_ctr": 0.055,
        "cvr": 0.029,
        "rating": 4.7,
        "mall_share": 0.15,
    },
    "nvzhuang_xindian": {
        "in_sale_sku": 1,
        "newbie_progress": 0.8,
        "decoration_pct": 0.9,
    },
    "nvzhuang_chengzhang": {
        "single_channel_share": 0.6,
        "qianchuan_roi": 1.8,
        "new_sku_sell_rate": 0.4,
        "repurchase_rate": 0.15,
        "uv_value": 10.0,
    },
    "nvzhuang_jijie": {
        "stale_inventory_pct": 0.15,
        "season_sku_count": 30,
    },
}


def _detect_anomalies(
    metrics_7d: dict,
    metrics_prev_7d: dict,
    overlays: list[str],
) -> tuple[list[dict], list[dict]]:
    """识别异常指标。返回 (anomalies, evidence_refs)。"""
    anomalies: list[dict] = []
    refs: list[dict] = []

    if not metrics_7d:
        return anomalies, refs

    # 合并所有命中 overlay 的基线（同字段取最严格 = 取最高基线）
    baseline: dict = {}
    for ov in overlays:
        for k, v in _BASELINE.get(ov, {}).items():
            if k not in baseline or v > baseline[k]:
                baseline[k] = v

    for metric, baseline_val in baseline.items():
        current = metrics_7d.get(metric)
        if current is None:
            continue
        prev = metrics_prev_7d.get(metric) if metrics_prev_7d else None

        # 双口径偏离：vs 上 7 天 + vs 类目基线
        dev_vs_baseline = (current - baseline_val) / baseline_val if baseline_val else 0
        dev_vs_prev = (current - prev) / prev if prev else 0

        # 用最大绝对偏离判定严重度（仅当偏离对店铺不利方向）
        # 大部分指标越高越好；退款率/滞销库存反向。
        is_lower_better = metric in {"refund_rate", "stale_inventory_pct"}
        unfavorable_dev = (
            -dev_vs_baseline if not is_lower_better else dev_vs_baseline
        )

        if unfavorable_dev < _MED_SEVERITY:
            continue  # 没超阈值，跳过

        severity = "high" if unfavorable_dev >= _HIGH_SEVERITY else "medium"

        ref_baseline = make_ref(
            layer="wiki",
            source_id=f"wiki_baseline_{overlays[0]}_{metric}",
            summary=f"{metric} 类目基线: {baseline_val}",
            confidence=0.9,
        )
        ref_shop = make_ref(
            layer="raw",
            source_id=f"shop_metrics_{metric}",
            summary=f"{metric} 当前: {current}, 上 7 天: {prev}",
            confidence=0.95,
        )
        refs.extend([ref_baseline, ref_shop])

        anomalies.append({
            "metric": metric,
            "current": current,
            "prev": prev,
            "baseline": baseline_val,
            "deviation_vs_baseline_pct": round(dev_vs_baseline * 100, 1),
            "deviation_vs_prev_pct": round(dev_vs_prev * 100, 1),
            "severity": severity,
            "evidence_refs": [ref_baseline["refId"], ref_shop["refId"]],
        })

    # 按严重度排序：high 在前
    anomalies.sort(key=lambda a: 0 if a["severity"] == "high" else 1)
    return anomalies, refs


def _summary_for(anomalies: list[dict], overlays: list[str]) -> str:
    """生成一句话核心问题（≤ 30 字）。"""
    if not anomalies:
        return "店铺核心指标健康，未发现显著异常"
    top = anomalies[0]
    metric = top["metric"]
    direction = "下跌" if top["deviation_vs_baseline_pct"] < 0 else "异常"
    overlay_hint = overlays[0].replace("nvzhuang_", "") if overlays else ""
    return f"{metric} 显著{direction}（{abs(top['deviation_vs_baseline_pct'])}%）"[:30]


class Checker(BaseNode):
    """经营诊断专家：异常识别 + overlay 归属 + 路由决策。"""

    name = "checker"

    async def run(self, state: dict) -> dict:
        shop_id = state.get("shop_id") or ""
        existing_profile = state.get("shop_profile") or {}

        # 1. 取数：优先用 state 传入，没有则查 mock JSON
        if existing_profile and state.get("shop_metrics"):
            shop_data = {
                "shop_profile": existing_profile,
                "metrics_7d": state.get("shop_metrics", {}).get("metrics_7d", {}),
                "metrics_prev_7d": state.get("shop_metrics", {}).get("metrics_prev_7d", {}),
            }
        else:
            shop_data = _load_mock_shop(shop_id) if (is_mock() or shop_id) else {}

        profile = shop_data.get("shop_profile") or existing_profile or {}
        raw_metrics_7d = shop_data.get("metrics_7d") or {}
        raw_metrics_prev_7d = shop_data.get("metrics_prev_7d") or {}

        # 拉取可能含子指标的扩展对象（副窗口 mock JSON 里把新店/达播/季节
        # 相关数据放在独立子键中）
        extras_7d = {
            "newbie_progress": shop_data.get("newbie_progress"),
            "live_room_metrics": shop_data.get("live_room_metrics"),
            "kol_metrics": shop_data.get("kol_metrics"),
            "sku_inventory": shop_data.get("sku_inventory"),
            "fulfillment_metrics": shop_data.get("fulfillment_metrics"),
        }

        # 把"基础指标 + 扩展子对象"合并归一化为单层扁平 dict
        metrics_7d = _normalize_metrics(raw_metrics_7d, extras_7d)
        metrics_prev_7d = _normalize_metrics(raw_metrics_prev_7d, None)

        # 把 shop_profile 里的关键字段也下放到 metrics 里，方便基线检查
        for k in ("exp_score", "in_sale_sku", "monthly_gmv"):
            if k in profile and k not in metrics_7d:
                metrics_7d[k] = profile[k]

        # 2. 类目归属
        overlays = _classify_overlays(profile, metrics_7d)

        # 3 + 4. 异常识别（含基线对照）
        anomalies, refs = _detect_anomalies(metrics_7d, metrics_prev_7d, overlays)

        # 5. 严重度 + 一句话总结
        summary = _summary_for(anomalies, overlays)

        # 6. 数据完整度（已传入字段数 / 期望 8 个核心字段）
        expected_fields = 8
        data_completeness = min(1.0, len(metrics_7d) / expected_fields) if metrics_7d else 0.0

        note = (
            f"shop={shop_id or profile.get('shop_id','?')} "
            f"overlays={overlays} 异常={len(anomalies)} 完整度={data_completeness:.2f}"
        )

        return {
            "shop_profile": profile,
            "shop_metrics": {
                "metrics_7d": metrics_7d,
                "metrics_prev_7d": metrics_prev_7d,
            },
            "diagnosis_summary": summary,
            "anomalies": anomalies,
            "matched_overlays": overlays,
            "data_completeness": round(data_completeness, 2),
            "evidence_refs": refs,
            "_trace": [self._trace_entry(note)],
        }
