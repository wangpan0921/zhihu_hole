# Docker 入门与基本使用

## 1. Docker 是什么

Docker 是一种容器化平台，用来把应用程序及其运行依赖打包成一个标准化的“镜像”，再通过这个镜像启动一个或多个“容器”。

可以把 Docker 理解为一种轻量级的应用运行环境：应用需要的系统库、运行时、环境变量、配置文件、依赖包等都可以被写进镜像中。这样应用不再强依赖某一台机器的本地环境，而是可以在开发机、测试环境、生产服务器、CI/CD 流水线中以更一致的方式运行。

常见概念：

- 镜像：只读模板，包含应用及其依赖，例如 `python:3.11-slim`、`nginx:1.25`。
- 容器：镜像运行后的实例，可以启动、停止、删除。
- Dockerfile：构建镜像的脚本文件，描述基础镜像、依赖安装、文件拷贝、启动命令等步骤。
- 仓库：存放镜像的地方，例如 Docker Hub、阿里云镜像仓库、GitHub Container Registry。

## 2. Docker 的优势

Docker 的核心优势是环境一致性和交付标准化。

第一，减少“我这里能跑”的问题。传统部署中，开发机和服务器可能存在 Python 版本、系统库版本、环境变量、依赖包版本不一致的问题。Docker 将这些依赖固化到镜像中，使运行环境更可控。

第二，部署更方便。应用可以被构建成镜像，服务器只需要拉取镜像并启动容器，就能运行服务。升级时通常只需要替换镜像版本。

第三，隔离性更好。不同应用可以运行在不同容器中，各自拥有独立的文件系统、进程空间、网络配置和依赖环境，降低互相影响的风险。

第四，资源开销相对虚拟机更低。Docker 容器共享宿主机内核，不需要像虚拟机那样启动完整操作系统，因此启动速度快、资源占用小。

第五，适合自动化流程。Docker 很适合和 CI/CD、Kubernetes、云平台结合，用于自动构建、测试、发布和扩缩容。

## 3. Docker 常用基本指令

### 镜像相关

查看本地镜像：

```bash
docker images
```

`docker image list` 和 `docker images` 基本等价，都用于查看本地镜像。

查看本地镜像及其 digest：

```bash
docker images --digests
```

拉取镜像：

```bash
docker pull nginx:1.25
```

构建镜像：

```bash
docker build -t my-app:1.0 .
```

删除镜像：

```bash
docker rmi my-app:1.0
```

查看镜像详细信息：

```bash
docker image inspect my-app:1.0
```

### 容器相关

启动一个容器：

```bash
docker run nginx:1.25
```

后台运行并映射端口：

```bash
docker run -d --name web -p 8080:80 nginx:1.25
```

查看运行中的容器：

```bash
docker ps
```

查看所有容器，包括已停止的容器：

```bash
docker ps -a
```

停止容器：

```bash
docker stop web
```

启动已停止的容器：

```bash
docker start web
```

删除容器：

```bash
docker rm web
```

进入容器内部：

```bash
docker exec -it web sh
```

如果容器里有 bash，也可以使用：

```bash
docker exec -it web bash
```

查看容器日志：

```bash
docker logs web
```

实时查看日志：

```bash
docker logs -f web
```

查看容器资源占用：

```bash
docker stats
```

### `docker run` 和 `docker exec` 的区别

`docker run` 和 `docker exec` 都可以执行命令，但它们操作的对象不同。

`docker run` 是基于镜像创建并启动一个新的容器：

```bash
docker run --rm my-image:tag pip freeze
```

这条命令的含义是：从 `my-image:tag` 这个镜像新建一个容器，在容器里执行 `pip freeze`，执行完成后因为有 `--rm`，容器会被自动删除。

`docker exec` 是在一个已经运行中的容器里执行新命令：

```bash
docker exec -it <container_name_or_id> pip freeze
```

这条命令要求 `<container_name_or_id>` 对应的容器已经处于运行状态。它不会创建新容器，而是在现有容器环境中再启动一个进程。

简单区分：

- `docker run`：从镜像创建新容器并执行命令。
- `docker exec`：进入已有运行容器并执行命令。
- 想检查某个镜像里有什么包，常用 `docker run --rm <image> pip freeze`。
- 想检查某个正在运行的服务容器当前环境，常用 `docker exec -it <container> pip freeze`。

如果只是验证镜像构建结果，优先使用 `docker run --rm`；如果要排查线上或测试环境中某个已启动容器的实际状态，使用 `docker exec` 更合适。

### 清理相关

删除无用容器、网络、悬空镜像和构建缓存：

```bash
docker system prune
```

连未被容器使用的镜像也一起删除：

```bash
docker system prune -a
```

使用清理命令前要确认不会误删仍需要的镜像或缓存。

## 4. 编译镜像

使用 `docker build` 根据 Dockerfile 编译镜像：

```bash
docker build -t ubuntu22.04-torch2.6.0-cuda12.6-nsys25.1.1:wp-test -f Dockerfile .
```

这里几个参数的含义是：

- `-t ubuntu22.04-torch2.6.0-cuda12.6-nsys25.1.1:wp-test`：给构建出来的镜像指定名称和 tag。
- `-f Dockerfile`：指定使用当前目录下的 `Dockerfile`。
- `.`：构建上下文目录，Docker 会把这个目录中的文件作为构建上下文发送给 Docker daemon。

## 5. Docker 里 pip 包版本的确认

如果 Python 应用运行在 Docker 容器中，确认 pip 包版本通常有几种方式。

第一种是在运行中的容器里查看：

```bash
docker exec -it <container_name_or_id> pip list
```

查看某个包的详细信息：

```bash
docker exec -it <container_name_or_id> pip show requests
```

或者：

```bash
docker exec -it <container_name_or_id> python -m pip show requests
```

第二种是在临时容器中查看镜像里的依赖版本。可以用 `docker run --rm` 临时启动一个容器并执行 `pip freeze`：

```bash
docker run --rm ubuntu22.04-torch2.6.0-cuda12.6-nsys25.1.1:wp-test pip freeze
```

这条命令会基于镜像启动一个临时容器，执行完 `pip freeze` 后自动删除容器。它适合用来检查镜像内容，而不需要手动创建、进入、停止、删除容器。

也可以使用：

```bash
docker run --rm ubuntu22.04-torch2.6.0-cuda12.6-nsys25.1.1:wp-test python -m pip freeze
```

`python -m pip` 的写法能更明确地使用当前 Python 解释器对应的 pip。

同样可以查看单个包：

```bash
docker run --rm my-python-app:1.0 python -m pip show numpy
```

第三种是在构建阶段固定依赖版本，例如 `requirements.txt`：

```txt
flask==3.0.0
requests==2.31.0
numpy==1.26.4
```

Dockerfile 中安装：

```dockerfile
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
```

生产环境建议明确固定关键依赖版本，避免构建时间不同导致安装到不同版本的包。

## 6. Docker 镜像版本的确认

Docker 镜像版本通常通过 tag、镜像 ID、digest 三类信息确认。

查看本地镜像及 tag：

```bash
docker images
```

输出中常见字段包括：

- `REPOSITORY`：镜像名，例如 `nginx`。
- `TAG`：标签，例如 `1.25`、`latest`。
- `IMAGE ID`：本地镜像 ID。
- `CREATED`：镜像创建时间。
- `SIZE`：镜像大小。

查看镜像详细信息：

```bash
docker image inspect nginx:1.25
```

查看镜像 digest：

```bash
docker image inspect nginx:1.25 --format='{{index .RepoDigests 0}}'
```

也可以直接用 `--digests` 选项查看本地镜像列表的 digest：

```bash
docker images --digests
```

digest 是镜像内容的哈希标识，比 tag 更精确。因为 tag 可以被重新指向新的镜像内容，例如 `latest` 今天和下个月可能不是同一个镜像。生产环境中如果需要严格可复现，可以使用 digest：

```bash
docker pull nginx@sha256:<digest>
```

查看容器实际使用的镜像：

```bash
docker inspect <container_name_or_id> --format='{{.Config.Image}}'
```

查看容器对应的镜像 ID：

```bash
docker inspect <container_name_or_id> --format='{{.Image}}'
```

实际使用中，建议不要只依赖 `latest`，而是使用明确版本号，例如：

```dockerfile
FROM python:3.11.9-slim
```

比下面这种更可控：

```dockerfile
FROM python:latest
```

## 7. 登录仓库、打 tag 和推送镜像

构建好的镜像如果要分享给其他机器使用，通常需要推送到镜像仓库。完整流程是：登录仓库、打远端 tag、推送镜像。

### 登录镜像仓库

推送镜像前，需要先登录目标镜像仓库：

```bash
docker login --username=<your-username> <registry-host>
```

其中 `<registry-host>` 是镜像仓库地址，例如 `registry.example.com`。执行后 Docker 会提示输入密码或访问凭证。登录成功后，本机 Docker 客户端会保存认证信息，后续才能向该 registry 推送镜像。

### 给镜像打 tag

本地构建出的镜像如果要推送到远端仓库，需要使用远端仓库地址重新打 tag：

```bash
docker tag <local-image-id> <registry-host>/<namespace>/<image-name>:<tag>
```

这里 `<local-image-id>` 是本地镜像 ID，也可以替换成本地镜像名：

```bash
docker tag <local-image-name>:<local-tag> <registry-host>/<namespace>/<image-name>:<tag>
```

`docker tag` 本身不会复制镜像内容，它只是给同一个镜像增加一个新的名称引用。

### 推送镜像

打好远端 tag 后，可以推送到镜像仓库：

```bash
docker push <registry-host>/<namespace>/<image-name>:<tag>
```

推送完成后，其他机器就可以通过这个完整镜像地址拉取：

```bash
docker pull <registry-host>/<namespace>/<image-name>:<tag>
```

## 8. 单架构镜像和多架构镜像

CPU 架构决定了程序能在哪类硬件上运行。常见架构包括：

- `linux/amd64`：常见 x86_64 服务器和个人电脑。
- `linux/arm64`：Apple Silicon、部分云服务器、树莓派等 ARM 设备。
- `linux/arm/v7`：较老的 32 位 ARM 设备。

### 单架构镜像

单架构镜像只支持一种平台，例如只支持 `linux/amd64`。如果在不匹配的平台上运行，可能会报错，或者依赖模拟器导致性能下降。

适用场景：

- 只部署在固定类型服务器上，例如全部是 x86_64 Linux。
- 内部系统环境统一，不需要兼容多平台。
- 构建流程简单，镜像只面向单一运行环境。

构建单架构镜像示例：

```bash
docker build --platform linux/amd64 -t my-app:amd64 .
```

### 多架构镜像

多架构镜像不是一个单独的普通镜像，而是一个 manifest list。它在同一个镜像名和 tag 下关联多个不同架构的镜像。用户执行 `docker pull my-app:1.0` 时，Docker 会根据当前机器平台自动拉取匹配的版本。

适用场景：

- 同一个应用需要同时支持 x86 服务器和 ARM 服务器。
- 开发者使用 Apple Silicon Mac，但生产环境是 x86_64 Linux。
- 需要发布公共基础镜像或开源项目镜像。
- Kubernetes 集群中混合了不同 CPU 架构节点。

使用 `buildx` 构建并推送多架构镜像：

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/my-app:1.0 \
  --push \
  .
```

查看镜像支持的平台：

```bash
docker buildx imagetools inspect registry.example.com/my-app:1.0
```

多架构镜像的好处是使用方不需要关心自己应该拉取哪个架构的镜像，Docker 会自动选择。但构建成本更高，依赖的基础镜像、系统包、二进制文件也都需要支持对应平台。

## 9. Docker 编译过程中的 layer 概念

Docker 镜像由一层一层的 layer 组成。Dockerfile 中的大多数指令都会生成新的镜像层，例如：

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

可以粗略理解为：

- `FROM` 提供基础层。
- `WORKDIR` 设置工作目录，可能产生元数据层。
- `COPY requirements.txt .` 增加一层文件变更。
- `RUN pip install -r requirements.txt` 增加一层依赖安装结果。
- `COPY . .` 再增加一层应用代码。
- `CMD` 记录默认启动命令。

layer 的重要作用是缓存。Docker 构建镜像时，会按 Dockerfile 从上到下执行。如果某一层没有变化，Docker 可以复用之前的构建缓存，从而加快构建速度。

例如 Python 项目中，通常推荐先复制 `requirements.txt` 并安装依赖，再复制业务代码：

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

这样当只修改业务代码时，`requirements.txt` 没有变化，依赖安装层可以复用缓存，不需要每次重新安装 pip 包。

如果写成下面这样：

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir -r requirements.txt
CMD ["python", "app.py"]
```

只要任意代码文件发生变化，`COPY . .` 这一层就会失效，后面的 `pip install` 也要重新执行，构建会变慢。

layer 还有几个实践要点：

- 把变化少的步骤放前面，把变化频繁的代码复制放后面。
- 使用 `.dockerignore` 排除不需要进入镜像的文件，例如 `.git`、缓存目录、日志、测试产物。
- 合理合并 `RUN` 命令，减少无意义层数，但不要牺牲可读性。
- 使用 `--no-cache-dir` 减少 pip 缓存进入镜像。
- 构建后可用 `docker history <image>` 查看镜像层历史。

查看镜像层：

```bash
docker history my-app:1.0
```

更详细地分析镜像体积时，可以使用 `dive` 等工具查看每一层包含了哪些文件。

## 10. 一个简单完整示例

假设有一个 Python Flask 应用，目录如下：

```txt
my-app/
  app.py
  requirements.txt
  Dockerfile
  .dockerignore
```

`requirements.txt`：

```txt
flask==3.0.0
```

`app.py`：

```python
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello Docker"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

`Dockerfile`：

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

`.dockerignore`：

```txt
.git
__pycache__
*.pyc
.venv
.env
```

构建镜像：

```bash
docker build -t flask-demo:1.0 .
```

运行容器：

```bash
docker run -d --name flask-demo -p 5000:5000 flask-demo:1.0
```

查看 pip 包版本：

```bash
docker exec -it flask-demo python -m pip list
```

查看镜像信息：

```bash
docker image inspect flask-demo:1.0
```

查看镜像层：

```bash
docker history flask-demo:1.0
```

停止并删除容器：

```bash
docker stop flask-demo
docker rm flask-demo
```

## 总结

Docker 解决的核心问题是应用运行环境的标准化。通过镜像，应用和依赖可以被统一打包；通过容器，镜像可以被快速、隔离地运行；通过 tag、digest、pip 版本和 Dockerfile，可以更精确地控制应用版本；通过单架构和多架构镜像，可以适配不同硬件平台；通过 layer 和缓存机制，可以让镜像构建更高效、更可复现。

实际使用 Docker 时，最重要的习惯是：明确版本、减少环境隐式依赖、写好 Dockerfile、理解缓存层、避免滥用 `latest`，并在构建和运行阶段都能确认自己实际使用的版本。
