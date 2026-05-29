"""知乎树洞圈子发布：复用 storage_state，打开圈子页 → 点'发想法' → 填标题+正文 → 上传图 → 点'发布'。

知乎想法编辑器结构（2026-05 实测）：
- 触发按钮：text=发想法（右上角绿色按钮）
- 模态框打开后：
    * 标题：textarea[placeholder='标题']
    * 正文：div.public-DraftEditor-content (contenteditable)
    * 图片：input[type=file]（隐藏，可直接 set_input_files）
    * 发布：button:has-text('发布') （初始 disabled）

每步都截图到 debug/ 便于排查。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    BrowserContext,
    Locator,
    Page,
    sync_playwright,
)

from .utils import DEBUG_DIR, get_logger, load_config

log = get_logger("publisher")


def _shot(page: Page, name: str) -> None:
    try:
        path = DEBUG_DIR / f"publish_{int(time.time())}_{name}.png"
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


def _dismiss_toasts(page: Page) -> None:
    """关掉模态框上方可能出现的'想法已支持云端草稿'等提示。"""
    for sel in ("button:has-text('知道了')", "div:has-text('知道了')"):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=1500)
                log.info("已关闭顶部提示")
                page.wait_for_timeout(400)
                return
        except Exception:
            continue


def _open_composer(page: Page) -> bool:
    """点击右上角'发想法'按钮，等待模态出现。"""
    # 知乎页面里只有一个文本节点写着'发想法'（在右上角按钮里），
    # 用 text= 选最外层 visible，再走父元素点击更稳。
    locator = page.locator("text=发想法").first
    try:
        locator.wait_for(state="visible", timeout=8000)
    except Exception:
        return False
    try:
        locator.click(timeout=4000)
    except Exception:
        locator.click(force=True, timeout=4000)
    # 等模态加载
    try:
        page.locator("textarea[placeholder='标题']").wait_for(state="visible", timeout=8000)
        return True
    except Exception:
        return False


def _fill_title(page: Page, title: str) -> bool:
    try:
        ta = page.locator("textarea[placeholder='标题']").first
        ta.click(timeout=3000)
        ta.fill("")
        ta.type(title, delay=10)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("填标题失败：%s", e)
        return False


def _fill_body(page: Page, body: str) -> bool:
    """正文是 Draft.js contenteditable，必须用 click+type 走真实键盘事件。"""
    try:
        ed = page.locator("div.public-DraftEditor-content").first
        ed.click(timeout=3000)
        page.wait_for_timeout(200)
        # Draft.js 不识别 \n 换行符，要按 Enter
        for i, line in enumerate(body.split("\n")):
            if i > 0:
                page.keyboard.press("Enter")
            if line:
                page.keyboard.type(line, delay=6)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("填正文失败：%s", e)
        return False


def _upload_image(page: Page, image_path: Path) -> bool:
    """模态框里有一个隐藏的 input[type=file][multiple]，直接 set_input_files 即可。"""
    try:
        # 模态可能有多个 file input，取最后一个（最近渲染的，对应当前 composer）
        inputs = page.locator("input[type='file']")
        n = inputs.count()
        if n == 0:
            log.warning("未找到 file input")
            return False
        inputs.nth(n - 1).set_input_files(str(image_path))
        log.info("已选择图片：%s", image_path)
        # 等图缩略图出现
        page.wait_for_timeout(5000)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("上传图片异常：%s", e)
        return False


def _click_publish(page: Page) -> bool:
    """等到发布按钮 enable 后点击。"""
    end = time.time() + 8
    btn: Optional[Locator] = None
    while time.time() < end:
        try:
            cand = page.locator("button:has-text('发布'):not(:disabled)")
            if cand.count() and cand.first.is_visible():
                btn = cand.first
                break
        except Exception:
            pass
        page.wait_for_timeout(300)
    if btn is None:
        log.warning("发布按钮一直 disabled，可能内容为空")
        return False
    try:
        btn.click(timeout=5000)
    except Exception:
        btn.click(force=True, timeout=5000)
    return True


def publish(
    title: str,
    body: str,
    image_path: Optional[Path] = None,
    *,
    dry_run: bool = False,
) -> bool:
    """发布一条想法到圈子。"""
    cfg = load_config()
    storage_state = Path(cfg["zhihu"]["storage_state"])
    ring_url = cfg["zhihu"]["ring_url"]

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
        log.info("打开圈子页：%s", ring_url)
        page.goto(ring_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3500)

        if not _ensure_logged_in(context, page):
            _shot(page, "not_logged_in")
            browser.close()
            raise RuntimeError("登录态失效，请重新运行：python scripts/login.py")

        _shot(page, "01_ring_loaded")

        # 1. 打开 composer
        if not _open_composer(page):
            _shot(page, "02_open_composer_failed")
            browser.close()
            raise RuntimeError("无法打开'发想法'编辑器，已截图")
        page.wait_for_timeout(800)
        _dismiss_toasts(page)
        _shot(page, "03_composer_opened")

        # 2. 填标题
        if not _fill_title(page, title):
            _shot(page, "04_title_failed")
            browser.close()
            raise RuntimeError("标题输入失败")
        _shot(page, "04_title_typed")

        # 3. 填正文
        if not _fill_body(page, body):
            _shot(page, "05_body_failed")
            browser.close()
            raise RuntimeError("正文输入失败")
        _shot(page, "05_body_typed")

        # 4. 上传图（可选）
        if image_path is not None and Path(image_path).exists():
            ok = _upload_image(page, Path(image_path))
            _shot(page, "06_image_" + ("uploaded" if ok else "failed"))

        # 5. 发布
        if dry_run:
            log.info("dry_run=True，不点发布。")
            _shot(page, "07_dry_run_final")
            browser.close()
            return True

        if not _click_publish(page):
            _shot(page, "07_publish_btn_disabled")
            browser.close()
            raise RuntimeError("发布按钮始终未启用")
        page.wait_for_timeout(4000)
        _shot(page, "08_after_publish")

        # 简单成功判定
        try:
            if page.locator(":text('发布成功'), :text('已发布')").count() > 0:
                log.info("检测到'发布成功'提示")
        except Exception:
            pass

        # 顺手刷新登录态
        try:
            context.storage_state(path=str(storage_state))
        except Exception:
            pass
        log.info("发布流程结束")
        browser.close()
        return True
