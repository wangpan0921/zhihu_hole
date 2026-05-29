#!/usr/bin/env python3
"""一次性索引一本书的所有章节 URL hash。

用法：
    ./venv/bin/python scripts/weread_index_book.py "<seed_url>"
    ./venv/bin/python scripts/weread_index_book.py "<seed_url>" --headful

工作流：
1. 用 weread_fetcher（纯 HTTP GET）从 SSR HTML 拿整本书的章节列表元数据。
2. Playwright 用已保存的 weread 登录态打开 seed_url；
3. 简单循环：点"下一章" → fixed wait → 看 page.url 是否变化；
   先朝末章方向走完，回种子再朝首章方向走完。
4. 浏览器关掉后，批量调 fetcher 把每个 URL 解析为 chapterUid。
5. 输出到 data/books/<bookId>/index.json。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import Page, sync_playwright

from src.utils import DATA_DIR, get_logger, load_config
from src.weread_fetcher import fetch_book_outline, fetch_chapter

log = get_logger("weread_index")


def _click_chapter_button(page: Page, label: str) -> bool:
    """点切章按钮（'上一章' 或 '下一章'）。返回是否点到了。"""
    sel = f"button:has-text('{label}')"
    loc = page.locator(sel).first
    if loc.count() == 0:
        log.info("没找到按钮 %s", label)
        return False
    try:
        if loc.is_disabled(timeout=500):
            log.info("按钮 %s 已 disabled", label)
            return False
    except Exception:
        pass
    try:
        loc.click(timeout=3000)
        return True
    except Exception as e:
        log.warning("点击 %s 失败：%s", label, e)
        return False


def _walk_one_direction(page: Page, label: str, max_steps: int) -> list[str]:
    """从当前位置一路点 label（'上一章' 或 '下一章'），返回访问到的新 URL 列表。"""
    visited: list[str] = []
    for i in range(max_steps):
        old = page.url
        if not _click_chapter_button(page, label):
            log.info("[%s] 第 %d 步：找不到/disabled，停止", label, i + 1)
            break
        # 等 SPA 完成路由 + 内容拉取（独立测试中 3 秒足够）
        page.wait_for_timeout(3500)
        new = page.url
        if new == old:
            log.info("[%s] 第 %d 步：URL 无变化（前后都是 ...%s），停止",
                     label, i + 1, old[-20:])
            break
        visited.append(new)
        log.info("[%s] 第 %d 步：→ ...%s", label, i + 1, new[-20:])
    return visited


def _url_chapter_hash(url: str) -> str | None:
    m = re.search(r"/web/reader/[a-z0-9]+k([a-z0-9]+)", url)
    return m.group(1) if m else None


def index_book(seed_url: str, *, headful: bool = False) -> Path:
    cfg = load_config()
    storage_path = Path(cfg["weread"]["storage_state"])
    if not storage_path.exists():
        raise RuntimeError(f"找不到登录态 {storage_path}，先跑 scripts/weread_login.py")

    outline = fetch_book_outline(seed_url)
    book_id = outline["book_id"]
    book_title = outline["book_title"]
    chapter_metas = outline["chapters"]
    log.info("书：《%s》/ %s / bookId=%s / 共 %d 章",
             book_title, outline["author"], book_id, len(chapter_metas))

    visited_urls: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context(
            storage_state=str(storage_path),
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()

        log.info("打开种子：%s", seed_url)
        page.goto(seed_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(5000)
        visited_urls.append(page.url)

        # 朝末章方向走
        log.info("=== 阶段 1：从种子向末章遍历 ===")
        forward = _walk_one_direction(page, "下一章", len(chapter_metas) + 5)
        visited_urls.extend(forward)

        # 回到种子，再朝首章方向走
        log.info("=== 阶段 2：回到种子，再向首章遍历 ===")
        page.goto(seed_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(5000)
        backward = _walk_one_direction(page, "上一章", len(chapter_metas) + 5)
        visited_urls.extend(backward)

        browser.close()

    # 去重保序
    seen = set()
    uniq_urls = []
    for u in visited_urls:
        if u not in seen:
            seen.add(u)
            uniq_urls.append(u)
    log.info("浏览器关闭，共拿到 %d 个不同 URL，开始批量解析 chapterUid…",
             len(uniq_urls))

    url_by_uid: dict[int, str] = {}
    for u in uniq_urls:
        try:
            data = fetch_chapter(u)
            uid = data.get("chapter_uid")
            if uid is not None and uid not in url_by_uid:
                url_by_uid[uid] = u
                log.info("  uid=%-3s idx=%-3s %s", uid,
                         data.get("chapter_idx"), data.get("chapter_title"))
        except Exception as e:
            log.warning("解析 %s 失败：%s", u, e)

    # 拼输出
    chapters_out = []
    for c in chapter_metas:
        uid = c["chapterUid"]
        url = url_by_uid.get(uid)
        chapters_out.append({
            "chapterUid": uid,
            "chapterIdx": c["chapterIdx"],
            "title": c["title"],
            "level": c["level"],
            "wordCount": c["wordCount"],
            "paid": c.get("paid", 0),
            "url": url,
            "url_hash": _url_chapter_hash(url) if url else None,
        })
    chapters_out.sort(key=lambda x: x["chapterIdx"])

    out_dir = DATA_DIR / "books" / str(book_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.json"
    payload = {
        "book_id": str(book_id),
        "book_title": book_title,
        "author": outline["author"],
        "chapter_size": outline["chapter_size"],
        "max_free_chapter": outline["max_free_chapter"],
        "indexed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "seed_url": seed_url,
        "chapters": chapters_out,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    got = sum(1 for c in chapters_out if c["url"])
    log.info("索引完成：%d / %d 章拿到 URL → %s", got, len(chapters_out), out_path)
    missing = [c for c in chapters_out if not c["url"]]
    if missing:
        log.warning("未拿到 URL 的 %d 章：", len(missing))
        for m in missing[:10]:
            log.warning("  uid=%s idx=%s %s",
                        m["chapterUid"], m["chapterIdx"], m["title"])

    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("seed_url", help="种子章节 URL")
    parser.add_argument("--headful", action="store_true", help="弹有头浏览器")
    args = parser.parse_args()
    out = index_book(args.seed_url, headful=args.headful)
    print(f"\n索引完成：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
