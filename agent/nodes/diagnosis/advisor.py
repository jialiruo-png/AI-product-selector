"""Advisor —— 行动建议专家节点。

职责（对应 agent/skills/xingdong_jianyi.md 的 SOP）：
1. 取 Attributor 产出的 root_cause_chains
2. overlay 映射：按 matched_overlays 加载对应建议模板
3. 资源匹配：每条建议挂活动 ID / 工具 / 模板
4. 准入门槛校验
5. 性价比评估 + 排序
6. 输出动作清单（禁止空建议）

mock 永不崩：无资源可挂时降级为"当前无对应资源，建议先 X"。
"""
from __future__ import annotations

from agent.evidence import make_ref
from agent.llm import chat_json, has_llm

from ..base import BaseNode

# 与 agent/wiki/industry/activity_db.md + tool_db.md 对齐的精简注册表
# 实际生产应改为 IndustryWiki.search 调用
_ACTIVITY_DB = {
    "618_nvzhuang_yure": {
        "name": "618 女装预热活动",
        "url": "activity://618_nvzhuang_yure",
        "eligibility": {"exp_score_min": 4.5, "shop_level_min": 3},
        "expected_impact": "GMV +15%~25%（活动期）",
    },
    "zibo_liuliang_2026": {
        "name": "女装自播扶持流量包",
        "url": "activity://zibo_liuliang_2026",
        "eligibility": {"exp_score_min": 4.5, "live_share_min": 0.5},
        "expected_impact": "直播间自然流量 +30%",
    },
    "brand_special_2026": {
        "name": "品牌专场 - 女装",
        "url": "activity://brand_special_2026",
        "eligibility": {"exp_score_min": 4.7, "shop_level_min": 5},
        "expected_impact": "GMV +30%~80%（专场当日）",
    },
    "summer_search_2026": {
        "name": "夏装焕新搜索流量包",
        "url": "activity://summer_search_2026",
        "eligibility": {"exp_score_min": 4.6},
        "expected_impact": "搜索流量 +25%",
    },
    "xindian_lengqidong": {
        "name": "新店冷启动流量扶持",
        "url": "activity://xindian_lengqidong",
        "eligibility": {"entry_days_max": 90, "in_sale_sku_min": 1},
        "expected_impact": "自然流量 +50%",
    },
    "xiazhuang_qingcang": {
        "name": "夏装清仓直播专场",
        "url": "activity://xiazhuang_qingcang",
        "eligibility": {"exp_score_min": 4.4},
        "expected_impact": "清仓专场流量入口",
    },
    "daily_new_arrival": {
        "name": "日常新品扶持",
        "url": "activity://daily_new_arrival",
        "eligibility": {"monthly_gmv_min": 300000},
        "expected_impact": "新品 7 天流量加权",
    },
}

_TOOL_DB = {
    "aigc_image_template_zibo_price_anchor": {
        "name": "价格锚定主图模板",
        "url": "tool://aigc_image?template=zibo_price_anchor",
        "expected_impact": "主图 CTR +30%~50%",
    },
    "title_optimizer_nvzhuang": {
        "name": "女装标题优化器",
        "url": "tool://title_optimizer?category=nvzhuang",
        "expected_impact": "搜索曝光 +10%~20%",
    },
    "shangcheng_jingxuan_apply": {
        "name": "商城精选入驻申请",
        "url": "tool://shangcheng_jingxuan_apply",
        "eligibility": {"rating_min": 4.6},
        "expected_impact": "新流量入口"
    },
    "intelligent_publish_nvzhuang_new": {
        "name": "智能上架（女装新店专版）",
        "url": "tool://intelligent_publish?category=nvzhuang_new",
        "expected_impact": "首单破冰"
    },
    "store_decoration_template": {
        "name": "店铺装修模板库",
        "url": "tool://store_decoration_template",
        "expected_impact": "装修完整度 +20pp"
    },
    "kol_match_nvzhuang": {
        "name": "达人粉丝画像匹配工具",
        "url": "tool://kol_match?category=nvzhuang",
        "expected_impact": "新合作 ROI +50%"
    },
    "jxlm_optimize": {
        "name": "精选联盟商品分层优化",
        "url": "tool://jxlm_optimize",
        "expected_impact": "精选联盟 CTR +20%"
    },
    "aigc_publish_autumn": {
        "name": "智能上架 - 秋装预售款",
        "url": "tool://aigc_publish_autumn",
        "expected_impact": "应季流量承接"
    },
    "qianchuan_plan_zibo_dress": {
        "name": "女装连衣裙千川计划模板",
        "url": "template://qianchuan_plan_zibo_dress",
        "expected_impact": "千川 ROI 回到 1.5+"
    },
    "qianchuan_autumn_pivot": {
        "name": "千川预算秋装倾斜",
        "url": "template://qianchuan_autumn_pivot",
        "expected_impact": "应季款 GMV +20%"
    },
    "live_welcome_v2": {
        "name": "直播间欢迎话术 V2",
        "url": "template://live_welcome_v2",
        "expected_impact": "人均停留 +30s"
    },
    "fudai_rhythm_001": {
        "name": "福袋节奏模板",
        "url": "template://fudai_rhythm_001",
        "expected_impact": "转粉率 +1pp"
    },
    "newbie_checklist": {
        "name": "新手任务清单",
        "url": "task://newbie_checklist",
        "expected_impact": "扶持流量激活"
    },
    "tixianfen_chongci": {
        "name": "体验分提升清单",
        "url": "task://tixianfen_chongci",
        "expected_impact": "体验分 +0.1~0.3"
    },
    "pause_low_roi_kol": {
        "name": "暂停低 ROI 达人合作",
        "url": "task://pause_low_roi_kol",
        "expected_impact": "止血 + ROI 回升"
    },
    "low_price_drainage": {
        "name": "滞销 SKU 改 9.9 引流款",
        "url": "task://low_price_drainage",
        "expected_impact": "回收资金 + 引流"
    },
    "laokek_zhaohui": {
        "name": "老客召回",
        "url": "task://laokek_zhaohui",
        "expected_impact": "复购率 +3pp"
    },
}

# 根据命中的 overlay + 主因维度 → 推荐的建议模板 ID 列表
_RECOMMENDATION_BY_OVERLAY = {
    "nvzhuang_zibo": {
        "转化类": ["live_welcome_v2", "fudai_rhythm_001", "aigc_image_template_zibo_price_anchor"],
        "流量类": ["qianchuan_plan_zibo_dress", "zibo_liuliang_2026", "618_nvzhuang_yure"],
        "履约类": ["tixianfen_chongci"],
        "货品类": ["aigc_image_template_zibo_price_anchor"],
    },
    "nvzhuang_dabo": {
        "货品类": ["pause_low_roi_kol", "kol_match_nvzhuang"],
        "流量类": ["jxlm_optimize", "brand_special_2026"],
        "转化类": ["jxlm_optimize"],
        "履约类": ["tixianfen_chongci"],
    },
    "nvzhuang_huojia": {
        "流量类": ["title_optimizer_nvzhuang", "shangcheng_jingxuan_apply", "summer_search_2026"],
        "转化类": ["title_optimizer_nvzhuang"],
        "履约类": ["tixianfen_chongci"],
        "货品类": ["title_optimizer_nvzhuang"],
    },
    "nvzhuang_xindian": {
        "货品类": ["intelligent_publish_nvzhuang_new"],
        "履约类": ["newbie_checklist", "store_decoration_template"],
        "流量类": ["xindian_lengqidong"],
        "转化类": ["store_decoration_template"],
    },
    "nvzhuang_chengzhang": {
        "流量类": ["qianchuan_plan_zibo_dress", "shangcheng_jingxuan_apply", "daily_new_arrival"],
        "货品类": ["daily_new_arrival"],
        "转化类": ["laokek_zhaohui"],
        "履约类": ["tixianfen_chongci"],
    },
    "nvzhuang_jijie": {
        "货品类": ["aigc_publish_autumn", "low_price_drainage"],
        "流量类": ["qianchuan_autumn_pivot", "xiazhuang_qingcang"],
        "转化类": ["aigc_publish_autumn"],
        "履约类": ["tixianfen_chongci"],
    },
}

# 性价比基线（与执行成本相关）
_COST_BENEFIT = {
    "template": "high",  # 话术 / 福袋模板等纯配置
    "tool": "medium",     # 工具一键跳转，需操作
    "activity": "medium",
    "task": "high",
}


def _check_eligibility(resource: dict, profile: dict) -> tuple[bool, str]:
    """校验商家是否达准入门槛。"""
    elig = resource.get("eligibility") or {}
    if not elig:
        return True, "无门槛"

    parts = []
    met = True
    if "exp_score_min" in elig:
        cur = profile.get("exp_score", 0)
        required = elig["exp_score_min"]
        if cur < required:
            met = False
            parts.append(f"体验分 {cur} < {required}，差 {round(required - cur, 2)}")
        else:
            parts.append(f"体验分 {cur} ≥ {required}")

    if "shop_level_min" in elig:
        cur_level = profile.get("shop_level", "L0")
        # L1=1, L2=2... 简化
        try:
            level_num = int(str(cur_level).lstrip("Ll"))
        except ValueError:
            level_num = 0
        required = elig["shop_level_min"]
        if level_num < required:
            met = False
            parts.append(f"等级 L{level_num} < L{required}")
        else:
            parts.append(f"等级 L{level_num} ≥ L{required}")

    if "live_share_min" in elig:
        cur = (profile.get("dau_gmv_share") or {}).get("live", 0)
        required = elig["live_share_min"]
        if cur < required:
            met = False
            parts.append(f"直播占比 {cur} < {required}")

    if "entry_days_max" in elig:
        cur = profile.get("entry_days", 9999)
        required = elig["entry_days_max"]
        if cur > required:
            met = False
            parts.append(f"入驻 {cur} 天 > {required} 天")

    if "in_sale_sku_min" in elig:
        cur = profile.get("in_sale_sku", 0)
        required = elig["in_sale_sku_min"]
        if cur < required:
            met = False
            parts.append(f"在售 SKU {cur} < {required}")

    if "monthly_gmv_min" in elig:
        cur = profile.get("monthly_gmv", 0)
        required = elig["monthly_gmv_min"]
        if cur < required:
            met = False
            parts.append(f"月销 {cur} < {required}")

    if "rating_min" in elig:
        cur = profile.get("rating") or (profile.get("metrics") or {}).get("rating", 0)
        required = elig["rating_min"]
        if cur and cur < required:
            met = False
            parts.append(f"评价分 {cur} < {required}")

    return met, "; ".join(parts) if parts else ("达标" if met else "未达标")


def _resource_kind(resource_id: str) -> tuple[str, dict]:
    """从注册表取 resource，返回 (type, info)。"""
    if resource_id in _ACTIVITY_DB:
        return "activity", _ACTIVITY_DB[resource_id]
    if resource_id in _TOOL_DB:
        info = _TOOL_DB[resource_id]
        if info["url"].startswith("template://"):
            return "template", info
        if info["url"].startswith("task://"):
            return "task", info
        return "tool", info
    return "unknown", {}


def _build_actions(
    chains: list[dict],
    overlays: list[str],
    profile: dict,
) -> tuple[list[dict], list[dict]]:
    """根据根因链 + overlay 产出动作清单，返回 (actions, refs)。"""
    actions: list[dict] = []
    refs: list[dict] = []
    seen_resource_ids: set[str] = set()

    for chain in chains:
        primary_idx = chain.get("primary_root_cause_index", 0)
        candidates = chain.get("candidates") or []
        if not candidates:
            continue
        primary = candidates[primary_idx]
        dimension = primary.get("dimension", "未分类")
        anomaly_metric = chain.get("anomaly_metric", "")

        # 对每个命中的 overlay，按维度找推荐资源
        for ov in overlays:
            recs = _RECOMMENDATION_BY_OVERLAY.get(ov, {}).get(dimension, [])
            for resource_id in recs:
                if resource_id in seen_resource_ids:
                    continue
                seen_resource_ids.add(resource_id)

                kind, info = _resource_kind(resource_id)
                if kind == "unknown":
                    continue

                met, details = _check_eligibility(info, profile)
                ref = make_ref(
                    layer="wiki",
                    source_id=f"wiki_{kind}_{resource_id}",
                    summary=info.get("name", resource_id),
                    confidence=0.85,
                )
                refs.append(ref)

                actions.append({
                    "action_id": f"act_{len(actions)+1:03d}",
                    "title": info.get("name", resource_id),
                    "linked_root_cause": primary.get("root_cause", ""),
                    "linked_anomaly_metric": anomaly_metric,
                    "resource": {
                        "type": kind,
                        "id": resource_id,
                        "url": info["url"],
                    },
                    "eligibility": {"met": met, "details": details},
                    "cost_benefit": _COST_BENEFIT.get(kind, "medium"),
                    "expected_impact": info.get("expected_impact", ""),
                    "confidence": primary.get("confidence", 0.8),
                    "evidence_refs": [ref["refId"]],
                })

    # 性价比 × 置信度排序
    cost_score = {"high": 3, "medium": 2, "low": 1}
    actions.sort(
        key=lambda a: (
            -cost_score.get(a["cost_benefit"], 1),
            -a["confidence"],
            0 if a["eligibility"]["met"] else 1,
        )
    )

    return actions, refs


# ---- LLM 增强：把"挂上的资源"翻译成商家视角的"为什么这条值得做" ----
_LLM_REASON_PROMPT = """你是抖音电商资深运营顾问。给一条建议（已包含 资源名称/类型/链接/准入状态/预期影响 + 关联根因），生成一句 ≤40 字的"为什么这条建议值得做"。

输出严格 JSON：
{
  "why_worth_it": "<≤40字的为什么>"
}

要求：
- 必须基于输入的根因和预期影响，逻辑链清楚
- 商家视角，避免行话（不要说 ROI、CTR 等术语，用"投入产出比"、"点击率"等替代）
- 优先突出"低成本 + 高确定性"
- 如果准入未达标，要先说"先把 X 做到 Y 才能用"
"""


def _llm_enhance_actions(actions: list[dict], top_n: list[int]) -> int:
    """对 TOP-N 建议调 LLM 生成"为什么值得做"。返回调用次数。"""
    if not has_llm():
        return 0
    calls = 0
    for idx in top_n:
        if idx >= len(actions):
            continue
        a = actions[idx]
        user_payload = (
            f"建议标题：{a['title']}\n"
            f"资源类型：{a['resource']['type']}\n"
            f"资源链接：{a['resource']['url']}\n"
            f"准入状态：{'达标' if a['eligibility']['met'] else '未达标 - ' + a['eligibility']['details']}\n"
            f"预期影响：{a['expected_impact']}\n"
            f"关联根因：{a['linked_root_cause']}\n"
            f"性价比评级：{a['cost_benefit']}\n"
        )
        result = chat_json(
            system=_LLM_REASON_PROMPT,
            user=user_payload,
            max_tokens=200,
            temperature=0.4,
            mock_fallback=None,
        )
        if result and not result.get("_mock") and not result.get("_parse_error"):
            why = (result.get("why_worth_it") or "").strip()
            if why:
                a["why_worth_it"] = why
                calls += 1
    return calls


class Advisor(BaseNode):
    """行动建议专家：资源匹配 + 准入校验 + 排序输出 + LLM 增强"为什么值得做"。"""

    name = "advisor"

    async def run(self, state: dict) -> dict:
        chains = state.get("root_cause_chains") or []
        overlays = state.get("matched_overlays") or []
        profile = state.get("shop_profile") or {}

        actions, refs = _build_actions(chains, overlays, profile)

        # 若没产出 action，给 fallback 提示（不许空建议）
        if not actions and chains:
            fallback_ref = make_ref(
                layer="wiki",
                source_id="wiki_fallback_no_resource",
                summary="当前根因暂无对应平台资源",
                confidence=0.6,
            )
            refs.append(fallback_ref)
            actions = [{
                "action_id": "act_fallback",
                "title": "当前根因暂无可直接挂的平台资源，建议先关注后续规则变动",
                "linked_root_cause": "fallback",
                "linked_anomaly_metric": "",
                "resource": {"type": "fallback", "id": "wait_and_watch", "url": ""},
                "eligibility": {"met": True, "details": "无门槛"},
                "cost_benefit": "high",
                "expected_impact": "观察 7-14 天后再评估",
                "confidence": 0.6,
                "evidence_refs": [fallback_ref["refId"]],
            }]

        top_n_for_user = list(range(min(5, len(actions))))

        # LLM 增强 TOP-N 建议的"为什么值得做"
        llm_calls = _llm_enhance_actions(actions, top_n_for_user)

        note = (
            f"actions={len(actions)} top_n={len(top_n_for_user)} "
            f"refs+{len(refs)} llm_calls={llm_calls}"
        )

        return {
            "actions": actions,
            "top_n_for_user": top_n_for_user,
            "evidence_refs": refs,
            "_trace": [self._trace_entry(note)],
        }
