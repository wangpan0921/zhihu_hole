#!/usr/bin/env python3
"""给已生成的草稿补上出处（书名）。

背景：读书（book_reflection）模式生成的想法以前正文末尾没有署出处。
新生成的想法已自动署名，但已经落盘的 pending 草稿需要回填。

用法：
    # 默认：回填明天（cron 19:00 预生成的那批）的草稿
    python scripts/backfill_book_source.py --for tomorrow

    python scripts/backfill_book_source.py --date 2026-06-09
    python scripts/backfill_book_source.py --date 2026-06-09 --dry-run
    python scripts/backfill_book_source.py --all          # 回填 pending/ 里所有草稿

只处理 mode == book_reflection 且带 book.book_title 的草稿；
themes 模式草稿原样跳过。幂等：已署名的草稿不会重复追加。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.content_generator import append_book_source  # noqa: E402
from src.utils import PENDING_DIR, get_logger  # noqa: E402

log = get_logger("backfill")


def _backfill_file(path: Path, *, dry_run: bool) -> bool:
    """回填单个草稿。返回是否发生了改动。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("跳过（无法解析）：%s（%s）", path.name, e)
        return False

    if (data.get("mode") or "").strip() != "book_reflection":
        log.info("跳过（非读书模式）：%s", path.name)
        return False

    book_title = (data.get("book") or {}).get("book_title", "")
    if not book_title:
        log.warning("跳过（缺少书名）：%s", path.name)
        return False

    old_body = data.get("body") or ""
    new_body = append_book_source(old_body, book_title)
    if new_body == old_body:
        log.info("已署名，跳过：%s", path.name)
        return False

    if dry_run:
        log.info("[dry-run] 将补出处《%s》：%s", book_title, path.name)
        return True

    data["body"] = new_body
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("已补出处《%s》：%s", book_title, path.name)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--for", dest="for_when", choices=["today", "tomorrow"],
        help="回填今天或明天的草稿",
    )
    g.add_argument("--date", help="YYYY-MM-DD 显式指定日期")
    g.add_argument("--all", action="store_true", help="回填 pending/ 里所有草稿")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写盘")
    args = parser.parse_args()

    if args.all:
        targets = sorted(PENDING_DIR.glob("*.json"))
    else:
        if args.date:
            date = dt.date.fromisoformat(args.date)
        elif args.for_when == "tomorrow":
            date = dt.date.today() + dt.timedelta(days=1)
        else:
            date = dt.date.today()
        targets = sorted(PENDING_DIR.glob(f"{date.isoformat()}_*.json"))

    if not targets:
        log.warning("没有匹配的草稿（PENDING_DIR=%s）", PENDING_DIR)
        return 0

    changed = 0
    for p in targets:
        if _backfill_file(p, dry_run=args.dry_run):
            changed += 1
    log.info("完成：扫描 %d 个，%s %d 个", len(targets),
             "将改动" if args.dry_run else "改动", changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
