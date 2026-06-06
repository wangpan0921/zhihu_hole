"""知乎私信：复用 storage_state，打开目标用户主页 → 点'发私信' → 填消息 → 发送。

用于「书籍池全部读完」后给运营者本人发一条提醒私信。

知乎私信入口（2026 实测，DOM 可能随版本变动）：
- 用户主页右上角有「发私信」按钮（文本 = 发私信）
- 点开后弹出聊天面板，里面是一个 contenteditable / textarea 输入框
- 回车或点「发送」按钮发出

配置（config.yaml）：
    zhihu:
      # 收私信的目标用户主页 URL（运营者本人）。留空则跳过发私信。
      notify_people_url: "https://www.zhihu.com/people/<urlToken>"

每步都截图到 debug/ 便于排查。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .utils import DEBUG_DIR, get_logger, load_config

log = get_logger("messenger")

# 「发私信」入口按钮候选 selector
OPEN_CHAT_SELECTORS = (
    "button:has-text('发私信')",
    "a:has-text('发私信')",
    "text=发私信",
)

# 私信输入框候选 selector
INPUT_SELECTORS = (
    "div[contenteditable='true']",
    "textarea[placeholder*='私信']",
    "textarea",
)

# 发送按钮候选 selector
SEND_SELECTORS = (
    "button:has-text('发送')",
    "button:has-text('发送私信')",
)


def _shot(page: Page, name: str) -> None:
    try:
        path = DEBUG_DIR / f"dm_{int(time.time())}_{name}.png"
        page.screenshot(path=str(path), full_page=True)
        log.info("调试截图：%s", path)
    except Exception as e:  # noqa: BLE001
        log.warning("截图失败：%s", e)


def _ensure_logged_in(context: BrowserContext, page: Page) -> bool:
    cookies = context.cookies()
    if any(c.get("name") == "z_c0" for c in cookies):
        return True
    try:
        return page.locator(".AppHeader-userInfo, .Avatar").count() > 0
    except Exception:
        return False


def _click_first(page: Page, selectors: tuple[str, ...], *, timeout: int = 6000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            try:
                loc.click(timeout=3000)
            except Exception:
                loc.click(force=True, timeout=3000)
            log.info("点击成功：%s", sel)
            return True
        except Exception:
            continue
    return False


def _fill_message(page: Page, message: str) -> bool:
    for sel in INPUT_SELECTORS:
        try:
            box = page.locator(sel).last
            if box.count() == 0:
                continue
            box.click(timeout=3000)
            page.wait_for_timeout(200)
            box.type(message, delay=8)
            log.info("已填入私信内容（selector=%s）", sel)
            return True
        except Exception:
            continue
    log.warning("没找到可用的私信输入框")
    return False


def send_private_message(message: str, *, dry_run: bool = False) -> bool:
    """给 config.zhihu.notify_people_url 指向的用户发一条私信。

    返回 True 表示成功（dry_run 也算成功）；
    若未配置 notify_people_url 则记录日志并返回 False（视为跳过，不报错）。
    """
    cfg = load_config()
    zcfg = cfg.get("zhihu", {})
    people_url = (zcfg.get("notify_people_url") or "").strip()
    if not people_url:
        log.warning("未配置 zhihu.notify_people_url，跳过发私信")
        return False

    storage_state = Path(zcfg["storage_state"])
    if not storage_state.exists():
        raise RuntimeError(
            f"未找到登录态文件 {storage_state}，请先运行：python scripts/login.py"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(storage_state),
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()
        log.info("打开目标用户主页：%s", people_url)
        page.goto(people_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        if not _ensure_logged_in(context, page):
            _shot(page, "not_logged_in")
            browser.close()
            raise RuntimeError("登录态失效，请重新运行：python scripts/login.py")

        _shot(page, "01_people_loaded")

        if not _click_first(page, OPEN_CHAT_SELECTORS):
            _shot(page, "02_open_chat_failed")
            browser.close()
            raise RuntimeError("找不到'发私信'入口，已截图")
        page.wait_for_timeout(1200)
        _shot(page, "03_chat_opened")

        if not _fill_message(page, message):
            _shot(page, "04_fill_failed")
            browser.close()
            raise RuntimeError("私信输入框填写失败")
        _shot(page, "04_message_typed")

        if dry_run:
            log.info("dry_run=True，不真正发送私信。")
            _shot(page, "05_dry_run_final")
            browser.close()
            return True

        # 优先点「发送」按钮，没有就回车
        if not _click_first(page, SEND_SELECTORS, timeout=2000):
            log.info("未找到发送按钮，改用回车发送")
            try:
                page.keyboard.press("Enter")
            except Exception as e:  # noqa: BLE001
                _shot(page, "05_send_failed")
                browser.close()
                raise RuntimeError(f"发送私信失败：{e}")
        page.wait_for_timeout(2500)
        _shot(page, "06_after_send")

        # 顺手刷新登录态
        try:
            context.storage_state(path=str(storage_state))
        except Exception:
            pass
        log.info("私信发送流程结束")
        browser.close()
        return True
