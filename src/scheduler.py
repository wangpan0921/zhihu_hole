"""调度逻辑：

- 每天 00:30 预生成 morning 和 evening 两条草稿到 pending/{date}_{slot}.json
- 每天 7:00 / 18:00 触发发布：
    * 若 pending/{date}_{slot}.json 存在 → 用它
    * 否则现生现发（fallback_realtime=True）
- 发布成功后把草稿移到 published/{date}_{slot}.json
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Optional

from .content_generator import generate_post
from .image_generator import get_image
from .utils import (
    PENDING_DIR,
    PUBLISHED_DIR,
    get_logger,
    load_config,
    load_env,
)
from .zhihu_publisher import publish

log = get_logger("scheduler")


def _draft_path(date: dt.date, slot: str, *, base: Path = PENDING_DIR) -> Path:
    return base / f"{date.isoformat()}_{slot}.json"


def _save_draft(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("草稿已保存：%s", path)


def _load_draft(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_one(slot: str, date: Optional[dt.date] = None) -> Path:
    """生成一条草稿（含配图）写入 pending/。返回草稿路径。"""
    load_env()
    date = date or dt.date.today()
    out = _draft_path(date, slot)
    if out.exists():
        log.info("草稿已存在，跳过生成：%s", out)
        return out

    post = generate_post(slot=slot, date=date)
    try:
        img = get_image(post["image_prompt"])
        post["image_path"] = str(img)
    except Exception as e:  # noqa: BLE001
        log.warning("配图失败，将以纯文字发布：%s", e)
        post["image_path"] = None

    post["slot"] = slot
    post["date"] = date.isoformat()
    _save_draft(out, post)
    return out


def generate_all_today(date: Optional[dt.date] = None) -> list[Path]:
    """为指定日期所有 slot 预生成草稿（默认今天）。"""
    cfg = load_config()
    slots = cfg["schedule"]["slots"]
    target = date or dt.date.today()
    paths = []
    for s in slots:
        try:
            paths.append(generate_one(s["name"], date=target))
        except Exception as e:  # noqa: BLE001
            log.exception("生成 slot=%s (%s) 失败：%s", s["name"], target, e)
    return paths


def publish_slot(slot: str, date: Optional[dt.date] = None, *, dry_run: bool = False) -> bool:
    """发布指定 slot。pending 不存在且 fallback_realtime=True 时现生现发。"""
    load_env()
    cfg = load_config()
    date = date or dt.date.today()

    pending = _draft_path(date, slot, base=PENDING_DIR)
    if not pending.exists():
        if not cfg["schedule"].get("fallback_realtime", True):
            log.warning("没有草稿且未开启实时回退，跳过：%s", pending)
            return False
        log.info("无草稿，现生现发：slot=%s", slot)
        pending = generate_one(slot, date=date)

    data = _load_draft(pending)
    img_path = Path(data["image_path"]) if data.get("image_path") else None
    log.info("准备发布：%s | %s", data["title"], pending.name)

    ok = publish(data["title"], data["body"], img_path, dry_run=dry_run)

    if ok and not dry_run:
        archived = _draft_path(date, slot, base=PUBLISHED_DIR)
        archived.parent.mkdir(parents=True, exist_ok=True)
        pending.rename(archived)
        log.info("已归档：%s", archived)
    return ok
