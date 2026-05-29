"""知乎登录：headless 浏览器抓登录页二维码 → 终端渲染供手机扫码 → 保存 storage_state。

工作流：
1. Playwright headless 打开 https://www.zhihu.com/signin
2. 等二维码出现，截图二维码 DOM
3. pyzbar 解码出 URL，再用 qrcode 库在终端打印 Unicode 块
4. 轮询页面 URL，登录成功后保存 storage_state.json
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

from .utils import AUTH_DIR, DEBUG_DIR, get_logger, load_config

log = get_logger("login")

LOGIN_URL = "https://www.zhihu.com/signin"
# 登录成功后的判定：URL 不再是 signin
LOGIN_TIMEOUT_SEC = 300  # 5 分钟扫码超时


def _decode_qr_from_image(png_bytes: bytes) -> str | None:
    """从 png 字节里解码二维码内容。"""
    try:
        from pyzbar.pyzbar import decode
    except ImportError as e:
        log.error("pyzbar 未安装：%s（系统需要 libzbar0）", e)
        return None

    img = Image.open(io.BytesIO(png_bytes))
    # 放大有助于解码
    img = img.resize((img.width * 2, img.height * 2))
    results = decode(img)
    if not results:
        return None
    return results[0].data.decode("utf-8", errors="ignore")


def _print_qr_in_terminal(data: str) -> None:
    """把 URL 字符串重渲染为终端 Unicode 二维码。"""
    import qrcode

    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    # print_ascii 输出在 SSH 终端里更兼容
    qr.print_ascii(out=sys.stdout, tty=False, invert=True)
    print(f"\n二维码内容：{data}\n")


def _try_capture_qr(page: Page) -> str | None:
    """尝试从页面抓二维码。返回二维码内容字符串，失败返回 None。"""
    # 知乎登录页二维码可能在 canvas 或 img 里。穷举几种 selector。
    candidates = [
        ".SignContainer-content .Qrcode",
        ".SignContainer .Qrcode",
        ".Qrcode",
        "canvas",
        "img[alt*='二维码']",
        "img[src*='qrcode']",
    ]
    for sel in candidates:
        try:
            el = page.locator(sel).first
            if el.count() == 0:
                continue
            el.wait_for(state="visible", timeout=3000)
            png = el.screenshot()
            data = _decode_qr_from_image(png)
            if data:
                log.info("通过 selector %s 拿到二维码", sel)
                return data
        except Exception:
            continue

    # 兜底：截整页找二维码
    png = page.screenshot(full_page=False)
    return _decode_qr_from_image(png)


def login_interactive(headful: bool = False) -> Path:
    """在终端引导扫码登录，保存 storage_state。

    headful: 如果你本机有显示且想直接弹窗扫码，可以传 True。
    服务器场景默认 False（headless + 终端 QR）。
    """
    cfg = load_config()
    storage_path = Path(cfg["zhihu"]["storage_state"])
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = context.new_page()
        log.info("打开知乎登录页：%s", LOGIN_URL)
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        # 知乎默认就是二维码登录；若不是则尝试切到二维码 tab
        try:
            tab = page.get_by_text("二维码登录", exact=False)
            if tab.count() > 0:
                tab.first.click(timeout=2000)
        except Exception:
            pass

        # 等几秒让二维码加载
        page.wait_for_timeout(3000)

        qr_data: str | None = None
        for attempt in range(5):
            qr_data = _try_capture_qr(page)
            if qr_data:
                break
            log.info("第 %d 次未抓到二维码，等待再试…", attempt + 1)
            page.wait_for_timeout(2000)

        if not qr_data:
            shot = DEBUG_DIR / "login_debug.png"
            page.screenshot(path=str(shot), full_page=True)
            browser.close()
            raise RuntimeError(
                f"未能从知乎登录页解出二维码，已保存调试截图：{shot}\n"
                f"可能页面结构变了，请查看截图调整 selector。"
            )

        print("\n========== 请用手机知乎 App 扫描下方二维码 ==========\n")
        _print_qr_in_terminal(qr_data)
        print("==================================================\n")
        print("（如果终端二维码扫描有困难，可以打开 debug/qr_raw.png）")

        # 保留原始二维码图（手机直接看）
        try:
            (DEBUG_DIR / "qr_raw.png").write_bytes(
                page.locator(".Qrcode, canvas").first.screenshot()
            )
        except Exception:
            pass

        # 等待登录成功
        log.info("等待扫码确认（最长 %d 秒）...", LOGIN_TIMEOUT_SEC)
        deadline = time.time() + LOGIN_TIMEOUT_SEC
        logged_in = False
        while time.time() < deadline:
            try:
                # 已登录后会跳到首页或 'signin' 退出
                cur = page.url
                if "signin" not in cur:
                    logged_in = True
                    break
                # 也可以查 cookie 中的 z_c0
                cookies = context.cookies()
                if any(c.get("name") == "z_c0" for c in cookies):
                    logged_in = True
                    break
            except Exception:
                pass
            page.wait_for_timeout(2000)

        if not logged_in:
            browser.close()
            raise TimeoutError("扫码超时未登录")

        # 让页面稳定一下再保存
        page.wait_for_timeout(2000)
        context.storage_state(path=str(storage_path))
        log.info("登录态已保存：%s", storage_path)
        browser.close()
        return storage_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--headful", action="store_true", help="弹出有头浏览器（本地调试用）")
    args = parser.parse_args()
    login_interactive(headful=args.headful)
