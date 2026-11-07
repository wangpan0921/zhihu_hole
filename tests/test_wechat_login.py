from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.wechat_login import _print_qr_in_terminal  # noqa: E402


def test_print_qr_in_terminal_renders_qr_and_payload():
    output = io.StringIO()
    with redirect_stdout(output):
        _print_qr_in_terminal("https://mp.weixin.qq.com/cgi-bin/login?ticket=test")

    rendered = output.getvalue()
    assert "二维码内容：https://mp.weixin.qq.com/cgi-bin/login?ticket=test" in rendered
    assert "██" in rendered or "▄▄" in rendered or "▀▀" in rendered
