# Dockerfile 中镜像层是如何计算的

写 Dockerfile 时，经常会听到几句建议：

- 少写几条 `RUN`，减少镜像层。
- 把 `COPY requirements.txt` 放在 `COPY . .` 前面，方便缓存。
- 删除临时文件要放在同一个 `RUN` 里，否则镜像不会变小。

这些建议都和 Docker 镜像层有关。但“层是怎么计算的”这件事，很多时候容易被讲得很模糊：是不是 Dockerfile 每一行都是一层？`ENV` 会不会生成层？删掉文件为什么镜像大小还在？缓存命中到底看什么？

这篇把 Dockerfile 里的 layer 计算逻辑拆开讲清楚。

## 一、先区分两个概念：镜像层和构建缓存

Docker 构建时有两个容易混淆的东西：

1. **镜像层（image layer）**：最终镜像里真正保存的文件系统差异。
2. **构建缓存（build cache）**：构建过程中用来判断某一步能不能复用旧结果的缓存记录。

它们相关，但不是一回事。

镜像层关心的是：

> 这一条构建步骤相比上一层，文件系统发生了什么变化？

构建缓存关心的是：

> 这一条构建步骤的输入有没有变化？如果没变化，能不能直接复用上次构建结果？

所以看 Dockerfile 的 layer，不只是数行数，而是要看每条指令是否会改变文件系统，以及 Docker 如何记录这些变化。

## 二、哪些 Dockerfile 指令会产生文件系统层

通常可以这样理解：

| 指令 | 是否通常产生文件系统层 | 说明 |
|---|---|---|
| `FROM` | 引入基础镜像已有层 | 不是新建一层，而是继承 base image 的层 |
| `RUN` | 是 | 在容器里执行命令，记录命令造成的文件变化 |
| `COPY` | 是 | 把构建上下文里的文件复制进镜像 |
| `ADD` | 是 | 类似 `COPY`，额外支持 URL、自动解压 tar |
| `ENV` | 通常不产生文件系统层 | 修改镜像配置，不直接改文件系统 |
| `LABEL` | 通常不产生文件系统层 | 修改镜像元数据 |
| `WORKDIR` | 通常不产生文件系统层 | 修改默认工作目录；目录不存在时可能表现为文件系统变化，具体看构建器实现 |
| `USER` | 否 | 修改默认运行用户 |
| `EXPOSE` | 否 | 声明端口元数据 |
| `CMD` / `ENTRYPOINT` | 否 | 修改容器默认启动命令 |
| `ARG` | 否 | 构建参数，本身不进最终镜像配置，除非被后续指令使用 |

最需要关注的是三类：

```dockerfile
RUN ...
COPY ...
ADD ...
```

它们通常会产生新的文件系统 diff，也就是我们平时说的“新增一层”。

不过现代 Docker 默认使用 BuildKit，内部表现会比老版本更聪明；某些只改配置的指令会记录在镜像 history 里，但不会生成实际文件系统层。日常优化时不用纠结这些细节，只要记住：真正影响文件系统体积的，主要是 `RUN`、`COPY`、`ADD`。

## 三、一层到底保存了什么

Docker 镜像不是每一层都保存一份完整文件系统，而是保存“相对上一层的差异”。

比如有这样一个 Dockerfile：

```dockerfile
FROM debian:12

RUN echo "hello" > /app/a.txt
RUN echo "world" > /app/b.txt
RUN rm /app/a.txt
```

可以粗略理解成：

```text
base layers: debian:12 原有文件
layer 1: 新增 /app/a.txt
layer 2: 新增 /app/b.txt
layer 3: 标记 /app/a.txt 被删除
```

第三层不是把第一层里的 `a.txt` 真的抹掉，而是在新层里记录一个“删除标记”。最终容器运行时，把这些层从下到上叠起来看，`/app/a.txt` 确实不存在了。

但第一层里曾经写入的 `a.txt` 内容还在镜像历史层里。

这就是为什么下面这种写法通常不会让镜像真正变小：

```dockerfile
RUN apt-get update
RUN apt-get install -y build-essential
RUN rm -rf /var/lib/apt/lists/*
```

`apt-get update` 产生的索引文件已经进入前面的层了，后面再删，只是在新层里记录“这些文件不可见”，并没有让前面那层变小。

更好的写法是把安装和清理放到同一个 `RUN`：

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
```

这样这一层最终提交时，临时索引文件已经被删除，不会进入该层的最终 diff。

## 四、镜像大小是怎么叠加出来的

镜像大小可以从两个角度看：

1. **本地解压后的大小**：镜像层在本地 Docker 存储里的展开大小。
2. **推送/拉取时的大小**：镜像层压缩后在 registry 里传输的大小。

同一个镜像，`docker images`、`docker history`、registry 页面上显示的大小可能不完全一样，原因就在这里：有的看解压后大小，有的看压缩后大小，有的还会复用本地已有层。

但核心逻辑一致：

> 镜像大小大致等于基础镜像层 + 你在 Dockerfile 中新增的文件系统 diff 层。

如果两个镜像共享同一个基础镜像层，本地只需要存一份；但单独看某个镜像时，它仍然会把这些基础层算作这个镜像可用文件系统的一部分。

可以用下面命令查看层历史：

```bash
docker history <image>
```

输出里会看到每一步对应的 `CREATED BY` 和 `SIZE`。这对排查“到底是哪一步把镜像变大了”很有用。

也可以用：

```bash
docker image inspect <image>
```

看更底层的 `RootFS.Layers` 信息。这里列出来的是镜像层的 digest，能帮助你理解镜像由哪些层组成。

## 五、缓存命中是怎么计算的

构建缓存的判断逻辑可以简单理解为：

> 当前指令 + 上一层结果 + 相关输入，没有变化，就可以复用缓存。

不同指令的“相关输入”不一样。

### 1. `RUN` 的缓存

例如：

```dockerfile
RUN pip install -r requirements.txt
```

Docker 判断这一步能不能用缓存时，重点看：

- 上一层镜像状态有没有变化；
- `RUN pip install -r requirements.txt` 这条指令文本有没有变化；
- 参与构建的参数、环境等输入有没有变化。

容易误解的一点是：Docker 不会自动理解 `pip install -r requirements.txt` 里面读取了什么文件。它只知道这条 `RUN` 命令本身，以及这条命令执行前的文件系统状态。

所以 Dockerfile 通常写成：

```dockerfile
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
```

这样只要 `requirements.txt` 没变，`pip install` 这一层就有机会复用缓存；业务代码变了，只会影响后面的 `COPY . .`。

如果反过来写：

```dockerfile
COPY . .
RUN pip install -r requirements.txt
```

任何一个业务代码文件变化，都会让 `COPY . .` 这一层变化，进而导致后面的 `RUN pip install` 缓存失效。

### 2. `COPY` / `ADD` 的缓存

`COPY` 和 `ADD` 的缓存会看被复制文件的内容、路径等信息。

例如：

```dockerfile
COPY requirements.txt .
```

只要 `requirements.txt` 内容没变，这一层就可能命中缓存。

但如果写成：

```dockerfile
COPY . .
```

那么构建上下文里任何没被 `.dockerignore` 排除的文件变化，都可能影响这一层缓存。

所以 `.dockerignore` 很重要。比如这些内容通常不应该进入构建上下文：

```text
.git
__pycache__
.pytest_cache
node_modules
dist
build
*.log
```

它们不只是让上下文变大，也会让缓存更容易失效。

### 3. `ARG` 和 `ENV` 对缓存的影响

`ARG` 本身不产生文件系统层，但如果后面的指令用到了它，就会影响缓存。

```dockerfile
ARG APP_VERSION
RUN echo "$APP_VERSION" > /app/version.txt
```

`APP_VERSION` 变了，`RUN` 的结果当然也要重新计算。

`ENV` 会进入镜像配置，也会影响后续命令运行时看到的环境变量，因此也可能影响后续缓存。

```dockerfile
ENV PIP_INDEX_URL=https://example.com/simple
RUN pip install -r requirements.txt
```

如果 `PIP_INDEX_URL` 变了，`pip install` 的结果可能不同，缓存就不应该继续复用。

## 六、为什么合并 RUN 可以减少层，但不是越少越好

很多人看到“每个 `RUN` 会产生一层”，就会把所有命令都塞进一个巨大的 `RUN`：

```dockerfile
RUN apt-get update \
    && apt-get install -y curl git build-essential python3 python3-pip \
    && pip install -r requirements.txt \
    && npm install \
    && rm -rf /var/lib/apt/lists/*
```

这样确实减少了层数，但不一定更好。

因为缓存粒度也变粗了。只要其中一个小步骤变化，整条 `RUN` 都要重新执行。

更实用的原则是：

> 把强相关、需要一起清理的命令合并；把变化频率不同的步骤拆开。

比如系统依赖和 Python 依赖可以分开：

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
```

这样：

- apt 索引文件不会残留到镜像层里；
- `requirements.txt` 不变时，Python 依赖层可以复用；
- 业务代码变化时，不会重新安装系统依赖和 Python 依赖。

这比单纯追求“层数最少”更有价值。

## 七、多阶段构建中的层怎么算

多阶段构建里，每个 `FROM` 都会开启一个新的构建阶段：

```dockerfile
FROM golang:1.22 AS builder
WORKDIR /src
COPY . .
RUN go build -o app .

FROM debian:12-slim
COPY --from=builder /src/app /usr/local/bin/app
CMD ["app"]
```

最终镜像只包含最后一个阶段的基础层，以及最后阶段产生的层。

上面例子里：

- `golang:1.22` 的巨大编译环境不会进入最终镜像；
- `builder` 阶段编译出来的 `/src/app` 会通过 `COPY --from=builder` 复制到最终镜像；
- 最终镜像只需要 `debian:12-slim` + 应用二进制文件。

这就是多阶段构建能显著减少镜像体积的原因：不是“删除了编译环境”，而是最终镜像从一开始就没有继承编译阶段的层。

## 八、几个常见误区

### 误区一：Dockerfile 每一行都是一层

不准确。

`RUN`、`COPY`、`ADD` 通常产生文件系统层；`ENV`、`CMD`、`EXPOSE` 这类主要修改配置或元数据，不一定产生实际文件系统层。

### 误区二：后面 `rm` 了，镜像就会变小

不一定。

如果文件是在前一层创建的，后一层删除只会让它在最终容器里不可见，不会让前一层体积消失。安装临时依赖、下载临时文件、清理 apt 缓存，最好放在同一个 `RUN` 里完成。

### 误区三：层数越少越好

不绝对。

层数太多会让镜像历史复杂，但层数太少会让缓存粒度变粗。真正要优化的是：

- 镜像体积；
- 构建速度；
- 缓存命中率；
- Dockerfile 可读性。

这几个目标要一起平衡。

### 误区四：`docker history` 看到的大小就是文件真实大小

也不完全准确。

`docker history` 很适合定位哪一步引入了大量内容，但它显示的是镜像历史视角下的层大小。实际拉取、推送、本地存储时，还会受到压缩、层复用、存储驱动等因素影响。

## 九、推荐的 Dockerfile 写法

以 Python 项目为例，一个比较合理的结构是：

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]
```

这里的层设计是有意的：

- `FROM` 选择尽量小且明确版本的基础镜像；
- 系统依赖安装和 apt 清理放在同一个 `RUN`；
- 先复制 `requirements.txt`，让 Python 依赖层尽量复用缓存；
- 最后再复制业务代码，避免代码小改动导致依赖重装；
- `pip install` 使用 `--no-cache-dir`，避免 pip 下载缓存进入镜像。

如果项目需要编译产物，还可以进一步用多阶段构建，把编译工具留在 builder 阶段，只把运行所需文件复制到最终镜像。

## 十、小结

Dockerfile 中层的计算，可以抓住三句话：

1. 镜像层保存的是“相对上一层的文件系统差异”，不是完整文件系统快照。
2. `RUN`、`COPY`、`ADD` 通常会产生实际文件系统层；配置类指令更多是修改镜像元数据。
3. 构建缓存按“上一层结果 + 当前指令 + 相关输入”判断，指令顺序会直接影响缓存命中率。

写 Dockerfile 时，不要只机械地数层数。更重要的是把变化频率不同的内容拆开，把需要一起清理的内容放在同一层，并用 `.dockerignore` 控制构建上下文。这样镜像既不会无谓变大，构建速度也更稳定。
