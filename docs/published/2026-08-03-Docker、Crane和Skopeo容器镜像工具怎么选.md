# Docker、Crane 和 Skopeo：容器镜像工具怎么选

平时提到容器镜像，大多数人首先想到的是 Docker。构建镜像用 `docker build`，下载镜像用 `docker pull`，运行容器用 `docker run`，似乎一套 Docker 命令就能完成所有工作。

但到了 CI/CD、镜像同步和私有仓库管理场景，经常会遇到一些更具体的问题：

- 只想查看远端镜像信息，为什么还要先把整个镜像拉到本地？
- 把镜像从一个仓库复制到另一个仓库，能不能不经过本地 Docker daemon？
- CI 节点不允许启动特权容器，也没有 Docker daemon，怎样操作镜像？
- 怎样复制一个多架构镜像，而不是只复制当前机器对应的架构？
- 怎样在 `docker://`、OCI 目录和镜像归档文件之间转换？

这时就会遇到另外两个工具：Crane 和 Skopeo。

它们都能操作容器镜像，但定位并不相同。最简单的理解是：

- **Docker**：完整的容器开发和运行平台，既管镜像，也管容器。
- **Crane**：面向容器 Registry 的轻量级命令行工具，擅长直接检查和操作远端镜像。
- **Skopeo**：专门处理容器镜像及其存储格式的工具，擅长跨仓库、跨格式复制与检查。

如果只是日常构建和运行容器，Docker 通常就够了；如果工作重点是“仓库里的镜像”，Crane 和 Skopeo 往往更直接。

## 一、先分清几个对象

在比较工具之前，先区分镜像操作中几个经常混在一起的对象。

### 1. 本地镜像

执行下面的命令：

```bash
docker pull nginx:1.27
```

Docker 会从远端 Registry 下载镜像层，并把镜像保存到 Docker daemon 管理的本地镜像存储中。之后执行 `docker image inspect nginx:1.27`，检查的是本地镜像。

### 2. 远端镜像

`registry.example.com/team/app:1.0` 表示 Registry 中的一个镜像引用。Crane 和 Skopeo 可以直接访问这个引用，不需要先把所有镜像层拉进 Docker 的本地存储。

### 3. Tag 和 Digest

Tag 是便于人阅读的名字，例如：

```text
nginx:1.27
```

同一个 tag 可以被重新指向另一份镜像，因此它不一定永远代表相同内容。

Digest 是由内容计算出来的不可变标识，例如：

```text
nginx@sha256:0123456789abcdef...
```

发布、审计和生产部署时，如果要求精确复现，使用 digest 比只使用 tag 更可靠。

### 4. Registry、Repository 和 Image

以下面的引用为例：

```text
registry.example.com/team/app:1.0
```

- `registry.example.com` 是 Registry 地址；
- `team/app` 是 Repository；
- `1.0` 是 tag；
- 整体表示一个具体的镜像引用。

Crane 和 Skopeo 的很多命令直接对 Registry 发起 HTTP API 请求，而 Docker 通常会通过 Docker daemon 管理本地镜像、网络和认证。

## 二、Docker 是什么，适合做什么

Docker 是一套完整的容器工具链。它不仅能处理镜像，还能构建镜像、创建容器、管理网络和数据卷，并通过 Compose 编排多个服务。

Docker 最常用的场景包括：

- 根据 Dockerfile 构建镜像；
- 在开发机上启动和调试容器；
- 查看容器日志、端口和资源占用；
- 使用 Docker Compose 启动一组相关服务；
- 将本地构建结果推送到镜像仓库。

### 1. 安装

桌面开发环境可以安装 Docker Desktop；Linux 服务器通常安装 Docker Engine。不同系统的安装步骤差异较大，建议按照 Docker 官方文档添加软件源并安装，不要长期依赖来源不明的一键安装脚本。

安装后确认版本：

```bash
docker version
```

如果只能看到客户端信息，而服务端连接失败，通常说明 Docker daemon 没有启动，或者当前用户无权访问 Docker socket。

### 2. 构建镜像

假设当前目录存在 Dockerfile：

```bash
docker build -t my-app:1.0 .
```

查看本地镜像：

```bash
docker image ls
```

### 3. 运行和调试容器

```bash
docker run -d --name my-app -p 8080:8080 my-app:1.0
docker logs -f my-app
docker exec -it my-app sh
```

这是 Docker 最明显的优势：Crane 和 Skopeo 都不能替代 `docker run`，因为它们不是容器运行时。

### 4. 推送镜像

先登录仓库：

```bash
docker login registry.example.com
```

重新打 tag 并推送：

```bash
docker tag my-app:1.0 registry.example.com/team/my-app:1.0
docker push registry.example.com/team/my-app:1.0
```

### 5. 用 Docker 跨仓库复制镜像

Docker 也能复制镜像，但通常需要经过“拉取、打 tag、推送”三个步骤：

```bash
docker pull source.example.com/team/app:1.0
docker tag source.example.com/team/app:1.0 target.example.com/team/app:1.0
docker push target.example.com/team/app:1.0
```

这种方式容易理解，也方便在复制后启动容器验证。但它会占用本地镜像存储，依赖 Docker daemon，而且处理多架构镜像时要格外小心：普通 `docker pull` 通常只拉取当前平台对应的镜像，而不是完整的多架构索引。

## 三、Crane 是什么，适合做什么

Crane 是 Google `go-containerregistry` 项目提供的命令行工具。它主要面向 OCI/Docker Registry，可以直接读取、复制、标记和删除远端镜像。

Crane 的特点是轻量、命令直观、适合脚本化。它不需要 Docker daemon，因此很适合 CI/CD 流水线和只有最小运行环境的管理节点。

Crane 最常用的场景包括：

- 快速查询远端镜像 digest；
- 查看 manifest 或镜像 config；
- 不落入 Docker 本地存储，直接跨仓库复制镜像；
- 给远端镜像增加新 tag；
- 列出仓库 tag；
- 删除 Registry 中的镜像引用。

### 1. 安装

macOS 或 Linux 使用 Homebrew：

```bash
brew install crane
```

已经安装 Go 时也可以执行：

```bash
go install github.com/google/go-containerregistry/cmd/crane@latest
```

生产环境和 CI 中建议固定具体版本，避免 `latest` 变化导致流水线行为漂移。

检查安装结果：

```bash
crane version
```

### 2. 登录私有仓库

交互式登录：

```bash
crane auth login registry.example.com -u my-user
```

在 CI 中可以从标准输入读取密码：

```bash
printf '%s' "$REGISTRY_PASSWORD" | crane auth login registry.example.com \
  -u "$REGISTRY_USER" --password-stdin
```

不要把真实密码直接写在命令参数、脚本或流水线日志中。

### 3. 查询远端镜像 digest

```bash
crane digest registry.example.com/team/app:1.0
```

这个命令不需要把完整镜像下载到本地，非常适合在部署前确认 tag 当前指向哪份内容。

### 4. 查看 manifest 和 config

查看镜像 manifest：

```bash
crane manifest registry.example.com/team/app:1.0 | jq .
```

查看镜像 config：

```bash
crane config registry.example.com/team/app:1.0 | jq .
```

两者关注的内容不同：

- manifest 记录镜像层、config digest、媒体类型等信息；
- config 记录架构、环境变量、入口命令、工作目录、rootfs diff ID 等信息。

### 5. 列出仓库中的 tag

```bash
crane ls registry.example.com/team/app
```

脚本中可以配合排序或筛选：

```bash
crane ls registry.example.com/team/app | sort -V
```

注意，tag 本身不一定符合语义化版本，简单排序不能替代正式的版本保留策略。

### 6. 跨仓库复制镜像

```bash
crane copy \
  source.example.com/team/app:1.0 \
  target.example.com/team/app:1.0
```

整个过程不需要先 `docker pull`，也不会把镜像导入 Docker daemon 的本地存储。

如果两个仓库中已经存在相同 blob，Registry 可以通过内容寻址复用已有层，实际传输量可能小于镜像完整大小。

### 7. 给远端镜像增加 tag

```bash
crane tag registry.example.com/team/app:1.0 stable
```

这相当于让 `stable` 指向 `1.0` 对应的镜像内容。tag 可以移动，所以不要把 `stable`、`latest` 当成不可变版本标识。

### 8. 删除远端镜像

```bash
crane delete registry.example.com/team/app:old
```

这是对远端 Registry 的删除操作，不是删除本地缓存。很多 Registry 的底层删除接口实际按 manifest digest 工作；如果多个 tag 指向同一个 digest，删除结果可能不只是移除眼前这个 tag。不同 Registry 对 tag、manifest 和垃圾回收的实现也不同：命令成功不一定代表相关 blob 会立刻释放磁盘空间。执行前应先确认仓库的引用关系、保留策略和回收机制。

## 四、Skopeo 是什么，适合做什么

Skopeo 是 Containers 项目中的容器镜像工具，与 Podman、Buildah 使用相同的底层镜像库。它也不要求 Docker daemon，核心能力是检查、复制、同步和删除镜像。

Skopeo 的一个显著特点是“传输协议”明确。镜像引用前通常会带上 transport，例如：

```text
docker://registry.example.com/team/app:1.0
docker-archive:/tmp/app.tar
oci:/tmp/app-oci:1.0
dir:/tmp/app-dir
```

这里的 `docker://` 表示 Registry 协议，不代表必须安装或启动 Docker。

Skopeo 最常用的场景包括：

- 检查远端镜像元数据；
- 在不同 Registry 之间复制镜像；
- 在 Registry、OCI layout、目录和归档文件之间转换；
- 完整复制多架构镜像；
- 批量同步仓库或命名空间；
- 配合容器镜像签名和信任策略进行校验。

### 1. 安装

Debian 或 Ubuntu：

```bash
sudo apt-get update
sudo apt-get install -y skopeo
```

Fedora、RHEL 系发行版：

```bash
sudo dnf install -y skopeo
```

macOS 使用 Homebrew：

```bash
brew install skopeo
```

确认版本：

```bash
skopeo --version
```

发行版软件仓库中的 Skopeo 版本可能落后于上游。使用某个新参数前，应先查看当前版本的 `skopeo <subcommand> --help`。

### 2. 登录私有仓库

```bash
skopeo login registry.example.com --username my-user
```

CI 中同样可以通过标准输入传入密码：

```bash
printf '%s' "$REGISTRY_PASSWORD" | skopeo login registry.example.com \
  --username "$REGISTRY_USER" --password-stdin
```

Docker、Crane 和 Skopeo 默认使用或查找的认证文件位置可能不同。自动化环境中如果出现“Docker 已登录，但 Skopeo 仍然未认证”，可以使用 `--authfile` 显式指定认证文件，并检查文件权限。

### 3. 检查远端镜像

```bash
skopeo inspect docker://registry.example.com/team/app:1.0
```

只查看原始 manifest：

```bash
skopeo inspect --raw docker://registry.example.com/team/app:1.0 | jq .
```

普通 `inspect` 输出的是整理后的 JSON，适合查看 digest、架构、系统、tag、环境变量和层信息；`--raw` 更适合检查 media type、多架构 manifest list 或 OCI index 的原始结构。

### 4. 跨仓库复制镜像

```bash
skopeo copy \
  docker://source.example.com/team/app:1.0 \
  docker://target.example.com/team/app:1.0
```

复制完整的多架构镜像时，应显式加上 `--all`：

```bash
skopeo copy --all \
  docker://source.example.com/team/app:1.0 \
  docker://target.example.com/team/app:1.0
```

不加 `--all` 时，Skopeo 通常只复制与当前系统或指定平台匹配的镜像实例。源镜像同时支持 `amd64`、`arm64` 时，这一点非常重要。

### 5. 保存为离线归档

从 Registry 导出为 Docker archive：

```bash
skopeo copy \
  docker://registry.example.com/team/app:1.0 \
  docker-archive:/tmp/app-1.0.tar:team/app:1.0
```

在离线机器上导入 Docker：

```bash
docker load -i /tmp/app-1.0.tar
```

这里要区分两种常见文件：

- `docker-archive` 对应 `docker save` / `docker load` 使用的镜像归档；
- 容器文件系统 tar 通常来自 `docker export`，不包含完整镜像元数据和历史，不能当成同一种格式使用。

### 6. 转换为 OCI layout

```bash
skopeo copy \
  docker://registry.example.com/team/app:1.0 \
  oci:/tmp/app-oci:1.0
```

OCI layout 是一个标准化目录结构，适合交给支持 OCI Image Layout 的扫描器、签名工具或其他镜像处理程序。

### 7. 批量同步镜像

同步单个仓库到另一个 Registry：

```bash
skopeo sync --all \
  --src docker --dest docker \
  source.example.com/team/app \
  target.example.com/mirror
```

实际同步前应先用当前版本的帮助信息确认源、目标路径规则：

```bash
skopeo sync --help
```

`skopeo sync` 适合做私有镜像仓库镜像、定期灾备和受控网络之间的镜像同步。仓库规模较大时，还要配合 tag 白名单、保留策略和失败重试，避免无边界地复制历史镜像。

### 8. 删除远端镜像

```bash
skopeo delete docker://registry.example.com/team/app:old
```

它和 `crane delete` 类似，操作的是远端镜像引用。Registry 是否立即清理无引用 blob，仍取决于服务端实现和垃圾回收配置。

## 五、三者核心区别

| 能力 | Docker | Crane | Skopeo |
|---|---|---|---|
| 构建镜像 | 支持，`docker build` | 不负责常规 Dockerfile 构建 | 不负责构建 |
| 运行容器 | 支持，`docker run` | 不支持 | 不支持 |
| 是否依赖 Docker daemon | 通常依赖 | 不依赖 | 不依赖 |
| 直接检查远端镜像 | 能力相对分散 | 很方便 | 很方便 |
| 跨 Registry 复制 | 可做，但通常经过本地存储 | 擅长 | 擅长 |
| 多架构镜像复制 | 需选对 Buildx 等方式 | 支持处理镜像索引 | 支持，复制全部平台时用 `--all` |
| 镜像格式转换 | 不是主要用途 | 能力相对简洁 | 强项，支持多种 transport |
| 批量同步 | 需要脚本或其他工具 | 可配合脚本 | 内置 `sync` |
| 远端删除 | 普通镜像命令主要管理本地对象 | 支持 | 支持 |
| 典型定位 | 开发、构建、运行、调试 | Registry 自动化和轻量脚本 | 镜像搬运、转换、同步和策略检查 |

一句话选择：

- 需要**构建或运行容器**，选 Docker；
- 需要用简洁命令**查询、复制、打 tag、删除远端镜像**，选 Crane；
- 需要**跨格式、全架构、批量同步或更复杂的镜像传输**，选 Skopeo。

它们不是互斥关系。实际团队里很常见的组合是：开发阶段用 Docker 构建和测试，CI 阶段用 Crane 查询 digest 或复制镜像，镜像迁移和离线交付用 Skopeo。

## 六、常用场景实战

### 场景 1：CI 中确认镜像是否已经存在

构建前先查询目标 tag：

```bash
if crane digest registry.example.com/team/app:"$VERSION" >/dev/null 2>&1; then
  echo "image already exists"
else
  echo "image does not exist"
fi
```

这样不需要拉取镜像层。需要注意：认证失败、网络失败和镜像不存在都可能导致非零退出码，正式脚本应记录错误信息，不能把所有失败都简单解释为“不存在”。

### 场景 2：将测试仓库中的镜像提升到生产仓库

使用 Crane：

```bash
crane copy \
  test.example.com/team/app@sha256:<digest> \
  prod.example.com/team/app:1.0.0
```

使用 digest 作为源，可以确保提升的是已经测试过的那一份内容，而不是某个后来被覆盖的 tag。

复制后再次确认：

```bash
crane digest prod.example.com/team/app:1.0.0
```

Crane 的复制操作以保留 digest 为目标，源和目标的 digest 应当一致。如果比较结果不一致，应停止发布并检查是否选错了平台、tag 是否在复制期间被覆盖，以及工具或目标仓库是否改变了 manifest。严格的供应链流程中，不要省略复制后的校验。

### 场景 3：迁移多架构镜像

先查看源镜像是不是镜像索引：

```bash
skopeo inspect --raw docker://source.example.com/team/app:1.0 | jq .mediaType
```

再复制所有平台：

```bash
skopeo copy --all \
  docker://source.example.com/team/app:1.0 \
  docker://target.example.com/team/app:1.0
```

迁移后再次检查原始 manifest，确认 `amd64`、`arm64` 等目标平台都还存在。仅验证一个 tag 能拉取成功，并不能证明所有架构都已迁移完整。

### 场景 4：在不能运行 Docker daemon 的 CI 中操作镜像

很多 Kubernetes CI Runner 不允许启动 Docker-in-Docker，也不会挂载宿主机的 Docker socket。此时可以：

- 用 Kaniko、BuildKit 等工具负责构建；
- 用 Crane 查询 digest、增加 tag 或复制结果；
- 用 Skopeo 将结果同步到其他 Registry 或导出为指定格式。

这样可以减少对特权模式和 Docker socket 的依赖。尤其不要为了执行一次 `docker push`，就随意把宿主机 `/var/run/docker.sock` 暴露给不可信的流水线任务；拿到这个 socket 往往接近拿到宿主机的高权限控制能力。

### 场景 5：离线环境交付镜像

联网环境导出：

```bash
skopeo copy \
  docker://registry.example.com/team/app:1.0 \
  docker-archive:/tmp/app-1.0.tar:team/app:1.0
```

对归档计算校验值：

```bash
sha256sum /tmp/app-1.0.tar > /tmp/app-1.0.tar.sha256
```

文件传到离线环境后先校验：

```bash
sha256sum -c /tmp/app-1.0.tar.sha256
docker load -i /tmp/app-1.0.tar
```

文件校验值用于确认传输是否损坏，不等于完整的软件供应链签名。需要验证发布者身份时，还应使用 Cosign 等镜像签名工具和相应的验证策略。

### 场景 6：检查镜像默认启动参数

Crane 可以直接读取远端 config：

```bash
crane config registry.example.com/team/app:1.0 \
  | jq '{Entrypoint: .config.Entrypoint, Cmd: .config.Cmd, Env: .config.Env}'
```

这适合快速确认 `ENTRYPOINT`、`CMD` 和环境变量，不必为了查看几行元数据下载几个 GB 的镜像。

但镜像 config 中的环境变量是任何有权拉取镜像的人都可能读到的内容，因此不能把密码、token 和私钥写进 Dockerfile 的 `ENV` 或最终镜像层。

## 七、几个常见误区

### 1. 以为 Crane 和 Skopeo 能运行容器

不能。它们处理的是镜像和 Registry，不是容器运行时。要运行容器，仍然需要 Docker Engine、containerd、CRI-O、Podman 等工具或运行时。

### 2. 以为 `docker inspect` 默认检查远端镜像

`docker image inspect` 检查的是 Docker 本地存储中的镜像。想直接查看远端镜像，可以使用：

```bash
crane manifest registry.example.com/team/app:1.0
skopeo inspect docker://registry.example.com/team/app:1.0
docker buildx imagetools inspect registry.example.com/team/app:1.0
```

### 3. 复制多架构镜像时只复制了当前架构

这是仓库迁移中最常见的问题之一。在 amd64 机器上执行普通拉取和推送，最后可能只剩 amd64 镜像，arm64 节点部署时才暴露问题。

使用 Skopeo 时显式写 `--all`，并在复制前后检查 OCI index 或 manifest list。

### 4. 把 tag 当成不可变版本

`latest`、`stable`，甚至 `1.0.0` 都可能被重新推送。需要精确部署时使用 digest；需要禁止覆盖时，在 Registry 中开启 tag immutability。

### 5. 遇到自签名证书就长期使用 `--insecure`

Crane 和 Skopeo 都提供跳过 TLS 校验的相关选项，但它们只适合临时排障。生产环境应该把企业 CA 正确安装到信任链中，否则认证信息和镜像内容可能受到中间人攻击。

### 6. 认为删除 tag 后磁盘空间会立刻下降

Registry 通常按 digest 保存 manifest 和 blob，多个 tag 或镜像可能共享相同层。删除一个引用后，blob 也可能仍被其他镜像引用；即使已经没有引用，也往往要等 Registry 执行垃圾回收才会真正释放空间。

## 八、认证和安全建议

无论使用哪个工具，都建议遵循以下原则：

1. CI 使用短期 token 或最小权限的机器人账号，不要使用个人管理员密码。
2. 推送账号和只读账号分开，镜像检查任务不应拥有删除权限。
3. 密码通过标准输入或 CI secret 注入，不要直接出现在命令行参数和日志里。
4. 生产部署尽量锁定 digest，并保留 tag 到 digest 的审计记录。
5. 从外部仓库同步镜像后，执行漏洞扫描、许可证检查和签名验证。
6. 删除镜像前先检查保留策略、引用关系和 Registry 垃圾回收机制。

还要注意，Crane、Docker 和 Skopeo 可能共享已有认证，也可能因为运行用户、`HOME`、`XDG_RUNTIME_DIR` 或 `--authfile` 不同而读取不同文件。排查 401 或 403 时，应同时确认：

- 登录的是不是正确的 Registry 主机名和端口；
- 当前进程读取的是哪一个认证文件；
- 账号是否有目标 Repository 的 pull、push 或 delete 权限；
- Registry 前面的反向代理是否正确转发认证请求。

## 九、最终怎么选

如果工作流是“写 Dockerfile、构建镜像、在本机启动服务”，直接用 Docker，学习成本最低。

如果工作流是“在脚本中查询远端 digest、复制镜像、增加 tag、清理旧引用”，Crane 通常更轻巧，命令也更容易组合。

如果工作流涉及“完整迁移多架构镜像、批量同步仓库、导出离线包、转换 OCI 或 Docker 归档格式”，Skopeo 的能力更完整。

一个常见而实用的组合流程是：

```text
Docker / BuildKit 构建并测试镜像
              ↓
Crane 查询 digest、提升版本、增加 tag
              ↓
Skopeo 做跨环境同步、全架构迁移或离线归档
```

真正的选择标准不是“哪个工具最强”，而是当前任务究竟在操作什么：要操作容器，就选择容器平台；只操作 Registry 中的镜像，就选择更专注的镜像工具。把这个边界分清，很多原本需要拉取、打 tag、再推送的繁琐流程，都可以变成一条更清晰的命令。
