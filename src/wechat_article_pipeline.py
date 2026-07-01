"""docs/pending → 微信公众号文章发布流水线。"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional, Tuple

from .article_state import (
    archive_if_complete,
    pending_files_unpublished_for,
    write_platform_meta,
)
from .utils import get_logger
from .wechat_article_publisher import publish_wechat_article

log = get_logger("wechat_article_pipeline")


def _extract_title_and_body(md_text: str, fallback_title: str) -> Tuple[str, str]:
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


def _pick_oldest_pending() -> Optional[Path]:
    files = pending_files_unpublished_for("wechat")
    return files[0] if files else None


def publish_one_pending_to_wechat(*, dry_run: bool = False) -> Optional[str]:
    """从 docs/pending 选一篇发布到微信公众号。

    返回 None 表示没有待发布文章；dry_run 不归档。
    """
    target = _pick_oldest_pending()
    if target is None:
        log.info("docs/pending 没有未发公众号的 .md，跳过本次微信公众号发布")
        return None

    all_count = len(pending_files_unpublished_for("wechat"))
    log.info("微信公众号待发数=%d（按规则只发一篇），选中：%s", all_count, target.name)

    md_text = target.read_text(encoding="utf-8")
    title, body = _extract_title_and_body(md_text, fallback_title=target.stem)
    log.info("微信公众号标题：%s | 正文 %d 字", title, len(body))

    article_url = publish_wechat_article(title, body, dry_run=dry_run)

    if dry_run:
        log.info("dry_run=True，不归档；编辑 URL=%s", article_url)
        return article_url

    meta = {
        "title": title,
        "source_file": target.name,
        "published_at": dt.datetime.now().isoformat(timespec="seconds"),
        "article_url": article_url,
        "platform": "wechat_mp",
    }
    write_platform_meta(target, "wechat", meta)
    archive_if_complete(target)
    return article_url
