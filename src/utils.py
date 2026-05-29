"""通用工具：配置加载、日志、目录路径。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PENDING_DIR = DATA_DIR / "pending"
PUBLISHED_DIR = DATA_DIR / "published"
IMAGES_DIR = DATA_DIR / "images"
AUTH_DIR = DATA_DIR / "auth"
LOGS_DIR = PROJECT_ROOT / "logs"
DEBUG_DIR = PROJECT_ROOT / "debug"

for _d in (PENDING_DIR, PUBLISHED_DIR, IMAGES_DIR, AUTH_DIR, LOGS_DIR, DEBUG_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    """加载 .env。.env 是配置的单一真相源，覆盖已有 os.environ
    （否则 shell 里残留的空字符串变量会让 .env 中的新值失效）。"""
    load_dotenv(PROJECT_ROOT / ".env", override=True)


def load_config() -> dict[str, Any]:
    """加载 config.yaml。"""
    with open(PROJECT_ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_logger(name: str) -> logging.Logger:
    """带文件 + 终端输出的 logger。"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def env(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key, default)
    if val is not None and val.strip() == "":
        return default
    return val
