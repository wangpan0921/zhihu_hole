#!/usr/bin/env python3
"""发布在职 MBA 群的每日内容。

默认读取已经审核的 YAML 内容；没有 webhook 或使用 --dry-run 时只预览。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTENT_FILE = PROJECT_ROOT / "mba" / "content" / "week_01.yaml"
STATE_FILE = PROJECT_ROOT / "mba" / "state.json"
LOG_FILE = PROJECT_ROOT / "logs" / "mba.log"


def load_content() -> dict[str, Any]:
    with CONTENT_FILE.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def format_message(item: dict[str, Any], target_date: date) -> str:
    return (
        f"MBA 每日一得 | {target_date:%Y-%m-%d} | {item['theme']}\n"
        f"【{item['title']}】\n"
        f"{item['idea']}\n\n"
        f"场景：{item['example']}\n"
        f"工具：{item['method']}\n"
        f"可直接套用：{item['template']}\n"
        f"判断标准：{item['metric']}\n"
        f"常见坑：{item['pitfall']}\n"
        f"今天行动：{item['action']}\n"
        f"讨论：{item['question']}"
    )


def read_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(payload: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def send_webhook(message: str, channel: str, webhook: str) -> None:
    if channel == "feishu":
        payload = {"msg_type": "text", "content": {"text": message}}
    else:
        payload = {"msgtype": "text", "text": {"content": message}}
    response = requests.post(webhook, json=payload, timeout=20)
    response.raise_for_status()
    body = response.json()
    if channel == "feishu" and body.get("code", 0) != 0:
        raise RuntimeError(f"飞书 webhook 返回错误：{body}")
    if channel == "wechat" and body.get("errcode", 0) != 0:
        raise RuntimeError(f"企业微信 webhook 返回错误：{body}")


def main() -> int:
    parser = argparse.ArgumentParser(description="发布 MBA 群每日内容")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD，默认今天")
    parser.add_argument("--channel", choices=("auto", "feishu", "wechat"), default="auto")
    parser.add_argument("--dry-run", action="store_true", help="只打印消息，不发送")
    parser.add_argument("--force", action="store_true", help="忽略当天已发布状态")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env", override=True)
    content = load_content()
    matches = [item for item in content.get("items", []) if item.get("weekday") == args.date.weekday()]
    if not matches:
        raise RuntimeError(f"内容库没有星期 {args.date.weekday()} 的条目")
    message = format_message(matches[0], args.date)
    state = read_state()
    if not args.force and state.get("last_published_date") == args.date.isoformat():
        print(f"已跳过：{args.date} 已发布（使用 --force 重发）")
        return 0
    print(message)
    if args.dry_run:
        return 0

    feishu = os.getenv("MBA_FEISHU_WEBHOOK", "").strip()
    wechat = os.getenv("MBA_WECHAT_WEBHOOK", "").strip()
    if args.channel == "feishu":
        channel, webhook = "feishu", feishu
    elif args.channel == "wechat":
        channel, webhook = "wechat", wechat
    elif feishu:
        channel, webhook = "feishu", feishu
    elif wechat:
        channel, webhook = "wechat", wechat
    else:
        raise RuntimeError("未配置 MBA_FEISHU_WEBHOOK 或 MBA_WECHAT_WEBHOOK；请先 --dry-run 预览")

    send_webhook(message, channel, webhook)
    write_state({"last_published_date": args.date.isoformat(), "channel": channel, "title": matches[0]["title"]})
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"{args.date.isoformat()} published via {channel}: {matches[0]['title']}\n")
    print(f"已发布到 {channel}，状态已记录到 {STATE_FILE}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"MBA 发布失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
