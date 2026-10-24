"""统一登录入口。

    python -m fc_promotion.login_cli zhihu --headful
    python -m fc_promotion.login_cli wechat
    python -m fc_promotion.login_cli --check zhihu

本机建议 --headful 直接弹窗扫码；无图形界面时去掉 --headful 走终端二维码。
"""
from __future__ import annotations

import argparse
import sys

from .common.login import available_platforms, get_login


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="悬浮时钟推广 - 平台登录")
    parser.add_argument("platform", choices=available_platforms(), help="平台标识")
    parser.add_argument("--headful", action="store_true", help="弹出有头浏览器（本机扫码推荐）")
    parser.add_argument("--check", action="store_true", help="只校验现有登录态是否有效，不重新登录")
    args = parser.parse_args(argv)

    login = get_login(args.platform)
    if args.check:
        ok = login.logged_in()
        print(f"[{args.platform}] 登录态{'有效' if ok else '无效/缺失'}：{login.storage_path}")
        return 0 if ok else 1

    path = login.login_interactive(headful=args.headful)
    print(f"[{args.platform}] 登录完成，登录态：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
