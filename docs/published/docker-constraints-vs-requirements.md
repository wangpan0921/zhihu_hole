# Docker 编译中 requirements 文件和 constraints 文件的区别

在 Python 项目做 Docker 镜像编译时，经常会看到两类文件：`requirements.txt` 和 `constraints.txt`。它们都会影响 `pip install` 的依赖解析，但职责完全不同：

- `requirements.txt`：声明“我要安装什么”。
- `constraints.txt`：限制“这些包最多、最少、必须用什么版本”，但它本身不会触发安装。

可以把 `requirements.txt` 理解成依赖清单，把 `constraints.txt` 理解成版本边界或版本策略。

## 1. requirements.txt：安装目标

`requirements.txt` 里的包会被 `pip` 主动安装。例如：

```txt
fastapi
uvicorn[standard]
requests>=2.31
```

Dockerfile 中常见写法：

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

这表示镜像构建时必须安装 `fastapi`、`uvicorn[standard]`、`requests`，同时 `pip` 还会解析并安装它们的间接依赖，比如 `starlette`、`pydantic`、`anyio` 等。

所以 `requirements.txt` 解决的是“项目运行需要哪些包”的问题。

## 2. constraints.txt：版本约束，不主动安装

`constraints.txt` 里的包不会因为写在文件里就被安装。它只在某个包被安装时，对该包版本施加限制。例如：

```txt
pydantic==2.7.4
urllib3<2.0
setuptools<70
```

配合 Dockerfile 使用：

```dockerfile
COPY requirements.txt constraints.txt .
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt
```

这里的含义是：

- 仍然只安装 `requirements.txt` 中声明的直接依赖及其间接依赖。
- 如果解析过程中需要安装 `pydantic`，必须用 `2.7.4`。
- 如果解析过程中需要安装 `urllib3`，版本必须小于 `2.0`。
- 如果没有任何依赖需要 `setuptools`，`constraints.txt` 里的 `setuptools<70` 不会让它自动安装。

所以 `constraints.txt` 解决的是“依赖版本必须被限制在什么范围”的问题。

## 3. 最核心区别

| 对比项 | `requirements.txt` | `constraints.txt` |
|---|---|---|
| 是否主动安装包 | 是 | 否 |
| 主要职责 | 声明项目需要的依赖 | 限制依赖版本选择 |
| 是否适合放业务直接依赖 | 适合 | 不适合单独使用 |
| 是否能约束间接依赖 | 可以，但不优雅 | 非常适合 |
| 常见 pip 参数 | `-r requirements.txt` | `-c constraints.txt` |

一个简单判断方法：

- 这个包是项目代码直接 import 或运行必须依赖的吗？放 `requirements.txt`。
- 这个包只是某个依赖带进来的，但版本需要固定或规避问题吗？放 `constraints.txt`。

## 4. Docker 编译中的典型场景

### 场景一：提高镜像构建的可复现性

如果 Dockerfile 只有：

```dockerfile
RUN pip install -r requirements.txt
```

而 `requirements.txt` 又写得比较宽松：

```txt
fastapi
uvicorn
requests
```

那么今天构建和下周构建出来的镜像可能安装到不同版本的依赖。即使业务代码没变，也可能因为某个间接依赖升级导致镜像构建失败或运行异常。

此时可以加 `constraints.txt`：

```txt
fastapi==0.111.0
uvicorn==0.30.1
starlette==0.37.2
pydantic==2.7.4
anyio==4.4.0
requests==2.32.3
urllib3==2.2.2
```

Dockerfile：

```dockerfile
COPY requirements.txt constraints.txt .
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt
```

这样项目仍然通过 `requirements.txt` 表达依赖意图，但实际构建版本由 `constraints.txt` 收紧，镜像更稳定。

### 场景二：统一多个服务的依赖版本

一个公司可能有多个 Python 服务：

```txt
service-a/requirements.txt
service-b/requirements.txt
service-c/requirements.txt
constraints/common.txt
```

每个服务的 `requirements.txt` 不一样：

```txt
# service-a/requirements.txt
fastapi
sqlalchemy
```

```txt
# service-b/requirements.txt
fastapi
celery
redis
```

但希望所有服务统一使用同一套基础依赖版本，比如：

```txt
# constraints/common.txt
fastapi==0.111.0
pydantic==2.7.4
sqlalchemy==2.0.30
redis==5.0.4
urllib3==2.2.2
```

构建时统一使用：

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt -c constraints/common.txt
```

这样每个服务仍然只声明自己需要什么，但公共依赖版本由团队统一管控，减少“这个服务能跑、那个服务不能跑”的环境差异。

### 场景三：规避某个间接依赖的新版本问题

假设项目只写了：

```txt
requests
```

某天 `urllib3` 新版本发布后，镜像构建正常，但线上请求行为异常。`urllib3` 是 `requests` 的间接依赖，业务代码并没有直接 import 它。

这时不一定要把 `urllib3` 加进 `requirements.txt`，因为它不是业务直接依赖。更合适的是在 `constraints.txt` 里限制：

```txt
urllib3<2.2
```

构建命令：

```bash
pip install -r requirements.txt -c constraints.txt
```

这样表达更清晰：项目不是直接依赖 `urllib3`，只是当前构建需要避开某个版本范围。

### 场景四：Docker 中编译原生扩展失败

有些 Python 包依赖 C 扩展或系统库，比如 `cryptography`、`numpy`、`pandas`、`grpcio` 等。不同 Python 版本、Linux 发行版、CPU 架构下，某些版本可能没有可用 wheel，导致 Docker build 过程中现场编译失败。

例如在 `python:3.12-slim` 中构建时，某个间接依赖拉到了不兼容版本。可以通过 `constraints.txt` 固定到已验证能在该镜像中安装的版本：

```txt
numpy==1.26.4
cryptography==42.0.8
grpcio==1.64.1
```

这类约束尤其适合 Docker，因为 Docker 镜像强调构建可重复、环境可复制。把这些经验沉淀到 constraints 文件里，比在 Dockerfile 里写一堆临时修补命令更容易维护。

## 5. 推荐实践

### 小项目

可以只用 `requirements.txt`，并尽量固定关键版本：

```txt
fastapi==0.111.0
uvicorn==0.30.1
requests==2.32.3
```

简单直接，维护成本低。

### 中大型项目或多个服务

推荐拆分：

```txt
requirements.txt      # 直接依赖
constraints.txt       # 全局版本约束，包括间接依赖
```

Dockerfile：

```dockerfile
COPY requirements.txt constraints.txt .
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt
```

### 生产镜像

生产镜像应尽量避免完全不固定版本的依赖。比较稳妥的方式是：

- `requirements.txt` 写清楚业务直接依赖。
- `constraints.txt` 固定经过测试的完整版本集合。
- CI 中定期更新 constraints，而不是每次 Docker build 都自动吃到最新依赖。

## 6. 和 lock 文件的关系

`constraints.txt` 不是严格意义上的 lock 文件。它只是给 `pip` 的解析器设置边界。真正的锁定通常由工具生成，例如：

- `pip-tools` 的 `pip-compile`
- Poetry 的 `poetry.lock`
- uv 的 `uv.lock`

如果团队使用 `pip-tools`，常见流程是：

```txt
requirements.in       # 人手写的直接依赖
requirements.txt      # pip-compile 生成的锁定结果
```

有些团队也会把生成结果作为 constraints 使用：

```bash
pip install -r requirements.in -c constraints.txt
```

选择哪种方式取决于团队习惯，但原则不变：安装清单和版本约束最好分清楚。

## 7. 总结

在 Docker 编译中，`requirements.txt` 和 `constraints.txt` 的区别可以一句话概括：

`requirements.txt` 决定安装哪些包，`constraints.txt` 决定这些包及其间接依赖允许安装哪些版本。

如果项目很小，只用 `requirements.txt` 就够了；如果项目需要稳定、可复现的 Docker 构建，或者多个服务要统一依赖版本，就应该引入 `constraints.txt`。这样既能保留依赖声明的清晰性，也能降低镜像构建因依赖漂移导致失败的概率。
