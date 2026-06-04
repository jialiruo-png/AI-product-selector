"""指标英文 key → 中文标签映射。

Composer / Checker / Attributor 渲染面向商家的文本时统一调 metric_zh()，
让报告里不再出现 "stale_inventory_pct" 这种工程黑话。

未在表里的字段返回原 key，避免误翻译。
"""
from __future__ import annotations

_ZH: dict[str, str] = {
    # 经营核心
    "gmv": "成交金额",
    "uv": "访客数",
    "cvr": "转化率",
    "aov": "客单价",
    "refund_rate": "退款率",
    "exp_score": "体验分",
    "rating": "评价分",
    "monthly_gmv": "月销 GMV",
    # 直播间
    "live_room_stay_sec": "直播间人均停留",
    "fanzhuan_rate": "转粉率",
    "uv_value": "访客价值",
    "main_image_ctr": "主图点击率",
    # 千川 / 投流
    "qianchuan_roi": "千川投产比",
    # 搜索 / 货架
    "search_ctr": "搜索点击率",
    "mall_share": "商城频道占比",
    # 达播
    "kol_roi": "达人坑位 ROI",
    "kol_collab_count": "达人合作数",
    "kol_commission_rate": "达人佣金率",
    "jxlm_ctr": "精选联盟点击率",
    # 成长期
    "single_channel_share": "单渠道流量占比",
    "new_sku_sell_rate": "新品动销率",
    "repurchase_rate": "复购率",
    # 新店
    "in_sale_sku": "在售商品数",
    "newbie_progress": "新手任务完成度",
    "decoration_pct": "店铺装修完整度",
    # 季节切换
    "stale_inventory_pct": "滞销库存占比",
    "season_sku_count": "应季 SKU 数",
}


def metric_zh(key: str) -> str:
    """返回中文标签，未登记则原样返回。"""
    return _ZH.get(key, key)


def metric_zh_with_key(key: str) -> str:
    """返回 '中文（英文）' 形式，给需要标注原字段的场景用。"""
    zh = _ZH.get(key)
    if zh and zh != key:
        return f"{zh}"
    return key


def is_lower_better(key: str) -> bool:
    """指标是否"越低越好"（用于方向描述）。"""
    return key in {"refund_rate", "stale_inventory_pct"}
