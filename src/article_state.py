"""Shared state for publishing docs/pending articles to multiple platforms."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .utils import PROJECT_ROOT, get_logger

log = get_logger("article_state")

DOCS_PENDING = PROJECT_ROOT / "docs" / "pending"
DOCS_PUBLISHED = PROJECT_ROOT / "docs" / "published"

PLATFORMS = ("zhihu", "wechat")
META_SUFFIXES = {
    "zhihu": ".meta.json",
    "wechat": ".wechat.meta.json",
}


def platform_meta_path(source: Path, platform: str) -> Path:
    return DOCS_PUBLISHED / f"{source.stem}{META_SUFFIXES[platform]}"


def is_platform_published(source: Path, platform: str) -> bool:
    return platform_meta_path(source, platform).exists()


def both_platforms_published(source: Path) -> bool:
    return all(is_platform_published(source, platform) for platform in PLATFORMS)


def pending_files_unpublished_for(platform: str) -> list[Path]:
    DOCS_PENDING.mkdir(parents=True, exist_ok=True)
    files = [p for p in DOCS_PENDING.glob("*.md") if not is_platform_published(p, platform)]
    files.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return files


def write_platform_meta(source: Path, platform: str, payload: dict[str, Any]) -> Path:
    DOCS_PUBLISHED.mkdir(parents=True, exist_ok=True)
    meta_path = platform_meta_path(source, platform)
    meta_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("已写 %s 元数据：%s", platform, meta_path)
    return meta_path


def archive_if_complete(source: Path) -> Path | None:
    """Move source md to docs/published only after both platforms have meta markers."""
    if not both_platforms_published(source):
        missing = [p for p in PLATFORMS if not is_platform_published(source, p)]
        log.info("暂不归档 %s，等待平台发布：%s", source.name, ", ".join(missing))
        return None

    DOCS_PUBLISHED.mkdir(parents=True, exist_ok=True)
    archived = DOCS_PUBLISHED / source.name
    if archived.exists():
        log.info("源文件已在 published：%s", archived)
        if source.exists():
            source.unlink()
        return archived

    source.rename(archived)
    log.info("知乎和公众号都已发布，已归档：%s", archived)
    return archived
