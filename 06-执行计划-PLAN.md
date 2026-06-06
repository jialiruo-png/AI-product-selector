# 执行计划 PLAN — 电商经营 Agent 框架往下推

> 编写日期 2026-06-04。本文件是「按步骤执行的路线图」，比 [05-Codex任务清单.md](05-Codex任务清单.md) 更偏顺序与决策；任务清单是派活卡片，本文件是开车路线。

---

## 0. 现状快照（开工前先跑一遍确认基线）

```bash
cd /Users/ganhualiang/Desktop/AI选品工具-dev
python3 -m agent.run "口红" --category 美妆 --mock     # 应出报告，trace 显示「后端: MiniGraph」，57 条证据
python3 -c "import langgraph" 2>&1                      # 现在会报 ModuleNotFoundError（langgraph 未装）
```

**结论**：
- ✅ LangGraph **风格**的编排骨架已搭好、能端到端跑（走内置 MiniGraph 纯 asyncio 兜底）。
- ❌ 真正的 `langgraph` 库**还没装**，`AGENT_USE_LANGGRAPH=1` 那条真后端路径**从未真跑过**（只有壳子）。
- 🟡 所有 LLM 节点是 mock 模板；真实 TikHub 链路、SQLite 落库尚未联调。

所以「往下推」的第一个里程碑就是：**把真 langgraph 后端点亮**，然后才是接真数据。

---

## 阶段 A — 点亮真 langgraph 后端（半天，先做这个）

**目标**：让 `AGENT_USE_LANGGRAPH=1` 真正走 `StateGraph`，MiniGraph 退回纯兜底。这是验证「我们确实有 langgraph 框架」的硬证据。

### A1. 装依赖 + 写进 requirements
- 把 `langgraph>=0.2` 加进 [requirements.txt](requirements.txt)。
- `pip install langgraph`。
- 验收：`python3 -c "import langgraph; print(langgraph.__version__)"` 不报错。

### A2. 跑通真后端，解决并行 list 合并
- **文件**：[agent/graph.py](agent/graph.py)
- 现在并行 4 个 analyzer 各自往 `_trace / evidence_refs` 追加，langgraph 默认覆盖会丢数据 → 必须给这些字段配 `Annotated[list, operator.add]` reducer。
- 验收：
  ```bash
  AGENT_USE_LANGGRAPH=1 python3 -m agent.run "口红" --mock
  # trace 必须显示「后端: langgraph」；evidence_refs 仍是 57 条（不丢不重复）；9 节点全到齐
  ```
- **回归**：`python3 -m agent.run "口红" --mock`（不带 env）仍走 MiniGraph 正常出报告。

> 完成 A 后，「LangGraph 框架已经有了吗」这个问题就有了 100% 肯定的答案：两套后端都能跑，默认 MiniGraph 兜底、可切真 langgraph。

---

## 阶段 B — 让框架「真的有用」（核心价值，最短路径）

顺序固定 **B1 → B2 → B3**，对应 05 清单的 T1/T2/T3。

### B1. 接通真实 LLM（替换 3 处 mock）
- **文件**：新增 [agent/llm.py](agent/llm.py)；改 [agent/nodes/planner.py](agent/nodes/planner.py)、[agent/nodes/aggregate.py](agent/nodes/aggregate.py)
- 抽 `agent/llm.py`：`chat_json(system, user, model=None) -> dict` / `chat_text(system, user) -> str`，复用 [采集工作台/scripts/analyze.py](采集工作台/scripts/analyze.py) 的 DashScope OpenAI 兼容范式，读 `.env` 的 `DASHSCOPE_API_KEY / LLM_BASE_URL / LLM_MODEL`。
- 三处接真：KeywordPlanner（类目→10-20 精准词）、Briefing（维度→中文摘要）、Editor（briefings→报告）。
- **铁律**：`AGENT_MOCK=1` 或缺 key 时仍走原 mock，**永不崩**。
- 验收：
  ```bash
  python3 -m agent.run "口红" --category 美妆          # 真 key：精准词/报告是 LLM 生成
  python3 -m agent.run "口红" --mock                   # 仍正常
  ```

### B2. 真实 TikHub 数据链路联调
- **文件**：[agent/tools/tikhub_tools.py](agent/tools/tikhub_tools.py)、[agent/nodes/analyzers.py](agent/nodes/analyzers.py)
- 用真 `TIKHUB_API_KEY` 跑非 mock，验证三件事：
  1. `search_products` 真实字段流进 `score.py` 打分——注意 score.py 读**嵌套字段**（`sold_info.sold_count` / `rate_info.score` / `product_price_info.sale_price_decimal`），mock 是扁平字段。确认真实数据分数不再是 0.5 基线。
  2. `fetch_reviews` 的 `page_start=1`（传 0 返回空）、400 重试不扣费。
  3. PriceAnalyzer 写的 `products` 真能被 HotItem/Competitor 读到（已加自取兜底，复核一次）。
- ⚠️ **记住**：抖音端无商品搜索，选品漏斗走 **TikTok Shop** 端点（见记忆 douyin-no-product-search）。
- 验收：`python3 -m agent.run "labubu" --region US --topn 5` 价格带/竞品/痛点是真实数据。

### B3. SQLite 落库打通（趋势可复盘）
- **文件**：[agent/nodes/analyzers.py](agent/nodes/analyzers.py)、[agent/tools/tikhub_tools.py](agent/tools/tikhub_tools.py)
- `snapshot_write` 真接 `db.py` 的 `start_run + save_tiktok_products + save_reviews + save_pain_points`，run_id 透传进 state；非 mock 每跑必落。新增 `--db` 参数。
- 验收：同关键词跑两次后 `python3 采集工作台/scripts/selector.py trend tiktok <pid>` 看到两条快照对比。

> **完成 B 这一里程碑 = 从「骨架能跑」变成「真出洞察的 demo」**——这是给别人演示的临界点。

---

## 阶段 C — 框架完整度（PRD 对齐，按需）

### C1. Skill MD 真正驱动节点（配置即技能）
- 节点 system prompt / SOP / next_skill 从 `agent/skills/*.md` 读（loader 已能解析），Hub 沿 `next_skill` 串链，不再硬编码路由。
- 验收：改 `agent/skills/xuanpin.md` 的 SOP → 重跑不动 .py，行为跟着变。

### C2. 证据引用前端可见 + Wiki 注入
- Editor 报告每条结论挂可点 `[refId]`，文末证据表（layer/sourceId/quote）；行业 Wiki 打分口径作为 `layer="wiki"` 证据注入。
- 验收：报告含证据表，≥1 条 wiki layer + N 条 raw layer。

---

## 阶段 D — 扩展专家（◐/○ 档，远期，按时间取舍）

- **D1 ◐ 档**：核价 Agent（纯本地 `agent/nodes/pricing.py` + `hejia.md`，成本→利润表）、客服 Agent（商家 FAQ→SellerWiki→RAG）。
- **D2 ○ 档占位**：新增 `agent/tools/native_tools.py`，抖店罗盘/千川/百应适配器**接口**与 TikHub 工具名一一对应，body 抛 `NotImplementedError("平台侧未来")`，证明「换数据源 Skill MD 不变」。

---

## 总约束（每阶段都要守）

1. **不改 `采集工作台/scripts/`**（只 import 复用）。
2. **mock 永不崩**：`AGENT_MOCK=1` 或缺 key 时所有节点必须出报告。
3. **每步做完跑** `python3 -m agent.run "口红" --mock` 防回归。
4. 新依赖写进 `requirements.txt`，且 MiniGraph 兜底不依赖 langgraph。

## 一句话路线

> **A（点亮真 langgraph）→ B1 接 LLM → B2 接 TikHub → B3 落库** 是核心主干，做完就是一个能演示、有真实价值的电商洞察 Agent；C/D 是完整度与远期扩展，按时间取舍。
