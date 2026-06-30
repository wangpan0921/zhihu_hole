#!/usr/bin/env python3
"""微信公众号后台登录入口。

默认打开有头浏览器，手机扫码登录后保存 data/auth/wechat_mp_state.json。
服务器无图形界面时可加 --headless，脚本会保存 debug/wechat_login_qr.png 供扫码。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from src.utils import DEBUG_DIR, get_logger, load_config  # noqa: E402

log = get_logger("wechat_login")


def login_wechat_mp(*, headless: bool = False) -> Path:
    cfg = load_config()
    mp_cfg = cfg.get("wechat_mp") or {}
    storage_path = Path(mp_cfg.get("storage_state", "data/auth/wechat_mp_state.json"))
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        if headless:
            shot = DEBUG_DIR / "wechat_login_qr.png"
            page.screenshot(path=str(shot), full_page=True)
            print(f"请打开截图扫码登录：{shot}")
        else:
            print("请在打开的 Chromium 窗口中扫码登录微信公众号后台。")

        deadline = time.time() + 300
        logged_in = False
        while time.time() < deadline:
            try:
                if "cgi-bin/home" in page.url or "token=" in page.url:
                    logged_in = True
                    break
                cookies = context.cookies()
                if any(c.get("name") in {"slave_sid", "bizuin", "data_bizuin"} for c in cookies):
                    logged_in = True
                    break
            except Exception:
                pass
            page.wait_for_timeout(2000)

        if not logged_in:
            browser.close()
            raise TimeoutError("微信公众号扫码登录超时")

        page.wait_for_timeout(2000)
        context.storage_state(path=str(storage_path))
        log.info("微信公众号登录态已保存：%s", storage_path)
        browser.close()
        return storage_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="无头模式，保存二维码截图供扫码")
    args = parser.parse_args()
    login_wechat_mp(headless=args.headless)
