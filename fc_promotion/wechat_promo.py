"""公众号推广软文 → 保存为草稿。

公众号是封闭生态，没有"搜别人内容去评论"的入口，只能发自有内容。
本模块生成一篇悬浮时钟推广软文（复用 copywriter 的卖点与原样邀请文本），
调用 zhihu 项目已有的、经过验证的 `publish_wechat_article` 存到**草稿箱**
（绝不直接群发：现有发布器强制 publish_action=draft）。

用法：
    # 仅生成 markdown 预览，不碰公众号
    python -m fc_promotion.wechat_promo --dry-run
    # 生成并填入公众号编辑器但不保存（需本机已登录公众号）
    python -m fc_promotion.wechat_promo --preview
    # 生成并保存为草稿（需本机已登录公众号）
    python -m fc_promotion.wechat_promo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, copywriter
from .common.logging_utils import get_logger

log = get_logger("wechat_promo")

TITLE = "手机屏幕上加一个带秒的悬浮时钟，看时间不用再退出应用"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_article_markdown() -> tuple[str, str]:
    """返回 (title, body_markdown)。正文=软文介绍 + 卖点 + 原样邀请文本。"""
    points = "\n".join(f"- {p}" for p in config.SELLING_POINTS)
    body = (
        "刷视频、打游戏、上网课的时候想看一眼时间，还得退出来或下拉状态栏？\n\n"
        "给安卓手机加一个**带秒的悬浮时钟**就能解决：时间浮在所有应用最上层，"
        "一眼就能看到，还精确到秒。\n\n"
        f"## 它有什么好\n\n{points}\n\n"
        "## 怎么用\n\n"
        "装上后开启悬浮开关即可；位置能拖、能锁定（锁定后触摸穿透，不挡你操作），"
        "字号/颜色/透明度都能调。\n\n"
        "## 下载与试用\n\n"
        f"{copywriter._invite_text()}\n\n"
        "## 实际使用和设置\n\n"
        "桌面、阅读和设置页的效果如下：\n\n"
        f"{copywriter.image_markdown()}\n"
    )
    return TITLE, body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="公众号悬浮时钟推广软文（存草稿）")
    parser.add_argument("--dry-run", action="store_true", help="只输出 markdown，不碰公众号")
    parser.add_argument("--preview", action="store_true", help="填入编辑器但不保存草稿")
    parser.add_argument("--save-md", help="同时把 markdown 写到该路径（如 docs/pending/xxx.md）")
    args = parser.parse_args(argv)

    title, body = build_article_markdown()
    md_full = f"# {title}\n\n{body}"

    if args.save_md:
        Path(args.save_md).write_text(md_full, encoding="utf-8")
        log.info("已写入 markdown：%s", args.save_md)

    if args.dry_run:
        print(md_full)
        return 0

    # 复用 zhihu 项目已验证的公众号发布器（强制存草稿，不群发）
    try:
        from src.wechat_article_publisher import publish_wechat_article  # type: ignore
    except Exception as exc:  # noqa: BLE001
        log.error("无法导入公众号发布器（需在 zhihu 项目根目录、PYTHONPATH=. 运行）：%s", exc)
        return 1

    url = publish_wechat_article(
        title,
        body,
        # 宽图适合作为公众号封面，正文中的三张图由 source_dir 上传并替换。
        cover_path=config.PROMO_ASSET_DIR / "shot_home.jpg",
        source_dir=PROJECT_ROOT,
        dry_run=args.preview,
    )
    if args.preview:
        log.info("预览完成（未保存草稿），编辑页：%s", url)
    else:
        log.info("已保存公众号草稿：%s", url)
    print(f"title: {title}\nresult_url: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
