"""知乎登录器。

实测：知乎对临时 context+默认自动化指纹返回 40362 风控页，必须用持久化
profile（见 common/humanized_browser）。故知乎登录与发布共用同一个持久化
profile（config.ZHIHU_PROFILE），登录一次长期复用，不走 storage_state.json。
"""
from __future__ import annotations

import time

from playwright.sync_api import BrowserContext, Page

from .base import PlatformLogin
from .. import humanized_browser as hb


class ZhihuLogin(PlatformLogin):
    name = "zhihu"
    # 仅为兼容基类接口；知乎实际用持久化 profile，不读写该文件
    storage_filename = "storage_state.json"

    @property
    def storage_path(self):
        # 知乎实际登录态在持久化 profile 目录，覆盖基类的 storage_state.json 字面量
        from .. import humanized_browser as hb
        from ... import config
        return hb.profile_dir(config.ZHIHU_PROFILE)

    @property
    def login_url(self) -> str:
        return "https://www.zhihu.com/signin"

    def is_logged_in(self, page: Page, context: BrowserContext) -> bool:
        if "signin" not in page.url:
            # 仍需确认确实拿到登录 cookie，避免停在风控/落地页
            if any(c.get("name") == "z_c0" for c in context.cookies()):
                return True
        return any(c.get("name") == "z_c0" for c in context.cookies())

    # 覆盖基类：用持久化 profile（headful 扫码）
    def login_interactive(self, *, headful: bool = True):  # noqa: ARG002
        from ... import config

        with hb.persistent_context(config.ZHIHU_PROFILE, headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(self.login_url, wait_until="domcontentloaded", timeout=40000)
            print("请在打开的浏览器窗口中扫码登录知乎（最长 5 分钟）…")
            deadline = time.time() + 300
            while time.time() < deadline:
                if self.is_logged_in(page, ctx):
                    print("[zhihu] 登录成功，登录态已写入持久化 profile。")
                    time.sleep(2)
                    return hb.profile_dir(config.ZHIHU_PROFILE)
                time.sleep(2)
            raise TimeoutError("[zhihu] 扫码登录超时")

    # 覆盖基类：用持久化 profile 静默校验
    def logged_in(self) -> bool:
        from ... import config

        try:
            with hb.persistent_context(config.ZHIHU_PROFILE, headless=False) as ctx:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto("https://www.zhihu.com/", wait_until="domcontentloaded", timeout=40000)
                time.sleep(3)
                return any(c.get("name") == "z_c0" for c in ctx.cookies())
        except Exception:  # noqa: BLE001
            return False
