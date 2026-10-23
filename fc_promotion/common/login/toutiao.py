"""头条号登录器（预留）。

头条号创作者平台为扫码登录。登录成功判定需按实际页面补全，
接入时在本机 headful 跑一次、确认 URL/cookie 特征后完善 is_logged_in。
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, Page

from .base import PlatformLogin


class ToutiaoLogin(PlatformLogin):
    name = "toutiao"
    storage_filename = "toutiao_state.json"

    @property
    def login_url(self) -> str:
        return "https://mp.toutiao.com/"

    def is_logged_in(self, page: Page, context: BrowserContext) -> bool:
        # 登录后会跳到创作中心 /profile_v4/ 等路径；sessionid cookie 存在即视为已登录。
        # TODO: 本机实测后收紧判定条件。
        if "/profile_v4" in page.url or "/creation" in page.url:
            return True
        return any(c.get("name") in {"sessionid", "sso_uid_tt"} for c in context.cookies())
