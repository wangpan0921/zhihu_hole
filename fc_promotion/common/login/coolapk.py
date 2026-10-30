"""酷安登录器（持久化 profile）。

酷安是安卓工具垂直社区，对第三方下载链接容忍度高、风控相对宽松。
登录判定 cookie 见 config.PLATFORM_LOGIN_COOKIES['coolapk']；首次本机 headful 登录。
"""
from __future__ import annotations

from .persistent_base import PersistentProfileLogin


class CoolapkLogin(PersistentProfileLogin):
    name = "coolapk"

    @property
    def login_url(self) -> str:
        """酷安首页没有网页版登录入口，直接打开账号登录页。"""
        return "https://account.coolapk.com/auth/login"
