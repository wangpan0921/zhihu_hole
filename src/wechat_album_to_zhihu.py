"""Publish one WeChat album article at a time to a dedicated Zhihu column."""
from __future__ import annotations

import datetime as dt
import html
import json
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify

from .utils import PROJECT_ROOT, get_logger, load_config
from .zhihu_article_publisher import publish_article

log = get_logger("wechat_album_to_zhihu")

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
        "Mobile Safari/537.36 MicroMessenger/8.0.49"
    )
}


@dataclass(frozen=True)
class AlbumItem:
    msgid: str
    itemidx: str
    title: str
    url: str

    @property
    def key(self) -> str:
        return f"{self.msgid}:{self.itemidx}"


class _AlbumParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[AlbumItem] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag != "li":
            return
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if "js_album_item" not in classes:
            return
        msgid = values.get("data-msgid") or ""
        itemidx = values.get("data-itemidx") or ""
        title = values.get("data-title") or ""
        url = values.get("data-link") or ""
        if msgid and itemidx and title and url:
            self.items.append(
                AlbumItem(
                    msgid=msgid,
                    itemidx=itemidx,
                    title=html.unescape(title),
                    url=html.unescape(url).replace("http://", "https://", 1),
                )
            )


def article_html_to_markdown(raw_html: str, fallback_title: str) -> tuple[str, str]:
    """Convert WeChat editor HTML into a flat Markdown document."""
    soup = BeautifulSoup(raw_html, "html.parser")
    content = soup.select_one("#js_content")
    if content is None:
        raise RuntimeError(f"公众号正文解析失败：{fallback_title}")

    title_node = soup.select_one("#activity-name, h1.rich_media_title")
    title = title_node.get_text("", strip=True) if title_node else fallback_title

    for node in content.select("script, style, iframe, video, audio"):
        node.decompose()

    for image in list(content.select("img")):
        src = image.get("data-src") or image.get("src")
        if not src or not src.startswith(("http://", "https://")):
            image.decompose()
            continue
        image.attrs = {"src": src, "alt": image.get("alt", "")}

        code_parent = image.find_parent("code")
        if code_parent and not code_parent.get_text("", strip=True):
            code_parent.replace_with(image.extract())

        list_parent = image.find_parent(["ul", "ol"])
        if list_parent:
            list_parent.insert_after(image.extract())

    for list_item in content.select("li"):
        for wrapper in list(list_item.find_all(["section", "div"])):
            wrapper.unwrap()

    body_md = markdownify(
        str(content),
        heading_style="ATX",
        bullets="-",
    )
    body_md = body_md.replace("\xa0", " ")
    body_md = re.sub(
        r"\x60(!\[[^\]]*\]\(https?://[^)]+\))\x60",
        r"\n\n\1\n\n",
        body_md,
    )
    body_md = "\n".join(line.rstrip() for line in body_md.splitlines())
    body_md = re.sub(r"\n{3,}", "\n\n", body_md).strip()
    return html.unescape(title).strip() or fallback_title, body_md


def fetch_album_items(album_url: str, *, timeout: int = 30) -> list[AlbumItem]:
    response = requests.get(album_url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    parser = _AlbumParser()
    parser.feed(response.text)
    if not parser.items:
        raise RuntimeError("微信公众号合集里没有解析到文章")
    return parser.items


def fetch_article(item: AlbumItem, *, timeout: int = 30) -> tuple[str, str]:
    response = requests.get(item.url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    title, body_md = article_html_to_markdown(response.text, item.title)
    if len(body_md) < 100:
        raise RuntimeError(f"公众号正文解析失败：{item.title}")
    return title, body_md


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "items": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def publish_next(*, dry_run: bool = False) -> Optional[str]:
    cfg = load_config().get("wechat_album_to_zhihu") or {}
    if not cfg.get("album_url") or not cfg.get("column_name"):
        raise RuntimeError("config.yaml 缺少 wechat_album_to_zhihu 配置")

    state_path = PROJECT_ROOT / cfg.get(
        "state_path", "data/wechat_album/state.json"
    )
    state = _load_state(state_path)
    records = state.setdefault("items", {})
    items = fetch_album_items(cfg["album_url"])
    skip_first = int(cfg.get("skip_first", 0))

    for item in items[:skip_first]:
        records.setdefault(
            item.key,
            {
                **asdict(item),
                "status": "skipped_existing",
                "recorded_at": dt.datetime.now().isoformat(timespec="seconds"),
            },
        )
    if not dry_run:
        _write_state(state_path, state)

    target = next((item for item in items if item.key not in records), None)
    if target is None:
        log.info("合集当前没有未发布文章，共 %d 篇", len(items))
        return None

    title, body_md = fetch_article(target)
    log.info("选中合集文章：%s（%s）", title, target.key)
    article_url = publish_article(
        title,
        body_md,
        dry_run=dry_run,
        column_name=cfg["column_name"],
    )
    if dry_run:
        return article_url

    records[target.key] = {
        **asdict(target),
        "title": title,
        "status": "published",
        "article_url": article_url,
        "published_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    _write_state(state_path, state)
    return article_url
