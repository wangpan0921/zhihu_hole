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
    def __init__(self, text: str, content_type: str = "text/html") -> None:
        self.text = text
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


class _ImageResponse(_Response):
    def __init__(self, content: bytes, content_type: str = "image/png") -> None:
        super().__init__("")
        self.content = content
        self.headers = {"Content-Type": content_type}


def test_parses_album_in_page_order(monkeypatch):
    monkeypatch.setattr(pipeline.requests, "get", lambda *a, **k: _Response(ALBUM_HTML))
    items = pipeline.fetch_album_items("https://example.test/album")
    assert [item.key for item in items] == ["1:1", "2:1"]
    assert items[1].title == "第二篇&判断"
    assert items[0].url.startswith("https://")


def test_fetches_album_pages_and_restores_chronological_order(monkeypatch):
    first_page = ALBUM_HTML + """
    <script>
    window.cgiData = {
      article_count: '4' * 1,
      continue_flag: '1' * 1,
    };
    </script>
    """
    second_page = """
    <script>
    window.cgiData = {
      article_count: '' * 1,
      articleList: [
        {title: '第四篇', url: 'http://mp.weixin.qq.com/s?mid=4',
         msgid: '4', itemidx: '1'},
        {title: '第三篇', url: 'http://mp.weixin.qq.com/s?mid=3',
         msgid: '3', itemidx: '1'},
      ],
      continue_flag: '0' * 1,
    };
    </script>
    """
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(first_page if len(calls) == 1 else second_page)

    monkeypatch.setattr(pipeline.requests, "get", fake_get)
    items = pipeline.fetch_album_items(
        "https://mp.weixin.qq.com/mp/appmsgalbum?__biz=test-biz&album_id=test-album"
    )

    assert [item.key for item in items] == ["1:1", "2:1", "3:1", "4:1"]
    assert calls[1][1]["params"]["begin_msgid"] == "2"
    assert calls[1][1]["params"]["begin_itemidx"] == "1"
    assert calls[1][1]["headers"]["X-Requested-With"] == "XMLHttpRequest"


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


def test_materializes_remote_images_once(tmp_path, monkeypatch):
    image_url = "https://mmbiz.qpic.cn/test/640?wx_fmt=png&from=appmsg"
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _ImageResponse(b"png-data")

    monkeypatch.setattr(pipeline.requests, "get", fake_get)
    source = f"before\n\n![封面]({image_url})\n\n![重复]({image_url})\n\nafter"

    first = pipeline._materialize_remote_images(source, tmp_path / "images")
    second = pipeline._materialize_remote_images(source, tmp_path / "images")

    assert image_url not in first
    assert first == second
    assert len(calls) == 1
    cached = next((tmp_path / "images").glob("*.png"))
    assert cached.read_bytes() == b"png-data"
    assert cached.resolve().as_posix() in first


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
    image_dir = tmp_path / "data" / "wechat_album" / "images" / "2_1"
    assert calls[0][1]["source_dir"] == image_dir
    assert calls[0][1]["image_cache_path"] == image_dir / "zhihu_urls.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["items"]["1:1"]["status"] == "skipped_existing"
    assert state["items"]["2:1"]["status"] == "published"
