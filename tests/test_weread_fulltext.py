from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.content_generator import _chunk_paragraphs  # noqa: E402
from src.weread_fetcher import (  # noqa: E402
    WereadFetchError,
    _paragraphs_from_canvas_records,
)


def _draw_line(text: str, y: int, canvas_id: int = 2) -> list[dict]:
    return [
        {"text": char, "x": index * 20, "y": y, "canvasId": canvas_id}
        for index, char in enumerate(text)
    ]


def test_canvas_records_restore_paragraphs_and_remove_title():
    title = "章节标题"
    first = "第一段" * 20
    second = "继续第一段" * 12
    third = "第二段" * 20
    records = _draw_line("菜单", 20, canvas_id=1)
    records += _draw_line(title, 52)
    records += _draw_line(first, 122)
    records += _draw_line(second, 163)
    records += _draw_line(third, 225)

    paragraphs = _paragraphs_from_canvas_records(records, chapter_title=title)

    assert paragraphs == [first + second, third]


def test_canvas_records_merge_adjacent_content_canvases():
    title = "章节标题"
    first = "第一部分" * 30
    ending = "结尾部分" * 10
    records = _draw_line(title, 52, canvas_id=2)
    records += _draw_line(first, 122, canvas_id=2)
    records += _draw_line(ending, 184, canvas_id=3)

    paragraphs = _paragraphs_from_canvas_records(records, chapter_title=title)

    assert paragraphs == [first, ending]


def test_canvas_records_reject_too_little_chinese():
    with pytest.raises(WereadFetchError, match="没有足够"):
        _paragraphs_from_canvas_records(_draw_line("字太少", 52))


def test_chapter_chunks_preserve_every_paragraph():
    paragraphs = ["甲" * 400, "乙" * 400, "丙" * 400]
    chunks = _chunk_paragraphs(paragraphs, 700)

    assert len(chunks) == 3
    assert "".join(chunks).replace("\n", "") == "".join(paragraphs)
    assert all(len(chunk) <= 700 for chunk in chunks)
