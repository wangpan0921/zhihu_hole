# PyTorch 分布式通信详解：NCCL、Gloo、TCPStore 和 broadcast

在 PyTorch 分布式训练中，经常会同时看到 `NCCL`、`Gloo`、`ProcessGroup`、`TCPStore` 和 `broadcast`。它们都和多进程训练有关，但处在不同层次。

先记住一句话：

> `TCPStore` 负责交换少量初始化信息，`ProcessGroup` 负责组织通信成员，NCCL 或 Gloo 负责真正的 Tensor 通信，`broadcast` 是 ProcessGroup 上执行的一种集合通信操作。

## 一、先看完整分层

```text
torchrun / 作业平台
        |
        v
rendezvous（进程发现）
        |
        | 通过 TCPStore、FileStore 等交换初始化信息
        v
ProcessGroup（通信进程组）
        |
        | 选择 NCCL、Gloo 等通信后端
        v
broadcast、all_reduce、all_gather、barrier
        |
        v
DDP、FSDP 等分布式训练框架
```

Store 属于控制面，负责 Rank、地址、端口、通信器初始化信息和就绪状态；NCCL、Gloo 属于数据面，负责实际传输 Tensor。后端初始化时也会使用 Store，但模型参数、梯度和大 Tensor 不会通过 Store 传输。

## 二、几个基本角色

`Rank` 是进程在整个任务中的编号，`WORLD_SIZE` 是进程总数。`LOCAL_RANK` 是进程在当前机器上的编号，通常用于绑定 GPU：

```python
local_rank = int(os.environ["LOCAL_RANK"])
torch.cuda.set_device(local_rank)
```

`ProcessGroup` 是一组 Rank 的通信上下文，记录参与者、Rank、通信后端和集合通信资源：

```python
import torch.distributed as dist

dist.init_process_group(backend="gloo")
group = dist.group.WORLD
```

之后的 `broadcast`、`all_reduce`、`barrier` 等操作都在这个组上执行。

## 三、NCCL：GPU 训练的通信后端

NCCL（NVIDIA Collective Communications Library）是 NVIDIA 为 GPU 集合通信设计的库。PyTorch 通过 `ProcessGroupNCCL` 使用它。

当代码写成：

```python
dist.init_process_group(backend="nccl")
```

后续的 `broadcast`、`all_reduce`、`all_gather` 等操作，就会由 NCCL 执行实际的 GPU 通信。NCCL 会根据硬件和网络拓扑选择 NVLink、PCIe、InfiniBand 或其他合适的路径。

NCCL 适合：

- 单机多卡和多机多卡训练；
- `DistributedDataParallel`、FSDP 等 GPU 并行方案；
- 对 CUDA Tensor 执行高吞吐集合通信。

CUDA GPU 训练通常优先使用 NCCL。NCCL 不是启动器、训练框架或键值存储，它主要负责 ProcessGroup 建立后的 GPU Tensor 通信。

### NCCL 最小用法

```python
import os

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP


local_rank = int(os.environ["LOCAL_RANK"])
torch.cuda.set_device(local_rank)

dist.init_process_group(backend="nccl")

model = torch.nn.Linear(10, 1).cuda(local_rank)
model = DDP(model, device_ids=[local_rank])
```

启动：

```bash
torchrun --standalone --nproc-per-node=4 train.py
```

`torchrun` 启动 4 个进程，通常每个进程绑定一张 GPU；NCCL 负责这些进程之间的梯度和 Tensor 通信。

## 四、Gloo：通用的通信后端

Gloo 是一个通用集合通信库，PyTorch 通过 `ProcessGroupGloo` 使用它：

```python
dist.init_process_group(backend="gloo")
```

Gloo 最常见的使用对象是 CPU Tensor，底层通常通过 TCP 等网络路径传输数据。

Gloo 适合：

- CPU 分布式训练；
- 没有 NVIDIA GPU 的机器；
- 本地开发和 CI 中的分布式测试；
- 验证 Rank、数据切分和集合通信逻辑；
- NCCL 出问题时，先用 CPU/Gloo 验证上层逻辑。

特定版本或构建可能支持有限的 GPU 场景，但 GPU 高吞吐训练通常仍应选择 NCCL。

### Gloo 最小用法

```python
import torch.distributed as dist


dist.init_process_group(backend="gloo")
dist.barrier()
dist.destroy_process_group()
```

启动：

```bash
torchrun --standalone --nproc-per-node=2 cpu_train.py
```

## 五、NCCL 和 Gloo 的区别

| 对比项 | NCCL | Gloo |
|---|---|---|
| 主要定位 | NVIDIA GPU 集合通信 | 通用集合通信 |
| 最常见设备 | CUDA GPU | CPU |
| 单机通信 | NVLink、PCIe 等 | 进程间网络通信 |
| 多机通信 | 高速网络、InfiniBand/RDMA 等 | TCP 等网络路径 |
| GPU 训练性能 | 通常更高 | 通常不是首选 |
| CPU 训练 | 不是主要场景 | 常用 |
| 调试门槛 | 需要 CUDA/NCCL 环境 | 普通机器即可运行 |

简单选择：模型和 Tensor 在 NVIDIA GPU 上，优先 NCCL；没有 GPU 或只验证分布式逻辑，使用 Gloo。后端不是操作，`broadcast` 是操作，NCCL 或 Gloo 是执行这个操作的实现。


## 六、Gloo broadcast 是什么

`broadcast` 是集合通信：源 Rank 的 Tensor 被复制到进程组中的所有 Rank。

```text
执行前：Rank 0 [100]，Rank 1 [0]，Rank 2 [0]
执行后：Rank 0 [100]，Rank 1 [100]，Rank 2 [100]
```

### Gloo broadcast Demo

创建 `gloo_broadcast_demo.py`：

```python
import os

import torch
import torch.distributed as dist


rank = int(os.environ["RANK"])
dist.init_process_group(backend="gloo")

if rank == 0:
    tensor = torch.tensor([100])
else:
    tensor = torch.tensor([0])

print(f"rank {rank}: before = {tensor.item()}")

# 所有 Rank 都必须调用，并且调用顺序要一致。
dist.broadcast(tensor, src=0, group=dist.group.WORLD)

print(f"rank {rank}: after  = {tensor.item()}")
dist.destroy_process_group()
```

运行：

```bash
torchrun --standalone --nproc-per-node=3 gloo_broadcast_demo.py
```

三个进程最终都会得到 `after = 100`。`broadcast` 原地更新目标 Tensor，不会返回一份新的 Tensor。

这是集合通信，所有 Rank 必须进入匹配的操作。例如下面的代码可能永远等待：

```python
if rank == 0:
    dist.broadcast(tensor, src=0)
else:
    dist.barrier()
```

不同 Rank 调用了不同的 collective，通信顺序已经不匹配。

## 七、TCPStore：进程之间的共享键值存储

`TCPStore` 是基于 TCP 的键值存储，一个进程启动服务端，其他进程作为客户端连接：

```text
Rank 0：TCPStore Server
          |
          +---- Rank 1：Client
          +---- Rank 2：Client
```

它适合传输少量控制信息：

- rendezvous 和进程组初始化信息；
- worker 是否就绪；
- 主进程选出的端口或配置；
- 简单的状态和计数器。

它不适合传输模型参数、梯度或大 Tensor。

`TCPStore` 的典型操作是：

```python
store.set("config", "batch_size=64")
value = store.get("config")
```

`get()` 返回的值通常是 `bytes`。如果 key 不存在，`get()` 通常会等待直到超时。和集合通信不同，读写两端不要求调用相同操作：一个 Rank 可以 `set`，另一个 Rank 可以 `get`。

### TCPStore Demo

创建 `tcp_store_demo.py`：

```python
import os
from datetime import timedelta

import torch.distributed as dist


rank = int(os.environ["RANK"])
world_size = int(os.environ["WORLD_SIZE"])

store = dist.TCPStore(
    host_name=os.environ.get("STORE_HOST", "127.0.0.1"),
    port=int(os.environ.get("STORE_PORT", "29600")),
    world_size=world_size,
    is_master=(rank == 0),
    timeout=timedelta(seconds=30),
    wait_for_workers=True,
)

if rank == 0:
    store.set("training_config", "batch_size=64")
    print("rank 0: config written")
    store.wait(["rank_1_read"])
else:
    config = store.get("training_config").decode()
    print(f"rank 1: received {config}")
    store.set("rank_1_read", "1")
```

同一台机器上分别运行：

```bash
RANK=0 WORLD_SIZE=2 python tcp_store_demo.py
```

```bash
RANK=1 WORLD_SIZE=2 python tcp_store_demo.py
```

多机运行时，`STORE_HOST` 必须是 Rank 0 所在机器的可达地址，不能使用 `127.0.0.1`。还要确保端口未被占用且被防火墙放行。

## 八、TCPStore 和 Gloo broadcast 的区别

| 对比项 | TCPStore | Gloo broadcast |
|---|---|---|
| 所属层次 | rendezvous / 控制面 | ProcessGroup / 数据面 |
| 操作对象 | key-value | Tensor |
| 典型 API | `set`、`get`、`wait`、`add` | `broadcast(tensor, src=0)` |
| 是否要求所有 Rank 调用相同操作 | 不要求 | 要求 |
| 是否适合大数据传输 | 不适合 | 适合 Tensor 通信 |
| 数据是否按 key 保存 | 是 | 否，一次操作结束即可 |
| 是否依赖后端 | 本身是 Store | 依附 Gloo ProcessGroup |

可以这样理解：

- TCPStore 是“公告栏”：发布配置、登记状态、等待某个 key 出现；
- Gloo ProcessGroup 是“通信团队”：定义哪些 Rank 可以通信；
- Gloo broadcast 是“团队广播”：把一个 Rank 的 Tensor 复制给所有成员。

## 九、TCPStore 如何参与 Gloo 或 NCCL 初始化

初始化大致分两步：

1. 各 Rank 通过 Store 交换通信器创建所需的少量元数据；
2. 后端建立通信器，使用 Gloo 传输 CPU Tensor，或者使用 NCCL 传输 GPU Tensor。

初始化完成以后，`broadcast`、`all_reduce` 等操作不会通过 `store.set()` 和 `store.get()` 传输 Tensor。

也可以显式把 TCPStore 和 Gloo 连接起来：

```python
import os
from datetime import timedelta

import torch
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

tensor = torch.tensor([rank])
dist.broadcast(tensor, src=0)
print(f"rank {rank}: {tensor.item()}")

dist.destroy_process_group()
```

这里 TCPStore 只负责帮助 Gloo ProcessGroup 初始化，真正的 Tensor 广播由 Gloo 完成。如果改用 NCCL，需要把 Tensor 放到当前 CUDA 设备，并设置正确的 `LOCAL_RANK`。


## 十、为什么普通训练代码很少直接创建 TCPStore

普通 DDP 代码通常只写：

```python
dist.init_process_group(backend="nccl", init_method="env://")
```

然后用 `torchrun` 启动：

```bash
torchrun --standalone --nproc-per-node=4 train.py
```

`torchrun` 和 `env://` 已经封装了大部分 rendezvous 工作。Store 仍可能参与底层协调，只是用户不需要手工创建它。

直接使用 TCPStore 的场景主要是：

- 开发分布式训练框架或启动器；
- 自定义 rendezvous；
- 编写底层通信测试；
- 需要额外的跨进程状态协调；
- 排查分布式初始化的地址、端口和超时问题。

## 十一、FileStore、HashStore 和 PrefixStore

除了 TCPStore，PyTorch 还提供：

| Store | 共享方式 | 典型场景 |
|---|---|---|
| `TCPStore` | TCP 服务端和客户端 | 多机、多进程 |
| `FileStore` | 共享文件 | 单机测试或已有共享文件系统 |
| `HashStore` | 当前进程的内存哈希表 | 单元测试、同进程线程 |
| `PrefixStore` | 包装另一个 Store，增加 key 前缀 | 隔离模块或通信组 |

`HashStore` 不能让两个独立进程通过各自创建的对象通信；`FileStore` 只有在多个进程访问真正同一个共享文件时才适合跨机器；`PrefixStore` 不负责网络通信，只是隔离 key 命名空间：

```python
base = dist.HashStore()
train_store = dist.PrefixStore("train/", base)
eval_store = dist.PrefixStore("eval/", base)

train_store.set("status", "running")
eval_store.set("status", "finished")
```

## 十二、实际选型建议

### NVIDIA GPU 训练

```python
dist.init_process_group(backend="nccl")
```

使用 `torchrun` 启动，每个进程绑定一张 GPU。DDP、FSDP 等 GPU 训练通常选择 NCCL。

### CPU 训练或分布式逻辑测试

```python
dist.init_process_group(backend="gloo")
```

Gloo 不要求 NVIDIA GPU，适合开发机和 CI。它可以帮助验证 Rank、数据切分、collective 调用顺序和进程组生命周期。

### 传递少量状态

```python
store.set("checkpoint_ready", "1")
store.wait(["checkpoint_ready"])
```

使用 TCPStore。若传递的是 Tensor，则使用 ProcessGroup 上的 `broadcast` 或其他集合通信。

### NCCL 出错时排查

先用 Gloo 在 CPU 上验证上层逻辑。如果 Gloo 正常而 NCCL 失败，再重点检查 CUDA、GPU 可见性、网卡、容器权限、共享内存和多机网络。

## 十三、常见排障点

### 1. collective 调用顺序不一致

所有 Rank 必须以一致顺序进入匹配的集合通信。一个 Rank 执行 `broadcast`、另一个执行 `barrier`，通常会挂起。

### 2. NCCL 进程没有绑定正确 GPU

```python
local_rank = int(os.environ["LOCAL_RANK"])
torch.cuda.set_device(local_rank)
```

多个进程都使用 `cuda:0`，会造成一张卡显存爆满、其他卡没有负载。

### 3. TCPStore 地址和端口不可达

多机环境不要使用 `127.0.0.1`。检查 `MASTER_ADDR`、`MASTER_PORT`、防火墙、安全组和容器网络。

### 4. `world_size` 不一致

Store 服务端等待 4 个进程，但只启动 3 个时，初始化会一直等待直到超时。所有进程必须使用一致的 `WORLD_SIZE`，且 Rank 唯一。

### 5. torchrun 和手工 TCPStore 端口冲突

已经使用 `torchrun` 完成 rendezvous 后，不要在同一端口再启动另一个 TCPStore 服务端，否则可能出现 `address already in use`。

## 十四、总结

```text
TCPStore：进程之间的共享公告栏
ProcessGroup：已经集合好的通信团队
NCCL：面向 NVIDIA GPU 的通信实现
Gloo：通用、常用于 CPU 的通信实现
broadcast：把一个 Rank 的 Tensor 广播给所有 Rank
```

一次典型的 GPU DDP 任务可以概括为：

```text
torchrun 启动进程
        |
        v
Store 完成 rendezvous 和初始化信息交换
        |
        v
创建 NCCL ProcessGroup
        |
        v
DDP 使用 all_reduce 同步梯度
```

CPU 测试则通常把 NCCL 换成 Gloo。理解这几个层次后，就能区分“进程为什么找不到彼此”“Tensor 为什么没有同步”“端口为什么冲突”分别属于初始化、ProcessGroup、后端还是具体 collective 操作的问题。
