#!/usr/bin/env python3
"""为指定日期所有 slot 预生成草稿。

用法：
    python scripts/generate_drafts.py                 # 默认：今天
    python scripts/generate_drafts.py --for tomorrow  # 明天（cron 19:00 用）
    python scripts/generate_drafts.py --for today
    python scripts/generate_drafts.py --date 2026-05-18
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scheduler import generate_all_today  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--for", dest="for_when", choices=["today", "tomorrow"], default="today")
    g.add_argument("--date", help="YYYY-MM-DD 显式指定日期")
    args = parser.parse_args()

    if args.date:
        target = dt.date.fromisoformat(args.date)
    elif args.for_when == "tomorrow":
        target = dt.date.today() + dt.timedelta(days=1)
    else:
        target = dt.date.today()

    paths = generate_all_today(date=target)
    for p in paths:
        print(p)
