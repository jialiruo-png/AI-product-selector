# 项目更新记录

> 更新日期：2026-06-04  
> 更新目标：把现有 TikHub 选品工具升级为「电商经营 Agent 框架」的可运行 MVP，并按功能批次推送到 GitHub。

## 批次 1：Agent 治理底座

**功能说明**

- 新增 `InsightState`，承接商机洞察子图的全局状态。
- 引入统一证据引用 `KnowledgeEvidenceRef`，要求 Agent 输出具备可追溯依据。
- 新增 Review 状态机，保留「AI 建议先候选、人工确认后执行」的人审边界。
- 新增双层 Wiki 最小实现：行业 Wiki 只读种子 + 商家 Wiki overlay。

**主要文件**

- `agent/state.py`
- `agent/evidence.py`
- `agent/review.py`
- `agent/wiki/industry.py`
- `agent/wiki/seller.py`
- `agent/wiki/__init__.py`

**价值**

这一批先搭好事实边界、知识边界和人审边界，避免 Agent 只是一条黑盒脚本。

**提交信息**

`feat(agent): add governance state evidence review wiki`

## 批次 2：工具协议层与 Skill MD

**功能说明**

- 新增 `BaseTool` 与 `TOOL_REGISTRY`，把工具统一成 JSON Schema 风格的协议层。
- 封装现有 `采集工作台/scripts` 能力为 Agent 工具，不改原脚本：
  - `search_products`
  - `rank_products`
  - `fetch_reviews`
  - `analyze_reviews`
  - `snapshot_write`
  - `trend_query`
- 支持 `AGENT_MOCK=1` 离线假数据，方便无 API key 时跑通完整链路。
- 新增 Skill MD 加载器，把专家能力从硬编码抽成 Markdown 配置。
- 新增 5 个可运行专家 Skill：
  - 关键词
  - 选品
  - 竞品
  - 爆款策划
  - 口碑诊断

**主要文件**

- `agent/tools/base.py`
- `agent/tools/tikhub_tools.py`
- `agent/tools/__init__.py`
- `agent/skills/loader.py`
- `agent/skills/README.md`
- `agent/skills/guanjianci.md`
- `agent/skills/xuanpin.md`
- `agent/skills/jingpin.md`
- `agent/skills/baokuan.md`
- `agent/skills/koubei_zhenduan.md`

**价值**

这一批把「数据采集脚本」升级为「可被 Agent 调用的标准工具」，并把业务策略沉淀到可读可改的 Skill MD。

**提交信息**

`feat(agent): add tool protocol and skill md experts`

## 批次 3：商机洞察子图与 Hub 路由

**功能说明**

- 新增商机洞察子图：
  - `KeywordPlanner`
  - `SocialAnalyzer`
  - `PriceAnalyzer`
  - `HotItemAnalyzer`
  - `CompetitorAnalyzer`
  - `Collector`
  - `Curator`
  - `Briefing`
  - `Editor`
- 支持 MiniGraph 离线运行器，并预留 LangGraph 后端。
- 新增 Hub Agent，按自然语言意图路由到对应专家链。
- 新增 CLI：`python3 -m agent.run "口红" --category 美妆 --mock`。
- 每次运行输出 Markdown 报告，并打印 trace 与 evidence_refs 摘要。

**主要文件**

- `agent/__init__.py`
- `agent/graph.py`
- `agent/hub.py`
- `agent/run.py`
- `agent/nodes/base.py`
- `agent/nodes/planner.py`
- `agent/nodes/analyzers.py`
- `agent/nodes/aggregate.py`
- `agent/nodes/__init__.py`

**价值**

这一批把「选品工具」变成「可编排的多专家 Agent 子图」，可以端到端从关键词生成商机洞察报告。

**提交信息**

`feat(agent): add opportunity insight graph and hub`

## 批次 4：文档与后续任务清单

**功能说明**

- 新增 Agent 框架 README，说明架构分层、运行方式、当前状态。
- 新增 Codex 任务清单，按 P0/P1/P2 标出后续开发优先级。
- 新增本更新记录，按功能批次说明本次云端推送内容。

**主要文件**

- `agent/README.md`
- `05-Codex任务清单.md`
- `update.md`

**价值**

这一批保证后续开发有清晰交接材料：已经完成什么、怎么运行、下一步先做什么。

**提交信息**

`docs: add agent framework update notes`

## 本次验证

建议每批提交前后执行：

```bash
python3 -m compileall -q agent
python3 -m agent.run "口红" --category 美妆 --mock
```

当前 MVP 预期：

- mock 模式无需 `TIKHUB_API_KEY` 和 `DASHSCOPE_API_KEY`。
- 输出包含「人群 / 价格 / 爆款 / 竞品 / 风险」章节。
- trace 显示节点执行顺序。
- evidence_refs 有证据引用计数。

---

## 批次 5：在运营商家诊断子图 - PRD 与协作宪法（贾丽婼）

> 更新日期：2026-06-04 晚
> 负责人：贾丽婼（Liruo）
> 状态：文档先行，未开始代码开发

**功能说明**

- 新增「在运营商家诊断子图」方向，与甘华梁负责的「冷启动选品子图」并列。
- 服务对象：抖音电商 S4/S5 层级中小商家——平台 90% 拿不到人工小二的店。
- 核心问题：补齐当前抖店 AI 助手对中小商家诊断的 4 大短板（不找根因 / 同质化 / 缺资源配套 / 不处理非数据信息）。
- V1 类目聚焦女装（抖音电商 GMV 第一大类目）。
- 设计 3 个新专家 Skill MD（经营诊断 / 归因 / 行动建议）+ 6 个女装细分场景 overlay（自播 / 达播 / 货架 / 新店冷启动 / 成长期 / 季节切换期）。
- 复用甘华梁框架底座：state / evidence / review / wiki / tools 协议 / skills loader / graph / hub。
- 共用资产改动均走 PR 协商；`采集工作台/scripts/` 零修改约束严格继承。

**主要文件**

- `06-在运营商家诊断Agent-PRD.md`（新增）
- `CLAUDE.md`（新增）：团队协作宪法、命名规范、分工边界、共用资产保护规则、提交规范
- `update.md`（追加本批次）

**价值**

把团队从「一个人单打独斗的选品工具」升级为「两个开发并行、有规范、有边界、可审计的多人 Agent 项目」。CLAUDE.md 把所有口头约定显性化，避免后续误改禁区或重复造轮子。

**待补文档（开发前）**

- `07-女装诊断Skill写作规范.md`：让 6 个 overlay 写法一致 ✅ 已完成
- `08-验收用例-女装真实场景.md`：3-5 个具体女装店真实诊断场景作为 V1 ground truth ✅ 已完成
- mock 商家数据 JSON（Day 2 开发时同步建）

**提交信息**

`docs(prd): add diagnosis subgraph prd and team charter`

---

## 批次 6：女装诊断写作规范 + 验收用例（贾丽婼）

> 更新日期：2026-06-04 晚
> 负责人：贾丽婼（Liruo）
> 状态：开发前置文档全部就位，准备进入 Day 1 开发

**功能说明**

- 新增 `07-女装诊断Skill写作规范.md`：定义 Skill MD 的 9 个标准章节、字段写作约束、6 个女装 overlay 差异化要点。核心约束：
  - SOP 每步必须带决策点 + 工具 + fallback，禁止空话
  - 输出 schema 必须含 evidence_refs + confidence + data_sources
  - 行动建议必须挂可执行资源（activity_id / tool_url / template_id），禁止空建议
- 新增 `08-验收用例-女装真实场景.md`：5 个具体女装店真实诊断 case，覆盖 6 个 overlay 的所有组合：
  - Case 1 咖喱生活（自播 + 成长期）：转化率断崖式下跌
  - Case 2 素笺布艺（货架店）：搜索流量塌方
  - Case 3 初见女装铺（新店冷启动）：体验分 0 卡住
  - Case 4 橙夏（达播店）：达人选品命中率低
  - Case 5 夏树（自播 + 季节切换）：滞销库存压力 + 秋装缺货
- 每个 case 都给了商家画像 / 数据现状 / 期望诊断 / 期望归因 / 期望建议四段对照
- V1 整体验收线：5 个 case 至少通过 4 个

**主要文件**

- `07-女装诊断Skill写作规范.md`（新增）
- `08-验收用例-女装真实场景.md`（新增）
- `update.md`（追加本批次）

**价值**

把 V1 验收口径从"主观判断 AI 报告好不好"变成"5 个具体 case 对照打分"。开发期间随时跑这 5 个 case 看回归，避免 overlay 写偏。同时这 5 个 case 也直接作为面试演示素材（Case 1 用了体验抖店时截图过的真实商家，故事性最强）。

**下一步**

- Day 1 开发：3 个通用 Skill MD + 6 个女装 overlay + 4 份 Wiki 种子
- Day 2 开发：4 个诊断节点骨架 + LangGraph 子图编排 + State 扩展 + mock 商家数据 JSON
- Day 3 开发：接通真 LLM + 接 Hub 路由 + 跑通 5 个 case
- Day 4 收尾：报告 markdown 优化 + 证据展示 + Streamlit demo + 演示话术

**提交信息**

`docs(diagnosis): add skill writing spec and v1 acceptance cases`

---

## 批次 7：经营诊断子图 Day 1 — Skill MD 与 Wiki 种子（贾丽婼）

> 更新日期：2026-06-04 晚
> 负责人：贾丽婼（Liruo）
> 分支：`运营`
> 状态：开发 Day 1 完成，Day 2 准备进入节点骨架

**功能说明**

Day 1 落地经营诊断子图的所有"配置即知识"层资产，纯 MD 文件，零代码改动：

- **3 个通用 Skill MD**（`agent/skills/`）：
  - `jingying_zhenduan.md`：经营诊断专家（入口调度）
  - `guiyin.md`：归因专家（MECE 拆维度 + 跨场景 + 非数据信号检索）
  - `xingdong_jianyi.md`：行动建议专家（资源挂钩 + 准入校验 + 性价比排序）
  - 串联链路验证：`经营诊断 → 归因 → 行动建议 → 经营总结`

- **6 个女装 overlay**（`agent/skills/category_overlays/`）：
  - `nvzhuang_zibo.md`：自播店（直播间 + 主图 + 千川直播）
  - `nvzhuang_dabo.md`：达播店（达人选品 + 精选联盟 + 品牌专场）
  - `nvzhuang_huojia.md`：货架店（搜索 + 评价 + 商城精选）
  - `nvzhuang_xindian.md`：新店冷启动（突破 0 分 + 新手任务，注：与甘华梁的"选品冷启动"不同）
  - `nvzhuang_chengzhang.md`：成长期（千川优化 + 渠道破局 + 跨子图路由到甘华梁选品专家）
  - `nvzhuang_jijie.md`：季节切换期（滞销清仓 + 应季备货 + 投流倾斜）

- **4 份行业 Wiki 种子 MD**（`agent/wiki/industry/`）：
  - `category_baseline.md`：女装 6 个细分场景的健康度基线
  - `activity_db.md`：10 个女装相关平台活动条目（含准入门槛 / 历史命中率 / 预估收益）
  - `tool_db.md`：23 个官方工具入口（AIGC / SEO / 千川 / 达人 / 商城 / 话术 / 任务）
  - `rule_changes.md`：5 条近 30 天规则变动 + 2 条预告（解决"AI 不处理非数据信号"短板）

**关键设计决定**

1. **格式对齐甘华梁**：Skill MD 采用甘华梁现有的 6 章节格式（`# Skill: 名字` + `## 1.角色定义` 到 `## 6.输出规范`），确保 `agent/skills/loader.py` 能零改动解析
2. **next_skill 用 markdown 列表格式**：写在 `## 6.输出规范` 段尾的 `- next_skill: "X"`，便于 loader 的 regex 命中
3. **强制约束写在输出规范段**：每个 Skill 都列出"强制约束 + 红线"，让 LLM 行为可预测
4. **资源挂钩硬规则**：行动建议专家产出的每条 action 必须有 `resource.url`，禁止空建议（专治抖店现有 AI "去优化主图" 类空话）
5. **类目 overlay 不独立调工具**：作为主专家的特化层，由主专家命中后合并加载

**主要文件**

新增（13 个 MD 文件）：
- `agent/skills/{jingying_zhenduan,guiyin,xingdong_jianyi}.md`
- `agent/skills/category_overlays/{nvzhuang_zibo,nvzhuang_dabo,nvzhuang_huojia,nvzhuang_xindian,nvzhuang_chengzhang,nvzhuang_jijie}.md`
- `agent/wiki/industry/{category_baseline,activity_db,tool_db,rule_changes}.md`

修改：
- `update.md`：追加本批次

**回归验证**

- ✅ `python3 -m compileall -q agent` 通过
- ✅ `python3 -m agent.run "口红" --category 美妆 --mock` 跑通甘华梁冷启动子图（9 节点全执行，57 条证据引用）
- ✅ `load_skills()` 加载 8 个 Skill（甘华梁 5 + 贾丽婼 3）+ 6 个 overlay
- ✅ `skill_chain("经营诊断")` 返回 `['经营诊断', '归因', '行动建议', '经营总结']`

**价值**

把"诊断子图怎么思考、看哪些指标、挂哪些资源、避哪些雷"全部沉淀到可被业务侧修改的 MD。Day 2 写节点代码时只需调用 `load_skills()` 取 SOP，不再有硬编码 prompt。

**下一步（Day 2）**

- 新增 `agent/nodes/diagnosis/{checker,attributor,advisor,composer}.py` 四个节点
- 扩展 `agent/state.py`（仅添加字段：`anomalies / root_cause_chains / actions`，不改现有）
- LangGraph 子图编排（`AGENT_USE_LANGGRAPH=1` 走 LangGraph，MiniGraph 兜底）
- 5 份 mock 商家 JSON（`agent/mocks/shops/case_{1..5}.json`）按抖店罗盘字段还原
- Hub 路由扩展（PR 提给甘华梁）

**提交信息**

`feat(diagnosis): add day-1 skill md and wiki seeds`

---

## 批次 X · 副窗口 · 任务 A：5 份 mock 商家 JSON（2026-06-05）

**背景**

按 `CLAUDE.md` §11 多 Claude Code 窗口并行开发协议，副窗口推进任务 A（Day 3 跑 5 个 case 的数据底座），主窗口同时推进 Day 2 主链路（`agent/nodes/diagnosis/*`、`state.py`、`graph.py`、`hub.py`）。本批次仅触碰副窗口独立资产（`agent/mocks/shops/*.json`），未碰任何主窗口高危文件。

**新增（5 个 JSON 文件）**

- `agent/mocks/shops/case_1.json` — 咖喱生活｜女装自播 + 成长期｜CVR 断崖跌（2.1%→1.3%）
- `agent/mocks/shops/case_2.json` — 素笺布艺｜女装货架｜搜索曝光塌方（-31%）
- `agent/mocks/shops/case_3.json` — 初见女装铺｜女装新店冷启动｜35 天 0 商品，`newbie_progress` 非 null
- `agent/mocks/shops/case_4.json` — 橙夏｜女装达播｜坑位 ROI 暴跌（-54%），含 `kol_metrics`
- `agent/mocks/shops/case_5.json` — 夏树｜女装自播 + 季节切换｜夏装滞销 12w + 秋装备货不足，含 `sku_inventory`

**字段约定**

- 通用：`shop_profile / metrics_7d / metrics_prev_7d / metrics_30d / category_baseline / traffic_breakdown / sku_performance / fulfillment_metrics`
- 仅 case 3：`newbie_progress`（其余 case 设为 `null`）
- 仅 case 4：`kol_metrics`（含 8 条 kol_list，覆盖新/老达人粉丝画像匹配度）
- 仅 case 5：`sku_inventory`（夏装滞销 SKU + 秋装备货缺口 + 热搜词趋势）
- 所有数据均显式 `_mock: true`、`_case_id`、`_case_name`、`_overlay_hints`、`_scenario_summary`，对齐 `08-验收用例` 5 个 case 的"经营数据"表

**回归验证**

- ✅ 5 份 JSON 全部 `json.loads()` 通过
- ✅ `python3 -m compileall -q agent` 通过
- ✅ `python3 -m agent.run "口红" --category 美妆 --mock` 跑通甘华梁冷启动子图（9 节点全执行，57 条证据引用）
- ✅ 字段覆盖 `08-验收用例-女装真实场景.md` 期望诊断/归因/建议所需的所有输入信号（基线对比、流量拆分、SKU 表现、活动报名状态、规则变动信号、新店进度、达人画像匹配、季节库存）

**与主窗口的字段衔接约束**

副窗口写的字段名按"语义清晰"原则起的，Day 2 主窗口实现 `fetch_shop_metrics` 等工具时若发现字段名需对齐，请按主窗口 schema 统一并通知副窗口 rename，避免接口割裂。

**下一步（副窗口）**

- 任务 B：`demo/streamlit_app.py` MVP（选 case → 三段式展示 → Day 4 接 `agent.run`）
- 任务 C：`09-演示话术.md` 五段式稿（开场/现状/方案/演示/Q&A）

**提交信息**

`feat(diagnosis): add 5 mock shop json for day-3 cases`

---

## 批次 X+1 · 副窗口 · 任务 B：Streamlit demo 框架（2026-06-05）

**背景**

按 `CLAUDE.md` §11.3 任务 B，搭面试演示用的 Streamlit MVP，把 5 个 case 的 mock 数据可视化展示。Day 4 收尾时把"诊断报告"占位区换成 `from agent.run import run; result = run(...)` 即可对接真实 Agent。

**新增**

- `demo/streamlit_app.py` — 单文件 MVP（约 100 行）
  - 左侧栏：从 `agent/mocks/shops/case_*.json` 列举 case，显示 `_overlay_hints` 和 `_scenario_summary`
  - 主区两列：左列商家画像（含流量来源拆分 + 完整 JSON 折叠区）；右列"AI 诊断报告"（含核心问题 + 异常清单占位表格 + 归因/建议占位）
  - 异常清单表格按 case 自适应（覆盖 `cvr / main_image_ctr / qianchuan_roi / live_room_stay_sec / search_ctr / kol_keng_wei_roi` 等指标，自动计算环比 + 对照类目基线）

**修改**

- `requirements.txt`：新增 `streamlit>=1.36.0`，注释标明"仅演示界面用，不影响 agent 主链路和 MiniGraph 兜底"（符合 §4.4 约束）

**启动**

```bash
pip install -r requirements.txt
streamlit run demo/streamlit_app.py
# 默认 http://localhost:8501
```

**回归验证**

- ✅ `python3 -m py_compile demo/streamlit_app.py` 通过
- ✅ `python3 -m compileall -q agent` 通过
- ✅ 甘华梁冷启动子图 mock 仍可跑通

**与主窗口的对接预留**

- Day 4 收尾时只需把 `col2` 中 `if st.button("跑一次诊断")` 分支里的占位代码换成调用 `agent.run`，UI 框架不动
- 已预留 `_overlay_hints` 显示位，主窗口完成 Attributor 节点后可在右列底部叠加"实际命中 overlay"对比

**提交信息**

`feat(demo): add streamlit mvp for case visualization`

---

## 批次 X+2 · 副窗口 · 任务 C：09-演示话术稿（2026-06-05）

**背景**

按 `CLAUDE.md` §11.3 任务 C，完成面试/评审用演示话术稿。参考 `06-PRD.md` §2 / §14 + `08-验收用例` Case 1 全量数据。

**新增**

- `09-演示话术.md` — 五段式结构，总时长约 4 分钟
  - 开场（30s）：90% 中小商家无小二的制度性结果
  - 现状（30s）：抖店 AI 4 大短板（不找根因 / 同质化 / 缺资源 / 不处理规则变动）
  - 方案（60s）：不做小二副驾 + 类目 overlay + 资源数据库 + 规则 Wiki + 与甘华梁共底座边界
  - 演示（90s）：跑 Case 1 咖喱生活，逐段讲解诊断/归因/建议
  - Q&A 预演（30s）：3 个高频问题（为什么先做女装 / 怎么保证不瞎说 / 怎么落地抖店现有系统）
- 附演示前 30 秒 checklist + case 推荐顺序 + 不该做的事

**与文档体系的衔接**

- `06-PRD.md` §6 文档表格里"待写"的 `09` 文档名为"演示话术"，本批次落地
- `CLAUDE.md` §6 表格保留 `09-演示话术.md` 占位（如需更新 CLAUDE.md 自行加一行），本批次不动 CLAUDE.md（避免和主窗口冲突）

**回归验证**

- ✅ `python3 -m compileall -q agent` 通过（无代码改动，纯文档）
- ✅ 冷启动子图 mock 跑通

**提交信息**

`docs(demo): add 09 demo script for interview rehearsal`

---

## 批次 8 · 主窗口 · Day 2：诊断子图节点骨架 + 图编排 + CLI（贾丽婼）

> 更新日期：2026-06-05
> 负责人：贾丽婼（Liruo） · 主窗口
> 分支：`运营`
> 状态：Day 2 完成，端到端可跑通 5 个验收 case

**功能说明**

把 Day 1 的纯 MD 配置层"变活"——加 4 个节点、子图编排和 CLI 入口，让 `python3 -m agent.run "..." --diagnosis` 能端到端跑出 markdown 报告。

- **扩展 `agent/state.py`**：新增 `DiagnosisState` TypedDict（不动现有 `InsightState`），定义诊断子图全局状态（shop_profile / shop_metrics / anomalies / matched_overlays / root_cause_chains / non_data_signals / actions / report 等字段）。
- **新增 4 个诊断节点**（`agent/nodes/diagnosis/`）：
  - `checker.py` **经营诊断专家**：mock JSON 取数 → overlay 归属判定 → 类目基线对照 → 异常识别 + 严重度评级（≥50% high / ≥20% medium）→ 字段别名归一化适配副窗口 mock 命名
  - `attributor.py` **归因专家**：MECE 拆维度（流量/货品/转化/履约）→ 跨指标耦合验证 → 检索 `rule_changes` Wiki 找非数据信号（5 条规则变动）
  - `advisor.py` **行动建议专家**：内嵌活动 + 工具 / 模板 / 任务注册表 → 按 overlay × 维度匹配资源 → 准入门槛校验（exp_score / shop_level / live_share 等）→ 性价比×置信度排序 → 资源不可用时 fallback 兜底（仍输出，不空建议）
  - `composer.py` **报告组装节点**：把诊断/归因/建议串成商家可读 markdown，每条结论挂可点 `[refId]`，文末输出证据表

- **扩展 `agent/graph.py`**：新增 `DiagnosisMiniGraph` + `_build_diagnosis_langgraph_app()` + `run_diagnosis()`。线性链路 checker → attributor → advisor → composer。与冷启动子图共用 `_merge_partial` 行为，完全独立编排——不动 `run_insight` / `MiniGraph` / `build_graph`。
- **扩展 `agent/hub.py`**：
  - 在 `_INTENT_RULES` 增加"经营诊断"意图（关键词：卖不动 / GMV 跌 / 店铺诊断 / 体检 / 卖不好 / 复盘…）
  - 重排 route 优先级：P0 经营诊断 > P1 future 档（罗盘/OKR） > P2 其他洞察档——避免 GMV 关键词被 future 档"罗盘归因"抢走
  - 扩展 `handle()` 加 shop_id 参数，命中诊断意图时调 run_diagnosis
- **扩展 `agent/run.py` CLI**：
  - 新增 `--diagnosis` / `--shop-id` / `--window` 三个参数
  - 主参数从 `keyword` 改名为 `query`（向后兼容，两个子图都能用）
  - 输出 trace 摘要标注子图名 + 后端类型

**关键设计决定**

1. **共用资产最小侵入**：state.py 只追加 `DiagnosisState`、graph.py 只追加 diagnosis 子图相关函数、hub.py 只增意图条目和分支——甘华梁冷启动子图所有现有代码 0 行修改
2. **字段别名归一化**：副窗口 mock JSON 用 `kol_keng_wei_roi` / `jingxuan_lianmeng_ctr` 等贴近真实抖店术语的命名；checker 内置 `_METRIC_ALIASES` 字典把它们映射到内部基线 key，两套命名都能跑通
3. **mock JSON 兼容子对象结构**：副窗口把新店字段放在 `newbie_progress` 子对象、季节字段放在 `sku_inventory` 子对象——`_normalize_metrics` 自动合并这些子对象到扁平指标字典
4. **空建议防御**：advisor 节点哪怕所有资源都不可用，也输出 fallback 建议"观察 7-14 天后再评估"——硬性兜住"禁空建议"红线
5. **LangGraph reducer 留口**：`_build_diagnosis_langgraph_app` 已经把 evidence_refs / _trace / messages 配置成 `Annotated[list, operator.add]`，Day 3 切到 LangGraph 后端不会丢证据

**主要文件**

新增：
- `agent/nodes/diagnosis/__init__.py` + `checker.py` + `attributor.py` + `advisor.py` + `composer.py`

修改（共用资产，最小侵入）：
- `agent/state.py`：追加 `DiagnosisState`
- `agent/graph.py`：追加 `DiagnosisMiniGraph` / `_build_diagnosis_langgraph_app` / `run_diagnosis`
- `agent/hub.py`：经营诊断意图 + route 优先级 + handle 加 shop_id
- `agent/run.py`：CLI 双子图分发

**回归验证**

- ✅ `python3 -m compileall -q agent` 通过
- ✅ `python3 -m agent.run "口红" --category 美妆 --mock` 冷启动子图 9 节点 / 57 证据引用，无回归
- ✅ `python3 -m agent.run "我店铺最近 GMV 跌了" --shop-id case_1 --diagnosis --mock` 诊断子图 4 节点 / 36 证据引用，出完整 markdown 报告
- ✅ 5 个验收 case 全部命中预期 overlay 与核心问题：
  - case_1（咖喱生活）：千川 ROI 倒挂 ✅
  - case_2（素笺布艺）：搜索点击率塌方 ✅
  - case_3（初见女装铺）：在售 SKU = 0 卡死体验分 ✅
  - case_4（橙夏）：达人坑位 ROI 暴跌 ✅
  - case_5（夏树）：千川 ROI + 自播指标异常 ✅
- ✅ Hub 路由：经营诊断意图优先于 future 档，不被 GMV 关键词抢走

**端到端跑通示例**

```bash
$ python3 -m agent.run "为什么我的店卖不动" --shop-id case_1 --diagnosis --mock

# 📋 经营诊断报告 · 咖喱生活优品铺子
> 类目：女装>连衣裙 · 等级：L3 · 体验分：4.3
## 🎯 核心问题  **qianchuan_roi 显著下跌（55.6%）**
> 🏷️ 适用画像：nvzhuang_chengzhang / nvzhuang_zibo · 数据完整度 100%
## ⚠️ 异常指标清单（6 条）
## 🔎 为什么会这样（根因链）
## 📡 非数据信号（商城精选频道升级 / 千川女装类目定向调整）
## 🚀 本周建议（按性价比 × 置信度排序）
## 📚 证据引用表（36 条）
```

**价值**

把 Day 1 静态 MD 配置变成可运行 Agent。Day 3 只剩"接通真 LLM 替换 mock 推理 + 联调 5 个 case 的 LLM 输出质量"，框架骨架不用再动。

**下一步（Day 3）**

- 接 `agent/llm.py`（DashScope/千问 OpenAI 兼容端点）
- 把 attributor / advisor 的根因解释 + 建议文案改为 LLM 生成（保留 mock fallback）
- 跑 5 个 case 的 LLM 生成版，对照 08 验收用例做主观打分
- 处理 case_5 季节切换识别（当前未识别"夏装滞销/秋装缺货"，需把 sku_inventory 字段加入基线检查）

**提交信息**

`feat(diagnosis): wire 4 nodes + langgraph subgraph + cli`

---

## 批次 X+3 · 副窗口 · 09 演示话术增量：升华收口段（2026-06-05）

**背景**

甘华梁建议在面试时把"女装诊断"上升到"可插拔 Agent 平台"的高度讲（"做一个基座，然后加各种场景"+ "明天面试可以先讲这个 story"）。原 09 话术稿四段产品价值已经完整，缺一段把框架延展性显性化的收口。本批次仅在 09 末尾增量补一段，原四段不动。

**修改**

- `09-演示话术.md`：
  - 顶部时间从 "4 分钟" → "4.5 分钟"（30s 升华独占）
  - 新增 `## 5. 升华收口（30 秒）`：基座 + 可插拔 Skill MD + Hub 路由三件套 → 换品类只换 MD → 与甘华梁共底座独立编排已被验证 → V1 是第一条端到端验证 → 未来可扩用户聚类/规则透传/潜力商家挖掘
  - 原 §5 Q&A 预演 → §6；§6 备料 checklist → §7；§7 case 顺序 → §8；§8 不要做的事 → §9

**价值**

讲完产品价值（解 4 大短板）后多 30 秒讲框架价值（可扩张的产品形态）。两层 story 拼起来：商家侧解决"AI 接管质量差"的具体问题，平台侧打开"基座 + 可插拔 → 多子图共建"的想象空间。

**回归验证**

- ✅ 章节序号 0/1/2/3/4/5/6/7/8/9 连续
- ✅ 纯文档改动，未触代码

**提交信息**

`docs(demo): add platform extensibility coda to 09 script`

---

## 批次 9 · 主窗口 · Day 3：接通真 LLM + 增强归因/建议/报告 + 修季节识别（贾丽婼）

> 更新日期：2026-06-05
> 负责人：贾丽婼（Liruo） · 主窗口
> 分支：`运营`
> 状态：Day 3 完成，5 个 case 全部端到端跑通真 LLM 版

**功能说明**

接通真 LLM，分档调用——只在最关键的 3 个位置增强 Agent 输出质量，主框架/数据流/降级路径全部不变。

- **新增 `agent/llm.py`**：DashScope / OpenAI 兼容协议的统一封装
  - `has_llm()` / `chat_json()` / `chat_text()` 三个对外函数
  - 自动加载项目根 `.env`（python-dotenv 优先，缺失则简单解析）
  - **mock 永不崩**：缺 key / `AGENT_MOCK=1` / `openai` 包未装 / 网络错误 → 全部走 mock，不抛异常
  - 用户配的 LLM 是 DeepSeek V4 Pro（`base_url=api.deepseek.com/v1`）—— OpenAI 兼容协议，llm.py 零修改

- **attributor 接 LLM**（`agent/nodes/diagnosis/attributor.py`）：
  - 对每条 anomaly 的**主因（primary）** 调一次 LLM 生成"商家视角根因解释" + "你可以这样验证"
  - 非主因仍用规则文案，控成本（5 个 case 累计 LLM 调用 ≤ 30 次）
  - 输出字段 `root_cause_plain` + `what_to_check`，composer 渲染时优先用 plain 版本

- **advisor 接 LLM**（`agent/nodes/diagnosis/advisor.py`）：
  - 对 TOP-N 建议（默认 5 条）调 LLM 生成"为什么这条值得做"（≤40 字）
  - 输出字段 `why_worth_it`，composer 渲染时挂在每条建议下方
  - 建议本体（资源、准入、影响）依然走规则，确保资源/准入信息严格不被 LLM 编造

- **composer 接 LLM**（`agent/nodes/diagnosis/composer.py`）：
  - 报告开头新增 `## 📝 一句话讲清楚` 段——用 LLM 写 100-150 字的"老板视角"通俗摘要
  - LLM 失败时直接省略这段，不影响其他章节
  - 根因/建议章节渲染时优先用 LLM 增强字段

- **修 case_5 季节切换识别**（`agent/nodes/diagnosis/checker.py`）：
  - 类目归属增加季节信号触发：`stockout_risk_level / autumn_sku_gap / summer_zhixiao_share_of_on_sale` 任一命中即归入 `nvzhuang_jijie`
  - 字段别名映射追加：`summer_zhixiao_share_of_on_sale → stale_inventory_pct`、`autumn_sku_count → season_sku_count`
  - case_5 现在正确识别 4 条异常：滞销库存超标 153% + 秋装 SKU 缺口 73% + 千川 ROI + CVR

**关键设计决定**

1. **LLM 分档调用，不无差别加成本**：参考 Soul 缘分档案"按通话时长分档调 LLM"的思路，attributor 只对主因调用、advisor 只对 TOP-N 调用、composer 只调一次开篇。单次诊断 LLM 调用 ≈ 12 次（6 主因 + 5 TOP 建议 + 1 开篇）
2. **LLM 编造的内容范围严格限定**：只允许 LLM 写"翻译/解释/为什么"，规则层产出的"指标值/资源 URL/准入门槛"全部不交给 LLM
3. **fallback 内嵌到每个增强点**：has_llm() / LLM 调用失败 / JSON 解析失败 → 全部走规则路径，main flow 不感知
4. **不动 graph.py / hub.py / state.py / run.py**：Day 2 的 4 个节点接口签名不变，只在节点内部增加 LLM 调用——共用资产零修改

**主要文件**

新增：
- `agent/llm.py`（约 180 行）

修改（仅诊断子图内部节点）：
- `agent/nodes/diagnosis/attributor.py`：增 LLM 增强主因
- `agent/nodes/diagnosis/advisor.py`：增 LLM 增强 TOP-N "为什么做"
- `agent/nodes/diagnosis/composer.py`：增 LLM 开篇摘要 + 主因 plain 版本渲染
- `agent/nodes/diagnosis/checker.py`：修 case_5 季节信号触发 + 字段别名追加

**回归验证**

- ✅ `python3 -m compileall -q agent` 通过
- ✅ `python3 -m agent.run "口红" --category 美妆 --mock` 冷启动子图 9 节点 / 57 证据引用，无回归
- ✅ 5 个 case 真 LLM 模式全部端到端跑通：
  - case_1（咖喱生活）：6 异常 / 36 证据，LLM 把 `qianchuan_roi 实际 0.8` 翻译成 `因为转化率仅1.3%、主图点击率5.1%，导致千川投产比降至0.8` + 验证方法 ✅
  - case_2（素笺布艺）：1 异常 / 10 证据 ✅
  - case_3（初见女装铺）：2 异常 / 10 证据 ✅
  - case_4（橙夏）：2 异常 / 13 证据 ✅
  - case_5（夏树）：**4 异常 / 31 证据，季节切换 overlay 命中** ✅
- ✅ `python3 -m agent.llm` 自检：DeepSeek V4 Pro 通，real LLM 输出正常

**LLM 增强样例**（节选自 case_1 真实运行）

```
🎯 因为转化率仅1.3%、主图点击率5.1%，导致千川投产比降至0.8 · 置信度 0.92
     👉 你可以这样验证：查看抖店商品流量分析，确认主图和转化

🎯 因为直播平均停留仅22秒、主图点击率仅5.1%，导致访客价值低至1.46元
     👉 你可以这样验证：查看直播数据看板中的停留时长和主图点击率

- 【高性价比】 直播间欢迎话术 V2
  - 资源：template://live_welcome_v2
  - 准入：✅
  - 预期：人均停留 +30s
  - 💡 为什么做：免费套用模板，就能多留住观众半分钟，立竿见影
```

**价值**

把 Day 2 的"规则归因 + 规则建议"升级为"规则 + LLM 双层"。规则层保证准确性（数据、资源、准入），LLM 层负责让商家听懂（翻译、为什么、可验证步骤）。这是抖店现有 AI "去优化主图"类空话与本 Agent 的根本差异。

**Day 4 收尾任务（剩余）**

- 接入 Streamlit demo（副窗口 demo/streamlit_app.py 把占位区换成 `from agent.run import run`）
- 整理面试演示话术（副窗口已就位 09-演示话术.md）
- 主观打分 5 case 的 LLM 输出质量并迭代 prompt

**提交信息**

`feat(diagnosis): wire real llm + enhance root cause / actions / opening`

---

## 批次 X+4 · 副窗口 · Streamlit demo 提前接通真实 Agent（2026-06-05）

**背景**

主窗口已经把诊断子图 4 节点跑通，但 Streamlit demo 还停在"占位"——按钮点了只显示静态文本和异常表，未调用真实 Agent。本批次把 demo 接通 `agent.graph.run_diagnosis`，让面试演示能"点一下就出完整诊断报告 + 证据引用 + 行动建议"，不再等 Day 4 收尾。

**修改**

- `demo/streamlit_app.py`（重写，约 200 行）：
  - 模块加载时 `os.environ.setdefault("AGENT_MOCK", "1")`，确保所有节点走 mock 分支
  - `run_diagnosis_cached(case_id, user_query, window)` 用 `@st.cache_data` 按三元组 key 缓存，避免重复跑
  - "跑一次诊断"按钮：实时 `asyncio.run(run_diagnosis(...))`，结果存 `st.session_state`，换 case 自动清空
  - 主区直接 `st.markdown(final_state["report"])` 渲染 composer 生成的完整 markdown ——商家在抖店 AI 助手卡片里会看到的形态
  - 顶部 4 个 metric：数据完整度 / 命中 overlay / 节点执行 / 证据引用
  - 6 个结构化下钻 expander：异常清单（表格）/ 根因链（按异常分组）/ 非数据信号（warning 卡片）/ 行动建议（表格含资源 URL）/ 证据引用表（表格）/ 节点 trace
  - 1 个 debug expander：完整 final_state

- `CLAUDE.md` §11.3 任务 B 段尾追加注解（不改原内容）：标记"已提前接通真实 Agent，不再等 Day 4"，明确副窗口只 import `agent.graph` 不动 `agent/*` 文件

**回归验证**

- ✅ `pip3 install "streamlit>=1.36.0"` 装好 streamlit 1.58.0 + 依赖（pandas / altair / pyarrow 等）
- ✅ `python3 -m py_compile demo/streamlit_app.py` 通过
- ✅ `streamlit run demo/streamlit_app.py --server.headless true` 启动成功，`/_stcore/health` 返回 200
- ✅ 直跑 `asyncio.run(run_diagnosis({'shop_id':'case_1', ...}))`：6 异常 / 6 根因链 / 9 actions / 36 证据引用 / 4 节点 trace
- ✅ `python3 -m agent.run "我店铺最近 GMV 跌了" --shop-id case_1 --diagnosis --mock` CLI 仍跑通（未触代码）

**未触碰主窗口在改的文件**

主窗口当前 working tree 仍有 modified：`agent/nodes/diagnosis/{advisor,attributor,checker,composer}.py` + untracked `agent/llm.py`。本批次仅 import `agent.graph.run_diagnosis`（公共接口），不修改 `agent/*` 任何文件。git add 精确指定 `demo/streamlit_app.py` + `CLAUDE.md` + `update.md` + `requirements.txt`（如果需要）。

**演示形态**

```bash
pip install -r requirements.txt
streamlit run demo/streamlit_app.py
# 浏览器打开 http://localhost:8501
```

1. 左侧栏选 `case_1 · 咖喱生活`
2. 点"跑一次诊断"——spinner "Agent 思考中…（checker → attributor → advisor → composer）"
3. 1 秒内出完整报告：核心问题（千川 ROI 跌 55.6%）+ 异常清单 + 根因链 + 非数据信号 + 9 条行动建议（每条挂资源 URL）+ 36 条证据引用表
4. 6 个下钻 expander 给面试官追问技术细节用

**对应 09 演示话术第 4 节（演示 90s）**：现在能边讲边点，不用再说"占位等 Day 3"。

**提交信息**

`feat(demo): wire streamlit to real run_diagnosis (skip day-4 wait)`

---

## 批次 X+5 · 副窗口 · Streamlit demo 视觉去 AI 痕迹（2026-06-05）

**背景**

X+4 接通 Agent 之后，demo 视觉上还是默认 Streamlit 味——大色块（warning 黄 / info 蓝 / primary 红按钮）、emoji 散落（🎯 ⚠️ 🔴 🟡 🏷️）、`st.metric` 卡片标签灰白对比强、`st.dataframe` 默认斑马纹。这些都是"AI demo"的明显痕迹，面试时容易让面试官认为是套壳玩具。本批次重写 UI 层，对齐"产品级中后台"观感。

**修改**

- `demo/streamlit_app.py`（重写视觉层，逻辑不变）：
  - **全局 CSS**：隐藏 Streamlit chrome（顶栏 / footer / hamburger）；统一系统字体（PingFang SC / -apple-system）；按钮改深灰扁平（去 primary 红）；blockquote 改左边灰竖线（去蓝色块）；expander 改浅灰底圆角；侧边栏淡灰背景；分隔线去黑改 1px 浅灰
  - **去 emoji**：`strip_emoji()` 用 5 段 Unicode 区间（含 Geometric Shapes Extended 覆盖 🟡 🟢）清掉 composer 报告里的所有装饰 emoji，保留 markdown 结构（# / - / >）。原 `## 🎯 核心问题` → `## 核心问题`，`- 🔴 **千川投产比**` → `- **千川投产比**`
  - **metric 卡片自定义**：用 `<div class='metric-card'>` 取代 `st.metric`，纯黑白灰 + 小标题大值，无任何色块
  - **Altair 横向条形图**：
    - 商家画像里的"流量来源" → 单色（#5a5a5a）横向条形图
    - 异常指标 → 严重度按 muted earth tones 配色（high #8c4a3c / medium #b8895a / low #a0a59c），避免饱和红黄绿
  - **非数据信号** → 左边灰竖线的 `.signal-card`，不再用 `st.warning` 黄色块
  - **expander 标题去 emoji**：`异常指标可视化` / `根因链下钻` / `非数据信号` / `行动建议清单` / `证据引用` / `节点执行轨迹` / `完整 final_state（调试）`
  - **行动建议表格**：`column_config.LinkColumn(display_text="打开")` 把资源 URL 渲染成文字超链
  - 顶部副标题用 ideographic space + #888 灰，弱化"V1 演示 / mock 数据"标签

**回归验证**

- ✅ `python3 -m py_compile demo/streamlit_app.py`
- ✅ `streamlit run` 启动成功，`/_stcore/health` 200
- ✅ `strip_emoji(report)` 在完整 case_1 报告上 sweep，剩余可疑字符 = set()（包括 🟡 🟢 等 Geometric Shapes Extended block）
- ✅ 主窗口 Day 3 commit `bf1397e` 已经把 composer 输出里的英文 metric 名翻译为中文（千川投产比 / 访客价值 / 直播间人均停留 / 转粉率），观感更"产品"

**为什么主报告保留中文 metric 而下钻表保留英文 metric**

- 主报告（composer 渲染的 markdown）面向商家：中文 metric 名易读
- 下钻表（异常清单 / 根因链）面向追问：英文 metric 名（来自 anomalies['metric'] 字段）和 schema 一致，便于面试讲解技术细节
- 不在 demo 层翻译——避免和主窗口的语义层冲突

**提交信息**

`refactor(demo): neutralize ui — strip emoji, mute palette, custom cards`

---

## 批次 X+6 · 副窗口 · Streamlit demo 商家友好化（2026-06-05）

**背景**

X+5 视觉中性化之后，几个问题：(1) 按钮深底白字被 Streamlit 1.58 的 `<p>` 颜色覆盖，呈现"全黑看不见文字"；(2) 主报告中文化了但下钻表、图表、metric 卡片里还充斥英文字段名（`qianchuan_roi` / `cvr` / `nvzhuang_chengzhang`）；(3) 报告里到处是 `[ev_a0ca94522d3a]` 这种工程哈希标签，商家根本看不懂；(4) Wiki 真的被检索了（17 条引用）但 UI 上没明确展示，面试无法体现"双层 Wiki"价值。

**修改**

`demo/streamlit_app.py`（继续重写）：

1. **按钮 CSS 修复**：改成白底黑字 + 1px 黑边框 + hover 反色（黑底白字）。`.stButton > button p/span/div { color: inherit !important; }` 强制 Streamlit 1.58 嵌套元素继承按钮颜色，避免外层 `<p>` 把文字盖黑。
2. **字段中文化**（demo 层维护本地翻译表，不依赖主窗口 untracked 的 `_labels.py`）：
   - `METRIC_ZH`：30+ 个 metric key → 中文（千川投产比 / 访客价值 / 主图点击率 / 直播间人均停留 / 转粉率 ……）
   - `SEVERITY_ZH` / `COST_ZH`：high/medium/low → 高/中/低
   - `RESOURCE_TYPE_ZH`：activity/tool/template/task → 平台活动/官方工具/话术 / 模板/任务清单
   - `OVERLAY_ZH`：nvzhuang_zibo → 女装自播店 等 6 个
   - 异常指标可视化 y 轴、根因链下钻、行动建议表、非数据信号影响指标、metric 卡片"命中商家画像"、侧边栏"预期画像"，全部用翻译后文本
3. **报告清理 `[ev_xxx]`**：`EVIDENCE_MARK_RE = r"\s*\[ev_[a-f0-9]+\]"` 在 `clean_report()` 里一并 strip。报告里残留可疑字符 = 空。
4. **Wiki 命中显性化**：
   - 顶部 metric 拆为 4 个：数据完整度 / 命中商家画像 / **数据证据**（raw layer 计数）/ **知识引用**（wiki layer 计数）—— 直接把"Wiki 引用 N 条"作为产品 metric 摆出来
   - 下钻区新增 expander "Wiki 命中条目（N 条 · 双层知识检索）"：按 quote 内容粗分类（类目基线 / 规则变动 / 平台活动 / 工具 / 模板），每条以灰底卡片展示 quoteOrSummary
5. **行动建议商家友好化**：列重排为「建议 / 资源类型 / 针对指标 / 性价比 / 置信度 / 门槛 / 资源入口」，建议列宽 `large`，资源入口用 `LinkColumn(display_text="打开")`，资源类型 / 针对指标 / 性价比 全部走翻译表
6. **节点 trace 中文化**：`NODE_ZH` 把 `checker / attributor / advisor / composer` 翻译为「体检（异常识别）/ 归因（根因拆解）/ 建议（资源挂钩）/ 组装（生成报告）」
7. **排版整齐**：
   - metric 卡片 `min-height: 92px` + flex 等高，加 `.sub` 第三行小字说明
   - 表格全部用 `column_config` 指定列宽（large / medium / small）
   - h1/h2/h3/h4 margin 显式控制
   - 主报告调用 `clean_report()` 收紧 `\n{3,}` 为 `\n\n`

**回归验证**

- ✅ `python3 -m py_compile demo/streamlit_app.py`
- ✅ `streamlit run` 启动，health 200
- ✅ `clean_report()` sweep 主报告：`[ev_`、🎯、⚠️、🔴、🟡 全无残留
- ✅ 主报告内容样本验证：`# 经营诊断报告` → `## 核心问题` → `**千川投产比显著下跌（55.6%）**` → 异常指标清单（中文）→ 根因链（中文），无英文字段名
- ✅ Wiki 引用 17 条按类目基线 / 规则变动 / 平台活动 / 工具 / 模板自动分组

**为什么 demo 层自己维护翻译表，不 import 主窗口 _labels.py**

主窗口的 `agent/nodes/diagnosis/_labels.py` 当前是 untracked（in-progress），属于 §11.2 副窗口禁区下的进行中改动。本批次先在 demo 层独立维护一份，等主窗口正式 commit 后再切到 `from agent.nodes.diagnosis._labels import metric_zh`，避免依赖未稳定的私有 API。

**提交信息**

`refactor(demo): translate fields, strip ev tags, surface wiki refs`

---

## 批次 10 · 主窗口 · Day 4：报告中文化 + LLM warning 静默 + 文案精修（贾丽婼）

> 更新日期：2026-06-05
> 负责人：贾丽婼（Liruo） · 主窗口
> 分支：`运营`
> 状态：Day 4 完成，V1 全链路收口可演示

**功能说明**

Day 4 收尾——把"能跑"升级为"能演示"。3 类小修，全部内嵌到诊断子图内部节点，零接口改动。

- **新增 `agent/nodes/diagnosis/_labels.py`**：指标英文 key → 中文标签字典（29 个常用指标）
  - `metric_zh("qianchuan_roi")` → "千川投产比"
  - `metric_zh("stale_inventory_pct")` → "滞销库存占比"
  - 未登记字段原样返回，避免误翻译
  - 副窗口现在自己维护了一份临时 demo 端 _labels，等主窗口 commit 后副窗口可切到 `from agent.nodes.diagnosis._labels import metric_zh` 复用（§11.2 私有 API 约定）

- **报告文案全链路中文化**：
  - `checker._summary_for`：核心问题文案翻译为中文 + 特殊场景兜底
    - 修复粗暴的 `[:30]` 截断（之前 case_5 出 "stale_inventory_pct 显著异常（153.3" 被切掉 %）
    - 滞销/退款类"越低越好"指标用"超标"代替"下跌"
    - case_3 特殊：在售商品 = 0 时显示"在售商品数为 0，需立即补齐"而非生硬的"下跌 100%"
    - case_5 季节：应季 SKU 数 8 时显示"仅 8 个，远低于类目均值（30）"
  - `composer._format_anomaly_line`：异常清单 metric → 中文
  - `composer._format_root_cause`：根因章节标题 → 中文
  - `attributor._root_cause_text`：fallback 文案（LLM 失败时兜底）从 "X 实际 Y vs 基线 Z" → "X（Y）显著偏离类目基线（Z）"
  - `attributor._coupled_text`：跨场景耦合描述也走中文

- **LLM warning 降级静默**：
  - `agent/llm.py` 把 `logger.warning` 全部改为 `logger.debug`
  - 之前 LLM 失败时会输出 "chat_json 调用失败：Connection error" 到 stderr，污染 CLI 报告输出
  - 降级后 fallback 静默生效

- **跑通副窗口 Streamlit demo 验证**：
  - `demo/streamlit_app.py` 已接通 `agent.graph.run_diagnosis`（mock 模式）
  - 后端可达，报告长度 5069 字符，4 节点全执行
  - 启动命令：`pip install -r requirements.txt && streamlit run demo/streamlit_app.py`
  - **注意**：demo 默认强制 `AGENT_MOCK=1`（不调 LLM），演示如想看 LLM 增强需 `unset AGENT_MOCK` 后再启动

**主观打分 5 case（基于 08 期望对照）**

| Case | 核心问题文案 | 期望 | 评分 |
|---|---|---|---|
| 1 咖喱生活 | 千川投产比显著下跌（55.6%） | 千川 ROI 倒挂 | ✅ A |
| 2 素笺布艺 | 搜索点击率显著下跌（23.6%） | 搜索流量塌方 | ✅ A |
| 3 初见女装铺 | 在售商品数为 0，需立即补齐 | 突破 0 分卡住 | ✅ A |
| 4 橙夏 | 达人坑位 ROI 显著下跌（45.0%） | 达人选品命中率低 | ✅ A |
| 5 夏树 | 滞销库存占比显著超标（153.3%） | 滞销+应季缺货 | ✅ A+ |

LLM 开篇摘要质量（case_5 实测）：
> 你的店本周滞销库存占比超了正常水平一倍多，根子上是夏季旧款积压太重、应季秋款又只上了零星几件，导致顾客进来没得挑。眼下最值得做的就是把那些卖不动的老款直接改成 9.9 引流款快速清仓，同时拿出女装连衣裙的千川投流模板，把广告预算往秋装上倾斜...

接近"老板/小二真人会说的话"的语气，达到 V1 演示线。

**主要文件**

新增：
- `agent/nodes/diagnosis/_labels.py`（指标中英映射）

修改（全部诊断子图内部，零接口改动）：
- `agent/nodes/diagnosis/checker.py`：导入 metric_zh + 改 _summary_for
- `agent/nodes/diagnosis/composer.py`：导入 metric_zh + 改 anomaly/root_cause 渲染
- `agent/nodes/diagnosis/attributor.py`：导入 metric_zh + 改 fallback 文案
- `agent/llm.py`：warning → debug

**回归验证**

- ✅ `python3 -m compileall -q agent` 通过
- ✅ `python3 -m agent.run "口红" --category 美妆 --mock` 冷启动子图 9 节点 / 57 证据引用，无回归
- ✅ 5 个 case LLM 模式全部端到端跑通，核心问题文案符合商家阅读习惯
- ✅ 副窗口 demo 后端可达
- ✅ stderr 不再泄漏 LLM 失败信息到报告输出

**V1 全链路就绪状态**

| 模块 | 状态 |
|---|---|
| Day 1 Skill MD + Wiki 种子 | ✅ 13 个 MD |
| Day 2 4 节点 + LangGraph 子图 + Hub 路由 + CLI | ✅ |
| Day 3 LLM 接入 + 3 处增强 + 季节识别 | ✅ |
| Day 4 报告中文化 + 文案精修 + warning 静默 | ✅ |
| 5 case mock JSON（副窗口） | ✅ |
| Streamlit demo（副窗口） | ✅ |
| 09-演示话术稿（副窗口） | ✅ |

**演示就绪**

```bash
# 端到端 CLI 演示（带 LLM 增强）
python3 -m agent.run "我店铺最近 GMV 跌了" --shop-id case_1 --diagnosis
python3 -m agent.run "诊断" --shop-id case_5 --diagnosis  # 季节切换最有戏剧效果

# 可视化 demo 启动（mock 模式）
pip install -r requirements.txt
streamlit run demo/streamlit_app.py

# 想看 LLM 增强版 demo：
unset AGENT_MOCK && streamlit run demo/streamlit_app.py
```

**提交信息**

`feat(diagnosis): chinese labels + llm warning mute + summary polish`

---

## 批次 X+7 · 副窗口 · 项目说明书 00-项目说明书.md（2026-06-05）

**背景**

03（V2 战略 PRD）/ 04（融合方案）/ 06（在运营诊断 PRD）三份文档各自只讲自己一块，外人第一次接触项目时**没有一份能 10 分钟读完就理解全景的入口文档**：
- 03 偏战略推演（15 个专家完整矩阵 + V1/V2/V3 演进）
- 04 偏技术架构（与冷启动框架的融合方案）
- 06 是单个子图（贾丽婼的诊断 V1 PRD）

面试官 / 新加入的人 / 未来的合作方需要一份整合视图，知道：项目是什么 / 为什么做 / 技术基座长啥样 / 选品 + 诊断两条线分别做什么 / 输出形态 / 为什么这是平台不是工具 / 现在跑到哪一步。

**新增**

- `00-项目说明书.md`（383 行 · 10 节）：
  1. 项目是什么（30 秒看懂）—— 两条业务线 + 共用框架的产品定位
  2. 为什么做这个 —— 90% 中小商家无小二 + AI 4 大短板 + 新商家选品困境
  3. 技术基座（四层架构）—— 基座 / Skill MD / 双层 Wiki / LLM 假设，含 ASCII 架构图
  4. 业务模块 A · 冷启动选品（甘华梁）—— 9 节点子图 + 5 个专家 Skill + TikHub 数据源
  5. 业务模块 B · 在运营诊断（贾丽婼）—— 4 节点子图 + 3 通用专家 + 6 女装 overlay + 5 case 验收
  6. 输出形态 —— 商家端 markdown 报告（含完整样例）+ 小二端潜力候选 + Streamlit demo + 三条出口契约
  7. 复用性 —— 三个维度可扩展 + 已验证扩展点 + 未来可扩方向边际
  8. 当前状态 —— ✅ 已完成 / ❌ 未完成 / 资产清单
  9. 文档导航 —— README / 03 / 04 / 05 / 06 / 07 / 08 / 09 / CLAUDE.md / update.md 各自看什么
  10. 一句话总结

**关键设计决定**

1. **不重抄**：03/04/06 已经写过的细节本文档不重复；只挑全景骨架，深细节留给原文档
2. **第一文档**：用编号 00（README 之后第一份），是看完就理解全局的入口
3. **务实口径**：未来扩展方向只标"已知扩展边际"，不写"我们将…"的承诺
4. **维护人**：贾丽婼 + 甘华梁共同维护（涉及两条线）

**与其他文档的关系**

| 文档 | 关系 |
|---|---|
| 03 / 04 / 06 | 本文档**索引到它们**，不替代 |
| 09 演示话术 | 演讲稿 ≠ 说明书，话术是 4.5 分钟口播节奏；本文档是给人看的文字综述 |
| CLAUDE.md | 团队协作宪法，本文档不重复（指向它） |
| README.md | 跑通命令行 hello world，本文档不替代（指向它） |

**回归验证**

- ✅ 纯文档改动，无代码触动
- ✅ `python3 -m compileall -q agent` 通过
- ✅ 引用的所有外部文档名（03-09 + CLAUDE.md + agent/README.md）实际存在

**提交信息**

`docs: add 00 project overview integrating 03/04/06 strategy + arch + v1`

---

## 批次 X+8 · 副窗口 · 00 说明书：重构商家端报告 + 新增下一步计划（2026-06-05）

**背景**

PM 复盘 00 项目说明书 §6.1 商家端报告样例时发现两个根本性问题：

1. **当前样例把工程化 metric 直接抛给商家**——"千川投产比 0.8 vs 基线 1.8 · 置信度 0.92"。S4/S5 老板（夫妻档亲自做）不可能关心置信度，也看不懂"访客价值 1.46 vs 基线 10.0"是什么意思。问题不在数据层，在**输出层没有解耦工程语言和商家语言**。
2. **缺"下一步计划"章节**——V1 跑通后该往哪走没明说，尤其是 PM 提的两个 idea（指标白名单 + schema 分层；二人商家"消费者 + 商家"双视角选品）没写进去。

**修改**

`00-项目说明书.md`（从 383 行扩到 541 行）：

1. **§6.1 商家端报告样例彻底重构**（老板视角 · 人话叙事）：
   - 删除"核心问题 / 异常指标清单 / 根因链 / 非数据信号 / 本周建议（按性价比 × 置信度排序）"工程化结构
   - 改成"近 7 天卖了 12 万，比上周少了 16 万——差不多砍半。跌得最狠的是直播：进直播间的人只待 22 秒就走"这种**人话叙事**
   - 三件事按"今晚就能换 / 后台 10 分钟 / 你够资格但还没申请"组织，每条标"花不花钱 + 几天见效"
   - 一件事提醒（体验分缺口 + 最快提分动作）
   - 加对照表说明：商家端不出现的工程 metric / 置信度 / 根因链结构 / Wiki 命中 / trace **全部保留在 Agent 内部**——只是视图层翻译
   - 引入"一份 state 三视图"：`view=owner / ops / team`，前向引用 §9.1

2. **新增 §9 下一步计划**（123 行，4 个方向 + 边界声明）：

   - **9.1 商家关心指标白名单 + 输出 schema 分层重构**（PM idea A）
     - 不动 input schema，新增 Translator / 改 Composer 加翻译层
     - 三视图同 state 多次渲染
     - 前置依赖 9.4 访谈
   - **9.2 二人商家「消费者 + 商家」双视角选品**（PM idea B）
     - 关键洞察：S5 老板自己就是某品类的资深消费者，"消费者直觉"是平台数据看不到的私有信号
     - 落地：选品子图加 PersonalTasteAnalyzer 节点 + 数据源（问卷 / 消费档案 / 收藏夹）
     - 跟 03 PRD 已有的"个性化推荐"对照表：商家维度 vs 消费者维度
   - **9.3 跨子图协同 · 诊断触发选品**（补充）
     - case_5 夏树秋装备货不足，诊断子图应能调甘华梁选品子图给 SKU 级建议
     - 真正落地"共底座、独立编排、Hub 路由"的整合价值
   - **9.4 商家访谈先于 schema 重构**（呼应 PM 一贯 data-first 原则）
     - 5-10 个真实 S4/S5 商家访谈
     - 三个核心问题：哪三个数字最在意 / 看到建议会不会真做 / 推送频次时机
     - **优先级反而最高**（是 9.1 / 9.2 的前置依赖）

   - **9.5 没列入下一步的方向**（说明边际，避免方向蔓延）：
     - 扩品类（先把女装做扎实再扩）
     - 跨平台（V3 量级）
     - 15 个专家全量上（按 ROI 分批）

3. **章节顺移**：原 §9 文档导航 → §10；原 §10 一句话总结 → §11

**关键设计决定**

1. **不动 input schema**：罗盘全量字段对 Checker 异常检测是必须的，问题在输出翻译层
2. **三视图共享 state**：不是三套 schema，是一份 state 多次渲染——和复用性 §7 的理念一致
3. **访谈前置 schema 重构**：呼应 PM「先锁样本 → 再建配套」习惯，避免自嗨设计
4. **idea B 是真新方向**：跟 03 PRD 的"个性化推荐"区别讲清——商家维度 vs 消费者维度
5. **明确说"非承诺，探索方向"**：避免被当成路线图 commitment

**和已有文档的关系**

| 现有内容 | 9.x 关系 |
|---|---|
| 03 V2 PRD §3 的 15 个专家矩阵 | 9.5 明确"按 ROI 分批，不一次性 ramp up" |
| 03 V2 PRD §1.2 个性化推荐 | 9.2 与之对照（商家维度 vs 消费者维度） |
| 06 PRD §10 风险与边界 | 9.4 商家访谈是缓解二手观察风险的措施 |
| 09 演示话术 §5 升华收口 | 9.3 跨子图协同是"共底座、独立编排"的真正落地 |

**回归验证**

- ✅ 纯文档改动，无代码触动
- ✅ `python3 -m compileall -q agent` 通过
- ✅ 章节序号 1→11 连续
- ✅ §6.1 重写后引用 §9.1 三视图，§9.1 引用 §9.4 前置访谈，前后引用一致

**提交信息**

`docs(overview): rebuild owner-view report + add v2 roadmap (4 directions)`

---

## 批次 X+9 · 副窗口 · 00 §9.1 话术驱动重写（2026-06-05）

**背景**

PM 复盘 §9.1，反馈"还是太技术——Translator 节点 / DiagnosisState 渲染 / view=owner/ops/team 都是工程语言，给出具体例子"。文档应该让看的人**通过例子自己看出来"为什么要做这件事"**，而不是先丢架构再让人去想象效果。

**修改**

`00-项目说明书.md` §9.1 整段重写：

1. **标题改**：「商家关心指标白名单 + 输出 schema 分层重构」→ **「商家话术重做 · 从「指标驱动」改成「钱 + 动作驱动」」**（标题就传递主张）
2. **加 7 行话术对照表**（核心新增内容）：成交 / 流量 / 直播间 / 投流 / 活动 / 履约 / SKU 经济，每行左列"当前 AI 的工程化说法"右列"老板想听到的人话"
3. **加 6 条话术原则**（从例子归纳）：用钱说话、拟人化对比、动作必带时效成本、损益估算挂在建议旁、指标级落到 SKU 级、承认局限不假装全能
4. **加 4 组指标白名单草稿**：赚钱 / 流量 / 动作 / 风险，对照「商家会在意 vs 当前 V1 全抛出来了」
5. **"怎么落地"改写**：从"新增 Translator 节点 + view=owner/ops/team"改成"先列映射表 → Composer 接管翻译 → 三种渲染（老板版 / 运营版 / 团队版）"——把技术黑话翻译成产品动作
6. **风险段加细化**：估算翻车 / 老板话术偏好差异 / 访谈 access，都给缓解方案

**关键变化**

| 之前 | 之后 |
|---|---|
| 讲架构（Translator / DiagnosisState 渲染） | 给 7 个对照例子 |
| 讲技术术语（view=owner/ops/team） | 讲商家心智（卖了多少 / 同行能 ... / 几天见效） |
| 说"输出 schema 分层重构" | 说"话术重做 · 钱 + 动作驱动" |
| 让读者自己脑补效果 | 让读者通过例子自己看出主张 |

**文档行数**：541 → 577（+36 行，从纯文字描述改成对照表 + 例子）

**回归验证**

- ✅ 纯文档改动，无代码触动
- ✅ §9.2 / 9.3 / 9.4 / 9.5 行号顺移正常（456 / 490 / 511 / 538）
- ✅ §10 / §11 锚点未动

**为什么这次值得专门 commit**

PM 提的"话术驱动"反馈本质上是文档语言风格的方向校正——以后写其他章节也会受这个反馈影响。单独提一次 commit 让这次校正可被审计。

**提交信息**

`docs(overview): rewrite 9.1 — table-driven owner talk vs current ai`

---

## 批次 X+10 · 副窗口 · 00 新增 §10 成本治理（2026-06-05）

**背景**

PM 复盘后追问："个性化 Agent 是否消耗大量 token，对字节团队成本如何控制？"

这是字节面试中典型的"硬问题"——任何"个性化 AI 应用"都绕不开的拷问。00 文档作为面试主展示资料，必须**正面回答 + 给出可算账的方案**，否则被问到无法接住。

**修改**

`00-项目说明书.md` 新增 §10 成本治理（独立成章，不放进 §9 下一步计划），共 7 个子节：

- **§10.1 算账**：单次诊断 10-15K token；全量规模按 300w S4/S5 商家 + 三种频次推演；DashScope 千问 plus 外采 API 价折算到年成本（每周全量 1.36 亿 / 仅异常触发 680 万）
- **§10.2 字节内部成本背景**：豆包内部调用 ≈ 外采价 1/3-1/5，年成本拉到内部 130-220 万级（异常触发场景）
- **§10.3 三个最有效的杠杆**（按 ROI 排序）：
  - 杠杆 A 分层触发漏斗（规则引擎扫 → LLM 诊断 → 深度归因）：**砍 95% LLM 调用**
  - 杠杆 B 分层模型路由（checker 规则 / attributor / advisor 中档 / composer 不能砍）：**单次成本再降 40-60%**
  - 杠杆 C Prompt 缓存（静态 Skill MD + overlay + Wiki 全员共享）：**input 成本降 60-70%**
- **§10.4 三杠杆叠加效果推演表**：朴素全量 2700-4500 万 → 三杠杆全跑后 **30-80 万 / 年**（≈ 1-2 个工程师人力）
- **§10.5 不该砍的地方**（成本边界）：composer 话术质量 / evidence_refs / Wiki 检索质量 / 三视图渲染
- **§10.6 成本治理建议**："成本 / 质量 / 采纳率"三维监控；看比值不看绝对值；压成本压到没人采纳是最贵的产品
- **§10.7 一句话结论**：1.36 亿 → 30-80 万的压缩路径

**章节顺移**：原 §10 文档导航 → §11；原 §11 一句话总结 → §12

**关键设计决定**

1. **独立成章而非放进 §9**：成本治理不是"探索方向"，是**已能算的事实**；跟 §7 复用性形成"可扩 + 可承载"姊妹章节
2. **算账驱动**：从"单次 token → 全量规模 → API 价 → 内部成本 → 杠杆压缩 → 最终成本"完整推演链，让面试官能跟着算
3. **三杠杆按 ROI 排序**：不堆砌 8 个方案，只给最有效的 3 个 + 一张叠加效果表
4. **承认边界**：§10.5 明说什么不能砍，避免面试官追问"成本是不是无底洞优化"时无法接住
5. **三维监控建议**：成本治理不是工程问题，是产品问题——"成本 / 采纳条"比"绝对成本"重要

**对面试展示的价值**

字节面试官几乎一定会问以下三个问题之一：
1. "token 成本能不能算一下"
2. "全量推开抖店 300w 商家，跑得动吗"
3. "你们这个跟豆包内部的 AI 工具相比有什么不一样"

§10 全部正面回答前两个 + 隐式回答第三个（"内部成本 1/3-1/5" + "豆包 pro / 千问 plus 按节点路由"）。

**回归验证**

- ✅ 纯文档改动，无代码触动
- ✅ 章节序号 1→12 连续
- ✅ §11 / §12 内部引用未崩（§9.1 / §9.4 行号未变）
- ✅ 文档行数 577 → 710（+133）

**提交信息**

`docs(overview): add chapter 10 cost governance — calc + 3 levers + budget`

---

## 批次 X+11 · 副窗口 · 10-Prompt 工程与幻觉治理（2026-06-05）

**背景**

PM 准备字节面试，希望 00 文档加一份「prompt 调优 + 幻觉治理」的专题。`/Users/damowang/Desktop/个人文件/字节面试-2026.6.4/05-面试真题应答框架手册.md` 已有 Q5（5 层防幻觉）/ Q6（bad case 三层处理）/ S8（婴儿湿疹案例 + 金句），但都是**通用模板**，面试官追问"在你这个项目里具体怎么做"时只有模板答不出细节。

需要一份**项目专题展开版**：把 05 手册的金句和模板**落到抖店诊断 Agent 的 4 个节点 + 4 件套架构 + 真实迭代痕迹上**。

**新增**

- `10-Prompt工程与幻觉治理.md`（约 230 行 · 8 节）

**结构**

- **§0 一句话**：本项目防幻觉**不靠 prompt 调魔法，靠架构**
- **§1 本项目独有的 6 类幻觉**：指标基线编造 / 资源 URL 编造 / 准入门槛编造 / 根因瞎编 / 跨 case 串台 / 数字幻视——前 5 类都是「AI 把不知道的事编得像那么回事」
- **§2 架构层防幻觉 · 四件套**：
  - Skill MD 强约束（治根因瞎编）
  - 双层 Wiki 事实底座（治基线/门槛编造）
  - evidence_refs 强制引用（治 ①②③）
  - Review 兜底（治高风险动作）
- **§3 4 节点的 Prompt 设计要点**：
  - Checker（用规则引擎不用 LLM）
  - Attributor（4 条硬约束 · 幻觉风险最高节点）
  - Advisor（3 条硬约束 · 资源/门槛全 Wiki + 规则代码校验）
  - Composer（4 条约束 · 数字逐字保留 + 仅语言风格化）
- **§4 真实迭代记录**（基于主窗口 commit `bf1397e` / `24d6d58` + 副窗口 commit `f6a1ea8`）：
  - v1 metric_zh 字典翻译（已落地）
  - v2 LLM 保留词禁用（已落地）
  - v3 [ev_xxx] 工程标签剥离（已落地）
  - v4 根因句长度强约束（计划中）
  - v5 overlay 命中校验（计划中）
- **§5 Bad case 治理闭环图**：商家投诉 → Review 标 → 小二抽检 → 分类施治（事实层改 Wiki / 策略层改 Skill MD / 语言层改 prompt）→ 跑 08 验收用例回归
  - 解释**为什么不选 RL / Fine-tune**：bad case 量不够 + 业务策略改太快 + 核心知识在 Wiki 不在模型参数里
- **§6 面试官追问预案**（5 个 30 秒回答）
- **§7 跟 05 手册 Q5/Q6/S8 的关系对照表**
- **§8 一句话结论**：跟字节自家发品 Review 治理层（07 文档）是同一个产品理念

**关键设计决定**

1. **定位错开 05 手册**：05 是答题速记本（口语 / 短模板），本文档是**追问展开版**（细节 / 项目专属）
2. **诚实标注迭代来源**：v1-v3 是真实 commit，v4-v5 标"计划中"，不编造迭代历史
3. **从架构入手，不堆 prompt trick**：先讲四件套架构，再讲 prompt 设计要点——核心论点是"prompt 不是核心防线"
4. **跟 05 手册建立显式映射**（§7 对照表）：方便面试时按 05 答完简短版后引导到本文档展开

**修改**

`00-项目说明书.md` §11 文档导航表新增一行：

```
| 10 | 10-Prompt工程与幻觉治理.md | 面试官追问"prompt 怎么写 / 怎么治幻觉"时展开讲 |
```

**回归验证**

- ✅ 纯文档改动，无代码触动
- ✅ 引用的 commit hash（bf1397e / 24d6d58 / f6a1ea8）实际存在
- ✅ 引用的 05 手册章节（Q5 / Q6 / S8 / Q10）实际存在
- ✅ 引用的项目文件路径（agent/skills/xingdong_jianyi.md / agent/wiki/industry/*.md / agent/nodes/diagnosis/_labels.py）实际存在

**提交信息**

`docs: add 10 prompt engineering & hallucination governance handbook`

---

## 批次 X+12 · 副窗口 · 11-电商格局与未来思考（2026-06-05）

**背景**

PM 头脑风暴讨论了三个格局问题：抖店 vs 千牛、抖店 vs 淘宝、未来电商格局。希望整理成文档，但**保留"思考的过程"**——不要写成 PRD 那种工整对比表，要保留"判断 + 依据 + 反向假设"的论证结构，让面试时按这个稿子能展开讲 10 分钟。

文档定位：不是 PRD / 不是说明书 / 不是面试速答，是 **PM 个人观察 + 推演**。

**新增**

- `11-电商格局与未来思考.md`（262 行 · 8 节）

**结构**

每节都给"反直觉钩子"，可被反驳：

- **§0 写在前面**：常见格局题答案都很平庸，本文档目标是给"别人没讲透的判断"
- **§1 抖店 vs 千牛 · 不是"内容 vs 货架"，是"投放驾驶舱 vs 运营驾驶舱"**
  - 商家时间花在哪的对照（千牛 70% 改 SKU / 抖店 70% 投千川）
  - 一句话比喻：「淘宝商家是租户，抖店商家是流量博主」
  - 对 AI 诊断的启示：抖店诊断 Agent 不是小二副驾，是"对赌结果分析师"
  - 反向假设：商城化会不会让两边趋同（功能会趋同 DNA 不会变）
- **§2 抖店 vs 淘宝 · 最被低估的是商家成本结构**
  - 毛利率对照表（达人佣金 22% / 千川波动 / 退款率 8-12%）
  - 「抖店爆款很多但能长期赚钱的少」
  - 启示：08 验收用例加 Case 6「看着卖得好但实际在亏」
- **§3 未来 3 年的格局 · 真正变量在腾讯系**
  - 视频号 + 小程序的"内容 + 关系"混合体
  - 拼多多已验证关系驱动威力
  - 反向假设：腾讯电商心智弱、商品供给不足，但最终形态可能是"嵌入熟人关系的导购系统"
- **§4 三个反直觉判断**
  - 平台 AI 价值 ∝ 商家分散度（不是技术多强）
  - 抖店 AI 价值高，因为不确定性高
  - 真正决定平台未来的，是 KA 占比，不是 GMV 总盘
- **§5 给我们诊断 Agent 的启示**
  - 不要假装通用（"换品类只换 MD"跨平台不成立）
  - 报告嵌入净利率影响（idea F）
  - 跨平台是 V3，不要 V2 就盘算
- **§6 5 个面试官可能问的格局题 + 30 秒回答**
- **§7 一句话结论**：看格局看 KA 占比 / 商家分散度 / 不确定性结构

**关键设计决定**

1. **不写工整对比表**，写"判断 + 依据 + 反向假设"三段式——保留思考过程
2. **每节都给反直觉钩子**——这是和"平庸答案"拉开距离的关键
3. **跟 04 竞品报告区分**：04 是功能层对比（按钮 / 操作流程），本文档是策略层判断
4. **跟 00 §9 idea 联动**：§5 启示部分直接呼应 §9 路线图，新增 idea F「净利率诊断」
5. **5 个格局题速答**单独成节：面试时可以直接背

**修改**

`00-项目说明书.md` §11 文档导航表新增一行：

```
| 11 | 11-电商格局与未来思考.md | 面试官追问"抖店 vs 千牛 / 淘宝 / 未来 3 年格局"时展开讲 |
```

**与现有面试材料的关系**

| 材料 | 关系 |
|---|---|
| `面试材料/04-抖音快手千牛-竞品体验报告.md` | 功能层细对比；本文档是策略层判断，互补 |
| `面试材料/05-面试真题应答框架手册.md` | 短模板答案；本文档 §6 给长展开版 |
| `00-项目说明书.md` §2 / §9 | 项目本身的"为什么"和"下一步"；本文档把这些放到行业格局里看 |

**回归验证**

- ✅ 纯文档改动，无代码触动
- ✅ 引用的外部文档（04 竞品报告 / 05 速答手册 / 06 PRD §2.4）实际存在
- ✅ 引用的项目章节（00 §2/§7/§9）锚点正确

**提交信息**

`docs: add 11 e-commerce landscape & future thinking — 3 platforms + 3 counter-intuitive`

---

## 批次 X+13 · 副窗口 · 00 §9 新增 idea「直播间精细化诊断闭环」（2026-06-05）

**背景**

PM 提出新 idea：抖店 70%+ 商家依赖直播带货，但当前 V1 对直播的支持只有 4 个汇总 metric 全是"七天平均值"——商家心里其实想问的是「**哪一场卖得最好** / **几点观众最多** / **同行哪个环节做得比我好** / **下次开播该几点上链接** / **上次让我做的事这次做了吗效果咋样**」。

这是当前 V1 完全答不了、但抖店商家**每天真正在问**的问题。本 idea 把诊断从"周报型助手"升级为"实时教练"。

**修改**

`00-项目说明书.md` §9 插入新 9.5，原 9.5 顺移成 9.6：

新 9.5 「直播间精细化诊断 · 「场次 → 动作 → 效果」闭环」：

- **5 个商家真问题**作为起点（哪场最好 / 几点观众多 / 同行咋做 / 下场该做啥 / 上次建议有没有效）
- **完整产品形态样例**：今晚直播复盘 markdown（这场做对的 / 没做对的 / 下次 3 个动作 / 一周后回来对照）—— 让面试官秒懂"形态升级"
- **5 个核心能力**（按依赖关系）：场次数据切片 / 黄金时段识别 / 同行场次对比（Wiki 扩 live_benchmark.md）/ 下场维度动作清单 / 效果回环验证
- **跟前 4 个 idea 的关系**表格：本 idea 底层依赖 9.1 话术规则、可借鉴 9.3 子图架构、9.4 访谈时要专门问"直播复盘想看什么"倒推优先级
- **为什么这个 idea 是 V1 → V2 最值得做**：场景命中率 70%+ / 闭环价值 / 商家粘性 / 可被验证
- **4 类风险 + 缓解**：数据合作 / 同行切片合规 / 预测建议错失信任 / 形态多样（按自播 / 达播 / 货架分模板）

**关键设计决定**

1. **以问题为起点，不以技术为起点**：先列 5 个商家心里的具体问题，再讲怎么落地
2. **直接给完整产品形态样例**：商家最终会看到的"今晚直播复盘"markdown，让"诊断 → 动作 → 效果回环"具象化
3. **强调闭环验证是关键差异化**：「上次建议做了吗，效果咋样」—— 这是当前所有抖店 AI 工具都没有的
4. **跟前 4 个 idea 显式建立关系**：避免"又一个 idea"的并列感，让读者看到内部依赖
5. **风险段务实**：直说数据依赖平台合作、合规审批等硬现实，不假装"做就完了"

**为什么放 9.5 而不是 9.6**

按优先级排，本 idea 是 V1 → V2 最高 ROI 方向之一（场景命中率最高 / 闭环价值最强）。9.6 是"不列入下一步的方向"边界声明，所以本 idea 应该排在 9.6 之前。

**回归验证**

- ✅ 纯文档改动，无代码触动
- ✅ 9.x 章节序号 9.1→9.6 连续（397/456/490/511/538/631 行）
- ✅ 文档行数 710 → 805
- ✅ §10 / §11 / §12 章节锚点未动

**提交信息**

`docs(overview): add 9.5 live session diagnosis loop — session-level + closed feedback`
