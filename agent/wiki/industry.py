"""行业 Wiki（PRD 1.3 上层：平台预编译，只读）。

MVP 最小集（融合方案 第 6 节）：TikTok Shop 选品打分口径、
价格带诊断 SOP、爆款元素清单。后续由平台知识工程团队按 version
release 扩充，此处仅做只读种子。
"""
from __future__ import annotations


# 只读种子知识。key 为业务可读的检索键。
_SEED: dict[str, dict] = {
    "打分口径": {
        "key": "打分口径",
        "title": "TikTok Shop 选品打分口径",
        "summary": "搜索端免费字段 min-max 归一化后加权求和。",
        "weights": {
            "销量": 0.40,
            "评分": 0.25,
            "评论": 0.20,
            "价格": 0.15,
        },
        "note": "权重对齐 score.py；价格走分位（越贴近机会带越高分）。",
    },
    "价格带诊断": {
        "key": "价格带诊断",
        "title": "价格带诊断 SOP",
        "summary": "对 TOP300 候选做价格分布直方，定位供给稀疏的空窗机会带。",
        "sop": [
            "取关键词 TOP300 商品价格",
            "分箱统计每价格带的商品数与销量",
            "找『需求有、供给少』的空窗带",
            "输出推荐切入价格带 + 理由",
        ],
    },
    "爆款元素清单": {
        "key": "爆款元素清单",
        "title": "爆款元素清单",
        "summary": "主图/卖点拆解的四类核心元素。",
        "elements": ["颜色", "材质", "价格", "卖点"],
    },
}


class IndustryWiki:
    """只读行业 Wiki。"""

    def __init__(self, seed: dict[str, dict] | None = None) -> None:
        self._pages: dict[str, dict] = dict(seed if seed is not None else _SEED)

    def get(self, key: str) -> dict | None:
        return self._pages.get(key)

    def search(self, q: str) -> list[dict]:
        """子串匹配 key / title / summary。"""
        ql = (q or "").lower()
        hits: list[dict] = []
        for page in self._pages.values():
            blob = f"{page.get('key','')}{page.get('title','')}{page.get('summary','')}".lower()
            if ql and ql in blob:
                hits.append(page)
        return hits

    def keys(self) -> list[str]:
        return list(self._pages.keys())
