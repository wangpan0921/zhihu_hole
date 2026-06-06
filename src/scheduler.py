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

from .content_generator import BookPoolFinished, generate_post, generate_from_theme
from .image_generator import get_image
from .utils import (
    DATA_DIR,
    PENDING_DIR,
    PUBLISHED_DIR,
    get_logger,
    load_config,
    load_env,
)
from .zhihu_messenger import send_private_message
from .zhihu_publisher import publish

log = get_logger("scheduler")

# 书籍池读完后，发私信通知的"已通知"标记，避免每个 slot 重复发
_POOL_DONE_FLAG = DATA_DIR / "books" / ".pool_done_notified"


def _notify_pool_finished() -> None:
    """书籍池全部读完：给运营者发一条知乎私信（仅一次）。

    用一个标记文件保证幂等。私信失败不影响后续内容发布，只记日志。
    """
    if _POOL_DONE_FLAG.exists():
        log.info("书籍池已读完且此前已发过私信通知，跳过")
        return

    cfg = load_config()
    book_cfg = (cfg.get("content", {}).get("book") or {})
    msg = (
        book_cfg.get("finish_message")
        or "📚 书籍池里的书都读完啦，自动发布已回退到主题池模式。"
        "想继续读新书的话，记得索引新书并更新 config.yaml 的 book_pool。"
    )
    try:
        ok = send_private_message(msg)
        if ok:
            _POOL_DONE_FLAG.parent.mkdir(parents=True, exist_ok=True)
            _POOL_DONE_FLAG.write_text(
                dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8"
            )
            log.info("书籍池读完私信已发送，已写标记 %s", _POOL_DONE_FLAG)
        else:
            log.warning("书籍池读完，但未发送私信（可能未配置 notify_people_url）")
    except Exception as e:  # noqa: BLE001
        log.exception("发送'书籍池读完'私信失败（不影响发布）：%s", e)


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

    try:
        post = generate_post(slot=slot, date=date)
    except BookPoolFinished:
        # 书籍池全部读完：发一次私信通知，然后回退到主题池继续产出内容。
        log.info("书籍池已全部读完，触发私信通知并回退 themes 模式")
        _notify_pool_finished()
        post = generate_from_theme()
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
