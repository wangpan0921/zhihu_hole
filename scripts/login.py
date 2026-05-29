#!/usr/bin/env python3
"""首次登录入口（终端二维码）。
    python scripts/login.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.zhihu_login import login_interactive  # noqa: E402

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()
    login_interactive(headful=args.headful)
