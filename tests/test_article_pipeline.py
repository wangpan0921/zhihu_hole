from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import article_pipeline as zp  # noqa: E402
from src import article_state as st  # noqa: E402


def _patch_dirs(tmp_path, monkeypatch):
    pending = tmp_path / "docs" / "pending"
    published = tmp_path / "docs" / "published"
    pending.mkdir(parents=True)
    monkeypatch.setattr(st, "DOCS_PENDING", pending)
    monkeypatch.setattr(st, "DOCS_PUBLISHED", published)
    return pending, published


def test_zhihu_first_keeps_source_until_wechat_meta_exists(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    article = pending / "article.md"
    article.write_text("# 知乎文\n\n正文", encoding="utf-8")

    monkeypatch.setattr(
        zp,
        "publish_article",
        lambda title, body, *, dry_run=False: "https://zhuanlan.zhihu.com/p/test",
    )

    url = zp.publish_one_pending()

    assert url == "https://zhuanlan.zhihu.com/p/test"
    assert article.exists()
    assert not (published / "article.md").exists()
    meta = json.loads((published / "article.meta.json").read_text(encoding="utf-8"))
    assert meta["title"] == "知乎文"
    assert meta["platform"] == "zhihu"


def test_zhihu_archives_when_wechat_meta_already_exists(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    article = pending / "article.md"
    article.write_text("# 知乎文\n\n正文", encoding="utf-8")
    st.write_platform_meta(article, "wechat", {"platform": "wechat_mp"})

    monkeypatch.setattr(
        zp,
        "publish_article",
        lambda title, body, *, dry_run=False: "https://zhuanlan.zhihu.com/p/test",
    )

    zp.publish_one_pending()

    assert not article.exists()
    assert (published / "article.md").exists()
    assert (published / "article.meta.json").exists()
    assert (published / "article.wechat.meta.json").exists()


def test_skips_pending_file_that_already_has_zhihu_meta(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    published.mkdir(parents=True)
    older = pending / "older.md"
    newer = pending / "newer.md"
    older.write_text("# 旧文\n\n正文", encoding="utf-8")
    newer.write_text("# 新文\n\n正文", encoding="utf-8")
    st.write_platform_meta(older, "zhihu", {"platform": "zhihu"})

    calls = []

    def fake_publish(title, body, *, dry_run=False):
        calls.append((title, body, dry_run))
        return "https://zhuanlan.zhihu.com/p/newer"

    monkeypatch.setattr(zp, "publish_article", fake_publish)

    url = zp.publish_one_pending()

    assert url == "https://zhuanlan.zhihu.com/p/newer"
    assert calls == [("新文", "正文", False)]
    assert older.exists()
    assert newer.exists()
    assert (published / "newer.meta.json").exists()
