---
name: publish-wechat-album-to-zhihu
description: 按微信公众号合集顺序将下一篇文章发布到指定知乎专栏，并维护去重进度、跳过已存在文章、保留标题/代码块/列表/图片格式及检查定时任务。用于立即发布或预演下一篇、查看合集同步进度、修复已发布文章格式、排查每天 08:30 的公众号合集转知乎任务。
---

# 微信公众号合集发布到知乎

使用项目现有发布链路，不要重新实现抓取或直接粘贴微信公众号原始 HTML。

## 固定环境

- 项目：当前 `zhihu_hole` 仓库根目录，或由 `ZHIHU_HOLE_PROJECT_DIR` 指定的目录
- 配置：`config.yaml` 中的 `wechat_album_to_zhihu`
- 进度：`data/wechat_album/state.json`
- 日志：`logs/cron.log`
- 调试产物：`debug/article_*`
- Skill 入口：`skills/publish-wechat-album-to-zhihu/scripts/publish-next.sh`

保护知乎登录态、合集进度文件和发布记录。不要删除或重建它们。

## 发布下一篇

仅在用户明确要求真实发布，或由已安装的 08:30 cron 触发时执行：

```bash
bash skills/publish-wechat-album-to-zhihu/scripts/publish-next.sh
```

用户要求预览、检查或诊断时先执行：

```bash
bash skills/publish-wechat-album-to-zhihu/scripts/publish-next.sh --dry-run
```

`--dry-run` 会创建一个未发布的知乎草稿用于检查，但不会发布，也不会推进 state。

该入口必须只调用项目的 `scripts/publish_wechat_album_to_zhihu.py`。项目代码负责：

1. 从配置的合集读取正序文章列表。
2. 按 `skip_first` 跳过已在知乎存在的开头文章。
3. 根据 state 跳过已处理文章，每次只选择下一篇。
4. 将微信正文清洗为 Markdown，再转为知乎可识别的结构化 HTML。
5. 成功发布到目标专栏后才写入 state。

真实发布后检查命令输出中的知乎 URL，并确认 state 新记录的状态为 `published`。

## 格式保护

- 使用 `src/wechat_album_to_zhihu.py` 清理微信包装节点并转换 Markdown。
- 使用 `src/markdown_html.py` 生成标题、列表、代码块和独立图片 HTML。
- 使用知乎编辑器的可信 HTML 粘贴路径；禁止把 `#js_content` 原始 HTML 直接粘贴到知乎。
- 若更改转换或发布代码，运行 `./venv/bin/pytest -q` 和 `git diff --check`。
- 格式异常时先比较最新的 `debug/article_*.html` 和截图，不要直接推进 state。

## 修复已发布文章

从 state 取得微信原文 URL 和知乎 `article_url`，重新调用
`publish_article(..., edit_url=article_url)`。必须满足以下保护条件：

1. 打开原文章的 `/edit` 页面，不创建新文章。
2. 清空旧正文后确认剩余字数为 0。
3. 粘贴清洗后的结构化正文。
4. 点击“更新”，而不是“发布”。
5. 重新打开编辑页，统计标题、代码块、列表项和图片节点确认已保存。

不要因格式修复新增 state 项或推进到下一篇。

## 定时任务

检查每天 08:30 的任务：

```bash
cd <项目根目录>
bash scripts/install_cron.sh status
```

安装或刷新任务：

```bash
cd <项目根目录>
bash scripts/install_cron.sh install
```

cron 必须调用本 Skill 的 `scripts/publish-next.sh`。若登录失效、抓取失败、格式校验失败或发布失败，保留 state 不变并从日志排查。
