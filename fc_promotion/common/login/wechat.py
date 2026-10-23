"""微信公众号后台登录器。复用 scripts/wechat_login.py 的判定与登录态文件。"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, Page

from .base import PlatformLogin


class WechatLogin(PlatformLogin):
    name = "wechat"
    # 与 config.yaml 的 wechat_mp.storage_state 一致
    storage_filename = "wechat_mp_state.json"

    @property
    def login_url(self) -> str:
        return "https://mp.weixin.qq.com/"

    def is_logged_in(self, page: Page, context: BrowserContext) -> bool:
        if "cgi-bin/home" in page.url or "token=" in page.url:
            return True
        return any(
            c.get("name") in {"slave_sid", "bizuin", "data_bizuin"}
            for c in context.cookies()
        )
