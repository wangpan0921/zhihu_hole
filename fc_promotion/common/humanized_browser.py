"""持久化 profile 浏览器（拟人化，绕过知乎对自动化浏览器的风控）。

实测结论：知乎对"临时 context + 默认自动化指纹（navigator.webdriver=true、空 profile）"
会直接返回 40362 风控页；改用**持久化 Chrome profile + 关闭 AutomationControlled
+ 抹掉 webdriver 指纹**后页面正常放行。真人化自动操作必须基于这种上下文。

登录态与发布共用同一个持久化 profile 目录（data/auth/zhihu_chrome_profile），
即"登录一次、长期复用"，不再依赖独立的 storage_state.json。
"""
from __future__ import annotations

import contextlib
import random
import time
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .paths import AUTH_DIR

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
        ctx = p.chromium.launch_persistent_context(
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
