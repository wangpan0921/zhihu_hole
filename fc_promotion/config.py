"""悬浮时钟推广的集中配置：产品卖点、下载渠道、飞书目标表、各平台搜索入口。"""
from __future__ import annotations

# ---- 产品 ----
APP_NAME = "悬浮时钟"

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
INVITE_CODE = "MHT-RRUHXOEPWQ"  # 复制邀请文案后打开 App 会自动填，享 14 天试用
# 用户提供的标准邀请文案（复制即用，App 会自动识别邀请码）
INVITE_TEXT = (
    "【icey悬浮时钟邀请】邀请码 MHT-RRUHXOEPWQ，复制这段话后打开 App 会自动填写，"
    "可享 14 天试用。下载：https://money-3jg.pages.dev/apps/floating-clock/"
)
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
    "Android 悬浮时钟",
    "手机 悬浮时钟 带秒",
    "安卓 桌面悬浮时间",
    "手机屏幕 悬浮 秒表时钟",
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

SEARCH_TARGETS = {
    "zhihu": {
        "search_url": "https://www.zhihu.com/search?type=content&q={kw}",
    },
    # 头条号 / 小红书待接入，补 search_url 与选择器后启用
}

# ---- 频控（B1 拟人化低频：每天随机 1~3 条，发一条停 60 秒再发下一条）----
DAILY_MIN_COMMENTS = 1          # 每天最少发布条数
DAILY_MAX_COMMENTS = 3          # 每天最多发布条数（每次运行在 [min,max] 间随机取）
MIN_SECONDS_BETWEEN = 60        # 两次发布最小间隔（秒）——发一条停 1 分钟
# 兼容旧引用：单次运行上限按每日上限算
MAX_COMMENTS_PER_RUN = DAILY_MAX_COMMENTS

# ---- 知乎持久化浏览器 profile 名（绕过 40362 风控的关键）----
ZHIHU_PROFILE = "zhihu"
