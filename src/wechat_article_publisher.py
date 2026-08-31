"""微信公众号文章草稿保存。

用 Playwright 复用微信公众号后台登录态，打开图文编辑器，填标题并把
Markdown 转成带内联样式的 HTML 粘贴到正文编辑区。

微信公众号后台 DOM 经常调整，所以这里尽量使用多组 selector fallback，并在
关键步骤保存 debug/wechat_article_* 截图，便于后续按截图修正。
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse

from playwright.sync_api import BrowserContext, Locator, Page, sync_playwright

from .markdown_html import markdown_to_html
from .utils import DEBUG_DIR, get_logger, load_config

log = get_logger("wechat_article_publisher")

MP_HOME_URL = "https://mp.weixin.qq.com/"
DEFAULT_EDIT_PATH = "/cgi-bin/appmsg"
DEFAULT_PUBLISH_ACTION = "draft"
ACTION_ENDPOINT_HINTS = {
    "draft": ("operate_appmsg", "appmsg", "draft"),
    "publish": ("freepublish", "action=publish", "sub=publish", "masssend"),
}
VALIDATION_ERROR_TEXTS = (
    "必须插入一张图片",
    "请插入一张图片",
    "请上传封面",
    "请设置封面",
    "封面不能为空",
    "标题不能为空",
    "正文不能为空",
)
SUCCESS_TEXTS = {
    "draft": ("保存成功", "已保存"),
    "publish": ("发表成功", "发布成功", "已发表"),
}


def _shot(page: Page, name: str) -> None:
    try:
        path = DEBUG_DIR / f"wechat_article_{int(time.time())}_{name}.png"
        page.screenshot(path=str(path), full_page=True)
        log.info("调试截图：%s", path)
    except Exception as e:  # noqa: BLE001
        log.warning("截图失败：%s", e)


def _dump_page_html(page: Page, name: str) -> None:
    try:
        path = DEBUG_DIR / f"wechat_page_{int(time.time())}_{name}.html"
        path.write_text(page.content(), encoding="utf-8")
        log.info("调试页面 HTML：%s", path)
    except Exception as e:  # noqa: BLE001
        log.warning("页面 HTML 转储失败：%s", e)


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
        # 新版公众号编辑器：标题是 .title-editor__input 内的 ProseMirror（textarea#title 不可见）
        ".title-editor__input [contenteditable='true']",
        ".title-editor__input .ProseMirror",
        "[contenteditable='true'][data-placeholder*='标题']",
        # 旧版 fallback
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
        # 新版公众号编辑器：正文是 .rich_media_content 内的 ProseMirror。
        # 必须放在通用 .ProseMirror 之前，否则会误抓到标题的 ProseMirror。
        ".rich_media_content .ProseMirror",
        ".rich_media_content[contenteditable='true']",
        ".rich_media_content [contenteditable='true']",
        "#ueditor_0",
        ".ProseMirror[contenteditable='true']",
        ".edui-editor-body [contenteditable='true']",
        "[contenteditable='true']:not([placeholder*='标题']):not([data-placeholder*='标题'])",
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


def _dismiss_education_dialog(page: Page) -> bool:
    """关闭公众号编辑器偶发的 education-dialog 引导层。"""
    dialog = page.locator(".education-dialog").last
    try:
        if not dialog.count() or not dialog.is_visible():
            return True
    except Exception:
        return True

    # 仅在该引导层内找关闭控件，避免误点保存、发表等业务按钮。
    for selector in (
        ".weui-desktop-dialog__close",
        ".weui-desktop-dialog__close-btn",
        "[aria-label*=\"关闭\"]",
        "button:has-text(\"我知道了\")",
        "button:has-text(\"知道了\")",
        "button:has-text(\"关闭\")",
        "[role=button]:has-text(\"我知道了\")",
        "[role=button]:has-text(\"知道了\")",
        "[role=button]:has-text(\"关闭\")",
    ):
        try:
            button = dialog.locator(selector).first
            if button.count() and button.is_visible() and button.is_enabled():
                button.click(timeout=2000)
                break
        except Exception:
            continue

    try:
        dialog.wait_for(state="hidden", timeout=3000)
        log.info("已关闭微信公众号编辑器引导弹窗")
        return True
    except Exception:
        log.warning("微信公众号编辑器引导弹窗仍在页面上，无法继续输入")
        return False


def _fill_title(page: Page, title: str) -> bool:
    if not _dismiss_education_dialog(page):
        return False
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


def _cover_is_ready(page: Page) -> bool:
    selectors = (
        "#js_cover_area .js_cover_preview_new",
        "#js_cover_area .js_cover_preview_square",
    )
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible():
                return True
        except Exception:
            continue

    try:
        default_cover = page.locator(
            "#js_cover_area .js_share_type_image"
        ).first
        return bool(default_cover.count() and default_cover.is_visible())
    except Exception:
        return False


def _select_cover_from_content(page: Page) -> bool:
    """Select the uploaded first image in WeChat explicit cover dialog."""
    if _cover_is_ready(page):
        return True
    try:
        page.locator("#js_cover_area .js_selectCoverFromContent").first.dispatch_event("click")
        picker = page.locator(".weui-desktop-dialog_img-picker")
        picker.wait_for(state="visible", timeout=5000)
        picker.locator(".appmsg_content_img_item").first.click(timeout=5000)
        picker.get_by_role("button", name="下一步", exact=True).click(timeout=5000)

        confirm_clicked = False
        confirm_deadline = time.time() + 8
        while time.time() < confirm_deadline and not confirm_clicked:
            confirm = page.get_by_role("button", name="确认", exact=True)
            for index in range(confirm.count()):
                button = confirm.nth(index)
                if button.is_visible() and button.is_enabled():
                    button.click(timeout=5000)
                    confirm_clicked = True
                    break
            if not confirm_clicked:
                page.wait_for_timeout(250)
        if not confirm_clicked:
            log.warning("封面裁剪窗口没有可用的确认按钮")
            return False
    except Exception as e:  # noqa: BLE001
        log.warning("从正文选择公众号封面失败：%s", e)
        return False

    deadline = time.time() + 10
    while time.time() < deadline:
        if _cover_is_ready(page):
            log.info("已从正文首图设置公众号封面")
            return True
        page.wait_for_timeout(300)
    log.warning("完成封面选择后，封面预览仍未显示")
    return False


def _upload_cover_as_first_image(page: Page, cover_path: Path) -> bool:
    if not cover_path.is_file():
        log.warning("微信公众号封面文件不存在：%s", cover_path)
        return False

    body = _body_locator(page)
    if body is None:
        log.warning("上传封面前找不到正文编辑器")
        return False

    try:
        body.click(timeout=3000)
        page.keyboard.press("Control+Home")
        image_count_before = body.locator("img").count()
        file_input = page.locator(
            "input[type=\"file\"][accept*=\"image\"]"
        ).first
        if not file_input.count():
            log.warning("找不到微信公众号图片上传 input")
            return False
        file_input.set_input_files(str(cover_path), timeout=10000)
    except Exception as e:  # noqa: BLE001
        log.warning("上传微信公众号封面失败：%s", e)
        return False

    end = time.time() + 30
    last_src = ""
    while time.time() < end:
        try:
            images = body.locator("img")
            image_inserted = images.count() > image_count_before
            src = images.nth(image_count_before).get_attribute("src") or "" if image_inserted else ""
        except Exception:
            image_inserted = False
            src = ""
        if src != last_src:
            log.info("封面图片上传状态：%s", src[:120] or "等待图片节点")
            last_src = src
        if image_inserted and src.startswith(("http://", "https://", "//")):
            page.wait_for_timeout(2500)
            try:
                if body.locator("img").count() > image_count_before:
                    log.info("封面图片已上传到远端并稳定插入正文")
                    return _select_cover_from_content(page)
            except Exception:
                pass
        if _cover_is_ready(page):
            log.info("公众号已识别上传的封面")
            return True
        page.wait_for_timeout(500)

    log.warning("封面上传后未检测到正文图片或封面状态")
    return False



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


def _action_response_payload(
    response: Any, action: str
) -> Optional[dict[str, Any]]:
    try:
        request = response.request
        url = str(response.url).lower()
        post_data = str(request.post_data or "").lower()
        signature = f"{url}\n{post_data}"
        if request.method.upper() != "POST":
            return None
        if not any(hint in signature for hint in ACTION_ENDPOINT_HINTS[action]):
            return None
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _base_response_ret(payload: dict[str, Any]) -> Optional[int]:
    base = payload.get("base_resp") or payload.get("baseResp")
    if not isinstance(base, dict):
        return None
    ret = base.get("ret")
    try:
        return int(ret)
    except (TypeError, ValueError):
        return None


def _visible_text(page: Page, texts: tuple[str, ...]) -> Optional[str]:
    for text in texts:
        try:
            matches = page.get_by_text(text, exact=False)
            for index in range(matches.count()):
                if matches.nth(index).is_visible():
                    return text
        except Exception:
            continue
    return None


def _saved_url(url: str) -> bool:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    has_id = any(query.get(key) for key in ("appmsgid", "appmsg_id", "id"))
    return has_id and query.get("isNew", ["0"])[0] != "1"


def _normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _find_published_article(page: Page, title: str) -> Optional[str]:
    """Return the public URL only after the title appears in publish history."""
    token = _extract_token(page.url)
    if not token:
        log.error("无法从公众号页面 URL 提取 token，不能核验发表记录")
        return None
    history_url = (
        "https://mp.weixin.qq.com/cgi-bin/appmsgpublish?"
        f"sub=list&begin=0&count=20&token={token}&lang=zh_CN"
    )
    expected = _normalize_title(title)
    deadline = time.time() + 30
    while time.time() < deadline:
        page.goto(history_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
        links = page.locator("a[href*=\"mp.weixin.qq.com/s/\"]")
        for index in range(links.count()):
            link = links.nth(index)
            if _normalize_title(link.inner_text()) == expected:
                url = link.get_attribute("href")
                log.info("已在公众号发表记录确认文章：%s", url)
                return url
        page.wait_for_timeout(1500)
    log.error("公众号发表记录中未找到标题：%s", title)
    return None


def _verify_action_success(
    page: Page,
    action: str,
    response_payloads: list[dict[str, Any]],
) -> bool:
    response_rets = [
        ret
        for payload in response_payloads
        if (ret := _base_response_ret(payload)) is not None
    ]
    log.info("微信公众号操作接口响应数量=%d，ret=%s", len(response_payloads), response_rets)
    error_text = _visible_text(page, VALIDATION_ERROR_TEXTS)
    publish_success = any(
        ret == 0 and "freepublish" in str(payload.get("_response_url", "")).lower()
        for payload, ret in ((payload, _base_response_ret(payload)) for payload in response_payloads)
        if ret is not None
    )
    if any(ret != 0 for ret in response_rets):
        log.error("微信公众号操作接口返回失败：ret=%s", response_rets)
        return False
    if error_text and not publish_success:
        log.error("微信公众号操作被页面校验拦截：%s", error_text)
        return False
    if any(ret == 0 for ret in response_rets):
        if publish_success:
            log.info("微信公众号发表接口返回成功：ret=0；忽略页面残留校验文字")
        else:
            log.info("微信公众号操作接口返回成功：ret=0")
        return True

    success_text = _visible_text(page, SUCCESS_TEXTS[action])
    if success_text:
        log.info("检测到微信公众号成功提示：%s", success_text)
        return True

    if action == "draft" and _saved_url(page.url):
        log.info("微信公众号草稿 URL 已包含素材 ID：%s", page.url)
        return True

    log.error("未检测到微信公众号成功响应、成功提示或已保存素材 ID")
    return False



_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+[\x27\"][^)]*[\x27\"])?\)")

def _prepare_body_images(page: Page, body_md: str, source_dir: Optional[Path]) -> str:
    """Upload local Markdown images and replace them with WeChat CDN URLs."""
    if source_dir is None:
        return body_md
    local_images: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for match in _MD_IMAGE_RE.finditer(body_md):
        ref = match.group(2)
        if re.match(r"^(?:https?:|data:|//)", ref, re.I):
            continue
        path = Path(ref).expanduser()
        if not path.is_absolute():
            path = source_dir / path
        path = path.resolve()
        if str(path) not in seen:
            if not path.is_file():
                raise FileNotFoundError(f"微信公众号正文图片不存在：{path}")
            local_images.append((ref, path))
            seen.add(str(path))
    if not local_images:
        return body_md

    body = _body_locator(page)
    if body is None:
        raise RuntimeError("上传微信公众号正文图片前找不到正文编辑器")
    replacements: dict[str, str] = {}
    for ref, path in local_images:
        body.click(timeout=3000)
        body.press("Control+A")
        body.press("Backspace")
        page.wait_for_timeout(300)
        before = body.locator("img").count()
        image_input = page.locator("input[type=\"file\"][accept*=\"image\"]").first
        if not image_input.count():
            raise RuntimeError("微信公众号编辑器中未找到图片上传 input")
        image_input.set_input_files(str(path), timeout=10000)
        deadline = time.time() + 30
        url = ""
        while time.time() < deadline:
            images = body.locator("img")
            for index in range(before, images.count()):
                src = images.nth(index).get_attribute("src") or ""
                if src.startswith(("http://", "https://", "//")):
                    url = src
                    break
            if url:
                break
            page.wait_for_timeout(500)
        if not url:
            raise RuntimeError(f"微信公众号正文图片上传失败：{path.name}")
        replacements[ref] = url
        log.info("微信公众号正文图片已上传：%s", path.name)

    body.click(timeout=3000)
    body.press("Control+A")
    body.press("Backspace")
    page.wait_for_timeout(300)

    def replace_image(match: re.Match[str]) -> str:
        ref = match.group(2)
        url = replacements.get(ref)
        return match.group(0) if not url else match.group(0).replace(ref, url, 1)

    return _MD_IMAGE_RE.sub(replace_image, body_md)


def publish_wechat_article(
    title: str,
    body_md: str,
    *,
    cover_path: Optional[Path] = None,
    source_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> Optional[str]:
    """把一篇微信公众号文章保存到草稿箱。

    dry_run=True 时只填入编辑器，不点击保存，并返回当前编辑页 URL。
    """
    cfg = load_config()
    mp_cfg = cfg.get("wechat_mp") or {}
    storage_state = Path(mp_cfg.get("storage_state", "data/auth/wechat_mp_state.json"))
    configured_url = str(mp_cfg.get("edit_url") or "")
    publish_action = str(mp_cfg.get("publish_action") or DEFAULT_PUBLISH_ACTION)
    if publish_action != "draft":
        raise ValueError("微信公众号文章仅允许保存到草稿箱，请将 wechat_mp.publish_action 设为 draft")

    if not storage_state.exists():
        raise RuntimeError(
            f"未找到微信公众号登录态 {storage_state}，请先运行：python scripts/wechat_login.py"
        )

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

        body_md = _prepare_body_images(page, body_md, source_dir)
        body_html = _wechat_template_html(markdown_to_html(body_md))
        if not _paste_html_body(page, body_html):
            _shot(page, "03_body_failed")
            browser.close()
            raise RuntimeError("微信公众号正文输入失败")
        _shot(page, "03_body_typed")
        _dump_editor_html(page, "03_body_typed")

        if not dry_run:
            if cover_path is None:
                browser.close()
                raise RuntimeError("微信公众号保存草稿前必须提供封面图")
            if not _upload_cover_as_first_image(page, cover_path):
                _shot(page, "04_cover_failed")
                browser.close()
                raise RuntimeError("微信公众号封面上传或识别失败")
            _shot(page, "04_cover_uploaded")

        page.wait_for_timeout(2500)
        edit_url_after = page.url

        if dry_run:
            log.info("dry_run=True，不点击保存草稿。")
            _shot(page, "98_dry_run_final")
            _dump_editor_html(page, "98_dry_run_final")
            browser.close()
            return edit_url_after

        action_payloads: list[dict[str, Any]] = []

        def capture_action_response(response: Any) -> None:
            payload = _action_response_payload(response, publish_action)
            if payload is not None:
                payload["_response_url"] = str(response.url)
                action_payloads.append(payload)

        page.on("response", capture_action_response)
        if not _perform_action(page, publish_action):
            _shot(page, "05_action_failed")
            browser.close()
            raise RuntimeError(f"没有找到微信公众号操作按钮：{publish_action}")

        page.wait_for_timeout(8000)
        _shot(page, "06_after_action")
        _dump_page_html(page, "06_after_action")
        if not _verify_action_success(page, publish_action, action_payloads):
            _shot(page, "07_action_unverified")
            browser.close()
            raise RuntimeError("微信公众号操作未通过成功校验，不写发布元数据")
        final_url = page.url
        if publish_action == "publish":
            final_url = _find_published_article(page, title)
            if not final_url:
                _shot(page, "08_publish_history_missing")
                browser.close()
                raise RuntimeError("公众号发表记录未出现目标文章，不写发布元数据")
        try:
            context.storage_state(path=str(storage_state))
        except Exception:
            pass
        browser.close()
        return final_url
