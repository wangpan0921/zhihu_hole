"""读书模式「出处署名」逻辑测试。

覆盖：
1. append_book_source 基本追加；
2. 幂等：已署名不重复追加；
3. 空书名原样返回；
4. book_reflection 生成的 post 正文带出处；
5. backfill 脚本对已落盘草稿的回填（含幂等、跳过 themes 模式）。
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


def test_append_basic():
    out = cg.append_book_source("正文一段。\n\n正文两段。", "被讨厌的勇气")
    assert out.endswith("——《被讨厌的勇气》")
    assert "正文两段。" in out
    # 出处与正文之间空一行
    assert "\n\n——《被讨厌的勇气》" in out


def test_append_idempotent():
    once = cg.append_book_source("正文。", "书名")
    twice = cg.append_book_source(once, "书名")
    assert once == twice
    assert twice.count("——《书名》") == 1


def test_append_idempotent_other_book():
    """已带出处时，即使传入不同书名也不重复追加（迁移幂等优先）。"""
    once = cg.append_book_source("正文。", "书A")
    twice = cg.append_book_source(once, "书B")
    assert twice == once


def test_append_empty_title():
    assert cg.append_book_source("正文。", "") == "正文。"
    assert cg.append_book_source("正文。", "   ") == "正文。"


def test_append_strips_trailing_whitespace():
    out = cg.append_book_source("正文。\n\n  \n", "书名")
    assert out == "正文。\n\n——《书名》"


def _make_index(tmp: Path, book_id: str, title: str, n_chapters: int) -> Path:
    chapters = []
    for i in range(n_chapters):
        chapters.append(
            {
                "chapterUid": int(book_id[-2:]) * 100 + i,
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


def _cfg(book_pool):
    return {
        "content": {
            "mode": "book_reflection",
            "provider": "fake",
            "min_chars": 100,
            "max_chars": 500,
            "book": {"book_pool": book_pool, "min_word_count": 800},
        }
    }


def test_generated_book_post_has_source(fake_env, monkeypatch):
    _make_index(fake_env, "11", "被讨厌的勇气", 2)
    monkeypatch.setattr(cg, "load_config", lambda: _cfg(["11"]))
    monkeypatch.setattr(cg, "load_env", lambda: None)

    post = cg._generate_from_book("morning", dt.date(2026, 6, 9))
    assert post["body"].endswith("——《被讨厌的勇气》")


def test_backfill_script(tmp_path, monkeypatch):
    """落盘的读书草稿被回填出处；themes 草稿与已署名草稿跳过。"""
    import importlib

    pending = tmp_path / "pending"
    pending.mkdir()

    book_draft = pending / "2026-06-09_morning.json"
    book_draft.write_text(
        json.dumps(
            {
                "title": "t",
                "body": "正文内容。",
                "mode": "book_reflection",
                "book": {"book_title": "被讨厌的勇气"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    theme_draft = pending / "2026-06-09_evening.json"
    theme_draft.write_text(
        json.dumps({"title": "t", "body": "纯主题正文。", "mode": "themes"},
                   ensure_ascii=False),
        encoding="utf-8",
    )

    backfill = importlib.import_module("scripts.backfill_book_source")
    monkeypatch.setattr(backfill, "PENDING_DIR", pending)

    # 第一次回填：读书草稿被改，themes 不动
    assert backfill._backfill_file(book_draft, dry_run=False) is True
    assert backfill._backfill_file(theme_draft, dry_run=False) is False

    book_data = json.loads(book_draft.read_text(encoding="utf-8"))
    assert book_data["body"].endswith("——《被讨厌的勇气》")

    # 再跑一次：幂等
    assert backfill._backfill_file(book_draft, dry_run=False) is False
