"""推广文案生成。

默认用内置模板按卖点随机组合生成"自然、像真人回复"的短文案（不依赖 LLM，离线可跑）；
若 zhihu 项目已配置 LLM，可在此扩展接入 src.content_generator，但推广评论
更适合短、口语、不硬广，模板已够用。
"""
from __future__ import annotations

import random

from . import config


def _invite_text() -> str:
    """用户提供的标准邀请文本，必须**原样输出，不得改动一个字**。
    任何推广文案只能加在它前面，不能在其后追加内容（如备用网盘等）。
    """
    return config.INVITE_TEXT


def generate_comment(*, question_title: str = "", platform: str = "zhihu") -> str:
    """生成一条推广评论：前面是随机组合的推广文案，最后原样附上标准邀请文本。

    突出体积小 / 不占空间 / 耗电低，口吻自然，像真人安利。
    """
    openers = [
        "我一直在用一个叫「icey悬浮时钟」的小工具，正好对口。",
        "分享个我自己在用的「icey悬浮时钟」，挺适合这个需求。",
        "这种带秒的悬浮时钟我试过不少，最后留下的是「icey悬浮时钟」这个。",
        "同需求，后来找到「icey悬浮时钟」就一直用到现在了。",
    ]
    # 固定强调三大卖点
    core = "最大的好处是安装包特别小、几乎不占空间，后台也基本不耗电；时间带秒浮在最上层，全屏看视频打游戏都能瞄一眼。"
    # 普适推荐语：随机补一条，覆盖不同使用场景与卖点
    extra = random.choice(
        [
            "可以拖动位置、锁定后还能触摸穿透不挡操作，怎么用都顺手。",
            "字号、颜色、透明度都能调，白天黑夜、亮屏暗屏都看得清。",
            "上手零门槛，装上点一下就浮出来了，不用折腾设置。",
            "看直播、打游戏、上网课盯时间特别方便，比频繁下拉状态栏省事多了。",
            "小而专注，没有广告弹窗和乱七八糟的权限，这点我很喜欢。",
        ]
    )
    promo = f"{random.choice(openers)}{core}{extra}"
    # 推广文案在前，邀请文本原样在后
    return f"{promo}\n\n{_invite_text()}"


def generate_article_snippet() -> str:
    """生成一段可用于公众号/文章的较长推广文案，末尾原样附标准邀请文本。"""
    points = "\n".join(f"- {p}" for p in config.SELLING_POINTS)
    promo = (
        f"【icey悬浮时钟】一个浮在所有安卓应用之上的带秒数字时钟，"
        f"适合看直播、打游戏、上网课、盯考试倒计时的人：\n{points}"
    )
    return f"{promo}\n\n{_invite_text()}"
