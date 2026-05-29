#!/usr/bin/env python3
"""发布指定 slot：
    python scripts/publish_slot.py morning
    python scripts/publish_slot.py evening [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scheduler import publish_slot  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slot", choices=["morning", "evening"])
    parser.add_argument("--dry-run", action="store_true", help="走流程但不真正点发布")
    args = parser.parse_args()

    ok = publish_slot(args.slot, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)
