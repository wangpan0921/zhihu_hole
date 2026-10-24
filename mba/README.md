# 在职 MBA 精英群内容助手

这个目录存放群内容库和发布说明。默认流程是：

1. `content/news_sources.yaml` 维护中文 RSS 和公开列表页来源，默认启用第一财经、钛媒体、国家统计局、人民银行和艾瑞咨询报告。
2. 每天 08:00 运行 `scripts/mba_news_daily.py`，抓取标题、摘要和公开正文摘录并去重。
3. 优先调用项目已有 LLM 做事实摘编和经营含义总结；LLM 不可用时使用保留原文段落与链接的确定性兜底格式。
4. 默认发布到 `mba/config.yaml` 中配置的知乎圈子；飞书/企业微信仅作为可选渠道。
5. 每次生成都会写入 `mba/archive/YYYY-MM-DD.md`，发布成功后再写入 `mba/news_state.json`，同一天重复发布会自动跳过。

## 本地预览

```bash
./venv/bin/python scripts/mba_news_daily.py --date 2026-09-06 --dry-run --limit 3
```

`--date` 便于预览任意一天，省略时使用今天。需要重复发送时使用 `--force`。生成后的正文在 `mba/archive/` 按日期查看；注意未来日期只能基于“当前抓到的最新 RSS”预览，真正的当天新闻要等 08:00 定时任务运行。

## 发布目标

当前目标是“在职MBA精英圈”：`https://www.zhihu.com/ring/host/2017205740402648085?tab=new&tab_id=0`。首次发布日期为 `2026-09-08`，每天只发布 1 条精选简报。

脚本使用项目现有 `data/auth/storage_state.json` 登录态；`--verify-target` 会打开圈子并填入内容，但不会点击发布。

## 可选群机器人

在项目根目录 `.env` 中配置其一：

```dotenv
# 飞书自定义机器人 webhook
MBA_FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/...
# 或企业微信机器人 webhook
MBA_WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...
```

只有显式使用 `--channel feishu` 或 `--channel wechat` 时才会调用 webhook；默认 `--channel zhihu` 发布到知乎圈子。Webhook 是敏感配置，不要写入内容库或提交到 git。

## 安装每日定时任务

```bash
bash mba/install_cron.sh install
bash mba/install_cron.sh status
```

MBA 任务使用独立标记，不影响项目里已有的定时任务。它会每天 08:00 抓取并发布新闻简报到知乎圈子，首次运行受 `first_publish_date` 保护。

正式安装前建议手动发送一次：

```bash
./venv/bin/python scripts/mba_news_daily.py --channel zhihu
```

## 来源与内容规范

来源配置见 `content/news_sources.yaml`。默认读取中文财经媒体、官方数据页和公开行业报告的标题、正文摘录、日期和原文链接，不绕过付费墙，不抓取登录态页面。

每条简报只保留三部分：原文事实与关键数据、对经营者的具体含义、原文链接。不要编造数据，不写群讨论，不给投资买卖建议；材料不足时明确标注“公开材料不足”。

## 内容规范

每天只发 1 条精选信息，优先选择有数字、有时间范围、有行业对象的新闻或报告。正文控制在知乎想法可读长度内，避免堆砌多条标题。内容质量的最低标准是：读者看完能知道发生了什么、数字是什么、可能影响自己的哪项经营决策。
