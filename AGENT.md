# AGENT.md

这个项目是知乎想法、知乎专栏文章、微信公众号文章的自动生成与发布系统。不同 agent 接手时，优先遵守本文规范，保持生成内容、脚本改动和发布流程一致。

## 项目边界

- 项目根目录：`/media/wangpan/hdd1/0-me/zhihu`
- 主要配置：`config.yaml`
- Python 虚拟环境：`venv/`
- 想法草稿：`data/pending/`
- 想法归档：`data/published/`
- 文章待发布目录：`docs/pending/`
- 文章已发布目录：`docs/published/`
- 登录态、密钥、发布标记都可能影响线上发布，不要随意删除或重建。

## 开发原则

- 优先沿用现有脚本、目录结构和命名方式，不要引入新的发布流程。
- 修改代码前先阅读相关脚本和 README，确认现有行为。
- 不要回滚用户或其他 agent 已经产生的改动，除非用户明确要求。
- 不要把 API key、cookie、storage state、token 等敏感信息写进文章、日志或提交说明。
- 需要执行真实发布、联网请求、登录态刷新、删除标记文件等动作时，先确认用户意图是否明确。
- 自动化脚本失败时，优先查看 `logs/` 和 `debug/` 目录中的日志、截图和中间产物。

## 常用命令

```bash
# 生成想法草稿
./venv/bin/python scripts/generate_drafts.py

# 发布知乎想法
./venv/bin/python scripts/publish_slot.py morning
./venv/bin/python scripts/publish_slot.py evening

# dry-run 发布知乎想法
./venv/bin/python scripts/publish_slot.py morning --dry-run

# 发布知乎专栏文章
./venv/bin/python scripts/publish_articles.py

# 发布微信公众号文章
./venv/bin/python scripts/publish_wechat_articles.py

# dry-run 微信公众号文章
./venv/bin/python scripts/publish_wechat_articles.py --dry-run

# 安装/查看/卸载 cron
bash scripts/install_cron.sh install
bash scripts/install_cron.sh status
bash scripts/install_cron.sh uninstall
```

## 文章生成规范

- 自动生成的文章统一放到 `docs/pending/`。
- `docs/pending/` 下自动生成的文章文件名必须以日期开头，格式为：

  ```text
  YYYY-MM-DD-文章标题.md
  ```

  示例：

  ```text
  2026-07-11-Dockerfile中镜像层是如何计算的.md
  ```

- 文件名中的标题尽量使用中文短标题，避免空格、特殊符号和过长文件名。
- Markdown 第一行必须是文章标题，使用一级标题：

  ```markdown
  # Dockerfile 中镜像层是如何计算的
  ```

- 不要手工在 `docs/published/` 创建发布标记，除非是在修复明确的发布状态问题。
- 知乎和微信公众号发布成功后，脚本会写入对应的 `.meta.json` / `.wechat.meta.json` 标记；两个平台都完成后才会归档 Markdown。
- 文章发布队列按脚本逻辑从 `docs/pending/` 中选择文件，创建或修改文件时要注意发布时间顺序。

## 内容风格

- 技术文章要直接解释问题、给出可运行命令和典型场景。
- 避免空泛介绍，优先写清楚“为什么”“怎么查”“常见误区”“推荐做法”。
- Docker、pip、Python 等工程类文章尽量包含实际命令和可复制代码块。
- 不要在文章中暴露本机路径、私有 token、真实 cookie 或账号信息，除非是无敏感性的示例路径。

## 微信读书与书籍池

- 书籍池配置在 `config.yaml` 的 `content.book.book_pool`。
- 微信读书索引文件放在 `data/books/<bookId>/index.json`。
- 新增书籍时，先索引章节，再把 `bookId` 加入书籍池，并确认索引中有可用正文 URL。

## 发布状态排查

- 想法发布状态优先看：
  - `data/pending/`
  - `data/published/`
  - `logs/app.log`
  - `logs/cron.log`
  - `debug/publish_*`
- 文章发布状态优先看：
  - `docs/pending/`
  - `docs/published/*.meta.json`
  - `docs/published/*.wechat.meta.json`
  - `debug/wechat_article_*`
- 如果用户说公众号或知乎看不到某篇文章，不要只看 Markdown 是否存在，要同时检查对应平台的 meta 标记和发布日志。

## 代码改动规范

- Python 代码优先保持现有风格，不做无关重构。
- 新增脚本放到 `scripts/`，可复用逻辑放到 `src/`。
- 改动发布链路后，至少运行对应 dry-run 或做最小可行验证。
- 涉及定时任务时，同时检查 `scripts/install_cron.sh`、`config.yaml` 和 README 中的说明是否需要同步更新。
