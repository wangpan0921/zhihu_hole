from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import wechat_album_to_zhihu as pipeline  # noqa: E402


ALBUM_HTML = """
<ul>
  <li class="js_album_item" data-msgid="1" data-itemidx="1"
      data-title="第一篇" data-link="http://mp.weixin.qq.com/s?mid=1"></li>
  <li class="other" data-msgid="ignored"></li>
  <li class="album__list-item js_album_item" data-msgid="2" data-itemidx="1"
      data-title="第二篇&amp;判断" data-link="https://mp.weixin.qq.com/s?mid=2"></li>
</ul>
"""

ARTICLE_HTML = """
<h1 id="activity-name">第二篇&amp;判断</h1>
<div id="js_content">
  <h2 style="color:red">标题</h2>
  <p>正文<strong>重点</strong>，这里补充足够长的测试文字，验证解析后正文不会过短。</p>
  <pre><code>hp = 5<br>if hp &lt; 6:<br>    print("危险")</code></pre>
  <ul><li><code>&gt;</code><section>大于</section></li></ul>
  <img data-src="https://mmbiz.qpic.cn/test.png" style="width:300px">
  <iframe><script>bad()</script></iframe>
</div>
"""


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_parses_album_in_page_order(monkeypatch):
    monkeypatch.setattr(pipeline.requests, "get", lambda *a, **k: _Response(ALBUM_HTML))
    items = pipeline.fetch_album_items("https://example.test/album")
    assert [item.key for item in items] == ["1:1", "2:1"]
    assert items[1].title == "第二篇&判断"
    assert items[0].url.startswith("https://")


def test_extracts_clean_article_html(monkeypatch):
    monkeypatch.setattr(pipeline.requests, "get", lambda *a, **k: _Response(ARTICLE_HTML))
    item = pipeline.AlbumItem("2", "1", "fallback", "https://example.test/2")
    title, body = pipeline.fetch_article(item)
    assert title == "第二篇&判断"
    assert "## 标题" in body
    assert "![](https://mmbiz.qpic.cn/test.png)" in body
    assert body.count(chr(96)) >= 6
    assert "- `>`大于" in body
    assert "style=" not in body
    assert "bad()" not in body


def test_skips_first_and_publishes_second(tmp_path, monkeypatch):
    items = [
        pipeline.AlbumItem("1", "1", "第一篇", "https://example.test/1"),
        pipeline.AlbumItem("2", "1", "第二篇", "https://example.test/2"),
    ]
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        pipeline,
        "load_config",
        lambda: {
            "wechat_album_to_zhihu": {
                "album_url": "https://example.test/album",
                "column_name": "跟着史蒂夫学编程",
                "skip_first": 1,
                "state_path": "state.json",
            }
        },
    )
    monkeypatch.setattr(pipeline, "fetch_album_items", lambda url: items)
    monkeypatch.setattr(
        pipeline,
        "fetch_article",
        lambda item: (item.title, "<p>正文内容足够长</p>"),
    )
    calls = []

    def fake_publish(title, body, **kwargs):
        calls.append((title, kwargs))
        return "https://zhuanlan.zhihu.com/p/2"

    monkeypatch.setattr(pipeline, "publish_article", fake_publish)
    url = pipeline.publish_next()
    assert url == "https://zhuanlan.zhihu.com/p/2"
    assert calls[0][0] == "第二篇"
    assert calls[0][1]["column_name"] == "跟着史蒂夫学编程"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["items"]["1:1"]["status"] == "skipped_existing"
    assert state["items"]["2:1"]["status"] == "published"
