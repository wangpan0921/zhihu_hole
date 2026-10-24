#!/usr/bin/env python3
"""抓取公开商业/经济 RSS，生成并发布 MBA 每日商业情报简报。"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = PROJECT_ROOT / "mba" / "content" / "news_sources.yaml"
MBA_CONFIG_FILE = PROJECT_ROOT / "mba" / "config.yaml"
STATE_FILE = PROJECT_ROOT / "mba" / "news_state.json"
LOG_FILE = PROJECT_ROOT / "logs" / "mba-news.log"
ARCHIVE_DIR = PROJECT_ROOT / "mba" / "archive"


def load_mba_config() -> dict[str, Any]:
    return yaml.safe_load(MBA_CONFIG_FILE.read_text(encoding="utf-8")) or {}


def validate_ring_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "www.zhihu.com":
        raise ValueError("MBA 圈子地址必须是 https://www.zhihu.com 下的链接")
    if not re.fullmatch(r"/ring/host/\d+", parsed.path):
        raise ValueError("MBA 圈子地址不是有效的 /ring/host/<id> 链接")
    return url


def clean_text(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _first(element: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        for child in list(element):
            if child.tag.rsplit("}", 1)[-1].lower() == name and child.text:
                return clean_text(child.text)
    return ""


def parse_feed(xml_bytes: bytes, source: dict[str, Any]) -> list[dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    entries = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    items: list[dict[str, str]] = []
    for node in entries[:12]:
        title = _first(node, ("title",))
        link = _first(node, ("link",))
        if not link:
            for child in list(node):
                if child.tag.rsplit("}", 1)[-1].lower() == "link":
                    link = child.attrib.get("href", "")
                    break
        summary = _first(node, ("encoded", "content", "description", "summary"))
        published = _first(node, ("pubdate", "published", "updated", "date"))
        if title and link and urlparse(link).scheme in {"http", "https"}:
            items.append({"source_id": source["id"], "source": source["name"], "focus": source.get("focus", ""), "title": title, "link": link, "summary": summary[:3000], "published": published})
    return items


def _decode_response(response: requests.Response) -> str:
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def parse_html_list(response: requests.Response, source: dict[str, Any]) -> list[dict[str, str]]:
    soup = BeautifulSoup(_decode_response(response), "html.parser")
    pattern = re.compile(source["link_pattern"])
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        link = urljoin(source["url"], anchor.get("href", ""))
        if link in seen or not pattern.fullmatch(link):
            continue
        heading = anchor.select_one("h1, h2, h3, h4")
        title = clean_text(heading.get_text(" ") if heading else anchor.get("title") or anchor.get_text(" "))
        if len(title) < 8:
            continue
        seen.add(link)
        items.append({
            "source_id": source["id"],
            "source": source["name"],
            "focus": source.get("focus", ""),
            "title": title[:160],
            "link": link,
            "summary": "",
            "published": "",
        })
        if len(items) >= int(source.get("max_items", 10)):
            break
    return items


def extract_article_text(item: dict[str, str], timeout: int = 20) -> str:
    response = requests.get(item["link"], headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(_decode_response(response), "html.parser")
    for node in soup.select("script, style, nav, header, footer, aside, form"):
        node.decompose()
    selectors = ("article", ".article-content", ".m-text", ".content", ".TRS_Editor", "#zoom", "main")
    container = next((soup.select_one(selector) for selector in selectors if soup.select_one(selector)), soup.body or soup)
    paragraphs: list[str] = []
    blocked = ("责任编辑", "免责声明", "下载客户端", "订阅", "登录后", "关注微信公众号", "未经授权")
    for node in container.select("p, h2, h3, li"):
        text = clean_text(node.get_text(" "))
        if len(text) >= 25 and not any(word in text for word in blocked):
            paragraphs.append(text)
    if not paragraphs:
        meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
        if meta:
            paragraphs.append(clean_text(meta.get("content")))
    return "\n".join(paragraphs)[:6000]


def fetch_items(timeout: int = 20) -> tuple[list[dict[str, str]], list[str]]:
    config = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8")) or {}
    items: list[dict[str, str]] = []
    errors: list[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MBA-business-digest/1.0)"}
    for source in config.get("sources", []):
        if not source.get("enabled", True):
            continue
        try:
            response = requests.get(source["url"], headers=headers, timeout=timeout)
            response.raise_for_status()
            if source.get("kind", "rss") == "html_list":
                items.extend(parse_html_list(response, source))
            else:
                items.extend(parse_feed(response.content, source))
        except (OSError, requests.RequestException, ET.ParseError, KeyError, ValueError) as exc:
            errors.append(f"{source.get('id', 'unknown')}: {exc}")
    unique: dict[str, dict[str, str]] = {}
    for item in items:
        unique.setdefault(item["link"], item)
    return list(unique.values()), errors


def enrich_items(items: list[dict[str, str]], timeout: int = 20) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    for item in items:
        try:
            article_text = extract_article_text(item, timeout=timeout)
            if article_text:
                item["article_text"] = article_text
        except (OSError, requests.RequestException, ValueError) as exc:
            errors.append(f"{item['source_id']}: {exc}")
    return items, errors


def relevance_score(item: dict[str, str]) -> int:
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    keywords = ("ai", "agent", "消费", "创业", "企业", "生产率", "融资", "就业", "利率", "pmi", "利润", "出海", "小微", "用户", "供应链", "成本")
    score = sum(1 for keyword in keywords if keyword in text)
    score += {"iresearch": 5, "stats": 4, "pbc": 3, "yicai": 2, "tmtpost": 1}.get(item.get("source_id", ""), 0)
    if any(word in text for word in ("值得买入", "个股", "股价", "涨停", "投资机会")):
        score -= 6
    return score


def choose_items(items: list[dict[str, str]], state: dict[str, Any], limit: int = 5) -> list[dict[str, str]]:
    seen = set(state.get("seen_links", []))
    candidates = [item for item in items if item["link"] not in seen] or items
    # 先按相关性排序，再按来源轮询，避免某个 RSS 占满整条简报。
    ranked = sorted(candidates, key=relevance_score, reverse=True)
    by_source: dict[str, list[dict[str, str]]] = {}
    for item in ranked:
        by_source.setdefault(item["source"], []).append(item)
    selected: list[dict[str, str]] = []
    while len(selected) < limit and by_source:
        for source in list(by_source):
            bucket = by_source[source]
            if bucket:
                selected.append(bucket.pop(0))
                if len(selected) >= limit:
                    break
            if not bucket:
                by_source.pop(source, None)
    return selected


def fallback_digest(items: list[dict[str, str]], today: dt.date) -> str:
    item = items[0]
    excerpt = (item.get("article_text") or item.get("summary") or "暂无公开摘要").strip()
    excerpt = excerpt[:900]
    lines = [f"MBA 商业简报 | {today:%Y-%m-%d}", f"【{item['title']}】", f"来源：{item['source']}", "", f"要点：{excerpt}"]
    if item.get("focus"):
        lines.append(f"\n经营提示：这条信息属于“{item['focus']}”方向，先判断它会影响你的需求、价格、成本、融资或渠道中的哪一项，再决定是否行动。")
    lines.append(f"\n原文：{item['link']}")
    lines.append("\n说明：内容基于公开页面的标题、摘要和可访问段落整理，建议打开原文核对完整上下文。")
    return "\n".join(lines)


def summarize(items: list[dict[str, str]], today: dt.date) -> str:
    try:
        from src.content_generator import _call_llm, _extract_json

        evidence = "\n".join(
            f"[{i + 1}] 来源：{x['source']}；主题：{x.get('focus', '')}；标题：{x['title']}；原文摘要：{x.get('summary', '')}；公开正文摘录：{x.get('article_text', '')[:5000]}；链接：{x['link']}"
            for i, x in enumerate(items)
        )
        prompt = f"""日期：{today:%Y-%m-%d}
以下是中文财经媒体、官方数据或公开行业报告的材料，只能依据提供的内容，不得补写或猜测：
{evidence}

请输出严格 JSON：{{"headline":"一句不超过35字的结论","summary":"180-280字中文摘要，优先保留原文中的数字、时间、范围和限制条件","business_value":"80-150字，说明它对普通创业者/经营者具体影响哪个变量，以及什么情况下值得关注"}}。
不要写群讨论、不要写口号、不要给投资买卖建议。若材料不足以得出结论，明确写“公开材料不足”，不要用常识补齐。"""
        raw, _ = _call_llm("你是中文财经与行业报告编辑，重视来源、数字和上下文。", prompt)
        data = _extract_json(raw)
        item = items[0]
        lines = [f"MBA 商业简报 | {today:%Y-%m-%d}", f"【{item['title']}】", f"来源：{item['source']}", "", f"摘要：{data.get('summary', '')}", f"经营含义：{data.get('business_value', '')}", f"原文：{item['link']}"]
        return "\n".join(lines)
    except Exception:
        return fallback_digest(items, today)


def save_archive(target_date: dt.date, message: str) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE_DIR / f"{target_date.isoformat()}.md"
    path.write_text(message + "\n", encoding="utf-8")
    return path


def send_zhihu(message: str, target_date: dt.date, ring_url: str, *, dry_run: bool) -> None:
    from src.zhihu_publisher import publish

    lines = message.splitlines()
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else message
    title = f"每日商业情报｜{target_date:%m月%d日}"
    if len(body) > 950:
        body = body[:900].rsplit("\n", 1)[0] + "\n\n篇幅所限，更多来源见当日归档。"
    publish(title, body, dry_run=dry_run, ring_url=validate_ring_url(ring_url))


def send_webhook(message: str, channel: str, webhook: str) -> None:
    payload = ({"msg_type": "text", "content": {"text": message}} if channel == "feishu" else {"msgtype": "text", "text": {"content": message}})
    response = requests.post(webhook, json=payload, timeout=20)
    response.raise_for_status()
    body = response.json()
    if (channel == "feishu" and body.get("code", 0) != 0) or (channel == "wechat" and body.get("errcode", 0) != 0):
        raise RuntimeError(f"{channel} webhook 返回错误：{body}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=dt.date.fromisoformat, default=dt.date.today())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--channel", choices=("zhihu", "feishu", "wechat"), default="zhihu")
    parser.add_argument("--verify-target", action="store_true", help="dry-run 时验证知乎目标圈子，不点发布")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    mba_config = load_mba_config()
    first_publish_date = dt.date.fromisoformat(str(mba_config["first_publish_date"]))
    if not args.dry_run and args.date < first_publish_date and not args.force:
        print(f"已跳过：MBA 首次发布日期为 {first_publish_date}")
        return 0
    items, errors = fetch_items()
    if not items:
        raise RuntimeError("所有新闻源均抓取失败或没有可用条目：" + "; ".join(errors))
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    if not args.force and state.get("last_digest_date") == args.date.isoformat():
        print(f"已跳过：{args.date} 已生成简报（使用 --force 重发）")
        return 0
    configured_limit = int(mba_config.get("items_per_digest", 1))
    selected = choose_items(items, state, max(1, min(args.limit or configured_limit, 10)))
    selected, enrich_errors = enrich_items(selected[:1])
    errors.extend(enrich_errors)
    message = summarize(selected, args.date)
    archive_path = save_archive(args.date, message)
    print(f"已生成简报归档：{archive_path.relative_to(PROJECT_ROOT)}")
    print(message)
    if args.dry_run:
        if args.channel == "zhihu" and args.verify_target:
            send_zhihu(message, args.date, mba_config["zhihu_ring_url"], dry_run=True)
        return 0
    if args.channel == "zhihu":
        send_zhihu(message, args.date, mba_config["zhihu_ring_url"], dry_run=False)
        channel = "zhihu"
    else:
        feishu = os.getenv("MBA_FEISHU_WEBHOOK", "").strip()
        wechat = os.getenv("MBA_WECHAT_WEBHOOK", "").strip()
        channel, webhook = (("feishu", feishu) if args.channel == "feishu" else ("wechat", wechat))
        if not webhook:
            raise RuntimeError(f"未配置 {channel} webhook；请先使用 --dry-run")
        send_webhook(message, channel, webhook)
    links = (state.get("seen_links", []) + [x["link"] for x in selected])[-200:]
    STATE_FILE.write_text(json.dumps({"last_digest_date": args.date.isoformat(), "seen_links": links}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"{args.date.isoformat()} published {len(selected)} items via {channel}; source_errors={errors}\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"MBA 新闻简报失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
