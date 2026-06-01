#!/usr/bin/env python3
"""Append a local Markdown article to a Feishu wiki/docx document."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


API_BASE = "https://open.feishu.cn/open-apis"


class FeishuError(RuntimeError):
    pass


def extract_wiki_token(url_or_token: str) -> str:
    if "/" not in url_or_token:
        return url_or_token
    parts = [part for part in urlparse(url_or_token).path.split("/") if part]
    if "wiki" not in parts:
        raise ValueError(f"Not a Feishu wiki URL: {url_or_token}")
    index = parts.index("wiki") + 1
    if index >= len(parts):
        raise ValueError(f"Wiki URL has no node token: {url_or_token}")
    return parts[index]


def request_json(method: str, path: str, token: str | None = None, **kwargs: Any) -> dict[str, Any]:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(method, f"{API_BASE}{path}", headers=headers, timeout=30, **kwargs)
    try:
        payload = response.json()
    except ValueError as exc:
        raise FeishuError(f"{method} {path} returned non-JSON HTTP {response.status_code}: {response.text[:300]}") from exc
    if response.status_code >= 400 or payload.get("code") not in (0, None):
        raise FeishuError(f"{method} {path} failed HTTP {response.status_code}: {json.dumps(payload, ensure_ascii=False)[:1500]}")
    return payload


def tenant_access_token() -> str:
    load_dotenv(".env")
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise FeishuError("FEISHU_APP_ID and FEISHU_APP_SECRET must be set in .env")
    payload = request_json(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
    )
    return payload["tenant_access_token"]


def resolve_docx(wiki_url_or_token: str, token: str) -> tuple[str, str]:
    wiki_token = extract_wiki_token(wiki_url_or_token)
    payload = request_json("GET", f"/wiki/v2/spaces/get_node?token={wiki_token}", token)
    node = payload.get("data", {}).get("node", {})
    if node.get("obj_type") != "docx" or not node.get("obj_token"):
        raise FeishuError(f"Wiki node is not a docx document: {json.dumps(node, ensure_ascii=False)}")
    return node["obj_token"], node.get("title", "")


def raw_content(document_id: str, token: str) -> str:
    payload = request_json("GET", f"/docx/v1/documents/{document_id}/raw_content", token)
    return payload.get("data", {}).get("content", "")


def text_block(content: str) -> dict[str, Any]:
    return {
        "block_type": 2,
        "text": {
            "elements": [
                {
                    "text_run": {
                        "content": content,
                        "text_element_style": {},
                    }
                }
            ],
            "style": {},
        },
    }


def heading_block(level: int, content: str) -> dict[str, Any]:
    level = min(max(level, 1), 9)
    return {
        "block_type": level + 2,
        f"heading{level}": {
            "elements": [
                {
                    "text_run": {
                        "content": content,
                        "text_element_style": {},
                    }
                }
            ],
            "style": {},
        },
    }


def code_block(content: str) -> dict[str, Any]:
    return {
        "block_type": 14,
        "code": {
            "elements": [
                {
                    "text_run": {
                        "content": content,
                        "text_element_style": {},
                    }
                }
            ],
            "style": {"language": 9, "wrap": True},
        },
    }


def markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(text_block("\n".join(paragraph).strip()))
            paragraph.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                blocks.append(code_block("\n".join(code_lines)))
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            blocks.append(heading_block(len(heading.group(1)), heading.group(2).strip()))
            continue
        if line.startswith("|"):
            flush_paragraph()
            blocks.append(text_block(line))
            continue
        paragraph.append(line)

    if in_code:
        blocks.append(code_block("\n".join(code_lines)))
    flush_paragraph()
    return blocks


def append_blocks(document_id: str, parent_block_id: str, token: str, blocks: list[dict[str, Any]]) -> int:
    created = 0
    for start in range(0, len(blocks), 50):
        batch = blocks[start : start + 50]
        payload = request_json(
            "POST",
            f"/docx/v1/documents/{document_id}/blocks/{parent_block_id}/children",
            token,
            params={"document_revision_id": -1},
            json={"index": -1, "children": batch},
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        created += len(payload.get("data", {}).get("children", []))
        time.sleep(0.45)
    return created


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wiki_url")
    parser.add_argument("markdown_file")
    parser.add_argument("--marker", default="递归求子集：用 26 步看懂 call stack 的完整变化")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    markdown = Path(args.markdown_file).read_text(encoding="utf-8")
    token = tenant_access_token()
    document_id, title = resolve_docx(args.wiki_url, token)
    before = raw_content(document_id, token)
    if args.marker in before and not args.force:
        print(f"Document already contains marker {args.marker!r}; skip append.")
        return 0

    blocks = markdown_to_blocks(markdown)
    if not blocks:
        raise FeishuError(f"No appendable content found in {args.markdown_file}")
    created = append_blocks(document_id, document_id, token, blocks)
    print(json.dumps({"document_id": document_id, "title": title, "blocks_requested": len(blocks), "blocks_created": created}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
