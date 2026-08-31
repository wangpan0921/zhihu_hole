"""知乎专栏文章发布：复用 storage_state，打开 zhuanlan.zhihu.com/write
新建一个 draft → 填标题 → 把 markdown 粘到 ProseMirror（让它自己转富文本）
→ 点右上角"发布" → 在弹窗里搜并选中目标专栏 → 点最终"发布"。

关键实现细节：
- 粘贴正文走 dispatchEvent('paste', {clipboardData: text/plain})。这是 ProseMirror
  原生处理路径，触发它内置的 markdown 转换规则，比模拟键盘 type 快上百倍。
- 浏览器开了 clipboard-read/write 权限，避免 ProseMirror 某些版本通过
  navigator.clipboard 二次校验时被拦。
- 编辑器选择器用一组候选+逐个 fallback；每步都截图到 debug/article_*。

如果出问题先看 debug/article_*.png 截图，按出错的步骤改对应的 selector。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    BrowserContext,
    Page,
    sync_playwright,
)

from .utils import DEBUG_DIR, get_logger, load_config

log = get_logger("article_publisher")

WRITE_URL = "https://zhuanlan.zhihu.com/write"


def _shot(page: Page, name: str) -> None:
    try:
        path = DEBUG_DIR / f"article_{int(time.time())}_{name}.png"
        page.screenshot(path=str(path), full_page=True)
        log.info("调试截图：%s", path)
    except Exception as e:  # noqa: BLE001
        log.warning("截图失败：%s", e)


def _dump_editor_html(page: Page, name: str) -> None:
    """把编辑器内 innerHTML 落盘到 debug/article_*_{name}.html，便于
    无截图情况下用 grep 检查 fenced code block / 标题 / 列表是否被正确转成富文本。"""
    try:
        sel = _editor_selector(page)
        if sel is None:
            return
        html = page.evaluate(
            "(s) => document.querySelector(s)?.innerHTML || ''",
            sel,
        )
        path = DEBUG_DIR / f"article_{int(time.time())}_{name}.html"
        path.write_text(html or "", encoding="utf-8")
        log.info("调试 HTML：%s", path)
    except Exception as e:  # noqa: BLE001
        log.warning("HTML 转储失败：%s", e)


def _ensure_logged_in(context: BrowserContext, page: Page) -> bool:
    cookies = context.cookies()
    if any(c.get("name") == "z_c0" for c in cookies):
        return True
    try:
        return page.locator(".AppHeader-userInfo, .Avatar").count() > 0
    except Exception:
        return False


def _wait_editor_ready(page: Page) -> bool:
    """等 URL 跳到 /p/{id}/edit 并且编辑器 contenteditable 节点出现。"""
    try:
        page.wait_for_url(
            re.compile(r"zhuanlan\.zhihu\.com/p/\d+/edit"),
            timeout=20000,
        )
    except Exception:
        log.warning("URL 没跳到 /p/{id}/edit，继续探编辑器节点")
    selectors = (
        "div.Editable div.ProseMirror",
        "div.ProseMirror",
        "div.Editable",
        "[contenteditable='true']",
    )
    end = time.time() + 15
    while time.time() < end:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    return True
            except Exception:
                pass
        page.wait_for_timeout(400)
    return False


def _fill_title(page: Page, title: str) -> bool:
    selectors = (
        "textarea[placeholder*='标题']",
        "textarea.Input",
        "input[placeholder*='标题']",
    )
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=3000)
                loc.fill("")
                loc.type(title, delay=10)
                return True
        except Exception:
            continue
    return False


def _editor_selector(page: Page) -> Optional[str]:
    for sel in (
        "div.Editable div.ProseMirror",
        "div.ProseMirror",
        "div.Editable",
        "[contenteditable='true']",
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                return sel
        except Exception:
            continue
    return None


def _count_html_tables(html_text: str) -> int:
    """统计待粘贴 HTML 中的 table 元素。"""
    return html_text.lower().count("<table")


def _count_html_images(html_text: str) -> int:
    """统计待粘贴 HTML 中的 img 元素。"""
    return html_text.lower().count("<img")


def _paste_stats_valid(
    stats: dict, expected_tables: int, expected_images: int = 0
) -> bool:
    """校验正文规模、块级结构、表格及图片是否完整进入编辑器。"""
    return (
        stats.get("blocks", 0) > 0
        and stats.get("len", 0) > 50
        and stats.get("tables", 0) >= expected_tables
        and stats.get("images", 0) >= expected_images
    )


def _verify_published_tables(
    page: Page,
    published_url: str,
    expected_tables: int,
) -> bool:
    """发布后打开文章页，确认渲染出的表格数没有减少。"""
    if expected_tables == 0:
        return True
    try:
        page.goto(published_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        observed = page.evaluate(
            """() => {
                const root = document.querySelector(
                    ".Post-RichTextContainer, article .RichText, article"
                );
                return (root || document).querySelectorAll("table").length;
            }"""
        )
    except Exception as e:  # noqa: BLE001
        log.warning("发布后表格校验失败：%s", e)
        return False

    log.info(
        "发布后表格校验：期望 %d 张，页面渲染 %d 张",
        expected_tables,
        observed,
    )
    return observed >= expected_tables


def _verify_published_images(
    page: Page,
    published_url: str,
    expected_images: int,
) -> bool:
    """发布后打开文章页，确认渲染出的正文图片数没有减少。"""
    if expected_images == 0:
        return True
    try:
        page.goto(published_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        observed = page.evaluate(
            """() => {
                const root = document.querySelector(
                    ".Post-RichTextContainer, article .RichText, article"
                );
                return (root || document).querySelectorAll("img").length;
            }"""
        )
    except Exception as e:  # noqa: BLE001
        log.warning("发布后图片校验失败：%s", e)
        return False

    log.info(
        "发布后图片校验：期望 %d 张，页面渲染 %d 张",
        expected_images,
        observed,
    )
    return observed >= expected_images


def _paste_html_body(
    page: Page,
    body_html: str,
    *,
    expected_tables: int = 0,
    expected_images: int = 0,
) -> bool:
    """首选策略：把 Markdown 转好的 HTML 通过 text/html 粘贴事件塞进 Draft.js。

    Draft.js 的 onPaste 会优先读取 clipboardData 里的 text/html，按标准 HTML 结构
    （h2 / ul / ol / blockquote / pre>code / table / strong / code / a）一次性建出对应的富
    文本 block。相比逐字符 keyboard.type 依赖 markdown 输入规则，HTML 粘贴的块结构
    稳定，不会出现「列表上下文吞掉后续所有内容、## 与 - 以纯文本出现」的崩坏。

    成功判定：粘贴后编辑器内出现 >0 个块级标签
    （h2/ul/ol/blockquote/pre/table），textContent 长度达到一定规模，且表格、图片数
    不少于 Markdown/HTML 源文档中的对应数量。
    """
    sel = _editor_selector(page)
    if sel is None:
        log.warning("找不到正文编辑器节点")
        return False
    try:
        page.locator(sel).first.click(timeout=3000)
        page.wait_for_timeout(300)
    except Exception as e:  # noqa: BLE001
        log.warning("聚焦编辑器失败：%s", e)
        return False

    js = """([selector, htmlText]) => {
        const el = document.querySelector(selector);
        if (!el) return Promise.resolve({ ok: false, reason: 'no editor' });
        el.focus();
        const plain = htmlText
            .replace(/<br\\s*\\/?>(?=)/gi, '\\n')
            .replace(/<\\/(p|li|h2|h3|blockquote|pre)>/gi, '\\n')
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
        r = page.evaluate(js, [sel, body_html])
    except Exception as e:  # noqa: BLE001
        log.warning("写入剪贴板失败：%s", e)
        return False
    if not (isinstance(r, dict) and r.get("ok")):
        log.warning("写入剪贴板未成功：%s", r)
        return False

    # 真实 Ctrl+V：产生 trusted paste 事件，Draft.js 的 onPaste 才会读 text/html
    try:
        page.locator(sel).first.click(timeout=3000)
        page.wait_for_timeout(200)
        page.keyboard.press("Control+V")
    except Exception as e:  # noqa: BLE001
        log.warning("Ctrl+V 粘贴失败：%s", e)
        return False
    page.wait_for_timeout(2500)

    try:
        stats = page.evaluate(
            """(s) => {
                const el = document.querySelector(s);
                if (!el) return { len: 0, blocks: 0, tables: 0, images: 0 };
                const blocks = el.querySelectorAll(
                    'h2,h3,ul,ol,blockquote,pre,table'
                ).length;
                return {
                    len: (el.textContent || "").length,
                    blocks,
                    tables: el.querySelectorAll("table").length,
                    images: el.querySelectorAll("img").length,
                };
            }""",
            sel,
        )
    except Exception:
        stats = {"len": 0, "blocks": 0, "tables": 0, "images": 0}

    log.info(
        "html paste → 编辑器内 %d 字 / %d 个块级元素 / %d 张表格 / %d 张图片",
        stats.get("len", 0),
        stats.get("blocks", 0),
        stats.get("tables", 0),
        stats.get("images", 0),
    )
    # 至少要有结构化块、足够正文，并保留所有期望表格和图片。
    return _paste_stats_valid(stats, expected_tables, expected_images)


CODE_FENCE_RE = re.compile(r"^\s*```")


def _flatten_fenced_code_blocks(body_md: str) -> str:
    """把 fenced code block 转成「每行 inline code 段落」。

    背景：知乎写文章用的是 Facebook Draft.js（不是 ProseMirror），实测无论是
    Mod+Enter / 双 Enter / dispatchEvent paste 都无法可靠退出 code-block，
    一旦键入开 ``` 进入代码块，后续所有内容（包括闭合 ``` 行）都会被吞进
    同一个超长代码块，导致正文渲染崩溃。

    取舍：放弃整体代码块的等宽视觉效果，把代码块每一行单独包成 `inline code`
    段落，靠 Draft.js 的 inline code 输入规则给每行加等宽字体。代价是行间
    没有连成一块的灰底，但所有内容完整可读，且不影响代码块以外正文的渲染。
    """
    lines = body_md.splitlines()
    out: list[str] = []
    in_code = False
    n_blocks = 0
    for line in lines:
        if CODE_FENCE_RE.match(line):
            in_code = not in_code
            if in_code:
                n_blocks += 1
            # 块前后插一个空行做视觉分隔，避免上下段挤在一起
            if out and out[-1] != "":
                out.append("")
            continue
        if in_code:
            # 反引号 escape，避免提前结束 inline code
            content = line.replace("`", "'")
            if content.strip():
                out.append(f"`{content}`")
            else:
                # 代码块内的空行：保留为普通空段落
                out.append("")
        else:
            out.append(line)
    if n_blocks:
        log.info("已把 %d 段 fenced code block 降级为 inline-code 多段落", n_blocks)
    return "\n".join(out)


def _paste_markdown_body(page: Page, body_md: str) -> bool:
    """优先策略：对 Draft.js 编辑器 dispatch ClipboardEvent('paste')，
    让编辑器自己的 onPaste handler 把 markdown 转富文本。

    成功条件：paste 后编辑器内 textContent 长度 ≥ md 字符数的 50%。
    （知乎 markdown paste 会消费掉 ``` # > * - 等标记字符，所以输出会比输入短，
    但不会短于一半。）
    """
    sel = _editor_selector(page)
    if sel is None:
        log.warning("找不到正文编辑器节点")
        return False
    try:
        page.locator(sel).first.click(timeout=3000)
        page.wait_for_timeout(300)
    except Exception as e:  # noqa: BLE001
        log.warning("聚焦编辑器失败：%s", e)
        return False

    js = """([selector, text, mimeType]) => {
        const el = document.querySelector(selector);
        if (!el) return { ok: false, reason: 'no editor' };
        el.focus();
        try {
            const dt = new DataTransfer();
            dt.setData(mimeType, text);
            // 同时塞 text/plain 兜底（Draft.js 优先取 text/plain）
            if (mimeType !== 'text/plain') dt.setData('text/plain', text);
            const ev = new ClipboardEvent('paste', {
                clipboardData: dt,
                bubbles: true,
                cancelable: true,
            });
            const dispatched = el.dispatchEvent(ev);
            return { ok: true, dispatched };
        } catch (e) {
            return { ok: false, reason: String(e) };
        }
    }"""

    for mime in ("text/markdown", "text/plain"):
        try:
            r = page.evaluate(js, [sel, body_md, mime])
        except Exception as e:  # noqa: BLE001
            log.warning("dispatch paste(%s) 失败：%s", mime, e)
            continue
        page.wait_for_timeout(2500)
        # 粗略校验：编辑器内 textContent 长度
        try:
            current_len = page.evaluate(
                "(s) => (document.querySelector(s)?.textContent || '').length",
                sel,
            )
        except Exception:
            current_len = 0
        log.info("paste(mime=%s) → 编辑器内 %d 字（源 %d 字）", mime, current_len, len(body_md))
        if current_len >= len(body_md) * 0.5:
            return True
        # 若上一次 paste 已经塞进部分内容，下一次 mime 切换前需要清空
        try:
            page.evaluate(
                "(s) => { const el = document.querySelector(s); if (el) el.innerHTML = ''; }",
                sel,
            )
        except Exception:
            pass

    return False


def _type_markdown_body(page: Page, body_md: str) -> bool:
    """点击编辑器使其获焦 → 用键盘逐行 type，且对 fenced code block 做特殊处理。

    知乎写文章编辑器底部明确标注「Markdown 语法输入中」，意味着 ProseMirror 内置
    了 markdown 输入规则：边输入边把 `# / ## / - / 1. / ``` / **bold** / [text](url)`
    等转成对应富文本节点。所以这里**不能**用 dispatchEvent('paste') 一次塞进去——
    那会被当作整段纯文本，markdown 不会被转。必须走真实键盘事件让它逐字符触发规则。

    换行用 keyboard.press('Enter') 而不是 \\n（ProseMirror 不识别 \\n）。

    ⚠️ fenced code block 的坑：如果整段都用 keyboard.type 含 ``` 闭合行，
    ProseMirror 进入 code_block 后**不会**再把后续 ``` 识别为闭合标记（输入规则只
    对普通段落生效，code_block 内不再触发），导致从开 ``` 起后续所有内容都被吞进
    一个永不结束的代码块。
    所以这里把行分四种处理：
      - 普通行：按之前的方式 type + Enter
      - 代码块开行（``` 或 ```lang）：type 整行后按 Enter，触发段落转 code_block，
        光标自动落在 code_block 内
      - 代码块内行：type + Enter（在 code_block 内换行）
      - 代码块闭合行（独立一行的 ```）：用 Mod+Enter（ProseMirror 的 exitCode 命令）
        跳出 code_block，**不**键入这行 ``` 字符
    """
    sel = _editor_selector(page)
    if sel is None:
        log.warning("找不到正文编辑器节点")
        return False
    try:
        page.locator(sel).first.click(timeout=3000)
        page.wait_for_timeout(300)
        lines = body_md.split("\n")
        log.info("开始逐行输入正文（%d 行 / %d 字符）", len(lines), len(body_md))

        in_code = False
        # 进入 code_block 的那一行（开 ``` 行）键入完后，光标已经在 code_block
        # 第一行行首；下一行不需要再多按一次 Enter
        just_entered_code = False
        n_fence_open = 0
        n_fence_close = 0

        for i, line in enumerate(lines):
            is_fence = bool(CODE_FENCE_RE.match(line))

            # 行间 Enter：除了首行 / 刚进入代码块的下一行
            if i > 0 and not just_entered_code:
                if in_code and is_fence:
                    # 闭合代码块：Draft.js 不响应 Mod+Enter exitCode；标准约定是
                    # 「在 code-block 末尾按两次 Enter（先到空行，再 Enter 切出 block）」。
                    # 这里不键入这行 ``` 字符。
                    page.keyboard.press("Enter")
                    page.keyboard.press("Enter")
                    in_code = False
                    n_fence_close += 1
                    continue
                page.keyboard.press("Enter")
            just_entered_code = False

            if not in_code and is_fence:
                # 进入代码块：type 整行（``` 或 ```lang），再按 Enter 触发输入规则把
                # 当前 paragraph 转成 code_block，光标落在 code_block 内
                page.keyboard.type(line, delay=2)
                page.keyboard.press("Enter")
                in_code = True
                just_entered_code = True
                n_fence_open += 1
                continue

            if line:
                page.keyboard.type(line, delay=2)

        # 文末仍困在 code_block 内：用双 Enter 兜底跳出
        if in_code:
            page.keyboard.press("Enter")
            page.keyboard.press("Enter")
            n_fence_close += 1

        log.info(
            "正文输入完成（识别代码块开 %d 次 / 闭合 %d 次）",
            n_fence_open,
            n_fence_close,
        )
        # 给最后一行 markdown 输入规则收尾的时间
        page.wait_for_timeout(800)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("正文输入失败：%s", e)
        return False


def _enable_column_and_select(page: Page, column_name: str) -> bool:
    """页面下半部分的「发布设置 → 专栏收录」面板：
      1) radio 「发布到专栏」选中（默认是「不发布到专栏」）
      2) 选中后会出现专栏选择 UI（搜索框 / 我的专栏列表）→ 选中目标专栏

    成功条件：目标专栏在页面上以"已选中"状态出现。
    """
    # 滚动到底，让"专栏收录"在视口内
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass
    page.wait_for_timeout(800)

    # 1) 勾选 "发布到专栏" radio
    radio_clicked = False
    for sel in (
        "label:has-text('发布到专栏')",
        "span:has-text('发布到专栏')",
        "text=发布到专栏",
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=3000)
                radio_clicked = True
                log.info("已点击「发布到专栏」radio")
                break
        except Exception:
            continue
    if not radio_clicked:
        log.warning("没找到「发布到专栏」radio")

    page.wait_for_timeout(1200)

    # 2) 选中目标专栏：先看是否列表里直接有名字
    try:
        # 限制在"专栏收录"附近的 DOM 范围找，避免误中其他位置同名节点
        loc = page.locator(f"text={column_name}").first
        if loc.count() and loc.is_visible():
            loc.click(timeout=3000)
            log.info("已点击列表中的专栏：%s", column_name)
            page.wait_for_timeout(800)
            return True
    except Exception:
        pass

    # 3) 否则尝试搜索式：输入框 placeholder 含"专栏"
    typed = False
    for sel in (
        "input[placeholder*='搜索专栏']",
        "input[placeholder*='专栏']",
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=2000)
                loc.fill("")
                loc.type(column_name, delay=20)
                typed = True
                break
        except Exception:
            continue

    if typed:
        page.wait_for_timeout(1500)
        try:
            match = page.locator(f"text={column_name}").last
            if match.count() and match.is_visible():
                match.click(timeout=3000)
                log.info("搜索后点中专栏：%s", column_name)
                page.wait_for_timeout(800)
                return True
        except Exception:
            pass

    # Current Zhihu uses a closed combobox inside ColumnSetting-ColumnSelector.
    # The target option is not in the DOM until this exact combobox is opened.
    try:
        dropdown = page.locator(
            ".ColumnSetting-ColumnSelector button[role='combobox']"
        ).first
        if dropdown.count() and dropdown.is_visible():
            dropdown.click(timeout=3000)
            page.wait_for_timeout(800)
            match = page.get_by_text(column_name, exact=True).last
            if match.count() and match.is_visible():
                match.click(timeout=3000)
                log.info("展开专栏下拉框后点中：%s", column_name)
                page.wait_for_timeout(800)
                return True
            page.keyboard.press("Escape")
    except Exception:
        pass

    # Keep generic fallbacks for future DOM variants.
    for sel in (
        "div.Select-control",
        "div[class*='Select-control']",
        "[role='combobox']",
        "button[aria-haspopup='listbox']",
    ):
        try:
            candidates = page.locator(sel)
            for i in range(candidates.count() - 1, -1, -1):
                dropdown = candidates.nth(i)
                if not dropdown.is_visible():
                    continue
                dropdown.click(timeout=3000)
                page.wait_for_timeout(800)
                match = page.get_by_text(column_name, exact=True).last
                if match.count() and match.is_visible():
                    match.click(timeout=3000)
                    log.info("展开专栏下拉框后点中：%s", column_name)
                    page.wait_for_timeout(800)
                    return True
                page.keyboard.press("Escape")
        except Exception:
            continue

    log.warning("没把专栏选上，请看截图")
    return False


def _click_publish_bottom(page: Page) -> bool:
    """点页面右下方蓝色「发布」按钮（不是模态框）。"""
    end = time.time() + 8
    while time.time() < end:
        for sel in (
            "button.PublishPanel-button:has-text('发布')",
            "button.Button.Button--primary:has-text('发布')",
            "button.Button--primary:has-text('发布')",
            "button:has-text('发布'):not(:has-text('设置'))",
        ):
            try:
                cand = page.locator(sel)
                n = cand.count()
                for i in range(n):
                    btn = cand.nth(i)
                    try:
                        if btn.is_visible() and btn.is_enabled():
                            btn.click(timeout=3000)
                            log.info("已点击底部「发布」按钮：%s", sel)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        page.wait_for_timeout(400)
    return False


def _click_update_bottom(page: Page) -> bool:
    """点编辑已发布文章时页面右下方的「更新」按钮。"""
    end = time.time() + 8
    while time.time() < end:
        for sel in (
            "button.PublishPanel-button:has-text('更新')",
            "button.Button.Button--primary:has-text('更新')",
            "button.Button--primary:has-text('更新')",
            "button:has-text('更新')",
        ):
            try:
                cand = page.locator(sel)
                for i in range(cand.count()):
                    btn = cand.nth(i)
                    if btn.is_visible() and btn.is_enabled():
                        btn.click(timeout=3000)
                        log.info("已点击底部「更新」按钮：%s", sel)
                        return True
            except Exception:
                continue
        page.wait_for_timeout(400)
    return False


def _clear_editor_body(page: Page) -> bool:
    """通过真实键盘事件清空 Draft.js 正文，确保其内部状态同步更新。"""
    sel = _editor_selector(page)
    if sel is None:
        return False
    try:
        editor_root = page.locator(sel).first
        editable = editor_root.locator("[contenteditable='true']").first
        editor = editable if editable.count() and editable.is_visible() else editor_root
        editor.click(timeout=3000)
        for attempt in range(2):
            editor.press("Control+A")
            editor.press("Backspace")
            page.wait_for_timeout(500)
            remaining = len((editor.text_content() or "").strip())
            log.info("第 %d 次清空旧正文后剩余 %d 字", attempt + 1, remaining)
            if remaining == 0:
                return True
        return False
    except Exception as e:  # noqa: BLE001
        log.warning("清空旧正文失败：%s", e)
        return False


_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")


def _local_image_paths(body_md: str, source_dir: Optional[Path]) -> list[tuple[str, Path]]:
    """Return local Markdown image references and resolved files.

    Remote URLs are deliberately ignored because they already work when pasted.
    """
    if source_dir is None:
        return []
    found: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for match in _MD_IMAGE_RE.finditer(body_md):
        ref = match.group(2)
        if re.match(r"^(?:https?:|data:|//)", ref, re.I):
            continue
        path = Path(ref).expanduser()
        if not path.is_absolute():
            path = source_dir / path
        key = str(path.resolve())
        if key not in seen:
            found.append((ref, path.resolve()))
            seen.add(key)
    return found


def _load_image_cache(path: Optional[Path]) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}
    except Exception as exc:  # noqa: BLE001
        log.warning("读取图片上传缓存失败：%s", exc)
        return {}


def _save_image_cache(path: Optional[Path], data: dict[str, str]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _prepare_body_images(
    page: Page,
    body_md: str,
    *,
    source_dir: Optional[Path],
    cache_path: Optional[Path],
) -> str:
    """Upload local images and rewrite their Markdown references to CDN URLs."""
    local_images = _local_image_paths(body_md, source_dir)
    if not local_images:
        return body_md
    cache = _load_image_cache(cache_path)
    pending = [(ref, path) for ref, path in local_images if str(path) not in cache]
    if pending:
        editor = _editor_selector(page)
        for _ref, path in pending:
            if not _clear_editor_body(page):
                raise RuntimeError("上传图片前无法清空临时图片节点")
            loc = page.locator(f"{editor} img" if editor else "img")
            before = loc.count()
            inputs = page.locator("input[type='file']")
            image_input = None
            for index in range(inputs.count()):
                accept = (inputs.nth(index).get_attribute("accept") or "").lower()
                if "image/" in accept:
                    image_input = inputs.nth(index)
                    break
            if image_input is None:
                raise RuntimeError("知乎编辑器中未找到图片上传 input")
            if editor:
                page.locator(editor).first.click(timeout=3000)
            image_input.set_input_files(str(path))
            log.info("已提交正文图片：%s", path.name)
            deadline = time.time() + 30
            url = ""
            while time.time() < deadline:
                current = page.locator(f"{editor} img" if editor else "img")
                for index in range(before, current.count()):
                    src = current.nth(index).get_attribute("src") or ""
                    if src.startswith("http"):
                        url = src
                        break
                if url:
                    break
                page.wait_for_timeout(500)
            if not url:
                raise RuntimeError(f"知乎图片上传失败：{path.name} 未获得图片 URL")
            cache[str(path)] = url
            _save_image_cache(cache_path, cache)
        if not _clear_editor_body(page):
            raise RuntimeError("上传图片后无法清空临时图片节点")
    replacements = {ref: cache[str(path)] for ref, path in local_images}

    def _replace_image(match: re.Match[str]) -> str:
        ref = match.group(2)
        url = replacements.get(ref)
        return match.group(0) if not url else match.group(0).replace(ref, url, 1)

    body_md = _MD_IMAGE_RE.sub(_replace_image, body_md)
    return body_md


def _confirm_publish_modal(page: Page) -> bool:
    """点完底部「发布」后，可能弹出二次确认（"确认发布到 XX 专栏？"），点确认。
    没弹模态就直接 True。"""
    page.wait_for_timeout(1500)
    for sel in (
        "div.Modal button.Button--primary:has-text('确定')",
        "div[role='dialog'] button.Button--primary:has-text('确定')",
        "div.Modal button:has-text('确认发布')",
        "div[role='dialog'] button:has-text('确认发布')",
        "div[role='dialog'] button.Button--primary:has-text('发布')",
    ):
        try:
            cand = page.locator(sel)
            n = cand.count()
            for i in range(n):
                btn = cand.nth(i)
                try:
                    if btn.is_visible() and btn.is_enabled():
                        btn.click(timeout=3000)
                        log.info("已点击二次确认按钮")
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return True  # 没有模态就当成功


def publish_article(
    title: str,
    body_md: str,
    *,
    dry_run: bool = False,
    column_name: Optional[str] = None,
    body_html_override: Optional[str] = None,
    edit_url: Optional[str] = None,
    source_dir: Optional[Path] = None,
    image_cache_path: Optional[Path] = None,
) -> Optional[str]:
    """新建文章，或通过 edit_url 更新一篇已发布文章。

    返回：成功 → 文章 URL（dry_run 时返回 draft 编辑 URL）；失败 → 抛 RuntimeError。
    """
    cfg = load_config()
    storage_state = Path(cfg["zhihu"]["storage_state"])
    column_name = column_name or (cfg.get("article") or {}).get(
        "column_name", "Agent工坊"
    )

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
        # 给剪贴板权限：某些 ProseMirror 版本会用 navigator.clipboard 做二次校验
        try:
            context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://zhuanlan.zhihu.com",
            )
        except Exception:
            pass

        page = context.new_page()
        target_url = edit_url or WRITE_URL
        if edit_url:
            target_url = re.sub(r"[?#].*$", "", edit_url).rstrip("/")
            if not target_url.endswith("/edit"):
                target_url += "/edit"
        log.info("打开文章编辑页：%s", target_url)
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        if not _ensure_logged_in(context, page):
            _shot(page, "00_not_logged_in")
            browser.close()
            raise RuntimeError("登录态失效，请重新运行：python scripts/login.py")

        if not _wait_editor_ready(page):
            _shot(page, "01_editor_not_ready")
            browser.close()
            raise RuntimeError("编辑器未就绪")
        current_edit_url = page.url
        log.info("文章编辑 URL：%s", current_edit_url)
        _shot(page, "01_editor_ready")

        # 1. 标题
        if not _fill_title(page, title):
            _shot(page, "02_title_failed")
            browser.close()
            raise RuntimeError("标题输入失败")
        _shot(page, "02_title_typed")

        if edit_url and not _clear_editor_body(page):
            _shot(page, "03_body_clear_failed")
            browser.close()
            raise RuntimeError("旧正文清空失败，已停止更新")

        # 2. 正文：首选「Markdown → HTML → text/html 粘贴」让 Draft.js 一次性
        #    建出 h2/ul/ol/blockquote/pre 等结构化 block；失败再回退到逐字符 type
        #    （type 路径对列表/代码块上下文不可靠，仅作兜底）。
        from .markdown_html import count_markdown_tables, markdown_to_html

        body_md = _prepare_body_images(
            page,
            body_md,
            source_dir=source_dir,
            cache_path=image_cache_path,
        )

        body_html = body_html_override or markdown_to_html(body_md)
        source_tables = count_markdown_tables(body_md)
        generated_tables = _count_html_tables(body_html)
        expected_tables = max(source_tables, generated_tables)
        expected_images = _count_html_images(body_html)
        if generated_tables < source_tables:
            browser.close()
            raise RuntimeError(
                f"Markdown 中有 {source_tables} 张表格，但只生成了 "
                f"{generated_tables} 个 table 元素"
            )

        body_ok = _paste_html_body(
            page,
            body_html,
            expected_tables=expected_tables,
            expected_images=expected_images,
        )
        if not body_ok and (expected_tables or expected_images):
            _shot(page, "03_content_validation_failed")
            _dump_editor_html(page, "03_content_validation_failed")
            browser.close()
            raise RuntimeError(
                "知乎编辑器未完整保留正文结构："
                f"{expected_tables} 张表格 / {expected_images} 张图片，已停止发布"
            )
        if not body_ok:
            log.warning("HTML 粘贴未达预期，回退到逐行 type")
            # 清空编辑器再走 type 兜底
            sel = _editor_selector(page)
            if sel:
                try:
                    page.evaluate(
                        "(s)=>{const el=document.querySelector(s);if(el)el.innerHTML='';}",
                        sel,
                    )
                except Exception:
                    pass
            body_md_processed = _flatten_fenced_code_blocks(body_md)
            body_ok = _type_markdown_body(page, body_md_processed)
        if not body_ok:
            _shot(page, "03_body_failed")
            browser.close()
            raise RuntimeError("正文输入失败")
        _shot(page, "03_body_typed")

        # 给 ProseMirror 自动保存的时间
        page.wait_for_timeout(2500)
        # 此时 URL 通常已经从 /write 跳到 /p/{id}/edit
        edit_url_after = page.url
        if edit_url_after != current_edit_url:
            log.info("URL 已跳转：%s → %s", current_edit_url, edit_url_after)
            current_edit_url = edit_url_after

        if dry_run:
            log.info("dry_run=True，不点发布。")
            _shot(page, "98_dry_run_final")
            _dump_editor_html(page, "98_dry_run_final")
            browser.close()
            return current_edit_url

        if edit_url:
            if not _click_update_bottom(page):
                _shot(page, "05_update_btn_not_found")
                browser.close()
                raise RuntimeError("找不到底部更新按钮")
            _confirm_publish_modal(page)
            page.wait_for_timeout(5000)
            _shot(page, "06_after_update")
            _dump_editor_html(page, "06_after_update")
            m = re.search(r"/p/(\d+)", current_edit_url)
            published_url = (
                f"https://zhuanlan.zhihu.com/p/{m.group(1)}" if m else edit_url
            )
            if not _verify_published_tables(
                page, published_url, expected_tables
            ):
                _shot(page, "07_published_table_verification_failed")
                log.error("文章已更新，但发布页表格校验未通过：%s", published_url)
            if not _verify_published_images(
                page, published_url, expected_images
            ):
                _shot(page, "07_published_image_verification_failed")
                log.warning("文章已更新，但发布页图片校验未通过；保留更新结果并继续返回 URL")
            try:
                context.storage_state(path=str(storage_state))
            except Exception:
                pass
            browser.close()
            return published_url

        # 3. 在「发布设置」面板勾选「发布到专栏」并选中目标专栏
        if not _enable_column_and_select(page, column_name):
            _shot(page, "04_column_select_failed")
            browser.close()
            raise RuntimeError(f"未能选中知乎专栏：{column_name}")
        _shot(page, "04_column_selected")

        # 4. 点底部右下方的蓝色"发布"按钮
        if not _click_publish_bottom(page):
            _shot(page, "05_publish_btn_not_found")
            browser.close()
            raise RuntimeError("找不到底部发布按钮（可能正文还没填好按钮被禁用）")
        _shot(page, "05_publish_clicked")

        # 5. 二次确认（如果有模态弹出）
        _confirm_publish_modal(page)
        page.wait_for_timeout(5000)
        _shot(page, "06_after_publish")

        # 取已发布 URL：知乎一般会跳到 /p/{id}（去掉 /edit）
        published_url = page.url
        if "/edit" in published_url:
            m = re.search(r"/p/(\d+)", current_edit_url)
            if m:
                published_url = f"https://zhuanlan.zhihu.com/p/{m.group(1)}"
        log.info("发布完成：%s", published_url)

        if not _verify_published_tables(page, published_url, expected_tables):
            _shot(page, "07_published_table_verification_failed")
            log.error("文章已发布，但发布页表格校验未通过：%s", published_url)

        if not _verify_published_images(page, published_url, expected_images):
            _shot(page, "07_published_image_verification_failed")
            log.warning("文章已发布，但发布页图片校验未通过；保留发布结果并继续返回 URL")

        # 顺手刷新登录态
        try:
            context.storage_state(path=str(storage_state))
        except Exception:
            pass

        browser.close()
        return published_url
