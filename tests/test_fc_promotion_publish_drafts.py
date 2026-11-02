import datetime as dt

from fc_promotion.publish_today_drafts import _record_date, select_drafts


def test_record_date_accepts_feishu_timestamp_and_iso_date():
    assert _record_date(1793548800000) == dt.date(2026, 11, 2)
    assert _record_date("2026/11/02") == dt.date(2026, 11, 2)


def test_select_drafts_filters_date_platform_url_and_deduplicates():
    records = [
        {
            "record_id": "rec1",
            "fields": {
                "日期": 1793548800000,
                "平台": ["知乎"],
                "链接": {"link": "https://www.zhihu.com/question/123/answer/456"},
            },
        },
        {
            "record_id": "rec2",
            "fields": {
                "日期": "2026-11-02",
                "平台": "zhihu",
                "链接": "https://www.zhihu.com/question/123",
            },
        },
        {
            "record_id": "rec3",
            "fields": {
                "日期": "2026-11-02",
                "平台": ["小红书"],
                "链接": "https://www.zhihu.com/question/789",
            },
        },
    ]

    drafts = select_drafts(records, dt.date(2026, 11, 2))

    assert len(drafts) == 1
    assert drafts[0].url == "https://www.zhihu.com/question/123"
    assert drafts[0].extra["record_id"] == "rec1"
