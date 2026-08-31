#!/usr/bin/env python3
"""Publish a specific kid_coding lesson to Zhihu article and/or WeChat MP.

Examples:
    python scripts/publish_kid_coding_lesson.py --lesson 4 --platform both --dry-run
    python scripts/publish_kid_coding_lesson.py --lesson 4 --platform wechat
    python scripts/publish_kid_coding_lesson.py --lesson 4 --platform zhihu

By default this script requires a final article file named lesson_*.md in the
lesson directory. Use --allow-draft to publish article.md when no final exists.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import get_logger, load_env  # noqa: E402
from src.wechat_article_publisher import publish_wechat_article  # noqa: E402
from src.zhihu_article_publisher import publish_article  # noqa: E402

log = get_logger("publish_kid_coding_lesson")

LESSON_DIR_RE = re.compile(r"lesson-(\d+)-(.+)")


def _extract_title_and_body(md_text: str, fallback_title: str) -> Tuple[str, str]:
    """Extract the first H1 as title and remove it from the body."""
    lines = md_text.splitlines()
    title: Optional[str] = None
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() == "":
            continue
        stripped = line.lstrip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            body_start = i + 1
        break

    body = "\n".join(lines[body_start:]).lstrip("\n")
    return (title or fallback_title), body


def _lesson_dirs(kid_root: Path) -> list[tuple[int, str, Path]]:
    out: list[tuple[int, str, Path]] = []
    if not kid_root.exists():
        return out
    for p in kid_root.glob("lesson-*"):
        if not p.is_dir():
            continue
        m = LESSON_DIR_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), m.group(2), p))
    return sorted(out)


def _find_lesson_dir(kid_root: Path, lesson: int) -> Path:
    matches = [p for num, _slug, p in _lesson_dirs(kid_root) if num == lesson]
    if not matches:
        available = ", ".join(f"{num:02d}" for num, _slug, _p in _lesson_dirs(kid_root))
        raise FileNotFoundError(
            f"未找到第 {lesson} 课目录：{kid_root}/lesson-{lesson:02d}-*"
            + (f"。当前可用课程：{available}" if available else "")
        )
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise RuntimeError(f"第 {lesson} 课匹配到多个目录，请先清理：{names}")
    return matches[0]


def _select_article_file(lesson_dir: Path, lesson: int, *, allow_draft: bool) -> Path:
    finals = sorted(lesson_dir.glob(f"lesson_{lesson:02d}_*.md"))
    if not finals:
        finals = sorted(lesson_dir.glob("lesson_*.md"))
    if len(finals) == 1:
        return finals[0]
    if len(finals) > 1:
        names = ", ".join(p.name for p in finals)
        raise RuntimeError(f"找到多个定稿文件，请只保留一个或手动指定逻辑：{names}")

    draft = lesson_dir / "article.md"
    if allow_draft and draft.exists():
        log.warning("未找到 lesson_*.md，因 --allow-draft 使用草稿：%s", draft)
        return draft

    raise FileNotFoundError(
        f"未找到第 {lesson} 课定稿文件 lesson_{lesson:02d}_*.md。"
        "如确认要发布草稿 article.md，请加 --allow-draft。"
    )


def _platforms(value: str) -> list[str]:
    if value == "both":
        return ["wechat", "zhihu"]
    return [value]


def _write_meta(
    lesson_dir: Path,
    lesson: int,
    platform: str,
    *,
    article_file: Path,
    title: str,
    url: Optional[str],
) -> Path:
    meta_dir = lesson_dir / "publish_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "lesson": lesson,
        "platform": platform,
        "title": title,
        "source_file": article_file.name,
        "article_url": url,
        "published_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    out = meta_dir / f"lesson_{lesson:02d}.{platform}.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def publish_lesson(
    lesson: int,
    *,
    platform: str,
    kid_root: Path,
    allow_draft: bool,
    dry_run: bool,
) -> dict[str, Optional[str]]:
    load_env()
    lesson_dir = _find_lesson_dir(kid_root, lesson)
    article_file = _select_article_file(lesson_dir, lesson, allow_draft=allow_draft)
    md_text = article_file.read_text(encoding="utf-8")
    title, body = _extract_title_and_body(md_text, fallback_title=article_file.stem)

    log.info("课程目录：%s", lesson_dir)
    log.info("发布文件：%s", article_file.name)
    log.info("标题：%s | 正文 %d 字", title, len(body))

    results: dict[str, Optional[str]] = {}
    for target in _platforms(platform):
        log.info("开始发布到 %s%s", target, "（dry-run）" if dry_run else "")
        if target == "wechat":
            url = publish_wechat_article(title, body, dry_run=dry_run)
        elif target == "zhihu":
            url = publish_article(
                title,
                body,
                dry_run=dry_run,
                source_dir=article_file.parent,
                image_cache_path=article_file.with_suffix(".zhihu.images.json"),
            )
        else:  # argparse prevents this, keep explicit for type safety.
            raise ValueError(f"未知平台：{target}")
        results[target] = url
        log.info("%s 返回 URL：%s", target, url)
        if not dry_run:
            meta = _write_meta(
                lesson_dir,
                lesson,
                target,
                article_file=article_file,
                title=title,
                url=url,
            )
            log.info("已写发布记录：%s", meta)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="发布 kid_coding 指定课程到微信公众号和/或知乎专栏。"
    )
    parser.add_argument("--lesson", "-l", type=int, required=True, help="课程编号，例如 4")
    parser.add_argument(
        "--platform",
        "-p",
        choices=["wechat", "zhihu", "both"],
        default="wechat",
        help="发布平台，默认 wechat",
    )
    parser.add_argument(
        "--kid-root",
        type=Path,
        default=PROJECT_ROOT / "kid_coding",
        help="kid_coding 根目录，默认项目内 kid_coding/",
    )
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="没有 lesson_*.md 定稿时，允许发布 article.md 草稿",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只填入编辑器，不点击最终发布/保存，也不写发布记录",
    )
    args = parser.parse_args()

    try:
        results = publish_lesson(
            args.lesson,
            platform=args.platform,
            kid_root=args.kid_root,
            allow_draft=args.allow_draft,
            dry_run=args.dry_run,
        )
    except Exception as e:  # noqa: BLE001
        log.exception("发布失败：%s", e)
        return 1

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
