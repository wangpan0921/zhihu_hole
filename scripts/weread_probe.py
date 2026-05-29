#!/usr/bin/env python3
"""微信读书章节探测脚本。

用途：评估能否从微信读书网页版抓到指定章节的正文。

用法：
    ./venv/bin/python scripts/weread_probe.py "<chapter_url>"

可选参数：
    --headful       有头浏览器（本地有 X 显示时调试用）
    --storage PATH  传入已保存的微信读书登录态（storage_state json）
    --no-scroll     不滚动，只看初始加载内容

产物（全部在 debug/weread_probe/ 下）：
    01_initial.png     刚打开页面时的视口截图
    02_after_scroll.png 滚动后的视口截图
    full_page.png      整页截图
    body_text.txt      整个 body 的 inner_text
    chapter_text.txt   命中的章节容器 inner_text
    page.html          当前页面 HTML（便于看 DOM 结构）
    summary.txt        汇总：登录态、文本长度、PUA 比例、API 请求等
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 让脚本从仓库根目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from src.utils import DEBUG_DIR, get_logger, load_env

log = get_logger("weread_probe")

OUT_DIR = DEBUG_DIR / "weread_probe"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 微信读书阅读器内可能的章节正文容器，从精确到宽泛依次尝试
CONTENT_SELECTORS = [
    ".readerChapterContent",
    ".app_content .readerChapterContent",
    ".renderTargetContent",
    ".app_content",
    ".readerContent",
    "#routerView",
    "main",
]


def _stat_text(text: str) -> dict:
    """统计文本里真实汉字 vs 私用区(PUA)字符。

    微信读书字体反爬的特征是：把汉字映射成 U+E000~U+F8FF 区段。
    PUA 比例高 → 复制出来就是乱码，必须走 OCR 或字体映射。
    """
    han = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    pua = sum(1 for c in text if "\ue000" <= c <= "\uf8ff")
    return {
        "len": len(text),
        "han": han,
        "pua": pua,
        "pua_ratio": pua / max(1, han + pua),
    }


def probe(url: str, *, headful: bool, storage: Path | None, do_scroll: bool) -> None:
    load_env()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        ctx_args: dict = dict(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        if storage and storage.exists():
            ctx_args["storage_state"] = str(storage)
            log.info("使用登录态：%s", storage)
        else:
            log.info("未提供登录态，作为游客访问")

        context = browser.new_context(**ctx_args)
        page = context.new_page()

        # 抓和章节相关的 API 请求 URL，便于后续考虑接口路线
        api_calls: list[str] = []

        def _on_req(req):
            u = req.url
            if "weread.qq.com" in u and any(
                k in u for k in ("/web/book/", "/web/reader/", "chapter", "/read")
            ):
                api_calls.append(f"{req.method} {u}")

        page.on("request", _on_req)

        log.info("打开：%s", url)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        # 给前端 SPA 渲染时间
        page.wait_for_timeout(5000)
        page.screenshot(path=str(OUT_DIR / "01_initial.png"), full_page=False)

        # 简单判定登录态：未登录通常右上角能看到「登录」按钮
        try:
            login_btn_count = page.locator("text=登录").count()
        except Exception:
            login_btn_count = -1
        is_logged_in = login_btn_count == 0
        log.info("登录态判断：%s（页面上「登录」字样命中数=%s）",
                 "已登录" if is_logged_in else "未登录", login_btn_count)

        # 找命中的章节容器
        used_sel: str | None = None
        for sel in CONTENT_SELECTORS:
            try:
                if page.locator(sel).count() > 0:
                    used_sel = sel
                    log.info("命中容器 selector：%s", sel)
                    break
            except Exception:
                continue

        # 滚动：模拟"往下滑"看完整章
        scroll_rounds = 0
        if do_scroll:
            last_text_len = -1
            stable_count = 0
            for i in range(60):
                scroll_rounds = i + 1
                # 鼠标滚轮 + PageDown 双管齐下
                try:
                    page.mouse.wheel(0, 1200)
                except Exception:
                    pass
                try:
                    page.keyboard.press("PageDown")
                except Exception:
                    pass
                page.wait_for_timeout(500)

                try:
                    cur_len = len(page.locator("body").inner_text())
                except Exception:
                    cur_len = last_text_len

                if cur_len == last_text_len:
                    stable_count += 1
                    if stable_count >= 3:
                        break
                else:
                    stable_count = 0
                last_text_len = cur_len

            log.info("滚动 %d 轮后稳定，最终 body 文本长度=%s", scroll_rounds, last_text_len)

        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT_DIR / "02_after_scroll.png"), full_page=False)
        try:
            page.screenshot(path=str(OUT_DIR / "full_page.png"), full_page=True)
        except Exception as e:
            log.warning("full_page 截图失败：%s", e)

        # 提取文本
        try:
            body_text = page.locator("body").inner_text()
        except Exception:
            body_text = ""
        (OUT_DIR / "body_text.txt").write_text(body_text, encoding="utf-8")

        chapter_text = ""
        if used_sel:
            try:
                chapter_text = page.locator(used_sel).first.inner_text()
            except Exception as e:
                log.warning("用 %s 提取章节文本失败：%s", used_sel, e)
        if chapter_text:
            (OUT_DIR / "chapter_text.txt").write_text(chapter_text, encoding="utf-8")

        try:
            (OUT_DIR / "page.html").write_text(page.content(), encoding="utf-8")
        except Exception as e:
            log.warning("dump html 失败：%s", e)

        body_stat = _stat_text(body_text)
        chap_stat = _stat_text(chapter_text) if chapter_text else None

        if body_stat["pua_ratio"] > 0.3:
            verdict = "字体反爬已生效（PUA 比例高，DOM 文本是乱码）→ 必须走 OCR 或字体映射"
        elif body_stat["han"] < 200:
            verdict = "页面里几乎没有正文（多半因为未登录看不到付费章节，或选择器没命中）"
        else:
            verdict = "DOM 文本看起来是正常字符，可以直接抓"

        title = page.title()
        lines: list[str] = [
            f"URL: {url}",
            f"页面标题: {title}",
            f"登录态: {'已登录' if is_logged_in else '未登录（游客）'}",
            f"内容容器 selector: {used_sel or '未找到'}",
            f"滚动轮数: {scroll_rounds}",
            "",
            f"[body inner_text]",
            f"  字符总数: {body_stat['len']}",
            f"  真实汉字: {body_stat['han']}",
            f"  私用区(PUA)字符: {body_stat['pua']}",
            f"  PUA 比例: {body_stat['pua_ratio']:.1%}",
        ]
        if chap_stat:
            lines += [
                "",
                f"[章节容器 inner_text]",
                f"  字符总数: {chap_stat['len']}",
                f"  真实汉字: {chap_stat['han']}",
                f"  私用区(PUA)字符: {chap_stat['pua']}",
                f"  PUA 比例: {chap_stat['pua_ratio']:.1%}",
            ]
        lines += ["", f"判断: {verdict}", "",
                  f"截获 weread 关键 API 请求数: {len(api_calls)}"]
        lines += [f"  - {u}" for u in api_calls[:25]]
        if len(api_calls) > 25:
            lines.append(f"  ... 另有 {len(api_calls) - 25} 条略")

        summary = "\n".join(lines)
        (OUT_DIR / "summary.txt").write_text(summary, encoding="utf-8")

        print("\n========== 探测结果 ==========\n")
        print(summary)
        print(f"\n所有产物已保存到：{OUT_DIR}\n")

        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="微信读书章节 URL")
    parser.add_argument("--headful", action="store_true", help="有头浏览器（本地调试）")
    parser.add_argument("--storage", type=Path, default=None,
                        help="可选：weread storage_state.json 路径")
    parser.add_argument("--no-scroll", action="store_true", help="不滚动，只看初始加载")
    args = parser.parse_args()
    probe(args.url, headful=args.headful, storage=args.storage, do_scroll=not args.no_scroll)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
