from __future__ import annotations

from src.zhihu_article_publisher import (
    _count_html_images,
    _count_html_tables,
    _paste_stats_valid,
    _verify_published_images,
    _verify_published_tables,
)


class FakePage:
    def __init__(self, observed_tables=0, error=None):
        self.observed_tables = observed_tables
        self.error = error
        self.goto_calls = []
        self.wait_calls = []

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        if self.error:
            raise self.error

    def wait_for_timeout(self, milliseconds):
        self.wait_calls.append(milliseconds)

    def evaluate(self, script):
        return self.observed_tables


def test_counts_table_elements_case_insensitively():
    html = "<table><tr></tr></table><TABLE class='wide'></TABLE>"
    assert _count_html_tables(html) == 2


def test_paste_stats_require_all_expected_tables():
    complete = {"len": 100, "blocks": 3, "tables": 2}
    dropped = {"len": 100, "blocks": 3, "tables": 1}

    assert _paste_stats_valid(complete, expected_tables=2)
    assert not _paste_stats_valid(dropped, expected_tables=2)
    assert not _paste_stats_valid({"len": 10, "blocks": 3, "tables": 2}, 2)


def test_counts_and_requires_all_expected_images():
    assert _count_html_images("<img src='a'><IMG src='b'>") == 2
    complete = {"len": 100, "blocks": 3, "tables": 0, "images": 2}
    dropped = {"len": 100, "blocks": 3, "tables": 0, "images": 1}

    assert _paste_stats_valid(complete, expected_tables=0, expected_images=2)
    assert not _paste_stats_valid(
        dropped, expected_tables=0, expected_images=2
    )


def test_verify_published_tables_reads_the_published_page():
    page = FakePage(observed_tables=2)
    url = "https://zhuanlan.zhihu.com/p/123"

    assert _verify_published_tables(page, url, expected_tables=2)
    assert page.goto_calls == [
        (url, {"wait_until": "domcontentloaded", "timeout": 30000})
    ]
    assert page.wait_calls == [3000]


def test_verify_published_tables_detects_missing_tables():
    page = FakePage(observed_tables=1)
    assert not _verify_published_tables(
        page,
        "https://zhuanlan.zhihu.com/p/123",
        expected_tables=2,
    )


def test_verify_published_tables_skips_navigation_when_none_expected():
    page = FakePage(error=RuntimeError("should not navigate"))
    assert _verify_published_tables(page, "https://example.test", expected_tables=0)
    assert page.goto_calls == []


def test_verify_published_tables_handles_page_errors():
    page = FakePage(error=RuntimeError("network failed"))
    assert not _verify_published_tables(page, "https://example.test", expected_tables=1)


def test_verify_published_images_reads_the_published_page():
    page = FakePage(observed_tables=3)
    url = "https://zhuanlan.zhihu.com/p/123"

    assert _verify_published_images(page, url, expected_images=3)
    assert page.goto_calls == [
        (url, {"wait_until": "domcontentloaded", "timeout": 30000})
    ]
    assert page.wait_calls == [3000]


def test_verify_published_images_detects_missing_images():
    page = FakePage(observed_tables=1)
    assert not _verify_published_images(page, "https://example.test", expected_images=2)
