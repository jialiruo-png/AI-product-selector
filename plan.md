# Agent 化方案 (plan.md)

> 把 selector 从 CLI 工具升级为可对话的选品 Agent。

## 1. 现在 vs 目标

| | 现在 (CLI) | 目标 (Agent) |
|---|---|---|
| 入口 | `selector.py tiktok "labubu" --topn 5 --analyze` | `agent.py "我想做夏季宠物用品选品"` |
| 关键词 | 用户硬编码 | Agent 自己派生 / 扩展 |
| 平台/地区/Top-N | 命令行参数 | Agent 决策（哪个先跑、要不要换地区、值不值得拉评论） |
| 输出 | SQLite 表 + 控制台打印 | 自然语言**选品建议报告**：推荐品 / 不推荐品 / 理由 / 风险 |
| LLM 角色 | NLP 抽取器（一次 prompt → 一次 JSON） | **决策者**：调工具、看结果、决定下一步 |

**核心差异判定**：现在是"工具调 LLM"，Agent 是"LLM 调工具"。

## 2. 典型 user query（先锁这个，再倒推一切）

MVP 必须能跑通以下 3 类 query，每类各 1-2 个真实例子作为验收用例：

**Query A：定品类、要选品候选**
- 输入：`"我想做夏季宠物用品的小红书选品，给我 5 个值得做的品类"`
- 输出：5 个 SKU 候选 + 每个的 score / 价格区间 / 痛点摘要 / 推荐理由

**Query B：定关键词、要选哪条 SKU**
- 输入：`"labubu 在 TikTok Shop 美区，挑 3 个最值得卖的具体 SKU"`
- 输出：3 个 product_id + 销量/评分 + 痛点 + 推荐理由 + 风险点（库存少、差评率高之类）

**Query C：复盘 / 趋势**
- 输入：`"上周搜过的露营椅，过去 7 天价格和销量有什么变化？"`
- 输出：从 SQLite 读历史 run，对比关键指标，给出"价格↑ 销量↓ → 不建议追"这类结论

**非目标**（v1 不做）：
- 自动下单、自动联系供应商
- 上传商品图片做 OCR 或视觉分析
- 跨数据源（亚马逊/速卖通）；继续只用 TikHub 覆盖的 TikTok Shop + 小红书

## 3. 架构：千问 + OpenAI tool use loop（轻量手写）

**为什么手写而非框架（LangGraph / OpenAI Agents SDK）**：
- 工具只有 7-8 个，无 multi-agent handoff 需求，框架是负担
- 千问的 OpenAI 兼容端点已支持 function calling（`tools=[{...}]`），用 `openai` SDK 直接走
- 与项目"少抽象、少依赖"风格一致
- 未来真复杂了再换，当前手写 200 行能 cover

**主循环骨架**（伪代码，落地在 `agent.py`）：

```python
def run_agent(user_query: str, max_iters: int = 12, max_cost_calls: int = 30):
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_query}]
    tool_calls_count = 0
    for it in range(max_iters):
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=messages,
            tools=TOOL_SPECS,
            tool_choice="auto",
        )
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content  # agent 收尾
        for tc in msg.tool_calls:
            tool_calls_count += 1
            if tool_calls_count > max_cost_calls:
                raise BudgetExceeded(...)
            result = TOOL_IMPLS[tc.function.name](**json.loads(tc.function.arguments))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
    raise MaxItersReached(...)
```

**模型选择**：
- 默认 `qwen-plus`（function calling 支持好、性价比高）
- 复杂 Query A 类（多轮派生关键词 + 多平台对比）可换 `qwen-max`（.env 改 LLM_MODEL）

**备选方案**（如果手写循环踩坑太多）：
- OpenAI Agents SDK（`pip install openai-agents`）：原生支持 handoff / tracing / guardrails，但 0.x 版 API 还在变；千问后端走兼容端口可用
- 不推荐：Claude Agent SDK（绑 Anthropic API，与千问后端不通）

## 4. 工具集（基于现有代码包薄薄一层，<300 行新增）

每个 tool 直接复用 `score.py / db.py / _tikhub_client.py / analyze.py` 已有的函数，agent.py 里只做 JSON schema + 参数校验 + 调用。

| Tool 名 | 入参 | 出参 | 底层调用 | 成本 |
|---|---|---|---|---|
| `search_tiktok_products` | keyword, region, page? | 商品列表 (打分前) | `fetch_search_products_list` | 搜索价 |
| `search_xhs_products` | keyword, page? | 商品卡列表 | `app_v2/search_products` | 搜索价 |
| `search_xhs_notes` | keyword, page? | 笔记列表 (含互动热度) | `web_v3/fetch_search_notes` | 搜索价 |
| `score_and_rank` | source, items | 排序后的 list | `score.score_*` | 0 |
| `fetch_reviews` | source, target_id, max_pages | 评论列表 | `_fetch_tiktok_reviews` / xhs 同名 | 评论价 |
| `extract_pain_points` | reviews | {sentiment, pain_points, highlights} | `analyze.analyze_reviews` | LLM 价 |
| `save_run_and_results` | source, keyword, scored, reviews?, analysis? | run_id | `db.start_run` + `save_*` | 0 |
| `query_trend` | source, source_id | 历次快照 list | `db.trend` | 0 |

**为什么这样切分**：每个 tool 对应现有 pipeline 的一个原子动作，agent 可以自由组合：跳过评论拉取、只对比趋势、先笔记测温度再商品测销量都行。

**预算守门**：每个会消耗 TikHub / LLM 额度的 tool 在 `agent.py` 顶部统一计数，超阈值直接 raise——agent 看到错误会自己收尾。

## 5. 数据流

```text
user query
  ↓
[planner: agent 第一次 LLM 调用]
  → 决定先派生关键词？还是直接搜？还是查 trend？
  ↓
[tool 调用循环：search → score → 看 Top → 决定要不要拉评论 → 拉评论 → 分析]
  ↓
[反思: 数据够了吗？要不要换地区/扩关键词？]
  ↓ (没够)  →  循环回 tool 调用
  ↓ (够了)
[最终输出: agent 写选品报告 Markdown]
  ↓
所有 tool 结果 + agent 决策日志落 SQLite (新表 agent_runs)
```

每个 tool 的入参/出参全程 JSON 化打印到 stdout，方便 PM 实时看 agent 在想什么、做什么——选品决策必须可审计。

## 6. 新增数据表

```sql
CREATE TABLE agent_runs (
    agent_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_query   TEXT NOT NULL,
    started_at   INTEGER,
    finished_at  INTEGER,
    status       TEXT,                  -- 'success' / 'budget_exceeded' / 'max_iters' / 'error'
    final_report TEXT,                  -- agent 最后输出的 markdown
    cost_summary TEXT                   -- JSON: {tikhub_calls, llm_tokens, ...}
);

CREATE TABLE agent_steps (
    agent_run_id INTEGER NOT NULL,
    step_idx     INTEGER NOT NULL,
    role         TEXT,                  -- 'assistant' / 'tool'
    tool_name    TEXT,
    tool_args    TEXT,                  -- JSON
    tool_result  TEXT,                  -- JSON, 可能很大
    ts           INTEGER,
    PRIMARY KEY (agent_run_id, step_idx)
);
```

事后审计：`SELECT * FROM agent_steps WHERE agent_run_id=N` 就能 replay 整个决策过程。

## 7. 风险与硬边界

| 风险 | 触发场景 | 守门方式 |
|---|---|---|
| Agent 失控烧 TikHub 额度 | 反复换关键词 / 翻页停不下来 | `max_cost_calls=30`，超阈值 raise；按 tool 类型再设细分上限 (评论调用最多 N 次/run) |
| Agent 反复调同一 tool | LLM 卡住 | `max_iters=12`，超阈值 raise；并对 (tool_name, args) 做去重缓存 |
| LLM 决策跑偏 | 选关键词南辕北辙 | system prompt 里写死"只在 TikTok Shop / 小红书做选品"；输出格式约束 |
| 评论里含隐私 | 用户名 / 地理位置出现在最终报告 | 报告生成时强制脱敏：用户名只留首字 + *，地理位置只到省 |
| .env key 泄漏 | agent 把 tool 入参写到日志，正巧带了 key | tool 实现内部读 env，**LLM 永远看不到 key 字段**；agent_steps 表只存 user_*** 字段，不存 raw env |

## 8. 分阶段实施路径

### v0.1 — MVP（目标：4-6 小时，单平台单 query 跑通）

- 只支持 Query B（"`关键词`，挑 N 个最值得卖的 SKU"）和单平台 TikTok Shop
- Tool 集只实现 4 个：`search_tiktok_products` / `score_and_rank` / `fetch_reviews` / `extract_pain_points`
- 不需要数据库审计层（先 print 到 stdout）
- 不需要关键词派生
- **验收**：`python3 agent.py "labubu 在美区，挑 3 个最值得卖的 SKU"` 能出一份 Markdown 报告，含 3 个 product_id、score、痛点摘要、推荐理由

### v0.5 — 加平台 + 加审计（再 4-6 小时）

- 补 4 个 tool：`search_xhs_*` × 2 / `save_run_and_results` / `query_trend`
- 加 `agent_runs` + `agent_steps` 两张表，每次 run 全程落库
- 支持 Query A（"`粗品类描述`，给我 N 个值得做的品类"）：agent 自己派生 3-5 个关键词然后并行评估
- **验收**：能跑通"夏季宠物用品在小红书选品"，输出 5 个 SKU 候选 + 落库可 replay

### v1.0 — 加 trend / 加守门强化（再 4-6 小时）

- 支持 Query C（趋势复盘）
- 守门：预算细分上限、tool 调用去重缓存、报告脱敏
- 可选：human-in-the-loop hook（关键决策点用 `input()` 让用户拍板，便于演示）
- **验收**：在演示场景下，3 类 Query 都能稳定跑出、所有 run 可审计、不会失控烧额度

### 不在 v1 里做的（避免范围蔓延）

- 多 Agent 协作（市场分析师 / 选品官 / 风审，过度设计）
- Web UI（命令行先跑稳定，再考虑接到飞书机器人或 Streamlit）
- 自动调价 / 自动联系供应商 / 自动上架
- 视觉理解（商品图 OCR / 图像质量打分）
- 持久化的跨会话 memory（先做单 session）

## 9. 落地步骤（v0.1 拆解，可直接照做）

1. 新建 `采集工作台/scripts/tools.py`：把 4 个 MVP tool 各包成函数，每个函数顶部一个 JSON schema dict（OpenAI tool spec 格式）
2. 新建 `采集工作台/scripts/agent.py`：tool use loop 主体 + SYSTEM_PROMPT
3. SYSTEM_PROMPT 必含：
   - 角色定义（选品分析师，覆盖 TikTok Shop / 小红书）
   - 工作流程（搜→打分→看 Top→决定要不要拉评论→分析→出报告）
   - 输出格式约束（最终 markdown 报告结构）
   - 预算意识（"评论拉取每次都花钱，确认值得才调"）
4. 跑一遍 Query B 验收用例，看 agent 决策合理性
5. 不合理就改 system prompt（不是改 tool；tool 应该保持原子）

## 10. 开放问题（写代码前再确认一次）

- 报告输出语言：默认中文，但 TikTok Shop 美区评论是英文——agent 是否需要先翻译再做痛点抽取？（建议：让 LLM 在 `extract_pain_points` 阶段直接输出中文标签，跨语言抽取千问做得动）
- 一次 run 默认覆盖几个关键词？（建议 v0.5 默认 3 个，超 5 个让 agent 自己 stop）
- 是否需要"对比模式"工具（同时跑 TikTok + 小红书 → 看哪个平台口碑/价格更好）？（v1 再加）
- 千问 function calling 在 `tool_choice="auto"` 下是否稳定？（先实测；如不稳，降级到 ReAct 式 prompt + 自己解析 JSON 函数调用）
