# 该不该出门冒险？and / or / not 三个小词，让电脑学会「掂量利弊」

> 这是《我的世界里学编程》系列的第 13 篇，**第二阶段·进阶关**第 4 讲。**上期回顾**：上一课我们请出了字符串世界的一把利器 `split`，把一整串 `/give steve diamond 64` 沿着空格剁成了一个整齐的列表——**长句子按记号剪成一段段**，再靠列表下标各就各位。命令能读懂了，可史蒂夫真正下决定的时候还差最后一步——**今晚到底出不出门？** 天黑不能出、血少不能出、没武器也不能出——**三件事得一起考虑**。今天请出布尔逻辑三兄弟：**and / or / not**。

## 先猜猜看

老规矩，先别往下拉。心里跑一遍这段代码——**猜猜它会打印哪 4 个值**？（每一行都是一个 `True` 或 `False`）

```python
day_time = True
hp = 12
has_sword = True

print(day_time and hp >= 10 and has_sword)
print((not day_time) or hp < 5)
print(day_time and hp < 5)
print(day_time or hp < 5)
```

（提示：**and 要「全都对」才对；or 只要「一个对」就对；not 就是把答案翻个面**。第 2 课学过的比较符号 `>=`、`<` 依然是那些老朋友。）

猜好了记在心里，等下 I-do 一起验。

## 一句话接主线

家园盖好了、价签贴齐了、命令也能读懂了——史蒂夫马上要走出门去探矿、砍树、打怪。**能不能安全出门**不是一件事说了算：**天亮、血够、装备齐**——三条得**同时**成立。**多个条件组合起来做一个决定**，这一步走通了，你的程序就第一次有了「掂量利弊」的能力。

## 用一堆 if 硬堆？好像哪里不对

回到第 2 课的老办法——`if / elif / else`。想判断能不能出门，看起来可以这么写：

```python
day_time = True
hp = 12
has_sword = True

if day_time:
    if hp >= 10:
        if has_sword:
            print("可以出门")
```

三条件三层缩进，勉强能跑。可再加一条「书包里得有食物」呢？再加一条「不能是下雨天」呢？**每多一条就要多缩进一层**——代码歪着长成一棵歪脖子树，改起来还容易漏。

Python 早就给你留了三个小词——**`and`（并且）**、**`or`（或者）**、**`not`（非）**——**把好几个「True/False」拼成一句话**，一行搞定「多条件决策」。翻译成人话：**and 是全票才通过，or 是一票就通过，not 是翻个面**。

## 第一步：认识 and / or / not（I-do）

先给三个小词各来一句最土的定义：

- **`and`（并且）**——**两边都为 `True`，结果才是 `True`**。翻译成人话：**「全都对」才对**。想象组队打副本，只要有一个人没到，团就开不起来。
- **`or`（或者）**——**两边只要有一个是 `True`，结果就是 `True`**。翻译成人话：**「至少一个对」就对**。家里的烟雾报警器，厨房或客厅任何一个响起来都算响。
- **`not`（非）**——**把 `True` 变 `False`，`False` 变 `True`**。翻译成人话：**「反过来」**。晴天说「不是阴天」，说的是同一件事。

一张最短的真值表，记这六条就够：

| 表达式 | 结果 |
|---|---|
| `True and True` | `True` |
| `True and False` | `False` |
| `False or True` | `True` |
| `False or False` | `False` |
| `not True` | `False` |
| `not False` | `True` |

现在回到史蒂夫。**能不能出门**这句话，一行就写得清清楚楚：

```python
day_time = True
hp = 12
has_sword = True

can_go = day_time and hp >= 10 and has_sword
print(can_go)
```

输出：

```
True
```

**从左往右念一遍**——「白天，**并且** 血量 ≥ 10，**并且** 手上有武器」——三件事全对，`can_go` 就是 `True`。少一件都不行。

## 第二步：or 和 not 各露一手（I-do）

**or 的用法**——只要**任何一条**危险信号亮起，就该报警。写成一句：

```python
zombie_near = False
danger = (not day_time) or hp < 5 or zombie_near
```

（这里 `zombie_near` 是「附近有僵尸吗」的布尔变量。）从左往右念：「**不是白天**，**或者** 血量 < 5，**或者** 附近有僵尸」——**任何一条**满足，`danger` 就变成 `True`。

**not 的用法**——把紧跟着的那一坨答案翻个面：

```python
safe = not danger
```

`danger` 是 `True`，`safe` 就是 `False`；`danger` 是 `False`，`safe` 就是 `True`。翻译成人话：**「安全」就是「不危险」**。

小心一个坑：**`not` 只翻紧挨着它的那一坨**。所以想否定一整句，别忘了给它加**括号**：

```python
not (day_time and hp >= 10)   # 否定整句
not day_time and hp >= 10     # 只否定了 day_time 一个
```

看起来长得很像，其实差着十万八千里。**加括号，永远不亏**。

## 第三步：先猜答案，再看揭晓

回到开头的四行，一起念答案：

```python
day_time = True
hp = 12
has_sword = True

print(day_time and hp >= 10 and has_sword)   # ?
print((not day_time) or hp < 5)               # ?
print(day_time and hp < 5)                    # ?
print(day_time or hp < 5)                     # ?
```

一行行看：

- 第一行：`True and (12 >= 10) and True` = `True and True and True` = **`True`**。
- 第二行：`(not True) or (12 < 5)` = `False or False` = **`False`**。
- 第三行：`True and (12 < 5)` = `True and False` = **`False`**——**and 就是那种「只要有一个 False 就投否决票」的家伙**。
- 第四行：`True or (12 < 5)` = `True or False` = **`True`**——**or 只要能找到一个 True，就直接举手通过**。

对上没？没对上也别慌，往回翻一遍上面那张真值表，你会发现规律其实很朴素。

## 一起改改看（We-do）

把上面的代码复制一份，我们改**一个数**——把 `hp = 12` 改成 `hp = 3`：

```python
day_time = True
hp = 3               # ← 只改这一处
has_sword = True

print(day_time and hp >= 10 and has_sword)
print((not day_time) or hp < 5)
print(day_time and hp < 5)
print(day_time or hp < 5)
```

**先别运行，先预测**，把 4 行结果写在纸上。

……

好了，运行一下。你会看到：

```
False
True
True
True
```

对照一下：

- 第一行**从 True 变成 False**——因为 `hp >= 10` 崩了，**and 一票否决**，全句沦陷。
- 第二行**从 False 变成 True**——因为 `hp < 5` 亮了，**or 一票通过**，`danger` 立刻响。
- 第三行**从 False 变成 True**——同上，`hp < 5` 这一路真了，`and` 才把这句救活。
- 第四行**依旧 True**——`day_time` 一直是 `True`，`or` 早就不用看第二个条件了。

**看出来了吗**：`hp` 从 12 掉到 3，「能出门」秒变「不能出门」，「危险」秒变「真危险」。**布尔逻辑就是这样：一个数字变一变，整个决定跟着翻天**。

## 第四步：德摩根——把「非」推进括号里

最后一个小魔法，信奥赛也常考——**德摩根定律（De Morgan's laws）**。翻译成人话：**「非」进括号，「与」变「或」，「或」变「与」**。

看两句大白话：

- **「不下雨 并且 不刮风」** = **「不(下雨 或者 刮风)」**
- **「不下雨 或者 不刮风」** = **「不(下雨 并且 刮风)」**

用代码表达：

```python
not rain and not wind        # 等价于   not (rain or wind)
not rain or  not wind        # 等价于   not (rain and wind)
```

回到史蒂夫。你可能已经写出这样一句判断：

```python
danger = (not day_time) or hp < 5
safe   = not danger
```

`safe` 展开一下，就是：

```python
safe = not ((not day_time) or hp < 5)
```

按德摩根把「非」推进去——**「或」变「与」，两边各自再取反**：

```python
# 一步步来：
# not ((not day_time) or (hp < 5))
# = (not not day_time) and (not (hp < 5))
# = day_time and hp >= 5
safe = day_time and hp >= 5
```

翻译成人话：**「安全」 = 「白天 并且 血量不低于 5」**。是不是比原来那一大坨顺眼多了？

**记这一条口诀就够**：`not (A and B) == not A or not B`；`not (A or B) == not A and not B`。**「非」跨进门，「与/或」互换脸**——考试遇上「化简布尔表达式」，八成靠它。

## 今天你学会了

- **`and`（并且）**：两边**都**为 `True` 才为 `True`——「全都对」才对。
- **`or`（或者）**：两边**任一**为 `True` 就为 `True`——「一个对」就对。
- **`not`（非）**：**翻个面**——`True` 变 `False`，`False` 变 `True`。
- **组合判断**：用 `and / or / not` 一行写清「多条件决策」，比三层 if 缩进优雅一百倍。
- **括号很重要**：`not (A and B)` 和 `not A and B` 差着一个宇宙。**不确定就加括号**。
- **德摩根定律**：`not (A and B) == not A or not B`；`not (A or B) == not A and not B`——**「非」进门，与或互换**。

学到这里，你的程序第一次学会**同时权衡几件事**再做决定——这已经不是「傻乎乎的 if」了，是**会掂量利弊的小脑袋**。

## 课后挑战

**🟢 基础关**

写三个变量：`hp`（血量整数）、`has_sword`（有没有剑，`True/False`）、`is_day`（是不是白天，`True/False`）。写**一行**代码得到 `can_go`：**白天 并且 血量 ≥ 10 并且 有剑**，才算能出门。分别试试下面三组值，**先猜再运行**：

- `hp = 20, has_sword = True, is_day = True` → 猜 True 还是 False？
- `hp = 20, has_sword = False, is_day = True` → ？
- `hp = 20, has_sword = True, is_day = False` → ？

**🔴 进阶关**

加两个条件：`food`（食物块数，整数）、`raining`（在下雨吗，`True/False`）。用**一行**布尔表达式定义 `danger`——**满足任意一条就算危险**：

- 不是白天
- 血量 < 5
- 没有剑
- 食物 < 2
- 下雨

写完之后，再定义 `safe = not danger`，然后**用德摩根定律把 `safe` 手动展开成一个不含 `not danger` 的等价表达式**（提示：**五条全部都不满足**，才算真安全）。

把展开前和展开后两句代码，配同一组变量值分别打印，验证结果**完全一样**——那一刻你就摸到了「等价变换」的门。免费编辑器还是那两个：https://www.online-python.com 和 https://pythontutor.com/visualize.html#mode=display 。动手去尝试，有问题发到评论区，我会一一解答。

## 下期预告

会「掂量」还不够——史蒂夫盘算了一晚上，第二天决定**开一家自动商店**：玩家丢东西进来，程序自己算总价、找零钱、发货。**下一课**（第 14 篇）——**会算账的自动商店**，我们把这一路学的**变量、条件、循环、列表、字典、字符串、函数**全捏到一起，让史蒂夫真正拥有第一台自动化机器。

> 系列导航：本文是第 13 篇。点关注，跟着史蒂夫从零打通信奥赛之路。
