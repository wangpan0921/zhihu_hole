"""头条号登录器（持久化 profile）。

登录判定 cookie 见 config.PLATFORM_LOGIN_COOKIES['toutiao']。
首次登录在本机 headful 扫码；若判定不准，按实测收紧 cookie 列表。
"""
from __future__ import annotations

from .persistent_base import PersistentProfileLogin


class ToutiaoLogin(PersistentProfileLogin):
    name = "toutiao"
