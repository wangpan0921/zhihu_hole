"""微信公众号后台的持久化浏览器上下文。

storage_state 只适合迁移和备份；公众号后台的 cookie、localStorage 以及
浏览器 profile 信息需要在同一 user-data-dir 中长期复用，才能减少频繁失效。
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, sync_playwright

from .utils import AUTH_DIR, PROJECT_ROOT, get_logger

log = get_logger("wechat_browser")

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_PROFILE_DIR = AUTH_DIR / "wechat_mp_chrome_profile"


def _project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def profile_has_state(profile_dir: Path) -> bool:
    """只把真正初始化过的 Chromium profile 视为可复用。"""
    profile_dir = _project_path(profile_dir)
    return any(
        (profile_dir / "Default" / marker).exists()
        for marker in ("Cookies", "Preferences", "Local Storage")
    ) or (profile_dir / "Local State").exists()


@contextlib.contextmanager
def browser_context(
    *,
    storage_state: Path | None = None,
    profile_dir: Path | None = None,
    headless: bool = True,
    viewport_width: int = 1440,
    viewport_height: int = 1000,
) -> Iterator[BrowserContext]:
    """打开公众号持久化上下文，首次运行可从旧 storage_state 迁移。"""
    profile = _project_path(profile_dir or DEFAULT_PROFILE_DIR)
    profile.mkdir(parents=True, exist_ok=True)
    state = _project_path(storage_state) if storage_state else None
    state_arg = None
    if state and state.is_file() and not profile_has_state(profile):
        state_arg = str(state)
        log.info("公众号持久化 profile 尚未初始化，将从登录态迁移：%s", state)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            storage_state=state_arg,
            user_agent=_UA,
            viewport={"width": viewport_width, "height": viewport_height},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            yield context
        finally:
            with contextlib.suppress(Exception):
                context.close()


def save_storage_state(context: BrowserContext, storage_state: Path) -> None:
    """保留一份可迁移/排障的 storage_state 备份。"""
    path = _project_path(storage_state)
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
