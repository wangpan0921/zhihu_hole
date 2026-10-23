"""Playwright 浏览器上下文封装。

统一 UA / viewport / locale，并复用已保存的 storage_state 登录态。
全自动评论场景用 persistent 的 headful 浏览器更稳（更接近真人、少触发风控）。
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, sync_playwright

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@contextlib.contextmanager
def browser_context(
    *,
    storage_state: Path | None = None,
    headless: bool = True,
    viewport_width: int = 1280,
    viewport_height: int = 900,
) -> Iterator[BrowserContext]:
    """打开一个带登录态的浏览器上下文。

    storage_state 存在则加载登录态；为 None 或文件不存在则匿名上下文（用于首次登录）。
    """
    state_arg = None
    if storage_state is not None and Path(storage_state).exists():
        state_arg = str(storage_state)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            storage_state=state_arg,
            user_agent=_UA,
            viewport={"width": viewport_width, "height": viewport_height},
            locale="zh-CN",
        )
        try:
            yield context
        finally:
            with contextlib.suppress(Exception):
                browser.close()
