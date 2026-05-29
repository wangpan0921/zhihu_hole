#!/usr/bin/env python3
"""微信读书登录入口：终端二维码扫码 → 保存 storage_state。

用法：
    ./venv/bin/python scripts/weread_login.py
    ./venv/bin/python scripts/weread_login.py --headful   # 本地有显示时调试
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.weread_login import login_interactive


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--headful", action="store_true", help="弹有头浏览器（本地调试）")
    args = parser.parse_args()
    path = login_interactive(headful=args.headful)
    print(f"\n登录态已保存：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
