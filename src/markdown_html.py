"""把 Markdown 正文转成「干净的 HTML」，专供粘贴进知乎 Draft.js 编辑器用。

为什么不用逐字符 keyboard.type + Draft.js markdown 输入规则：
    实测一旦进入列表 / 代码块上下文，后续的 Enter 会一直停留在该上下文里，
    后面的段落、`##` 标题、`- ` 列表项全被吞进同一个 <ul>，并且 `##` / `-`
    标记不再被转换，直接以纯文本出现，导致整篇排版崩坏。

改用「自己转 HTML → 触发一次 text/html 粘贴」：
    Draft.js 的 onPaste 会读取 clipboardData 里的 text/html，按标准 HTML 结构
    （h2 / ul / ol / blockquote / pre>code / strong / code / a）一次性建出对应的
    富文本 block，不依赖逐字符输入规则，块结构稳定。

只实现常见子集：标题、无序/有序列表、引用、围栏代码块、加粗、行内代码、链接、段落。
"""
from __future__ import annotations

import html
import re
from typing import List

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^\s*\d+\.\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*```")


def _inline(text: str) -> str:
    """行内标记 → HTML。先抠出行内代码占位，避免代码里的 ** 被当成加粗。"""
    placeholders: List[str] = []

    def _stash_code(m: "re.Match[str]") -> str:
        placeholders.append(html.escape(m.group(1)))
        return f"\x00{len(placeholders) - 1}\x00"

    # 1) 行内代码：先抠出来占位（内容已 escape）
    tmp = _CODE_RE.sub(_stash_code, text)
    # 2) 其余文本 escape
    tmp = html.escape(tmp)
    # 3) 链接：注意此时 [ ] ( ) 未被 escape（escape 不动这些字符），可直接匹配
    tmp = _LINK_RE.sub(
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        tmp,
    )
    # 4) 加粗
    tmp = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", tmp)
    # 5) 还原行内代码占位
    def _restore(m: "re.Match[str]") -> str:
        idx = int(m.group(1))
        return (
            '<code style="margin:0 2px;padding:3px 4px;border-radius:3px;'
            'background-color:#f6f6f6;font-family:Menlo,Monaco,Consolas,monospace;">'
            f"{placeholders[idx]}</code>"
        )

    tmp = re.sub(r"\x00(\d+)\x00", _restore, tmp)
    return tmp


def markdown_to_html(md_text: str) -> str:
    """把 Markdown 正文转成 HTML 字符串（不含 <html>/<body> 外壳）。"""
    lines = md_text.splitlines()
    out: List[str] = []

    i = 0
    n = len(lines)
    list_stack: List[str] = []  # 'ul' / 'ol'

    def _close_lists() -> None:
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    while i < n:
        line = lines[i]

        # 围栏代码块
        if _FENCE_RE.match(line):
            _close_lists()
            code_lines: List[str] = []
            i += 1
            while i < n and not _FENCE_RE.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过闭合 ```
            code_html = html.escape("\n".join(code_lines))
            out.append(
                '<pre style="background-color:#f6f6f6;padding:12px;border-radius:4px;'
                'overflow:auto;"><code style="font-family:Menlo,Monaco,Consolas,'
                f'monospace;white-space:pre;">{code_html}</code></pre>'
            )
            continue

        # 空行
        if line.strip() == "":
            _close_lists()
            i += 1
            continue

        # 标题
        m = _HEADING_RE.match(line)
        if m:
            _close_lists()
            level = len(m.group(1))
            # 知乎正文一般只用 h2/h3；# 一级标题降到 h2，避免和文章主标题冲突
            tag = "h2" if level <= 2 else "h3"
            out.append(f"<{tag}>{_inline(m.group(2).strip())}</{tag}>")
            i += 1
            continue

        # 引用：合并连续的 > 行
        if line.lstrip().startswith(">"):
            _close_lists()
            quote_lines: List[str] = []
            while i < n and lines[i].lstrip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = "<br/>".join(_inline(q) for q in quote_lines if q.strip() != "")
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # 无序列表
        m = _UL_RE.match(line)
        if m:
            if not list_stack or list_stack[-1] != "ul":
                _close_lists()
                out.append("<ul>")
                list_stack.append("ul")
            out.append(f"<li>{_inline(m.group(1).strip())}</li>")
            i += 1
            continue

        # 有序列表
        m = _OL_RE.match(line)
        if m:
            if not list_stack or list_stack[-1] != "ol":
                _close_lists()
                out.append("<ol>")
                list_stack.append("ol")
            out.append(f"<li>{_inline(m.group(1).strip())}</li>")
            i += 1
            continue

        # 普通段落：把连续非空、非块级行合并成一段
        _close_lists()
        para_lines: List[str] = [line]
        i += 1
        while i < n:
            nxt = lines[i]
            if (
                nxt.strip() == ""
                or _FENCE_RE.match(nxt)
                or _HEADING_RE.match(nxt)
                or _UL_RE.match(nxt)
                or _OL_RE.match(nxt)
                or nxt.lstrip().startswith(">")
            ):
                break
            para_lines.append(nxt)
            i += 1
        inner = "<br/>".join(_inline(p) for p in para_lines)
        out.append(f"<p>{inner}</p>")

    _close_lists()
    return "\n".join(out)
