# 火山机器学习平台入门：GPU 卡、Worker、Rank 到底是什么意思

刚开始用火山机器学习平台跑训练任务时，最容易被几个词绕晕：

- GPU 卡
- Worker
- Rank
- World Size
- Local Rank
- Master

这些词经常一起出现，尤其是跑 PyTorch 分布式训练时，平台配置里要填实例数、每个实例几张 GPU，代码里又要读 `RANK`、`LOCAL_RANK`、`WORLD_SIZE`。如果没有先把这些概念分清楚，很容易出现“申请了 8 张卡但只用了一张”“每个进程都抢同一张 GPU”“日志重复打印 8 份”“保存了 8 份模型”等问题。

这篇用尽量通俗的方式解释这些概念。

## 一、先把层级关系想清楚

可以先记住一个简单层级：

```text
一个训练任务
  └── 多个 Worker
        └── 每个 Worker 上有若干张 GPU 卡
              └── 每张 GPU 通常对应一个训练进程
                    └── 每个训练进程有一个 Rank
```

如果把训练任务比作一个工地：

- 训练任务：整个工程；
- Worker：一台参与干活的机器，或者一个训练实例；
- GPU 卡：这台机器上的工人；
- Rank：每个工人的编号；
- Master：负责协调大家集合、通信的那个地址。

真实平台上的叫法可能会有“实例”“节点”“副本”“Worker”等差异，但理解上可以先按这个模型看。

## 二、GPU 卡是什么

GPU 卡就是实际执行深度学习计算的硬件资源。

比如你在平台上选择：

```text
1 个 Worker，每个 Worker 4 张 GPU
```

可以理解为：平台给你的训练任务分配了一台机器，这台机器上有 4 张可用 GPU。

如果你选择：

```text
2 个 Worker，每个 Worker 4 张 GPU
```

总 GPU 数就是：

```text
2 × 4 = 8 张 GPU
```

这里有一个新手常见误区：

> 申请了多张 GPU，不代表代码会自动使用所有 GPU。

如果你的训练代码只是普通单进程代码，比如：

```python
model.to("cuda")
```

它通常只会使用一张 GPU，常见是当前进程看到的 `cuda:0`。

要真正用多张 GPU，通常需要：

- 使用分布式训练框架，例如 PyTorch DistributedDataParallel；
- 或者使用平台/框架封装好的分布式启动方式；
- 确保每张 GPU 对应合适的训练进程。

## 三、Worker 是什么

Worker 可以理解为参与训练的一台机器，或者一个训练实例。

在云上机器学习平台里，训练任务通常不是你手工登录一台机器运行命令，而是提交一个任务，让平台帮你拉起一个或多个 Worker。

比如：

```text
Worker 数：1
每个 Worker GPU 数：8
```

这是单机 8 卡训练。

再比如：

```text
Worker 数：4
每个 Worker GPU 数：8
```

这是 4 机 32 卡训练。

它们的区别是：

| 配置 | 含义 | 常见叫法 |
|---|---|---|
| 1 个 Worker × 1 张 GPU | 单机单卡 | single GPU |
| 1 个 Worker × 多张 GPU | 单机多卡 | single node multi GPU |
| 多个 Worker × 每个多张 GPU | 多机多卡 | multi node multi GPU |

所以 Worker 解决的是“有几台机器一起训练”的问题；GPU 卡解决的是“每台机器上有几张卡”的问题。

## 四、Rank 是什么

Rank 是分布式训练里每个训练进程的编号。

注意这里说的是“进程编号”，不是 GPU 编号，也不是 Worker 编号。

如果一个任务总共启动了 8 个训练进程，那么它们的全局 Rank 通常是：

```text
0, 1, 2, 3, 4, 5, 6, 7
```

每个进程都有一个唯一的全局编号，这个编号就叫 **global rank**，通常环境变量名是：

```text
RANK
```

总进程数叫 **world size**，通常环境变量名是：

```text
WORLD_SIZE
```

比如：

```text
WORLD_SIZE=8
RANK=0
RANK=1
...
RANK=7
```

可以理解为：

- `WORLD_SIZE`：总共有多少个训练进程；
- `RANK`：我是第几个训练进程。

## 五、Local Rank 又是什么

`RANK` 是全局编号，`LOCAL_RANK` 是当前 Worker 内部的编号。

比如有 2 个 Worker，每个 Worker 4 张 GPU：

```text
Worker 0:
  GPU 0 -> global rank 0, local rank 0
  GPU 1 -> global rank 1, local rank 1
  GPU 2 -> global rank 2, local rank 2
  GPU 3 -> global rank 3, local rank 3

Worker 1:
  GPU 0 -> global rank 4, local rank 0
  GPU 1 -> global rank 5, local rank 1
  GPU 2 -> global rank 6, local rank 2
  GPU 3 -> global rank 7, local rank 3
```

这里可以看到：

- `RANK` 在整个任务里唯一；
- `LOCAL_RANK` 只在当前 Worker 内唯一；
- 不同 Worker 上可以有相同的 `LOCAL_RANK`。

为什么 `LOCAL_RANK` 很重要？

因为它通常用来绑定当前进程应该使用哪张 GPU：

```python
torch.cuda.set_device(local_rank)
```

如果 4 个进程都没有正确设置 `LOCAL_RANK`，它们可能都去抢 `cuda:0`，结果就是：

- 第 0 张卡显存爆了；
- 其他卡几乎没用；
- 你以为自己在多卡训练，实际只有一张卡在忙。

## 六、Master 是什么

分布式训练的多个进程需要先互相找到对方，才能组成一个通信组。

通常会用两个环境变量：

```text
MASTER_ADDR
MASTER_PORT
```

它们表示：

- `MASTER_ADDR`：主节点地址；
- `MASTER_PORT`：主节点通信端口。

可以把 Master 理解成集合地点。所有训练进程启动后，都先去这个地址“报到”，然后建立通信关系。

在云上平台里，这些环境变量很多时候由平台或分布式启动器自动注入。你不一定要手动设置，但要知道它们的作用。一旦出现多机训练卡住、初始化超时、进程互相找不到，排查时就要看这些变量是否正确。

## 七、一个具体例子：2 个 Worker，每个 4 张 GPU

假设平台上配置：

```text
Worker 数：2
每个 Worker GPU 数：4
```

那么总 GPU 数：

```text
2 × 4 = 8
```

通常会启动 8 个训练进程：

```text
WORLD_SIZE=8
```

全局 Rank 分布：

```text
Worker 0: RANK 0, 1, 2, 3
Worker 1: RANK 4, 5, 6, 7
```

每台 Worker 内部的 Local Rank：

```text
Worker 0: LOCAL_RANK 0, 1, 2, 3
Worker 1: LOCAL_RANK 0, 1, 2, 3
```

所以不要把 `RANK` 和 `LOCAL_RANK` 混为一谈。

一个常见判断方式：

```text
local_rank 用来选本机 GPU
rank 用来判断全局身份
world_size 表示总进程数
```

## 八、PyTorch 代码里通常怎么用

下面是一个简化版示例：

```python
import os
import torch
import torch.distributed as dist


def setup_distributed():
    rank = int(os.environ["RANK"])
    local_rank = int(os.environ["LOCAL_RANK"])
    world_size = int(os.environ["WORLD_SIZE"])

    torch.cuda.set_device(local_rank)

    dist.init_process_group(
        backend="nccl",
        init_method="env://",
        rank=rank,
        world_size=world_size,
    )

    return rank, local_rank, world_size
```

这里几件事很关键：

1. 从环境变量读取 `RANK`、`LOCAL_RANK`、`WORLD_SIZE`；
2. 用 `LOCAL_RANK` 绑定当前进程使用哪张 GPU；
3. 用 `RANK` 和 `WORLD_SIZE` 初始化分布式通信；
4. GPU 训练一般用 `nccl` 后端。

模型通常会这样包一层：

```python
model = model.cuda()
model = torch.nn.parallel.DistributedDataParallel(
    model,
    device_ids=[local_rank],
    output_device=local_rank,
)
```

这表示当前进程只负责当前 `local_rank` 对应的 GPU。

## 九、为什么只有 rank 0 保存模型

分布式训练时，每个 Rank 都会跑一份训练代码。

如果代码里写：

```python
torch.save(model.state_dict(), "model.pt")
```

那么 8 个 Rank 可能同时保存模型：

```text
rank 0 保存一次
rank 1 保存一次
...
rank 7 保存一次
```

这会带来几个问题：

- 日志重复；
- 文件互相覆盖；
- 存储压力变大；
- checkpoint 状态混乱。

所以通常只让 global rank 0 做这些全局动作：

```python
if rank == 0:
    torch.save(model.module.state_dict(), "model.pt")
```

常见只在 rank 0 做的事情包括：

- 保存 checkpoint；
- 打印总进度日志；
- 上传最终模型；
- 写 TensorBoard 主日志；
- 做最终评估汇总。

注意：这里应该判断 `rank == 0`，而不是 `local_rank == 0`。

因为多机多卡时，每个 Worker 都有一个 `local_rank == 0` 的进程。如果用 `local_rank == 0` 保存模型，就会每台机器都保存一次。

## 十、数据集为什么也要按 Rank 切分

分布式训练不是让每个 Rank 都重复训练同一批数据，而是把数据分给不同 Rank。

PyTorch 里常见写法是：

```python
from torch.utils.data.distributed import DistributedSampler

sampler = DistributedSampler(dataset)

dataloader = DataLoader(
    dataset,
    batch_size=batch_size,
    sampler=sampler,
)
```

`DistributedSampler` 会根据 `world_size` 和 `rank` 把数据切开，让每个进程拿到不同的一部分。

如果不用它，可能出现：

- 8 张卡都在训练同一批数据；
- 看起来 batch size 变大了，实际有效数据没有增加；
- 指标不稳定；
- 训练速度提升不明显。

每个 epoch 还通常需要：

```python
sampler.set_epoch(epoch)
```

这样每一轮的数据 shuffle 才能在各个 Rank 之间保持一致。

## 十一、平台配置和代码配置要对上

使用火山机器学习平台这类云上训练平台时，常见配置大概是：

```text
Worker 数
每个 Worker 的 GPU 数
启动命令
镜像
数据路径
输出路径
环境变量
```

代码里通常关心：

```text
RANK
LOCAL_RANK
WORLD_SIZE
MASTER_ADDR
MASTER_PORT
CUDA_VISIBLE_DEVICES
```

两边要对得上。

比如平台分配的是：

```text
2 个 Worker × 每个 4 张 GPU
```

代码或启动器就应该让分布式训练感知到：

```text
WORLD_SIZE=8
每个 Worker 启动 4 个训练进程
每个进程绑定 1 张 GPU
```

如果平台给了 8 张 GPU，但启动命令只启动 1 个进程，最终还是单进程训练。

## 十二、常见问题排查

### 1. 申请了多张 GPU，但只有一张在跑

重点检查：

```bash
echo $WORLD_SIZE
echo $RANK
echo $LOCAL_RANK
nvidia-smi
```

再看启动方式是不是只启动了一个 Python 进程。

单纯写：

```bash
python train.py
```

通常不是多卡分布式训练。

PyTorch 常见启动方式是类似：

```bash
torchrun --nproc_per_node=4 train.py
```

多机时还要包含节点数、节点编号、master 地址等参数，或者使用平台封装好的分布式启动能力。

### 2. 每个进程都占用 cuda:0

重点检查代码里有没有：

```python
torch.cuda.set_device(local_rank)
```

以及模型是否按 local rank 放到了正确设备。

### 3. 日志打印很多份

这是正常现象，因为每个 Rank 都在跑同一份代码。

如果只想打印一份：

```python
if rank == 0:
    print("training started")
```

### 4. checkpoint 保存了很多份

检查是不是用了：

```python
if local_rank == 0:
    save()
```

多机训练中这通常不够，应该用：

```python
if rank == 0:
    save()
```

### 5. 多机训练一直卡在初始化

重点检查：

```text
MASTER_ADDR
MASTER_PORT
RANK
WORLD_SIZE
```

还要确认不同 Worker 之间网络是否能互通，端口是否可用，所有 Worker 的训练进程是否都正常启动。

## 十三、一张速查表

| 概念 | 通俗理解 | 常见变量 |
|---|---|---|
| GPU 卡 | 负责计算的硬件 | `CUDA_VISIBLE_DEVICES` |
| Worker | 一台参与训练的机器/实例 | `NODE_RANK` 或平台内部变量 |
| Rank | 全局训练进程编号 | `RANK` |
| Local Rank | 当前 Worker 内部的进程编号 | `LOCAL_RANK` |
| World Size | 总训练进程数 | `WORLD_SIZE` |
| Master | 分布式训练集合地址 | `MASTER_ADDR` / `MASTER_PORT` |

再记一条最实用的：

```text
总 GPU 数 = Worker 数 × 每个 Worker 的 GPU 数
通常总训练进程数 = 总 GPU 数
WORLD_SIZE 通常等于总训练进程数
LOCAL_RANK 通常用来选择本机 GPU
RANK 通常用来判断全局身份
```

## 十四、小结

用火山机器学习平台跑 GPU 训练时，不要只看“申请了几张卡”。更关键的是理解资源和进程之间的关系：

1. Worker 是机器/实例维度；
2. GPU 卡是计算硬件维度；
3. Rank 是训练进程维度；
4. Local Rank 用来绑定本机 GPU；
5. World Size 表示总共有多少个训练进程；
6. Master 地址用于让所有进程建立通信。

如果只是单机单卡训练，这些概念可以先不用深究；但一旦进入单机多卡或多机多卡训练，就必须把它们分清楚。多数分布式训练问题，不是模型代码本身错了，而是 Worker、GPU、Rank、启动进程数这几件事没有对齐。
