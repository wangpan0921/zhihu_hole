# 一文看懂 PyTorch GPU 训练中的 PCIe、NVLink 与 RDMA

用 PyTorch 做多 GPU 训练时，经常会看到三个词：`PCIe`、`NVLink` 和 `RDMA`。

有些资料会把它们放在一张带宽表里比较，于是很容易产生一个误解：它们是三种可以互相替换的 GPU 通信方案。

实际上，它们并不完全处于同一层：

- **PCIe** 是通用设备互连总线，CPU、GPU、网卡、NVMe 等设备通常都通过它连接；
- **NVLink** 是 NVIDIA 面向 GPU 高带宽互连设计的链路，常用于同一台服务器内的 GPU 之间；
- **RDMA** 是一种让设备直接读写远端内存、减少 CPU 搬运和内核参与的通信机制，主要解决跨服务器传输问题。

在一次多机多卡训练中，三者可能同时工作：GPU 先通过 NVLink 或 PCIe 在本机交换数据，跨机器时再由 RDMA 网卡传到另一台服务器；网卡本身通常仍挂在 PCIe 上。

因此，理解它们的关键不是背带宽数字，而是先问：**数据从哪里出发，要到哪里去，中间经过哪些设备？**

## 一、从一个 PyTorch 训练 step 说起

以 `DistributedDataParallel`，也就是 DDP 为例。通常一张 GPU 对应一个训练进程，每个进程保存一份完整模型，并处理不同的 mini-batch。

一个简化后的训练 step 如下：

```text
CPU 读取和预处理数据
        |
        | H2D copy
        v
GPU 执行 forward
        |
        v
GPU 执行 backward，逐步产生梯度
        |
        | NCCL all-reduce
        v
所有 GPU 得到一致的聚合梯度
        |
        v
optimizer.step() 更新参数
```

这里至少存在两类数据移动：

1. CPU 内存与 GPU 显存之间传输训练数据；
2. 不同 GPU 之间同步梯度、参数或其他 Tensor。

如果所有 GPU 在同一台服务器里，第二类通信一般走 NVLink 或 PCIe。如果 GPU 分布在多台服务器，通信还要经过网卡和交换网络，此时就可能使用 InfiniBand RDMA 或 RoCE。

PyTorch 通常不会让业务代码直接操作这些链路。我们写的是：

```python
dist.init_process_group(backend="nccl")
model = DDP(model, device_ids=[local_rank])
```

DDP 在反向传播时触发梯度 bucket 的 `all_reduce`，NCCL 再根据机器拓扑、消息大小和可用传输能力选择通信路径。

可以把软件和硬件关系简化为：

```text
PyTorch DDP / FSDP
        |
        v
ProcessGroupNCCL
        |
        v
NCCL 集合通信算法
        |
        +---- 单机：NVLink / NVSwitch / PCIe P2P
        |
        +---- 多机：InfiniBand 或 RoCE 等网络
                         |
                         +---- 普通网络路径
                         +---- GPUDirect RDMA
```

## 二、PCIe：GPU 服务器里的通用道路

PCIe，全称 Peripheral Component Interconnect Express，是服务器内部连接高速设备的通用总线。

独立 GPU 通常通过 PCIe 接入主机。网卡和 NVMe SSD 也经常接在 PCIe 上，因此下面这些流量都可能经过 PCIe：

- CPU 内存到 GPU 显存的 H2D 传输；
- GPU 显存到 CPU 内存的 D2H 传输；
- 两张 GPU 之间的 PCIe P2P 传输；
- GPU 与 RDMA 网卡之间的数据传输；
- NVMe 到主机内存，或者支持 GPUDirect Storage 时到 GPU 显存的传输。

### 1. PCIe 带宽不能只看“第几代”

PCIe 的理论带宽由代际和链路宽度共同决定。例如同为 PCIe 4.0，`x16` 和 `x8` 的上限并不相同。

此外，理论带宽不等于训练可用带宽。实际结果还会受到以下因素影响：

- GPU 实际协商到的 PCIe 代际和 lane 数；
- 两张 GPU 是否位于同一个 PCIe switch 下；
- 通信是否需要经过 CPU root complex；
- 是否跨 NUMA 节点或 CPU socket；
- 是否与网卡、NVMe 等设备共享上行链路；
- 消息大小、协议开销和并发程度。

所以“这台机器是 PCIe 4.0”只能说明一部分信息，不能直接推出 DDP 的通信性能。

### 2. PCIe P2P 是什么

如果硬件拓扑和软件配置支持，GPU 可以通过 PCIe Peer-to-Peer 直接访问另一张 GPU 的显存，不必先把数据复制到 CPU 内存。

```text
较理想的 PCIe P2P：

GPU 0 <---- PCIe switch ----> GPU 1

需要绕行主机的路径：

GPU 0 -> CPU/主机内存 -> GPU 1
```

“都插在同一台机器里”不代表 GPU 之间一定有同样好的 P2P 路径。服务器插槽布局、BIOS 设置、IOMMU/ACS 配置、虚拟化方式和容器设备映射都可能影响 P2P。

### 3. PyTorch 中哪些操作会用到 PCIe

最常见的是 DataLoader 把 batch 送到 GPU：

```python
loader = DataLoader(
    dataset,
    batch_size=128,
    num_workers=8,
    pin_memory=True,
)

for images, labels in loader:
    images = images.cuda(non_blocking=True)
    labels = labels.cuda(non_blocking=True)
```

`pin_memory=True` 让 DataLoader 返回页锁定内存中的 Tensor。配合 `non_blocking=True` 和独立 CUDA stream，H2D 复制才具备与 GPU 计算重叠的条件。

注意，“具备条件”不等于“一定已经重叠”。如果后续代码立即等待数据、CPU 预处理太慢、batch 太小，或者时间线上没有并行区间，吞吐仍然不会提高。

## 三、NVLink：GPU 之间的高带宽专用互连

PCIe 要服务许多设备，而 NVLink 更专注于 NVIDIA 加速器之间的高速通信。

在常见的单机多 GPU 服务器中，NVLink 可以带来：

- 更高的 GPU 间带宽；
- 更低的 GPU 间通信延迟；
- 更适合大规模 `all_reduce`、`all_gather` 和 `reduce_scatter`；
- 减少 GPU 间通信对 PCIe 上行链路的争用。

一些服务器还使用 NVSwitch。它可以把多张 GPU 连接成带宽更均衡的交换网络，避免只有部分 GPU 两两直连。

```text
GPU 0 ---\
GPU 1 ----\
GPU 2 ----- NVSwitch fabric
GPU 3 ----/
GPU 4 ---/
```

### 1. 有 NVLink 不等于任意两卡性能相同

不同 GPU 型号、服务器产品和 NVLink 代际的连接方式不同。某些拓扑里，一对 GPU 之间有直连 NVLink，另一对可能需要经过中间 GPU 或 NVSwitch；消费级显卡、PCIe 数据中心卡和 SXM 模组的能力也不能混为一谈。

因此不能只查 GPU 型号，还要查这台具体服务器的拓扑。

### 2. PyTorch 怎么使用 NVLink

通常不需要在 PyTorch 代码里写“使用 NVLink”。当满足以下条件时，NCCL 会发现并利用可用的 NVLink 路径：

- Tensor 位于 CUDA GPU；
- ProcessGroup 使用 NCCL；
- GPU 拓扑和 P2P 访问正常；
- NCCL 没有被环境变量或容器配置禁用相关能力。

业务代码仍然只是调用集合通信：

```python
dist.all_reduce(tensor)
```

底层到底走 NVLink、PCIe 还是其他路径，应通过拓扑、NCCL 日志和基准测试确认，而不是从这一行 Python 代码猜测。

### 3. NVLink 不能解决所有训练瓶颈

如果单卡计算占绝大多数时间，或者 DDP 已经把大部分通信隐藏在 backward 计算后面，更快的互连未必显著提升 step 吞吐。

反过来，以下场景往往更依赖 GPU 间带宽：

- 模型参数量大、每步同步的梯度多；
- 单卡计算很快，通信占比高；
- FSDP 或 ZeRO-3 频繁执行 `all_gather`、`reduce_scatter`；
- Tensor Parallel 在层内频繁通信；
- batch 较小，计算无法充分覆盖通信开销。

所以 NVLink 的价值要结合“通信量与计算量之比”判断。

## 四、RDMA：让数据直接进入远端内存

RDMA 全称 Remote Direct Memory Access，核心目标是让一台机器上的设备直接访问另一台机器已注册的内存区域，减少远端 CPU 参与、内核协议栈处理和额外内存复制。

它不是某一种线缆，也不是 PCIe 或 NVLink 的同类替代品。常见承载方式包括：

- **InfiniBand**：为高性能计算设计的网络体系，原生支持 RDMA；
- **RoCE**：RDMA over Converged Ethernet，在以太网上承载 RDMA；
- 其他支持 RDMA 语义的网络实现。

### 1. 普通跨机 GPU 通信

不使用 GPUDirect RDMA 时，一种简化路径是：

```text
GPU 0 显存
   |
   | PCIe，复制到主机内存
   v
Node 0 主机内存
   |
   | 网卡发送
   v
================ 网络 ================
   |
   v
Node 1 主机内存
   |
   | PCIe，复制到 GPU
   v
GPU 1 显存
```

这条路径存在 CPU 内存中转和额外复制，CPU、内存带宽及 PCIe 都可能成为瓶颈。

### 2. GPUDirect RDMA

NVIDIA GPUDirect RDMA 允许支持的网卡直接对 GPU 显存执行 DMA。简化后的路径是：

```text
GPU 0 显存
   |
   v
RDMA NIC 0
   |
   v
================ 网络 ================
   |
   v
RDMA NIC 1
   |
   v
GPU 1 显存
```

这里的“直接”是指不再把大块数据搬到 CPU 主机内存中转，并不表示 CPU 完全消失。CPU 仍要负责进程调度、提交通信、建立连接、处理控制逻辑和异常。

而且 GPU 与网卡通常仍通过 PCIe 拓扑相连，所以 GPUDirect RDMA 的效果也取决于 GPU 和 NIC 的物理距离：同一个 PCIe switch 下通常比跨 CPU socket 更理想。

### 3. RDMA 对 PyTorch 多机训练有什么价值

在 DDP 中，每个 backward 都可能触发多个梯度 bucket 的 `all_reduce`。在 FSDP 中，还会频繁出现 `all_gather` 和 `reduce_scatter`。节点数量越多，跨机通信越容易成为扩展瓶颈。

RDMA 和 GPUDirect RDMA 主要带来：

- 减少 CPU 内存中转和复制；
- 降低 CPU 占用；
- 降低大消息传输延迟；
- 提高跨节点 GPU 通信吞吐；
- 让 NCCL 更高效地执行跨机集合通信。

但 RDMA 也不是“打开一个开关就一定更快”。RoCE 网络的无损配置、拥塞控制、MTU、网卡固件、驱动、NCCL 版本、GPU Direct 支持、NUMA 拓扑和容器权限都可能影响最终结果。

## 五、三者究竟是什么关系

把三者放在一起对比，可以更清楚地看到它们的边界：

| 对比项 | PCIe | NVLink / NVSwitch | RDMA |
|---|---|---|---|
| 本质 | 通用设备互连总线 | NVIDIA GPU 高速互连 | 远程直接内存访问机制 |
| 常见范围 | 单机内部 | 主要是单机 GPU fabric，具体以平台为准 | 跨服务器网络 |
| 典型参与者 | CPU、GPU、NIC、NVMe | GPU、NVSwitch | 本地内存、远端内存、RDMA NIC |
| PyTorch 常见场景 | H2D/D2H、GPU P2P、GPU 到 NIC | 单机 GPU collective | 多机 GPU collective |
| 是否传输 GPU Tensor | 可以 | 可以 | 可以，GPUDirect RDMA 可直达显存 |
| 是否可能同时出现 | 是 | 是 | 是 |

最重要的一点是：**RDMA 往往没有绕开 PCIe，NVLink 也不会代替跨机网络。**

例如一台 8 卡服务器中，GPU 之间通过 NVSwitch 通信；其中某张 GPU 的数据需要发往另一台服务器时，会进入本机 RDMA 网卡，再经过 InfiniBand 或 RoCE 网络到达远端。GPU 到 NIC 的本地路径仍要受服务器 I/O 拓扑影响。

## 六、单机和多机训练的数据路径

### 场景一：单机单卡

```text
CPU 内存 -- PCIe --> GPU 显存
```

这里最值得关注的是 DataLoader、页锁定内存、H2D 带宽，以及数据复制能否与计算重叠。NVLink 和 RDMA 通常不参与训练主路径。

### 场景二：单机多卡，没有 NVLink

```text
GPU 0 <-- PCIe P2P / PCIe switch --> GPU 1
```

DDP 可以正常工作，但 GPU 排列和进程绑定会影响性能。跨 CPU socket 的 GPU 通信可能明显慢于同一 PCIe switch 下的通信。

### 场景三：单机多卡，有 NVLink 或 NVSwitch

```text
GPU 0 <-- NVLink / NVSwitch --> GPU 1 ... GPU N
```

NCCL 通常优先利用高带宽 GPU fabric。大模型梯度同步、FSDP 和张量并行更容易从中受益。

### 场景四：多机多卡，普通 TCP 网络

```text
GPU -> 主机内存 -> 普通 NIC -> TCP/IP -> 普通 NIC -> 主机内存 -> GPU
```

这种方式可以运行，但在大规模 GPU 训练中，CPU 中转、网络带宽和协议栈开销通常更明显。

### 场景五：多机多卡，GPUDirect RDMA

```text
本机 GPU -> RDMA NIC -> IB/RoCE fabric -> RDMA NIC -> 远端 GPU
```

同一节点内仍可能使用 NVLink/NVSwitch，跨节点部分使用 RDMA。NCCL 会把这些链路组合成完整的 collective 拓扑。

## 七、怎样查看服务器的真实拓扑

### 1. 查看 GPU、CPU 和网卡距离

```bash
nvidia-smi topo -m
```

常见标记会随驱动和平台有所不同，通常可能看到：

- `NV#`：GPU 之间通过若干条 NVLink 连接；
- `PIX`：路径经过单个 PCIe switch；
- `PXB`：路径经过多个 PCIe bridge；
- `PHB`：路径经过 PCIe host bridge；
- `NODE`：跨同一 NUMA 节点内的 host bridge；
- `SYS`：跨 NUMA 节点或 CPU socket，通常距离更远。

![nvidia-smi-topo](../nvidia-smi-topo-m.png)

不要机械地把标记当成性能值，最终仍应实测。但它很适合发现“某两张 GPU 特别远”或“网卡与 GPU 不在同一 NUMA 节点”等问题。

还可以查看 PCIe 树：

```bash
lspci -tv
```

查看 GPU 当前 PCIe 链路信息：

```bash
nvidia-smi --query-gpu=index,name,pcie.link.gen.current,pcie.link.width.current \
  --format=csv
```
![pcie-lane](../pcie-lane.png)

链路在空闲时可能降速节能，因此排查性能时应结合负载下的状态和硬件规格判断。

### 2. 查看 RDMA 设备

```bash
rdma link
ibv_devices
ibv_devinfo
```
![rdma-link](../rdma-link.png)

这些命令可以确认 RDMA 设备、端口和 link layer，但“能看到网卡”还不能证明 NCCL 已经走 GPUDirect RDMA。

### 3. 打开 NCCL 日志

```bash
NCCL_DEBUG=INFO \
NCCL_DEBUG_SUBSYS=INIT,GRAPH,NET \
torchrun --nproc-per-node=8 train.py
```

日志可以帮助确认：

- NCCL 发现了哪些 GPU 和网卡；
- GPU P2P 是否启用；
- 选择了 Socket 还是 IB/RDMA 网络；
- ring、tree、channel 等通信拓扑如何建立；
- 是否发生网卡、插件或 P2P 初始化失败。

不同 NCCL 版本的日志格式会变化，应以任务实际使用版本为准。

## 八、用 PyTorch 实测 all-reduce

下面的脚本可以测量 NCCL `all_reduce` 的平均延迟。它既可用于单机多卡，也可用于多机多卡。

创建 `all_reduce_bench.py`：

```python
import argparse
import os

import torch
import torch.distributed as dist


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-mb", type=int, default=256)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--iters", type=int, default=50)
    args = parser.parse_args()

    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)
    dist.init_process_group(backend="nccl")

    element_size = torch.tensor([], dtype=torch.float32).element_size()
    numel = args.size_mb * 1024 * 1024 // element_size
    tensor = torch.zeros(numel, device="cuda", dtype=torch.float32)

    for _ in range(args.warmup):
        dist.all_reduce(tensor)

    dist.barrier()
    torch.cuda.synchronize()

    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()

    for _ in range(args.iters):
        dist.all_reduce(tensor)

    end.record()
    end.synchronize()

    elapsed_ms = start.elapsed_time(end) / args.iters
    payload_gb = tensor.numel() * tensor.element_size() / 1e9
    payload_gbps = payload_gb / (elapsed_ms / 1000)

    if dist.get_rank() == 0:
        print(f"world_size: {dist.get_world_size()}")
        print(f"message:    {args.size_mb} MiB")
        print(f"latency:    {elapsed_ms:.3f} ms/all_reduce")
        print(f"payload:    {payload_gbps:.2f} GB/s")

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
```

单机 8 卡运行：

```bash
torchrun --standalone --nproc-per-node=8 \
  all_reduce_bench.py --size-mb 256
```

这里输出的 `payload` 只是“Tensor 大小除以操作时间”，便于同一环境做前后对比，**不等于物理链路带宽**。`all_reduce` 的实际传输量与 world size、ring/tree 算法和协议有关。严谨测试通常还会使用 NVIDIA 的 `nccl-tests`，分别观察算法带宽和总线带宽，并扫描多种消息大小。

测试时至少要控制这些变量：

- GPU 数量和进程到 GPU 的绑定；
- 消息大小、dtype、warmup 和迭代次数；
- 单机还是跨机；
- NCCL、CUDA、驱动和固件版本；
- 网络接口、GPU/NIC NUMA 位置；
- 机器上是否存在其他计算或网络流量。

## 九、怎样判断训练是不是通信瓶颈

不能仅凭 GPU 利用率低就判断“需要 NVLink”或“RDMA 没生效”。更可靠的方法是给一个 step 分段：

```text
取数据等待
    + H2D copy
    + forward
    + backward compute
    + collective communication
    + optimizer step
```

重点观察：

1. NCCL kernel 占整个 step 的时间比例；
2. NCCL 通信和 backward 计算有多少重叠；
3. backward 结束后还剩多少未完成通信；
4. 不同 rank 是否有明显的到达时间差；
5. 单机扩展效率正常、跨机后是否突然下降；
6. 小消息慢还是大消息带宽上不去。

可以用 PyTorch Profiler 或 Nsight Systems 查看时间线。一次 DDP step 常见的优化方向包括：

- 调整 DDP bucket，使梯度更早开始同步；
- 增大每卡有效计算量，提高计算通信比；
- 避免某个 rank 的 DataLoader 或预处理成为拖尾；
- 优化 rank、GPU、CPU NUMA 和 NIC 亲和性；
- 检查 collective 是否因为错误同步而失去重叠；
- 确认 NCCL 选择了预期的 P2P 和网络接口。

先有时间线证据，再改环境变量。盲目设置 NCCL 参数，很容易把原本正确的自动拓扑选择改坏。

## 十、几个常见误区

### 误区一：PCIe、NVLink、RDMA 三选一

它们解决的问题不同。多机训练完全可能同时经过 PCIe、NVLink 和 RDMA。

### 误区二：有 InfiniBand 就一定用了 GPUDirect RDMA

InfiniBand 说明网络具备相应能力，但还要检查 GPU、NIC、驱动、内核模块、NCCL 和容器配置。最终应看 NCCL 日志与实测结果。

### 误区三：有 NVLink，PyTorch 就一定在用

硬件链路存在，不代表 P2P 权限、进程绑定和 NCCL 拓扑都正确。虚拟机、容器和 BIOS 配置都可能改变可用路径。

### 误区四：标称带宽就是 all-reduce 带宽

链路单向带宽、双向聚合带宽、NCCL 算法带宽和业务脚本的 Tensor 大小除以耗时，是不同口径。比较数据前必须先统一定义。

### 误区五：通信慢都是网络问题

某个 rank 数据加载慢、GPU 降频、NUMA 绑定错误、collective 调用顺序不一致、消息切得太碎，都可能表现为其他 rank 在 NCCL 中等待。

### 误区六：RDMA 完全不需要 CPU

RDMA 减少的是数据面的 CPU 搬运和内核参与。连接管理、任务调度、通信提交和错误处理仍然需要 CPU。

## 十一、实际选型怎么考虑

### 单机训练

先画出 GPU 拓扑，再根据通信强度选机器：

- 普通模型、通信占比较低：PCIe 多卡可能已经足够；
- 大梯度同步、FSDP、张量并行：优先考虑 NVLink/NVSwitch；
- 数据入口慢：先优化存储、解码、DataLoader 和 H2D，不要把问题归到 GPU 互连。

### 多机训练

除了单机 GPU fabric，还要一起评估：

- 每节点 GPU 数量与网络带宽的配比；
- InfiniBand 或 RoCE 的实际可用带宽；
- 是否支持并正确启用 GPUDirect RDMA；
- GPU 与 NIC 的 PCIe/NUMA 位置；
- 交换网络是否存在超卖和拥塞；
- 作业跨节点后的扩展效率和尾延迟。

例如一台服务器有 8 张高带宽 GPU，但只有一张带宽较低的网卡，那么单机 collective 可能很快，跨机扩展却仍然受网络出口限制。

## 十二、总结

最后用三句话概括：

1. **PCIe 是服务器内部连接 GPU、CPU、网卡等设备的通用基础设施。**
2. **NVLink/NVSwitch 主要提高 GPU 之间的本地高带宽通信能力。**
3. **RDMA 主要优化跨服务器的远程内存访问，GPUDirect RDMA 进一步减少 GPU 数据经过主机内存中转。**

在 PyTorch 中，DDP、FSDP 等上层框架决定何时进行什么集合通信，NCCL 负责组织和执行 GPU collective，PCIe、NVLink 与 RDMA 则构成真正搬运数据的底层路径。

排查性能时，不要从名词或标称带宽出发，而要沿着实际数据路径逐段确认：

```text
数据在哪里？
    -> 要传到哪里？
    -> 经过哪些 GPU、PCIe switch、CPU socket 和 NIC？
    -> NCCL 实际选择了什么路径？
    -> 时间线显示瓶颈真在通信吗？
```

把这条链路搞清楚，才能判断应该优化 DataLoader、PCIe 拓扑、NVLink 通信、RDMA 网络，还是训练框架本身的计算通信重叠。
