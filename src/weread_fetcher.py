"""微信读书章节抓取器。

目录和章节元数据来自公开 SSR 页面。正文需要已登录的网页版阅读器；阅读器把
文字绘制到 Canvas，因此通过 Playwright 在绘制阶段捕获文字，再按行距还原段落。
"""
from __future__ import annotations

import html as html_lib
import json
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

from .utils import AUTH_DIR, get_logger

log = get_logger("weread_fetcher")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_RE_DESCRIPTION = re.compile(r'<meta\s+name="description"\s+content="([^"]+)"', re.IGNORECASE)
_RE_INITIAL_STATE = re.compile(
    r"window\.__INITIAL_STATE__\s*=\s*({.+?});", re.DOTALL
)
_RE_TITLE = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE)


class WereadFetchError(Exception):
    """抓章节失败。"""


DEFAULT_STORAGE_STATE = AUTH_DIR / "weread_state.json"
MIN_FULLTEXT_RATIO = 0.90
MAX_FULLTEXT_RATIO = 1.25

_CANVAS_CAPTURE_SCRIPT = r"""
(() => {
  window.__wereadCanvasText = [];
  let nextCanvasId = 1;
  const original = CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.fillText = function(text, x, y, maxWidth) {
    const canvas = this.canvas;
    if (!canvas.__wereadCaptureId) canvas.__wereadCaptureId = nextCanvasId++;
    window.__wereadCanvasText.push({
      text: String(text),
      x: Number(x),
      y: Number(y),
      canvasId: canvas.__wereadCaptureId
    });
    if (arguments.length >= 4) return original.call(this, text, x, y, maxWidth);
    return original.call(this, text, x, y);
  };
})();
"""


def _validate_storage_state(storage_state: Path) -> None:
    if not storage_state.exists():
        raise WereadFetchError(
            f"微信读书登录态不存在：{storage_state}，请先运行扫码登录脚本"
        )
    try:
        state = json.loads(storage_state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise WereadFetchError(f"微信读书登录态无法读取：{storage_state}") from e

    cookie_names = {
        str(cookie.get("name"))
        for cookie in state.get("cookies", [])
        if isinstance(cookie, dict)
    }
    missing = {"wr_skey", "wr_vid"} - cookie_names
    if missing:
        raise WereadFetchError(
            "微信读书登录态不完整，缺少 "
            + "、".join(sorted(missing))
            + "，请重新扫码登录"
        )


def _han_count(value: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in value)


def _normalize_text(value: str) -> str:
    value = value.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"[ \t]+", " ", value).strip()


def _paragraphs_from_canvas_records(
    records: list[dict[str, Any]],
    *,
    chapter_title: str = "",
) -> list[str]:
    """Select the text-bearing canvas and reconstruct paragraphs from line gaps."""
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        text = record.get("text")
        y = record.get("y")
        canvas_id = record.get("canvasId")
        if not isinstance(text, str) or not text:
            continue
        if not isinstance(y, (int, float)) or not isinstance(canvas_id, int):
            continue
        # Chromium/WeRead may draw a long ASCII probe while measuring fonts.
        if len(text) > 40 and _han_count(text) == 0:
            continue
        groups[canvas_id].append(record)

    if not groups:
        raise WereadFetchError("阅读器没有绘制章节文字，登录态可能已失效")

    group_stats = {
        canvas_id: {
            "han": sum(_han_count(str(item["text"])) for item in group),
            "min_y": min(float(item["y"]) for item in group),
            "max_y": max(float(item["y"]) for item in group),
        }
        for canvas_id, group in groups.items()
    }
    primary_id = max(group_stats, key=lambda canvas_id: group_stats[canvas_id]["han"])
    if group_stats[primary_id]["han"] < 100:
        raise WereadFetchError("Canvas 中没有足够的中文正文，登录态可能已失效")

    # Long chapters can be split across adjacent canvases. Start with the main
    # text canvas, then include Chinese canvases whose vertical ranges continue it.
    selected_ids = {primary_id}
    min_y = group_stats[primary_id]["min_y"]
    max_y = group_stats[primary_id]["max_y"]
    changed = True
    while changed:
        changed = False
        for canvas_id, stats in group_stats.items():
            if canvas_id in selected_ids or stats["han"] < 20:
                continue
            overlaps = stats["min_y"] <= max_y and stats["max_y"] >= min_y
            continues = (
                0 <= stats["min_y"] - max_y <= 120
                or 0 <= min_y - stats["max_y"] <= 120
            )
            if overlaps or continues:
                selected_ids.add(canvas_id)
                min_y = min(min_y, stats["min_y"])
                max_y = max(max_y, stats["max_y"])
                changed = True

    content_records = [
        record
        for canvas_id in selected_ids
        for record in groups[canvas_id]
    ]
    content_records.sort(key=lambda item: (float(item["y"]), float(item.get("x", 0))))

    lines: list[tuple[float, str]] = []
    current_y: float | None = None
    parts: list[str] = []
    for record in content_records:
        y = float(record["y"])
        if current_y is None or abs(y - current_y) < 0.5:
            current_y = y if current_y is None else current_y
            parts.append(str(record["text"]))
            continue
        line = _normalize_text("".join(parts))
        if line:
            lines.append((current_y, line))
        current_y = y
        parts = [str(record["text"])]
    if parts and current_y is not None:
        line = _normalize_text("".join(parts))
        if line:
            lines.append((current_y, line))

    if len(lines) < 2:
        raise WereadFetchError("Canvas 正文行数异常，无法还原完整章节")

    positive_gaps = [
        lines[i][0] - lines[i - 1][0]
        for i in range(1, len(lines))
        if 0 < lines[i][0] - lines[i - 1][0] < 55
    ]
    line_height = statistics.median(positive_gaps) if positive_gaps else 40.0
    paragraph_gap = line_height * 1.35

    paragraphs: list[str] = []
    current = lines[0][1]
    for i in range(1, len(lines)):
        gap = lines[i][0] - lines[i - 1][0]
        if gap >= paragraph_gap:
            paragraphs.append(_normalize_text(current))
            current = lines[i][1]
        else:
            current += lines[i][1]
    paragraphs.append(_normalize_text(current))
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]

    normalized_title = re.sub(r"\s+", "", chapter_title)
    if paragraphs and re.sub(r"\s+", "", paragraphs[0]) == normalized_title:
        paragraphs.pop(0)
    return paragraphs


def fetch_chapter_fulltext(
    url: str,
    *,
    storage_state: str | Path = DEFAULT_STORAGE_STATE,
    timeout: float = 60.0,
    min_ratio: float = MIN_FULLTEXT_RATIO,
) -> dict[str, Any]:
    """Fetch metadata plus the complete chapter text from the logged-in reader.

    The call fails closed: missing auth, too little captured text, or an incomplete
    chapter raises WereadFetchError. It never falls back to the SSR AI summary.
    """
    metadata = fetch_chapter(url, timeout=min(timeout, 30.0))
    storage_path = Path(storage_state)
    _validate_storage_state(storage_path)
    expected_chars = int(metadata.get("word_count") or 0)

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise WereadFetchError("缺少 Playwright，无法读取微信读书全文") from e

    records: list[dict[str, Any]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    storage_state=str(storage_path),
                    viewport={"width": 1280, "height": 900},
                    locale="zh-CN",
                    user_agent=DEFAULT_HEADERS["User-Agent"],
                )
                page = context.new_page()
                page.add_init_script(_CANVAS_CAPTURE_SCRIPT)
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(timeout * 1000),
                )
                minimum_han = max(100, int(expected_chars * 0.6))
                page.wait_for_function(
                    """minimum => {
                      const rows = window.__wereadCanvasText || [];
                      let count = 0;
                      for (const row of rows) {
                        count += (row.text.match(/[\u4e00-\u9fff]/g) || []).length;
                      }
                      return count >= minimum;
                    }""",
                    arg=minimum_han,
                    timeout=int(timeout * 1000),
                )
                page.wait_for_timeout(500)
                records = page.evaluate("() => window.__wereadCanvasText || []")
            finally:
                browser.close()
    except PlaywrightTimeoutError as e:
        raise WereadFetchError(
            "等待微信读书正文超时，登录态可能已失效或页面结构已变化"
        ) from e
    except WereadFetchError:
        raise
    except Exception as e:
        raise WereadFetchError(f"读取微信读书全文失败：{e}") from e

    paragraphs = _paragraphs_from_canvas_records(
        records,
        chapter_title=str(metadata.get("chapter_title") or ""),
    )
    full_text = "\n\n".join(paragraphs)
    compact_length = len(re.sub(r"\s+", "", full_text))
    ratio = compact_length / expected_chars if expected_chars > 0 else 1.0
    if expected_chars > 0 and ratio < min_ratio:
        raise WereadFetchError(
            f"章节正文疑似不完整：抓到 {compact_length} 字，"
            f"元数据标注 {expected_chars} 字（{ratio:.1%}）"
        )
    if expected_chars > 0 and ratio > MAX_FULLTEXT_RATIO:
        raise WereadFetchError(
            f"章节正文疑似重复：抓到 {compact_length} 字，"
            f"元数据标注 {expected_chars} 字（{ratio:.1%}）"
        )
    if compact_length < 100:
        raise WereadFetchError(f"章节正文过短：{compact_length} 字")

    result = dict(metadata)
    result.update(
        {
            "paragraphs": paragraphs,
            "full_text": full_text,
            "full_text_chars": compact_length,
            "completeness_ratio": ratio,
            "fetched_at": int(time.time()),
        }
    )
    return result


def _parse_initial_state(html: str) -> dict[str, Any]:
    m = _RE_INITIAL_STATE.search(html)
    if not m:
        raise WereadFetchError("HTML 里没找到 __INITIAL_STATE__")
    raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise WereadFetchError(f"__INITIAL_STATE__ 不是合法 JSON：{e}") from e


def fetch_chapter(url: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """抓取章节页面，返回结构化数据。

    返回字段：
        book_id        书 ID（数字字符串）
        book_title     书名
        author         作者
        chapter_uid    当前章节 UID
        chapter_idx    当前章节 index
        chapter_title  章节标题
        level          章节层级（1=部分/扉页，2+=正文小节）
        word_count     章节字数
        description    SSR 出的章节摘要（核心素材）
        page_title     <title> 文本
    """
    log.info("GET %s", url)
    r = httpx.get(url, headers=DEFAULT_HEADERS, follow_redirects=True, timeout=timeout)
    if r.status_code != 200:
        raise WereadFetchError(f"HTTP {r.status_code} 访问失败：{url}")
    html = r.text

    state = _parse_initial_state(html)
    reader = state.get("reader") or {}
    book = reader.get("bookInfo") or {}
    cur = reader.get("currentChapter") or {}

    if not book or not cur:
        raise WereadFetchError("INITIAL_STATE 里缺 bookInfo 或 currentChapter，URL 可能无效")

    desc_m = _RE_DESCRIPTION.search(html)
    description = html_lib.unescape(desc_m.group(1)) if desc_m else ""

    title_m = _RE_TITLE.search(html)
    page_title = html_lib.unescape(title_m.group(1)) if title_m else ""

    return {
        "book_id": str(book.get("bookId", "")),
        "book_title": book.get("title", ""),
        "author": book.get("author", ""),
        "chapter_uid": cur.get("chapterUid"),
        "chapter_idx": cur.get("chapterIdx"),
        "chapter_title": cur.get("title", ""),
        "level": cur.get("level", 1),
        "word_count": cur.get("wordCount", 0),
        "description": description,
        "page_title": page_title,
    }


def fetch_book_outline(url: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """从任意章节 URL 抓整本书的目录元数据。

    返回 {book_id, title, author, chapter_size, max_free_chapter, chapters: [...]}。
    其中 chapters 是 chapterInfos 全量（仅元数据，不含 URL hash——URL hash 需要
    用 weread_index_book.py 单独索引）。
    """
    log.info("GET (outline) %s", url)
    r = httpx.get(url, headers=DEFAULT_HEADERS, follow_redirects=True, timeout=timeout)
    if r.status_code != 200:
        raise WereadFetchError(f"HTTP {r.status_code}")

    state = _parse_initial_state(r.text)
    reader = state.get("reader") or {}
    book = reader.get("bookInfo") or {}
    chapter_infos = reader.get("chapterInfos") or []

    return {
        "book_id": str(book.get("bookId", "")),
        "book_title": book.get("title", ""),
        "author": book.get("author", ""),
        "chapter_size": book.get("chapterSize", len(chapter_infos)),
        "max_free_chapter": book.get("maxFreeChapter", 0),
        "chapters": [
            {
                "chapterUid": c.get("chapterUid"),
                "chapterIdx": c.get("chapterIdx"),
                "title": c.get("title", ""),
                "level": c.get("level", 1),
                "wordCount": c.get("wordCount", 0),
                "paid": c.get("paid", 0),
            }
            for c in chapter_infos
        ],
    }


# 默认跳过的章节标题关键词（封面/版权/前言这类非正文）
NON_CONTENT_KEYWORDS = (
    "封面", "版权", "扉页", "目录", "推荐序", "再版自序", "自序",
    "序言", "前言", "出版说明", "作者简介", "致谢", "后记", "附录",
    "编者按", "编辑推荐", "代序", "导读",
)


def is_content_chapter(chapter: dict[str, Any], *, min_word_count: int = 800) -> bool:
    """判断一个 chapterInfos 元素是不是"正文章节"。

    规则（任一为否就跳过）：
    1. 标题不命中关键词
    2. wordCount >= min_word_count（默认 800 字）

    注：level 不直接作为判定，因为这本书 level=1 也有正文章节"第一部分 看见攻击性"。
    """
    title = chapter.get("title", "") or ""
    if any(kw in title for kw in NON_CONTENT_KEYWORDS):
        return False
    if (chapter.get("wordCount") or 0) < min_word_count:
        return False
    return True


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="weread_fetcher 命令行调试")
    parser.add_argument("url", help="章节 URL")
    parser.add_argument("--outline", action="store_true", help="改抓整本书目录")
    args = parser.parse_args()

    try:
        if args.outline:
            data = fetch_book_outline(args.url)
            print(f"《{data['book_title']}》 / {data['author']}")
            print(f"bookId={data['book_id']}  共 {data['chapter_size']} 章  免费 {data['max_free_chapter']} 章")
            for c in data["chapters"]:
                marker = "  " if is_content_chapter(c) else "× "
                print(f"  {marker}uid={c['chapterUid']:>3} idx={c['chapterIdx']:>3} "
                      f"lvl={c['level']} wc={c['wordCount']:>5} {c['title']}")
        else:
            data = fetch_chapter(args.url)
            print(f"《{data['book_title']}》 第{data['chapter_idx']}章「{data['chapter_title']}」")
            print(f"chapter_uid={data['chapter_uid']} level={data['level']} word_count={data['word_count']}")
            print(f"\ndescription ({len(data['description'])} 字):")
            print(data["description"])
    except WereadFetchError as e:
        print(f"抓取失败: {e}", file=sys.stderr)
        sys.exit(1)
