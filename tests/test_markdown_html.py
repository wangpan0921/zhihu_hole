from __future__ import annotations

from src.markdown_html import count_markdown_tables, markdown_to_html


def test_converts_gfm_table_to_structured_html():
    result = markdown_to_html(
        """| 名称 | 说明 |
| --- | --- |
| TCPStore | 键值存储 |
| Gloo | 集合通信 |"""
    )

    assert result.count("<table>") == 1
    assert "<thead><tr><th>名称</th><th>说明</th></tr></thead>" in result
    assert "<tbody><tr><td>TCPStore</td><td>键值存储</td></tr>" in result
    assert "<tr><td>Gloo</td><td>集合通信</td></tr></tbody>" in result


def test_preserves_alignment_and_inline_markdown_in_cells():
    result = markdown_to_html(
        """名称 | 代码 | 文档
:--- | :---: | ---:
**TCPStore** | `store.set()` | [API](https://pytorch.org)"""
    )

    assert '<th style="text-align:left;">名称</th>' in result
    assert '<th style="text-align:center;">代码</th>' in result
    assert '<th style="text-align:right;">文档</th>' in result
    assert "<strong>TCPStore</strong>" in result
    assert "store.set()" in result
    assert '<a href="https://pytorch.org">API</a>' in result


def test_handles_escaped_and_inline_code_pipes():
    result = markdown_to_html(
        """表达式 | 含义
--- | ---
left \\| right | `a|b`"""
    )

    assert "<td>left | right</td>" in result
    assert "a|b</code>" in result
    assert result.count("<td>") == 2


def test_pads_missing_cells_and_truncates_extra_cells():
    result = markdown_to_html(
        """A | B
--- | ---
only-a |
one | two | ignored"""
    )

    assert "<tr><td>only-a</td><td></td></tr>" in result
    assert "<tr><td>one</td><td>two</td></tr>" in result
    assert "ignored" not in result


def test_invalid_delimiter_is_left_as_paragraph_text():
    source = """A | B
-- | ---
one | two"""
    result = markdown_to_html(source)

    assert "<table>" not in result
    assert "A | B" in result
    assert "-- | ---" in result


def test_counts_only_tables_outside_fenced_code_blocks():
    source = """A | B
--- | ---
1 | 2

```
fake | table
--- | ---
x | y
```

C | D
:--- | ---:
3 | 4"""

    assert count_markdown_tables(source) == 2
    assert markdown_to_html(source).count("<table>") == 2
