"""悬浮时钟推广的集中配置：产品卖点、下载渠道、飞书目标表、各平台搜索入口。"""
from __future__ import annotations

from pathlib import Path

# ---- 产品 ----
APP_NAME = "悬浮时钟"

# 图文推广素材。相对引用用于 Markdown 正文，绝对目录用于公众号上传。
PROMO_ASSET_DIR = Path(__file__).resolve().parent / "assets"
PROMO_IMAGE_REFS = (
    ("桌面悬浮时钟", "fc_promotion/assets/shot_home.jpg"),
    ("微信读书内悬浮时钟", "fc_promotion/assets/shot_weread.jpg"),
    ("悬浮时钟设置页", "fc_promotion/assets/shot_app.jpg"),
)

# 用户点名要突出的卖点（APK 体积小 / 不占空间 / 耗电低）
SELLING_POINTS = [
    "APK 体积小，安装包不到几 MB，不占手机空间",
    "后台几乎不耗电，走秒由系统驱动，常驻也不卡",
    "带秒显示、浮在所有应用之上，全屏看视频/打游戏也能瞄一眼时间",
    "可拖动、可锁定（锁定后触摸穿透不挡操作），还能调字号/颜色/透明度",
    "用邀请码可享 14 天试用，1 元一次性永久解锁，桌面小部件永久免费",
]

# ---- 下载 / 邀请 ----
# 仅安卓；鸿蒙(HarmonyOS)不支持。
DOWNLOAD_WEB = "https://money-3jg.pages.dev/apps/floating-clock/"  # 安卓下载页
INVITE_CODE = "MHT-35FITT4IE4"  # 复制邀请文案后打开 App 会自动填，享 14 天试用
# 用户提供的标准邀请文案（复制即用，App 会自动识别邀请码）
INVITE_TEXT = (
    "【icey悬浮时钟邀请】邀请码 MHT-35FITT4IE4，复制这段话后打开 App 会自动填写，"
    "可享 14 天试用。下载：https://money-3jg.pages.dev/apps/floating-clock/"
)
# 邀请文本之后的固定提醒，不能插入邀请文本内部或图片之后。
KEEP_ALIVE_REMINDER = "强烈建议开启保活设置，防止被系统杀掉。"
# 百度网盘作为备用下载渠道（可选，站外平台慎用网盘链接）
DOWNLOAD_BAIDU = "https://pan.baidu.com/s/1fo7CZ43Wfk99axTpFLXB1A?pwd=83jc"  # 提取码 83jc
DOWNLOAD_BAIDU_CODE = "83jc"

# ---- 飞书多维表格 ----
# 推广数据库（写入目标）
FEISHU_PROMO_URL = (
    "https://my.feishu.cn/wiki/P5RFwejEKicQwWkUn3ocfZyjnCh"
    "?table=tblV3dRjBSjMxqH0&view=vewQ212bQq"
)
FEISHU_PROMO_WIKI_TOKEN = "P5RFwejEKicQwWkUn3ocfZyjnCh"
FEISHU_PROMO_TABLE_ID = "tblV3dRjBSjMxqH0"

# 悬浮时钟数据库（字段写法参考）
FEISHU_REF_URL = (
    "https://my.feishu.cn/wiki/HSRQwrzoYiob9pkVHhHcjG4In1b"
    "?table=tblleOk0BDmVS0YN&view=vewwWrnr6k"
)
FEISHU_REF_WIKI_TOKEN = "HSRQwrzoYiob9pkVHhHcjG4In1b"
FEISHU_REF_TABLE_ID = "tblleOk0BDmVS0YN"

# 推广记录字段名（需与飞书表实际字段一致；首次运行用 list_field_names 核对后调整）
FIELD_DATE = "日期"
FIELD_PLATFORM = "平台"
FIELD_TARGET_URL = "目标链接"
FIELD_TARGET_TITLE = "问题/帖子标题"
FIELD_COMMENT = "推广文案"
FIELD_STATUS = "状态"

# ---- 搜索目标：按平台配搜索入口与关键词 ----
# 悬浮时钟是**安卓 App**，关键词要带安卓/手机限定，避免召回苹果版、桌面版。
SEARCH_KEYWORDS = [
    "安卓 悬浮时钟",
    "手机 悬浮时钟",
    "悬浮时钟 带秒",
    "手机 悬浮窗 时间",
    "全屏 显示时间 悬浮",
    "手机 带秒 时钟 app",
]

# ---- 线索相关性过滤 ----
# 要推广的是安卓 App。命中以下任一排除词的标题直接丢弃（苹果/iOS/桌面/电脑端等）。
EXCLUDE_KEYWORDS = [
    "苹果", "iphone", "ipad", "ios", "mac", "macos", "ipados",
    "电脑", "桌面版", "windows", "win10", "win11", "pc端", "台式", "笔记本",
    "鸿蒙",  # HarmonyOS 装不了本 apk，先排除；如需覆盖可后续单独做
]
# 可选正向信号：开启 REQUIRE_ANDROID_HINT 后，标题须含以下任一词才保留。
ANDROID_HINT_KEYWORDS = ["安卓", "android", "手机", "apk", "小米", "华为", "oppo", "vivo", "红米", "realme", "魅族", "一加"]
# 是否要求标题必须出现安卓/手机正向信号（更严，召回更少但更准）。
REQUIRE_ANDROID_HINT = False

# 主题相关性：标题必须命中以下任一"真实需求词"，才算对口线索。
# 解决"召回泛泛问题(如旧手机处理/手机必备神器)答非所问"的问题——这些不含悬浮/带秒等需求词。
TOPIC_KEYWORDS = [
    "悬浮", "浮窗", "浮动", "悬浮窗", "悬浮时钟",
    "带秒", "秒表", "秒钟", "精确到秒", "显示秒",
    "全屏显示时间", "屏幕显示时间", "看时间", "时间显示", "时钟app", "计时",
]
# 是否要求标题含主题词（默认开启，避免答非所问；关掉会召回更多但更泛）。
REQUIRE_TOPIC = True

SEARCH_TARGETS = {
    "zhihu": {
        "search_url": "https://www.zhihu.com/search?type=content&q={kw}",
    },
    # 酷安：安卓工具垂直社区，图文广场搜索；对第三方下载链接容忍度高
    "coolapk": {
        "search_url": "https://www.coolapk.com/s?q={kw}&type=feed",
    },
    # 头条号：今日头条站内搜索（文章/问答），导流能力强
    "toutiao": {
        "search_url": "https://so.toutiao.com/search?dvpf=pc&keyword={kw}&pd=question",
    },
    # 小红书：explore 搜索；风控最凶，评论带链接易限流，务必低频
    "xiaohongshu": {
        "search_url": "https://www.xiaohongshu.com/search_result?keyword={kw}",
    },
}

# ---- 各平台登录态/浏览器 profile 与登录判定 cookie ----
# 所有平台都走持久化 profile（反风控通用）。profile 名即 data/auth/<name>_chrome_profile。
PLATFORM_PROFILE = {
    "zhihu": "zhihu",
    "coolapk": "coolapk",
    "toutiao": "toutiao",
    "xiaohongshu": "xiaohongshu",
}
# 判定"已登录"的 cookie 名（任一存在即视为登录）
PLATFORM_LOGIN_COOKIES = {
    "zhihu": ["z_c0"],
    "coolapk": ["uid", "username", "token"],
    "toutiao": ["sessionid", "sso_uid_tt", "sid_tt"],
    "xiaohongshu": ["web_session", "customerClientId"],
}
# 各平台首页（先过首页拿正常会话再搜，降低风控）
PLATFORM_HOME = {
    "zhihu": "https://www.zhihu.com/",
    "coolapk": "https://www.coolapk.com/",
    "toutiao": "https://www.toutiao.com/",
    "xiaohongshu": "https://www.xiaohongshu.com/",
}

# 搜索结果里"线索链接"的 a 标签选择器（抓 href + 文本作标题）。
# 选择器随站点改版会变，失效时本机 headful 跑一次、看 debug 截图调整。
PLATFORM_LINK_SELECTOR = {
    "zhihu": "a[href*='/question/']",
    "coolapk": "a[href*='/feed/'], a[href*='/picture/']",
    "toutiao": "a[href*='/article/'], a[href*='/question/'], a[href*='/a']",
    "xiaohongshu": "a[href*='/explore/'], a[href*='/discovery/item/']",
}

# 发布动作的候选选择器（多候选兜底）。评论/回答入口因平台而异：
# 知乎=写回答；酷安/头条/小红书=帖子下的评论框。任一步找不到就跳过不误发。
PLATFORM_POST_SELECTORS = {
    "zhihu": {
        "open": ["button:has-text('写回答')", "a:has-text('写回答')",
                 ".QuestionHeaderActions button:has-text('回答')"],
        "editor": [".public-DraftEditor-content", "div[contenteditable='true']", ".Editable-content"],
        "submit": ["button:has-text('发布回答')", "button:has-text('发布')",
                   ".AnswerAdd button:has-text('发布')"],
    },
    "coolapk": {
        "open": ["textarea", "div[contenteditable='true']", "input[placeholder*='评论']",
                 "button:has-text('说点什么')"],
        "editor": ["textarea", "div[contenteditable='true']"],
        "submit": ["button:has-text('发送')", "button:has-text('评论')", "button:has-text('发布')"],
    },
    "toutiao": {
        "open": ["textarea[placeholder*='评论']", "input[placeholder*='评论']",
                 "div[contenteditable='true']", "button:has-text('写评论')"],
        "editor": ["textarea", "div[contenteditable='true']"],
        "submit": ["button:has-text('发布')", "button:has-text('发表')", "button:has-text('评论')"],
    },
    "xiaohongshu": {
        "open": ["div:has-text('说点什么')", "div[contenteditable='true']",
                 "input[placeholder*='评论']", "textarea[placeholder*='评论']"],
        "editor": ["div[contenteditable='true']", "textarea", "p[contenteditable='true']"],
        "submit": ["button:has-text('发送')", "button:has-text('发布')", "button:has-text('评论')"],
    },
}

# ---- 频控（B1 拟人化低频：每天随机 1~3 条，发一条停 60 秒再发下一条）----
DAILY_MIN_COMMENTS = 1          # 每天最少发布条数
DAILY_MAX_COMMENTS = 3          # 每天最多发布条数（每次运行在 [min,max] 间随机取）
MIN_SECONDS_BETWEEN = 60        # 两次发布最小间隔（秒）——发一条停 1 分钟
# 兼容旧引用：单次运行上限按每日上限算
MAX_COMMENTS_PER_RUN = DAILY_MAX_COMMENTS
# 发布模式下抓取的候选线索池大小（需多于每日配额，以便跳过已回答的问题后仍有备选）
CANDIDATE_POOL = 20

# ---- 知乎持久化浏览器 profile 名（绕过 40362 风控的关键）----
ZHIHU_PROFILE = "zhihu"
