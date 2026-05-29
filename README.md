# 知乎树洞圈子自动发布系统

每天定时为知乎圈子自动生成「自我觉醒 / 个人成长」类想法并发布。

- 文案：Claude / OpenAI 任选其一生成
- 配图：DALL·E 3 生意境图，失败回退 Unsplash
- 发布：Playwright 控制 Chromium 模拟人工流程（点"发想法" → 粘贴 → 上传图 → 发布）
- 调度：cron 在 7:00 / 18:00 触发；00:30 预生成草稿到 `data/pending/` 供人工把关
- 登录：服务器场景用**终端二维码**，手机扫一次后 cookie 长期复用

## 目录结构

```
.
├── config.yaml                # 主题池、模型、时间表等可改的配置
├── .env                       # API Key（拷自 .env.example）
├── requirements.txt
├── src/
│   ├── content_generator.py   # 调 LLM 生标题+正文+图prompt
│   ├── image_generator.py     # 生图（DALL·E 优先，Unsplash 兜底）
│   ├── zhihu_login.py         # 终端二维码登录
│   ├── zhihu_publisher.py     # Playwright 自动发布
│   ├── scheduler.py           # 生成 / 发布 / 归档逻辑
│   └── utils.py
├── scripts/
│   ├── login.py               # 入口：首次登录
│   ├── generate_drafts.py     # 入口：预生成草稿（cron 调用）
│   ├── publish_slot.py        # 入口：发布（cron 调用）
│   └── install_cron.sh        # 安装 / 卸载 cron 任务
├── data/
│   ├── auth/storage_state.json  # 知乎登录态（自动生成）
│   ├── pending/                 # 待审核草稿
│   ├── published/               # 已发布归档
│   └── images/                  # 生成 / 下载的图
├── logs/                        # 应用日志 + cron 日志
└── debug/                       # 每步流程截图（出错时排查用）
```

---

## 首次部署（一次性步骤）

### 1. 系统依赖（已装可跳过）

```bash
sudo apt-get install -y python3.12-venv libzbar0
```

如果服务器上 `playwright install chromium` 跑完后启动浏览器报缺库，再补：

```bash
./venv/bin/playwright install-deps chromium   # 需要 sudo
```

### 2. Python 环境

```bash
cd /media/wangpan/hdd1/0-me/zhihu
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
./venv/bin/playwright install chromium
```

### 3. 配置 API Key

```bash
cp .env.example .env
vim .env
```

至少填一个 LLM Key：

```ini
ANTHROPIC_API_KEY=sk-ant-...    # 推荐，文笔更细腻
OPENAI_API_KEY=sk-...            # 也可用，且 OpenAI Key 还能复用做 DALL·E 生图
UNSPLASH_ACCESS_KEY=...          # 可选，作为图源兜底
HTTPS_PROXY=http://127.0.0.1:7890   # 如果服务器需要梯子访问 OpenAI / Anthropic
```

> 提示：如果只填了 `ANTHROPIC_API_KEY` 没有 `OPENAI_API_KEY`，配图会自动回退到 Unsplash，请务必填 `UNSPLASH_ACCESS_KEY`，否则发的就是纯文字。

### 4. 首次扫码登录知乎

```bash
./venv/bin/python scripts/login.py
```

终端会打印一个 Unicode 字符块组成的二维码 → **用手机知乎 App 扫描** → 看到"已登录"提示后脚本会自动保存 `data/auth/storage_state.json`。

> 如果终端二维码看不清（字体/颜色问题），调整终端为黑底白字，或打开生成的 `debug/qr_raw.png` 直接用图片查看器扫。

### 4b. （可选）扫码登录微信读书

如果你打算用「读某本书的某一章 → 写读书感悟」这种内容生成方式，需要先登录微信读书，把登录态存下来供后续抓章节用：

```bash
./venv/bin/python scripts/weread_login.py
```

终端会打印二维码，**用「微信」扫码**（不是微信读书 App）后在手机上点确认即可。登录态会写到 `data/auth/weread_state.json`。

验证登录是否拿到正文，可以跑探测脚本：

```bash
./venv/bin/python scripts/weread_probe.py "<章节URL>" \
  --storage data/auth/weread_state.json
```

产物在 `debug/weread_probe/`，看 `summary.txt` 里 PUA 比例和章节文本字符数。

### 5. 试发一条（dry-run，不真正点发布）

```bash
./venv/bin/python scripts/publish_slot.py morning --dry-run
```

打开 `debug/publish_*_*.png` 检查每一步截图：
- `01_ring_loaded` 圈子页是否正常
- `03_composer_opened` 编辑器是否被唤起
- `05_text_typed` 文字是否填进去了
- `06_image_uploaded` 图是否上传成功
- `07_dry_run_final` 提交前的最终样子

如果哪一步不对，看一眼截图，可能需要在 `src/zhihu_publisher.py` 的 `SELECTORS` 里加一条新的 selector。

### 6. 真发一条

```bash
./venv/bin/python scripts/publish_slot.py morning
```

去知乎 App 看圈子是否出现了这条想法。

### 7. 安装定时任务

```bash
bash scripts/install_cron.sh install
bash scripts/install_cron.sh status   # 查看
```

默认时间表：

| 时间 | 动作 |
| ---- | ---- |
| 19:00 | 为「明天」的 morning + evening 各生成一条草稿到 `data/pending/` |
| 07:00 | 发布当天的 morning 草稿（若没有则现生现发） |
| 18:00 | 发布当天的 evening 草稿（若没有则现生现发） |

要修改时间，编辑 `scripts/install_cron.sh` 重装，或直接 `crontab -e` 改。

---

## 日常使用

### 看今天有什么草稿

```bash
ls data/pending/
cat data/pending/2026-05-17_morning.json | python -m json.tool
```

### 改一条草稿

直接编辑 JSON 里的 `title` / `body` 即可，发布时会用最新内容。

### 删掉一条草稿（不发那一条）

```bash
rm data/pending/2026-05-17_morning.json
```

注意：`config.yaml` 里 `fallback_realtime: true` 表示**没草稿也会现场生成新的发出去**。如果你今天就是不想发某一条，把这项改成 `false`，或者干脆删那个 slot 的 cron 行。

### 看日志

```bash
tail -f logs/app.log     # 应用日志
tail -f logs/cron.log    # cron 输出
```

### 卸载 cron

```bash
bash scripts/install_cron.sh uninstall
```

---

## 调整内容风格

编辑 `config.yaml`：

```yaml
content:
  themes:           # 主题池，每次随机抽一个
    - "..."
  min_chars: 180
  max_chars: 380
```

或编辑 `src/content_generator.py` 里的 `SYSTEM_PROMPT` 改写作风格。

---

## 「读书感悟」模式（book_reflection）

把每天发布的内容从「主题池随机文」切换到「按章节顺序读一本书写感悟」。

### 一次性准备：索引一本书的所有章节

1. 在微信读书 App / 网页打开你想读的书，复制**任意一章的 URL**（最好是靠前的章节，索引脚本是从这里向**末章**方向遍历）。
2. 索引一遍，把所有章节 URL 缓存到 `data/books/<bookId>/index.json`：

   ```bash
   ./venv/bin/python scripts/weread_index_book.py "<章节 URL>"
   ```

   脚本会用你已保存的微信读书登录态，在阅读器里循环点"下一章"，把每章的 URL 抓出来。一本书 40 章左右大约 2-3 分钟。

### 切换到 book_reflection 模式

`config.yaml` 里：

```yaml
content:
  mode: "book_reflection"
  min_chars: 200
  max_chars: 500
  book:
    book_id: "3300144506"      # 索引出的 bookId（看 index.json 文件名）
    skip_chapter_uids: []       # 额外想跳过的 chapterUid
    min_word_count: 800         # 字数小于此的章节视为非正文跳过
```

### 工作流

- 每次发布（早 7:00 / 晚 18:00 各一条）从 index.json 里挑下一个**正文章节**（自动跳过封面/版权/推荐序/部分扉页等）
- 用纯 HTTP GET 抓该章的 AI 摘要（在页面 `<meta name="description">` 里，约 600-1000 字）
- 喂给 LLM，让它写一段 200-500 字的读书感悟（含原文摘抄）
- 当章节 claim 状态记录到 `data/books/<bookId>/progress.json`，发完一章自动推进
- 当书发完时**自动回退到 themes 模式**（主题池随机），不会卡住

### 看进度 / 重置进度

```bash
cat data/books/3300144506/progress.json
# 或重新从头开始：
rm data/books/3300144506/progress.json
```

### 已知限制

索引脚本只能从种子章节向**末章**方向遍历（阅读器顶部的"上一章"按钮、键盘左方向键、history.back 都不能切到上一章）。如果你的种子 URL 不是第一章，前面那部分章节的 URL 就拿不到。索引完成后看终端打印的"未拿到 URL 的 N 章"列表，那些章节会被自动跳过。

---

## 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| `登录态失效` | cookie 过期，重跑 `python scripts/login.py` |
| 找不到"发想法"入口 | 知乎 DOM 改了，看 `debug/publish_*_02_no_opener.png` 截图，往 `SELECTORS["open_composer"]` 里加新 selector |
| 上传图失败 | 同上，看 `debug/publish_*_06_image_*.png`；或先把 `image_path` 设为空，发纯文字验证主流程 |
| `OPENAI_API_KEY` 报 401 / 网络错误 | 服务器需要走代理，在 `.env` 里加 `HTTPS_PROXY=...` |
| `pyzbar.zbar_library not found` | 没装系统库：`sudo apt-get install -y libzbar0` |
| Playwright 启动报缺 .so | 跑 `sudo ./venv/bin/playwright install-deps chromium` |

---

## 后续可加的功能（暂未实现，按需扩展）

- 发布失败时邮件 / Server 酱通知
- 接入更多 LLM（DeepSeek / 通义）
- 内容去重（避免连续几天主题相近）
- 互动监控（自动给评论点赞 / 简单回复）
