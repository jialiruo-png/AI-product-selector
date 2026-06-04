# Skill MD 目录（配置即技能）

每个专家 Agent = 一份人可读、业务可改的 Markdown（PRD 1.2 / 第 5 节）。
业务运营改 MD = 改产品策略，无需研发介入。

## ● 现在能跑（TikHub 数据 + 现有代码）—— 已落地 MD

沿 `next_skill` 串联成 Skill 链：
`关键词 → 选品 → 竞品 / 爆款策划 → 口碑诊断 → 洞察报告`

| 专家 | MD 文件 | PRD 出处 | next_skill |
|---|---|---|---|
| 关键词 | `guanjianci.md` | L2B | 选品 |
| 选品 | `xuanpin.md` | L2B | 竞品 |
| 竞品 | `jingpin.md` | L2B | 爆款策划 |
| 爆款策划 | `baokuan.md` | L2B | 口碑诊断 |
| 商品诊断（口碑版） | `koubei_zhenduan.md` | L2B | 洞察报告 |

## ◐ 半跑（TikHub + 商家私域导入）—— 未来占位，暂无 MD

| 专家 | 缺什么 | 折中实现 | tier |
|---|---|---|---|
| 客服 Agent | 真实订单/退换货数据 | 商家 Wiki overlay → RAG 应答 | ◐ |
| 售后 Agent | 抖店售后规则库 | 评论负向痛点 + 商家自定义退换货政策 | ◐ |
| 核价 Agent | 抖店成本/采购数据 | 纯本地利润核算表 | ◐ |

## ○ 平台侧未来（必须抖店原生 API）—— 未来占位，暂无 MD

| 专家 | 依赖的原生数据 | tier |
|---|---|---|
| 罗盘归因 Agent | 抖店罗盘实时 GMV/CTR/CVR 漏斗 | ○ |
| 经营 OKR Agent | 抖店历史销售数据 | ○ |
| 直播策划 Agent | 巨量百应达人池 + 抖音直播 API | ○ |
| 短视频脚本 Agent | 抖音内容生态数据 | ○ |
| 订单 / 物流 Agent | 抖店订单/物流 API | ○ |
| 新品立项 / 上市节奏 Agent | 抖店 ERP / 审批流集成 | ○ |
