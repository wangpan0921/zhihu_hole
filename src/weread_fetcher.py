"""微信读书章节抓取器：纯 HTTP GET + 正则提取。

核心发现：
- 微信读书把当前章节的 AI 摘要塞在 `<meta name="description">` 里（约 600~1000 字，
  结构化要点）；
- 整本书的章节列表（含 chapterUid/title/wordCount 等元数据）在
  `window.__INITIAL_STATE__.reader.chapterInfos` 里；
- description 走的是 SSR，**不需要登录**。

所以日常生成读书感悟根本不需要 Playwright，1 次 HTTP GET 就能拿到全部素材。
"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any

import httpx

from .utils import get_logger

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
