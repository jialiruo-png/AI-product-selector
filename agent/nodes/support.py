"""客服 Agent（◐ 档，SellerWiki 检索 + LLM 润色）。

PRD D1：商家私域 FAQ 知识 → 检索命中 + LLM 润色应答。
体现「商家私有 Wiki overlay → RAG 应答」这条折中路径——不依赖真实订单/
退换货 API，靠商家自己导入的 FAQ/政策页回答。

应答策略：
    1. SellerWiki.search(seller_id, question) 召回 Top-K 命中页 → 拼检索上下文。
    2. llm.available() 时用 chat_text 把上下文 + 问题润色成自然客服话术。
    3. 缺 key / mock / LLM 失败 / 无命中 → 回退：有命中拼原文，无命中礼貌兜底。
       —— mock 永不崩。
"""
from __future__ import annotations

import re

from agent import llm
from agent.skills.loader import load_skill_prompt
from agent.state import new_evidence_ref

from .base import BaseNode

# C1：客服角色/SOP 从 kefu.md 读，注入 LLM system 前缀（改 MD 行为跟着变）。
_SKILL_PREFIX = load_skill_prompt("客服")

_SUPPORT_SYSTEM = """你是电商店铺的金牌客服。依据【商家知识库】里的事实回答买家问题，
语气亲切、简洁、专业，像真人客服。严格约束：
- 只能依据我给的知识库内容作答，不得编造政策、价格、时效等任何未提供的信息。
- 知识库没有相关内容时，礼貌说明「这个问题我帮您转人工核实」，不要硬编。
- 直接给最终回复，不要复述问题、不要加 markdown 标题。"""

# 兜底话术（无命中 / 无法润色时用）
_FALLBACK_NO_HIT = "您好，这个问题我暂时没有找到对应的说明，已为您记录，稍后由人工客服跟进，感谢理解～"

_TOP_K = 3


def _support_system() -> str:
    return (f"{_SKILL_PREFIX}\n\n{_SUPPORT_SYSTEM}"
            if _SKILL_PREFIX else _SUPPORT_SYSTEM)


def _page_text(page: dict) -> str:
    """把一条命中页拍平成可读文本（标题: 正文/字段拼接）。"""
    if not isinstance(page, dict):
        return str(page)
    title = page.get("title") or page.get("key") or ""
    # 取正文类字段；其余键值兜底拼接
    body = page.get("content") or page.get("answer") or page.get("text")
    if body:
        return f"{title}：{body}".strip("：")
    skip = {"key", "seller_id", "title"}
    parts = [f"{k}={v}" for k, v in page.items() if k not in skip]
    return f"{title}：{'; '.join(parts)}".strip("：")


class SupportNode(BaseNode):
    """客服节点：商家 FAQ 检索 → LLM 润色（缺 key 回退原文）。

    可独立调用（HubAgent.handle 直接 await node.run(state)），不进洞察子图。
    入参 state：{seller_id, question, _seller_wiki(实例)}。
    """

    name = "support"

    @staticmethod
    def _query_terms(question: str) -> list[str]:
        """把整句问题拆成检索片段：整句 + 去停用词后的 token + 中文 2-gram。

        SellerWiki.search 是纯子串匹配，整句「怎么退货」匹配不到「退换货政策」页，
        故在节点侧扩召回——不改 SellerWiki，只补查询侧分词。
        """
        q = question.strip()
        if not q:
            return []
        terms: list[str] = [q]
        # 去常见请求性停用词后按非汉字/标点切 token
        cleaned = q
        for stop in ("怎么", "如何", "请问", "你们", "我想", "可以", "吗", "呢",
                     "的", "了", "啊", "下", "一下", "是否", "能不能", "能"):
            cleaned = cleaned.replace(stop, " ")
        for t in re.split(r"[\s，,。.!！?？、]+", cleaned):
            t = t.strip()
            if len(t) >= 2:
                terms.append(t)
        # 中文 2-gram 兜底（捕捉「退货」→「退换」这类近义子串）
        han = re.sub(r"[^一-鿿]", "", q)
        for i in range(len(han) - 1):
            terms.append(han[i:i + 2])
        # 去重保序
        seen: set[str] = set()
        return [t for t in terms if not (t in seen or seen.add(t))]

    @classmethod
    def _retrieve(cls, state: dict) -> list[dict]:
        """SellerWiki 多片段召回命中页（Top-K，按页 key 去重保序）。"""
        seller_id = state.get("seller_id")
        wiki = state.get("_seller_wiki")
        question = state.get("question") or ""
        if not (seller_id and wiki is not None and question):
            return []
        out: list[dict] = []
        seen_keys: set = set()

        def _collect(terms: list[str]) -> bool:
            """逐片段 search 累积命中（按页 key 去重）。满 Top-K 返回 True。"""
            for term in terms:
                try:
                    hits = wiki.search(seller_id, term)
                except Exception:  # noqa: BLE001 — 检索失败不致命
                    continue
                for p in hits or []:
                    key = p.get("key") if isinstance(p, dict) else None
                    dedup = key if key is not None else id(p)
                    if dedup in seen_keys:
                        continue
                    seen_keys.add(dedup)
                    out.append(p)
                    if len(out) >= _TOP_K:
                        return True
            return False

        terms = cls._query_terms(question)
        if _collect(terms):
            return out
        # 多片段全落空 → 单字兜底（噪声大，仅在前面 0 命中时启用）
        if not out:
            han = re.sub(r"[^一-鿿]", "", question)
            singles = [c for c in dict.fromkeys(han)]  # 去重保序
            _collect(singles)
        return out

    async def run(self, state: dict) -> dict:
        question = (state.get("question") or "").strip()
        hits = self._retrieve(state)

        context = "\n".join(f"- {_page_text(p)}" for p in hits)
        source = "商家知识库" if hits else "未命中"

        answer: str | None = None
        mode = "fallback"
        if hits and llm.available():
            user = f"【商家知识库】\n{context}\n\n买家问题：{question}"
            answer = llm.chat_text(_support_system(), user, max_tokens=400)
            if answer:
                mode = "llm"

        # 回退：有命中拼原文，无命中礼貌兜底（永不崩）
        if not answer:
            if hits:
                answer = "您好～为您找到以下说明：\n" + context
                mode = "retrieval"
            else:
                answer = _FALLBACK_NO_HIT
                mode = "fallback"

        refs: list[dict] = []
        for p in hits:
            refs.append(new_evidence_ref(
                layer="semantic_unit",
                source_id=p.get("key") if isinstance(p, dict) else None,
                summary=f"FAQ 命中：{_page_text(p)[:40]}",
                confidence=0.85,
            ))

        note = f"客服应答（{mode}，命中 {len(hits)} 条，来源 {source}）"
        return {
            "support_answer": answer,
            "support_hits": hits,
            "evidence_refs": self._merge_refs(state, refs),
            "_trace": [self._trace_entry(note)],
        }
