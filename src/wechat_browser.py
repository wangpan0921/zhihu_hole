"""微信公众号后台的持久化浏览器上下文。

storage_state 只适合迁移和备份；公众号后台的 cookie、localStorage 以及
浏览器 profile 信息需要在同一 user-data-dir 中长期复用，才能减少频繁失效。
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any, Iterator

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


def _migrate_storage_state(context: BrowserContext, state: Path) -> None:
    """把旧版 storage_state 显式导入持久化 context。

    Playwright 的 ``launch_persistent_context`` 不接受 ``storage_state`` 参数，
    因此 cookies 需用 API 导入，localStorage 则在对应 origin 页面中写入。
    """
    try:
        payload: dict[str, Any] = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"微信公众号旧登录态无法读取：{state}") from exc

    cookies = payload.get("cookies") or []
    if cookies:
        context.add_cookies(cookies)

    for origin_state in payload.get("origins") or []:
        origin = str(origin_state.get("origin") or "").rstrip("/")
        items = origin_state.get("localStorage") or []
        if not origin or not items:
            continue
        page = context.new_page()
        try:
            page.goto(origin, wait_until="domcontentloaded", timeout=15000)
            page.evaluate(
                "items => items.forEach(item => localStorage.setItem(item.name, item.value))",
                items,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("迁移微信公众号 localStorage 失败（%s）：%s", origin, exc)
        finally:
            with contextlib.suppress(Exception):
                page.close()


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
    migrate_state = bool(state and state.is_file() and not profile_has_state(profile))
    if migrate_state:
        log.info("公众号持久化 profile 尚未初始化，将从登录态迁移：%s", state)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            user_agent=_UA,
            viewport={"width": viewport_width, "height": viewport_height},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            if migrate_state and state is not None:
                _migrate_storage_state(context, state)
            yield context
        finally:
            with contextlib.suppress(Exception):
                context.close()


def save_storage_state(context: BrowserContext, storage_state: Path) -> None:
    """保留一份可迁移/排障的 storage_state 备份。"""
    path = _project_path(storage_state)
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
