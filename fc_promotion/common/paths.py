"""项目路径。复用 zhihu 项目已有的 data/auth、logs、debug 目录，
这样登录态与现有脚本共享，不另起炉灶。

fc_promotion 位于 zhihu 项目根目录下，故项目根 = 本文件的上上级目录。
"""
from __future__ import annotations

from pathlib import Path

# .../zhihu/fc_promotion/common/paths.py -> parents[2] == .../zhihu
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
AUTH_DIR = DATA_DIR / "auth"
LOGS_DIR = PROJECT_ROOT / "logs"
DEBUG_DIR = PROJECT_ROOT / "debug"
ENV_FILE = PROJECT_ROOT / ".env"

for _d in (AUTH_DIR, LOGS_DIR, DEBUG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
