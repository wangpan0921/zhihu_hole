"""读取飞书推广数据库中当天的知乎草稿链接并正式发布。"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any

from . import config
from .common.feishu_bitable import FeishuBitable, FeishuError
from .common.logging_utils import get_logger
from .promote import Lead, publish_saved_zhihu_draft

log = get_logger("publish_today_drafts")


def _record_date(value: Any) -> dt.date | None:
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone(dt.timedelta(hours=8))).date()
    if isinstance(value, str):
        text = value.strip().replace("/", "-")
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def _is_zhihu(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    return any(str(item).strip().lower() in {"知乎", "zhihu"} for item in values)


def _link(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("link") or value.get("url") or "").strip()
    return ""


def select_drafts(records: list[dict[str, Any]], target_date: dt.date) -> list[Lead]:
    """从飞书记录中筛出指定日期的知乎问题链接并去重。"""
    leads: list[Lead] = []
    seen: set[str] = set()
    for record in records:
        fields = record.get("fields") or {}
        if _record_date(fields.get(config.FIELD_DATE)) != target_date:
            continue
        if not _is_zhihu(fields.get(config.FIELD_PLATFORM)):
            continue
        url = _link(fields.get(config.FIELD_TARGET_URL)).split("/answer/", 1)[0].rstrip("/")
        if not url.startswith("https://www.zhihu.com/question/") or url in seen:
            continue
        seen.add(url)
        leads.append(
            Lead(
                platform="zhihu",
                title=f"飞书草稿记录 {record.get('record_id') or record.get('id') or ''}".strip(),
                url=url,
                status="待发布草稿",
                extra={"record_id": record.get("record_id") or record.get("id") or ""},
            )
        )
    return leads


def load_drafts(target_date: dt.date) -> list[Lead]:
    bitable = FeishuBitable()
    app_token = bitable.resolve_app_token(config.FEISHU_PROMO_URL)
    required_fields = {config.FIELD_DATE, config.FIELD_PLATFORM, config.FIELD_TARGET_URL}
    actual_fields = set(
        bitable.list_field_names(app_token=app_token, table_id=config.FEISHU_PROMO_TABLE_ID)
    )
    missing_fields = required_fields - actual_fields
    if missing_fields:
        raise FeishuError(f"推广数据库缺少必要字段：{sorted(missing_fields)}")
    records = bitable.list_records(app_token=app_token, table_id=config.FEISHU_PROMO_TABLE_ID)
    if records and all(not (record.get("fields") or {}) for record in records):
        raise FeishuError("能读取记录 ID，但记录字段为空；请检查多维表格字段读取权限")
    return select_drafts(records, target_date)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发布推广数据库中指定日期的知乎草稿")
    parser.add_argument("--date", type=dt.date.fromisoformat, default=dt.date.today(), help="日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--max", type=int, default=None, help="最多发布几条，默认发布当天全部草稿")
    parser.add_argument("--dry-run", action="store_true", help="只列出草稿，不打开知乎、不发布")
    args = parser.parse_args(argv)

    if args.max is not None and args.max < 1:
        parser.error("--max 必须大于 0")
    try:
        drafts = load_drafts(args.date)
    except (FeishuError, RuntimeError) as exc:
        log.error("读取推广数据库失败：%s", exc)
        print(f"错误：读取推广数据库失败：{exc}", file=sys.stderr)
        return 2
    if args.max is not None:
        drafts = drafts[: args.max]
    if not drafts:
        print(f"{args.date.isoformat()} 没有可发布的知乎草稿记录。")
        return 1

    print(f"找到 {len(drafts)} 条 {args.date.isoformat()} 的知乎草稿：")
    for draft in drafts:
        print(f"- {draft.url}（record={draft.extra['record_id']}）")
    if args.dry_run:
        return 0

    failed = 0
    for draft in drafts:
        if publish_saved_zhihu_draft(draft):
            print(f"{draft.status}：{draft.url}")
        else:
            failed += 1
            print(f"发布失败：{draft.url}", file=sys.stderr)
    return 3 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
