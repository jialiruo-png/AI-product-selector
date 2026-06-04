# Codex 任务清单 — 电商经营 Agent 框架收尾

> 框架骨架已由 subagent 搭好并跑通（`python3 -m agent.run "口红" --mock` 可端到端出报告）。
> 本清单是交给 Codex 的**剩余任务**，按优先级分阶段，每条都给了「文件 / 做什么 / 验收命令」，可直接逐条派活。
> 编写日期 2026-06-04。

## 现状基线（Codex 开工前先确认）

```bash
cd /Users/ganhualiang/Desktop/AI选品工具-dev
python3 -m agent.run "口红" --category 美妆 --mock   # 应出含 人群/价格/爆款/竞品/风险 的报告 + 57 条证据
python3 -m compileall -q agent && echo OK            # 全部 byte-compile 通过
```

已落地：`agent/{state,graph,run,hub,evidence,review}.py`、`agent/nodes/*`、`agent/tools/*`、`agent/skills/*.md`、`agent/wiki/*`。
原 `采集工作台/scripts/` **禁止改动**（全靠 import 复用）。

---

## P0 — 让框架「真的有用」（建议 Codex 先做这 3 条）

### T1. 接通真实 LLM（替换 3 处 mock）
- **文件**：`agent/nodes/planner.py`（KeywordPlanner）、`agent/nodes/aggregate.py`（Briefing、Editor）
- **做什么**：把标了 `# TODO: wire real LLM` 的 mock 替换为真实调用。复用现有 `采集工作台/scripts/analyze.py` 里的 OpenAI 兼容客户端范式（DashScope 千问，`response_format={"type":"json_object"}`）。
  - 抽一个 `agent/llm.py`：`def chat_json(system, user, model=None) -> dict` 和 `def chat_text(system, user) -> str`，读 `.env` 的 `DASHSCOPE_API_KEY / LLM_BASE_URL / LLM_MODEL`。
  - **保留 mock 开关**：`AGENT_MOCK=1` 或缺 key 时仍走原 mock，不准崩。
  - KeywordPlanner：叶子类目 + 关键词 → LLM 出 10-20 精准词（JSON 数组）。
  - Briefing：每个维度的 curated 数据 → 一段中文摘要。Editor：briefings → markdown 报告。
- **验收**：`python3 -m agent.run "口红" --category 美妆`（不带 --mock，需真 key）出的精准词/报告是 LLM 生成而非模板；`python3 -m agent.run "口红" --mock` 仍正常。

### T2. 真实 TikHub 数据链路联调
- **文件**：`agent/tools/tikhub_tools.py`、`agent/nodes/analyzers.py`
- **做什么**：用真 `TIKHUB_API_KEY` 跑非 mock 模式，验证：
  - `search_products` 真实返回字段（`product_id/price/sold/rating`）正确流进 `score.score_tiktok_products`（注意 score.py 读的是 `sold_info.sold_count` 等**嵌套字段**，mock 是扁平字段——确认真实数据走嵌套路径打分正常，分数不再是 0.5 基线）。
  - `fetch_reviews` 的 `page_start=1`（传 0 返回空，见 tikhub 文档）、400 重试不扣费。
  - PriceAnalyzer 写入的 `products` 真能被 HotItem/Competitor 读到（已加自取兜底，复核一次）。
- **验收**：`python3 -m agent.run "labubu" --region US --topn 5` 报告里价格带/竞品/痛点是真实数据。

### T3. SQLite 落库打通（趋势可复盘）
- **文件**：`agent/nodes/analyzers.py`（PriceAnalyzer 调 snapshot_write）、`agent/tools/tikhub_tools.py`
- **做什么**：把 `snapshot_write` 真正接到 `db.py` 的 `start_run + save_tiktok_products + save_reviews + save_pain_points`，run_id 透传进 state；非 mock 模式每次跑都落 SQLite。新增 `--db` 参数。
- **验收**：跑两次同关键词后 `python3 采集工作台/scripts/selector.py trend tiktok <pid>` 能看到两条快照对比。

---

## P1 — 框架完整度（PRD 对齐）

### T4. langgraph 真后端 + list reducer
- **文件**：`agent/graph.py`、`requirements.txt`
- **做什么**：把 `langgraph` 加进 requirements；让 `AGENT_USE_LANGGRAPH=1` 真正走 StateGraph（现在装了也优先 MiniGraph）。重点解决并行节点的 `_trace/evidence_refs` 列表合并——用 `Annotated[list, operator.add]` reducer。MiniGraph 作为无依赖兜底保留。
- **验收**：`pip install langgraph && AGENT_USE_LANGGRAPH=1 python3 -m agent.run "口红" --mock` trace 显示 `后端: langgraph`，evidence_refs 不丢、不重复。

### T5. Skill MD 驱动节点（配置即技能真正生效）
- **文件**：`agent/skills/loader.py`、`agent/nodes/*`、`agent/hub.py`
- **做什么**：现在节点是硬编码、Skill MD 只是文档。让节点的 system prompt / SOP / next_skill **从对应 .md 读取**（loader 已能解析）。Hub 沿 `next_skill` 串 Skill 链执行，而非写死路由。
- **验收**：改 `agent/skills/xuanpin.md` 的 SOP 描述 → 重跑不用改 .py，行为/提示词跟着变。

### T6. 证据引用前端可见 + Wiki 注入
- **文件**：`agent/nodes/aggregate.py`（Editor）、`agent/evidence.py`、`agent/wiki/`
- **做什么**：Editor 报告里每条结论后挂可点的 `[refId]`，文末列证据表（layer/sourceId/quote）。行业 Wiki 的打分口径/价格带 SOP 作为 `layer="wiki"` 证据注入报告。
- **验收**：报告含证据表，至少 1 条 `wiki` layer + N 条 `raw` layer。

---

## P2 — 扩展专家（◐/○ 档，按需）

### T7. ◐ 档专家落地（客服/核价）—— 不依赖原生 API
- **核价 Agent**：纯本地，新增 `agent/nodes/pricing.py` + `agent/skills/hejia.md`，商家导入原料成本 → 利润核算表。
- **客服 Agent**：商家 FAQ 导入 `SellerWiki` → RAG 应答。
- **验收**：`HubAgent().handle("帮我核算这个新品利润")` 返回核算结果。

### T8. ○ 档占位明确化（原生 API 适配器接口）
- **文件**：`agent/tools/` 新增 `native_tools.py`（抖店罗盘/千川/百应适配器**接口**，方法签名与 TikHub 工具一致，body 抛 `NotImplementedError("平台侧未来")`）。
- **目的**：证明「换数据源 Skill MD 不变」——罗盘归因/OKR 智能拆解等 ○ 档专家未来只需实现这层。
- **验收**：`native_tools.py` 与 `tikhub_tools.py` 工具名一一对应。

---

## 给 Codex 的总体约束

1. **不改 `采集工作台/scripts/`**（只 import）。
2. **mock 永不崩**：`AGENT_MOCK=1` 或缺 key 时所有节点必须能跑通出报告。
3. **每条任务做完跑一遍** `python3 -m agent.run "口红" --mock` 确保没回归。
4. **新依赖**写进 `requirements.txt`，且 MiniGraph 兜底不依赖 langgraph。
5. 优先级 **T1 → T2 → T3** 是「从能跑的骨架变成有真实价值的 demo」最短路径，其余按时间取舍。
