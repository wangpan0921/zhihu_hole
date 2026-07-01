"""docs/pending → 知乎专栏 文章发布流水线。

约定：
- docs/pending/*.md  → 待发布文章；每次只挑**一篇**（按修改时间最旧的优先）
- docs/published/    → 发布成功后的归档目录；同时写一份 {stem}.meta.json
- docs/pending 为空 → 不报错，直接返回 None

标题取自 markdown 第一行 `# 标题`，没有就用文件名（不含扩展）。
"""
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
from .zhihu_article_publisher import publish_article

log = get_logger("article_pipeline")


def _extract_title_and_body(md_text: str, fallback_title: str) -> Tuple[str, str]:
    """取第一行非空的内容；如果是 `# X` 则当 H1 抽出来并从正文删掉，否则全文当正文。"""
    lines = md_text.splitlines()
    title: Optional[str] = None
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() == "":
            continue
        stripped = line.lstrip()
        # 一级标题（不是 ## / ### …）
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            body_start = i + 1
        break  # 第一非空行处理完就退出（无论是 H1 还是别的）

    body = "\n".join(lines[body_start:])
    # 去掉抠出 H1 后开头多余的空行
    body = body.lstrip("\n")
    return (title or fallback_title), body


def _pick_oldest_pending() -> Optional[Path]:
    """从 docs/pending 选一个未发知乎的 .md：按 mtime 最旧优先。"""
    files = pending_files_unpublished_for("zhihu")
    return files[0] if files else None


def publish_one_pending(*, dry_run: bool = False) -> Optional[str]:
    """从 docs/pending 选一篇发布到知乎专栏。

    返回：
        - None：目录为空，啥也没发
        - str：已发布文章 URL（dry_run 时是 draft URL）
    """
    target = _pick_oldest_pending()
    if target is None:
        log.info("docs/pending 没有未发知乎的 .md，跳过本次发布")
        return None

    all_count = len(pending_files_unpublished_for("zhihu"))
    log.info("待发数=%d（按规则只发一篇），选中：%s", all_count, target.name)

    md_text = target.read_text(encoding="utf-8")
    title, body = _extract_title_and_body(md_text, fallback_title=target.stem)
    log.info("标题：%s | 正文 %d 字", title, len(body))

    article_url = publish_article(title, body, dry_run=dry_run)

    if dry_run:
        log.info("dry_run=True，不归档；draft URL=%s", article_url)
        return article_url

    meta = {
        "title": title,
        "source_file": target.name,
        "published_at": dt.datetime.now().isoformat(timespec="seconds"),
        "article_url": article_url,
        "column": "Agent工坊",
        "platform": "zhihu",
    }
    write_platform_meta(target, "zhihu", meta)
    archive_if_complete(target)
    return article_url
