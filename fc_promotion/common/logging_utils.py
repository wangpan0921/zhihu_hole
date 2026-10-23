"""统一 logger：终端 + logs/fc_promotion.log。"""
from __future__ import annotations

import logging
import sys

from .paths import LOGS_DIR


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"fc_promotion.{name}")
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
    fh = logging.FileHandler(LOGS_DIR / "fc_promotion.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger
