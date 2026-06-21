#!/usr/bin/env python3
"""扫 docs/pending/，把其中**最早的一篇** .md 发布到知乎专栏「Agent工坊」。

行为：
- 目录为空 → 不发，正常退出（exit 0）
- 即便有多篇也只发一篇（按 mtime 最早）
- 发完移动到 docs/published/ 并写 {stem}.meta.json

用法：
    python scripts/publish_articles.py            # 真发
    python scripts/publish_articles.py --dry-run  # 走流程但不点最终发布按钮
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.article_pipeline import publish_one_pending  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="走完编辑器流程但不点最终发布；可用来验证标题/正文是否正确",
    )
    args = parser.parse_args()

    url = publish_one_pending(dry_run=args.dry_run)
    if url:
        print(url)
    sys.exit(0)
