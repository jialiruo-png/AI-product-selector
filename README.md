# AI 素材采集平台

一个面向内容生产的本地素材采集工具。当前版本支持通过关键词或链接采集公众号、小红书、知乎和 GitHub 素材，并输出为干净的 Markdown 文件。

## 当前能力

- 输入关键词或多个链接
- 选择平台：公众号 / 小红书 / 知乎 / GitHub
- 设置候选筛选数量和最终下载数量
- 优先根据平台数据和相关性做候选排序
- 将正文保存为 Markdown
- 图片以内嵌 `data:image` 的形式写入 Markdown
- 运行产物默认保存在 `采集工作台/素材库/`，该目录不会提交到 Git

## 环境要求

- Python 3.12+
- macOS 推荐使用 Homebrew Python
- OpenCLI：用于公众号、小红书、知乎等平台搜索和浏览器态采集
- GitHub CLI `gh`：用于 GitHub 平台搜索和仓库信息采集

## 安装

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

确认 OpenCLI 可用：

```bash
opencli doctor
```

确认 GitHub CLI 可用：

```bash
gh auth status
```

## 命令行使用

公众号：

```bash
./采集工作台/scripts/collect_any.py --platform weixin --input "AI产品经理" --candidate-limit 10 --limit 3
```

小红书：

```bash
./采集工作台/scripts/collect_any.py --platform xiaohongshu --input "AI产品经理" --candidate-limit 10 --limit 3
```

知乎：

```bash
./采集工作台/scripts/collect_any.py --platform zhihu --input "AI产品经理" --candidate-limit 10 --limit 3
```

GitHub：

```bash
./采集工作台/scripts/collect_any.py --platform github --input "AI agent" --candidate-limit 10 --limit 3
```

## 图形界面

```bash
python3 采集工作台/scripts/material_collector_gui.py
```

界面里可以同时填写链接、关键词、平台、筛选数量和下载数量。填写链接时优先按链接采集；链接为空时按关键词搜索。

## 目录说明

```text
采集工作台/
  collect                         # 公众号链接/关键词基础采集脚本
  scripts/
    collect_any.py                # 统一采集入口
    material_collector_gui.py     # 本地图形界面
    inline_markdown_images.py     # Markdown 图片内嵌工具
    topic_fetch_agent.py          # 主题采集实验脚本
web-fetcher/                      # 内置网页抓取内核
requirements.txt                  # 项目依赖
```

## 不提交的内容

以下内容属于运行产物，已写入 `.gitignore`：

- `采集工作台/素材库/`
- `采集工作台/outputs/`
- `采集工作台/topics/`
- `采集工作台/logs/`
- `.venv/`
- `__pycache__/`

## 开发备注

这个仓库已经移除了原始 `web-fetcher` 仓库的历史文档、升级方案、测试报告、原 README、`.git` 和虚拟环境，只保留当前项目运行需要的代码与配置。
