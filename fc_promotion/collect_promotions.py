"""18 点采集知乎线索，写入推广数据库等待人工审核。"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from typing import Any

from . import config, copywriter
from .common.feishu_bitable import FeishuBitable, FeishuError
from .common.logging_utils import get_logger
from .promote import Lead, _canonical_zhihu_question_url, search_zhihu_leads

log = get_logger("collect_promotions")


def _link(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("link") or value.get("url") or "").strip()
    return ""


def _date_ms(value: dt.date) -> int:
    return int(
        dt.datetime.combine(value, dt.time.min, tzinfo=dt.timezone(dt.timedelta(hours=8))).timestamp()
        * 1000
    )


def _plain_recommendation(title: str) -> str:
    text = copywriter.generate_comment(question_title=title, platform="zhihu")
    return re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text).strip()


def _question_titles(urls: list[str]) -> dict[str, str]:
    """用已登录知乎页面读取旧记录标题；失败时返回空标题。"""
    if not urls:
        return {}
    from .common import humanized_browser as hb

    titles: dict[str, str] = {}
    try:
        with hb.persistent_context(config.ZHIHU_PROFILE, headless=True) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=40000)
                    title = (page.title() or "").replace(" - 知乎", "").strip()
                    if title:
                        titles[url] = title
                except Exception as exc:  # noqa: BLE001
                    log.warning("读取问题标题失败：%s | %s", url, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("无法打开知乎标题读取浏览器：%s", exc)
    return titles


def _records(bitable: FeishuBitable) -> tuple[str, list[dict[str, Any]]]:
    app_token = bitable.resolve_app_token(config.FEISHU_PROMO_URL)
    names = set(bitable.list_field_names(app_token=app_token, table_id=config.FEISHU_PROMO_TABLE_ID))
    required = {
        config.FIELD_DATE,
        config.FIELD_PLATFORM,
        config.FIELD_TARGET_URL,
        config.FIELD_REVIEW,
        config.FIELD_PUBLISHED,
        config.FIELD_COMMENT,
    }
    missing = required - names
    if missing:
        raise FeishuError(f"推广数据库缺少字段：{sorted(missing)}")
    return app_token, bitable.list_records(app_token=app_token, table_id=config.FEISHU_PROMO_TABLE_ID)


def _is_zhihu(record: dict[str, Any]) -> bool:
    value = record.get("fields", {}).get(config.FIELD_PLATFORM)
    values = value if isinstance(value, list) else [value]
    return any(str(item).strip().lower() in {"知乎", "zhihu"} for item in values)


def run(*, max_leads: int = 1, backfill: bool = True) -> list[Lead]:
    bitable = FeishuBitable()
    app_token, records = _records(bitable)
    existing: dict[str, dict[str, Any]] = {}
    missing_recommendations: list[str] = []
    for record in records:
        if not _is_zhihu(record):
            continue
        url = _canonical_zhihu_question_url(_link(record.get("fields", {}).get(config.FIELD_TARGET_URL)))
        if not url:
            continue
        existing[url] = record
        fields = record.get("fields", {})
        if backfill and fields.get(config.FIELD_REVIEW) == "是" and not str(fields.get(config.FIELD_COMMENT) or "").strip():
            missing_recommendations.append(url)

    if missing_recommendations:
        titles = _question_titles(missing_recommendations)
        for url in missing_recommendations:
            recommendation = _plain_recommendation(titles.get(url, "这个问题可以试试带秒的悬浮时钟"))
            record = existing[url]
            bitable.update_record(
                app_token=app_token,
                table_id=config.FEISHU_PROMO_TABLE_ID,
                record_id=record.get("record_id", ""),
                fields={config.FIELD_COMMENT: recommendation},
            )
            log.info("已回填推荐文案：%s", url)

    leads = search_zhihu_leads(
        config.SEARCH_KEYWORDS,
        max_leads,
        exclude_urls=set(existing),
        search_round=0,
    )
    today = dt.date.today()
    for lead in leads:
        lead.comment = _plain_recommendation(lead.title)
        record_id = bitable.append_record(
            app_token=app_token,
            table_id=config.FEISHU_PROMO_TABLE_ID,
            fields={
                config.FIELD_DATE: _date_ms(today),
                config.FIELD_PLATFORM: ["知乎"],
                config.FIELD_TARGET_URL: {"link": lead.url, "text": lead.url},
                config.FIELD_REVIEW: "否",
                config.FIELD_PUBLISHED: "否",
                config.FIELD_COMMENT: lead.comment,
            },
        )
        lead.extra["record_id"] = record_id
        lead.status = "待人工审核"
        log.info("已写入待审核线索：%s record=%s", lead.url, record_id)
    return leads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="采集知乎推广线索并写入飞书推广数据库")
    parser.add_argument("--max", type=int, default=1, help="本次最多写入几条新线索")
    parser.add_argument("--no-backfill", action="store_true", help="不回填已审核但缺少推荐文案的旧记录")
    args = parser.parse_args(argv)
    if args.max < 1:
        parser.error("--max 必须大于 0")
    try:
        leads = run(max_leads=args.max, backfill=not args.no_backfill)
    except (FeishuError, RuntimeError) as exc:
        print(f"错误：采集推广线索失败：{exc}", file=sys.stderr)
        return 2
    print(f"写入 {len(leads)} 条待审核线索；未审核记录不会进入知乎发布流程。")
    for lead in leads:
        print(f"- {lead.title}\n  {lead.url}\n  {lead.extra.get('record_id', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
