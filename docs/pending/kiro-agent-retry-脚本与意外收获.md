# 我只是想让 Kiro 自动重试，结果顺手治好了"按 y 按到手抽筋"的毛病

## 起因：kiro-cli 极不稳定，尤其是凌晨，高频提示 dispatch failure，几乎无法正常工作

我用 `kiro-cli chat` 跑 agent 已经有一段时间了，体验整体不错，但有一个让我相当头大的小毛病——网络一抖，输出里就会蹦出来类似这样的几行字：

```
dispatch failure
Failed to send the request
error sending request for url ...
Kiro is having trouble responding
```

然后整个会话就停在那里，等我一脸无奈地手动敲一句"继续"或者干脆重跑一遍 prompt。一次两次还能忍，频率上来之后，我基本是一边写代码、一边像看炉子一样盯着终端，生怕错过那一行红字。

更尴尬的是另一个小问题：交互模式下，agent 每跑一个稍微"重"一点的工具调用，都会问一句要不要继续，需要我手动按个键确认。两件事叠在一起，结果就是——**我不是在用 agent，我是在给 agent 当人肉看门人**。

于是我写了个非常朴素的 bash 脚本：`scripts/kiro-agent-retry.sh`。目标只有一个：报错就自己重试，别再叫我了。

## 技术方案：一个 bash 脚本，几个不算花哨的细节

整体思路非常直白：用 `kiro-cli chat --no-interactive` 跑 agent，把输出实时打到终端，同时镜像一份到临时文件用于错误检测，命中错误模式就自动重试，最多重试 N 次。

但真要让它"用起来不难受"，有几个细节是必须处理好的。

### 1. 非交互模式 + 实时输出

非交互模式很关键，否则脚本会卡在某个等待用户输入的地方。但非交互模式带来的副作用是：很多人会图省事直接 `>` 重定向到日志文件，然后人就两眼一抹黑——agent 在跑还是卡住了？跑到哪一步了？完全看不到。

我的做法是用 `tee` 同时写终端和临时文件：

```bash
"${RUNNER[@]}" "${KIRO_BASE[@]}" "$PROMPT" 2>&1 | tee "$TMP_OUT"
ec=${PIPESTATUS[0]}
```

这样既能"边跑边看"agent 的进度，也能在脚本里 grep 错误关键词。`PIPESTATUS[0]` 用来取回管道前面那一段（也就是 `kiro-cli` 自己）的真实退出码，避免被 `tee` 的退出码盖掉，这是 bash 管道里很容易踩的一个坑。

### 2. 错误模式集中维护

把所有"看到这行就当失败"的关键词放到一个数组里，按需添加：

```bash
ERROR_PATTERNS=(
  "dispatch failure"
  "dispatch failed"
  "Failed to send the request"
  "error sending request for url"
  "Kiro is having trouble responding"
)
```

然后用 `|` 拼成一条正则，配 `grep -qiE` 不区分大小写做子串匹配。以后再遇到新的"网络抽风提示"，加一行就行，不需要改逻辑。

### 3. 三段式重试策略：不要把第一次失败就 resume 到一个无关的旧会话

这是写到一半才想明白的一个坑。`kiro-cli` 支持 `--resume` 续上一次的会话，听起来失败重试用 `--resume "继续"` 就完美了——但**首次 dispatch 就失败的时候，会话其实根本没建立**，这时候 `--resume` 会续到本机上一个不相关的旧会话，agent 一上来就开始干奇怪的事。

所以我把重试分成三段：

- 第 1 次：原 prompt 启动。
- 第 2 次（首次失败后的第一次重试）：**仍然用原 prompt 重新开始**，避免续到无关会话。
- 第 3 次及以后：用 `--resume "继续"`，避免每次都从头重做、白白烧 token。

```bash
if (( attempt <= 2 )); then
  "${RUNNER[@]}" "${KIRO_BASE[@]}" "$PROMPT" 2>&1 | tee "$TMP_OUT"
else
  "${RUNNER[@]}" "${KIRO_BASE[@]}" --resume "继续" 2>&1 | tee "$TMP_OUT"
fi
```

**续跑模式下行为略有不同**：当我用 `-r/--continue/--pick` 显式要求续跑某次旧会话时，脚本会在启动时就锁定一个 `SESSION_ID`，之后每次重试都用 `--resume-id "$SESSION_ID"` 死磕同一个会话；同样保持"前两次发原 prompt、第 3 次起发『继续』"的节奏，免得反复重发原始 prompt 烧 token。这样既不会续错会话，也不会因为脚本自己又 dispatch 失败而改换门庭。

### 4. 一些"听起来不重要、用起来很爽"的细节

- **行缓冲**：如果系统里有 `stdbuf`，就用 `stdbuf -oL -eL` 包一层，让 CLI 输出按行刷新，看进度的时候不会出现"卡半天突然吐一大段"的体验。
- **退避**：每次失败之间 `sleep 5`，对端在抖动的时候让它喘口气。
- **退出码语义保留**：成功就用 `kiro-cli` 自身的退出码退出；超过最大重试次数才以 `1` 退出并提示"请人工介入"。
- **`trap cleanup EXIT INT TERM`**：临时文件自动清理，Ctrl-C 中断也不会留垃圾。

整个脚本不到 130 行，没用任何外部依赖，纯 bash + 系统自带的 `tee` / `grep` / `mktemp` / `stdbuf` 就能跑。

## 使用方法

脚本支持「全新会话」和「续跑旧会话」两种模式，常用调用形式如下：

```bash
# === 全新会话（最常用）===

# 1) 用 kiro-cli 配置的默认 agent
scripts/kiro-agent-retry.sh "帮我把 README 重写成更口语化的版本"

# 2) 显式指定 agent
scripts/kiro-agent-retry.sh --agent my-writer "帮我把 README 重写成更口语化的版本"

# 3) 兼容旧用法：第一个位置参数当 agent 名
scripts/kiro-agent-retry.sh my-writer "帮我把 README 重写成更口语化的版本"

# === 续跑已有会话（避免从头重做）===

# 4) 自动续上"当前目录下最近的那次会话"，免去手动找 session id
scripts/kiro-agent-retry.sh -r "继续把昨天那个改了一半的脚本写完"
scripts/kiro-agent-retry.sh --continue "继续把昨天那个改了一半的脚本写完"   # 同上，喜欢敲 --continue 也行

# 5) 交互式从最近若干个会话里挑一个续跑（输一个数字即可）
scripts/kiro-agent-retry.sh --pick "继续之前那个 PR 描述"
scripts/kiro-agent-retry.sh --pick --pick-n 20 "..."   # 默认列最近 10 个，可用 --pick-n 调
```

完整选项一览：

| 选项 | 作用 |
| --- | --- |
| `-a, --agent <agent>` | 指定 agent；不传就用 `kiro-cli` 配置的默认 agent |
| `-r, --resume` / `--continue` | 启动时自动锁定"当前目录下最近一次会话"，全程 `--resume-id` 续跑 |
| `--pick` | 交互式列出最近若干个会话，输数字选一个续跑（默认回车=1，q 取消） |
| `--pick-n <N>` | `--pick` 模式展示最近多少个会话，默认 10 |
| `-h, --help` | 查看帮助 |

参数解析里也顺手支持了 `--agent=xxx`、`--pick-n=20`、`--` 这一套常见 flag 写法，行为和大多数 CLI 工具一致，不需要专门记。

跑起来之后，终端长这样（"第 N/M 次运行 …"那一行会用**黄色高亮**显示，方便一眼定位重试节奏）：

```
[retry] 第 1/10 次运行 agent=<kiro-cli 默认 agent>
[retry] ----- agent 输出开始 -----
... agent 正常输出 ...
... 突然 dispatch failure ...
[retry] ----- agent 输出结束 (exit=1) -----
[retry] 检测到错误，5 秒后重试…
[retry] 第 2/10 次运行 agent=<kiro-cli 默认 agent>
...
[retry] 未检测到错误（退出码 0），结束。
[retry] 共运行 3 次（重试了 2 次）后成功。
```

如果是续跑模式，第一行会变成：

```
[retry] 第 1/10 次运行 agent=<kiro-cli 默认 agent> (续跑 01HZXXXXXXXXXXXXXXXXXXXXXX)
```

成功结束时会额外打一行总结：一次过就提示"一次成功，无需重试"，否则给出"共运行 N 次（重试了 N-1 次）后成功"；如果用满 `MAX_RETRY` 还是失败，则在末尾提示"已达最大重试 …，请人工介入"并附带运行 / 重试次数。我可以放心去做别的事，回头瞄一眼终端就知道它跑了几次、是不是真的成功了。

## 意外的副作用：人肉确认环节也一起没了

写这个脚本的时候，我心里只有一个目标：**别再让我手动重试了**。

但跑了几天之后我才反应过来，**它顺手把另一个我抱怨已久的痛点也解决了**：

因为脚本里固定用的是 `kiro-cli chat --no-interactive -a`，agent 在跑的过程中不会再每隔几十秒弹出来一次"是否继续 / 是否允许这个工具调用"的人工确认。一个长任务从开始到结束，我可以完全不动键盘——出错自动重试，不出错就一路跑到底。

这是个有点反直觉的体会：**我本来想解决 A，结果工具用法变了之后，B 自己就没了**。回过头看，"反复手动重试"和"反复手动确认"其实是同一个根：我把自己塞进了 agent 的执行循环里，做了一件本不该由人做的事。把这一层包装出去之后，我的角色才真正变回"提需求 + 看结果"，agent 也才真正像个 agent。

## 一些坦白话

这个脚本说穿了真的就是个朴素的 bash 包装，没什么巧思：`tee` + `grep` + `while` 循环 + 一点点关于 `--resume` 时机的小细节。能解决我自己的问题，纯粹是因为我用得够多、痛得够具体。

我也很清楚它有不少可以更好的地方：

- 错误模式现在是硬编码的，更优雅的做法应该是放到一个外部配置文件里，甚至支持按 exit code 区分。
- 退避策略目前是固定 5 秒，指数退避会更礼貌一些。
- 没有日志归档，长期使用的话 `mktemp` 出来的文件其实可以保留下来按天归档，方便事后排查。
- 多人协作或 CI 场景下，可能还需要加一层"重试期间不要打印重复 banner"的小优化。

这些我自己都还没动手做，后面用到了再慢慢补。如果你也在被 `kiro-cli` 的网络毛刺折磨、或者有更聪明的写法，非常欢迎拍砖、贴 patch、贴你自己的版本——我对自己的 bash 水平没啥幻觉，能学到一点是一点，一起进步。🙏
