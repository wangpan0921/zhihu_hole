"""各平台登录器。抽象基类见 base.py，注册表见 registry.py。"""
from .registry import LOGIN_REGISTRY, get_login, available_platforms

__all__ = ["LOGIN_REGISTRY", "get_login", "available_platforms"]
