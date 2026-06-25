# 本地用 Docker 搭一套 JFrog Artifactory：踩坑实录与可复现配置

最近想在本地折腾一套制品仓库（Artifactory），用来管 generic / Docker / Maven 等各种包。
本以为 `docker run` 一把梭就能起来，结果连踩两个坑才跑通。这篇把完整、可复现的配置和踩到的坑都记下来，
省得下次再翻日志。

环境：Ubuntu，Docker 29 + Docker Compose v2，社区版镜像 `artifactory-cpp-ce`（Artifactory 7.146/7.176 系列）。

## 坑一：新版 Artifactory 不让用内置 Derby 启动

直觉做法是直接跑官方镜像，不配数据库，让它用自带的 Derby。结果容器起来后一直卡在启动循环，
access 服务永远起不来，日志刷的是：

```
org.jfrog.storage.dbtype.DbTypeNotAllowedException:
DB Type derby is not allowed: Cannot start the application with a database other than PostgreSQL.
```

也就是说，新版本**强制要求外接数据库**（PostgreSQL）。Derby 只在很老的版本里能当默认库用，
现在直接被禁掉了。所以正确做法是用 docker-compose 把 Artifactory 和 PostgreSQL 一起拉起。

## 坑二：别用只读 bind mount 挂 system.yaml

配好 PostgreSQL 后，第二个坑更隐蔽。数据库连接信息要写在 `system.yaml` 里，
我一开始很自然地用只读 bind mount 把它挂进容器：

```yaml
- ./system.yaml:/var/opt/jfrog/artifactory/etc/system.yaml:ro
```

结果 router 启动直接 FATAL：

```
[FATAL] Could not save system configuration file: ...
open /opt/jfrog/artifactory/var/etc/system.yaml: read-only file system
```

原因是 Artifactory 的 router 在启动时**需要原地改写这个文件**——它会把你写的明文数据库密码
加密成 `aesgcm256` 密文再写回去。只读挂载 + 单文件 bind mount（破坏了原子写 rename）让这步失败，
连带导致后面 ping 一直 500（`Session filter is not initialized`）、access 注册不上 router。

正确做法是把 `system.yaml` 预置进**可写的数据卷**里，而不是只读挂单个文件。

## 可复现的完整配置

目录结构：

```
jfrog/
├── docker-compose.yml
└── artifactory/var/etc/system.yaml
```

### docker-compose.yml

```yaml
name: jfrog

services:
  postgres:
    image: postgres:15
    container_name: jfrog-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: artifactory
      POSTGRES_USER: artifactory
      POSTGRES_PASSWORD: artifactory_password
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U artifactory -d artifactory"]
      interval: 10s
      timeout: 5s
      retries: 10
    networks:
      - jfrog-net

  artifactory:
    image: releases-docker.jfrog.io/jfrog/artifactory-cpp-ce:latest
    container_name: artifactory-ce
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8081:8081"   # Artifactory REST API
      - "8082:8082"   # 统一入口 / Web UI (JFrog Platform)
    volumes:
      - artifactory-data:/var/opt/jfrog/artifactory
    networks:
      - jfrog-net

volumes:
  postgres-data:
  artifactory-data:

networks:
  jfrog-net:
```

几个要点：
- 镜像 `artifactory-cpp-ce` 是免费社区版，**自带 PostgreSQL JDBC 驱动**（`postgresql-42.7.11.jar`），
  不用手动塞驱动。
- 两个容器走自定义网络 `jfrog-net`，连接串里直接用服务名 `postgres` 当主机名即可。
- `depends_on ... condition: service_healthy` 配合 PostgreSQL 的 healthcheck，保证 DB 先就绪，避免首启竞态。

### artifactory/var/etc/system.yaml

```yaml
configVersion: 1

shared:
  database:
    type: postgresql
    driver: org.postgresql.Driver
    url: "jdbc:postgresql://postgres:5432/artifactory"
    username: artifactory
    password: artifactory_password
```

### 启动（注意 system.yaml 的预置方式）

```bash
cd jfrog

# 先单独起 DB，并 create（不 start）artifactory 以初始化数据卷
docker compose up -d postgres
docker compose create artifactory

# 用临时容器把 system.yaml 拷进 artifactory 数据卷（可写位置）
docker run --rm \
  -v jfrog_artifactory-data:/data \
  -v "$PWD/artifactory/var/etc/system.yaml:/seed/system.yaml:ro" \
  alpine sh -c 'mkdir -p /data/etc && cp /seed/system.yaml /data/etc/system.yaml && chown -R 1030:1030 /data/etc'

# 正式启动
docker compose up -d
```

（容器内 artifactory 用户的 uid/gid 是 `1030`；数据卷名前缀 `jfrog_` 来自 compose 的 `name: jfrog`。）

首次启动要做 schema 迁移，约 1～3 分钟。期间 ping 接口会依次返回
`000`（没起）→ `503`（启动中）→ `500`（部分服务没就绪）→ `200`（就绪）。可以这样轮询：

```bash
until [ "$(curl -s -o /dev/null -w '%{http_code}' \
  http://localhost:8081/artifactory/api/system/ping)" = "200" ]; do
  echo "waiting..."; sleep 10
done
echo "Artifactory is up"
```

## 验证

```bash
# Artifactory 健康检查
curl http://localhost:8081/artifactory/api/system/ping        # -> OK

# 平台整体健康，各微服务（jfrt/jfac/jfmd/jffe/...）都应为 HEALTHY
curl http://localhost:8082/router/api/v1/system/health

# Web UI
curl -o /dev/null -w '%{http_code}\n' http://localhost:8082/ui/   # -> 200

# 确认确实在用 PostgreSQL、且已建表
docker exec jfrog-postgres psql -U artifactory -d artifactory -t \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
# -> 150+ 张表
```

浏览器打开 `http://localhost:8082/ui/`，默认账号 `admin` / 密码 `password`，首次登录强制改密。

### 创建一个本地仓库并上传/下载（generic 为例）

UI：`Administration → Repositories → Add Repositories → Local`，Package Type 选 `Generic`，
Repository Key 填 `example-local`。然后命令行验证：

```bash
echo "hello jfrog" > demo.txt
curl -u admin:<新密码> -T demo.txt \
  "http://localhost:8081/artifactory/example-local/demo.txt"
curl -u admin:<新密码> \
  "http://localhost:8081/artifactory/example-local/demo.txt"   # -> hello jfrog
```

## 进阶：让局域网其它机器访问

上面的 compose 把端口映射成 `0.0.0.0:8081-8082`，等于绑在所有网卡上，所以局域网内别的机器
不用改配置就能访问，把 `localhost` 换成这台机器的局域网 IP 即可：

- Web UI：`http://<本机LAN IP>:8082/ui/`
- REST API：`http://<本机LAN IP>:8081/artifactory/`

连不上时按这个顺序查：

1. **连通性**：对方机器 `ping <IP>`、`curl -v http://<IP>:8082/ui/`，确认在同一网段、能路由到。
   另外 DHCP 分配的 IP 重启会漂，长期用建议在路由器做绑定或设静态 IP。
2. **防火墙**：宿主机若开了 ufw，要放行端口。更安全的是只放行可信网段：
   ```bash
   sudo ufw allow from 10.0.0.0/8 to any port 8081 proto tcp
   sudo ufw allow from 10.0.0.0/8 to any port 8082 proto tcp
   ```
3. **Base URL**：跨机器访问、尤其后面要用 Docker/包管理客户端时，最好在
   `Administration → General → Settings` 把 Platform Base URL 设成 `http://<IP>:8082`，
   否则生成的下载地址、重定向可能还指向 `localhost`。

安全提醒：绑 `0.0.0.0` 等于对所有能访问到这台机器的网络开放，且默认 admin 口令很弱。
务必改掉默认密码，并用 `ufw allow from <网段>` 只放行可信网段，而不是裸奔对全网开放。

## 几个容易卡住的概念

### 首次进 :8082/ui 时让填的 Proxy Key / Host / Port 是干嘛的？

那是 onboarding 向导里的「配置反向代理（Reverse Proxy）」步骤，作用是**生成一份 Nginx 或 Apache 的反向代理配置模板**，本身不是核心必填项。

- **Proxy Key**：这份反向代理配置的名字/标识，随便起个有意义的名字即可（如 `nginx`），只用来区分多份配置。
- **Host（Server Name）**：你打算用来访问 Artifactory 的域名/主机名（如 `artifactory.example.com` 或机器 IP），会写进生成配置的 `server_name`。
- **Port**：反向代理对外监听的端口，通常 80（HTTP）或 443（HTTPS）。

**为什么需要它？** 核心是为了 Docker registry：Docker 客户端默认要求 registry 走 443/HTTPS 或标准端口，而 Artifactory 默认跑在 8081/8082 这种非标准端口上；Artifactory 的 Docker 仓库（subdomain / port 模式）也依赖前面一层反向代理做端口转发和 TLS 终止。这一步的产物就是一段能直接拿去用的 Nginx/Apache 配置。

**什么时候能跳过？** 如果只是本地/局域网测试、用 `http://<IP>:8082/ui/` 直接访问、暂时不用 Docker 仓库，这一步**完全可以跳过**，不影响 generic/Maven/npm 等仓库。等要对外提供服务、用 Docker registry、上 HTTPS 时，再到 `Administration → General → HTTP Settings`（旧版叫 Reverse Proxy）配置即可。

### Docker Registry 是什么？

Docker Registry 就是**存放和分发 Docker 镜像（image）的仓库服务**。`docker pull nginx`、`docker push myapp` 时，镜像就是从某个 registry 拉取/推送的。

打个比方：镜像像安装包，registry 是放安装包的「应用商店」，repository 是商店里某个应用的页面（如 `nginx`），下面用 tag 区分版本（`nginx:1.27`、`nginx:latest`）。

常见的 registry：
- **Docker Hub**（`docker.io`）：默认公共 registry，`docker pull nginx` 就是从这里拉。
- **云厂商**：阿里云 ACR、AWS ECR、GitHub GHCR 等。
- **私有自建**：官方 `registry:2`，或功能更全的 **Harbor**、**JFrog Artifactory**。

**和本文的关系**：Artifactory 可以同时充当一个私有 Docker Registry。建一个 Docker 类型仓库后即可：

```bash
docker login <Artifactory地址>
docker tag myapp:1.0 <地址>/<docker仓库名>/myapp:1.0
docker push <地址>/<docker仓库名>/myapp:1.0
```

这也正是上面那个反向代理步骤存在的原因——用 Artifactory 当 Docker registry 时，通常要在前面加一层 Nginx 做端口转发和 TLS。只用 generic/Maven/npm 仓库则用不到。

## 排障速查表

| 现象 | 日志关键字 | 原因 / 解决 |
|------|-----------|------------|
| 容器反复重启，access 起不来 | `DB Type derby is not allowed` | 没配外部 DB，按本文挂 PostgreSQL |
| router FATAL | `read-only file system` ... `system.yaml` | 用了只读 bind mount 挂 system.yaml，改为放进可写数据卷 |
| ping 一直 500 | `Session filter is not initialized` | 主服务上下文没起来，多为上面 router 写配置失败的连带结果 |
| access 反复重试 | `Registration with router ... UNAVAILABLE` | 同上，根因仍是 system.yaml 写入失败 |
| 镜像拉取超时 | `TLS handshake timeout` | 镜像源/网络抖动，重试 `docker pull` 即可 |

## Virtual Repository 与 Local Repository 的关系，以及多仓同名包的获取顺序

把仓库跑起来后，第二个常被问到的概念就是仓库类型。Artifactory 里仓库分三种：

- **Local Repository（本地仓库）**：真正存放制品的地方，你 `push` / 上传的包就落在这里，是「源」。
- **Remote Repository（远程仓库）**：对外部仓库（如 Docker Hub、Maven Central、npmjs）的代理，拉过一次的包会缓存在它的本地 cache 里。
- **Virtual Repository（虚拟仓库）**：本身**不存任何制品**，只是一个「聚合入口 / 别名」。它按顺序把若干 local、remote（甚至其它 virtual）仓库聚合成一个统一地址。客户端只需要配置这一个 URL，背后挂了哪些仓库、顺序如何，都对客户端透明。

打个比方：local 是一个个真实的仓库货架，virtual 是前台的一个「统一取货窗口」。你跟窗口要某个包，窗口按它内部登记的一串货架顺序，一个个去找，谁先有就给你谁的。

### 一个 virtual 映射多个 local，同名包的解析顺序

这正是问题的核心。**当一个 virtual repository 里挂了多个 local repository，而这些 local 里存在路径完全相同的包时，Artifactory 的解析规则是：按 virtual repository 里「Selected/Included Repositories」配置的顺序，从上到下逐个查找，返回第一个命中的仓库里的那一份，后面的同名包直接被「遮蔽」，不再参与。**

完整的解析优先级（virtual repo 永远是这个大顺序）：

1. **所有 local 仓库**——按 virtual 里配置的先后顺序；
2. **remote 仓库的本地 cache**——按顺序；
3. **remote 仓库本身**（真正去外网拉）——按顺序。

所以对于「多个 local 有同样的 package」这种情形，关键结论是：

- **谁在 virtual 的列表里排在前面，谁的那一份就被返回**，跟版本号高低、上传时间早晚都无关——它只认列表顺序，不会自动挑「最新的那一个」。
- 想换成另一个 local 的包，要么调整 virtual 里的仓库排序，要么直接绕过 virtual、用 `local-repo-name` 这个具体地址去取。
- 这也是为什么官方反复强调：**一个 virtual repository 只放同一种 package type**，并且要**精心安排成员仓库的顺序**——把更可信、更优先的源放在前面。

### 一个常见的认知误区

不少人以为 virtual 会「合并所有 local 并返回版本最高的包」。**不会。** Latest 类的查询（如 `[RELEASE]`、Latest Version API）在跨多个 local 时，历史上就踩过「只取列表第一个仓库的版本、而非全局最新」的坑（JFrog 官方 issue RTFACT-17532 即为此类）。所以生产里如果依赖「取最新」，不要把同名制品分散到多个 local 再指望 virtual 帮你择优，而应：同一类制品集中到同一个 local，或在客户端/CI 里显式指定来源仓库。

### 怎么查 virtual 实际解析了哪些仓库、什么顺序

在 UI 里编辑 virtual repository，`Repositories` 配置页的 **Selected Repositories / Resolved Repositories** 列表就是真实的解析顺序（从上到下）；如果成员里还嵌套了 virtual，Resolved 列表会自动展开成最终的 local/remote 序列。命令行可以用 REST 看配置：

```bash
curl -u admin:<密码> \
  "http://localhost:8081/artifactory/api/repositories/<virtual-repo-key>"
# 返回里的 "repositories": [...] 数组顺序，就是解析顺序
```

一句话记忆：**virtual 不存包，只按「成员列表顺序」做查找；多个 local 撞同名包时，列表里排第一个的获胜，不比版本、不比时间。**

## 小结

新版 Artifactory 自建的两个关键认知：(1) 必须外接 PostgreSQL，Derby 已被禁；
(2) `system.yaml` 要放在可写位置让 router 原地加密密码，别用只读单文件 bind mount。
踩过这两个坑后，整套 compose 配置就能稳定复现了。
