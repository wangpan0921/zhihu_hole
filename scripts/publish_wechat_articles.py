#!/usr/bin/env python3
"""扫 docs/pending/，把其中最早的一篇 .md 发布到微信公众号。

用法：
    python scripts/publish_wechat_articles.py
    python scripts/publish_wechat_articles.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.wechat_article_pipeline import publish_one_pending_to_wechat  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只填入微信公众号编辑器，不点击保存/发表，也不归档",
    )
    args = parser.parse_args()

    url = publish_one_pending_to_wechat(dry_run=args.dry_run)
    if url:
        print(url)
    sys.exit(0)
