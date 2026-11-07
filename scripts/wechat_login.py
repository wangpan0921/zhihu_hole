#!/usr/bin/env python3
"""微信公众号后台登录入口。

默认打开有头浏览器，手机扫码登录后保存持久化 profile，并同步备份
data/auth/wechat_mp_state.json。
服务器无图形界面时可加 --headless，脚本会保存 debug/wechat_login_qr.png 供扫码。
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import DEBUG_DIR, get_logger, load_config  # noqa: E402
from src.wechat_browser import browser_context, save_storage_state  # noqa: E402

log = get_logger("wechat_login")


def _decode_qr_from_image(png_bytes: bytes) -> str | None:
    """从截图中解码二维码内容。"""
    try:
        from pyzbar.pyzbar import decode
    except ImportError as exc:
        log.error("pyzbar 未安装：%s（系统需要 libzbar0）", exc)
        return None

    try:
        image = Image.open(io.BytesIO(png_bytes))
        image = image.resize((image.width * 2, image.height * 2))
        results = decode(image)
    except Exception as exc:  # noqa: BLE001
        log.debug("二维码截图解码失败：%s", exc)
        return None
    if not results:
        return None
    return results[0].data.decode("utf-8", errors="ignore")


def _print_qr_in_terminal(data: str) -> None:
    """把二维码内容重新渲染为 SSH 终端可扫描的 Unicode 块。"""
    import qrcode

    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    qr.print_ascii(out=sys.stdout, tty=False, invert=True)
    print(f"\n二维码内容：{data}\n")


def _try_capture_qr(page: Page) -> tuple[str | None, bytes | None]:
    """从公众号登录页抓取二维码，返回二维码内容和原始截图。"""
    candidates = [
        ".login_qrcode",
        ".login-qrcode",
        ".qrcode",
        "#qrcode",
        "canvas",
        "img[src*='qrcode']",
        "img[alt*='二维码']",
    ]
    for selector in candidates:
        try:
            element = page.locator(selector).first
            if element.count() == 0:
                continue
            element.wait_for(state="visible", timeout=1500)
            png = element.screenshot()
            data = _decode_qr_from_image(png)
            if data:
                log.info("通过 selector %s 拿到公众号登录二维码", selector)
                return data, png
        except Exception:
            continue

    png = page.screenshot(full_page=False)
    return _decode_qr_from_image(png), png


def login_wechat_mp(*, headless: bool = False) -> Path:
    cfg = load_config()
    mp_cfg = cfg.get("wechat_mp") or {}
    storage_path = Path(mp_cfg.get("storage_state", "data/auth/wechat_mp_state.json"))
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    profile_dir = Path(mp_cfg.get("profile_dir", "data/auth/wechat_mp_chrome_profile"))
    with browser_context(
        storage_state=storage_path,
        profile_dir=profile_dir,
        headless=headless,
        viewport_width=1280,
        viewport_height=900,
    ) as context:
        page = context.new_page()
        page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        if not headless:
            print("请在打开的 Chromium 窗口中扫码登录微信公众号后台。")

        raw_qr_path = DEBUG_DIR / "wechat_login_qr.png"
        deadline = time.time() + 300
        logged_in = False
        last_qr: str | None = None
        shown_qr = False
        while time.time() < deadline:
            try:
                if headless:
                    qr_data, qr_png = _try_capture_qr(page)
                    if qr_data and qr_data != last_qr:
                        last_qr = qr_data
                        if qr_png:
                            raw_qr_path.write_bytes(qr_png)
                        if shown_qr:
                            print("\n[公众号登录二维码已刷新，请扫描下面这张最新二维码]\n")
                        else:
                            print("\n========== 请用微信扫描下方二维码登录公众号 ==========")
                            print(f"（原始二维码图已保存：{raw_qr_path}）\n")
                            shown_qr = True
                        _print_qr_in_terminal(qr_data)
                        print("====================================================\n")
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
            if headless and not shown_qr:
                shot = DEBUG_DIR / "wechat_login_debug.png"
                page.screenshot(path=str(shot), full_page=True)
                raise RuntimeError(
                    "未能从公众号登录页解出二维码，"
                    f"已保存调试截图：{shot}"
                )
            raise TimeoutError("微信公众号扫码登录超时")

        page.wait_for_timeout(2000)
        save_storage_state(context, storage_path)
        log.info("微信公众号登录态已保存：%s", storage_path)
        return storage_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式，在终端显示二维码并保存原始截图",
    )
    args = parser.parse_args()
    login_wechat_mp(headless=args.headless)
