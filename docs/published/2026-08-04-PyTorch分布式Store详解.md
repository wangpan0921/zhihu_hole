# PyTorch 分布式 Store 详解：TCPStore、FileStore、HashStore 和 PrefixStore

第一次接触 PyTorch 分布式训练时，经常会看到下面这些名字：

- `TCPStore`
- `FileStore`
- `HashStore`
- `PrefixStore`

它们听起来像数据库，实际却不是用来保存训练数据、模型参数或梯度的。它们是 PyTorch 在建立分布式通信时使用的轻量级键值存储，主要负责让不同进程交换少量控制信息。

例如，多个训练进程刚启动时，需要先解决这些问题：

- 总共有多少个进程？
- 每个进程的 Rank 是多少？
- 大家应该连接到哪个地址？
- NCCL 或 Gloo 建立通信时需要的初始化信息放在哪里？
- 某个进程是否已经完成初始化？

Store 就是这些进程交换信息和协调状态的地方。

这篇文章介绍 PyTorch 中几种常见 Store 的原理、区别、使用场景，并给出可以直接运行的示例。

## 一、Store 到底是什么

PyTorch 在 `torch.distributed` 中定义了 `Store` 抽象。可以把它理解为一个支持并发访问的共享字典：

```text
key -> value
```

例如：

```text
"worker/0/address" -> "10.0.0.11"
"worker/1/address" -> "10.0.0.12"
"initialized"      -> "1"
```

不同进程可以向 Store 写入信息，也可以读取其他进程写入的信息。常用操作包括：

- `set(key, value)`：写入键值；
- `get(key)`：读取值，键不存在时通常会等待，直到超时；
- `add(key, number)`：对整数值进行原子加法；
- `wait(keys)`：等待指定的 key 全部出现；
- `check(keys)`：检查指定的 key 是否已经存在；
- `delete_key(key)`：删除 key；TCPStore 和 HashStore 支持该操作，FileStore 不支持；
- `compare_set(key, expected, desired)`：满足预期值时再更新，可用于简单的并发协调。

具体方法会随 PyTorch 版本有所增加，使用时可以通过下面的命令查看当前版本支持的接口：

```python
import torch.distributed as dist

print(dir(dist.Store))
```

Store 里的 key 一般使用字符串，`get()` 返回的 value 通常是 `bytes`：

```python
store.set("status", "ready")
value = store.get("status")

print(value)           # b'ready'
print(value.decode())  # ready
```

## 二、Store 在分布式训练中处于什么位置

Store 属于分布式系统的控制面，而 NCCL、Gloo 等通信后端负责数据面。

可以用下面的流程理解它们的关系：

```text
启动多个训练进程
        |
        v
进程通过 rendezvous 相互发现
        |
        v
借助 Store 交换初始化信息
        |
        v
创建 ProcessGroup
        |
        v
NCCL / Gloo 执行 all_reduce、broadcast 等通信
        |
        v
传输 Tensor、同步梯度
```

因此需要特别区分：

- Store 负责少量元数据、状态和初始化信息；
- ProcessGroup 负责组织参与通信的进程；
- NCCL、Gloo 等后端负责真正的 Tensor 通信；
- DDP 使用 ProcessGroup 同步模型梯度。

不要把模型权重序列化后塞进 Store。即使技术上能写入字节数据，它也不适合高吞吐、大数据量传输。

## 三、TCPStore：通过 TCP 连接多个进程

`TCPStore` 是最常见的一种 Store。它采用客户端/服务端模式：一个进程启动 TCPStore 服务端，其他进程作为客户端连接它。

```text
Rank 0：TCPStore Server
          |
          +---- Rank 1：TCPStore Client
          +---- Rank 2：TCPStore Client
          +---- Rank 3：TCPStore Client
```

所有进程只要能通过网络访问服务端的 IP 和端口，就能共享其中的键值。它不要求机器之间存在共享文件系统，因此非常适合多机训练。

### 1. TCPStore 适合什么场景

- 多机多进程之间交换初始化信息；
- 自定义 `ProcessGroup` 初始化流程；
- 编写分布式启动器或训练框架；
- 在分布式测试中协调多个独立进程；
- 多个进程需要一个简单的计数器或状态同步点。

### 2. 一个可运行的 TCPStore 示例

新建 `tcp_store_demo.py`：

```python
import os
import time
from datetime import timedelta

import torch.distributed as dist


rank = int(os.environ["RANK"])
world_size = int(os.environ["WORLD_SIZE"])
host = os.environ.get("STORE_HOST", "127.0.0.1")
port = int(os.environ.get("STORE_PORT", "29600"))

store = dist.TCPStore(
    host_name=host,
    port=port,
    world_size=world_size,
    is_master=(rank == 0),
    timeout=timedelta(seconds=30),
    wait_for_workers=True,
)

if rank == 0:
    store.set("message", "hello from rank 0")

message = store.get("message").decode()
print(f"rank {rank} received: {message}")

# add 是原子操作，多个进程同时调用也不会丢失更新。
finished = store.add("finished_workers", 1)
print(f"rank {rank}: finished_workers={finished}")

# 避免服务端进程过早退出，让所有客户端完成读取。
if rank == 0:
    while int(store.get("finished_workers")) < world_size:
        time.sleep(0.1)
    store.set("can_exit", "1")
else:
    store.wait(["can_exit"])
```

在同一台机器的两个终端中分别运行：

终端 1：

```bash
RANK=0 WORLD_SIZE=2 STORE_HOST=127.0.0.1 STORE_PORT=29600 \
python tcp_store_demo.py
```

终端 2：

```bash
RANK=1 WORLD_SIZE=2 STORE_HOST=127.0.0.1 STORE_PORT=29600 \
python tcp_store_demo.py
```

可能得到类似输出：

```text
rank 0 received: hello from rank 0
rank 1 received: hello from rank 0
rank 0: finished_workers=1
rank 1: finished_workers=2
```

如果在两台机器上运行，需要把 `STORE_HOST` 改成 Rank 0 所在机器能够被另一台机器访问的 IP，并确保对应端口已经放行。此时不能写 `127.0.0.1`，因为每台机器的 `127.0.0.1` 都只指向自己。

### 3. 用 TCPStore 初始化 ProcessGroup

Store 更典型的用途不是业务代码直接调用 `set()`、`get()`，而是交给 `init_process_group()`：

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

print(f"rank {rank} initialized")

dist.barrier()
dist.destroy_process_group()
```

如果是 GPU 训练，通常将后端换成 `nccl`，并为每个进程设置正确的 GPU。

## 四、FileStore：通过共享文件协调进程

`FileStore` 把协调信息保存在文件中。不同进程只要能访问同一个文件，就可以通过它共享键值。

```text
Process 0 -----+
Process 1 -----+---- 共享文件 ---- FileStore
Process 2 -----+
```

这里的关键不是“路径字符串相同”，而是多个进程实际访问的是同一个文件。

例如，在两台机器上都写 `/tmp/pytorch_store`，通常表示两台机器各自磁盘上的两个文件，它们并不共享，因此无法用于跨机器协调。多机使用 FileStore 时，需要 NFS 等共享文件系统。

### 1. FileStore 适合什么场景

- 单机上的多进程测试；
- 已经具备可靠共享文件系统的集群；
- 网络端口受到限制，但进程可以访问同一共享目录；
- 临时调试或复现分布式初始化问题。

对于普通多机训练，如果没有现成的共享存储，通常优先使用 TCPStore，而不是专门为 FileStore 搭建一套共享文件系统。

### 2. FileStore 示例

新建 `file_store_demo.py`：

```python
import os
import time
from datetime import timedelta

import torch.distributed as dist


rank = int(os.environ["RANK"])
world_size = int(os.environ["WORLD_SIZE"])
store_path = os.environ["STORE_FILE"]

store = dist.FileStore(store_path, world_size)
store.set_timeout(timedelta(seconds=30))

if rank == 0:
    store.set("config", "batch_size=64")

config = store.get("config").decode()
print(f"rank {rank} received: {config}")

# 保证先启动的进程不会在其他进程读取前退出。
store.add("finished_workers", 1)
if rank == 0:
    while int(store.get("finished_workers")) < world_size:
        time.sleep(0.1)
    store.set("can_exit", "1")
else:
    store.wait(["can_exit"])
```

给这次任务准备一个新的、所有进程都能访问的文件路径，然后在两个终端中运行：

```bash
RANK=0 WORLD_SIZE=2 STORE_FILE=/tmp/pytorch_file_store_demo \
python file_store_demo.py
```

```bash
RANK=1 WORLD_SIZE=2 STORE_FILE=/tmp/pytorch_file_store_demo \
python file_store_demo.py
```

实际任务中最好为每次运行生成唯一文件名，并在确认所有进程已经退出后清理旧文件。复用上一次异常退出留下的 Store 文件，可能导致读取旧状态或初始化失败。

## 五、HashStore：进程内的内存键值存储

`HashStore` 使用内存中的哈希表保存数据，不启动 TCP 服务，也不依赖文件。

它最大的限制是：只能在创建它的进程内部共享，不能让两个独立进程通过各自创建的 HashStore 通信。

下面这种写法是错误理解：

```python
# 进程 A
store = dist.HashStore()
store.set("key", "value")

# 进程 B
store = dist.HashStore()
print(store.get("key"))  # 这是另一个独立的 HashStore
```

两个进程分别创建了两个内存对象，它们之间没有任何连接。

### 1. HashStore 适合什么场景

- 单元测试；
- 在一个进程的多个线程之间测试 Store 操作；
- 测试依赖 Store 接口的组件，不想启动端口或创建临时文件；
- 构造 `PrefixStore` 的简单测试环境。

### 2. HashStore 示例

```python
import threading

import torch.distributed as dist


store = dist.HashStore()


def writer():
    store.set("result", "success")


def reader():
    value = store.get("result").decode()
    print(value)


t1 = threading.Thread(target=writer)
t2 = threading.Thread(target=reader)

t2.start()  # get 会等待 result 出现
t1.start()

t1.join()
t2.join()
```

运行后输出：

```text
success
```

`HashStore` 很适合测试，但如果测试目标是验证真正的跨进程行为，应该换成 TCPStore 或 FileStore。

## 六、PrefixStore：给另一个 Store 增加命名空间

`PrefixStore` 和前面三种 Store 不完全相同。

TCPStore、FileStore 和 HashStore 决定数据实际保存在哪里、进程之间怎样访问；PrefixStore 则是一个包装器，它在另一个 Store 的基础上，为 key 自动增加前缀。

假设两个模块都使用 `status` 这个 key：

```text
训练模块：status -> running
评估模块：status -> finished
```

如果它们直接共用同一个底层 Store，就会发生 key 冲突。使用 PrefixStore 后，逻辑上相当于：

```text
train/status -> running
eval/status  -> finished
```

### 1. PrefixStore 适合什么场景

- 多个 ProcessGroup 共用同一个底层 Store；
- 一个分布式任务中包含训练、评估等多个子模块；
- 框架需要隔离不同任务、会话或通信组的 key；
- 测试中希望复用 Store，同时避免不同测试用例互相污染。

### 2. PrefixStore 示例

```python
import torch.distributed as dist


base_store = dist.HashStore()

train_store = dist.PrefixStore("train/", base_store)
eval_store = dist.PrefixStore("eval/", base_store)

train_store.set("status", "running")
eval_store.set("status", "finished")

print(train_store.get("status").decode())  # running
print(eval_store.get("status").decode())   # finished
```

两个 PrefixStore 使用的是同一个 `base_store`，但因为前缀不同，相同的 `status` key 不会互相覆盖。

PrefixStore 可以包装 TCPStore、FileStore、HashStore，也可以包装另一个 PrefixStore。它解决的是 key 命名空间问题，而不是底层通信问题。

## 七、四种 Store 应该怎么选

| Store | 数据位置或通信方式 | 跨线程 | 跨进程 | 跨机器 | 典型用途 |
|---|---|---:|---:|---:|---|
| `TCPStore` | TCP 服务端 | 是 | 是 | 是 | 多机训练、进程组初始化 |
| `FileStore` | 共享文件 | 是 | 是 | 取决于共享文件系统 | 单机测试、已有 NFS 的环境 |
| `HashStore` | 当前进程内存 | 是 | 否 | 否 | 单元测试、进程内测试 |
| `PrefixStore` | 包装另一个 Store | 取决于底层 Store | 取决于底层 Store | 取决于底层 Store | key 隔离、命名空间 |

可以按下面的方式快速判断：

```text
是否需要独立进程或多机通信？
  |
  +-- 否：HashStore
  |
  +-- 是
       |
       +-- 所有进程是否能访问同一个可靠的共享文件？
       |      |
       |      +-- 是：可以使用 FileStore
       |      +-- 否：使用 TCPStore
       |
       +-- 是否还需要隔离不同模块或进程组的 key？
              |
              +-- 是：在底层 Store 外包装 PrefixStore
```

## 八、平时使用 torchrun，为什么没有见过 Store

大多数 PyTorch 用户不需要手工创建 Store。

典型的分布式训练代码可能只有：

```python
import torch.distributed as dist

dist.init_process_group(backend="nccl", init_method="env://")
```

启动时使用：

```bash
torchrun \
  --nnodes=1 \
  --nproc-per-node=4 \
  train.py
```

`torchrun` 和 PyTorch 的 rendezvous、进程组初始化逻辑已经处理了大部分协调工作。用户通常只需要正确提供：

- `MASTER_ADDR`；
- `MASTER_PORT`；
- `RANK`；
- `WORLD_SIZE`；
- `LOCAL_RANK`。

这也是为什么普通 DDP 训练教程里很少显式创建 `TCPStore`：Store 仍然参与了底层协调，只是被启动和初始化流程封装起来了。

只有在以下情况下，才更可能直接操作 Store：

- 开发分布式训练框架；
- 自定义 rendezvous 或 ProcessGroup 创建过程；
- 排查分布式初始化问题；
- 编写 PyTorch 分布式相关的底层测试；
- 需要额外的轻量级跨进程协调。

## 九、常见问题和误区

### 1. 把 Store 当成参数服务器

Store 不适合保存或传输大 Tensor，也不是参数服务器。梯度同步应使用：

```python
dist.all_reduce(tensor)
dist.broadcast(tensor, src=0)
```

或者直接使用 `DistributedDataParallel`。

### 2. TCPStore 的地址写成 localhost

单机测试可以使用 `127.0.0.1`。多机环境中，客户端必须填写服务端可达的真实 IP 或域名。

### 3. TCPStore 端口被占用或被防火墙拦截

常见表现是初始化超时、连接失败，或者提示 address already in use。应检查：

- 服务端端口是否已经被其他任务占用；
- 客户端是否能访问该 IP 和端口；
- 容器端口、宿主机端口和安全组是否正确配置；
- 是否意外使用了 `torchrun` 已占用的端口，又创建了第二个 TCPStore。

### 4. world_size 配置不一致

如果服务端等待 4 个进程，但实际上只启动了 3 个，初始化会一直等待，最终超时。所有参与者必须对 `world_size` 有一致认识，并使用唯一的 Rank。

### 5. 读取不存在的 key

`get()` 通常不是立即返回“key 不存在”，而是等待其他进程写入，直到达到 Store 的超时时间。因此一次看似普通的 `get()` 也可能让程序长时间卡住。

不确定 key 是否存在时，可以先根据当前 PyTorch 版本支持的接口使用 `check()`，或者设计明确的 `wait()` 和超时逻辑。

### 6. FileStore 使用的并不是同一个文件

两台机器拥有相同路径，不代表它们访问同一个文件。只有挂载了同一共享存储，FileStore 才能跨机器工作。

### 7. 重复使用旧的 FileStore 文件

异常退出留下的文件可能包含旧状态。为每次任务使用唯一文件路径，比反复使用固定文件名更可靠。

### 8. 让 TCPStore 服务端过早退出

TCPStore 服务端通常由 `is_master=True` 的进程持有。如果这个进程在其他客户端完成操作前退出，客户端后续访问可能失败。程序需要保证 Store 的生命周期覆盖所有使用者。

## 十、总结

PyTorch 的 Store 是分布式通信建立之前的重要协调组件。它负责共享少量控制信息，但不负责传输训练中的大规模 Tensor。

四种 Store 可以这样记：

- `TCPStore`：通过 TCP 连接进程，适合多进程、多机器；
- `FileStore`：通过共享文件协调，适合单机测试或已有共享文件系统的环境；
- `HashStore`：数据只在当前进程内，适合单元测试；
- `PrefixStore`：包装其他 Store，为 key 增加命名空间，避免冲突。

对于普通 DDP 训练，推荐继续使用 `torchrun` 和 `init_process_group()` 提供的标准初始化方式，不必手工管理 Store。只有进入框架开发、自定义初始化或底层排障时，才需要直接使用这些 API。

理解 Store 的价值不在于以后每个训练脚本都手写一个 TCPStore，而在于分布式初始化卡住时，能够知道多个进程究竟在等待什么、它们通过什么方式相互发现，以及问题应该从地址、端口、共享文件、Rank 还是 `world_size` 开始排查。
