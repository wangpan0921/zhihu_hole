"""Publish one WeChat album article at a time to a dedicated Zhihu column."""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

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

_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)"
)
_IMAGE_SUFFIXES = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
_CGI_ARTICLE_LIST_RE = re.compile(
    r"articleList\s*:\s*\[(.*?)\]\s*,?\s*continue_flag\s*:",
    re.S,
)
_CGI_ARTICLE_RE = re.compile(
    r"title\s*:\s*'((?:\\.|[^'])*)'.*?"
    r"url\s*:\s*'((?:\\.|[^'])*)'.*?"
    r"msgid\s*:\s*'([^']+)'.*?"
    r"itemidx\s*:\s*'([^']+)'",
    re.S,
)
_CONTINUE_FLAG_RE = re.compile(r"\bcontinue_flag\s*:\s*['\"]?(\d+)")
_ARTICLE_COUNT_RE = re.compile(r"\barticle_count\s*:\s*['\"]?(\d+)")
_ALBUM_PAGE_SIZE = 10
_MAX_ALBUM_PAGES = 100


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


def _decode_js_string(value: str) -> str:
    value = re.sub(
        r"\\x([0-9a-fA-F]{2})",
        lambda match: chr(int(match.group(1), 16)),
        value,
    )
    value = value.replace(r"\'", "'").replace(r"\\", "\\")
    return html.unescape(value)


def _parse_cgi_article_list(raw_html: str) -> list[AlbumItem]:
    match = _CGI_ARTICLE_LIST_RE.search(raw_html)
    if not match:
        return []
    items: list[AlbumItem] = []
    for title, url, msgid, itemidx in _CGI_ARTICLE_RE.findall(match.group(1)):
        items.append(
            AlbumItem(
                msgid=msgid,
                itemidx=itemidx,
                title=_decode_js_string(title),
                url=_decode_js_string(url).replace("http://", "https://", 1),
            )
        )
    return items


def _parse_album_html(raw_html: str) -> list[AlbumItem]:
    parser = _AlbumParser()
    parser.feed(raw_html)
    return parser.items or _parse_cgi_article_list(raw_html)


def _response_album_page(
    response: requests.Response,
) -> tuple[list[AlbumItem], bool, Optional[int]]:
    content_type = (
        response.headers.get("Content-Type", "") if response.headers else ""
    ).lower()
    if "json" in content_type:
        data = response.json()
        base_ret = int((data.get("base_resp") or {}).get("ret", 0))
        if base_ret != 0:
            raise RuntimeError(f"微信公众号合集分页失败：ret={base_ret}")
        payload = data.get("getalbum_resp") or {}
        raw_items = payload.get("article_list") or []
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        items = [
            AlbumItem(
                msgid=str(item.get("msgid") or ""),
                itemidx=str(item.get("itemidx") or ""),
                title=html.unescape(str(item.get("title") or "")),
                url=html.unescape(str(item.get("url") or "")).replace(
                    "http://", "https://", 1
                ),
            )
            for item in raw_items
            if item.get("msgid")
            and item.get("itemidx")
            and item.get("title")
            and item.get("url")
        ]
        return items, bool(int(payload.get("continue_flag", 0))), None

    items = _parse_album_html(response.text)
    flag_match = _CONTINUE_FLAG_RE.search(response.text)
    count_match = _ARTICLE_COUNT_RE.search(response.text)
    return (
        items,
        bool(int(flag_match.group(1))) if flag_match else False,
        int(count_match.group(1)) if count_match else None,
    )


def _chronological_page(items: list[AlbumItem]) -> list[AlbumItem]:
    if len(items) < 2:
        return items
    msgids = [int(item.msgid) for item in items if item.msgid.isdigit()]
    if len(msgids) == len(items) and msgids[0] > msgids[-1]:
        return list(reversed(items))
    return items


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
    items, has_more, total_count = _response_album_page(response)
    if not items:
        raise RuntimeError("微信公众号合集里没有解析到文章")

    parsed_url = urlparse(album_url)
    query = parse_qs(parsed_url.query)
    biz = query.get("__biz", [""])[0]
    album_id = query.get("album_id", [""])[0]
    if has_more and (not biz or not album_id):
        raise RuntimeError("微信公众号合集 URL 缺少 __biz 或 album_id，无法加载更多")

    seen = {item.key for item in items}
    for _page_number in range(2, _MAX_ALBUM_PAGES + 1):
        if not has_more or (total_count is not None and len(items) >= total_count):
            break
        cursor = items[-1]
        page_url = (
            f"{parsed_url.scheme or 'https'}://"
            f"{parsed_url.netloc or 'mp.weixin.qq.com'}/mp/appmsgalbum"
        )
        page_headers = {
            **REQUEST_HEADERS,
            "Referer": album_url,
            "X-Requested-With": "XMLHttpRequest",
        }
        page_response = requests.get(
            page_url,
            headers=page_headers,
            params={
                "action": "getalbum",
                "__biz": biz,
                "album_id": album_id,
                "count": _ALBUM_PAGE_SIZE,
                "begin_msgid": cursor.msgid,
                "begin_itemidx": cursor.itemidx,
            },
            timeout=timeout,
        )
        page_response.raise_for_status()
        page_items, has_more, page_total = _response_album_page(page_response)
        if page_total is not None:
            total_count = page_total
        new_items = [
            item for item in _chronological_page(page_items) if item.key not in seen
        ]
        if not new_items:
            raise RuntimeError("微信公众号合集分页没有返回新文章，已停止以避免死循环")
        items.extend(new_items)
        seen.update(item.key for item in new_items)
    else:
        raise RuntimeError(f"微信公众号合集分页超过 {_MAX_ALBUM_PAGES} 页，已停止")

    if total_count is not None and len(items) < total_count:
        raise RuntimeError(
            f"微信公众号合集抓取不完整：应有 {total_count} 篇，实际 {len(items)} 篇"
        )
    return items


def fetch_article(item: AlbumItem, *, timeout: int = 30) -> tuple[str, str]:
    response = requests.get(item.url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    title, body_md = article_html_to_markdown(response.text, item.title)
    if len(body_md) < 100:
        raise RuntimeError(f"公众号正文解析失败：{item.title}")
    return title, body_md


def _image_suffix(url: str, content_type: str) -> str:
    media_type = content_type.partition(";")[0].strip().lower()
    if media_type in _IMAGE_SUFFIXES:
        return _IMAGE_SUFFIXES[media_type]
    wx_fmt = parse_qs(urlparse(url).query).get("wx_fmt", [""])[0].lower()
    if wx_fmt in {"gif", "jpeg", "jpg", "png", "svg", "webp"}:
        return ".jpg" if wx_fmt == "jpeg" else f".{wx_fmt}"
    return ".img"


def _materialize_remote_images(
    body_md: str,
    cache_dir: Path,
    *,
    timeout: int = 30,
) -> str:
    """Download remote Markdown images so Zhihu can upload them itself."""
    refs = [
        match.group(2)
        for match in _MARKDOWN_IMAGE_RE.finditer(body_md)
        if re.match(r"^https?://", match.group(2), re.I)
    ]
    if not refs:
        return body_md

    cache_dir.mkdir(parents=True, exist_ok=True)
    replacements: dict[str, str] = {}
    for ref in dict.fromkeys(refs):
        digest = hashlib.sha256(ref.encode("utf-8")).hexdigest()[:24]
        cached = next(
            (path for path in cache_dir.glob(f"{digest}.*") if not path.name.endswith(".tmp")),
            None,
        )
        if cached is None:
            response = requests.get(
                ref,
                headers=REQUEST_HEADERS,
                timeout=timeout,
            )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if not content_type.lower().startswith("image/"):
                raise RuntimeError(
                    f"公众号图片下载结果不是图片：{content_type or 'unknown'} | {ref}"
                )
            if not response.content:
                raise RuntimeError(f"公众号图片下载为空：{ref}")
            cached = cache_dir / f"{digest}{_image_suffix(ref, content_type)}"
            tmp = cached.with_suffix(cached.suffix + ".tmp")
            tmp.write_bytes(response.content)
            tmp.replace(cached)
            log.info("已缓存公众号正文图片：%s", cached)
        replacements[ref] = cached.resolve().as_posix()

    def replace_image(match: re.Match[str]) -> str:
        ref = match.group(2)
        local = replacements.get(ref)
        return match.group(0) if local is None else match.group(0).replace(ref, local, 1)

    return _MARKDOWN_IMAGE_RE.sub(replace_image, body_md)


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
    image_dir = (
        PROJECT_ROOT / "data" / "wechat_album" / "images"
        / target.key.replace(":", "_")
    )
    body_md = _materialize_remote_images(body_md, image_dir)
    log.info("选中合集文章：%s（%s）", title, target.key)
    article_url = publish_article(
        title,
        body_md,
        dry_run=dry_run,
        column_name=cfg["column_name"],
        source_dir=image_dir,
        image_cache_path=image_dir / "zhihu_urls.json",
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
