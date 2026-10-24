---
name: add-weread-book
description: 把一本微信读书的书加入知乎想法书籍池（索引章节 → 写 config.yaml 的 book_pool → 验证全文抓取完整度）。当用户给出 weread.qq.com/web/reader/... 链接说"加入书籍池""加一本新书""换本书读"，或书籍池读完需要续书时使用。
---

在 `/media/wangpan/hdd1/0-me/zhihu` 项目里给知乎想法的 `book_reflection` 链路添加新书。
必须按顺序做完四步，其中第 3 步（完整度验证）是硬闸：没过就不算加好，要报告原因而不是留个坏配置。

先读 `AGENT.md` 的「微信读书与书籍池」一节，命令统一用项目内的 `./venv/bin/python`。

## 输入

用户给的种子链接形如：

```text
https://weread.qq.com/web/reader/8eb322e0722245bc8eb9520ke4d32d5015e4da3b7fbb1fa
```

没给链接就先问，不要猜 bookId。链接里的 hash 不是 bookId，bookId 由第 1 步的脚本从 SSR 页面解析出来。

## 前置检查

- 登录态 `data/auth/weread_state.json` 必须存在且含 `wr_skey` / `wr_vid`；缺了或过期先让用户跑 `./venv/bin/python scripts/weread_login.py` 扫码，不要自己删登录态文件。
- 抓全文时 `fetch_chapter_fulltext` 会把阅读位置重置到章首并拦掉进度上报，不会改用户真实的阅读进度；索引脚本 `weread_index_book.py` 仍会正常翻章。

## 1. 索引章节

```bash
./venv/bin/python scripts/weread_index_book.py "<seed_url>"
```

产出 `data/books/<bookId>/index.json`。检查日志里的书名/作者/bookId/章节数，并确认：

```bash
./venv/bin/python -c "
import json,sys
from src.weread_fetcher import is_content_chapter
d=json.load(open('data/books/<bookId>/index.json'))
body=[c for c in d['chapters'] if c['url'] and is_content_chapter(c, min_word_count=800)]
print(d['book_title'], d['author'], '总章节', len(d['chapters']), '正文章节', len(body))
print('缺 URL', [c['chapterIdx'] for c in d['chapters'] if not c['url']])
for c in body[:3]: print(c['chapterIdx'], c['chapterUid'], c['wordCount'], c['title'])
"
```

- 正文章节数为 0 → 这本书不适合入池（多半全是短章节或非正文），停下来问用户。
- 有章节缺 URL → 脚本会用确定性编码兜底，一般没问题；仍然缺就记下来，后面验证时避开这些章节。

## 2. 写入 book_pool

编辑 `config.yaml` 的 `content.book.book_pool`，在**列表末尾**追加 bookId，注释写书名和作者，格式跟已有条目对齐：

```yaml
      - "35800508"     # 《积极情绪的力量》芭芭拉·弗雷德里克森
```

- 池子是「按顺序逐本读完」，追加到末尾意味着新书排在最后；用户要求先读这本才前置。
- 已在池中的 bookId 不要重复添加。
- 别动 `data/books/<bookId>/progress.json`（阅读进度，删了会重读）。
- 如果池子此前已读完，检查并删除过期标记 `data/books/.pool_done_notified`，否则下次读完不会再发提醒私信。

## 3. 验证全文抓取完整度（硬闸）

至少验证第一个正文章节，长章节（wordCount > 10000）再抽验一个：

```bash
./venv/bin/python -c "
import json
from src.weread_fetcher import fetch_chapter_fulltext, WereadFetchError, is_content_chapter
d=json.load(open('data/books/<bookId>/index.json'))
body=[c for c in d['chapters'] if c['url'] and is_content_chapter(c, min_word_count=800)]
picks=[body[0]] + [c for c in body if c['wordCount'] > 10000][:1]
for c in picks:
    try:
        r=fetch_chapter_fulltext(c['url'])
        print('OK ', c['chapterIdx'], c['title'][:20], c['wordCount'], '->', r['full_text_chars'], round(r['completeness_ratio'],3))
    except WereadFetchError as e:
        print('ERR', c['chapterIdx'], c['title'][:20], c['wordCount'], e)
"
```

要求完整度 ≥ 0.90（`MIN_FULLTEXT_RATIO`），且 ≤ 1.25（超了说明段落重复）。一章可能要跑 1–2 分钟，别把超时设太短。

不达标时按这几种已知原因排查，不要去改阈值、也不要让链路用残缺正文生成内容（设计上就是 fail closed）：

- **章节正文疑似不完整**：`src/weread_fetcher.py` 已处理四种已知形态——长章节被分页（底部按钮是「下一页」）、正文 canvas + 绝对定位 DOM 字符混排、正文跨多个 canvas（中间隔着插图/引文框留白）、阅读器恢复到章节中段导致前面的内容既不是 DOM 也没有 fillText。若这本书又是新形态，先用 Playwright 起个临时探针脚本定位文字的渲染路径（截图 + `document.querySelectorAll('canvas')` + `fillText` 钩子 + DOM 文本节点位置），查完删掉临时脚本。
- **登录态失效**：报「等待微信读书正文超时」或「没有绘制章节文字」，重新扫码。
- **付费/试读限制**：`index.json` 的 `max_free_chapter`、章节 `paid` 字段；确实没权限的章节写进 `content.book.skip_chapter_uids`，或者告诉用户这本书要先解锁。

## 4. 让新书生效并回报

- 池子里前面的书还没读完 → 新书要等前面读完才轮到，说明这一点就够了，不要改进度文件。
- 池子已读完（日志出现「书籍池已全部读完」并回退 themes）→ 下一个 slot 就会用新书。用户要求立刻出内容时，重新生成当天草稿：

  ```bash
  ./venv/bin/python -c "
  from src.scheduler import generate_one
  import datetime as dt
  print(generate_one('evening', date=dt.date.today()))
  "
  ```

  已存在的草稿要先移走/删掉才会重新生成（`generate_one` 见到同名文件会跳过）；已经发布归档到 `data/published/` 的那条撤不回来，如实说明。
- 真正发布仍走既有入口 `./venv/bin/python scripts/publish_slot.py {morning|evening}`；未经用户确认不要提前发（默认交给 cron 的 7:00 / 18:00）。

最后回报：bookId 与书名、正文章节数、验证章节的完整度、新书什么时候会被用到、以及是否还需要用户做的事（扫码 / 解锁 / 手动发布）。
