# PyTorch TCPStore 实现原理：从客户端、服务端到阻塞唤醒

在 PyTorch 分布式训练中，`TCPStore` 经常藏在 `torchrun` 和 `init_process_group()` 背后。平时只会看到：

```text
MASTER_ADDR=10.0.0.10
MASTER_PORT=29500
```

但多个进程第一次集合时，必须有一个地方交换少量初始化信息，例如通信器 ID、进程组前缀和就绪状态。TCPStore 就是 PyTorch 为这类场景提供的基于 TCP 的共享键值存储。

它可以用一句话概括：

> 一个进程启动内存键值服务，所有进程通过 TCP 客户端连接它，使用 `set`、`get`、`add` 和 `wait` 等操作完成初始化与状态协调。

TCPStore 不是用来同步梯度的。模型参数和梯度由 NCCL、Gloo 等通信后端传输，TCPStore 主要属于控制面。

本文结合 PyTorch 当前源码结构，解释 TCPStore 的服务端、客户端、通信协议、阻塞唤醒、原子操作和生命周期，并通过一个双进程 Demo 观察这些行为。

## 一、整体架构

TCPStore 使用经典的客户端/服务端结构：

```text
                      TCPStore Server
                    +-------------------+
                    | 内存中的 key-value |
                    | 等待者注册表       |
                    | TCP 事件循环       |
                    +---------+---------+
                              |
              +---------------+---------------+
              |                               |
        TCPStore Client                 TCPStore Client
            Rank 0                          Rank 1
```

其中：

- `is_master=True` 的进程负责启动 TCP 服务端；
- 所有 Store 实例都会创建客户端连接，包括启动服务端的那个进程；
- 服务端在内存中保存 key-value；
- 客户端把 `set/get/add/wait` 编码为请求，通过 TCP socket 发送；
- 服务端解析请求、修改内存状态，并按需要返回数据或唤醒等待者。

PyTorch C++ 源码大致分成三部分：

```text
TCPStore.hpp / TCPStore.cpp
  客户端 API、服务端启动、连接重试、超时处理

store/TCPStoreBackend.cpp
  传统服务端后端，单后台线程处理 socket 事件

store/TCPStoreLibUvBackend.cpp
  基于 libuv 的事件驱动服务端，当前默认后端
```

不同 PyTorch 版本的文件组织和扩展 API 可能变化，但客户端/服务端、内存哈希表和请求协议这几个核心思路基本一致。

## 二、创建 TCPStore 时发生了什么

Python 中常见的构造方式是：

```python
from datetime import timedelta
import torch.distributed as dist


store = dist.TCPStore(
    host_name="127.0.0.1",
    port=29600,
    world_size=2,
    is_master=True,
    timeout=timedelta(seconds=30),
    wait_for_workers=True,
)
```

主要参数含义如下：

| 参数 | 含义 |
|---|---|
| `host_name` | 服务端地址 |
| `port` | 服务端监听端口 |
| `world_size` | 使用 Store 的总进程数，包括服务端所在进程 |
| `is_master` | 是否负责启动服务端 |
| `timeout` | 连接、`get`、`wait` 等操作的超时 |
| `wait_for_workers` | 固定 world size 时，服务端是否等待所有用户连接 |
| `use_libuv` | 是否使用 libuv 服务端后端，当前默认是 `True` |

构造过程可以简化为：

```text
is_master=True？
   |
   +-- 是：绑定端口，启动后台服务端线程
   |
   +-- 否：不启动服务端
   |
   v
创建 TCP 客户端并连接 host:port
   |
   v
发送 VALIDATE 魔数，确认对端是 TCPStore
   |
   v
发送 PING，确认连接可正常收发
   |
   v
wait_for_workers=True？
   |
   +-- 是：登记当前用户，Master 等待 world_size 个用户加入
```

### 1. 为什么 Master 也要创建客户端

Master 进程不仅运行服务端，它自己也需要使用 `set/get/add`。因此同一个 TCPStore 对象中可以同时持有：

- 一个服务端后台线程；
- 一个连接到该服务端的客户端 socket。

这样所有调用都走相同协议，不需要为 Master 单独写一套内存访问逻辑。

### 2. 客户端如何处理启动顺序

分布式进程几乎不可能同时启动。客户端连接失败时不会立即放弃，而是在超时期限内使用带抖动的退避策略重试连接。

因此，客户端比服务端稍早启动通常没有问题。真正需要检查的是：

- 地址是否可达；
- 端口是否正确；
- 服务端最终是否启动；
- 防火墙和容器网络是否放行。

### 3. wait_for_workers 如何实现

固定 `world_size` 时，每个 Store 用户都会对内部初始化 key 做一次原子加法。Master 读取这个计数，直到达到 `world_size`。

概念上类似：

```python
store.add("internal_init_key", 1)

if is_master:
    while int(store.get("internal_init_key")) < world_size:
        wait_a_moment()
```

真实源码使用内部保留 key，并包含超时检查。这里的 `world_size` 是 Store 用户数，不一定永远等同于某个训练 ProcessGroup 的成员数，只是在常见初始化流程中二者通常一致。

## 三、数据到底保存在哪里

TCPStore 名字里有“Store”，但它不是 Redis、etcd 或数据库。服务端核心状态本质上是一个内存哈希表：

```cpp
std::unordered_map<std::string, std::vector<uint8_t>> tcpStore_;
```

可以把它理解成：

```text
"/config"          -> bytes("batch_size=64")
"/worker_count"    -> bytes("2")
"/nccl_unique_id"  -> bytes(...)
```

几个重要结论：

- key 最终以字符串处理；
- value 在服务端以字节数组保存；
- Python `get()` 返回 `bytes`；
- 数据主要驻留在服务端内存中；
- 服务端退出后，数据不会持久化恢复；
- 服务端没有多副本一致性或自动故障转移。

因此 TCPStore 适合短生命周期、小数据量的进程协调，不适合作为业务数据库或大规模参数服务器。

## 四、客户端和服务端怎样通信

TCPStore 在 TCP 字节流上定义了自己的轻量协议。每个请求先发送一个命令类型，再发送参数数量、长度和内容。

概念上可以表示为：

```text
SET  | key_length | key | value_length | value
GET  | key_length | key
ADD  | key_length | key | int64_delta
WAIT | key_count  | key1_length | key1 | key2_length | key2 | ...
```

当前源码中的命令类型包括：

```text
VALIDATE、PING、SET、GET、ADD、CHECK、WAIT、CANCEL_WAIT、
COMPARE_SET、DELETE_KEY、APPEND、MULTI_GET、MULTI_SET、BARRIER 等
```

客户端会把同一次请求的字段放入发送缓冲区。服务端从 socket 读取命令类型，再分发给对应处理函数：

```text
QueryType::SET   -> set handler
QueryType::GET   -> get handler
QueryType::ADD   -> add handler
QueryType::WAIT  -> wait handler
```

TCP 是字节流协议，一次请求可能被拆成多个网络包。默认 libuv 后端会维护流式解析状态，等字段完整后再执行命令，而不是假设一次读取就能得到完整请求。

同一个客户端对象还使用互斥锁保护活动操作，避免多个线程同时向同一个 socket 写入时把两条请求交叉在一起。


## 五、get 为什么会阻塞

读取不存在的 key 不会立即返回 `None`，而是一直等待，最后才超时。这是因为客户端的 `get(key)` 并非直接发送 GET：

```text
get(key)
   |
   v
先发送 WAIT(key)
   |
   +-- key 已存在：服务端立即回复 STOP_WAITING
   |
   +-- key 不存在：服务端登记当前客户端
   |
   v
WAIT 完成后发送 GET(key)
   |
   v
服务端返回 value
```

服务端维护两类等待状态，概念上类似：

```text
waiting_clients[key] -> 正在等待该 key 的客户端列表
keys_awaited[client] -> 该客户端还缺少多少个 key
```

假设 Rank 1 调用 `store.get("config")`，但 `config` 尚不存在，服务端会把 Rank 1 的连接登记到等待列表。Rank 0 随后调用：

```python
store.set("config", "batch_size=64")
```

服务端保存数据后会检查等待列表，将 Rank 1 剩余等待 key 的数量减一。如果已经全部满足，就返回停止等待响应。Rank 1 随后发出真正的 GET 请求并取得 value。

### 超时如何处理

客户端等待响应超过 `timeout` 后，会发送 `CANCEL_WAIT`。服务端删除该连接对应的等待状态并确认取消，客户端最后抛出 `DistStoreError`。

取消协议很重要：如果客户端只在本地放弃，而不通知服务端，服务端会一直保存已经无效的等待者。

## 六、set、add 和 compare_set 的语义

### 1. set

`set(key, value)` 会覆盖同名 key。服务端更新哈希表后，还会唤醒等待这个 key 的客户端：

```python
store.set("status", "starting")
store.set("status", "ready")
```

### 2. add

`add(key, delta)` 在服务端完成“读取旧值、相加、写回”并返回新值：

```python
new_value = store.add("finished_workers", 1)
```

多个客户端同时调用时，更新由服务端串行处理，因此不会出现普通客户端侧“先 get 再 set”造成的丢失更新。这也是它适合实现计数器和简单 barrier 的原因。

服务端将计数值以十进制文本对应的字节保存，读取旧值时再转换为整数。

### 3. compare_set

`compare_set` 只有在当前值等于期望值时才写入新值：

```python
actual = store.compare_set("leader", "", "rank-0")
```

这个操作同样在服务端一次完成，可用于简单的 leader 竞争或一次性初始化。但 TCPStore 没有 etcd 那样的租约、事务和持久化能力，不应把它扩展成复杂的分布式协调系统。

## 七、传统后端和 libuv 后端

PyTorch 当前保留两种 TCPStore 服务端后端。

### 1. 传统后端

传统后端启动一个 Master 后台线程，通过 `poll` 等待监听 socket 和客户端 socket 上的事件。请求到达后，由该线程同步执行对应 handler。

```text
一个后台线程
    |
    +-- accept 新连接
    +-- poll 多个客户端 socket
    +-- 读取命令并处理
```

因为核心状态由一个服务端线程处理，`add` 等操作天然形成串行更新。

### 2. libuv 后端

当前 `use_libuv=True` 是默认设置。libuv 后端使用事件循环和异步流处理多个连接：

```text
libuv event loop
    |
    +-- 接收连接事件
    +-- 接收可读事件
    +-- 增量解析 TCP 字节流
    +-- 执行命令并发送响应
```

它比“每个连接一个线程”的模型更轻量，也更适合启动阶段大量 worker 同时连接。两种后端对 Python 用户暴露基本一致的 Store API，差异主要在服务端 I/O 实现。

## 八、TCPStore 如何帮助创建 ProcessGroup

下面的代码显式使用 TCPStore 初始化 Gloo ProcessGroup：

```python
import os
from datetime import timedelta

import torch.distributed as dist


rank = int(os.environ["RANK"])
world_size = int(os.environ["WORLD_SIZE"])

store = dist.TCPStore(
    host_name=os.environ["MASTER_ADDR"],
    port=int(os.environ["MASTER_PORT"]),
    world_size=world_size,
    is_master=(rank == 0),
    timeout=timedelta(seconds=60),
)

dist.init_process_group(
    backend="gloo",
    store=store,
    rank=rank,
    world_size=world_size,
)
```

此时的职责划分是：

```text
TCPStore
  交换 Gloo ProcessGroup 初始化所需的小量元数据
        |
        v
Gloo ProcessGroup
  建立真正的进程间通信上下文
        |
        v
broadcast / all_reduce
  通过 Gloo 传输 Tensor
```

如果后端换成 NCCL，TCPStore 仍然可以承担初始化信息交换，但 GPU Tensor 由 NCCL 传输，而不是通过 Store。

日常训练通常直接使用：

```python
dist.init_process_group(backend="nccl", init_method="env://")
```

`torchrun` 和 rendezvous 逻辑已经在内部处理 Store，因此普通训练脚本很少需要手工创建 TCPStore。

## 九、一个可以观察阻塞和原子加法的 Demo

下面使用两个独立进程创建一个 TCPStore。Rank 1 会先读取尚不存在的 `config`，因此在 `get()` 中等待；Rank 0 一秒后写入，服务端随即唤醒 Rank 1。

新建 `tcpstore_demo.py`：

```python
import multiprocessing as mp
import time
from datetime import timedelta

import torch.distributed as dist


HOST = "127.0.0.1"
PORT = 29600
WORLD_SIZE = 2


def worker(rank):
    store = dist.TCPStore(
        host_name=HOST,
        port=PORT,
        world_size=WORLD_SIZE,
        is_master=(rank == 0),
        timeout=timedelta(seconds=10),
        wait_for_workers=True,
    )

    if rank == 0:
        # 确保 Rank 1 已经进入 get() 的等待流程。
        time.sleep(1)
        print("rank 0: set config")
        store.set("config", "batch_size=64")

        store.add("counter", 1)
        store.wait(["rank_1_done"])

        counter = int(store.get("counter"))
        print(f"rank 0: final counter={counter}")
    else:
        started = time.monotonic()
        print("rank 1: get config, waiting...")

        config = store.get("config").decode()
        elapsed = time.monotonic() - started
        print(f"rank 1: config={config}, waited={elapsed:.1f}s")

        store.add("counter", 1)
        store.set("rank_1_done", "1")


if __name__ == "__main__":
    ctx = mp.get_context("spawn")
    processes = [
        ctx.Process(target=worker, args=(rank,))
        for rank in range(WORLD_SIZE)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join()

    for process in processes:
        if process.exitcode != 0:
            raise SystemExit(
                f"child process failed: exitcode={process.exitcode}"
            )
```

运行：

```bash
python tcpstore_demo.py
```

可能输出：

```text
rank 1: get config, waiting...
rank 0: set config
rank 1: config=batch_size=64, waited=1.0s
rank 0: final counter=2
```

输出顺序可能略有不同，但有两个稳定结论：

1. Rank 1 的 `get("config")` 会等待 Rank 0 写入；
2. 两个进程各执行一次 `add("counter", 1)`，最终计数是 2。

如果端口 29600 已经被占用，需要换成一个未使用端口。多机运行时还要把 `HOST` 改为服务端可达地址。

## 十、TCPStore 的边界和常见问题

### 1. 服务端是单点

key-value 集中保存在服务端内存中。Master 进程退出后，其他客户端的后续请求会失败，数据也不会自动迁移到新服务端。

因此必须保证服务端对象的生命周期覆盖所有客户端。Demo 中 Rank 0 等待 `rank_1_done`，就是为了避免服务端提前退出。

### 2. 它不是持久化数据库

TCPStore 没有磁盘持久化、复制、选主和自动故障恢复。它适合训练任务启动期间的短生命周期协调，不适合保存业务状态或 checkpoint。

### 3. 它不适合传输大 Tensor

即使 value 可以保存字节，也不应该把模型权重序列化后写进 Store。Tensor 通信应使用 NCCL/Gloo ProcessGroup 的 `broadcast`、`all_reduce` 等接口。

### 4. 多机不能使用 127.0.0.1

每台机器的 `127.0.0.1` 都指向自己。客户端必须填写 Master 所在机器可达的 IP 或域名，并放行监听端口。

### 5. world_size 不一致会导致超时

服务端等待 8 个 Store 用户，但只启动 7 个时，`wait_for_workers=True` 会一直等待，最终报告加入数量和超时。

### 6. get 不存在的 key 会等待

如果 key 可能永远不会出现，应设置合理的 `timeout`。排查“代码卡在 get”时，先确认生产该 key 的进程是否执行了 `set/add`，以及两边是否使用完全相同的 key 和前缀。

### 7. 不要暴露到不可信网络

TCPStore 的内部协议主要用于分布式任务协调，不是面向公网设计的通用服务。不要把监听端口直接暴露到不可信网络，网络访问控制应由集群、防火墙或安全组负责。

## 十一、从一次 get 看完整调用链

最后用一条调用链串起全文：

```text
Rank 1 调用 get("config")
        |
        v
客户端发送 WAIT("/config")
        |
        v
服务端发现 key 不存在，登记 Rank 1 的 socket
        |
        v
Rank 0 调用 set("config", value)
        |
        v
服务端写入内存哈希表并唤醒 Rank 1
        |
        v
Rank 1 发送 GET("/config")
        |
        v
服务端返回 bytes，Python 调用 decode() 得到字符串
```

这里能看到 TCPStore 的几个核心设计：

- 中心化内存哈希表保存数据；
- TCP 客户端/服务端协议负责请求和响应；
- 等待者注册表实现阻塞读取；
- 服务端串行处理使 `add` 等更新具有原子性；
- libuv 事件循环负责高效管理大量连接；
- timeout 和取消请求负责清理未完成等待。

## 十二、总结

TCPStore 的实现并不神秘，它是一个为 PyTorch 分布式启动场景定制的内存键值服务：

```text
一个服务端后台线程或事件循环
        +
一个内存 key-value 哈希表
        +
多个 TCP 客户端连接
        +
WAIT/唤醒和原子计数等协调语义
```

它最重要的价值不是高性能存储，而是让尚未建立 ProcessGroup 的进程先拥有一个简单、跨机器可访问的协调通道。待 NCCL 或 Gloo 通信器建立后，TCPStore 继续留在控制面，真正的大规模 Tensor 通信则交给专业通信后端。

## 参考源码

- PyTorch [`TCPStore.hpp`](https://github.com/pytorch/pytorch/blob/main/torch/csrc/distributed/c10d/TCPStore.hpp)
- PyTorch [`TCPStore.cpp`](https://github.com/pytorch/pytorch/blob/main/torch/csrc/distributed/c10d/TCPStore.cpp)
- PyTorch [`TCPStoreBackend.cpp`](https://github.com/pytorch/pytorch/blob/main/torch/csrc/distributed/c10d/store/TCPStoreBackend.cpp)
- PyTorch [`TCPStoreLibUvBackend.cpp`](https://github.com/pytorch/pytorch/blob/main/torch/csrc/distributed/c10d/store/TCPStoreLibUvBackend.cpp)

源码实现会随 PyTorch 版本演进。阅读本机版本时，可以先通过 `torch.__version__` 确认版本，再对照对应 tag 下的源码。
