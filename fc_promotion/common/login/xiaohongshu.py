"""小红书登录器（持久化 profile）。

风控最严，自动化务必低频。登录判定 cookie 见
config.PLATFORM_LOGIN_COOKIES['xiaohongshu']；首次本机 headful 扫码。
"""
from __future__ import annotations

from .persistent_base import PersistentProfileLogin


class XiaohongshuLogin(PersistentProfileLogin):
    name = "xiaohongshu"
