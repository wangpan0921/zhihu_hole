#!/usr/bin/env python3
"""判断是否应生成下一课的草稿。

规则（与人工定稿流程配合）：
- 每个课程目录 kid_coding/lesson-NN-主题/ 里：
    article.md  配图.md         —— 自动化生成的「草稿」
    lesson_NN_主题.md            —— 使用者「定稿」后手动创建的最终文章
- 找到编号最大的课程目录（最新一课）：
    * 若其中存在定稿文件 lesson_*.md  → 说明该课已定稿，应生成「下一课」草稿。
    * 若不存在                         → 说明还没定稿，跳过，不生成。
- 若 kid_coding 下没有任何课程目录 → 应生成第 1 课。

输出首行是机器可读指令：
    ACTION=skip LATEST=NN
    ACTION=generate NEXT=MM [LATEST=NN]
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KID = ROOT / "kid_coding"


def lesson_dirs() -> list[tuple[int, str, Path]]:
    out: list[tuple[int, str, Path]] = []
    if not KID.exists():
        return out
    for p in KID.glob("lesson-*"):
        if not p.is_dir():
            continue
        m = re.match(r"lesson-(\d+)-(.+)", p.name)
        if m:
            out.append((int(m.group(1)), m.group(2), p))
    return sorted(out)


def has_final_article(path: Path) -> bool:
    # 定稿文件命名 lesson_NN_主题.md（下划线），区别于草稿 article.md
    return any(path.glob("lesson_*.md"))


def main() -> int:
    dirs = lesson_dirs()
    if not dirs:
        print("ACTION=generate NEXT=1")
        print("说明：kid_coding 下没有任何课程目录，应生成第 1 课草稿。")
        return 0
    num, slug, path = dirs[-1]
    if has_final_article(path):
        print(f"ACTION=generate NEXT={num + 1} LATEST={num}")
        print(f"说明：最新课程 lesson-{num:02d}-{slug} 已有定稿文件，应生成第 {num + 1} 课草稿。")
    else:
        print(f"ACTION=skip LATEST={num}")
        print(f"说明：最新课程 lesson-{num:02d}-{slug} 尚未定稿（无 lesson_*.md），跳过，不生成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
