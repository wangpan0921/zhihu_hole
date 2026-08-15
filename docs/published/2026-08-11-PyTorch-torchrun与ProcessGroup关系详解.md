# PyTorch torchrun 与 ProcessGroup：从启动命令到真正开始训练

使用 PyTorch 做分布式训练时，我们经常会同时看到下面几个概念：

```text
torchrun
Rendezvous
TCPStore
ProcessGroup
NCCL / Gloo
DistributedDataParallel
```

这些组件经常连续出现，很容易让人误以为它们都在做同一件事。实际上，它们处在分布式训练的不同层次。

最核心的关系可以概括为：

> `torchrun` 负责启动、配置和监控训练进程；训练进程调用
> `init_process_group()` 创建 ProcessGroup；ProcessGroup 再通过 NCCL 或
> Gloo 完成真正的集合通信。

TCPStore 通常参与初始化和协调，但不负责传输模型梯度。DDP 则建立在 ProcessGroup 之上，决定训练过程中何时同步参数和梯度。

本文从一条 `torchrun` 命令出发，沿着实际调用过程解释：进程怎样启动，rank 怎样分配，Store 和 ProcessGroup 在哪里出现，以及 DDP 在什么时候真正开始通信。

## 一、先看全局调用链

从执行命令到进入训练循环，整体过程可以简化为：

```text
用户执行 torchrun
        |
        v
torchrun 解析节点数、每节点进程数和 Rendezvous 参数
        |
        v
各节点参加 Rendezvous，确定本轮训练成员
        |
        v
Elastic Agent 分配 global rank、local rank 和 world size
        |
        v
每个节点启动 nproc-per-node 个 Python 子进程
        |
        v
通过环境变量把 rank、master 地址等信息传给子进程
        |
        v
每个子进程分别执行一次 train.py
        |
        v
train.py 调用 dist.init_process_group()
        |
        v
通过 Store 交换通信初始化信息
        |
        v
创建 NCCL 或 Gloo ProcessGroup
        |
        v
DDP 检查模型并同步初始参数
        |
        v
forward / backward / 梯度 all-reduce / optimizer.step
```

这里有三个容易混淆的“开始”：

1. `torchrun` 启动子进程，只表示训练脚本开始执行；
2. `init_process_group()` 返回，表示默认通信组已经建立；
3. 进入 DDP 的 forward/backward，才表示模型真正开始分布式训练。

## 二、torchrun 是什么

`torchrun` 是 PyTorch 提供的分布式进程启动器，等价于：

```bash
python -m torch.distributed.run
```

例如在一台有 4 张 GPU 的机器上启动 4 个训练进程：

```bash
torchrun \
  --standalone \
  --nproc-per-node=4 \
  train.py
```

这条命令不是让一个 Python 进程同时控制 4 张 GPU，而是启动 4 个独立的 Python 进程：

```text
train.py 进程 0  ->  GPU 0
train.py 进程 1  ->  GPU 1
train.py 进程 2  ->  GPU 2
train.py 进程 3  ->  GPU 3
```

每个进程都有独立的 Python 解释器、CUDA context、模型、optimizer、DataLoader 和地址空间。脚本里的模块导入、模型创建和数据集创建都会执行 4 次。

`torchrun` 的主要职责包括：

- 解析单机或多机启动参数；
- 组织 Rendezvous；
- 确定 worker 数量并分配 rank；
- 设置分布式环境变量；
- 启动每个本地训练进程；
- 监控训练进程的退出状态；
- 在 elastic 模式下重启失败的 worker group。

它本身不执行梯度 `all_reduce`，也不会自动把普通模型转换成 DDP 模型。

## 三、Rendezvous：所有节点先集合

Rendezvous 可以理解为分布式任务开始前的“集合与点名”。

在多机环境中，每台机器都运行一条 `torchrun` 命令。例如两台机器，每台 8 张 GPU：

```bash
torchrun \
  --nnodes=2 \
  --nproc-per-node=8 \
  --rdzv-backend=c10d \
  --rdzv-endpoint=node0.example.com:29400 \
  --rdzv-id=train-001 \
  train.py
```

两台机器必须使用相同的 `rdzv-id`、`rdzv-backend` 和 `rdzv-endpoint`，才能加入同一次训练任务。

Rendezvous 需要回答几个问题：

- 哪些节点参加本轮训练；
- 每台机器需要启动多少个 worker；
- 全局一共有多少个 worker；
- 每个 worker 应获得什么 rank；
- 后续初始化通信时应该使用什么入口地址。

Rendezvous 属于控制面。它处理成员发现和身份分配，不传输模型参数或梯度。

在弹性训练中，如果成员发生变化，通常需要重启整个 worker group，再从检查点恢复，而不是让一个新进程直接插入正在执行的 NCCL 集合通信。

## 四、rank 是怎样分配的

假设有两台机器，每台启动 4 个进程，总进程数为 8：

| 节点 | LOCAL_RANK | RANK | WORLD_SIZE |
|---|---:|---:|---:|
| node0 | 0 | 0 | 8 |
| node0 | 1 | 1 | 8 |
| node0 | 2 | 2 | 8 |
| node0 | 3 | 3 | 8 |
| node1 | 0 | 4 | 8 |
| node1 | 1 | 5 | 8 |
| node1 | 2 | 6 | 8 |
| node1 | 3 | 7 | 8 |

几个常用概念分别表示：

| 名称 | 含义 |
|---|---|
| `LOCAL_RANK` | 进程在本机的编号，通常用于选择 GPU |
| `RANK` | 进程在整个训练任务中的全局编号 |
| `WORLD_SIZE` | 全局训练进程总数 |
| `LOCAL_WORLD_SIZE` | 当前节点启动的本地 worker 数量 |
| `GROUP_RANK` | 当前节点在 worker group 中的编号 |

`torchrun` 启动子进程时会设置环境变量：

```text
LOCAL_RANK
RANK
WORLD_SIZE
LOCAL_WORLD_SIZE
MASTER_ADDR
MASTER_PORT
TORCHELASTIC_RESTART_COUNT
```

训练脚本通常直接读取它们：

```python
import os

local_rank = int(os.environ["LOCAL_RANK"])
rank = int(os.environ["RANK"])
world_size = int(os.environ["WORLD_SIZE"])
```

不同 PyTorch 版本也可能向脚本传递 `--local-rank` 参数，但读取 `LOCAL_RANK` 环境变量是当前训练脚本中很常见的写法。

## 五、训练脚本启动后发生什么

完成 rank 分配后，`torchrun` 会创建指定数量的子进程。每个子进程都从头执行一次 `train.py`。

此时进程虽然已经运行，但它们还不一定拥有可用于张量集合通信的 ProcessGroup。训练脚本通常先绑定本地 GPU：

```python
local_rank = int(os.environ["LOCAL_RANK"])
torch.cuda.set_device(local_rank)
```

然后调用：

```python
dist.init_process_group(
    backend="nccl",
    init_method="env://",
)
```

这一步才开始创建训练使用的默认 ProcessGroup。

## 六、init_process_group 做了什么

`init_method="env://"` 表示从环境变量读取 `MASTER_ADDR`、`MASTER_PORT`、`RANK` 和 `WORLD_SIZE`。

`init_process_group()` 的过程可以概括为：

1. 读取当前进程的 rank 和 world size；
2. 找到或连接用于初始化的 Store；
3. 使用 Store 交换通信后端所需的信息；
4. 为每个进程创建默认 ProcessGroup；
5. 初始化指定的 NCCL 或 Gloo 后端；
6. 等待必要的初始化步骤完成后返回。

默认 ProcessGroup 通常包含所有训练进程：

```text
default ProcessGroup = {
    rank 0,
    rank 1,
    ...
    rank WORLD_SIZE - 1
}
```

后续不显式传入 `group` 的集合通信，默认使用这个组：

```python
dist.all_reduce(tensor)
dist.broadcast(tensor, src=0)
dist.barrier()
```

也可以建立只包含部分 rank 的子组：

```python
group = dist.new_group(ranks=[0, 1, 2, 3])
dist.all_reduce(tensor, group=group)
```

张量并行、流水线并行和数据并行的混合方案，通常会创建多个不同成员集合的 ProcessGroup。

## 七、TCPStore 在哪里出现

建立 ProcessGroup 之前，各进程必须交换少量初始化信息，例如通信器唯一 ID、rank 与设备映射、就绪状态以及建立连接所需的元数据。

TCPStore 是常用的 Store 实现之一，它提供：

```text
set(key, value)
get(key)
add(key, value)
wait(keys)
```

可以把它理解为一个用于分布式初始化的共享键值服务：

```text
rank 0                         TCPStore                    rank 1
  |                               |                          |
  | set("comm_id", value)         |                          |
  |------------------------------>|                          |
  |                               | get("comm_id")           |
  |                               |<-------------------------|
  |                               | return value             |
  |                               |------------------------->|
```

三者的职责是：

| 组件 | 主要职责 |
|---|---|
| TCPStore | 交换初始化元数据和少量控制信息 |
| ProcessGroup | 定义哪些 rank 参加通信，并提供集合通信接口 |
| NCCL/Gloo | 实现具体的数据传输和集合通信算法 |

TCPStore 不适合传输大规模模型参数，也不会在每次 backward 时同步梯度。

Rendezvous 阶段使用的 Store 与 ProcessGroup 初始化使用的 Store，在不同 PyTorch 版本和启动配置下，可能复用底层服务，也可能通过不同前缀或不同实例隔离。但从职责上应该分开理解：

- Rendezvous Store 服务于成员发现和 worker 分配；
- ProcessGroup Store 服务于通信后端初始化；
- ProcessGroup 才是训练代码使用的通信域。

## 八、NCCL 和 Gloo 是什么角色

ProcessGroup 提供统一接口：

```python
dist.broadcast(...)
dist.all_reduce(...)
dist.all_gather(...)
dist.reduce_scatter_tensor(...)
dist.barrier(...)
```

NCCL 和 Gloo 是这一抽象背后的通信后端。

### NCCL

NCCL 主要用于 NVIDIA GPU 张量通信：

```python
dist.init_process_group(backend="nccl")
```

典型场景包括单机多 GPU、多机多 GPU、DDP 梯度同步，以及 GPU 上的 all-reduce、all-gather 和 reduce-scatter。

### Gloo

Gloo 主要用于 CPU 张量通信：

```python
dist.init_process_group(backend="gloo")
```

它常用于 CPU 分布式任务、不依赖 CUDA 的测试和小规模控制通信。通常可以简单记忆：

```text
GPU 分布式训练 -> NCCL
CPU 分布式训练 -> Gloo
```

## 九、DDP 初始化阶段做了什么

创建 ProcessGroup 后，训练脚本一般会创建模型并包装为 DDP：

```python
model = MyModel().to(local_rank)
model = DDP(model, device_ids=[local_rank])
```

DDP 初始化阶段通常会：

1. 检查不同 rank 上的模型参数结构是否一致；
2. 从权威 rank 向其他 rank 同步初始参数和 buffer；
3. 为模型参数注册 autograd hook；
4. 把参数划分成若干 gradient bucket；
5. 准备在反向传播过程中触发梯度集合通信。

ProcessGroup 决定“和谁通信”，NCCL/Gloo 决定“怎样通信”，DDP 决定“训练过程中的什么时机通信”。

## 十、backward 时如何同步梯度

训练循环中的 forward 由每个 rank 独立完成：

```python
output = model(batch)
loss = criterion(output, target)
```

每个 rank 读取不同的数据分片，所以计算出的本地梯度也不同。执行 `loss.backward()` 时，DDP 注册的 autograd hook 会在梯度准备好后，按 bucket 触发 ProcessGroup 的 `all_reduce`：

```text
rank 0 的本地梯度  --+
rank 1 的本地梯度  --+--> NCCL all-reduce --> 每个 rank 获得相同的平均梯度
rank 2 的本地梯度  --+
rank 3 的本地梯度  --+
```

然后所有进程分别执行：

```python
optimizer.step()
```

虽然 optimizer 各自独立存在，但由于初始参数、同步后的梯度、optimizer 算法及超参数都相同，每个 rank 更新后的模型参数仍然相同。

DDP 并不是在 `optimizer.step()` 中同步参数。主要同步发生在 backward 阶段的梯度 all-reduce。

## 十一、一个可以运行的完整 Demo

下面是一个单机多 GPU DDP 示例：

```python
# train.py
import os

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, DistributedSampler, TensorDataset


def main():
    local_rank = int(os.environ["LOCAL_RANK"])
    rank = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])

    torch.cuda.set_device(local_rank)
    dist.init_process_group(backend="nccl", init_method="env://")

    # 每个进程都会创建模型，DDP 初始化时会同步模型状态。
    model = torch.nn.Sequential(
        torch.nn.Linear(16, 32),
        torch.nn.ReLU(),
        torch.nn.Linear(32, 2),
    ).to(local_rank)
    model = DDP(model, device_ids=[local_rank])

    features = torch.randn(1024, 16)
    labels = torch.randint(0, 2, (1024,))
    dataset = TensorDataset(features, labels)

    sampler = DistributedSampler(
        dataset,
        num_replicas=world_size,
        rank=rank,
        shuffle=True,
    )
    loader = DataLoader(
        dataset,
        batch_size=32,
        sampler=sampler,
        pin_memory=True,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    criterion = torch.nn.CrossEntropyLoss()

    for epoch in range(3):
        # 每轮使用不同但跨 rank 一致的数据切分顺序。
        sampler.set_epoch(epoch)

        for features, labels in loader:
            features = features.to(local_rank, non_blocking=True)
            labels = labels.to(local_rank, non_blocking=True)

            optimizer.zero_grad()
            output = model(features)
            loss = criterion(output, labels)
            loss.backward()
            optimizer.step()

        if rank == 0:
            print(f"epoch={epoch}, loss={loss.item():.4f}")

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
```

在一台 4 卡机器上运行：

```bash
torchrun --standalone --nproc-per-node=4 train.py
```

代码中各组件的对应关系是：

```text
torchrun
  -> 启动 4 个 train.py 进程

LOCAL_RANK
  -> 每个进程选择一张本地 GPU

init_process_group("nccl")
  -> 创建默认 NCCL ProcessGroup

DistributedSampler
  -> 让不同 rank 读取不同的数据分片

DDP
  -> 在 backward 中通过 ProcessGroup 同步梯度
```

## 十二、多机启动示例

假设：

```text
node0: 10.0.0.10，8 张 GPU
node1: 10.0.0.11，8 张 GPU
```

在两台机器上执行相同命令：

```bash
torchrun \
  --nnodes=2 \
  --nproc-per-node=8 \
  --rdzv-backend=c10d \
  --rdzv-endpoint=10.0.0.10:29400 \
  --rdzv-id=my-training-job \
  train.py
```

最终会形成：

```text
2 个 torchrun / Elastic Agent 进程
16 个 train.py worker 进程
1 个包含 16 个 rank 的默认 ProcessGroup
```

每台机器上的 `LOCAL_RANK` 都是 `0~7`，但全局 `RANK` 是 `0~15`。

## 十三、训练结束和故障重启

训练结束时，每个 worker 通常调用：

```python
dist.destroy_process_group()
```

它用于释放 ProcessGroup 及通信后端持有的资源。随后训练脚本退出，`torchrun` 的 agent 收集所有子进程的退出状态。

如果某个 worker 异常退出，在启用了重启且没有超过 `max_restarts` 时，Elastic Agent 通常会终止并重新启动整个 worker group：

```text
某个 rank 失败
      |
      v
本轮 worker group 结束
      |
      v
重新 Rendezvous 和分配 rank
      |
      v
重新启动训练脚本
      |
      v
训练代码从 checkpoint 恢复
```

elastic 提供的是进程级故障恢复能力，模型和 optimizer 状态仍然需要训练代码通过 checkpoint 保存与恢复。

## 十四、几个常见误区

### 误区一：执行 torchrun 后已经建立了 ProcessGroup

不一定。`torchrun` 负责启动训练脚本，默认训练 ProcessGroup 通常由脚本中的 `dist.init_process_group()` 创建。

### 误区二：TCPStore 负责同步梯度

TCPStore 只适合初始化元数据和少量控制信息。梯度 all-reduce 由 NCCL/Gloo ProcessGroup 执行。

### 误区三：一个进程负责所有 GPU

标准 DDP 通常采用“一张 GPU 对应一个进程”。每个进程都有一份完整模型，并处理不同的数据分片。

### 误区四：DDP 在 optimizer.step 时同步参数

DDP 的主要同步发生在 backward 阶段。各 rank 获得相同梯度后，分别执行相同的 optimizer 更新。

### 误区五：DistributedSampler 会自动切换 epoch

使用 shuffle 时，通常需要在每个 epoch 开始时调用：

```python
sampler.set_epoch(epoch)
```

否则每个 epoch 可能使用相同的打乱顺序。

## 十五、总结

完整的 PyTorch 分布式训练可以分成四层：

| 层次 | 组件 | 职责 |
|---|---|---|
| 启动与容错 | torchrun / Elastic Agent | 启动、配置、监控和重启 worker |
| 发现与协调 | Rendezvous / TCPStore | 成员发现、rank 分配、交换初始化信息 |
| 集合通信 | ProcessGroup / NCCL / Gloo | 在指定 rank 之间传输张量 |
| 训练同步 | DDP | 在模型初始化和 backward 阶段调用集合通信 |

最后用一句话串起来：

> `torchrun` 把训练进程启动起来并分配身份，Rendezvous 让各节点完成集合，
> TCPStore 帮助进程交换初始化信息，ProcessGroup 建立通信域，NCCL/Gloo
> 负责传输张量，DDP 则在模型初始化和反向传播过程中使用这些通信能力。

理解这条链路之后，再排查“某个 rank 没启动”“卡在 init_process_group”“NCCL all-reduce 超时”或“不同 GPU 数据重复”等问题时，就能先判断故障发生在启动、集合、通信初始化还是训练同步阶段。
