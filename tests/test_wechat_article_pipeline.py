from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import article_state as st  # noqa: E402
from src import wechat_article_pipeline as wp  # noqa: E402
from src import wechat_article_publisher as pub  # noqa: E402


def _patch_dirs(tmp_path, monkeypatch):
    pending = tmp_path / "docs" / "pending"
    published = tmp_path / "docs" / "published"
    pending.mkdir(parents=True)
    covers = tmp_path / "assets" / "wechat_covers"
    covers.mkdir(parents=True)
    monkeypatch.setattr(st, "DOCS_PENDING", pending)
    monkeypatch.setattr(st, "DOCS_PUBLISHED", published)
    monkeypatch.setattr(wp, "WECHAT_COVER_DIR", covers)
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
    (wp.WECHAT_COVER_DIR / "article.png").write_bytes(b"cover")

    monkeypatch.setattr(
        wp,
        "publish_wechat_article",
        lambda title, body, *, cover_path=None, dry_run=False: "https://mp.weixin.qq.com/s/test",
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
    (wp.WECHAT_COVER_DIR / "article.png").write_bytes(b"cover")
    st.write_platform_meta(article, "zhihu", {"platform": "zhihu"})

    monkeypatch.setattr(
        wp,
        "publish_wechat_article",
        lambda title, body, *, cover_path=None, dry_run=False: "https://mp.weixin.qq.com/s/test",
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
    (wp.WECHAT_COVER_DIR / "newer.png").write_bytes(b"cover")
    os.utime(older, (older.stat().st_mtime - 10, older.stat().st_mtime - 10))
    st.write_platform_meta(older, "wechat", {"platform": "wechat_mp"})

    calls = []

    def fake_publish(title, body, *, cover_path=None, dry_run=False):
        calls.append((title, body, cover_path, dry_run))
        return "https://mp.weixin.qq.com/s/newer"

    monkeypatch.setattr(wp, "publish_wechat_article", fake_publish)

    url = wp.publish_one_pending_to_wechat()

    assert url == "https://mp.weixin.qq.com/s/newer"
    assert calls == [("新文", "正文", wp.WECHAT_COVER_DIR / "newer.png", False)]
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
        lambda title, body, *, cover_path=None, dry_run=False: "draft-url",
    )

    url = wp.publish_one_pending_to_wechat(dry_run=True)

    assert url == "draft-url"
    assert article.exists()
    assert not published.exists()


def test_missing_cover_stops_before_publish_and_meta(tmp_path, monkeypatch):
    pending, published = _patch_dirs(tmp_path, monkeypatch)
    article = pending / "article.md"
    article.write_text("# 标题\n\n正文", encoding="utf-8")

    called = False

    def fake_publish(*args, **kwargs):
        nonlocal called
        called = True
        return "unexpected"

    monkeypatch.setattr(wp, "publish_wechat_article", fake_publish)

    with pytest.raises(RuntimeError, match="封面不存在"):
        wp.publish_one_pending_to_wechat()

    assert not called
    assert article.exists()
    assert not (published / "article.wechat.meta.json").exists()


def test_cover_lookup_supports_common_image_extensions(tmp_path, monkeypatch):
    _patch_dirs(tmp_path, monkeypatch)
    article = tmp_path / "article.md"
    expected = wp.WECHAT_COVER_DIR / "article.webp"
    expected.write_bytes(b"cover")

    assert wp._cover_path_for(article) == expected


class FakeTextMatches:
    def __init__(self, visible):
        self.visible = visible

    def count(self):
        return 1 if self.visible else 0

    def nth(self, index):
        return self

    def is_visible(self):
        return self.visible


class FakeWechatPage:
    def __init__(self, visible_texts=(), url="https://mp.weixin.qq.com/cgi-bin/appmsg?isNew=1"):
        self.visible_texts = set(visible_texts)
        self.url = url

    def get_by_text(self, text, exact=False):
        return FakeTextMatches(text in self.visible_texts)


class FakeRequest:
    def __init__(self, method="POST", post_data=""):
        self.method = method
        self.post_data = post_data


class FakeResponse:
    def __init__(self, url, payload, method="POST", post_data=""):
        self.url = url
        self.request = FakeRequest(method, post_data)
        self.payload = payload

    def json(self):
        return self.payload


def test_publish_response_filter_rejects_plain_autosave():
    response = FakeResponse(
        "https://mp.weixin.qq.com/cgi-bin/operate_appmsg?sub=create",
        {"base_resp": {"ret": 0}},
    )

    assert pub._action_response_payload(response, "publish") is None
    assert pub._action_response_payload(response, "draft") == {
        "base_resp": {"ret": 0}
    }


def test_publish_response_filter_accepts_freepublish_success():
    response = FakeResponse(
        "https://mp.weixin.qq.com/cgi-bin/freepublish?action=publish",
        {"base_resp": {"ret": 0}},
    )

    assert pub._action_response_payload(response, "publish") == {
        "base_resp": {"ret": 0}
    }


def test_page_validation_error_overrides_success_response():
    page = FakeWechatPage(visible_texts={"必须插入一张图片"})

    assert not pub._verify_action_success(
        page,
        "publish",
        [{"base_resp": {"ret": 0}}],
    )


def test_draft_saved_url_requires_material_id_and_not_new():
    assert pub._saved_url(
        "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&appmsgid=123"
    )
    assert not pub._saved_url(
        "https://mp.weixin.qq.com/cgi-bin/appmsg?action=edit&isNew=1"
    )


def test_success_response_is_accepted_without_page_error():
    page = FakeWechatPage()

    assert pub._verify_action_success(
        page,
        "publish",
        [{"base_resp": {"ret": 0}}],
    )
