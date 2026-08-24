# PyTorch torchrun 的 rdzv-backend：c10d、static 与其他选项

上一篇《PyTorch torchrun 与 ProcessGroup：从启动命令到真正开始训练》介绍了完整调用链：

```text
torchrun
  -> Rendezvous
  -> rank / world size
  -> init_process_group()
  -> NCCL / Gloo ProcessGroup
  -> DDP 梯度同步
```

实际进行多机演练时，经常会遇到这个参数：

```bash
--rdzv-backend=c10d
```

`rdzv` 是 rendezvous 的缩写，可以理解为“分布式节点集合与注册”。`--rdzv-backend` 决定各个 `torchrun` 节点通过什么机制互相发现、分配身份并完成启动前协调。

本文比较 `c10d`、`static`、`etcd-v2` 和旧版 `etcd`，并结合公司内部平台提供的 `MLP_*` 环境变量，解释不同后端的使用场景和排错方法。

## 一、rdzv-backend 解决什么问题

假设有两台机器，每台启动两个训练进程：

```text
node0: local rank 0, local rank 1
node1: local rank 0, local rank 1
```

训练脚本执行 `init_process_group()` 之前，系统必须先知道：

- 哪些节点参加本次任务；
- 总共有多少个 worker；
- 当前节点和进程应该获得什么 rank；
- 哪个地址和端口用于初始化；
- 所需节点是否都已到达。

`rdzv-backend` 就是完成这一步的协调机制。

它只负责启动阶段的控制面，不负责训练期间的梯度通信：

```text
rdzv-backend
  -> 成员发现、rank 分配、启动协调

ProcessGroup / NCCL / Gloo
  -> barrier、broadcast、all-reduce、梯度同步
```

因此，`--rdzv-backend=c10d` 不表示训练使用 c10d 传输梯度。训练使用哪个 ProcessGroup 后端，仍由训练代码决定：

```python
dist.init_process_group(backend="nccl")
```

## 二、PyTorch 内置的 rdzv-backend

常见内置选项如下：

| 选项 | 协调机制 | 支持弹性成员 | 适合场景 |
|---|---|---|---|
| `static` | 固定 master 地址、端口和 node rank | 否 | 固定规模、多机平台、传统 DDP |
| `c10d` | PyTorch C10d Store，通常基于 TCPStore | 是 | 不想单独部署 etcd 的多机任务 |
| `etcd-v2` | 外部 etcd 服务 | 是 | 已有高可用 etcd 集群的生产环境 |
| `etcd` | 旧版 etcd rendezvous handler | 是 | 兼容旧部署，不建议新项目使用 |

PyTorch 还允许框架或平台注册自定义 rendezvous backend，不过普通训练一般不需要。

不同 PyTorch 版本的默认值和 etcd 支持细节可能变化。可以先查看当前版本的参数：

```bash
torchrun --help
```

## 三、c10d 是什么意思

`c10d` 是 PyTorch 分布式通信基础设施的名称。在 `torchrun` 中，c10d rendezvous backend 使用 PyTorch 自己的 Store 保存 rendezvous 状态，常见底层实现是 TCPStore。

可以把它理解为：

```text
node0 torchrun  \
node1 torchrun   +--> c10d rendezvous store
node2 torchrun  /
```

各节点把自己的信息写入 Store，再读取本轮 worker group 的成员和 rank。达到 `--nnodes` 要求后，rendezvous 才会完成。

### c10d 的典型命令

两台机器、每台两张 GPU：

```bash
torchrun \
  --nnodes=2 \
  --nproc-per-node=2 \
  --rdzv-backend=c10d \
  --rdzv-endpoint=node0.example.com:29400 \
  --rdzv-id=job-20260814 \
  train.py
```

两台机器通常执行相同命令。各节点上的 `torchrun` agent 都连接：

```text
node0.example.com:29400
```

然后由 rendezvous 自动确定节点和进程的全局 rank，一般不需要显式传入 `--node-rank`。

### c10d 的优点

- 不需要额外部署 etcd；
- 和 PyTorch 分布式栈集成紧密；
- 支持 elastic rendezvous；
- 适合临时集群和多数普通多机训练。

### c10d 的前提

- `--rdzv-endpoint` 必须是所有节点都能访问的地址；
- 端口必须开放且不能被其他任务占用；
- 同一任务的节点必须使用相同 `--rdzv-id`；
- 固定 `--nnodes=2` 时，两个节点都必须加入；
- 不同任务不应该误用相同的 rendezvous ID。

### c10d 是否一定代表弹性训练

不一定。c10d 说明“使用什么 rendezvous backend”，节点数是否允许变化还取决于 `--nnodes`。

固定节点数：

```bash
--nnodes=2
```

允许节点数在一个范围内变化：

```bash
--nnodes=1:4
```

即使允许范围变化，训练代码也要正确保存 checkpoint，作业平台也要支持 worker group 重启，才能获得完整的弹性恢复能力。

## 四、static 是什么

`static` 是固定拓扑的 rendezvous 方式。它不需要动态发现节点，而是直接告诉每个节点：

- 总节点数；
- 当前节点编号；
- master 节点地址；
- master 监听端口。

node0 的命令：

```bash
torchrun \
  --rdzv-backend=static \
  --nnodes=2 \
  --nproc-per-node=2 \
  --node-rank=0 \
  --master-addr=node0.example.com \
  --master-port=29500 \
  train.py
```

node1 的命令：

```bash
torchrun \
  --rdzv-backend=static \
  --nnodes=2 \
  --nproc-per-node=2 \
  --node-rank=1 \
  --master-addr=node0.example.com \
  --master-port=29500 \
  train.py
```

两台机器的 master 地址、端口和节点总数必须一致，只有 `--node-rank` 不同。

### static 的优点

- 参数直接，行为容易预测；
- 不需要 `rdzv-id`；
- 很适合平台已经分配好节点角色的场景；
- 容易和 `MASTER_ADDR`、`MASTER_PORT` 等环境变量对接。

### static 的限制

- 节点数量固定；
- 每个节点必须知道自己的 node rank；
- 两个节点不能错误地使用同一个 node rank；
- 不提供动态成员发现；
- 节点失败后通常需要整组重启。

## 五、为什么公司内部平台适合 static

很多内部机器学习平台在调度阶段已经确定节点集合，并注入类似下面的环境变量：

```bash
MLP_WORKER_0_HOST
MLP_WORKER_0_PORT
MLP_ROLE_INDEX
MLP_WORKER_NUM
```

它们通常可以映射为：

| 平台变量 | 常见含义 | torchrun 参数 |
|---|---|---|
| `MLP_WORKER_0_HOST` | 第 0 个节点的地址 | `--master-addr` |
| `MLP_WORKER_0_PORT` | 第 0 个节点的端口 | `--master-port` |
| `MLP_ROLE_INDEX` | 当前节点编号 | `--node-rank` |
| `MLP_WORKER_NUM` | 节点总数或平台定义的 worker 数 | 通常对应 `--nnodes`，需确认平台语义 |

因此可以使用：

```bash
export MASTER_ADDR="$MLP_WORKER_0_HOST"
export MASTER_PORT="$MLP_WORKER_0_PORT"

echo "ROLE_INDEX=$MLP_ROLE_INDEX"
echo "MASTER_ADDR=$MASTER_ADDR"
echo "MASTER_PORT=$MASTER_PORT"
echo "MLP_WORKER_NUM=$MLP_WORKER_NUM"

torchrun \
  --rdzv-backend=static \
  --nnodes=2 \
  --nproc-per-node=2 \
  --node-rank="$MLP_ROLE_INDEX" \
  --master-addr="$MASTER_ADDR" \
  --master-port="$MASTER_PORT" \
  /high_perf_store2/users/wangpan6/train.py
```

这条命令正常的关键是平台提供了真实可达的 master 地址、端口和节点编号，而且每个节点实际只启动两个训练进程。

如果确认 `MLP_WORKER_NUM` 表示节点数，也可以使用：

```bash
--nnodes="$MLP_WORKER_NUM"
```

但有的平台把 worker 表示为进程而不是节点，所以必须先确认变量定义。

## 六、static 与 c10d 的直接对比

| 对比项 | static | c10d |
|---|---|---|
| 节点编号 | 显式提供 `--node-rank` | 通常由 rendezvous 分配 |
| 初始化入口 | `--master-addr/port` | `--rdzv-endpoint` |
| 任务 ID | 通常不需要 | 使用 `--rdzv-id` |
| 成员发现 | 固定配置 | 通过 Store 集合 |
| 节点数量 | 固定 | 可固定，也可配置范围 |
| 外部 etcd | 不需要 | 不需要 |
| 典型平台 | 已分配固定角色的内部平台 | 通用多机和弹性任务 |

最容易混淆的是两组参数：

```text
static:
  --master-addr
  --master-port
  --node-rank

c10d:
  --rdzv-backend=c10d
  --rdzv-endpoint
  --rdzv-id
```


## 七、etcd-v2 是什么

`etcd-v2` 使用外部 etcd 服务保存 rendezvous 状态。它适合已有 etcd 集群，并希望多个训练任务共享稳定协调服务的环境。

```bash
torchrun \
  --nnodes=2 \
  --nproc-per-node=2 \
  --rdzv-backend=etcd-v2 \
  --rdzv-endpoint=etcd.example.com:2379 \
  --rdzv-id=job-20260814 \
  train.py
```

使用前需要确认：

- etcd 对所有训练节点可达；
- etcd 服务启用了对应 API；
- 不同任务使用不同的 `rdzv-id`；
- 认证、TLS 和网络策略正确；
- 当前 PyTorch 与服务端 API 兼容。

### 什么时候使用 etcd-v2

适合：

- 已有高可用 etcd 集群；
- 多个任务需要统一的协调服务；
- 平台希望 rendezvous 服务独立于训练节点；
- 有能力维护 etcd 的认证、监控和可用性。

不适合：

- 临时两机 Demo；
- 没有 etcd 运维能力；
- 平台已经直接提供 master 地址和 node rank。

普通 DDP 训练没有必要仅因为 etcd 看起来更“生产级”就额外引入它。

## 八、旧版 etcd 选项

`etcd` 是较早的 rendezvous backend，主要用于兼容已有部署。新项目通常优先考虑：

```bash
--rdzv-backend=etcd-v2
```

而不是：

```bash
--rdzv-backend=etcd
```

如果平台已有依赖旧版 `etcd` handler 的模板，应确认 PyTorch 版本、etcd API、服务端配置和认证方式。不要只改 backend 名称就直接上线。

## 九、standalone 与 c10d 的关系

单机 Demo 经常使用：

```bash
torchrun --standalone --nproc-per-node=4 train.py
```

`--standalone` 是单机快捷配置。torchrun 会自动选择本机 rendezvous 地址和端口，并生成一次性任务标识，底层通常使用 c10d rendezvous。

它适合单机多 GPU和本地调试，不适合多机任务或要求固定 master 地址的内部平台。

不要把自动管理 rendezvous 的：

```bash
torchrun --standalone ...
```

与手工指定多机 endpoint 的：

```bash
torchrun --rdzv-endpoint=node0:29400 ...
```

混为一谈。

## 十、为什么通用 c10d 示例在内部平台失败

原来的通用示例是：

```bash
torchrun \
  --nnodes=2 \
  --nproc-per-node=8 \
  --rdzv-backend=c10d \
  --rdzv-endpoint=10.0.0.10:29400 \
  --rdzv-id=my-training-job \
  train.py
```

它在内部平台失败，常见原因包括：

### 1. endpoint 只是示例地址

`10.0.0.10` 必须替换为所有节点都能访问的真实地址。

### 2. 端口不可达

如果 `29400` 被防火墙拦截、没有暴露或已被占用，c10d rendezvous 会超时。

### 3. 每节点进程数不匹配

平台每个节点只分配两张 GPU，却设置：

```bash
--nproc-per-node=8
```

可能出现 CUDA device ordinal 错误、NCCL 初始化失败或资源超限。

### 4. 平台已经固定了节点角色

平台已经通过 `MLP_ROLE_INDEX` 告诉每台机器自己的 node rank。这种固定拓扑天然适合 static，没有必要再依赖动态成员发现。

### 5. rendezvous ID 冲突

多个任务复用同一个 `rdzv-id`，可能导致任务互相等待或状态混淆。

## 十一、static 的排错清单

static 虽然简单，仍要满足：

```text
node0 的 node-rank 是 0
node1 的 node-rank 是 1
所有节点的 nnodes 相同
所有节点的 master 地址和端口相同
nproc-per-node 与节点实际资源匹配
```

尤其不要让两个节点都使用：

```bash
--node-rank=0
```

启动前可以打印：

```bash
hostname
echo "ROLE_INDEX=$MLP_ROLE_INDEX"
echo "MASTER_ADDR=$MLP_WORKER_0_HOST"
echo "MASTER_PORT=$MLP_WORKER_0_PORT"
nvidia-smi -L
```

如果平台允许，可以从非 master 节点测试连通性：

```bash
nc -vz "$MLP_WORKER_0_HOST" "$MLP_WORKER_0_PORT"
```

## 十二、如何选择

| 场景 | 推荐方式 |
|---|---|
| 单机多 GPU 调试 | `--standalone` |
| 公司平台固定分配多机和角色 | `static` |
| 通用多机训练，不想部署 etcd | `c10d` |
| 需要弹性成员发现 | `c10d` |
| 已有外部高可用 etcd | `etcd-v2` |
| 维护旧任务兼容性 | `etcd` |

简单决策过程是：

```text
平台是否已经提供 master 地址、端口和 node rank？
        |
    是  |  否
        |
     static
          \
           是否需要动态成员发现？
                  |
             否   |   是
                  |
               c10d
                    \
                     是否已有统一 etcd 基础设施？
                            |
                       是   |   否
                            |
                        etcd-v2  c10d
```

## 十三、与 ProcessGroup 的关系

无论使用哪一种 rendezvous backend，训练代码通常不变：

```python
import os
import torch
import torch.distributed as dist

local_rank = int(os.environ["LOCAL_RANK"])
torch.cuda.set_device(local_rank)

dist.init_process_group(
    backend="nccl",
    init_method="env://",
)
```

变化的是训练脚本启动前的成员发现方式；不变的是后续链路：

```text
rdzv-backend
  -> 进程集合与身份分配

init_process_group
  -> 创建默认 ProcessGroup

NCCL / Gloo
  -> 执行集合通信

DDP
  -> 在 backward 阶段同步梯度
```

把 c10d 换成 static，并不意味着把 NCCL 换成了其他通信后端。它只改变“训练进程如何先找到彼此”。

## 十四、总结

`--rdzv-backend` 选择的是 torchrun 的 rendezvous 机制：

- `c10d`：使用 PyTorch C10d Store，通常基于 TCPStore，适合通用多机和弹性任务；
- `static`：固定 master 地址、端口和 node rank，适合内部固定拓扑平台；
- `etcd-v2`：使用外部 etcd，适合已有高可用 etcd 基础设施；
- `etcd`：旧版兼容选项，新项目一般不优先；
- 自定义 backend：供框架和平台开发者扩展，普通训练不需要。

公司内部平台使用下面的方式正常运行：

```bash
torchrun \
  --rdzv-backend=static \
  --nnodes=2 \
  --nproc-per-node=2 \
  --node-rank="$MLP_ROLE_INDEX" \
  --master-addr="$MLP_WORKER_0_HOST" \
  --master-port="$MLP_WORKER_0_PORT" \
  train.py
```

根本原因是平台已经提供了真实可达的 master 地址、端口和节点编号，而且每个节点实际只需要启动两个 worker。相比之下，通用 c10d 示例中的 endpoint 和每节点 GPU 数量只是演示假设，不能直接照搬到内部平台。
