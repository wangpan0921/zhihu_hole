"""小红书登录器（预留）。

小红书网页端扫码登录。接入时在本机 headful 跑一次、确认登录成功特征后完善。
注意：小红书风控较严，自动化操作务必低频，优先用于"收集线索 + 人工回复"。
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, Page

from .base import PlatformLogin


class XiaohongshuLogin(PlatformLogin):
    name = "xiaohongshu"
    storage_filename = "xiaohongshu_state.json"

    @property
    def login_url(self) -> str:
        return "https://www.xiaohongshu.com/explore"

    def is_logged_in(self, page: Page, context: BrowserContext) -> bool:
        # 登录后 web_session cookie 存在。TODO: 本机实测后收紧判定。
        return any(c.get("name") in {"web_session", "customerClientId"} for c in context.cookies())
