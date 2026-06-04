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
