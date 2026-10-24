# Dockerfile 已经找不到了：怎么给线上镜像改一行代码，并证明只改了这一行

线上有个 18GB 的训练镜像，123 层，现在需要改里面一个 shell 脚本的一行代码——给 `git clone` 加上 `--depth=1`。

改动本身是一行的事，麻烦在两件事上。

第一件是**不能重建**。这个项目经手过好几个同事，仓库里有多个 Dockerfile、改过很多轮，已经说不清线上那个镜像到底是哪一份、哪个 commit 构建出来的；就算考古考对了，那份 Dockerfile 今天也未必还能构建成功。也就是说，线上这个镜像本身就是唯一可信的基线，它是个黑盒，你只能在它之上叠东西，没法从源头再生产一份。

第二件是**要能证明**。灰度镜像要上线，评审的人凭什么相信你没顺手带进别的东西。而且恰恰因为没法重建，"和 base 只差一行"这个论断没有第二条路可以交叉验证——不能拿"我重建一份对比一下"来兜底，只能从镜像本身下手取证。

这两件事是同一个问题的两面：当构建不可复现时，镜像就从"构建产物"退化成了"既成事实"，你对它的一切论断都只能靠对镜像本身做取证来支撑。

这篇把我实际的做法和验证过程记下来。

## 一、三种改法，只有一种能用

### 1. 从 Dockerfile 完整重建：这条路已经断了

最直觉的做法是去仓库改源码，然后重跑构建流水线。在这个场景下它走不通，而原因不是慢——全量重建也就几十分钟，等得起。

真正的问题是**不知道该重建哪一份，以及大概率重建不出来**。

项目经手过多个同事，`dockerfiles/` 下有好几个目录，Dockerfile 本身也改过很多轮。线上镜像是某个时间点、由某个人、用某一版 Dockerfile 构建的，但这个对应关系没有被完整记录下来。翻 git log 能看到一堆 commit，看不出哪个 commit 产出了现在线上跑的这个 tag。tag 本身也不帮忙——`:default` 这种滚动 tag 被覆盖过很多次，它只告诉你"当前哪个镜像在用"，不告诉你"它从哪来"。

退一步说，就算考古考对了，那份 Dockerfile 今天也未必还能跑通。长期没重建过的镜像，构建链条上到处是会腐坏的环节：

- `FROM` 的上游镜像 tag 被覆盖或删除了；
- `apt-get install` 里没锁版本的包，源里已经换了新版本，编译不过；
- `pip install` 锁的某个版本被 yank 了，或者私有源里那个包清理掉了；
- 构建过程里 `wget` / `curl` 的外部链接失效了；
- 某个编译步骤依赖的工具链版本变了，报一堆陌生错误。

一旦其中任何一环断掉，你就得先把构建修通才能继续——而修构建的过程本身必然改变镜像内容，"只改一行"从此不成立。

还有第三层问题，就算 Dockerfile 完好、构建也能跑通，重建出来的仍然不是"base + 一行"。base 是几周甚至几个月前从某个 commit 构建的，仓库 HEAD 早就往前走了。重建会把这期间所有改动一起带上：别人的 commit、依赖版本变化、apt 源里的包升级。

这三层叠加起来，结论很明确：**线上镜像是唯一可信基线**。把它当黑盒，在它之上叠改动，别试图回到源头。

### 2. `docker commit`：能改，但不可复现

进容器改完文件，然后 `docker commit` 存成新镜像：

```bash
docker run -it --name tmp base-image:tag bash
# 容器里 vi 改文件
docker commit tmp new-image:tag
```

结果是对的，但这个镜像没有构建记录。半年后你想知道它和 base 差在哪，只能靠翻文档或者猜。`docker history` 里那一层的 `CreatedBy` 是空的，什么信息都没有。一次性调试可以，要上线的镜像不行。

### 3. `FROM base` + `COPY`：正确解

写一个只有两行的 Dockerfile，在 base 上叠一层：

```dockerfile
FROM registry.example.com/dev/ubuntu22.04-torch2.6.0-cuda12.6:default

COPY --chmod=755 get_code.sh /root/get_code.sh
```

这个方案的好处不在于快（虽然确实只花几秒），而在于三点：

**它完全不依赖原始 Dockerfile 可用。** base 是怎么来的、当初那份 Dockerfile 还在不在、能不能跑通，都无关紧要。你只需要 base 镜像本身存在。

**改动意图落在文件里，可追溯。** 这两行 Dockerfile 可以提交进仓库，`docker history` 里也会留下 `COPY ... # buildkit` 的记录。比 `docker commit` 那种黑盒强得多。

**它在结构上就保证了 base 的每一层原封不动。** 这点最重要——第五节的整套验证就是建立在这个性质上的。`FROM` + 一个 `COPY` 只会在 base 的层序列尾部追加一层，底下 123 层的 digest 一个都不会变。这不是"我小心操作所以没碰到"，而是构建方式决定的，可以用 digest 严格验证。

## 二、有个坑：别用仓库里的文件去 COPY

上面那个 Dockerfile 里 `COPY get_code.sh`，这个 `get_code.sh` 从哪来？

直觉是从 git 仓库里拿一份改改。**这是错的**，而且在"说不清镜像是哪个 commit 构建的"这个前提下，错得更彻底——你连该 checkout 到哪个 commit 都不知道，仓库里任何一份文件都不能假定和镜像里那份一致。

我这次的实际情况：从镜像里抠出来的脚本是 6277 字节，`git clone` 后面跟的是老式的 `if [ $? -ne 0 ]` 判断；而仓库 HEAD 那份已经被人重构成 `if ! git clone ...; then` 了，还顺带改了几处错误提示文案。

镜像是几周前构建的，仓库一直在往前走。如果直接拿仓库版本去 COPY，这个号称"只改一行"的镜像实际上会把别人那次重构一起带进去。而且这种偏差很隐蔽——两个文件长得很像，肉眼过一遍不容易发现，`diff` 一下才现形。

正确做法是从**镜像里**把文件抠出来改。镜像是唯一基线，这个原则要一路贯彻到取文件这一步：

```bash
BASE=registry.example.com/dev/ubuntu22.04-torch2.6.0-cuda12.6:default
WORK=/tmp/depth1_build
mkdir -p "$WORK"

CID=$(docker create "$BASE")
docker cp "$CID":/root/get_code.sh "$WORK/get_code.sh"
docker rm "$CID"
```

`docker create` 只创建容器不启动，专门用来做这种文件提取，比 `docker run` 干净。

留一份原件用来比对：

```bash
cd "$WORK"
cp get_code.sh get_code.sh.orig
```

## 三、精确改那一行

不要用 `vi` 手改，容易带进不可见的空白变化。用 `sed` 锚定整行替换：

```bash
sed -i 's|^\(\s*\)git clone https://\$MI_USER:\$MI_TOKEN@\$REPO_URL \$REPO_DIR$|\1git clone --depth=1 https://$MI_USER:$MI_TOKEN@$REPO_URL $REPO_DIR|' get_code.sh
```

几个细节：

- 用 `|` 当分隔符而不是 `/`，因为待匹配内容里有 URL 的斜杠。
- 开头 `^\(\s*\)` 捕获原有缩进并在替换里用 `\1` 还原，避免改变缩进。
- 结尾 `$` 锚定行尾，保证是整行精确匹配，不会误伤别处。
- 模式里的 `$MI_USER` 等要写成 `\$MI_USER` 转义。

改完立刻做两件事——看 diff，跑语法检查：

```bash
diff get_code.sh.orig get_code.sh
bash -n get_code.sh && echo "语法 OK"
```

我这次的输出，两处 `git clone`（gerrit 分支和非 gerrit 分支各一处）都命中了：

```
131c131
<   git clone https://$MI_USER:$MI_TOKEN@$REPO_URL $REPO_DIR
---
>   git clone --depth=1 https://$MI_USER:$MI_TOKEN@$REPO_URL $REPO_DIR
174c174
<   git clone https://$MI_USER:$MI_TOKEN@$REPO_URL $REPO_DIR
---
>   git clone --depth=1 https://$MI_USER:$MI_TOKEN@$REPO_URL $REPO_DIR
```

`bash -n` 这一步别省。脚本类改动如果引入语法错误，镜像能构建成功、能推上去，直到线上跑起来才炸。

## 四、构建，并且别让 `unknown/unknown` 冒出来

```bash
TAG=$(date +"%Y%m%d%H%M%S")
IMAGE="registry.example.com/dev/ubuntu22.04-torch2.6.0-cuda12.6:${TAG}"

docker build --provenance=false --sbom=false --platform linux/amd64 \
  -t "$IMAGE" -f Dockerfile .
```

`--provenance=false --sbom=false` 这两个参数有必要解释一下，它解决的是一个很常见的困惑。

新版 Docker（23+）在启用 containerd 镜像存储时，`docker build` 实际走的是 BuildKit，默认会给镜像附加 provenance attestation。这时构建输出不再是单个 manifest，而是一个 OCI index，里面装着两条：真实镜像（`linux/amd64`）和一条 attestation manifest。attestation 那条的 platform 字段是空的，推到仓库后 UI 就显示成 `unknown/unknown`。

于是你在镜像仓库页面上会看到自己的镜像有两个"平台"，而同事推的只有一个 `linux/amd64`，差别就在这里。加上这两个参数关掉 attestation，导出的就是干净的单 manifest。

对照一下构建日志就很清楚。不加参数时：

```
#7 exporting manifest sha256:191ccea...
#7 exporting attestation manifest sha256:203ae86...   ← 这条就是 unknown/unknown
#7 exporting manifest list sha256:4a81b55...          ← 被包成了 OCI index
```

加上参数后：

```
#7 exporting manifest sha256:a3abe177...
#7 exporting config sha256:5a1faa85...
```

没有 attestation，没有 manifest list。

`--platform linux/amd64` 是显式固定目标平台，不依赖本机默认值，多人协作时能少一类"我这儿构建出来是对的"的问题。

如果要兼容老版本 Docker（传统 builder 不认这些参数），可以先探测再决定传不传：

```bash
BUILD_FLAGS=()
BUILD_HELP="$(docker build --help 2>/dev/null || true)"
case "$BUILD_HELP" in *--provenance*) BUILD_FLAGS+=(--provenance=false) ;; esac
case "$BUILD_HELP" in *--sbom*)       BUILD_FLAGS+=(--sbom=false) ;; esac
case "$BUILD_HELP" in *--platform*)   BUILD_FLAGS+=(--platform linux/amd64) ;; esac

docker build "${BUILD_FLAGS[@]}" -t "$IMAGE" -f Dockerfile .
```

顺带一提，老版本 Docker 不加这些参数也不会产生 attestation，所以探测不到就不传是安全的。

## 五、怎么证明只改了那一行

这是重点。下面五道检查，按证明力从强到弱排。日常跑前两道就够，要出评审报告再往下走。

先约定变量：

```bash
BASE=registry.example.com/dev/ubuntu22.04-torch2.6.0-cuda12.6:default
NEW=a3abe177a3e3   # 新镜像的 Image ID
```

### 检查 1：层 digest 前缀比对（决定性）

这一步是整套验证的地基。

OCI 镜像的层是内容寻址的，`docker inspect` 里 `RootFS.Layers` 那一串是各层的 diff_id，即未压缩层 tarball 的 sha256。**只要 base 的层序列是 new 的严格前缀，那些层叠出来的文件系统状态就是密码学意义上完全一致的**，不需要再去逐个文件核对下面那 18GB。

```bash
docker inspect --format '{{range .RootFS.Layers}}{{println .}}{{end}}' "$BASE" | grep . > /tmp/base.layers
docker inspect --format '{{range .RootFS.Layers}}{{println .}}{{end}}' "$NEW"  | grep . > /tmp/new.layers

N=$(wc -l < /tmp/base.layers)
echo "base 层数: $N   new 层数: $(wc -l < /tmp/new.layers)"

if cmp -s /tmp/base.layers <(head -n "$N" /tmp/new.layers); then
  echo "base 全部 $N 层是 new 的严格前缀，digest 与顺序完全一致"
else
  echo "底层存在差异！"
  diff /tmp/base.layers <(head -n "$N" /tmp/new.layers)
fi

echo "new 独有的新增层:"
tail -n +"$((N+1))" /tmp/new.layers
```

我的结果：

```
base 层数: 123   new 层数: 124
base 全部 123 层是 new 的严格前缀，digest 与顺序完全一致
new 独有的新增层:
sha256:f652d0b5cb4187f1a4aa804bebc8930090df4e7bd668827cd66c43873882e6df
```

**注意那个 `grep .`。** Go template 的 `{{println}}` 会在最后多吐一个空行，不过滤掉的话 `wc -l` 会多算一行，`diff` 会报一个不存在的差异。我第一次跑就被这个坑了，输出是这样的：

```
=== base 的层是否是 new 的严格前缀 ===
NO: 底层有差异
124c124
<
---
> sha256:f652d0b5cb41...
```

看着像底层被改了，其实是拿 base 的尾部空行去和 new 的第 124 层比。加个 `grep .` 就干净了。

### 检查 2：新增层有多大、由什么指令产生

`docker history` 给出每层的大小和 CreatedBy，和 base 对比就知道多了几步：

```bash
docker history --no-trunc --format '{{.Size}}|{{.CreatedBy}}' "$BASE" > /tmp/base.hist
docker history --no-trunc --format '{{.Size}}|{{.CreatedBy}}' "$NEW"  > /tmp/new.hist
diff /tmp/base.hist /tmp/new.hist
```

结果只多一行：

```
> 16.4kB|COPY --chmod=755 get_code.sh /root/get_code.sh # buildkit
```

16.4kB 这个数字本身就是证据。一层只有十几 KB，物理上装不下别的东西——文件本身 6297 字节，剩下是 tar 块对齐和父目录条目的开销。反过来说，如果这里显示的是几百 MB，那就该去查查是不是 COPY 的范围写宽了。

### 检查 3：config 对比（最容易漏）

**层没变不等于镜像行为没变。**

`ENV`、`CMD`、`ENTRYPOINT`、`USER`、`WORKDIR`、`LABEL`、`VOLUME`、`EXPOSE` 这些全部存在 image config 里，改它们**不产生任何新层**。也就是说，两个镜像可以层完全一致但跑起来行为完全不同：

```dockerfile
FROM app:base
ENV MODE=prod
```
```dockerfile
FROM app:base
ENV MODE=dev
```

这两个镜像的 `RootFS.Layers` 一模一样。所以检查 1 通过之后必须补一刀 config 对比：

```bash
dump_cfg() {
  docker inspect "$1" --format '{{json .Config}}' | python3 -c '
import json,sys
c=json.load(sys.stdin)
for k in sorted(c):
    v=c[k]
    if k=="Env" and v:
        for e in sorted(v): print("Env:", e)
    else:
        print(k+":", json.dumps(v, sort_keys=True, ensure_ascii=False))
'
  docker inspect "$1" --format 'Architecture: {{.Architecture}}
Os: {{.Os}}'
}

diff <(dump_cfg "$BASE") <(dump_cfg "$NEW")
```

这里把 `Env` 拆开逐条排序输出，是因为 `Env` 是数组，元素顺序可能因构建方式不同而变化，直接比 JSON 会产生假差异。`Architecture` / `Os` 单独带上，防止误比了不同平台的镜像。

我的结果是无差异。

### 检查 4：rootfs 逐文件对比（端到端兜底）

不依赖任何镜像元数据，直接进容器枚举全部文件的路径、类型、大小、权限、属主：

```bash
enum() {
  docker run --rm --entrypoint find "$1" / -xdev \
    -printf '%y %10s %M %U:%G %p\n' 2>/dev/null | LC_ALL=C sort
}

diff <(enum "$BASE") <(enum "$NEW")
```

结果，两边各 197070 个文件，差异仅一条：

```
< f       6277 -rwxrwxr-x 0:0 /root/get_code.sh
> f       6297 -rwxr-xr-x 0:0 /root/get_code.sh
```

几个要点：

- `-xdev` 不跨文件系统，避免把 `/proc`、`/sys`、`/dev` 这些运行时挂载点扫进来。
- `LC_ALL=C sort` 固定排序规则，不同 locale 下排序结果不一样，会产生大量假差异。
- 这一步只读元数据不读文件内容，所以比想象的快，18GB 镜像几分钟能跑完。

**它和检查 1 是互补的**，这点值得说清楚。单看检查 4 有个盲区：如果某个文件被换成了同样大小、同样权限的另一份内容，元数据对比发现不了。但检查 1 已经用 digest 证明了下面 123 层的内容完全一致，这种篡改不可能藏在那里；而新增层只有 16.4kB，能塞的东西也就这一个文件。两道检查合起来，没有漏网空间。

反过来单看检查 1 也不够——它只能证明底层没动，证明不了新增层里没有夹带别的路径，那正是检查 4 覆盖的。

### 检查 5：那个文件本身改了什么

最后确认文件内容的实际差异：

```bash
diff <(docker run --rm --entrypoint cat "$BASE" /root/get_code.sh) \
     <(docker run --rm --entrypoint cat "$NEW"  /root/get_code.sh)
```

输出就是第三节那两处 `--depth=1`，差异 4 行（2 处改动），别的没动。

用 `--entrypoint cat` 是因为这个镜像的 ENTRYPOINT 是训练启动脚本，直接 `docker run` 会拉起一堆东西。覆盖掉 entrypoint 才能干净地只读一个文件。

## 六、一个必须承认的副作用

上面检查 4 的输出里有个细节，我得单独拎出来：

```
< f       6277 -rwxrwxr-x 0:0    (base, mode 775)
> f       6297 -rwxr-xr-x 0:0    (new,  mode 755)
```

权限从 775 变成了 755。原因是我 Dockerfile 里写的是 `COPY --chmod=755`。

base 那个 775 其实是当初构建时宿主机文件的 group-write 位漏进镜像的产物。脚本以 root 执行，755 不影响功能，而且更规范。但严格说，"只改了内容"这个描述是不准确的——同一个文件的 mode 也变了，写评审说明时要如实提一句。

如果要求连 mode 都和线上完全一致，把 `--chmod=755` 改成 `--chmod=775` 重建即可。或者干脆不写 `--chmod`，让它继承宿主机文件的权限——但那样就得保证宿主机上那份文件的权限是你想要的，不如显式写死。

这件事的普适教训是：`COPY` 会同时决定内容和元数据，验证的时候两样都要看。

## 七、几个容易搞错的概念

**`docker diff` 不能比较两个镜像。** 它的语义是"某个容器相对于它自己的镜像发生了哪些变化"，参数是容器 ID 不是镜像 ID。想比两个镜像得用上面检查 4 的办法。

**层 digest 相同不代表是同一个镜像。** 判断"是不是同一个镜像"的严格标准是 manifest digest；判断"行为是否等价"是 config digest（也就是 Image ID）；层 digest 只覆盖文件系统。三者的覆盖范围是层层包含的关系：

| 比什么 | 覆盖范围 | 够不够 |
| --- | --- | --- |
| manifest digest（`RepoDigests`） | config + 全部层 + 顺序 + 平台 | 最严格，相等即同一镜像 |
| config digest（Image ID，`.Id`） | config + 全部层的 diff_id | 覆盖行为等价性 |
| layer digests（`RootFS.Layers`） | 只有文件系统内容 | 不够，config 可能不同 |

**本地没 push 过的镜像没有 manifest digest。** `RepoDigests` 要 push 之后才有。想在 push 前拿本地镜像和线上比，就 `docker pull` 线上那个然后比 `.Id`：

```bash
docker pull "$BASE"
docker inspect --format '{{.Id}}' "$BASE"
docker inspect --format '{{.Id}}' "$NEW"
```

顺带说，我这次 base 的本地 Image ID 是 `22aea9907348`，而 `docker buildx imagetools inspect` 查到线上 manifest digest 是 `sha256:22aea9907348...`，两者一致，说明本地这份就是线上那份，可以放心当基线用。这一步在动手前做一次比较稳妥——万一你本地那个 `:default` 是三个月前 pull 的旧货，后面所有验证都是在错的基线上做的。

## 八、完整流程速查

```bash
# ---- 0. 确认基线就是线上那份 ----
BASE=registry.example.com/dev/your-image:default
docker pull "$BASE"
docker inspect --format '{{.Id}}' "$BASE"
docker buildx imagetools inspect "$BASE" | grep Digest   # 两者应一致

# ---- 1. 从镜像里抠出文件 ----
WORK=/tmp/patch_build; rm -rf "$WORK"; mkdir -p "$WORK"; cd "$WORK"
CID=$(docker create "$BASE")
docker cp "$CID":/root/get_code.sh ./get_code.sh
docker rm "$CID"
cp get_code.sh get_code.sh.orig

# ---- 2. 精确改行 + 自检 ----
sed -i 's|<原行正则>|<新行>|' get_code.sh
diff get_code.sh.orig get_code.sh
bash -n get_code.sh

# ---- 3. 叠一层构建 ----
cat > Dockerfile <<EOF
FROM $BASE
COPY --chmod=755 get_code.sh /root/get_code.sh
EOF
TAG=$(date +"%Y%m%d%H%M%S")
NEW="${BASE%:*}:$TAG"
docker build --provenance=false --sbom=false --platform linux/amd64 -t "$NEW" .

# ---- 4. 验证 ----
# 层前缀
docker inspect --format '{{range .RootFS.Layers}}{{println .}}{{end}}' "$BASE" | grep . > /tmp/b.l
docker inspect --format '{{range .RootFS.Layers}}{{println .}}{{end}}' "$NEW"  | grep . > /tmp/n.l
N=$(wc -l < /tmp/b.l); cmp -s /tmp/b.l <(head -n "$N" /tmp/n.l) && echo "底层未变"
# 新层大小与指令
diff <(docker history --no-trunc --format '{{.Size}}|{{.CreatedBy}}' "$BASE") \
     <(docker history --no-trunc --format '{{.Size}}|{{.CreatedBy}}' "$NEW")
# config
diff <(docker inspect "$BASE" --format '{{json .Config}}') \
     <(docker inspect "$NEW"  --format '{{json .Config}}')
# rootfs
enum() { docker run --rm --entrypoint find "$1" / -xdev -printf '%y %10s %M %U:%G %p\n' 2>/dev/null | LC_ALL=C sort; }
diff <(enum "$BASE") <(enum "$NEW")
```

## 小结

这个需求的真实背景不是"重建太慢"，而是"重建这条路已经断了"：项目经手过多个同事，说不清线上镜像是哪份 Dockerfile、哪个 commit 构建的，那份 Dockerfile 今天也未必还能跑通。一旦构建不可复现，镜像就从"构建产物"退化成"既成事实"——**它自己成了唯一可信基线**。

这个前提决定了后面所有选择。改法上只能用 `FROM base` + `COPY` 在黑盒上叠一层，因为它不依赖原始 Dockerfile 可用；待 COPY 的文件必须从镜像里抠而不是从仓库拿，因为连该用哪个 commit 都不知道；验证上不能靠"重建一份对比"来交叉印证，只能对镜像本身做取证。

取证的最小充分集是两道检查：**层 digest 前缀比对 + config 对比**。一个管文件系统，一个管运行时配置，加起来覆盖了镜像的全部构成。前者是密码学强度的——digest 相同就是内容相同，不需要读那 18GB；后者堵住"层没变但行为变了"这个最容易漏的口子。要更硬的证据就补 rootfs 逐文件枚举，它和层比对互补，能堵住"新层夹带别的路径"。

最后，如实说明副作用。这次 mode 从 775 变成 755，是 `--chmod` 带来的真实差异，藏着不说比差异本身更糟。
