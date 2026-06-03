# TikHub API 接入说明（实测版）

> 测试时间 2026-06-03，全部端点用真实 key 实测。

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

## 二、小红书（✅ 全链路实测通过）

### 搜索笔记（生产用 App 端，web_v3 上游易故障）
```
GET /api/v1/xiaohongshu/app/search_notes
    keyword（必填） page=1 sort=general noteType=_0
```
返回 `data.data.items[]`，过滤 `model_type=="note"`，取每条 `it["note"]`，单条自带：
- `id` → note_id；`xsec_token`（**note 顶层**）→ 详情接口的 xsec_token
- `title` 标题；`desc` **正文预览（上游硬截断 ≈60 字，拿不到更多）**
- `liked_count / collected_count / comments_count / shared_count` 互动数（**齐全**）
- `images_list[].url`（或 `url_size_large`）→ **全部图片 URL，张数完整**
- `user.nickname` 作者

> 备用：`web_v3/fetch_search_notes`（page/sort/note_type=0）字段名为驼峰
> （`xsecToken`、`noteCard.displayTitle`），但上游搜索时常 400，生产勿用。

### 图文详情
```
GET /api/v1/xiaohongshu/web_v3/fetch_note_detail
    note_id（必填） xsec_token（必填）
```
返回 `data.data.items[0].noteCard`（`data` 可能为 null，需空安全取）：
- `title` 标题，`desc` **完整长正文（几百~上千字，详情唯一不可替代的价值）**
- `tagList[].name` 标签
- `interactInfo` 互动数据（与搜索端一致）
- `imageList[].urlDefault` 高清图 URL（**张数与搜索端相同，不为图片多花钱**）

### 搜索 vs 详情：哪步能用脚本代替（决定成本）

| 数据 | 搜索端 | 详情端 | 能否脚本代替 |
|---|---|---|---|
| 图片 URL（全张） | ✅ 全有 | 相同 | ✅ 搜索端直接拿，零额外成本 |
| 互动数 / 标题 / 作者 | ✅ 全有 | 相同 | ✅ 搜索端直接拿 |
| 正文 | ⚠️ 仅前 ≈60 字 | ✅ 完整长文 | ❌ **唯一必须花钱补的步骤** |

**单价**：搜索 $0.01/页（20条），详情 $0.01/**条**。结论：图片/互动/预览全免费白拿，
只在「值得的笔记」上花钱补长正文 → 详情只对评分 Top-N 调用。

> ⚠️ 对比 OpenCLI（浏览器自动化）：只能小批量、慢、易触发风控封号；
> TikHub 走官方代理池，可批量、稳定、无封号风险，差价就买的是这个。

## 三、知乎（✅ 搜索实测通过，正文自带）

### 文章/回答搜索
```
GET /api/v1/zhihu/web/fetch_article_search_v3
    keyword（必填） offset=0 limit=20
```
返回 `data.data[]`，过滤 `type=="search_result"`（去掉 `knowledge_ad` 广告）。
每条 `object`：
- `id`、`type`（answer/article）、`title`
- `content` **已是完整正文 HTML，无需再调详情接口**
- `excerpt` 摘要，`voteup_count` 赞同，`comment_count`、`favorites_count`
- `question.{id,name}`、`author.name`、`created_time`

## 四、公众号（⚠️ 上游临时不可用）

```
GET /api/v1/wechat_mp/web/fetch_search_article
    keyword（必填） offset=0 sort_type=_0
```
实测连续返回 400（含官方 demo 参数），属 **TikHub 上游微信搜索故障**（该情况不扣费）。
应用层需重试 + 失败回退 OpenCLI。其余详情类端点：
- `fetch_mp_article_detail_json` 文章详情
- `fetch_mp_article_list` 号内文章列表
- `fetch_search_official_account` 搜号

## 五、字段映射到现有 collect_any.py

现有 `enrich_scores` 评分用的 key（likes/collects/comments/votes...）已通过 `first_present`
多名兼容，TikHub 字段（likedCount/collectedCount/voteup_count）大多能对上，
新增映射时补到对应 keys 列表即可。

## 六、降本：筛选漏斗 + 三路分流（tikhub_xhs_collect.py）

一次搜索（$0.01/20条）拿回全部图片+预览+互动后，**先用免费数据筛，再按结果分三路**，
只在达标且高分的笔记上花详情钱：

| 分流 | 判定 | 去向 | 是否花详情钱 |
|---|---|---|---|
| **重复** | note_id 已在去重缓存 | 跳过，不落盘 | 否（零成本） |
| **未达标** | 正文<40字 / 标题含求助·问句词 | **草稿库**（带图，标注未达标原因，供人工二筛） | 否 |
| **达标** | 通过筛选 | **素材库**，仅评分 Top-N 调详情补长正文 | 仅 Top-N |

- 去重缓存：`采集工作台/.tikhub_seen_notes.json`（已 gitignore），素材库+草稿库的
  note_id 都进缓存，跨次运行同关键词不重复落盘。
- 草稿库：`采集工作台/草稿库/{日期}-小红书-{关键词}/`（已 gitignore），按关键词累积。
- 实测：抓 8 条仅花 ≈$0.03（旧方案每条都调详情 $0.09），省 67%；
  `--detail-top 0` 完全不调详情时省 87%。

### 用法
```bash
# 默认：筛选 + Top5 调详情 + 去重，未达标进草稿库
python3 采集工作台/scripts/tikhub_xhs_collect.py "关键词" --limit 15

# 最省：完全不调详情，只要图片+预览
python3 采集工作台/scripts/tikhub_xhs_collect.py "关键词" --detail-top 0

# 调更多长文 / 放宽正文门槛 / 强制重抓
... --detail-top 10 --min-desc 30 --no-cache
```

## 七、复测脚本

```
python3 采集工作台/scripts/tikhub_probe.py "关键词"
```
