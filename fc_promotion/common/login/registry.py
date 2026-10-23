"""平台登录器注册表。扩展新平台只需在 LOGIN_REGISTRY 登记一行。"""
from __future__ import annotations

from .base import PlatformLogin
from .toutiao import ToutiaoLogin
from .wechat import WechatLogin
from .xiaohongshu import XiaohongshuLogin
from .zhihu import ZhihuLogin

LOGIN_REGISTRY: dict[str, type[PlatformLogin]] = {
    ZhihuLogin.name: ZhihuLogin,
    WechatLogin.name: WechatLogin,
    ToutiaoLogin.name: ToutiaoLogin,
    XiaohongshuLogin.name: XiaohongshuLogin,
}


def available_platforms() -> list[str]:
    return list(LOGIN_REGISTRY)


def get_login(platform: str) -> PlatformLogin:
    try:
        return LOGIN_REGISTRY[platform]()
    except KeyError as exc:
        raise KeyError(
            f"未知平台 {platform!r}；可选：{', '.join(available_platforms())}"
        ) from exc
