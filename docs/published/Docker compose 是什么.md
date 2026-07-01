Docker Compose 是 Docker 的“多容器编排工具”。

如果 `docker run` 适合启动一个容器：

```bash
docker run -d -p 8080:80 nginx:1.25
```

那么 Docker Compose 更适合管理一组相关容器，比如：

```text
Web 服务 + 数据库 + Redis + 消息队列
```

你不用手动敲很多条 `docker run`，而是把配置写进一个文件：

```yaml
# docker-compose.yml
services:
  web:
    image: nginx:1.25
    ports:
      - "8080:80"
```

然后执行：

```bash
docker compose up -d
```

Compose 就会按照配置帮你创建并启动容器。

常见命令：

```bash
docker compose up -d
```

后台启动服务。

```bash
docker compose ps
```

查看当前 Compose 项目的容器。

```bash
docker compose logs
```

查看日志。

```bash
docker compose down
```

停止并删除这些容器、网络等资源。

它的核心作用可以理解为：

```text
docker run：一次启动一个容器
docker compose：用一个配置文件管理一组容器
```

现在推荐使用的是：

```bash
docker compose
```

而不是老版本的：

```bash
docker-compose
```

**注意**

`docker compose ps` 和 `docker compose logs` 不是全局查看所有容器的命令，它们默认会在**当前目录**查找类似下面的文件：

```text
compose.yaml
compose.yml
docker-compose.yaml
docker-compose.yml
```

如果当前目录没有这些文件，就会报：

```text
configuration file provided: not found
```

举个例子，如果你的配置文件在这个目录：

```bash
/home/me/artifactory/docker-compose.yml
```

那你需要先进入该目录：

```bash
cd /home/me/artifactory
docker compose ps
docker compose logs
```

或者显式指定配置文件：

```bash
docker compose -f /home/me/artifactory/docker-compose.yml ps
docker compose -f /home/me/artifactory/docker-compose.yml logs
```

如果你只是想查看所有 Docker 容器，不用 Compose，应该用：

```bash
docker ps
```

查看包括已退出的容器：

```bash
docker ps -a
```

查看某个容器日志：

```bash
docker logs 容器名或容器ID
```

简单说：

```text
docker ps / docker logs
```

是 Docker 容器级别的命令。

```text
docker compose ps / docker compose logs
```

是 Compose 项目级别的命令，需要在有 Compose 配置文件的目录里执行。

如果你想一直等待并查看后续新日志，使用

```text
docker compose logs -f
```