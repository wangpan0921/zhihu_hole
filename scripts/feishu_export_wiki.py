#!/usr/bin/env python3
"""Export a Feishu wiki/docx page through Feishu Open API.

The script keeps raw API responses next to human-readable text so the article
can be written from evidence instead of from screenshots alone.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
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
    path = urlparse(url_or_token).path
    parts = [part for part in path.split("/") if part]
    try:
        wiki_index = parts.index("wiki")
    except ValueError as exc:
        raise ValueError(f"Not a Feishu wiki URL: {url_or_token}") from exc
    if wiki_index + 1 >= len(parts):
        raise ValueError(f"Wiki URL has no node token: {url_or_token}")
    return parts[wiki_index + 1]


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
        raise FeishuError(f"{method} {path} failed HTTP {response.status_code}: {json.dumps(payload, ensure_ascii=False)[:1000]}")
    return payload


def request_binary(method: str, path: str, token: str, **kwargs: Any) -> requests.Response:
    response = requests.request(
        method,
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
        **kwargs,
    )
    if response.status_code >= 400:
        raise FeishuError(f"{method} {path} failed HTTP {response.status_code}: {response.text[:1000]}")
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if payload.get("code") not in (0, None):
            raise FeishuError(f"{method} {path} failed: {json.dumps(payload, ensure_ascii=False)[:1000]}")
    return response


def tenant_access_token() -> str:
    load_dotenv()
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


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def page_all(method_path: str, token: str, params: dict[str, Any] | None = None, key: str = "items") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = ""
    base_params = dict(params or {})
    while True:
        req_params = dict(base_params)
        if page_token:
            req_params["page_token"] = page_token
        payload = request_json("GET", method_path, token, params=req_params)
        data = payload.get("data", {})
        items.extend(data.get(key, []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token", "")
        if not page_token:
            break
    return items


def plain_text_from_blocks(blocks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for block in blocks:
        text = block_to_text(block)
        if text:
            lines.append(text)
    return "\n".join(lines)


def block_to_text(block: dict[str, Any]) -> str:
    block_type = block.get("block_type")
    if block_type == 1:
        return text_elements(block.get("page", {}).get("elements", []))
    if block_type == 2:
        return text_elements(block.get("text", {}).get("elements", []))
    if block_type in {3, 4, 5, 6, 7, 8, 9, 10, 11}:
        # Headings use different numeric block types but the same payload shape.
        heading = next((value for key, value in block.items() if re.fullmatch(r"heading\d", key)), None)
        if heading:
            return text_elements(heading.get("elements", []))
    if block_type == 12:
        return "- " + text_elements(block.get("bullet", {}).get("elements", []))
    if block_type == 13:
        return "1. " + text_elements(block.get("ordered", {}).get("elements", []))
    if block_type == 14:
        return "```" + "\n" + text_elements(block.get("code", {}).get("elements", [])) + "\n```"
    if block_type == 15:
        return "> " + text_elements(block.get("quote", {}).get("elements", []))
    if block_type == 22:
        return "---"
    if block_type == 27:
        return "[image]"
    if block_type == 31:
        return "[table]"
    if block_type == 43:
        return "[board]"
    return ""


def text_elements(elements: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for element in elements:
        if "text_run" in element:
            chunks.append(element["text_run"].get("content", ""))
        elif "mention_user" in element:
            chunks.append("@" + element["mention_user"].get("name", ""))
        elif "mention_doc" in element:
            chunks.append(element["mention_doc"].get("title", ""))
        elif "equation" in element:
            chunks.append(element["equation"].get("content", ""))
        elif "reminder" in element:
            chunks.append(element["reminder"].get("text", ""))
    return "".join(chunks).strip()


def export_markdown(document_id: str, token: str, out_dir: Path) -> None:
    # These endpoints are available for many docx documents but not every tenant.
    # Keep failures non-fatal because block export is the authoritative fallback.
    try:
        raw_payload = request_json(
            "GET",
            f"/docx/v1/documents/{document_id}/raw_content",
            token,
        )
        write_json(out_dir / "raw_content.json", raw_payload)
        content = raw_payload.get("data", {}).get("content", "")
        if content:
            (out_dir / "raw_content.txt").write_text(content, encoding="utf-8")
    except FeishuError as exc:
        (out_dir / "raw_content.error.txt").write_text(str(exc), encoding="utf-8")




def extension_from_content_type(content_type: str) -> str:
    content_type = content_type.split(";")[0].strip().lower()
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
    }.get(content_type, ".bin")


def export_assets(blocks: list[dict[str, Any]], token: str, out_dir: Path) -> None:
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    manifest: list[dict[str, Any]] = []

    for block in blocks:
        block_type = block.get("block_type")
        block_id = block.get("block_id")
        if block_type == 27 and block.get("image", {}).get("token"):
            file_token = block["image"]["token"]
            try:
                response = request_binary("GET", f"/drive/v1/medias/{file_token}/download", token)
                ext = extension_from_content_type(response.headers.get("content-type", ""))
                asset_path = assets_dir / f"image_{block_id}_{file_token}{ext}"
                asset_path.write_bytes(response.content)
                manifest.append({
                    "type": "image",
                    "block_id": block_id,
                    "token": file_token,
                    "path": str(asset_path),
                    "content_type": response.headers.get("content-type"),
                    "bytes": len(response.content),
                    "width": block["image"].get("width"),
                    "height": block["image"].get("height"),
                })
            except FeishuError as exc:
                manifest.append({"type": "image", "block_id": block_id, "token": file_token, "error": str(exc)})

        if block_type == 43 and block.get("board", {}).get("token"):
            whiteboard_id = block["board"]["token"]
            try:
                nodes = page_all(f"/board/v1/whiteboards/{whiteboard_id}/nodes", token, params={"page_size": 500}, key="nodes")
                nodes_path = assets_dir / f"board_{block_id}_{whiteboard_id}_nodes.json"
                write_json(nodes_path, nodes)
                manifest.append({
                    "type": "board_nodes",
                    "block_id": block_id,
                    "token": whiteboard_id,
                    "path": str(nodes_path),
                    "nodes": len(nodes),
                })
            except FeishuError as exc:
                manifest.append({"type": "board_nodes", "block_id": block_id, "token": whiteboard_id, "error": str(exc)})
            try:
                response = request_binary("GET", f"/board/v1/whiteboards/{whiteboard_id}/download_as_image", token)
                ext = extension_from_content_type(response.headers.get("content-type", ""))
                asset_path = assets_dir / f"board_{block_id}_{whiteboard_id}{ext}"
                asset_path.write_bytes(response.content)
                manifest.append({
                    "type": "board_image",
                    "block_id": block_id,
                    "token": whiteboard_id,
                    "path": str(asset_path),
                    "content_type": response.headers.get("content-type"),
                    "bytes": len(response.content),
                })
            except FeishuError as exc:
                manifest.append({"type": "board_image", "block_id": block_id, "token": whiteboard_id, "error": str(exc)})

    write_json(out_dir / "assets_manifest.json", manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wiki_url_or_token")
    parser.add_argument("--out", default="artifacts/feishu_recursive_subsets")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    wiki_token = extract_wiki_token(args.wiki_url_or_token)
    token = tenant_access_token()

    node_payload = request_json("GET", f"/wiki/v2/spaces/get_node?token={wiki_token}", token)
    write_json(out_dir / "wiki_node.json", node_payload)
    node = node_payload.get("data", {}).get("node", {})
    obj_type = node.get("obj_type")
    obj_token = node.get("obj_token")
    if not obj_type or not obj_token:
        raise FeishuError(f"Cannot resolve wiki node: {json.dumps(node_payload, ensure_ascii=False)}")

    summary = {
        "wiki_token": wiki_token,
        "obj_type": obj_type,
        "obj_token": obj_token,
        "title": node.get("title"),
        "url": args.wiki_url_or_token,
    }
    write_json(out_dir / "summary.json", summary)

    if obj_type != "docx":
        raise FeishuError(f"Unsupported wiki object type {obj_type!r}; expected docx")

    doc_payload = request_json("GET", f"/docx/v1/documents/{obj_token}", token)
    write_json(out_dir / "document.json", doc_payload)

    blocks = page_all(f"/docx/v1/documents/{obj_token}/blocks", token, params={"page_size": 500})
    write_json(out_dir / "blocks.json", blocks)
    (out_dir / "blocks_text.txt").write_text(plain_text_from_blocks(blocks), encoding="utf-8")
    export_markdown(obj_token, token, out_dir)
    export_assets(blocks, token, out_dir)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Exported {len(blocks)} blocks to {out_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
