"""微信读书登录：headless 浏览器抓登录二维码 → 终端渲染供手机扫码 → 保存 storage_state。

工作流：
1. Playwright headless 打开 https://weread.qq.com/
2. 点击右上「登录」按钮，等模态框中的二维码出现
3. 截图 canvas/img，pyzbar 解码出 URL，再用 qrcode 库在终端重画
4. 轮询 cookie，看到 wr_skey + wr_vid 即视为登录成功，保存 storage_state.json

注：微信读书的二维码必须用「微信」扫码（不是微信读书 App），扫完手机上点确认即可。
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

from .utils import AUTH_DIR, DEBUG_DIR, get_logger, load_config

log = get_logger("weread_login")

HOME_URL = "https://weread.qq.com/"
LOGIN_TIMEOUT_SEC = 300  # 5 分钟扫码超时

# 登录成功的 cookie 标志：这两个同时存在基本就 OK
LOGIN_COOKIE_KEYS = ("wr_skey", "wr_vid")


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
    """把 URL 字符串重新渲染为终端 Unicode 二维码。"""
    import qrcode

    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    qr.print_ascii(out=sys.stdout, tty=False, invert=True)
    print(f"\n二维码内容：{data}\n")


def _open_login_modal(page: Page) -> None:
    """点击右上角「登录」按钮，把扫码模态框唤起来。

    微信读书首页右上一般直接显示「登录」文字按钮；如果改版了就尝试一些备用 selector。
    """
    candidates = [
        "text=登录",
        "button:has-text('登录')",
        "a:has-text('登录')",
        ".navBar_link_Login",
        ".navBar_link.navBar_link_Login",
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            loc.click(timeout=3000)
            log.info("点击登录按钮：%s", sel)
            return
        except Exception:
            continue
    # 都没点到也不报错——可能页面本来就直接展示二维码
    log.info("未找到明确的「登录」按钮，跳过点击；继续找二维码")


def _try_capture_qr(page: Page) -> tuple[str | None, bytes | None]:
    """尝试从页面抓二维码。返回 (二维码内容, 二维码原始 png)。"""
    candidates = [
        ".login_dialog_qrcode canvas",
        ".login_dialog canvas",
        ".wr_dialog canvas",
        ".dialog_content canvas",
        "canvas",
        "img[src*='qrcode']",
        "img[alt*='二维码']",
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
                return data, png
        except Exception:
            continue

    # 兜底：截当前视口找二维码
    png = page.screenshot(full_page=False)
    return _decode_qr_from_image(png), png


def _is_logged_in(context) -> bool:
    cookies = context.cookies()
    names = {c.get("name") for c in cookies}
    return all(k in names for k in LOGIN_COOKIE_KEYS)


def login_interactive(headful: bool = False) -> Path:
    """终端引导扫码登录微信读书，保存 storage_state。

    headful=True 时弹有头浏览器（本地 X 调试用）。
    """
    cfg = load_config()
    storage_path = Path(cfg["weread"]["storage_state"])
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
        log.info("打开微信读书首页：%s", HOME_URL)
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)

        # 已经登录过（极少见，但 storage_state 复用时会出现）
        if _is_logged_in(context):
            log.info("检测到已登录，直接保存 storage_state")
            context.storage_state(path=str(storage_path))
            browser.close()
            return storage_path

        _open_login_modal(page)
        page.wait_for_timeout(2500)

        qr_data: str | None = None
        qr_png: bytes | None = None

        # 微信读书的扫码二维码会每隔约 20~60 秒自动轮换，过期的旧码扫出来就是
        # 「二维码失效」。所以这里不再「抓一次静态渲染后干等」，而是在等待扫码的
        # 整个过程里持续重新抓取页面上的实时二维码：内容一变就重画终端二维码、
        # 刷新 debug/weread_qr_raw.png，保证你看到/扫到的始终是当前有效的那张。
        shot_raw = DEBUG_DIR / "weread_qr_raw.png"
        last_qr: str | None = None
        shown_once = False
        no_qr_streak = 0

        log.info("等待扫码确认（最长 %d 秒），二维码会自动刷新...", LOGIN_TIMEOUT_SEC)
        deadline = time.time() + LOGIN_TIMEOUT_SEC
        logged_in = False
        while time.time() < deadline:
            if _is_logged_in(context):
                logged_in = True
                break

            qr_data, qr_png = _try_capture_qr(page)
            if qr_data:
                no_qr_streak = 0
                if qr_data != last_qr:
                    last_qr = qr_data
                    if qr_png:
                        shot_raw.write_bytes(qr_png)
                    if not shown_once:
                        print(
                            "\n========== 请用「微信」扫描下方二维码，再在手机上点确认登录 =========="
                        )
                        print("（二维码会自动刷新，始终扫终端里最新的这张；也可打开 "
                              f"{shot_raw} 用图片查看器扫）\n")
                        shown_once = True
                    else:
                        print("\n[二维码已刷新，请扫下面这张最新的]\n")
                    _print_qr_in_terminal(qr_data)
                    print(
                        "===============================================================\n"
                    )
            else:
                # 偶发没抓到（刷新间隙）不立刻报错，连续多次才判定失败
                no_qr_streak += 1
                if no_qr_streak == 1 and not shown_once:
                    shot = DEBUG_DIR / "weread_login_debug.png"
                    page.screenshot(path=str(shot), full_page=True)
                    log.info("暂未抓到二维码，已存调试截图 %s，继续重试…", shot)

            page.wait_for_timeout(2000)

        if not logged_in:
            if not shown_once:
                browser.close()
                raise RuntimeError(
                    "始终未能从微信读书登录页解出二维码（可能登录按钮/selector 变了），"
                    f"调试截图见 {DEBUG_DIR}/weread_login_debug.png"
                )
            browser.close()
            raise TimeoutError("扫码超时未登录")

        # 让登录回调跑完再保存
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
