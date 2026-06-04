"""商家私有 Wiki overlay（PRD 1.3 下层：租户私有，可增长）。

商家导入的 SKU 详情 / 卖点 / FAQ / 自定义 SOP，按 seller_id 租户隔离。
MVP 用内存 dict 模拟（对应未来的 SQLite `wiki_pages` 表）。
"""
from __future__ import annotations


class SellerWiki:
    """按 seller_id 隔离的商家私有知识 overlay。"""

    def __init__(self) -> None:
        # seller_id -> {key: page}
        self._tenants: dict[str, dict[str, dict]] = {}

    def add_page(self, seller_id: str, key: str, content: dict) -> dict:
        page = {"key": key, "seller_id": seller_id, **content}
        self._tenants.setdefault(seller_id, {})[key] = page
        return page

    def get(self, seller_id: str, key: str) -> dict | None:
        return self._tenants.get(seller_id, {}).get(key)

    def search(self, seller_id: str, q: str) -> list[dict]:
        ql = (q or "").lower()
        pages = self._tenants.get(seller_id, {})
        hits: list[dict] = []
        for page in pages.values():
            blob = " ".join(str(v) for v in page.values()).lower()
            if ql and ql in blob:
                hits.append(page)
        return hits

    def keys(self, seller_id: str) -> list[str]:
        return list(self._tenants.get(seller_id, {}).keys())
