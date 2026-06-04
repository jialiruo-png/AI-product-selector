# CLAUDE.md · 项目宪法

> 给 Claude Code / Codex / 团队成员的项目协作约定。**先读完再动手**。

---

## 0. 项目概览

**项目名**：AI-product-selector（现已演化为「电商经营 Agent 框架」）
**最初定位**：基于 TikHub 的电商选品工具
**当前形态**：多专家 Agent 框架，覆盖两大业务方向
- **冷启动选品**（甘华梁负责）：新商家选品 → 商机洞察子图
- **在运营诊断**（贾丽婼负责）：S4/S5 中小商家经营诊断 → 经营诊断子图

**技术框架**：LangGraph + Skill MD + 双层 Wiki + 证据引用 + Review 状态机

---

## 1. 团队分工与边界

| 成员 | 负责子图 | 入口 |
|---|---|---|
| 甘华梁（Hualiang） | 冷启动选品子图 | `python3 -m agent.run "口红" --category 美妆 --mock` |
| 贾丽婼（Liruo） | 经营诊断子图 | `python3 -m agent.run "我店铺最近卖不动" --shop-id <id> --diagnosis` |

### 1.1 共用资产（不许独自改）

任何人改动以下文件**必须先和对方确认**：
- `agent/state.py`（状态结构）
- `agent/evidence.py`（证据引用协议）
- `agent/review.py`（人审状态机）
- `agent/wiki/{industry,seller}.py`（Wiki 加载器，不是 MD 文件）
- `agent/tools/base.py`（工具协议）
- `agent/skills/loader.py`（Skill MD 加载器）
- `agent/graph.py`（图后端切换）
- `agent/hub.py`（路由入口）
- `agent/run.py`（CLI 入口）

### 1.2 独立资产（各自维护）

- 甘华梁：`agent/nodes/{planner,analyzers,aggregate}.py` + `agent/skills/{guanjianci,xuanpin,jingpin,baokuan,koubei_zhenduan}.md`
- 贾丽婼：`agent/nodes/diagnosis/*` + `agent/skills/{jingying_zhenduan,guiyin,xingdong_jianyi}.md` + `agent/skills/category_overlays/*`
- 共用 Wiki MD：双方都可以新增 MD 文件到 `agent/wiki/industry/` 或 `agent/wiki/seller/`，加载器不动

### 1.3 绝对禁区

**`采集工作台/scripts/` 是甘华梁的基础设施 + 历史脚本，零修改**。所有调用都走 import，不准改原文件。

---

## 2. 技术栈与依赖

- **Python 3.12+**
- **LangGraph**（图编排，已加入 requirements）—— 默认走 LangGraph，MiniGraph 作为无依赖兜底
- **OpenAI SDK**（兼容 DashScope/千问）—— 走 `agent/llm.py` 统一封装
- **SQLite**（趋势复盘）—— 通过 `db.py`
- **TikHub API**（外部数据，仅冷启动子图用）—— 通过 `_tikhub_client.py`

**环境切换**：
- `AGENT_MOCK=1`：所有节点走 mock，不调真 LLM / 不调真 TikHub，离线可跑
- `AGENT_USE_LANGGRAPH=1`：用 LangGraph 后端（默认）
- 缺 `DASHSCOPE_API_KEY`：自动 fallback 到 mock 模式，不许崩

---

## 3. 命名规范

### 3.1 文件命名
- Skill MD：拼音小写，下划线分隔（`jingying_zhenduan.md`）
- Wiki MD：英文小写，下划线分隔（`activity_db.md`）
- 节点文件：`agent/nodes/<子图名>/<节点名>.py`（如 `agent/nodes/diagnosis/checker.py`）
- PRD/文档：数字前缀+中文标题（`06-在运营商家诊断Agent-PRD.md`）

### 3.2 函数命名
- 节点类：`<职责>Node`（如 `CheckerNode`）
- 工具函数：动词开头（`fetch_shop_metrics`、`rank_products`）
- LLM 调用：`chat_json` / `chat_text`（统一走 `agent/llm.py`）

### 3.3 Skill MD 结构
每个 Skill MD 必须包含以下章节：
```markdown
# <专家名>
## 角色定义
## 核心目标
## 工作流程（SOP）
## 工具依赖（列出可调用工具名）
## 输入输出 schema
## 类目 overlay（如适用）
```

---

## 4. 开发规范

### 4.1 不破坏现有功能
**每个 commit 前必跑**：
```bash
python3 -m compileall -q agent
python3 -m agent.run "口红" --category 美妆 --mock
```
任何 commit 都不能让甘华梁的冷启动选品报告跑挂。

### 4.2 mock 永不崩
所有新增节点必须支持 `AGENT_MOCK=1`，缺 key 时返回 mock 数据，不许抛异常。

### 4.3 不写假数据当真数据
mock 数据必须**显式标记**（如 `_mock: True` 字段或日志打 `[MOCK]`），不能让用户误以为是真数据。

### 4.4 新增依赖必入 requirements.txt
任何 `pip install` 都要进 requirements.txt，且 MiniGraph 兜底逻辑不能依赖新增依赖。

### 4.5 证据引用强制
每条 AI 结论必须挂至少一条 `KnowledgeEvidenceRef`（layer + sourceId + quote）。空结论不许出。

### 4.6 不擅自删除别人的文件
如果觉得别人的代码该重构，先开 issue 讨论，不直接覆盖。

---

## 5. 提交与分支

### 5.1 分支策略
- `main`：稳定分支，跑 mock 永远能出报告
- `运营`：贾丽婼经营诊断子图开发分支
- 甘华梁的开发分支：他自己定（已合并 `godkiller/main`）

### 5.2 Commit 信息格式
```
<类型>(<范围>): <简述>

例：
feat(diagnosis): add checker and attributor nodes
docs(prd): update v1 scope to nvzhuang only
fix(wiki): handle missing category_baseline.md gracefully
```

类型：`feat / fix / docs / refactor / test / chore`
范围：`agent / diagnosis / wiki / tools / skills / prd / docs`

### 5.3 提交前必做
1. 跑过 mock 测试
2. 没改禁区文件
3. 新增依赖写进 requirements
4. **同步更新 `update.md`**（按批次写功能说明）

---

## 6. 文档体系（按编号读）

| 文档 | 用途 | 维护人 |
|---|---|---|
| `README.md` | 项目入门 | 甘华梁 |
| `plan.md` | Agent 化初始方案 | 甘华梁 |
| `CLAUDE.md`（本文件） | 团队协作宪法 | 共同维护 |
| `03-抖店商家经营 Agent-V2 升级版 PRD.md` | 上层战略 PRD（多专家矩阵） | 贾丽婼 |
| `04-电商经营 Agent-融合方案.md` | 框架融合说明 | 共同 |
| `05-Codex 任务清单.md` | Codex 收尾任务 | 甘华梁 |
| `06-在运营商家诊断 Agent-PRD.md` | 经营诊断子图 PRD | 贾丽婼 |
| `07-女装诊断 Skill 写作规范.md`（待写） | overlay 写作模板 | 贾丽婼 |
| `08-验收用例-女装真实场景.md`（待写） | V1 验收 ground truth | 贾丽婼 |
| `小二职责与痛点.md` | 业务背景资料 | 贾丽婼 |
| `update.md` | 每次开发批次更新记录 | 全员追加 |

**读文档顺序**：
- 新加入：`README.md` → `CLAUDE.md` → `03 PRD` → 自己负责的子图 PRD
- 想理解框架：`plan.md` → `04 融合方案` → `update.md`
- 想动手：`CLAUDE.md` → `06 PRD`（如做诊断）→ `07 写作规范`

---

## 7. 与 Codex / Claude Code 协作约定

### 7.1 给 AI 的输入
- 优先指明文件路径（绝对路径）
- 说明意图 + 约束（"不许改 X、必须复用 Y"）
- 引用现有代码做参照

### 7.2 AI 输出后必查
- 是否动了禁区文件？
- 是否破坏 mock 链路？
- 是否在 `update.md` 追加批次说明？
- 是否符合 Skill MD 章节结构？

### 7.3 失败回退
如果 AI 一次性改动太大，回滚到 git 上一个稳定 commit，分小步重做。

---

## 8. 常见坑（踩过的）

| 坑 | 解法 |
|---|---|
| TikHub `page_start` 从 1 起而文档写 0 | 工具层硬编码 `page_start=1`，注释说明 |
| TikHub 400 重试不扣费 | 工具层做 retry，但要打 `[RETRY]` 日志 |
| `score.py` 读嵌套字段 vs mock 扁平字段 | mock 也写成嵌套结构，与真实数据一致 |
| LangGraph 并行节点 list 字段冲突 | 用 `Annotated[list, operator.add]` reducer |
| DashScope JSON 模式偶尔返回非 JSON | `response_format={"type":"json_object"}` + 解析失败兜底 |

---

## 9. V1 验收口径

任何一次"V1 完成"声明都必须满足：
1. `python3 -m compileall -q agent` 通过
2. `python3 -m agent.run "口红" --category 美妆 --mock` 跑通（甘华梁子图不挂）
3. `python3 -m agent.run "我店铺最近 GMV 跌了" --shop-id mock_001 --diagnosis --mock` 跑通（贾丽婼子图出报告）
4. 报告包含证据引用 + 至少 3 条可执行建议
5. `update.md` 有对应批次说明

---

## 10. 联系与决策

- **小决策**（命名、文件位置）：动手前在 commit message 写清楚理由
- **中决策**（新增专家、改 state schema）：先开 issue / PR，描述影响面
- **大决策**（换框架、改路由协议）：所有人对齐后再动

**最高原则**：**不破坏对方的工作，不重复造轮子，所有变更可审计**。

---

## 11. 多 Claude Code 窗口并行开发协议

> 当贾丽婼开两个 Claude Code 窗口同时推进诊断子图开发时遵守。

### 11.1 主窗口 vs 副窗口分工

| 窗口 | 负责范围 | 触碰的文件 |
|---|---|---|
| **主窗口** | 核心代码主链路（Day 2/3 主体） | `agent/nodes/diagnosis/*`、`agent/state.py`、`agent/graph.py`、`agent/hub.py` |
| **副窗口** | 独立资产（数据 + UI + 文档） | `agent/mocks/shops/*.json`、`demo/streamlit_app.py`、`09-演示话术.md` |

### 11.2 严禁同时触碰的文件（冲突高危）

副窗口绝对不要碰：
- `agent/state.py`（主窗口在 Day 2 扩展字段）
- `agent/graph.py`（主窗口在 Day 2 编排子图）
- `agent/hub.py`（主窗口在 Day 2 加路由）
- `agent/nodes/diagnosis/*.py`（主窗口在 Day 2-3 开发）
- `agent/llm.py`（主窗口在 Day 3 接通 LLM）

主窗口绝对不要碰：
- `agent/mocks/shops/*.json`（副窗口在做）
- `demo/streamlit_app.py`（副窗口在做）
- `09-演示话术.md`（副窗口在做）

### 11.3 副窗口任务清单（按顺序做）

#### 任务 A：5 份 mock 商家 JSON（最高优先级）

**目的**：让 Day 3 跑 5 个 case 时有数据可吃。
**路径**：`agent/mocks/shops/case_{1..5}.json`
**字段约定**（按抖店罗盘真实字段结构还原）：

```json
{
  "_mock": true,
  "_case_id": "case_1",
  "_case_name": "咖喱生活",
  "shop_profile": {
    "shop_id": "mock_shop_001",
    "shop_name": "咖喱生活优品铺子",
    "category": "女装>连衣裙",
    "entry_days": 142,
    "shop_level": "L3",
    "exp_score": 4.3,
    "monthly_gmv": 870000,
    "dau_gmv_share": {
      "live": 0.65,
      "video": 0.15,
      "search": 0.12,
      "mall": 0.08
    }
  },
  "metrics_7d": {
    "gmv": 120000,
    "uv": 82000,
    "cvr": 0.013,
    "aov": 113,
    "live_room_stay_sec": 22,
    "fanzhuan_rate": 0.014,
    "uv_value": 4.8,
    "main_image_ctr": 0.051,
    "qianchuan_roi": 0.8,
    "refund_rate": 0.082
  },
  "metrics_prev_7d": { /* 上 7 天对照 */ },
  "metrics_30d": { /* 近 30 天 */ },
  "traffic_breakdown": { /* 渠道拆分 */ },
  "sku_performance": [ /* SKU 列表 */ ],
  "fulfillment_metrics": { /* 履约 */ },
  "newbie_progress": null /* 仅新店 case 3 用 */
}
```

**5 个 case 对应**：
- case_1.json：咖喱生活（女装自播 + 成长期）
- case_2.json：素笺布艺（女装货架店）
- case_3.json：初见女装铺（女装新店冷启动）—— `newbie_progress` 必须非 null
- case_4.json：橙夏（女装达播店）—— 含 `kol_metrics` 字段
- case_5.json：夏树（女装自播 + 季节切换）—— 含 `sku_inventory` 字段

**数据来源**：`08-验收用例-女装真实场景.md` 里每个 case 的"经营数据"表，直接照搬填到 JSON。

**验收**：5 份 JSON 能被 `json.load()` 解析，且字段覆盖 06 PRD §6.3 提到的所有节点输入需求。

---

#### 任务 B：Streamlit demo 框架（中优先级）

**目的**：面试演示用，把 CLI 输出包装成可视化界面。
**路径**：`demo/streamlit_app.py`（新目录 `demo/`）
**MVP 范围**：

```python
import streamlit as st
import json
from pathlib import Path

st.set_page_config(page_title="抖店中小商家经营诊断 Agent", layout="wide")

# 左侧栏：选择 case
case_files = sorted(Path("agent/mocks/shops").glob("case_*.json"))
case = st.sidebar.selectbox("选择诊断 case", case_files, format_func=lambda p: p.stem)

# 主区：三段式展示
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("商家画像")
    data = json.loads(case.read_text())
    st.json(data["shop_profile"])

with col2:
    st.subheader("AI 诊断报告")
    if st.button("跑一次诊断"):
        # 暂用占位，等 Day 3 接 agent.run
        st.markdown("**核心问题**：[占位] 等 Day 3 接 agent.run")
        st.info("Day 3 后会接通真实 Agent 调用")
```

**Day 4 收尾时**：把占位换成真实 `from agent.run import run; result = run(case_id, mock=True)`。

> 2026-06-05 更新：主窗口 Day 2 完成 4 节点子图后，副窗口已提前把 demo 接通真实
> `agent.graph.run_diagnosis`（mock 模式），不再等 Day 4。当前 demo 直接渲染 composer
> 生成的完整 markdown 报告 + 结构化下钻面板（异常清单 / 根因链 / 行动建议 / 证据引用 / 节点 trace）。
> 副窗口仍只 import `agent.graph`，不修改 `agent/*` 任何文件。

**新增依赖**：`streamlit` 必入 `requirements.txt`。

---

#### 任务 C：09-演示话术.md（低优先级，可选）

**目的**：面试时按这个稿子讲，2-3 分钟内把诊断 Agent 价值讲清楚。
**路径**：`/Users/damowang/Desktop/AI-product-selector/09-演示话术.md`
**结构**：
1. 开场（30 秒）：90% 中小商家拿不到小二
2. 现状（30 秒）：抖店 AI 4 大短板
3. 方案（60 秒）：经营诊断子图 + 女装 6 个 overlay
4. 演示（90 秒）：跑 case 1 咖喱生活 → 展示诊断 + 归因 + 建议
5. Q&A 预演（30 秒）：3 个常被追问的问题及答案

参考资料：`06-PRD.md` §14、`08-验收用例.md` Case 1。

---

### 11.4 协调机制

1. **commit 顺序**：副窗口先 commit 它的独立文件；主窗口在做完一个原子节点（如 checker.py）就 commit，避免大批量改动堆积
2. **每次 commit 后跑** `python3 -m compileall -q agent` + `python3 -m agent.run "口红" --category 美妆 --mock`，确保没回归
3. **如果副窗口任务做完想往前抢**：先跟主窗口（或主窗口 commit log）确认 Day 2 已合入，再去做 Day 3 的子任务
4. **不许 push 到远程**：所有 commit 都本地 `运营` 分支，等 V1 完整跑通后由贾丽婼统一 push

### 11.5 副窗口可读但不可改的文档

读完这些再开干（避免和主窗口认知不一致）：
- `06-在运营商家诊断Agent-PRD.md`（产品方案主文档）
- `07-女装诊断Skill写作规范.md`（Skill 写作约束）
- `08-验收用例-女装真实场景.md`（5 个 case 的期望输出，做 mock 时直接照搬数据）
- `agent/skills/category_overlays/*.md`（女装 6 个 overlay，了解每个 case 应该命中哪个）
- `CLAUDE.md`（本文件第 11 章必读）
