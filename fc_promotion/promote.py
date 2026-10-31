"""推广主编排。

流程（以知乎为例）：
  1. 用本机登录态打开平台搜索页，按关键词找有需求的问题/帖子
  2. 为每条生成一条自然的推广评论（突出体积小/不占空间/耗电低 + 下载方式）
  3. 可选：用本人账号发出评论（--post；默认 dry-run 不发，只预览）
  4. 把每一条推广记录写入飞书「推广数据库」多维表格，方便人工查看

安全：
  - 仅在本机、有登录态时运行；云端无登录态会直接搜不到。
  - 默认 dry-run。真正发评论需显式 --post，且受 config 频控限制。
  - 自动发评论有平台风控风险，请把 --max 调小、间隔调大。

    python -m fc_promotion.promote --dry-run
    python -m fc_promotion.promote --platform zhihu --post --max 2
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field

from . import config, copywriter
from .common.feishu_bitable import FeishuBitable
from .common.logging_utils import get_logger
from .common.login import get_login

log = get_logger("promote")


def _headless_mode() -> bool:
    """仅在明确设置时启用无头模式，默认保留已验证的有头流程。"""
    return os.getenv("FC_PROMOTION_HEADLESS", "").lower() in {"1", "true", "yes"}


@dataclass
class Lead:
    platform: str
    title: str
    url: str
    comment: str = ""
    status: str = "待发布"
    extra: dict = field(default_factory=dict)


def is_android_relevant(title: str) -> bool:
    """判断一条线索标题是否与"安卓悬浮时钟"相关。

    规则：
      1. 命中任一排除词（苹果/iOS/桌面/电脑端等）→ 判为不相关。
      2. 若 config.REQUIRE_ANDROID_HINT 为真，则还要求标题含安卓/手机等正向信号。
    标题为空时按不相关处理。
    """
    if not title:
        return False
    low = title.lower()
    for bad in config.EXCLUDE_KEYWORDS:
        if bad.lower() in low:
            return False
    # 主题相关性：必须命中"悬浮/带秒/看时间"等真实需求词，否则是答非所问的泛问题（剔除）
    if getattr(config, "REQUIRE_TOPIC", False):
        if not any(t.lower() in low for t in config.TOPIC_KEYWORDS):
            return False
    if config.REQUIRE_ANDROID_HINT:
        return any(hint.lower() in low for hint in config.ANDROID_HINT_KEYWORDS)
    return True


def search_zhihu_leads(keywords: list[str], limit: int) -> list[Lead]:
    """用持久化 profile（拟人化）打开知乎搜索页，抓取问题链接作为推广线索。

    用 is_android_relevant 过滤苹果版/桌面版等非安卓线索。
    必须用持久化 profile，否则知乎返回 40362 风控页。
    """
    from .common import humanized_browser as hb

    leads: list[Lead] = []
    skipped = 0
    tmpl = config.SEARCH_TARGETS["zhihu"]["search_url"]
    with hb.persistent_context(config.ZHIHU_PROFILE, headless=_headless_mode()) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # 先过首页，拿到正常会话再搜，降低风控
        page.goto("https://www.zhihu.com/", wait_until="domcontentloaded", timeout=40000)
        hb.human_pause(2, 4)
        if not any(c.get("name") == "z_c0" for c in ctx.cookies()):
            raise RuntimeError(
                "知乎未登录（持久化 profile 内无登录态）。请先在本机扫码：\n"
                "  python -m fc_promotion.login_cli zhihu"
            )
        for kw in keywords:
            if len(leads) >= limit:
                break
            page.goto(tmpl.format(kw=kw), wait_until="domcontentloaded", timeout=40000)
            hb.human_pause(2, 4)
            hb.human_scroll(page, times=random.randint(2, 4))
            anchors = page.locator("a[href*='/question/']")
            count = min(anchors.count(), 15)
            for i in range(count):
                if len(leads) >= limit:
                    break
                try:
                    a = anchors.nth(i)
                    href = a.get_attribute("href") or ""
                    title = (a.inner_text() or "").strip()
                    if not href or not title:
                        continue
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        href = "https://www.zhihu.com" + href
                    if any(l.url == href for l in leads):
                        continue
                    if not is_android_relevant(title):
                        skipped += 1
                        log.info("跳过非安卓线索：%s", title[:40])
                        continue
                    leads.append(Lead(platform="zhihu", title=title, url=href))
                except Exception:  # noqa: BLE001
                    continue
    log.info("知乎收集到 %d 条安卓相关线索（过滤掉 %d 条非安卓）", len(leads), skipped)
    return leads


SEARCHERS = {
    "zhihu": search_zhihu_leads,
    # 酷安/头条/小红书用通用搜索器（见下方 generic_search / make_searcher）
}


def _abs_url(href: str, platform: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        base = config.PLATFORM_HOME.get(platform, "/").rstrip("/")
        return base + href
    return href


def generic_search_leads(platform: str, keywords: list[str], limit: int) -> list[Lead]:
    """通用搜索器：持久化 profile + 拟人化，按平台配置的 URL/选择器抓线索。

    用于酷安/头条/小红书。选择器在 config.PLATFORM_LINK_SELECTOR，随改版需本机核对。
    """
    from .common import humanized_browser as hb

    profile = config.PLATFORM_PROFILE[platform]
    home = config.PLATFORM_HOME[platform]
    tmpl = config.SEARCH_TARGETS[platform]["search_url"]
    link_sel = config.PLATFORM_LINK_SELECTOR[platform]
    login_cookies = set(config.PLATFORM_LOGIN_COOKIES.get(platform, []))

    leads: list[Lead] = []
    skipped = 0
    with hb.persistent_context(profile, headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(home, wait_until="domcontentloaded", timeout=40000)
        hb.human_pause(2, 4)
        if login_cookies and not any(c.get("name") in login_cookies for c in ctx.cookies()):
            raise RuntimeError(
                f"{platform} 未登录（持久化 profile 内无登录态）。先在本机扫码：\n"
                f"  python -m fc_promotion.login_cli {platform}"
            )
        for kw in keywords:
            if len(leads) >= limit:
                break
            page.goto(tmpl.format(kw=kw), wait_until="domcontentloaded", timeout=40000)
            hb.human_pause(2, 4)
            hb.human_scroll(page, times=random.randint(2, 4))
            anchors = page.locator(link_sel)
            count = min(anchors.count(), 15)
            for i in range(count):
                if len(leads) >= limit:
                    break
                try:
                    a = anchors.nth(i)
                    href = a.get_attribute("href") or ""
                    title = (a.inner_text() or "").strip()
                    if not href or not title:
                        continue
                    url = _abs_url(href, platform)
                    if any(l.url == url for l in leads):
                        continue
                    if not is_android_relevant(title):
                        skipped += 1
                        log.info("[%s] 跳过非安卓线索：%s", platform, title[:40])
                        continue
                    leads.append(Lead(platform=platform, title=title, url=url))
                except Exception:  # noqa: BLE001
                    continue
    log.info("[%s] 收集到 %d 条安卓相关线索（过滤掉 %d 条非安卓）", platform, len(leads), skipped)
    return leads


def generic_post_comment(platform: str, lead: Lead) -> bool:
    """通用发布器：持久化 profile + 拟人化，在帖子下发评论。

    用于酷安/头条/小红书。选择器在 config.PLATFORM_POST_SELECTORS，多候选兜底，
    任一环节找不到即返回 False（不误发）。首次务必本机 headful 盯一遍确认选择器。
    """
    from .common import humanized_browser as hb

    profile = config.PLATFORM_PROFILE[platform]
    sels = config.PLATFORM_POST_SELECTORS[platform]
    login_cookies = set(config.PLATFORM_LOGIN_COOKIES.get(platform, []))
    text = lead.comment

    def _find(page, candidates):
        for sel in candidates:
            loc = page.locator(sel).first
            try:
                if loc.count() > 0:
                    return loc
            except Exception:  # noqa: BLE001
                continue
        return None

    try:
        with hb.persistent_context(profile, headless=False) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(config.PLATFORM_HOME[platform], wait_until="domcontentloaded", timeout=40000)
            hb.human_pause(2, 4)
            if login_cookies and not any(c.get("name") in login_cookies for c in ctx.cookies()):
                log.error("[%s] 未登录，无法发布。先 python -m fc_promotion.login_cli %s", platform, platform)
                return False
            page.goto(lead.url, wait_until="domcontentloaded", timeout=40000)
            hb.human_pause(2, 4)
            hb.human_scroll(page, times=random.randint(2, 4))

            opener = _find(page, sels["open"])
            if opener is None:
                log.error("[%s] 未找到评论/回答入口，跳过：%s", platform, lead.url)
                return False
            try:
                opener.click()
            except Exception:  # noqa: BLE001
                pass
            hb.human_pause(1.5, 3)

            editor = _find(page, sels["editor"])
            if editor is None:
                log.error("[%s] 未找到编辑器，跳过：%s", platform, lead.url)
                return False
            hb.human_type(page, editor, text)
            hb.human_pause(1.5, 3)

            submit = _find(page, sels["submit"])
            if submit is None:
                log.error("[%s] 未找到发送按钮，跳过（内容未提交）：%s", platform, lead.url)
                return False
            submit.click()
            hb.human_pause(2, 4)
            log.info("[%s] 已提交评论：%s", platform, lead.url)
            return True
    except Exception as exc:  # noqa: BLE001
        log.error("[%s] 发布失败：%s", platform, exc)
        return False


def _make_generic_searcher(platform: str):
    def _s(keywords: list[str], limit: int) -> list[Lead]:
        return generic_search_leads(platform, keywords, limit)
    return _s


# 注册通用平台（酷安/头条/小红书）
for _p in ("coolapk", "toutiao", "xiaohongshu"):
    SEARCHERS[_p] = _make_generic_searcher(_p)


def post_for_platform(platform: str, lead: Lead) -> bool:
    """按平台分派发布：知乎用专用实现，其余用通用实现。"""
    if platform == "zhihu":
        return post_comment_zhihu(lead)
    return generic_post_comment(platform, lead)


def write_to_feishu(leads: list[Lead]) -> None:
    """把推广记录写入飞书推广数据库多维表格。"""
    if not leads:
        return
    bitable = FeishuBitable()
    app_token = bitable.resolve_app_token(config.FEISHU_PROMO_URL)
    # 首次运行先核对字段名，避免字段不匹配写入失败
    try:
        names = bitable.list_field_names(app_token=app_token, table_id=config.FEISHU_PROMO_TABLE_ID)
        log.info("推广数据库字段：%s", names)
    except Exception as exc:  # noqa: BLE001
        log.warning("读取飞书字段失败（继续尝试写入）：%s", exc)
    today = dt.date.today().isoformat()
    for lead in leads:
        fields = {
            config.FIELD_DATE: today,
            config.FIELD_PLATFORM: lead.platform,
            config.FIELD_TARGET_TITLE: lead.title,
            config.FIELD_TARGET_URL: {"link": lead.url, "text": lead.url},
            config.FIELD_COMMENT: lead.comment,
            config.FIELD_STATUS: lead.status,
        }
        try:
            rec = bitable.append_record(
                app_token=app_token,
                table_id=config.FEISHU_PROMO_TABLE_ID,
                fields=fields,
            )
            log.info("写入飞书成功 record=%s %s", rec, lead.title[:30])
        except Exception as exc:  # noqa: BLE001
            log.error("写入飞书失败：%s | %s", exc, lead.title[:30])


def _upload_zhihu_images(page, editor) -> None:
    """把文案中的三张本地图片逐张上传到知乎编辑器。

    知乎不会解析 Markdown 本地路径；set_input_files 后需等待图片节点
    从 blob URL 变成知乎图片 CDN URL，才能继续发布。
    """
    from pathlib import Path

    image_input = page.locator("input[type='file'][accept*='image']").first
    if image_input.count() == 0:
        raise RuntimeError("知乎回答编辑器中未找到图片上传 input")
    for _, ref in config.PROMO_IMAGE_REFS:
        path = config.PROMO_ASSET_DIR / Path(ref).name
        if not path.exists():
            raise FileNotFoundError(f"知乎推广图片不存在：{path}")
        remote = False
        for attempt in range(1, 4):
            before = editor.locator("img").count()
            image_input.set_input_files(str(path), timeout=15000)
            deadline = time.time() + 30
            while time.time() < deadline:
                images = editor.locator("img")
                for index in range(before, images.count()):
                    src = images.nth(index).get_attribute("src") or ""
                    if src.startswith(("https://", "http://")) and "zhimg.com" in src:
                        remote = True
                        break
                if remote:
                    break
                page.wait_for_timeout(500)
            if remote:
                break
            log.warning("知乎图片上传等待超时，准备重试(%d/3)：%s", attempt, path.name)
        if not remote:
            raise RuntimeError(f"知乎图片上传未完成：{path.name}")
        log.info("知乎推广图片已上传：%s", path.name)


def post_comment_zhihu(lead: Lead) -> bool:
    """用持久化 profile（拟人化）在知乎问题下写一条简短回答并发布。

    发布动作：打开问题页 → 拟人滚动 → 点"写回答" → 逐字输入文案 → 点"发布回答"。
    知乎 DOM 会改版，关键节点用多候选选择器兜底；任一环节失败则返回 False（不误发）。
    """
    from .common import humanized_browser as hb

    text = lead.comment
    try:
        with hb.persistent_context(config.ZHIHU_PROFILE, headless=_headless_mode()) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.zhihu.com/", wait_until="domcontentloaded", timeout=40000)
            hb.human_pause(2, 4)
            if not any(c.get("name") == "z_c0" for c in ctx.cookies()):
                log.error("知乎未登录，无法发布。先 python -m fc_promotion.login_cli zhihu")
                return False

            # 规范到问题主页（去掉 /answer/xxx 尾巴，回答入口在问题页）
            qurl = lead.url.split("/answer/")[0]
            page.goto(qurl, wait_until="domcontentloaded", timeout=40000)
            hb.human_pause(2, 4)
            if "40362" in (page.title() or "") or page.locator("text=请求存在异常").count() > 0:
                log.error("打开问题页仍触发风控，跳过：%s", qurl)
                return False
            hb.human_scroll(page, times=random.randint(2, 4))

            # 0) 已回答过的问题：只会显示"我的回答/编辑回答"，没有"写回答"，直接跳过换下一条
            has_write = any(
                page.locator(s).first.count() > 0
                for s in ("button:has-text('写回答')", "a:has-text('写回答')")
            )
            answered = any(
                page.locator(s).first.count() > 0
                for s in ("a:has-text('我的回答')", "button:has-text('编辑回答')",
                          "button:has-text('编辑我的回答')", "button:has-text('继续编辑')")
            )
            if not has_write and answered:
                log.info("该问题已回答过，跳过换下一条：%s", qurl)
                return False

            # 1) 点"写回答"
            write_btn = None
            for sel in ("button:has-text('写回答')", "a:has-text('写回答')", ".QuestionHeaderActions button:has-text('回答')"):
                loc = page.locator(sel).first
                if loc.count() > 0:
                    write_btn = loc
                    break
            if write_btn is None:
                log.error("未找到'写回答'入口（可能已回答/未登录/页面改版），跳过：%s", qurl)
                return False
            write_btn.click()
            hb.human_pause(1.5, 3)

            # 2) 定位编辑器并逐字输入
            editor = None
            for sel in (".public-DraftEditor-content", "div[contenteditable='true']", ".Editable-content"):
                loc = page.locator(sel).first
                if loc.count() > 0:
                    editor = loc
                    break
            if editor is None:
                log.error("未找到回答编辑器，跳过：%s", qurl)
                return False
            # Markdown 图片引用仅用于飞书记录；知乎编辑器必须通过文件 input 上传。
            text_only = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text).strip()
            hb.human_type(page, editor, text_only)
            _upload_zhihu_images(page, editor)
            hb.human_pause(1.5, 3)

            # 3) 点"发布回答"
            pub = None
            for sel in ("button:has-text('发布回答')", "button:has-text('发布')", ".AnswerAdd button:has-text('发布')"):
                loc = page.locator(sel).first
                if loc.count() > 0:
                    pub = loc
                    break
            if pub is None:
                log.error("未找到'发布'按钮，跳过（内容未提交）：%s", qurl)
                return False
            pub.click()
            hb.human_pause(2, 4)
            log.info("已提交回答：%s", qurl)
            return True
    except Exception as exc:  # noqa: BLE001
        log.error("发布失败：%s", exc)
        return False


def run(platform: str, *, max_leads: int, post: bool, to_feishu: bool) -> list[Lead]:
    searcher = SEARCHERS.get(platform)
    if searcher is None:
        raise SystemExit(f"平台 {platform} 的搜索器尚未接入；已接入：{list(SEARCHERS)}")

    # 发布模式下多抓候选线索（需要备选来跳过已回答的问题）；dry-run 用 max_leads。
    fetch_n = max_leads if not post else max(max_leads, config.CANDIDATE_POOL)
    leads = searcher(config.SEARCH_KEYWORDS, fetch_n)
    for lead in leads:
        lead.comment = copywriter.generate_comment(question_title=lead.title, platform=platform)

    if post:
        # B1：本次运行随机发 1~3 条，发一条停 60 秒再发下一条。
        # 只有"成功发布"才计入配额；遇到已回答/失败则换下一条继续尝试，直到满配额或线索用尽。
        quota = random.randint(config.DAILY_MIN_COMMENTS, config.DAILY_MAX_COMMENTS)
        quota = min(quota, max_leads)
        log.info("本次计划发布 %d 条（每天随机 1~3，间隔 %d 秒）；候选线索 %d 条",
                 quota, config.MIN_SECONDS_BETWEEN, len(leads))
        posted = 0
        for lead in leads:
            if posted >= quota:
                lead.status = "未安排（已达今日配额）"
                continue
            ok = post_for_platform(platform, lead)
            if ok:
                lead.status = "已发布"
                posted += 1
                if posted < quota:
                    time.sleep(config.MIN_SECONDS_BETWEEN)
            else:
                lead.status = "跳过（已回答/失败）"
        if posted < quota:
            log.warning("仅发布 %d/%d 条：候选线索不足或多为已回答问题，建议扩充关键词", posted, quota)
    else:
        for lead in leads:
            lead.status = "待人工发布（dry-run）"

    if to_feishu:
        write_to_feishu(leads)
    return leads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="悬浮时钟跨平台推广")
    parser.add_argument("--platform", default="zhihu", help="平台（默认 zhihu）")
    parser.add_argument("--max", type=int, default=config.MAX_COMMENTS_PER_RUN, help="最多处理线索数")
    parser.add_argument("--post", action="store_true", help="真正用本人账号发评论（默认只预览）")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不发布、不写飞书")
    parser.add_argument("--no-feishu", action="store_true", help="不写飞书")
    parser.add_argument(
        "--require-android-hint",
        action="store_true",
        help="更严：标题必须含安卓/手机等正向信号才保留（召回更少但更准）",
    )
    args = parser.parse_args(argv)

    if args.require_android_hint:
        config.REQUIRE_ANDROID_HINT = True

    to_feishu = not (args.dry_run or args.no_feishu)
    post = args.post and not args.dry_run

    leads = run(args.platform, max_leads=args.max, post=post, to_feishu=to_feishu)

    print(f"\n==== 共 {len(leads)} 条推广线索（platform={args.platform}）====")
    for i, lead in enumerate(leads, 1):
        print(f"\n[{i}] {lead.title}\n  {lead.url}\n  状态：{lead.status}\n  文案：{lead.comment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
