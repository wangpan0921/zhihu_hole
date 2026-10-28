# fc_promotion —— 悬浮时钟跨平台推广

「悬浮时钟」App 的推广自动化。复用 zhihu 项目的 Playwright + venv，按平台可扩展。

**平台现状**：
- 知乎 ✅ 搜问题→写回答（已实测真发通过，持久化 profile 绕 40362 风控）
- 酷安 / 头条号 / 小红书 ⏳ 搜帖→评论（已接入通用搜索/发布框架，选择器需首次本机实测核对）
- 公众号 ✅ 发自有推广软文草稿（复用项目现有发布器，强制存草稿不群发）

## 定位与边界

- 用**本人账号 + 本机持久化浏览器 profile**，在有真实需求的帖子下自然评论；不做机器人私信陌生人。
- 只在本机（有登录态的 Chromium）运行；云端无登录态搜不到也发不了。
- 自动评论有风控/封号风险，内置频控（每天随机 1~3 条、发一条停 60 秒），小红书风控最凶务必低频。

## 反风控：持久化 profile

知乎/酷安/头条/小红书对"临时 context + 默认自动化指纹"会风控（知乎返回 40362）。
解法：`common/humanized_browser.py` 用 `launch_persistent_context` 持久化 profile
+ 关闭 AutomationControlled + 抹 webdriver 指纹 + 拟人动作（随机停顿/滚动/逐字输入）。
登录态绑在持久化 profile（`data/auth/<platform>_chrome_profile`），扫码一次长期复用。

## 目录结构

```
fc_promotion/
  common/
    paths.py / logging_utils.py / browser.py
    humanized_browser.py   # 持久化 profile + 反指纹 + 拟人动作
    feishu_bitable.py      # 飞书多维表格写入
    login/
      base.py              # 旧 storage_state 流程基类（公众号等轻量登录用）
      persistent_base.py   # 持久化 profile 通用登录基类（知乎/酷安/头条/小红书）
      zhihu.py coolapk.py toutiao.py xiaohongshu.py wechat.py
      registry.py          # 平台登录器注册表
  config.py                # 卖点/下载邀请/飞书表/各平台搜索URL与选择器/频控
  copywriter.py            # 推广文案（卖点在前 + 图片块 + 原样邀请文本在后）
  promote.py               # 搜索→生成文案→发布→写飞书（知乎专用 + 通用实现）
  wechat_promo.py          # 公众号推广软文 → 存草稿
  assets/                  # 三张产品截图（桌面/阅读/设置页）
  login_cli.py             # python -m fc_promotion.login_cli <platform>
```

## 快速开始

```bash
cd /media/wangpan/hdd1/0-me/zhihu && source venv/bin/activate

# 1) 各平台首次登录（本机扫码，登录态入持久化 profile）
PYTHONPATH=. python -m fc_promotion.login_cli zhihu
PYTHONPATH=. python -m fc_promotion.login_cli coolapk
PYTHONPATH=. python -m fc_promotion.login_cli toutiao
PYTHONPATH=. python -m fc_promotion.login_cli xiaohongshu
PYTHONPATH=. python -m fc_promotion.login_cli <platform> --check   # 校验登录态

# 2) 预览线索与文案（不发布、不写飞书）
PYTHONPATH=. python -m fc_promotion.promote --platform coolapk --dry-run

# 3) 正式跑（本机、有登录态）；--post 才真发，默认每天随机 1~3 条
PYTHONPATH=. python -m fc_promotion.promote --platform coolapk --post

# 公众号推广软文存草稿
PYTHONPATH=. python -m fc_promotion.wechat_promo --dry-run    # 只看 markdown
PYTHONPATH=. python -m fc_promotion.wechat_promo             # 存草稿（需登录公众号）
```

公众号软文会自动插入 `assets/` 下的三张产品截图，并将桌面悬浮图作为草稿封面。
知乎、酷安、头条和小红书的评论入口当前按纯文字发送，不会把本地路径误发给用户。

## 新平台首次接入须本机核对选择器

酷安/头条/小红书的"线索链接选择器"与"评论入口/编辑器/发送按钮选择器"在
`config.PLATFORM_LINK_SELECTOR` 与 `config.PLATFORM_POST_SELECTORS`，是多候选兜底的
**最佳猜测**。首次务必在本机 headful 跑一遍、对照 debug 截图核对并收紧，确认
"搜到帖→打开→定位编辑器→发送"链路后再开 `--post`（和知乎当初一样的流程）。

## 飞书记录

写入「推广数据库」多维表格；凭据从 zhihu 项目 `.env`（`FEISHU_APP_ID`/`FEISHU_APP_SECRET`）读取。
注意：飞书自建应用需开通 `bitable:app` 权限，否则写入报 `99991672`。

## 扩展新平台

1. `common/login/` 新增 `<platform>.py`，继承 `persistent_base.PersistentProfileLogin`，设 `name`；
2. `registry.py` 登记；
3. `config.py` 补 `SEARCH_TARGETS` / `PLATFORM_PROFILE` / `PLATFORM_LOGIN_COOKIES` / `PLATFORM_HOME` / `PLATFORM_LINK_SELECTOR` / `PLATFORM_POST_SELECTORS`；
4. `promote.py` 的通用 searcher/poster 会自动适配（知乎是专用实现）。
