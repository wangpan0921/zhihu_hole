"""持久化 profile 通用登录基类。

知乎/酷安/头条/小红书都靠"持久化 Chrome profile + 反指纹"绕风控，登录流程一致：
打开首页/登录页 → 用户扫码/登录 → 轮询登录 cookie → 登录态落在持久化 profile。
差异仅在"profile 名、登录 URL、判定 cookie"，全部从 config 读取，子类只设 name。

扩展新平台：继承本类、设 name，并在 config 的 PLATFORM_PROFILE /
PLATFORM_LOGIN_COOKIES / PLATFORM_HOME 补三项，再到 registry 登记。
"""
from __future__ import annotations

import time

from playwright.sync_api import BrowserContext, Page

from .base import PlatformLogin
from .. import humanized_browser as hb


class PersistentProfileLogin(PlatformLogin):
    """基于持久化 profile 的登录器；各平台仅需设置 name。"""

    name = ""
    storage_filename = "unused.json"  # 兼容基类接口，实际不用

    # 登录页（默认用首页；需要独立登录页的平台覆盖）
    @property
    def login_url(self) -> str:
        from ... import config
        return config.PLATFORM_HOME.get(self.name, "/")

    def _profile(self) -> str:
        from ... import config
        return config.PLATFORM_PROFILE[self.name]

    def _login_cookies(self) -> list[str]:
        from ... import config
        return config.PLATFORM_LOGIN_COOKIES.get(self.name, [])

    @property
    def storage_path(self):
        return hb.profile_dir(self._profile())

    def is_logged_in(self, page: Page, context: BrowserContext) -> bool:
        names = set(self._login_cookies())
        return any(c.get("name") in names for c in context.cookies())

    def login_interactive(self, *, headful: bool = True):  # noqa: ARG002
        with hb.persistent_context(self._profile(), headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(self.login_url, wait_until="domcontentloaded", timeout=40000)
            print(f"请在打开的浏览器窗口中登录【{self.name}】（最长 5 分钟）…")
            deadline = time.time() + 300
            while time.time() < deadline:
                if self.is_logged_in(page, ctx):
                    print(f"[{self.name}] 登录成功，登录态已写入持久化 profile。")
                    time.sleep(2)
                    return hb.profile_dir(self._profile())
                time.sleep(2)
            raise TimeoutError(f"[{self.name}] 登录超时")

    def logged_in(self) -> bool:
        from ... import config
        try:
            with hb.persistent_context(self._profile(), headless=False) as ctx:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(config.PLATFORM_HOME.get(self.name, "/"),
                          wait_until="domcontentloaded", timeout=40000)
                time.sleep(3)
                return self.is_logged_in(page, ctx)
        except Exception:  # noqa: BLE001
            return False
