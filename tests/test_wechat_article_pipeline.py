from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import article_state as st  # noqa: E402
from src import wechat_article_pipeline as wp  # noqa: E402


def _patch_dirs(tmp_path, monkeypatch):
    pending = tmp_path / "docs" / "pending"
    published = tmp_path / "docs" / "published"
    pending.mkdir(parents=True)
    monkeypatch.setattr(st, "DOCS_PENDING", pending)
    monkeypatch.setattr(st, "DOCS_PUBLISHED", published)
    return pending, published


def test_extract_title_and_body_from_h1():
    title, body = wp._extract_title_and_body("# 标题\n\n正文", "fallback")

    assert title == "标题"
    assert body == "正文"


def test_extract_title_falls_back_to_filename():
    title, body = wp._extract_title_and_body("正文第一行\n\n第二行", "file-name")

    assert title == "file-name"
    assert body == "正文第一行\n\n第二行"


def test_wechat_first_keeps_source_until_zhihu_meta_exists(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    article = pending / "article.md"
    article.write_text("# 公众号文\n\n正文", encoding="utf-8")

    monkeypatch.setattr(
        wp,
        "publish_wechat_article",
        lambda title, body, *, dry_run=False: "https://mp.weixin.qq.com/s/test",
    )

    url = wp.publish_one_pending_to_wechat()

    assert url == "https://mp.weixin.qq.com/s/test"
    assert article.exists()
    assert not (published / "article.md").exists()
    meta = json.loads((published / "article.wechat.meta.json").read_text(encoding="utf-8"))
    assert meta["title"] == "公众号文"
    assert meta["platform"] == "wechat_mp"


def test_wechat_archives_when_zhihu_meta_already_exists(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    article = pending / "article.md"
    article.write_text("# 公众号文\n\n正文", encoding="utf-8")
    st.write_platform_meta(article, "zhihu", {"platform": "zhihu"})

    monkeypatch.setattr(
        wp,
        "publish_wechat_article",
        lambda title, body, *, dry_run=False: "https://mp.weixin.qq.com/s/test",
    )

    wp.publish_one_pending_to_wechat()

    assert not article.exists()
    assert (published / "article.md").exists()
    assert (published / "article.meta.json").exists()
    assert (published / "article.wechat.meta.json").exists()


def test_skips_pending_file_that_already_has_wechat_meta(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    published.mkdir(parents=True)

    older = pending / "older.md"
    newer = pending / "newer.md"
    older.write_text("# 旧文\n\n正文", encoding="utf-8")
    newer.write_text("# 新文\n\n正文", encoding="utf-8")
    os.utime(older, (older.stat().st_mtime - 10, older.stat().st_mtime - 10))
    st.write_platform_meta(older, "wechat", {"platform": "wechat_mp"})

    calls = []

    def fake_publish(title, body, *, dry_run=False):
        calls.append((title, body, dry_run))
        return "https://mp.weixin.qq.com/s/newer"

    monkeypatch.setattr(wp, "publish_wechat_article", fake_publish)

    url = wp.publish_one_pending_to_wechat()

    assert url == "https://mp.weixin.qq.com/s/newer"
    assert calls == [("新文", "正文", False)]
    assert older.exists()
    assert newer.exists()
    assert (published / "newer.wechat.meta.json").exists()


def test_dry_run_does_not_write_meta_or_archive(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    article = pending / "article.md"
    article.write_text("# 标题\n\n正文", encoding="utf-8")

    monkeypatch.setattr(
        wp,
        "publish_wechat_article",
        lambda title, body, *, dry_run=False: "draft-url",
    )

    url = wp.publish_one_pending_to_wechat(dry_run=True)

    assert url == "draft-url"
    assert article.exists()
    assert not published.exists()
