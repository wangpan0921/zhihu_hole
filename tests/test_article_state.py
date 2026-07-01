from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import article_state as st  # noqa: E402


def _patch_dirs(tmp_path, monkeypatch):
    pending = tmp_path / "docs" / "pending"
    published = tmp_path / "docs" / "published"
    pending.mkdir(parents=True)
    monkeypatch.setattr(st, "DOCS_PENDING", pending)
    monkeypatch.setattr(st, "DOCS_PUBLISHED", published)
    return pending, published


def test_pending_files_unpublished_for_skips_only_same_platform(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    published.mkdir(parents=True)
    article = pending / "article.md"
    article.write_text("# 标题", encoding="utf-8")
    st.write_platform_meta(article, "wechat", {"platform": "wechat_mp"})

    assert st.pending_files_unpublished_for("wechat") == []
    assert st.pending_files_unpublished_for("zhihu") == [article]


def test_archive_waits_until_both_platforms_have_meta(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    article = pending / "article.md"
    article.write_text("# 标题", encoding="utf-8")

    st.write_platform_meta(article, "wechat", {"platform": "wechat_mp"})
    assert st.archive_if_complete(article) is None
    assert article.exists()

    st.write_platform_meta(article, "zhihu", {"platform": "zhihu"})
    archived = st.archive_if_complete(article)

    assert archived == published / "article.md"
    assert archived.exists()
    assert not article.exists()
    assert (published / "article.wechat.meta.json").exists()
    assert (published / "article.meta.json").exists()
