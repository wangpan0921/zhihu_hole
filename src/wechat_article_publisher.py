"""微信公众号文章发布。

用 Playwright 复用微信公众号后台登录态，打开图文编辑器，填标题并把
Markdown 转成带内联样式的 HTML 粘贴到正文编辑区。

微信公众号后台 DOM 经常调整，所以这里尽量使用多组 selector fallback，并在
关键步骤保存 debug/wechat_article_* 截图，便于后续按截图修正。
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

from playwright.sync_api import BrowserContext, Locator, Page, sync_playwright

from .markdown_html import markdown_to_html
from .utils import DEBUG_DIR, get_logger, load_config

log = get_logger("wechat_article_publisher")

MP_HOME_URL = "https://mp.weixin.qq.com/"
DEFAULT_EDIT_PATH = "/cgi-bin/appmsg"


def _shot(page: Page, name: str) -> None:
    try:
        path = DEBUG_DIR / f"wechat_article_{int(time.time())}_{name}.png"
        page.screenshot(path=str(path), full_page=True)
        log.info("调试截图：%s", path)
    except Exception as e:  # noqa: BLE001
        log.warning("截图失败：%s", e)


def _dump_editor_html(page: Page, name: str) -> None:
    try:
        body = _body_locator(page)
        if body is None:
            return
        html = body.evaluate("el => el.innerHTML || ''")
        path = DEBUG_DIR / f"wechat_article_{int(time.time())}_{name}.html"
        path.write_text(html or "", encoding="utf-8")
        log.info("调试 HTML：%s", path)
    except Exception as e:  # noqa: BLE001
        log.warning("HTML 转储失败：%s", e)


def _wechat_template_html(body_html: str) -> str:
    """套一个公众号友好的极简内联样式模板。

    微信编辑器会保留大部分 inline style，但不稳定保留外部 class。这里用 section
    包住正文，并给常见块级元素补上适合公众号阅读的间距、字号和颜色。
    """
    replacements = (
        ("<p>", '<p style="margin:0 0 16px;line-height:1.85;font-size:15px;color:#2b2f36;">'),
        ("<h2>", '<h2 style="margin:28px 0 14px;padding-left:10px;border-left:4px solid #2f80ed;font-size:18px;line-height:1.5;color:#1f2937;font-weight:700;">'),
        ("<h3>", '<h3 style="margin:24px 0 12px;font-size:16px;line-height:1.5;color:#1f2937;font-weight:700;">'),
        ("<ul>", '<ul style="margin:0 0 16px;padding-left:22px;line-height:1.85;font-size:15px;color:#2b2f36;">'),
        ("<ol>", '<ol style="margin:0 0 16px;padding-left:22px;line-height:1.85;font-size:15px;color:#2b2f36;">'),
        ("<li>", '<li style="margin:4px 0;">'),
        ("<blockquote>", '<blockquote style="margin:18px 0;padding:12px 16px;border-left:4px solid #d0d7de;background:#f6f8fa;color:#57606a;line-height:1.8;font-size:14px;">'),
        ("<pre ", '<pre style="margin:18px 0;padding:12px;border-radius:4px;background:#f6f8fa;overflow:auto;line-height:1.65;font-size:13px;color:#24292f;" '),
        ("<strong>", '<strong style="font-weight:700;color:#111827;">'),
    )
    styled = body_html
    for old, new in replacements:
        styled = styled.replace(old, new)
    return (
        '<section style="box-sizing:border-box;margin:0 auto;padding:0 2px;'
        'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,'
        'PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;">'
        f"{styled}"
        "</section>"
    )


def _extract_token(url: str) -> Optional[str]:
    parsed = urlparse(url)
    token = parse_qs(parsed.query).get("token", [None])[0]
    if token:
        return token
    m = re.search(r"[?&]token=(\d+)", url)
    return m.group(1) if m else None


def _build_edit_url(configured_url: str, token: Optional[str]) -> str:
    """构造新建图文链接。

    如果配置里给了完整 appmsg_edit_v2 链接，优先使用；若不含 token，则从首页 URL
    抽到的 token 补进去。公众号后台多数入口都要求 token。
    """
    if configured_url:
        parsed = urlparse(configured_url)
        qs = parse_qs(parsed.query)
        if token:
            qs["token"] = [token]
            qs["timestamp"] = [str(int(time.time() * 1000))]
            query = urlencode(qs, doseq=True)
            return parsed._replace(query=query).geturl()
        return configured_url

    qs = {
        "t": "media/appmsg_edit_v2",
        "action": "edit",
        "isNew": "1",
        "type": "10",
        "lang": "zh_CN",
    }
    if token:
        qs["token"] = token
    return f"https://mp.weixin.qq.com{DEFAULT_EDIT_PATH}?{urlencode(qs)}"


def _ensure_logged_in(context: BrowserContext, page: Page) -> bool:
    cookies = context.cookies()
    if any(c.get("domain", "").endswith("mp.weixin.qq.com") for c in cookies):
        if any(c.get("name") in {"slave_sid", "bizuin", "data_bizuin"} for c in cookies):
            return True
    try:
        if "cgi-bin/loginpage" in page.url or "login" in page.url:
            return False
        for text in ("首页", "新的创作", "素材库"):
            if page.get_by_text(text, exact=False).count() > 0:
                return True
        return False
    except Exception:
        return False


def _title_selector(page: Page) -> Optional[str]:
    selectors = (
        "textarea[placeholder*='标题']",
        "input[placeholder*='标题']",
        "[contenteditable='true'][placeholder*='标题']",
        ".js_title",
        "#title",
    )
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                return sel
        except Exception:
            continue
    return None


def _body_locator(page: Page) -> Optional[Locator]:
    iframe_selectors = (
        "iframe.ueditor_iframe",
        "iframe[id^='ueditor_']",
        "iframe[src*='ueditor']",
    )
    for sel in iframe_selectors:
        try:
            iframe = page.locator(sel).first
            if iframe.count() and iframe.is_visible():
                body = page.frame_locator(sel).locator("body").first
                if body.count() and body.is_visible():
                    return body
        except Exception:
            continue

    selectors = (
        "#ueditor_0",
        ".ProseMirror[contenteditable='true']",
        ".rich_media_content[contenteditable='true']",
        ".edui-editor-body [contenteditable='true']",
        "[contenteditable='true']:not([placeholder*='标题'])",
    )
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _body_selector(page: Page) -> Optional[str]:
    # Backward-compatible helper for readiness checks that only need presence.
    return "body" if _body_locator(page) is not None else None


def _wait_editor_ready(page: Page) -> bool:
    end = time.time() + 30
    while time.time() < end:
        if _title_selector(page) and _body_selector(page):
            return True
        page.wait_for_timeout(500)
    return False


def _fill_title(page: Page, title: str) -> bool:
    sel = _title_selector(page)
    if sel is None:
        log.warning("找不到标题输入框")
        return False
    try:
        loc = page.locator(sel).first
        loc.click(timeout=3000)
        # contenteditable 元素不一定支持 fill，先试 fill，失败再键盘输入。
        try:
            loc.fill("")
            loc.type(title, delay=10)
        except Exception:
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(title, delay=10)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("标题输入失败：%s", e)
        return False


def _paste_html_body(page: Page, body_html: str) -> bool:
    body = _body_locator(page)
    if body is None:
        log.warning("找不到正文编辑器")
        return False
    try:
        body.click(timeout=3000)
        page.wait_for_timeout(300)
    except Exception as e:  # noqa: BLE001
        log.warning("聚焦正文失败：%s", e)
        return False

    js = r"""(htmlText) => {
        const plain = htmlText
            .replace(/<br\s*\/?>(?=)/gi, '\n')
            .replace(/<\/(p|li|h2|h3|blockquote|pre|section)>/gi, '\n')
            .replace(/<[^>]+>/g, '');
        try {
            const item = new ClipboardItem({
                'text/html': new Blob([htmlText], { type: 'text/html' }),
                'text/plain': new Blob([plain], { type: 'text/plain' }),
            });
            return navigator.clipboard.write([item])
                .then(() => ({ ok: true }))
                .catch((e) => ({ ok: false, reason: String(e) }));
        } catch (e) {
            return Promise.resolve({ ok: false, reason: String(e) });
        }
    }"""
    try:
        r = page.evaluate(js, body_html)
    except Exception as e:  # noqa: BLE001
        log.warning("写剪贴板失败：%s", e)
        return False
    if not (isinstance(r, dict) and r.get("ok")):
        log.warning("写剪贴板未成功：%s", r)
        return False

    try:
        body.click(timeout=3000)
        page.keyboard.press("Control+V")
    except Exception as e:  # noqa: BLE001
        log.warning("粘贴正文失败：%s", e)
        return False
    page.wait_for_timeout(2500)

    try:
        length = body.evaluate("el => (el.textContent || '').length")
    except Exception:
        length = 0
    log.info("HTML 粘贴后编辑器内 %d 字", length)
    return length > 50


def _click_button_by_text(page: Page, texts: tuple[str, ...]) -> bool:
    for text in texts:
        for sel in (
            f"button:has-text('{text}')",
            f"a:has-text('{text}')",
            f"span:has-text('{text}')",
            f"div[role='button']:has-text('{text}')",
        ):
            try:
                cand = page.locator(sel)
                for i in range(cand.count()):
                    btn = cand.nth(i)
                    if btn.is_visible() and btn.is_enabled():
                        btn.click(timeout=3000)
                        log.info("已点击按钮：%s", text)
                        return True
            except Exception:
                continue
    return False


def _perform_action(page: Page, action: str) -> bool:
    if action == "draft":
        return _click_button_by_text(page, ("保存为草稿", "保存", "存草稿"))
    if action == "publish":
        clicked = _click_button_by_text(page, ("发表", "发布", "群发"))
        if not clicked:
            return False
        page.wait_for_timeout(1200)
        # 兼容二次确认按钮；没有弹窗则继续。
        _click_button_by_text(page, ("继续发表", "确定", "确认", "发表"))
        return True
    raise ValueError(f"未知 wechat_mp.publish_action：{action}")


def publish_wechat_article(
    title: str,
    body_md: str,
    *,
    dry_run: bool = False,
) -> Optional[str]:
    """发布一篇微信公众号文章。

    dry_run=True 时只填入编辑器，不点击保存/发表，并返回当前编辑页 URL。
    """
    cfg = load_config()
    mp_cfg = cfg.get("wechat_mp") or {}
    storage_state = Path(mp_cfg.get("storage_state", "data/auth/wechat_mp_state.json"))
    configured_url = str(mp_cfg.get("edit_url") or "")
    publish_action = str(mp_cfg.get("publish_action") or "publish")

    if not storage_state.exists():
        raise RuntimeError(
            f"未找到微信公众号登录态 {storage_state}，请先运行：python scripts/wechat_login.py"
        )

    body_html = _wechat_template_html(markdown_to_html(body_md))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(storage_state),
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1000},
            locale="zh-CN",
        )
        try:
            context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://mp.weixin.qq.com",
            )
        except Exception:
            pass

        page = context.new_page()
        page.goto(MP_HOME_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
        if not _ensure_logged_in(context, page):
            _shot(page, "00_not_logged_in")
            browser.close()
            raise RuntimeError("微信公众号登录态失效，请重新运行：python scripts/wechat_login.py")

        token = _extract_token(page.url)
        edit_url = _build_edit_url(configured_url, token)
        log.info("打开微信公众号图文编辑器：%s", edit_url)
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        if not _wait_editor_ready(page):
            _shot(page, "01_editor_not_ready")
            browser.close()
            raise RuntimeError("微信公众号编辑器未就绪，请看 debug 截图调整 selector")
        _shot(page, "01_editor_ready")

        if not _fill_title(page, title):
            _shot(page, "02_title_failed")
            browser.close()
            raise RuntimeError("微信公众号标题输入失败")
        _shot(page, "02_title_typed")

        if not _paste_html_body(page, body_html):
            _shot(page, "03_body_failed")
            browser.close()
            raise RuntimeError("微信公众号正文输入失败")
        _shot(page, "03_body_typed")
        _dump_editor_html(page, "03_body_typed")

        page.wait_for_timeout(2500)
        edit_url_after = page.url

        if dry_run:
            log.info("dry_run=True，不点击保存/发表。")
            _shot(page, "98_dry_run_final")
            _dump_editor_html(page, "98_dry_run_final")
            browser.close()
            return edit_url_after

        if not _perform_action(page, publish_action):
            _shot(page, "04_action_failed")
            browser.close()
            raise RuntimeError(f"没有找到微信公众号操作按钮：{publish_action}")

        page.wait_for_timeout(5000)
        _shot(page, "05_after_action")
        final_url = page.url
        try:
            context.storage_state(path=str(storage_state))
        except Exception:
            pass
        browser.close()
        return final_url
