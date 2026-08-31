"""Publish the training-efficiency series from its independent article queue.

The series deliberately does not reuse the project-wide docs queue: it has its
own draft/pending/published directories, target Zhihu column, and metadata.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Optional

from .utils import PROJECT_ROOT, get_logger, load_config

log = get_logger("training_efficiency_pipeline")

DEFAULT_ROOT = PROJECT_ROOT / "pytorch_training_efficiency" / "docs"
META_SUFFIXES = {
    "zhihu": ".zhihu.meta.json",
    "wechat": ".wechat.meta.json",
}


def _config() -> dict[str, Any]:
    config = load_config().get("training_efficiency") or {}
    root = PROJECT_ROOT / str(config.get("root_dir", "pytorch_training_efficiency/docs"))
    return {
        "root": root,
        "zhihu_column_name": str(config.get("zhihu_column_name", "训练效能工程成长记录")),
        "wechat_album_name": str(config.get("wechat_album_name", "训练效能工程成长记录")),
    }


def _dirs() -> dict[str, Path]:
    root = _config()["root"]
    result = {
        "root": root,
        "draft": root / "draft",
        "pending": root / "pending",
        "published": root / "published",
    }
    for path in result.values():
        path.mkdir(parents=True, exist_ok=True)
    return result


def _extract_title_and_body(md_text: str, fallback_title: str) -> tuple[str, str]:
    lines = md_text.splitlines()
    title: Optional[str] = None
    body_start = 0
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        stripped = line.lstrip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            body_start = index + 1
        break
    return title or fallback_title, "\n".join(lines[body_start:]).lstrip("\n")


def _meta_path(source: Path, platform: str, published_dir: Path) -> Path:
    return published_dir / f"{source.stem}{META_SUFFIXES[platform]}"


def _is_done(source: Path, platform: str, published_dir: Path) -> bool:
    return _meta_path(source, platform, published_dir).exists()


def _pick_oldest(pending_dir: Path, published_dir: Path) -> Optional[Path]:
    files = [
        path
        for path in pending_dir.glob("*.md")
        if not (_is_done(path, "zhihu", published_dir) and _is_done(path, "wechat", published_dir))
    ]
    files.sort(key=lambda path: (path.stat().st_mtime, path.name))
    return files[0] if files else None


def _write_meta(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("已写发布元数据：%s", path)


def _publish_zhihu(title: str, body: str, source: Path, published_dir: Path, *, dry_run: bool) -> Optional[str]:
    from .zhihu_article_publisher import publish_article

    cfg = _config()
    url = publish_article(
        title,
        body,
        dry_run=dry_run,
        column_name=cfg["zhihu_column_name"],
        source_dir=source.parent,
        image_cache_path=source.with_suffix(".zhihu.images.json"),
    )
    if not dry_run:
        _write_meta(
            _meta_path(source, "zhihu", published_dir),
            {
                "title": title,
                "source_file": source.name,
                "published_at": dt.datetime.now().isoformat(timespec="seconds"),
                "article_url": url,
                "column": cfg["zhihu_column_name"],
                "platform": "zhihu",
            },
        )
    return url


def _publish_wechat(title: str, body: str, source: Path, published_dir: Path, *, dry_run: bool) -> Optional[str]:
    from .wechat_article_publisher import publish_wechat_article

    cfg = _config()
    # 课程正文旁的截图是最可靠的系列封面候选；按文件名稳定选择。
    cover_candidates = sorted(
        path for path in source.parent.iterdir()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    cover_path = cover_candidates[0] if cover_candidates else None
    if not dry_run and cover_path is None:
        raise RuntimeError(f"微信公众号封面不存在，请将图片放入：{source.parent}")
    if cover_path is not None:
        log.info("微信公众号封面：%s", cover_path)
    url = publish_wechat_article(title, body, cover_path=cover_path, dry_run=dry_run)
    if not dry_run:
        _write_meta(
            _meta_path(source, "wechat", published_dir),
            {
                "title": title,
                "source_file": source.name,
                "published_at": dt.datetime.now().isoformat(timespec="seconds"),
                "article_url": url,
                "album": cfg["wechat_album_name"],
                "album_status": "published_as_article;_album_membership_requires_backend_support_or_manual_check",
                "platform": "wechat_mp",
            },
        )
    return url


def repair_zhihu_meta(article_url: str, *, filename: Optional[str] = None) -> dict[str, Any]:
    """Record a Zhihu article confirmed published before verification failed.

    Metadata-only repair: never opens a browser or creates another article.
    """
    if not article_url.startswith(("https://zhuanlan.zhihu.com/", "http://zhuanlan.zhihu.com/")):
        raise ValueError("article_url must be a Zhihu column URL")
    dirs = _dirs()
    if filename:
        target = dirs["pending"] / filename
        if not target.is_file():
            raise FileNotFoundError(f"pending article not found: {target}")
    else:
        candidates = sorted(dirs["pending"].glob("*.md"), key=lambda path: (path.stat().st_mtime, path.name))
        if not candidates:
            raise FileNotFoundError("pending article not found")
        if len(candidates) > 1:
            raise ValueError("multiple pending articles; pass --file to identify the article")
        target = candidates[0]

    meta_path = _meta_path(target, "zhihu", dirs["published"])
    if meta_path.exists():
        log.info("知乎元数据已存在，跳过修复：%s", meta_path)
        return {"source": str(target), "zhihu_url": article_url, "metadata": str(meta_path), "already_exists": True}

    title, _ = _extract_title_and_body(target.read_text(encoding="utf-8"), target.stem)
    _write_meta(meta_path, {
        "title": title,
        "source_file": target.name,
        "published_at": dt.datetime.now().isoformat(timespec="seconds"),
        "article_url": article_url,
        "column": _config()["zhihu_column_name"],
        "platform": "zhihu",
        "repaired_after_post_publish_verification": True,
    })
    return {"source": str(target), "zhihu_url": article_url, "metadata": str(meta_path), "repaired": True}

def publish_one(*, dry_run: bool = False, platform: str = "both") -> Optional[dict[str, Any]]:
    """Publish at most one pending series article.

    ``dry_run`` only prints the selected article and never opens a browser.
    A real run writes a platform meta file after each successful platform and
    archives the Markdown only after both platform meta files exist.
    """
    if platform not in {"both", "zhihu", "wechat"}:
        raise ValueError("platform must be one of: both, zhihu, wechat")
    dirs = _dirs()
    target = _pick_oldest(dirs["pending"], dirs["published"])
    if target is None:
        log.info("训练效能系列 pending 没有待发布文章，跳过")
        return None

    title, body = _extract_title_and_body(target.read_text(encoding="utf-8"), target.stem)
    cfg = _config()
    result: dict[str, Any] = {
        "source": str(target),
        "title": title,
        "zhihu_column": cfg["zhihu_column_name"],
        "wechat_album": cfg["wechat_album_name"],
        "platform": platform,
    }
    log.info("选中训练效能系列文章：%s | %s", target.name, title)
    if dry_run:
        log.info("dry_run=True，不打开浏览器、不发布、不归档")
        return result

    if platform in {"both", "zhihu"} and not _is_done(target, "zhihu", dirs["published"]):
        result["zhihu_url"] = _publish_zhihu(title, body, target, dirs["published"], dry_run=False)
    if platform in {"both", "wechat"} and not _is_done(target, "wechat", dirs["published"]):
        result["wechat_url"] = _publish_wechat(title, body, target, dirs["published"], dry_run=False)

    if _is_done(target, "zhihu", dirs["published"]) and _is_done(target, "wechat", dirs["published"]):
        archived = dirs["published"] / target.name
        if target.exists():
            target.rename(archived)
        result["archived"] = str(archived)
        log.info("知乎专栏和公众号都已完成，归档：%s", archived)
    else:
        result["archived"] = None
        log.info("仍有平台未完成，源文件保留在 pending：%s", target)
    return result
