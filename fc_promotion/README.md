# fc_promotion —— 悬浮时钟跨平台推广

专门存放「悬浮时钟」App 的推广自动化代码。复用 zhihu 项目既有的 Playwright + 登录态基建，把各平台登录抽成**公共模块** `common/`，按平台可扩展（已内置知乎、微信公众号登录态复用；头条号、小红书预留接入点）。

## 定位与边界

- 用**本人账号、复用本机已登录的浏览器登录态**，在有真实需求的问题/帖子下自然评论推广，不做机器人私信陌生人。
- 全自动评论脚本**只在本机（有登录态的 Chromium）运行**，不要部署到无登录态的云端环境。
- 高频自动评论仍有平台风控/封号风险，脚本内置限速与每日上限，请谨慎调小频率。

## 目录结构

```
fc_promotion/
  common/
    __init__.py
    paths.py            # 复用 zhihu 项目的 data/auth、logs、debug 路径
    logging_utils.py    # 统一 logger
    browser.py          # Playwright 上下文封装（复用 storage_state 登录态）
    login/
      __init__.py
      base.py           # PlatformLogin 抽象基类 + 登录态扫码保存通用流程
      zhihu.py          # 知乎登录（复用 scripts/login.py 的二维码逻辑）
      wechat.py         # 微信公众号登录（复用 scripts/wechat_login.py）
      toutiao.py        # 头条号登录（预留，待接入）
      xiaohongshu.py    # 小红书登录（预留，待接入）
      registry.py       # 平台名 → 登录器的注册表，扩展新平台只需在此登记
    feishu_bitable.py   # 飞书多维表格（bitable）写入客户端
  config.py             # 推广目标、飞书表 token、下载渠道、卖点等集中配置
  copywriter.py         # 推广文案生成（突出体积小/不占空间/耗电低）
  promote.py            # 主编排：搜索 → 生成评论 → 发布 → 写飞书
  login_cli.py          # 统一登录入口：python -m fc_promotion.login_cli <platform>
  requirements.txt      # 额外依赖（基本复用 zhihu 项目 venv）
  README.md
```

## 快速开始

```bash
cd /media/wangpan/hdd1/0-me/zhihu
source venv/bin/activate

# 1) 各平台首次登录（扫码），登录态存 data/auth/
python -m fc_promotion.login_cli zhihu --headful
python -m fc_promotion.login_cli wechat --headful

# 2) 看看会生成什么推广文案（不发布、不写飞书）
python -m fc_promotion.promote --dry-run

# 3) 正式跑一轮（本机、有登录态时）
python -m fc_promotion.promote --platform zhihu --max 3
```

## 飞书记录

推广记录写入「推广数据库」飞书多维表格；字段写法参考「悬浮时钟数据库」。表标识集中在 `config.py`，飞书应用凭据从 zhihu 项目 `.env`（`FEISHU_APP_ID` / `FEISHU_APP_SECRET`）读取。

## 扩展新平台

1. 在 `common/login/` 下新增 `<platform>.py`，继承 `base.PlatformLogin`，实现 `login_url`、`is_logged_in()`、`storage_filename`。
2. 在 `common/login/registry.py` 的 `LOGIN_REGISTRY` 登记。
3. 在 `config.py` 的 `SEARCH_TARGETS` 补该平台的搜索入口与选择器。
