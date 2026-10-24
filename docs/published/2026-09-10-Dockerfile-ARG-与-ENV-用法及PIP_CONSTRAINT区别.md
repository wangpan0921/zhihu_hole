# Dockerfile 里的 ARG 与 ENV：机制、用法，以及 PIP_CONSTRAINT 的两种写法

写 Dockerfile 时，`ARG` 和 `ENV` 都是"设置一个变量"，看起来能互换。真正上手会发现它们的生效阶段、作用域、能否被覆盖、写不写进镜像都完全不同。用错的典型症状是：

- 明明 `ARG` 设了值，容器里 `echo $VAR` 却是空的；
- `--build-arg` 传进来的版本号，没体现在镜像元数据里；
- 构建期改了个 ARG，缓存却没打穿，仍然用了旧的层；
- 明明想只在构建期用一个变量，结果它跟着镜像跑到线上；
- 同名 `ARG` 和 `ENV` 一起写，行为跟直觉相反。

这篇文章把两者的机制讲清楚，最后用一个真实的案例做对照：同一个变量名 `PIP_CONSTRAINT`，为什么在同一份 Dockerfile 里既作为 `ARG` 又作为 `ENV` 出现，两次出现的目的截然不同。

---

## 一、ARG：只在构建期活着的变量

### 语法

```dockerfile
ARG <name>[=<default>]
```

- `ARG NAME`：声明一个构建参数，没有默认值。构建时若未通过 `--build-arg` 传入，值为空。
- `ARG NAME=default`：带默认值。

一个最小可运行的例子：

```dockerfile
FROM ubuntu:22.04
ARG APP_VERSION=dev
RUN echo "building version: ${APP_VERSION}"
```

构建：

```bash
docker build -t demo:latest .
# 输出：building version: dev

docker build --build-arg APP_VERSION=1.2.3 -t demo:v1 .
# 输出：building version: 1.2.3
```

### 只在构建期存在

ARG 只在 `docker build` 过程中存在，**不会**写入最终镜像的元数据，也不会作为环境变量出现在容器进程里。上面的例子构建完后：

```bash
docker run --rm demo:v1 sh -c 'echo "$APP_VERSION"'
# 输出：（空行）
```

容器里的 `APP_VERSION` 是空的，因为 ARG 从来没被写进镜像。这一点是 ARG 与 ENV 最本质的区别。

### 引用方式

在 Dockerfile 里用 `${VAR}` 或 `$VAR` 引用。它有两个层次：

1. **Dockerfile 指令层的变量替换**：解析器在处理 `COPY`、`ADD`、`WORKDIR`、`FROM` 等指令时，直接把 `${VAR}` 替换成字面量。
2. **RUN 的 shell 环境**：BuildKit 会把 ARG 值作为环境变量注入 `RUN` 起的那个 shell，所以 `RUN echo $VAR` 也能拿到值。

因此下面两种写法在 RUN 里都工作：

```dockerfile
ARG APP_VERSION=1.2.3
RUN echo "${APP_VERSION}"    # 变量替换
RUN echo "$APP_VERSION"      # shell 环境
```

第二种写法特别重要，因为它意味着**很多识别环境变量的工具（比如 pip 认 `PIP_CONSTRAINT`、curl 认 `HTTPS_PROXY`）在 RUN 里能自动读到 ARG 的值**，即便这些值不会留在最终镜像里。

### 作用域：三条规则

ARG 的作用域是新手最容易踩的坑，记住三条：

**规则 1：`FROM` 之前的 ARG，只对 `FROM` 行本身可见。**

```dockerfile
ARG BASE_TAG=22.04
FROM ubuntu:${BASE_TAG}
# 这里 BASE_TAG 已经"消失"了，下面这行拿不到值
RUN echo "$BASE_TAG"    # 空
```

如果之后还想用它，必须在 FROM 之后重新声明一次：

```dockerfile
ARG BASE_TAG=22.04
FROM ubuntu:${BASE_TAG}
ARG BASE_TAG            # 再声明一次，作用域重新开始
RUN echo "$BASE_TAG"    # 22.04
```

**规则 2：`FROM` 之后的 ARG，从声明位置开始生效，直到当前 stage 结束。**

```dockerfile
FROM ubuntu:22.04
RUN echo "${MY_VAR}"    # 空，还没声明
ARG MY_VAR=hello
RUN echo "${MY_VAR}"    # hello
```

**规则 3：多阶段构建时，每个 stage 独立，需要重新声明。**

```dockerfile
FROM ubuntu:22.04 AS builder
ARG COMMIT=unknown
RUN echo "$COMMIT"      # 生效

FROM ubuntu:22.04 AS runtime
RUN echo "$COMMIT"      # 空！第二个 stage 里没有 COMMIT
ARG COMMIT              # 再声明一次才拿得到
RUN echo "$COMMIT"
```

### 缓存行为

改变 `--build-arg` 传入的值会让**从该 ARG 首次被引用的那一层开始**cache 失效，之后所有层都会重建。这里的"首次被引用"指的是变量替换或 shell 环境注入实际发生的那一层，而不是 ARG 声明的那一层。

由此得出两条实用建议：

- **频繁变化的 ARG 尽量放到 Dockerfile 靠后位置**。比如 CI 每次构建都会变化的 git commit / 版本号，放在最末尾就行；如果放在开头，后面所有 apt/pip 层都会被打穿。
- **稳定的、决定基础镜像结构的 ARG 才放到 `FROM` 之前**，比如 `BASE_TAG`、`PYTHON_VERSION`。

### 预定义 ARG

Docker 内置了一批 ARG，声明后可直接使用：

- `HTTP_PROXY`、`HTTPS_PROXY`、`FTP_PROXY`、`NO_PROXY`（大小写各一份）
- `TARGETPLATFORM`、`TARGETOS`、`TARGETARCH`、`TARGETVARIANT`
- `BUILDPLATFORM`、`BUILDOS`、`BUILDARCH`、`BUILDVARIANT`

代理类的预定义 ARG 有一个便利：它们不会出现在 `docker history` 里，构建期临时用代理不会泄漏到镜像元数据。

### 安全：ARG 不适合传密钥

`ARG` 的值虽然不会写入运行时环境，但会出现在 `docker history --no-trunc` 里，也会随构建层的元数据保存。**任何拿到这份镜像的人都能看到 ARG 值。**

要在构建期使用密钥（比如私有仓库 token），用 BuildKit 的 secret 机制：

```dockerfile
# syntax=docker/dockerfile:1
FROM ubuntu:22.04
RUN --mount=type=secret,id=pip_token \
    PIP_TOKEN=$(cat /run/secrets/pip_token) \
    pip install --index-url "https://oauth2:${PIP_TOKEN}@pypi.internal/simple" mypkg
```

构建命令：

```bash
docker build --secret id=pip_token,src=./token.txt -t myimg .
```

secret 只在那一条 RUN 里可见，不会进入任何镜像层。

---

## 二、ENV：跨越构建与运行的变量

### 语法

```dockerfile
ENV <key>=<value>
ENV <key1>=<value1> <key2>=<value2>
ENV <key> <value>   # 旧写法，等号被省略；不推荐
```

例子：

```dockerfile
FROM ubuntu:22.04
ENV APP_HOME=/opt/app \
    APP_ENV=production
RUN echo "$APP_HOME - $APP_ENV"
```

### 同时作用于构建期与运行时

ENV 会：

1. 立刻作为环境变量注入到当前及之后所有 `RUN` 的 shell；
2. **写入镜像元数据**，容器启动时也会作为默认环境变量存在。

```bash
docker run --rm demo sh -c 'echo "$APP_HOME"'
# /opt/app
```

`docker inspect` 也能看到：

```bash
docker inspect demo | jq '.[0].Config.Env'
# ["PATH=...", "APP_HOME=/opt/app", "APP_ENV=production"]
```

### 覆盖方式

- **构建期**：后声明的 ENV 覆盖前面同名的 ENV。
- **运行时**：`docker run -e APP_ENV=staging` 或 Kubernetes 里的 `env:` 都能覆盖。
- **在同一条 RUN 内**：可以临时导出但只对当前 RUN 生效，不影响后续层。

```dockerfile
ENV LOG_LEVEL=info
RUN LOG_LEVEL=debug some-cmd    # 只影响这一条 RUN
RUN echo "$LOG_LEVEL"            # 仍是 info
```

### 生命周期

一旦用 ENV 写进镜像，就随镜像走。除非后续层显式 `ENV X=` 覆盖成空，或者在运行时用 `-e X=` 覆盖，否则一直存在。

这就是 ENV 与 ARG 的分水岭：**ENV 是"打算带到运行时"的变量，ARG 是"只在构建期使用"的变量。**

### ENV 影响构建结果的方式

因为 ENV 的值会保留到运行时，所以它有些副作用要注意：

- `ENV PATH=/opt/venv/bin:$PATH`：合适，容器启动就能用虚拟环境。
- `ENV HTTP_PROXY=http://proxy:8080`：不合适——代理配置会跟着镜像跑到没有该代理的环境里，导致运行时网络请求失败。这类"只在构建期用"的东西应该走 ARG 或预定义 ARG。

---

## 三、ARG 与 ENV 的组合与顺序

### 常见组合：把构建参数固化到运行时

想让用户可以在构建时传入一个版本号，同时让容器内也能读到它：

```dockerfile
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
```

- ARG 决定构建期的默认值和可覆盖能力（`--build-arg APP_VERSION=1.2.3`）；
- ENV 把这个值"固化"进镜像，运行时读得到。

这是 Dockerfile 里非常常见的模式。

### 同名的 ARG 与 ENV：ENV 优先

如果同一个 stage 里同名的 ARG 和 ENV 都存在，**后声明的那个决定当前上下文，但 ENV 一旦声明就会持续覆盖同名 ARG**。看这个例子：

```dockerfile
FROM ubuntu:22.04
ARG PIP_CONSTRAINT=/tmp/build.txt
ENV PIP_CONSTRAINT=/etc/runtime.txt
RUN echo "$PIP_CONSTRAINT"        # /etc/runtime.txt
```

RUN 看到的是 ENV 的值。如果构建期想临时用 ARG 的默认值，要在命令里显式指定：

```dockerfile
ARG PIP_CONSTRAINT_BUILD=/tmp/build.txt
ENV PIP_CONSTRAINT=/etc/runtime.txt
RUN PIP_CONSTRAINT="$PIP_CONSTRAINT_BUILD" pip install some-pkg
```

或者更清楚地——**用两个不同名字**，避免歧义。

### 变量替换发生在什么时候

`${VAR}` 的替换是 Dockerfile 解析阶段完成的，那时能拿到的值取决于该指令位置之前已经声明的 ARG / ENV。所以顺序至关重要：

```dockerfile
ENV APP_HOME=/opt/app
COPY entrypoint.sh ${APP_HOME}/    # OK：APP_HOME 已经声明

COPY entrypoint.sh ${DATA_HOME}/   # 出错：DATA_HOME 从未声明，替换为空
ENV DATA_HOME=/opt/data            # 再声明也来不及了
```

---

## 四、案例：`ARG PIP_CONSTRAINT` vs `ENV PIP_CONSTRAINT`

这是一份真实项目里的 Dockerfile 片段，同一个变量名 `PIP_CONSTRAINT` 在文件的两个位置分别以 `ARG` 和 `ENV` 出现：

**开头附近：**

```dockerfile
COPY pip-constraints-default.txt /tmp/pip-constraints-default.txt
ARG PIP_CONSTRAINT=/tmp/pip-constraints-default.txt

# 之后是几十条 RUN pip install ...
RUN pip install numpy==1.24.0
RUN pip install torch==2.6.0+cu126
...
```

**末尾附近：**

```dockerfile
# 单独约束运行时 Cython 版本为 2.x
RUN printf 'cython<3\n' > /etc/pip-constraints-runtime.txt
ENV PIP_CONSTRAINT=/etc/pip-constraints-runtime.txt
```

这两次出现看似矛盾，其实在做两件完全不同的事情。要理解这一点，先要知道 pip 认这个环境变量：

> pip 会读取 `PIP_CONSTRAINT` 环境变量，把它指向的文件作为 `--constraint` 参数，用于**限定传递依赖的版本**，但不会主动安装约束文件里列出的包。

有了这个前提，两次出现的意图就清楚了。

### 第 1 次：`ARG PIP_CONSTRAINT`

意图：**在整个构建过程中，让每一条 `RUN pip install ...` 自动应用同一份约束文件，锁死传递依赖版本，提升镜像可复现性。**

为什么选 ARG 而不是 ENV：

- 项目希望这份约束**只在构建期生效**。构建完成后，用户在容器里 `pip install xxx` 应该走正常的依赖解析，不受这份构建期约束文件影响。
- ARG 天然满足这一点：BuildKit 把它注入到 RUN 的 shell 环境里，pip 读得到，但它不会写入镜像元数据，容器启动时 `PIP_CONSTRAINT` 就是空的。
- 同时 ARG 支持 `--build-arg PIP_CONSTRAINT=...` 由 CI 覆盖，比 ENV 更灵活。

用 ENV 会出什么问题？看下面这种反例：

```dockerfile
COPY pip-constraints-default.txt /tmp/pip-constraints-default.txt
ENV PIP_CONSTRAINT=/tmp/pip-constraints-default.txt
```

构建期一样能生效，但 `/tmp/pip-constraints-default.txt` 这个路径和文件都会跟着镜像走到运行时。用户运行时 `pip install anything`，pip 会尝试打开这个文件；文件在（因为写进了镜像层），但内容是构建期锁定的一堆传递依赖版本，会**不加提示地约束用户的运行时安装**，甚至可能导致他们装不上一个新包却看不明白为什么。这种"泄漏"是隐蔽的、难排查的。

### 第 2 次：`ENV PIP_CONSTRAINT`

意图：**给容器运行时的 `pip install` 提供一个明确的、有意为之的约束——比如强制 `cython<3`。**

为什么选 ENV：

- 这条约束需要**在运行时生效**。用户在容器里装东西时，希望 pip 自动读到它。
- ENV 写进镜像元数据，容器启动时环境里就有 `PIP_CONSTRAINT=/etc/pip-constraints-runtime.txt`。
- 内容与构建期完全不同，只有一行 `cython<3`，作用是"允许你装东西，但别把 Cython 升到 3.x，会破坏兼容性"。

### 两次出现的关系

关键在于 **ENV 出现在 ARG 之后，并且它们指向的是两份不同的文件**。回顾一下作用域：

- 从 `ARG PIP_CONSTRAINT=/tmp/pip-constraints-default.txt` 到 `ENV PIP_CONSTRAINT=/etc/pip-constraints-runtime.txt` 之间的所有 RUN——受**构建期**约束文件影响。
- `ENV PIP_CONSTRAINT=...` 之后的所有 RUN——受**运行时**约束文件影响（也就是那份只有 `cython<3` 的文件）。
- 容器运行时——只看得到 ENV，也就是运行时约束文件。

这里有一个容易忽视的细节：ENV 一旦声明，会**同时改变从这一行开始的构建期行为**。也就是说，紧跟着 `ENV PIP_CONSTRAINT=/etc/pip-constraints-runtime.txt` 的那些 `RUN pip install ...` 也会切换到运行时约束文件。看一下实际的排布：

```dockerfile
# ...大量 RUN pip install（用构建期约束）
RUN printf 'cython<3\n' > /etc/pip-constraints-runtime.txt
ENV PIP_CONSTRAINT=/etc/pip-constraints-runtime.txt
# 这之后基本没有 pip install 了，或者剩下的 pip install 明确希望只受 cython<3 约束
```

作者显然是有意让 ENV 出现在几乎所有 `pip install` 之后。如果不小心把 ENV 提前，就会让本该受"构建期完整约束"约束的安装步骤，改成只受"运行时 `cython<3`"约束——依赖解析结果可能就变了。

### 表格对照

| 维度 | `ARG PIP_CONSTRAINT` | `ENV PIP_CONSTRAINT` |
|---|---|---|
| 生效阶段 | 只在构建期 | 构建期 + 运行时 |
| 是否写入镜像元数据 | 否 | 是（`docker inspect` 可见） |
| 指向的约束文件 | 构建期锁定所有传递依赖 | 运行时最小化约束（仅 `cython<3`） |
| 是否影响用户在容器里的 `pip install` | 否 | 是 |
| CI 覆盖方式 | `--build-arg` | `docker run -e` 或 K8s `env:` |
| 目的 | 提升镜像可复现性 | 保护关键依赖不被运行时破坏 |

---

## 五、常见误区与实战建议

### 误区 1：以为 ARG 能带到运行时

```dockerfile
ARG APP_VERSION=1.2.3
# ...没有 ENV APP_VERSION...
CMD ["sh", "-c", "echo $APP_VERSION"]
```

容器里 `APP_VERSION` 是空的。要么加 `ENV APP_VERSION=${APP_VERSION}` 固化，要么把值写到文件里由应用读取。

### 误区 2：以为 ARG 值也进 `docker inspect`

不进。要看构建时的 ARG 值，只能通过：

```bash
docker history --no-trunc <image>
```

或者在构建时用 `ENV` 固化关键值。

### 误区 3：多阶段构建拿不到值

```dockerfile
FROM ubuntu:22.04 AS builder
ARG COMMIT=unknown
RUN echo "$COMMIT" > /tmp/commit

FROM ubuntu:22.04 AS runtime
# 直接用 $COMMIT 会拿到空值
COPY --from=builder /tmp/commit /etc/commit    # 用文件桥接
# 或者在这个 stage 里再声明：
ARG COMMIT
RUN echo "$COMMIT"
```

### 误区 4：ARG 覆盖 ENV 不成功

```dockerfile
ENV LEVEL=info
ARG LEVEL=debug        # 无效！同名 ENV 已存在
RUN echo "$LEVEL"      # info
```

同名情况下 ENV 优先。要么改名，要么在 RUN 里显式导出。

### 误区 5：把频繁变化的 ARG 放在前面

```dockerfile
FROM ubuntu:22.04
ARG BUILD_TIME
RUN echo "$BUILD_TIME" > /etc/build_time    # 一变就打穿缓存
RUN apt-get update && apt-get install -y ...    # 每次都要重装
```

改成：

```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y ...    # 稳定层先做
ARG BUILD_TIME
RUN echo "$BUILD_TIME" > /etc/build_time         # 频繁变化的放最后
```

### 误区 6：用 ARG 传密钥

前面提过，`docker history` 能看到 ARG。密钥应该用 BuildKit secret，不要用 ARG。

### 误区 7：以为 ENV 只能一行一个

`ENV KEY=VALUE` 支持一行多个：

```dockerfile
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Shanghai
```

比多条 `ENV` 更省一层，也更清楚地表达"这些变量属于一组"。

---

## 六、决策清单

写 Dockerfile 需要一个变量时，用下面这个流程决定用什么：

1. **它是密钥吗？** 是 → BuildKit secret，不是继续。
2. **需要在容器运行时读到吗？** 是 → `ENV`，可以配合 `ARG` 做默认值。
3. **只在构建期使用，不想污染运行时？** → `ARG`。
4. **希望构建时可覆盖、运行时也可读？** → `ARG X` + `ENV X=${X}`。
5. **想让每个 stage 都能用？** → 每个 stage 都重新 `ARG`，或用文件桥接。
6. **频繁变化？** → 放在 Dockerfile 靠后位置，保护前面的缓存。

回到本文开头 `PIP_CONSTRAINT` 的例子，把它套进这个清单：

- 构建期用 → `ARG`；
- 运行时也要用，但内容不同、目的不同 → 另外声明 `ENV`，指向不同文件；
- 结果就是同名变量在同一份 Dockerfile 里前后各出现一次，各司其职。

---

## 小结

一句话记住：**ARG 是"构建阶段的旋钮"，用完即弃；ENV 是"镜像内建的环境"，随镜像走。同名混用时后声明的 ENV 会遮蔽 ARG，密钥两者都别用。**

对照到 `PIP_CONSTRAINT` 的具体场景：`ARG PIP_CONSTRAINT` 是给构建脚本用的隐式约束旋钮，构建完就消失；`ENV PIP_CONSTRAINT` 是给容器里未来的 `pip install` 用的运行时护栏，随镜像发布。两者指向的文件、内容和用途都不同——不是重复，是分工。
