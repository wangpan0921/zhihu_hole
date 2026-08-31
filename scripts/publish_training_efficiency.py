#!/usr/bin/env python3
"""Publish one reviewed training-efficiency article at a time.

The cron job calls this entry at 21:00. Human-reviewed files must be moved
from ``pytorch_training_efficiency/docs/draft`` to ``pending`` first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.training_efficiency_pipeline import publish_one, repair_zhihu_meta  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示 21:00 本次会选择的文章，不打开浏览器、不发布",
    )
    parser.add_argument(
        "--platform",
        choices=("both", "zhihu", "wechat"),
        default="both",
        help="实际发布的平台；默认同时发布知乎和公众号",
    )
    parser.add_argument(
        "--repair-zhihu-url",
        help="记录已确认发布的知乎 URL，不会打开浏览器；用于发布后校验异常的修复",
    )
    parser.add_argument(
        "--file",
        help="配合 --repair-zhihu-url 指定 pending 中的 Markdown 文件名",
    )
    args = parser.parse_args()
    if args.repair_zhihu_url:
        result = (
            {"dry_run": True, "repair_zhihu_url": args.repair_zhihu_url, "file": args.file}
            if args.dry_run
            else repair_zhihu_meta(args.repair_zhihu_url, filename=args.file)
        )
    else:
        result = publish_one(dry_run=args.dry_run, platform=args.platform)
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
