"""平台登录抽象基类。

把"打开登录页 → 展示二维码 → 轮询登录成功 → 保存 storage_state"的通用流程
固化在这里，各平台只需实现差异点：登录 URL、登录成功判定、登录态文件名、
（可选）二维码定位与登录前的页面准备。

扩展新平台：继承 PlatformLogin，实现 abstract 成员，再到 registry.py 登记。
"""
from __future__ import annotations

import abc
import io
import sys
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Page

from ..logging_utils import get_logger
from ..paths import AUTH_DIR, DEBUG_DIR
from ..browser import browser_context

log = get_logger("login")

# 二维码可能出现的通用候选选择器，子类可覆盖/追加
_DEFAULT_QR_SELECTORS = (
    ".Qrcode",
    "canvas",
    "img[alt*='二维码']",
    "img[src*='qrcode']",
    "img[src*='qr']",
)


class PlatformLogin(abc.ABC):
    """单个平台的登录器。"""

    #: 平台标识，如 "zhihu"
    name: str = ""

    #: storage_state 文件名（存到 data/auth/ 下）
    storage_filename: str = ""

    #: 扫码超时秒数
    login_timeout_sec: int = 300

    #: 二维码候选选择器
    qr_selectors: tuple[str, ...] = _DEFAULT_QR_SELECTORS

    @property
    @abc.abstractmethod
    def login_url(self) -> str:
        """登录页 URL。"""

    @abc.abstractmethod
    def is_logged_in(self, page: Page, context: BrowserContext) -> bool:
        """根据当前 URL / cookie 判定是否登录成功。"""

    # --- 可选覆盖的钩子 ---

    def prepare_login_page(self, page: Page) -> None:
        """登录前的页面准备（如切到"二维码登录"tab）。默认空实现。"""

    # --- 通用能力 ---

    @property
    def storage_path(self) -> Path:
        if not self.storage_filename:
            raise ValueError(f"{self.name}: storage_filename 未设置")
        return AUTH_DIR / self.storage_filename

    def logged_in(self) -> bool:
        """用已保存的登录态静默校验是否仍有效。"""
        if not self.storage_path.exists():
            return False
        try:
            with browser_context(storage_state=self.storage_path, headless=True) as ctx:
                page = ctx.new_page()
                page.goto(self.login_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)
                return self.is_logged_in(page, ctx)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s 登录态校验失败：%s", self.name, exc)
            return False

    def login_interactive(self, *, headful: bool = True) -> Path:
        """扫码登录并保存 storage_state。本机建议 headful=True 直接弹窗扫码。"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with browser_context(headless=not headful) as context:
            page = context.new_page()
            log.info("[%s] 打开登录页：%s", self.name, self.login_url)
            page.goto(self.login_url, wait_until="domcontentloaded", timeout=30000)
            self.prepare_login_page(page)
            page.wait_for_timeout(3000)

            if not headful:
                self._emit_terminal_qr(page)
            else:
                print(f"请在打开的浏览器窗口中扫码登录【{self.name}】。")

            if not self._wait_until_logged_in(page, context):
                raise TimeoutError(f"[{self.name}] 扫码登录超时")

            page.wait_for_timeout(2000)
            context.storage_state(path=str(self.storage_path))
            log.info("[%s] 登录态已保存：%s", self.name, self.storage_path)
            return self.storage_path

    def _wait_until_logged_in(self, page: Page, context: BrowserContext) -> bool:
        deadline = time.time() + self.login_timeout_sec
        while time.time() < deadline:
            try:
                if self.is_logged_in(page, context):
                    return True
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2000)
        return False

    def _emit_terminal_qr(self, page: Page) -> None:
        """无头模式下：抓二维码 → 终端渲染 + 保存图片供扫码。"""
        data = self._capture_qr(page)
        shot = DEBUG_DIR / f"{self.name}_login_qr.png"
        try:
            page.screenshot(path=str(shot), full_page=True)
        except Exception:  # noqa: BLE001
            pass
        if data:
            self._print_qr(data)
            print(f"\n（也可打开截图扫码：{shot}）\n")
        else:
            print(f"未能解出二维码，请打开截图手动扫码：{shot}")

    def _capture_qr(self, page: Page) -> str | None:
        for sel in self.qr_selectors:
            try:
                el = page.locator(sel).first
                if el.count() == 0:
                    continue
                el.wait_for(state="visible", timeout=3000)
                data = self._decode_qr(el.screenshot())
                if data:
                    log.info("[%s] 通过 selector %s 拿到二维码", self.name, sel)
                    return data
            except Exception:  # noqa: BLE001
                continue
        try:
            return self._decode_qr(page.screenshot(full_page=False))
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _decode_qr(png_bytes: bytes) -> str | None:
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode
        except ImportError as exc:  # noqa: BLE001
            log.error("二维码解码依赖缺失（Pillow/pyzbar，需 libzbar0）：%s", exc)
            return None
        img = Image.open(io.BytesIO(png_bytes))
        img = img.resize((img.width * 2, img.height * 2))
        results = decode(img)
        return results[0].data.decode("utf-8", errors="ignore") if results else None

    @staticmethod
    def _print_qr(data: str) -> None:
        try:
            import qrcode
        except ImportError:
            print(f"二维码内容（请手动打开）：{data}")
            return
        qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(data)
        qr.make(fit=True)
        qr.print_ascii(out=sys.stdout, tty=False, invert=True)
        print(f"\n二维码内容：{data}\n")
