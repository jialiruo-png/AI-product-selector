# 电商经营 Agent — 融合方案

> 融合对象：
> - [03-抖店商家经营Agent-V2-升级版PRD.md](03-抖店商家经营Agent-V2-升级版PRD.md)（架构蓝图：15 专家矩阵 / Skill MD / 双层 Wiki / Review / 证据引用 / OKR 闭环）
> - [docs/开源项目调研与选型.md](docs/开源项目调研与选型.md)（落地骨架：LangGraph + company-research-agent 范式 + TikHub 数据源）
> - 已有代码：[采集工作台/scripts/](采集工作台/scripts/)（search→score→SQLite→Top-N 评论→LLM 痛点 的真 pipeline）
>
> 编写日期 2026-06-04。

---

## 0. 这份文档要解决的核心矛盾

把两份文档摆在一起，矛盾很清楚：

| | V2 PRD | 选型 doc + 现有代码 |
|---|---|---|
| 定位 | 平台级「商家经营操作系统」，15 个专家 | 单条「商机洞察」选品流水线 |
| 数据底座 | **抖店罗盘 / 千川 / 百应 原生 API**（假设你在字节内部） | **TikHub 商用 API**（外部能拿到的真实数据） |
| 形态 | 架构蓝图（很多还没法跑） | 能跑的 Python 脚本 |
| 风格 | 面试用的全景野心 | 工程师的务实落地 |

**融合的本质 = 用 PRD 的「架构骨」装选型 doc 的「数据肉」**：

1. PRD 的多专家矩阵、Skill MD、双层 Wiki、Review 状态机、证据引用、OKR 闭环 —— 全部保留为**系统框架**。
2. 每个专家 Agent 的「能力」必须落到 **TikHub 实际能拿到的字段** 或 **现有 score/analyze 代码** 上，拿不到的明确标注为「平台侧 / 未来」。
3. PDF 五步洞察流程 = 融合系统的**第一个、也是最先能跑通的「洞察子图」**，对应 PRD 里 L2B 的 5 个存量经营 Agent。

一句话：**对外（TikHub 版）现在就能做的是「商机洞察 + 选品打分 + 痛点分析」；对内（抖店原生版）PRD 描绘的是同一套架构接上原生数据后的完全体。两者共用一套骨架，只换数据源适配层。**

---

## 1. 融合后的总体架构（三段式）

```
┌──────────────────────────────────────────────────────────────┐
│  L0 · Hub 路由层（PRD 1.1）                                     │
│  商家自然语言意图 → 路由到专家 / 编排 Skill 链                    │
└──────────────────────────────────────────────────────────────┘
                              ↓ Handoff / Skill 链
┌──────────────────────────────────────────────────────────────┐
│  L1 · 专家 Agent 矩阵（PRD 第 3 节，按数据可得性分三档）           │
│                                                                │
│  ● 现在可跑（TikHub）：选品 / 关键词 / 竞品 / 爆款 / 商品诊断(口碑) │
│  ◐ 半跑（TikHub+商家私域导入）：客服 / 售后 / 核价               │
│  ○ 平台侧未来（需抖店原生 API）：罗盘归因 / 直播 / 千川投流 / OKR  │
│                                                                │
│  每个专家 = 一份 Skill MD（角色/SOP/工具依赖/IO schema/next_skill）│
└──────────────────────────────────────────────────────────────┘
                              ↓ 调用
┌──────────────────────────────────────────────────────────────┐
│  L2 · 工具协议层（PRD 5.1）—— MCP / Function Calling 合规        │
│  把现有脚本封装成 BaseTool：search / score / reviews / analyze   │
│  + TikHub 适配器 + （未来）抖店原生 API 适配器                    │
└──────────────────────────────────────────────────────────────┘
                              ↓ 读写
┌──────────────────────────────────────────────────────────────┐
│  L3 · 数据 + 知识底座                                            │
│  · SQLite 快照库（现有 db.py：runs/products/notes/reviews/...）  │
│  · 双层 Wiki（行业只读 + 商家 overlay，PRD 1.3）                 │
│  · 视觉证据库（image-index.json，PRD 6.1，TikHub 主图免费可建）   │
│  · 统一证据引用 KnowledgeEvidenceRef（PRD 9.1）                  │
└──────────────────────────────────────────────────────────────┘
```

横切关注点（贯穿所有层，来自 PRD 第 9 节）：
**Review 状态机** · **证据引用强制** · **运行可观测 timeline** · **租户隔离** · **成本透明**。

---

## 2. LangGraph 编排骨架（直接复用 company-research-agent）

选型 doc 已确认 `reference/company-research-agent/backend/graph.py` 与 PDF 流程几乎同构。融合方案把它**就地改造**为「商机洞察子图」，作为整个系统第一个落地的编排单元：

```
原 company-research-agent              →   融合后的「商机洞察子图」
─────────────────────────────────────────────────────────────────
grounding（公司预处理）                →   KeywordPlanner（Step1 叶子类目→10-20 精准词）
  ├ FinancialAnalyst  ┐                  ├ SocialAnalyzer    ┐ Step2 社媒/persona（小红书笔记）
  ├ NewsScanner       ├ 4 并行           ├ PriceAnalyzer     ├ Step3 价格带（商品搜索）
  ├ IndustryAnalyzer  │                  ├ HotItemAnalyzer   │ Step4 爆款+主图（商品+image）
  └ CompanyAnalyzer   ┘                  └ CompetitorAnalyzer┘ Step5 竞品+评价词云（评论端点）
collector（聚合）                      →   Collector（沿用）
curator（相关性打分过滤）              →   Curator（复用 score.py 的归一化加权打分）
enricher → briefing → editor          →   Enricher → Briefing → Editor（出洞察报告）
```

**关键透传字段**（改造 `state.py` 的 `ResearchState`）：
- `keywords: List[str]` —— Step1 产出的「精准词」，作为 Step2-5 全局筛选条件透传（选型 doc 明确强调）。
- 沿用「原始字段 + curated_ 字段并存」范式：`social_data / curated_social_data`、`price_data / curated_price_data`…
- 新增 `evidence_refs: List[KnowledgeEvidenceRef]` —— 每个 Analyzer 产出时挂证据（PRD 9.1），Editor 出报告时每条结论可点回原始数据。

**双模型分工**（选型 doc 共识 3）：长上下文综合（Briefing/Editor）用便宜大窗口模型；精确 JSON 格式化（Curator 打分、analyze 痛点抽取）用强指令模型。现有 `analyze.py` 已是这个范式。

---

## 3. 专家 Agent 矩阵 —— 按「数据可得性」重排 PRD 的 15 个

PRD 按业务层级（L1-L4）组织，很完整但不可落地。融合方案**保留 PRD 的全部 15 个定义**，但叠加一列「能不能现在跑」，把它变成**可执行的优先级路线**。

### ● 现在就能跑（TikHub 数据 + 现有代码）—— 这是 MVP

| 专家 Agent | PRD 出处 | 融合后用什么数据/代码实现 |
|---|---|---|
| **选品 Agent** | L2B | `fetch_search_products_list` + `score.py`（销量0.4+评分0.25+评论0.2+价格0.15）→ Top-N 候选 |
| **关键词 Agent** | L2B | Step1 KeywordPlanner（叶子类目→LLM 精准词）+ 小红书笔记 `tagList` 选词 |
| **竞品 Agent** | L2B | 搜索端 `seller_info/brand_info` 横向对标 + 按时间重搜对比销量/价格（趋势） |
| **爆款策划 Agent** | L2B | 主图 `image.url_list`（免费）→ VLM caption + 价格/材质元素拆解 |
| **商品诊断 Agent（口碑版）** | L2B | `fetch_product_reviews_v2` + `analyze.py`（情感分布/痛点/好评词云）。⚠️ 注意：**不是** PRD 原版的「罗盘 CTR/CVR 诊断」，而是降级为**评价口碑诊断**——罗盘指标 TikHub 拿不到 |

> 这 5 个正好就是 **PDF 五步洞察流程**，也就是第 2 节的「商机洞察子图」。**先把这一个子图跑通 = 同时交付 5 个专家 Agent 的 v0.1。**

### ◐ 半跑（TikHub + 商家自助导入私域数据）

| 专家 Agent | 缺什么 | 折中实现 |
|---|---|---|
| **客服 Agent** | 真实订单/退换货数据 | 商家上传 SKU 详情 + FAQ 到「商家 Wiki overlay」→ RAG 应答 |
| **售后 Agent** | 抖店售后规则库 | 用 TikHub 评论里的负向痛点 + 商家自定义退换货政策 |
| **核价 Agent** | 抖店成本/采购数据 | 纯本地：商家导入原料+辅料成本 → 利润核算表（不依赖 TikHub） |

### ○ 平台侧未来（必须抖店原生 API，PRD 完全体）

| 专家 Agent | 依赖的原生数据 |
|---|---|
| **罗盘归因 Agent** | 抖店罗盘实时 GMV/CTR/CVR 漏斗 |
| **经营 OKR Agent** | 抖店历史销售数据（做 OKR 智能拆解） |
| **直播策划 Agent** | 巨量百应达人池 + 抖音直播 API |
| **短视频脚本 Agent** | 抖音内容生态数据 |
| **订单 / 物流 Agent** | 抖店订单/物流 API |
| **新品立项 / 上市节奏 Agent** | 抖店 ERP / 审批流集成 |

**这一列的价值**（也是面试关键判断点，对应 PRD 第 2 节）：它诚实地说明了**为什么这个产品由抖店官方做才有不可替代性**——○ 档的全部能力，第三方 SaaS（包括你这套 TikHub 版）**永远拿不到原生数据**。你的 TikHub 版恰好是「第三方 SaaS 能做到的天花板」，正好反衬出官方版的护城河。

---

## 4. Skill MD 范式落地（PRD 1.2 / 第 5 节）

每个专家 = 一份 Markdown，**不是硬编码**。融合方案给出选品 Agent 的真实可跑版本（对照 PRD 的「商品诊断」样例，但字段全部对齐 TikHub）：

```markdown
# Skill: 选品

## 1. 角色定义
你是 TikTok Shop 选品专家，基于搜索端免费打分字段，从关键词冷启动产出 Top-N 选品候选。

## 2. 核心目标
关键词 → 商品列表 → min-max 归一化加权打分 → Top-N 候选 + 价格带机会诊断。

## 3. SOP
1. 数据拉取：fetch_search_products_list(search_word, region=US)，翻页拿全量
2. 打分：score.py 的 TikTok 权重（销量0.4+评分0.25+评论0.2+价格分位0.15）
3. 价格带诊断：TOP300 价格分布 → 找空窗机会带
4. 落库：db.py products 表（带 run_id，便于趋势复盘）
5. 建议生成：Top-N 候选，每条挂 KnowledgeEvidenceRef（layer=raw，指向 product_id）

## 4. 工具依赖
- tikhub.search_products / score.rank / db.write_products

## 5. 输入 Schema
- keyword (必填) / region (默认 US) / topn (默认 5)

## 6. 输出规范
- candidates[] / price_band_gaps[] / evidence_refs[]
- next_skill: "竞品" | "爆款策划" | "商品诊断(口碑)"
```

**`next_skill` 字段 = Skill 链**（PRD 第 3 节末）。融合后的真实链路：
`关键词 → 选品 → 竞品 / 爆款策划 → 商品诊断(口碑) → 洞察报告`。
Hub Agent 不用每次重新规划，沿着 `next_skill` 串就行。

---

## 5. 工具协议层 —— 把现有脚本封装成 MCP 合规工具（PRD 5.1）

现有 5 个脚本本就是干净的原子能力，封装成 `BaseTool` 即可满足 PRD 的「JSON Schema 强制化 + MCP 兼容 + 自动注册」三要求：

| 现有脚本 | 封装为工具 | input/output schema |
|---|---|---|
| `_tikhub_client.py` | `TikHubClient`（底座，非工具） | — |
| `selector.search` | `search_products` | `{keyword, source, region}` → `products[]` |
| `score.py` | `rank_products` | `{products[], weights?}` → `scored[]` |
| `analyze.py` | `analyze_reviews` | `{reviews[]}` → `{sentiment, pain_points, highlights}` |
| `db.py` | `snapshot_write` / `trend_query` | `{run_id, rows}` / `{source_id}` → `history[]` |

**未来扩展**：抖店原生 API 适配器实现同一组工具接口（`search_products` 换成罗盘端点），**Skill MD 一字不改**就能从 TikHub 版切到原生版——这正是 PRD 强调「换数据源/换模型成本接近 0」的工程兑现。

---

## 6. 双层 Wiki + 证据引用（PRD 1.3 / 9.1）—— 务实裁剪版

PRD 的双层 Wiki + 6 种语义冲突治理很完整，但 MVP 阶段全做太重。融合方案分两步：

**第一步（MVP，能落地）**：
- 行业 Wiki：先放**最小集**——TikTok Shop 选品打分口径、价格带诊断 SOP、爆款元素清单（从 eCommerce-Skills 的 Output Format 段落抄维度，选型 doc 已说明用法）。
- 商家 Wiki overlay：商家导入的 SKU 详情 / 卖点 / FAQ，存 SQLite 一张 `wiki_pages` 表（租户隔离用 `seller_id`）。
- 证据引用：**强制每条 AI 结论挂 `KnowledgeEvidenceRef`**（PRD 9.1 接口），MVP 只用 `raw`（指向 product_id/review_id）和 `wiki` 两个 layer，其余 layer 枚举先占位。

**第二步（V1+，PRD 完全体）**：
- 6 种语义关系冲突治理（supports/refines/scope_differs/contradicts/supersedes/duplicates）。
- AI 高质量回答回流 Wiki 的「知识复利」闭环。
- `superseded` 批量失效机制。

**视觉证据库（PRD 6.1）现在就能起步**：TikHub 商品搜索的 `image.url_list` 免费，可立即建 `image-index.json`（imageId + VLM caption + 价格 + 销量），供爆款策划 Agent「取问题主图 + 同类爆款主图并排展示」。这是 TikHub 版少有的、能直接兑现 PRD 「视觉证据一等公民」的点。

---

## 7. Review 状态机 + 可观测性（PRD 1.4 / 9.2）

TikHub 版**没有改价/退款/上下架的写操作**，所以高敏感动作 Review 在 MVP 阶段触发不多。但融合方案保留状态机骨架，用于两类场景：
1. **建议转任务**：洞察报告里的行动建议 → 商家点「采纳」才落任务（Candidate→Approved）。
2. **未来原生版**：接上抖店写 API 后，改价/补库存必须走 Candidate→Pending Review→Approved→Executed。

**可观测 timeline（PRD 9.2）MVP 就该做**，因为它便宜且是信任地基：每次 Agent 调用记录「用了哪些 TikHub 端点 / 哪些 Wiki 页 / 消耗 token / 花了多少钱」。现有 `db.py` 加一张 `agent_runs` 表即可。

---

## 8. OKR 闭环（PRD 第 4 节）—— 明确标注「依赖原生数据」

PRD 的 KPI→OKR→日任务→复盘→沉淀主线非常完整，但**「AI 智能拆解」依赖抖店历史销售数据**，TikHub 拿不到。融合方案的处理：

- **○ 标注清楚**：AI 智能拆解路径属平台侧未来。
- **◐ MVP 兜底**：保留「手动新增 OKR」+「Excel 导入」两条冷启动路径（PRD 4.2 已列），商家手填 O/KR → 日任务关联到「商机洞察子图」的选品/诊断结论。这样**洞察报告不再是死文档，而是能转成日任务**，跑通「洞察→行动」的最小闭环。

---

## 9. 融合后的演进路线图（替换 PRD 第 8 节）

把 PRD 的时间表，重写成「按数据可得性」而非「按业务层级」推进——这样每一步都真的能交付：

| 阶段 | 范围 | 数据依赖 |
|---|---|---|
| **MVP（现在）** | 商机洞察子图跑通 = 选品/关键词/竞品/爆款/商品诊断(口碑) 5 个专家 v0.1 + 证据引用 + SQLite 快照 + 可观测 timeline | 纯 TikHub，**今天就能写** |
| **V0.5** | Hub 路由 + Skill MD 化 + next_skill 链 + 视觉证据库（主图 caption） + 手动 OKR→日任务兜底 | TikHub |
| **V1.0** | 客服/售后/核价（◐ 档，商家私域导入）+ 行业 Wiki 最小集 + 商家 Wiki overlay + Review 骨架 | TikHub + 商家导入 |
| **V1.5** | 6 语义关系冲突治理 + 知识回流复利 + MCP 工具协议正式化 | TikHub + 商家导入 |
| **V2.0（接原生）** | 罗盘归因/OKR 智能拆解/直播/千川（○ 档）—— 工具层换原生适配器，Skill MD 不变 | **抖店原生 API** |

灰度沿用 PRD：100 家内测 → 1% 服饰 → 多类目 → 全量。

---

## 10. 一页总结

> **对外能跑的版本**：一套 LangGraph 编排的「商机洞察 Agent」——关键词进，5 个专家（选品/关键词/竞品/爆款/口碑诊断）沿 PDF 五步流程并行洞察，TikHub 取数、score.py 打分、analyze.py 抽痛点，每条结论挂证据引用、落 SQLite 可复盘趋势。这是第三方用公开商用数据能做到的天花板。
>
> **架构上预留的完全体**：同一套骨架（Hub 路由 + Skill MD + 双层 Wiki + Review + 证据引用 + 可观测 + OKR 闭环），只要把工具协议层的 TikHub 适配器换成抖店罗盘/千川/百应原生适配器，Skill MD 一字不改，就长成 PRD 描绘的 15 专家「商家经营操作系统」。
>
> **融合的一句话**：**用 PRD 的架构骨，装选型 doc 的数据肉；现在用 TikHub 把骨架跑活，未来用原生 API 把它喂成完全体。** 数据源是唯一的可替换变量，其余架构两版共用。

---

## 附：两份文档的取舍对照表

| 设计点 | PRD 主张 | 融合方案处理 |
|---|---|---|
| 多专家矩阵 | 15 个，按业务层级 | **保留全部**，按数据可得性重排为 ●◐○ 三档优先级 |
| Skill MD | 配置即技能 | **采纳**，给出对齐 TikHub 字段的真实可跑样例 |
| 双层 Wiki | 6 语义关系治理 | **采纳但分两步**：MVP 最小集 + raw/wiki 双 layer，完全治理放 V1.5 |
| 视觉证据 | 一等公民 | **采纳且提前**：TikHub 主图免费，MVP 即可建 image-index |
| Review 状态机 | 高敏感动作必审 | **保留骨架**：MVP 用于「建议转任务」，写操作待原生版 |
| 证据引用 | KnowledgeEvidenceRef 强制 | **采纳**：MVP 强制挂，先用 raw/wiki 两 layer |
| OKR 闭环 | AI 智能拆解 | **拆**：智能拆解标平台侧未来，MVP 走手动/Excel 兜底 |
| 罗盘/千川/百应 | 原生直连 | **诚实标 ○ 档**：第三方拿不到，正是官方版护城河 |
| LangGraph 骨架 | （PRD 未细化） | **补上**：直接改造 company-research-agent 的 graph.py |
| TikHub 数据源 | （PRD 假设原生） | **补上**：作为 MVP 唯一现实数据源，写进工具适配层 |
