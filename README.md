# AI 选品工具

基于 **TikHub** 的电商选品数据工具，覆盖 **TikTok Shop** 与 **小红书** 两个数据源。
通过关键词拉取商品与种草笔记，用搜索端自带的价格 / 销量 / 评分 / 互动热度字段做打分排序，
再对高分目标按需补评论，做情感与痛点分析。

支撑选品的三件事：

1. **商品打分排序** —— 关键词 → 商品列表，按价格、销量、评分、评论数、互动热度综合打分
2. **评价情感 / 痛点分析** —— 仅对 Top-N 目标调评论，提取真实差评与痛点
3. **竞品 / 趋势监控** —— 用搜索端的店铺、品牌、互动字段，按时间重复搜索对比销量、价格与热度走势

## 数据源

### TikTok Shop（选品打分主源）

抖音端没有「关键词 → 商品」搜索，电商端点全部要求已持有 `product_id` / `room_id`，
无法从关键词冷启动；**TikTok Shop 命名空间有完整漏斗，打分所需字段全在免费搜索端**，因此选品入口走 TikTok Shop。

- `fetch_search_products_list` —— 关键词 → 商品列表，每条自带价格 / 销量 / 评分 / 评论数 / 店铺 / 品牌
- `fetch_product_reviews_v2` —— 评分 Top-N 商品的评论文本，做情感 / 痛点
- 多地区（`US / MY / GB / ID` 等，覆盖中文与东南亚选品）

### 小红书（内容 / 口碑维度）

小红书提供**两条互补漏斗**，分别承担「选品打分」与「种草热度 / 口碑趋势」：

**商品漏斗**

- `app_v2/search_products` —— 关键词 → 商品列表，每条自带价格、原价、主图、店铺（`vendor`）
- `app_v2/get_product_review_overview` —— 评分分布、差评率、销量（便宜的概览）
- `app_v2/get_product_reviews` —— Top-N 商品的评论文本，做情感 / 痛点

**笔记漏斗**

- `web_v3/fetch_search_notes` —— 关键词 → 笔记列表，每条自带点赞 / 收藏 / 评论 / 分享互动热度
- `web_v3/fetch_note_detail` —— 笔记正文 + 话题标签（选词 / 语义来源）
- `web_v3/fetch_note_comments` —— 笔记评论，真实声音与痛点的第二来源

详细端点、字段映射与降本结构见 [docs/tikhub_接入说明.md](docs/tikhub_接入说明.md)。

## 降本思路：搜索免费筛 → Top-N 才花钱

价格、销量、评分、图片、互动热度在免费搜索端全部白拿；只在「值得的目标」上花钱补评论。

| 步骤 | 端点 | 何时调 | 成本 |
|---|---|---|---|
| 商品搜索 + 打分（TikTok） | `fetch_search_products_list` | 每次（翻页） | 搜索价 |
| 商品搜索 + 打分（小红书） | `app_v2/search_products` | 每次（翻页） | 搜索价 |
| 笔记搜索 + 热度（小红书） | `web_v3/fetch_search_notes` | 每次（翻页） | 搜索价 |
| 商品评分概览（小红书） | `app_v2/get_product_review_overview` | 仅 Top-N | 概览价 |
| 评论情感 / 痛点 | `fetch_product_reviews_v2`、`app_v2/get_product_reviews`、`web_v3/fetch_note_comments` | **仅 Top-N** | 评论价 |

## 环境要求

- Python 3.12+
- 一个 TikHub API key（控制台获取：<https://user.tikhub.io>）

## 配置

在项目根目录的 `.env` 中填入 key（该文件已 gitignore）：

```bash
# 大陆用 api.tikhub.dev，海外用 api.tikhub.io
TIKHUB_API_KEY=你的真实key
TIKHUB_BASE=https://api.tikhub.dev
```

## 安装

探测脚本仅依赖 Python 标准库，可直接运行。如需隔离环境：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用

**TikTok Shop 选品漏斗**（账户连通性 → 商品搜索打分字段 → Top 商品评论 → 商品详情）：

```bash
# 探一个关键词的完整漏斗
python3 采集工作台/scripts/tikhub_douyin_probe.py "labubu"

# 指定地区（默认 US，TikTok Shop 美区数据最全）
python3 采集工作台/scripts/tikhub_douyin_probe.py "phone case" --region US

# 把每步原始 JSON 落到 /tmp，方便细看字段
python3 采集工作台/scripts/tikhub_douyin_probe.py "labubu" --dump
```

**小红书选品漏斗**（账户连通性 → 商品搜索 / 评分 / 评论 → 笔记搜索 / 正文 / 评论）：

```bash
# 探一个关键词的商品 + 笔记双漏斗
python3 采集工作台/scripts/tikhub_xiaohongshu_probe.py "口红"

# 把每步原始 JSON 落到 /tmp，方便细看字段
python3 采集工作台/scripts/tikhub_xiaohongshu_probe.py "口红" --dump
```

## 目录说明

```text
采集工作台/
  scripts/
    tikhub_douyin_probe.py        # TikTok Shop 选品漏斗（搜索打分 / 评论 / 详情）
    tikhub_xiaohongshu_probe.py   # 小红书商品 + 笔记双漏斗（商品打分 / 评分 / 评论 / 笔记热度 / 正文 / 评论）
docs/
  tikhub_接入说明.md               # TikHub API 接入说明（端点、字段、降本结构）
.env                              # TikHub key（gitignore）
requirements.txt                  # 依赖
```
