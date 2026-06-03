# TikHub API 接入说明（选品·实测版）

> 测试时间 2026-06-03，全部端点用真实 key 实测。
> 本工具的选品数据源为 **TikTok Shop** + **小红书**（抖音端无关键词商品搜索，见下）。

## 一、基础配置

| 项 | 值 |
|---|---|
| Base URL（大陆） | `https://api.tikhub.dev` |
| Base URL（海外） | `https://api.tikhub.io` |
| 认证 | Header `Authorization: Bearer {API_KEY}` |
| 必带头 | `User-Agent`（否则 Cloudflare 返回 403） |
| 限流 | QPS 10/秒，超时建议 30–60s，失败最多重试 3 次 |
| key 位置 | 项目根 `.env` 的 `TIKHUB_API_KEY`（已 gitignore） |

返回统一包装：`{code, data, message, request_id, ...}`，`code==200` 为成功。

## 二、抖音/TikTok 电商（✅ 实测，2026-06-03）—— 选品数据源

### 关键结论：抖音无商品搜索，选品走 TikTok Shop 命名空间
- **抖音(`/douyin/`)没有「关键词→商品」搜索，也没有独立商品详情。**
  其电商端点全部需要你**已持有 ID**：
  - `web/fetch_product_review_list`（要 `product_id`+`shop_id`）
  - `web/fetch_product_review_score`（要 `product_id`+`shop_id`）
  - `web/fetch_product_sku_list`（要 `product_id`+`author_id`）
  - `web/fetch_live_room_product_result`（要 `room_id`+`author_id`）
  → 无法从关键词冷启动，只能从直播间/分享链接/已知商品反查，不适合做选品入口。
- **TikTok Shop(`/tiktok/shop/web/`)有完整漏斗，且打分字段全在免费搜索端。**

### 漏斗与字段（实测路径）

**① 商品搜索（免费拿全量打分字段）**
```
GET /api/v1/tiktok/shop/web/fetch_search_products_list
    search_word（必填） offset=0 page_token="" region=US
```
返回 `data.data.data.products[]`，**每条自带打分所需全部字段**：
- `product_id`、`title`、`image.url_list[]`（图片，免费）
- `product_price_info.sale_price_decimal` → **价格**
- `rate_info.score`(4.7) + `rate_info.review_count`(22) → **评分 + 评论数**
- `sold_info.sold_count`(101) → **销量**
- `seller_info.{seller_id,shop_name}`、`brand_info.brand_name` → **店铺/品牌（竞品维度）**
- 翻页：页级 `has_more` + `load_more_params` + `page_token`

**② 商品评论（情感/痛点原料，仅 Top-N 调用）**
```
GET /api/v1/tiktok/shop/web/fetch_product_reviews_v2
    product_id（必填） page_start=1 region=US
    sort_rule / filter_type / filter_value（可选）
```
⚠️ **`page_start` 从 1 起，传 0 返回空 `data:{}`**。返回 `data.data.data.product_reviews[]`：
- `review_rating`(1-5) → **差评率/评分分布**
- `review_text` → **情感/痛点文本**（实测约 1/3 评论带文字，其余仅星级）
- `review_time`、`is_verified_purchase`、`review_images[]`、`review_country`
- 页级 `total_reviews`、`has_more`

**③ 商品详情（价值低，可跳过）**
- `web/fetch_product_detail`、`_v3`：v1 受 region 限制常回 `error_code`；
  v3 只回页面渲染 config（`page_config.components_map`），**无干净长描述字段**。
- 结论：**选品打分完全用免费搜索端即可，无需付费详情。**

### 降本结构（搜索免费筛 → Top-N 才花钱）
| 步骤 | 端点 | 何时调 | 成本 |
|---|---|---|---|
| 搜索筛选 + 打分 | `fetch_search_products_list` | 每次（翻页） | 搜索价 |
| 评论情感/痛点 | `fetch_product_reviews_v2` | **仅评分 Top-N** | 评论价 |
| 商品详情 | ~~fetch_product_detail_v3~~ | **不调**（无干净字段） | 0 |

> 三件事数据可得性：①打分排序=免费搜索端全字段可做；②情感/痛点=Top-N 评论可做；
> ③竞品/趋势=搜索端 seller_info/brand_info + 按时间重复搜索对比销量/价格可做。

### 注意：上游间歇 400（不扣费）
`fetch_search_products_list` 等会偶发 `400 {"message":"...Please retry...You won't be charged"}`，
属 TikHub 上游临时故障、**不扣费**，重试 2~3 次即可（probe 脚本已内置 400 重试）。
`fetch_search_products_list_v2` / `app/v3/fetch_product_search` 实测更易 400，生产用 **V1**。

## 三、小红书（✅ 实测，2026-06-03）—— 选品的内容/口碑维度

小红书有**两条互补漏斗**，命名空间分别在 `app_v2`（商品）和 `web_v3`（笔记），
分别承担「选品打分」和「种草热度 / 口碑趋势」。

### 漏斗 ① 商品（选品打分核心，`/xiaohongshu/app_v2/`）

**① 商品搜索（免费拿打分字段）**
```
GET /api/v1/xiaohongshu/app_v2/search_products
    keyword（必填） page=1 search_id="" sort/scope/min_price/max_price（可选）
```
返回 `data.data.module.data[]` 卡片，取 `card_name` 含 `goods` 的卡，`content` 自带：
- `id`（= **sku_id**）、`title`
- `price_info.{price, origin_price, foreign_price}` → **价格**
- `image[].url` → **主图**（免费）
- `vendor.{vendor_name, seller_id, vendor_link}` → **店铺（竞品维度）**
- `tag_strategy_map.*` → 促销 / 库存 / 上新标
- 翻页：页级 `next_page` + `search_id`

**② 评分概览（便宜的差评率原料）**
```
GET /api/v1/xiaohongshu/app_v2/get_product_review_overview
    sku_id（必填） tab=2
```
返回 `data.{avgScore, total, scoreToCnt{1..5}, purchaseHistoryCount}` → **评分分布 / 差评率 / 销量**。

**③ 商品评论（情感/痛点文本，仅 Top-N 调）**
```
GET /api/v1/xiaohongshu/app_v2/get_product_reviews
    sku_id（必填） page=0 sort_strategy_type=0 share_pics_only=0
```
返回 `data.reviews[]`。⚠️ 与 TikTok 一致：**跨境 / 冷门商品评论常为空或仅星级**，文本评论占比有限。
`app_v2/get_product_detail`（需 `sku_id`）长描述价值有限，按需调。

### 漏斗 ② 笔记（种草 / 口碑 / 趋势，`/xiaohongshu/web_v3/`）

**① 笔记搜索（免费拿互动热度）**
```
GET /api/v1/xiaohongshu/web_v3/fetch_search_notes
    keyword（必填） page=1 sort/note_type（可选）
```
返回 `data.data.items[]`，取 `modelType=="note"`，`noteCard` 自带：
- `displayTitle`、`cover.urlDefault`、`type`(normal / video)
- `user.{nickname, userId}`
- `interactInfo.{likedCount, collectedCount, commentCount, sharedCount}` → **互动热度**
- note 级 `id` + `xsecToken`（**详情 / 评论必须带 `xsec_token`**）

**② 笔记详情（正文 + 话题标签）**
```
GET /api/v1/xiaohongshu/web_v3/fetch_note_detail
    note_id（必填） xsec_token（必填）
```
返回 `data.data.items[0].noteCard.{title, desc, tagList[], imageList, time}` → 正文与话题词（选品语义/选词）。

**③ 笔记评论（真实声音 / 痛点的另一来源）**
```
GET /api/v1/xiaohongshu/web_v3/fetch_note_comments
    note_id（必填） xsec_token（必填）
```
返回 `data.data.comments[]`，每条 `content / likeCount / ipLocation / userInfo / subComments`，页级 `hasMore`。

### 降本结构（与 TikTok 同：搜索免费筛 → Top-N 才花钱）
| 步骤 | 端点 | 何时调 | 成本 |
|---|---|---|---|
| 商品搜索 + 打分 | `app_v2/search_products` | 每次（翻页） | 搜索价 |
| 笔记搜索 + 热度 | `web_v3/fetch_search_notes` | 每次（翻页） | 搜索价 |
| 商品评分概览 | `app_v2/get_product_review_overview` | 仅 Top-N | 概览价 |
| 商品 / 笔记评论 | `app_v2/get_product_reviews`、`web_v3/fetch_note_comments` | **仅 Top-N** | 评论价 |

> 三件事数据可得性：①打分排序=`search_products` 价格 + `review_overview` 评分/销量；
> ②情感/痛点=商品评论 + 笔记评论双来源；
> ③竞品/趋势=笔记 `interactInfo` 热度 + 商品 `vendor` 店铺，按时间重复搜对比。

## 四、复测脚本

```
python3 采集工作台/scripts/tikhub_douyin_probe.py "labubu"          # 抖音/TikTok 电商选品漏斗
python3 采集工作台/scripts/tikhub_douyin_probe.py --dump            # 把原始 JSON 落 /tmp 供查字段
python3 采集工作台/scripts/tikhub_xiaohongshu_probe.py "口红"        # 小红书商品+笔记双漏斗
python3 采集工作台/scripts/tikhub_xiaohongshu_probe.py "口红" --dump # 把原始 JSON 落 /tmp 供查字段
```

## 五、待办
- region 目前实测 `US`（TikTok Shop 美区数据最全）；若要中文/东南亚选品需试 `MY/GB/ID` 等。
- 小红书商品 / 笔记评论在跨境 / 冷门 sku 上常为空，热门词（如 `口红`）笔记评论充足。
- 正式采集脚本 `tikhub_douyin_product_collect.py` / `tikhub_xiaohongshu_collect.py` 尚未写（按指示先探接口，未急于落库）。
