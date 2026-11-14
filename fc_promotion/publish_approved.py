"""06 点发布前一天人工审核通过的知乎推广记录。"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any

from . import config
from .common.feishu_bitable import FeishuBitable, FeishuError
from .promote import Lead, post_comment_zhihu


def _date(value: Any) -> dt.date | None:
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone(dt.timedelta(hours=8))).date()
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value[:10].replace("/", "-"))
        except ValueError:
            return None
    return None


def _link(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("link") or value.get("url") or "").strip()
    return ""


def _is_zhihu(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    return any(str(item).strip().lower() in {"知乎", "zhihu"} for item in values)


def load_approved(target_date: dt.date) -> tuple[FeishuBitable, str, list[dict[str, Any]]]:
    bitable = FeishuBitable()
    app_token = bitable.resolve_app_token(config.FEISHU_PROMO_URL)
    names = set(bitable.list_field_names(app_token=app_token, table_id=config.FEISHU_PROMO_TABLE_ID))
    required = {config.FIELD_DATE, config.FIELD_PLATFORM, config.FIELD_TARGET_URL, config.FIELD_REVIEW, config.FIELD_PUBLISHED, config.FIELD_COMMENT}
    missing = required - names
    if missing:
        raise FeishuError(f"推广数据库缺少字段：{sorted(missing)}")
    selected = []
    for record in bitable.list_records(app_token=app_token, table_id=config.FEISHU_PROMO_TABLE_ID):
        fields = record.get("fields", {})
        url = _link(fields.get(config.FIELD_TARGET_URL))
        if (_date(fields.get(config.FIELD_DATE)) == target_date and _is_zhihu(fields.get(config.FIELD_PLATFORM))
                and fields.get(config.FIELD_REVIEW) == "是" and fields.get(config.FIELD_PUBLISHED) != "是"
                and url and str(fields.get(config.FIELD_COMMENT) or "").strip()):
            selected.append(record)
    return bitable, app_token, selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发布推广数据库中人工审核通过的知乎记录")
    parser.add_argument("--date", type=dt.date.fromisoformat, default=dt.date.today() - dt.timedelta(days=1), help="目标日期，默认昨天")
    parser.add_argument("--max", type=int, default=None, help="最多发布几条")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不打开知乎")
    args = parser.parse_args(argv)
    try:
        bitable, app_token, records = load_approved(args.date)
    except (FeishuError, RuntimeError) as exc:
        print(f"错误：读取推广数据库失败：{exc}", file=sys.stderr)
        return 2
    if args.max is not None:
        records = records[:args.max]
    print(f"找到 {len(records)} 条 {args.date.isoformat()} 已审核记录。")
    for record in records:
        fields = record["fields"]
        print(f"- {_link(fields.get(config.FIELD_TARGET_URL))}（record={record.get('record_id')}）")
    if args.dry_run:
        return 0
    failed = 0
    for record in records:
        fields = record["fields"]
        lead = Lead(platform="zhihu", title="飞书审核通过记录", url=_link(fields.get(config.FIELD_TARGET_URL)), comment=str(fields[config.FIELD_COMMENT]))
        if post_comment_zhihu(lead, draft=False):
            bitable.update_record(
                app_token=app_token,
                table_id=config.FEISHU_PROMO_TABLE_ID,
                record_id=record.get("record_id", ""),
                fields={config.FIELD_PUBLISHED: "是"},
            )
            print(f"已发布并回写：{lead.url}")
        else:
            failed += 1
            print(f"发布失败：{lead.url}", file=sys.stderr)
    return 3 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
