#!/usr/bin/env python3
"""Publish the next article from the configured WeChat album to Zhihu."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.wechat_album_to_zhihu import publish_next  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    url = publish_next(dry_run=args.dry_run)
    if url:
        print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
