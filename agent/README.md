# 电商经营 Agent 框架（LangGraph）

融合 [03 V2 PRD](../03-抖店商家经营Agent-V2-升级版PRD.md) 的架构 + [选型 doc](../docs/开源项目调研与选型.md) 的 LangGraph 骨架 + 现有 [采集工作台](../采集工作台/scripts/) 的 TikHub 能力。
**原 `采集工作台/scripts/` 一字未改**，全部以 import / BaseTool 方式复用。

## 一分钟跑起来

```bash
# 离线 mock 模式（无需任何 API key，端到端出洞察报告）
python3 -m agent.run "口红" --category 美妆 --mock

# 真实 TikHub 模式（需 .env 里 TIKHUB_API_KEY；--analyze 那步还需 DASHSCOPE_API_KEY）
python3 -m agent.run "口红" --category 美妆 --region US --topn 5

# 强制走 langgraph 后端（未装则自动回退 MiniGraph，不崩）
AGENT_USE_LANGGRAPH=1 python3 -m agent.run "口红" --mock
```

## 架构分层（对应融合方案三段式）

```
L0 Hub 路由      agent/hub.py            自然语言 → 意图 → Skill 链 → 调洞察子图
L1 专家 Skill    agent/skills/*.md       配置即技能：选品/关键词/竞品/爆款/口碑诊断（PRD §5 模板）
   编排骨架      agent/graph.py          LangGraph 子图（langgraph 或内置 MiniGraph 双后端）
   9 个节点      agent/nodes/            KeywordPlanner→4并行Analyzer→Collector→Curator→Briefing→Editor
L2 工具协议      agent/tools/            BaseTool（JSON Schema + MCP/OpenAI/Anthropic 转换 + 自动注册）
L3 状态/知识     agent/state.py          InsightState（raw+curated_ 透传，keywords 全局精准词）
                 agent/wiki/             双层 Wiki（行业只读 + 商家 overlay，6 语义关系占位）
                 agent/evidence.py       KnowledgeEvidenceRef（PRD §9.1 强制证据引用）
                 agent/review.py         Review 状态机（Candidate→Approved→Executed）
```

## 商机洞察子图（P0，已跑通）

`keyword_planner`（Step1 精准词）
→ 并行 `social_analyzer`(Step2 人群) / `price_analyzer`(Step3 价格带) / `hot_item_analyzer`(Step4 爆款主图) / `competitor_analyzer`(Step5 竞品+口碑)
→ `collector` → `curator`(相关性过滤) → `briefing`(分维摘要) → `editor`(出报告)

每条结论挂 `evidence_refs`，全程 `_trace` 记录可观测 timeline。

## 当前状态（务实标注）

- ✅ **能跑**：mock 模式端到端出报告；真实模式 TikHub 取数 + score.py 打分。
- 🟡 **mock 占位**：所有 LLM 节点（KeywordPlanner / Briefing / Editor）现为模板 mock，代码里 `# TODO: wire real LLM` 标清。
- 🔵 **占位层**：Wiki 6 语义关系治理、Review 写操作、◐/○ 档专家（客服/罗盘/OKR/直播）—— 见 `agent/skills/README.md`。

接下来要做的事见 [../05-Codex任务清单.md](../05-Codex任务清单.md)。
