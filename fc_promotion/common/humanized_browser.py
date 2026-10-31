"""持久化 profile 浏览器（拟人化，绕过知乎对自动化浏览器的风控）。

实测结论：知乎对"临时 context + 默认自动化指纹（navigator.webdriver=true、空 profile）"
会直接返回 40362 风控页；改用**持久化 Chrome profile + 关闭 AutomationControlled
+ 抹掉 webdriver 指纹**后页面正常放行。真人化自动操作必须基于这种上下文。

登录态与发布共用同一个持久化 profile 目录（data/auth/zhihu_chrome_profile），
即"登录一次、长期复用"，不再依赖独立的 storage_state.json。
"""
from __future__ import annotations

import contextlib
import logging
import random
import time
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, Error, Page, sync_playwright

from .paths import AUTH_DIR

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 抹掉常见自动化指纹
_STEALTH_JS = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    "window.chrome={runtime:{}};"
    "Object.defineProperty(navigator,'languages',{get:()=>['zh-CN','zh']});"
    "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
)

_BROWSER_NOT_FOUND_MARKERS = (
    "executable doesn't exist",
    "distribution 'chrome' is not found",
    "looks like playwright was just installed or updated",
)

_CHROME_LAUNCH_FAILURE_MARKERS = (
    "target page, context or browser has been closed",
)


def _browser_not_found(error: Error) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in _BROWSER_NOT_FOUND_MARKERS)


def _chrome_unavailable(error: Error) -> bool:
    message = str(error).lower()
    return _browser_not_found(error) or any(
        marker in message for marker in _CHROME_LAUNCH_FAILURE_MARKERS
    )


def _launch_persistent_context(browser_type, **kwargs) -> BrowserContext:
    """优先系统 Chrome，缺失时回退 Playwright Chromium。"""
    try:
        return browser_type.launch_persistent_context(channel="chrome", **kwargs)
    except Error as chrome_error:
        if not _chrome_unavailable(chrome_error):
            raise
        reason = str(chrome_error).splitlines()[0]
        log.warning("系统 Chrome 不可用，回退到 Playwright Chromium：%s", reason)

    try:
        return browser_type.launch_persistent_context(**kwargs)
    except Error as chromium_error:
        if not _browser_not_found(chromium_error):
            raise
        raise RuntimeError(
            "系统 Chrome 不可用，且 Playwright Chromium 也未安装。"
            "请运行：python -m playwright install chromium"
        ) from chromium_error


def profile_dir(name: str) -> Path:
    d = AUTH_DIR / f"{name}_chrome_profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextlib.contextmanager
def persistent_context(
    profile_name: str,
    *,
    headless: bool = False,
    viewport_width: int = 1280,
    viewport_height: int = 900,
) -> Iterator[BrowserContext]:
    """打开一个持久化、带反自动化指纹的浏览器上下文。headful 更接近真人。"""
    with sync_playwright() as p:
        ctx = _launch_persistent_context(
            p.chromium,
            user_data_dir=str(profile_dir(profile_name)),
            headless=headless,
            user_agent=_UA,
            viewport={"width": viewport_width, "height": viewport_height},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx.add_init_script(_STEALTH_JS)
        try:
            yield ctx
        finally:
            with contextlib.suppress(Exception):
                ctx.close()


# ---- 拟人化动作 ----

def human_pause(a: float = 0.6, b: float = 1.8) -> None:
    time.sleep(random.uniform(a, b))


def human_scroll(page: Page, times: int = 3) -> None:
    """随机滚动页面，模拟真人浏览。"""
    for _ in range(times):
        page.mouse.wheel(0, random.randint(300, 800))
        human_pause(0.4, 1.2)


def human_type(page: Page, selector_or_locator, text: str) -> None:
    """逐字输入（带随机间隔），比一次性 fill 更像真人。"""
    loc = page.locator(selector_or_locator) if isinstance(selector_or_locator, str) else selector_or_locator
    loc.click()
    human_pause(0.3, 0.9)
    for ch in text:
        loc.type(ch, delay=random.randint(40, 140))
    human_pause(0.5, 1.3)
