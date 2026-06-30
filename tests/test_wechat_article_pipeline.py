from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import wechat_article_pipeline as wp  # noqa: E402


def test_extract_title_and_body_from_h1():
    title, body = wp._extract_title_and_body("# 标题\n\n正文", "fallback")

    assert title == "标题"
    assert body == "正文"


def test_extract_title_falls_back_to_filename():
    title, body = wp._extract_title_and_body("正文第一行\n\n第二行", "file-name")

    assert title == "file-name"
    assert body == "正文第一行\n\n第二行"


def test_publish_one_pending_archives_oldest(tmp_path, monkeypatch):
    pending = tmp_path / "docs" / "pending"
    published = tmp_path / "docs" / "published"
    pending.mkdir(parents=True)

    older = pending / "older.md"
    newer = pending / "newer.md"
    older.write_text("# 旧文\n\n正文", encoding="utf-8")
    newer.write_text("# 新文\n\n正文", encoding="utf-8")

    older_mtime = older.stat().st_mtime - 10
    newer_mtime = newer.stat().st_mtime
    os.utime(older, (older_mtime, older_mtime))
    os.utime(newer, (newer_mtime, newer_mtime))

    monkeypatch.setattr(wp, "DOCS_PENDING", pending)
    monkeypatch.setattr(wp, "DOCS_PUBLISHED", published)

    calls = []

    def fake_publish(title, body, *, dry_run=False):
        calls.append((title, body, dry_run))
        return "https://mp.weixin.qq.com/s/test"

    monkeypatch.setattr(wp, "publish_wechat_article", fake_publish)

    url = wp.publish_one_pending_to_wechat()

    assert url == "https://mp.weixin.qq.com/s/test"
    assert calls == [("旧文", "正文", False)]
    assert not older.exists()
    assert newer.exists()
    assert (published / "older.md").exists()

    meta = json.loads((published / "older.wechat.meta.json").read_text(encoding="utf-8"))
    assert meta["title"] == "旧文"
    assert meta["platform"] == "wechat_mp"
    assert meta["article_url"] == "https://mp.weixin.qq.com/s/test"


def test_dry_run_does_not_archive(tmp_path, monkeypatch):
    pending = tmp_path / "docs" / "pending"
    published = tmp_path / "docs" / "published"
    pending.mkdir(parents=True)
    article = pending / "article.md"
    article.write_text("# 标题\n\n正文", encoding="utf-8")

    monkeypatch.setattr(wp, "DOCS_PENDING", pending)
    monkeypatch.setattr(wp, "DOCS_PUBLISHED", published)
    monkeypatch.setattr(
        wp,
        "publish_wechat_article",
        lambda title, body, *, dry_run=False: "draft-url",
    )

    url = wp.publish_one_pending_to_wechat(dry_run=True)

    assert url == "draft-url"
    assert article.exists()
    assert not published.exists()
