# AI 选品工具

基于 **TikHub** 的电商选品工具，覆盖 **TikTok Shop** 与 **小红书**。
关键词进，Top-N 选品候选 + 真实痛点/好评点出，全程落 SQLite 便于按时间复盘趋势。

## 它做的三件事

1. **打分排序** —— 关键词 → 商品/笔记列表，搜索端自带的 `价格/销量/评分/评论数/互动热度` 字段做 min-max 归一化加权打分
2. **情感/痛点分析** —— 仅对 Top-N 调评论，LLM 抽情感分布 + 痛点短语 + 好评短语（默认千问，可切任意 OpenAI 兼容厂商）
3. **趋势监控** —— 同一商品/笔记按时间复跑，SQLite 按 `run_id` 存快照，`selector.py trend` 直接出对比

降本结构：搜索端**免费**筛 → 仅 Top-N 才花评论价 → LLM 只在 Top-N 评论上跑一次。

## 模块分层

```text
采集工作台/scripts/
  _tikhub_client.py        # HTTP 客户端：.env / 401 重试 / dig() 嵌套取值
  score.py                 # 打分：TikTok 商品、小红书商品、小红书笔记三套权重
  db.py                    # SQLite：runs / products / notes / reviews / pain_points 五张表
  analyze.py               # LLM：千问（OpenAI 兼容端点）→ JSON {sentiment, pain_points, highlights}
  selector.py              # 主 pipeline：search → score → db → top-N 评论 → analyze → db
  tikhub_tiktok_shop_probe.py   # 接口探测（摸字段 / 验证连通，不入库）
  tikhub_xiaohongshu_probe.py   # 同上，小红书商品 + 笔记双漏斗
docs/
  tikhub_接入说明.md       # 端点 / 字段 / 降本结构（实测）
```

## 环境

- Python 3.12+
- TikHub API key（<https://user.tikhub.io>）
- 千问 / DashScope API key（仅 `--analyze` 时需要，<https://bailian.console.aliyun.com>）
  - 或任意 OpenAI 兼容厂商：在 `.env` 改 `LLM_BASE_URL` + `LLM_MODEL`

## 安装

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt    # 只装 openai；其余走标准库
cp .env.example .env               # 填入 TIKHUB_API_KEY（必填）和 DASHSCOPE_API_KEY（可选）
```

## 用法

### 主 pipeline：`selector.py`

```bash
# TikTok Shop 选品（搜索 + 打分 + 落 SQLite）
python3 采集工作台/scripts/selector.py tiktok "labubu" --topn 5

# 加 --analyze：拉 Top-N 评论 + LLM 痛点/好评分析
python3 采集工作台/scripts/selector.py tiktok "labubu" --topn 5 --analyze

# 小红书商品 + 笔记双漏斗（同样支持 --analyze）
python3 采集工作台/scripts/selector.py xhs "口红" --topn 5 --analyze

# 看某商品历次快照（按时间趋势对比价格/销量/评分/score）
python3 采集工作台/scripts/selector.py trend tiktok 1729...
```

### 探测脚本（不入库，仅看字段）

```bash
python3 采集工作台/scripts/tikhub_tiktok_shop_probe.py "labubu" --region US --dump
python3 采集工作台/scripts/tikhub_xiaohongshu_probe.py "口红" --dump
```

## 打分公式（写死在 `score.py` 顶部，可参数覆盖）

| 来源 | 字段权重 |
|---|---|
| **TikTok 商品** | 销量 0.40 + 评分 0.25 + 评论数 0.20 + 价格分位 0.15 |
| **小红书商品** | 价格分位 0.30 + 折扣 0.30 + 评分 0.40 |
| **小红书笔记** | 点赞 0.40 + 收藏 0.30 + 评论 0.20 + 分享 0.10 |

价格/销量/评论数/互动热度先在本批次内 min-max 归一（log1p 抑长尾），价格取反让"便宜=高分"。
评分把 4.0-5.0 线性映射到 0-1。

## 数据模型（SQLite）

```text
runs(run_id, source, keyword, region, fetched_at, note)
products(run_id, source, source_id, title, price, sold, rating, review_count, shop, brand, score, extra_json, fetched_at)
notes(run_id, note_id, xsec_token, title, user_name, likes, collects, comments, shares, score, extra_json, fetched_at)
reviews(source, target_id, review_id, rating, text, ts, fetched_at, extra_json)
pain_points(run_id, source, target_id, kind, label, freq, example, fetched_at)   # kind ∈ {'pain','highlight'}
```

同一 `source_id` 在多次 `run_id` 下都会保留快照——直接 `SELECT ... ORDER BY fetched_at` 就是趋势。

## 接口/字段细节

详见 [docs/tikhub_接入说明.md](docs/tikhub_接入说明.md)，包含每个端点的入参、返回路径、踩坑（如 TikTok `page_start` 从 1 起、TikHub 400 重试不扣费等）。
