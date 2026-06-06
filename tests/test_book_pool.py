"""书籍池（book_pool）逻辑测试。

聚焦三件事：
1. 按池子顺序逐本读完：第一本没读完时不碰第二本；
2. 第一本读完后自动切到第二本；
3. 池子全部读完时抛 BookPoolFinished，且调度层据此发私信 + 回退 themes。

不依赖真实 LLM / 网络：用 monkeypatch 打桩 _call_llm 和 fetch_chapter。
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import content_generator as cg  # noqa: E402


def _make_index(tmp: Path, book_id: str, title: str, n_chapters: int) -> Path:
    """造一本 n_chapters 个正文章节的 index.json，返回其路径。"""
    chapters = []
    for i in range(n_chapters):
        chapters.append(
            {
                "chapterUid": int(book_id[-2:]) * 100 + i,  # 保证跨书 uid 不撞
                "chapterIdx": i,
                "title": f"第{i + 1}章 正文内容",
                "level": 2,
                "wordCount": 2000,
                "paid": 0,
                "url": f"https://weread.qq.com/web/reader/{book_id}k{i:03d}",
                "url_hash": f"{i:03d}",
            }
        )
    d = tmp / "data" / "books" / book_id
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "book_id": book_id,
        "book_title": title,
        "author": "作者",
        "chapter_size": n_chapters,
        "max_free_chapter": n_chapters,
        "chapters": chapters,
    }
    p = d / "index.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """把 DATA_DIR 指到 tmp，并打桩 LLM + 章节抓取。"""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(cg, "DATA_DIR", data_dir)

    def _fake_fetch(url, **kw):
        return {"description": "x" * 600, "chapter_title": "t"}

    monkeypatch.setattr(cg, "fetch_chapter", _fake_fetch)

    def _fake_llm(system, user):
        return (
            json.dumps(
                {"title": "标题", "body": "正文内容。", "image_prompt": "calm light"}
            ),
            "fake",
        )

    monkeypatch.setattr(cg, "_call_llm", _fake_llm)
    return tmp_path


def _cfg(book_pool, *, min_wc=800):
    return {
        "content": {
            "mode": "book_reflection",
            "provider": "fake",
            "min_chars": 100,
            "max_chars": 500,
            "book": {"book_pool": book_pool, "min_word_count": min_wc},
        }
    }


def test_pool_reads_books_in_order(fake_env, monkeypatch):
    """两本各 2 章。前 2 次读完 A，第 3 次才开始 B。"""
    _make_index(fake_env, "11", "书A", 2)
    _make_index(fake_env, "22", "书B", 2)
    monkeypatch.setattr(cg, "load_config", lambda: _cfg(["11", "22"]))
    monkeypatch.setattr(cg, "load_env", lambda: None)

    titles = []
    for i in range(4):
        post = cg._generate_from_book(
            "morning", dt.date(2026, 1, 1) + dt.timedelta(days=i)
        )
        titles.append(post["book"]["book_title"])

    assert titles == ["书A", "书A", "书B", "书B"], titles


def test_pool_finished_raises(fake_env, monkeypatch):
    """一本 1 章，读完后再取应抛 BookPoolFinished。"""
    _make_index(fake_env, "11", "书A", 1)
    monkeypatch.setattr(cg, "load_config", lambda: _cfg(["11"]))
    monkeypatch.setattr(cg, "load_env", lambda: None)

    cg._generate_from_book("morning", dt.date(2026, 1, 1))
    with pytest.raises(cg.BookPoolFinished):
        cg._generate_from_book("evening", dt.date(2026, 1, 1))


def test_pool_idempotent_reclaim(fake_env, monkeypatch):
    """同一 slot/date 再次生成应复用已 claim 的章节，不推进。"""
    _make_index(fake_env, "11", "书A", 3)
    monkeypatch.setattr(cg, "load_config", lambda: _cfg(["11"]))
    monkeypatch.setattr(cg, "load_env", lambda: None)

    d = dt.date(2026, 1, 1)
    p1 = cg._generate_from_book("morning", d)
    p2 = cg._generate_from_book("morning", d)
    assert p1["book"]["chapter_uid"] == p2["book"]["chapter_uid"]


def test_single_book_backward_compat(fake_env, monkeypatch):
    """只配 book_id（无 book_pool）仍然工作。"""
    _make_index(fake_env, "11", "书A", 1)
    cfg = {
        "content": {
            "mode": "book_reflection",
            "provider": "fake",
            "min_chars": 100,
            "max_chars": 500,
            "book": {"book_id": "11", "min_word_count": 800},
        }
    }
    monkeypatch.setattr(cg, "load_config", lambda: cfg)
    monkeypatch.setattr(cg, "load_env", lambda: None)

    post = cg._generate_from_book("morning", dt.date(2026, 1, 1))
    assert post["book"]["book_title"] == "书A"


def test_missing_index_skipped_in_pool(fake_env, monkeypatch):
    """池里第一本索引缺失时跳过，读第二本。"""
    _make_index(fake_env, "22", "书B", 1)
    monkeypatch.setattr(cg, "load_config", lambda: _cfg(["11", "22"]))  # 11 不存在
    monkeypatch.setattr(cg, "load_env", lambda: None)

    post = cg._generate_from_book("morning", dt.date(2026, 1, 1))
    assert post["book"]["book_title"] == "书B"
