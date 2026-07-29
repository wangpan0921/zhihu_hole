# GPU 监控技术栈基础：DCGM、DCGM Exporter、Prometheus 与 Grafana

上一篇介绍了 GPU 利用率、显存、SM Activity、PCIe、Tensor Activity、温度和功率等指标。本篇继续回答一个更工程化的问题：**这些数据是怎样从 GPU 一路走到监控面板上的？**

常见的 GPU 监控方案由 DCGM、DCGM Exporter、Prometheus 和 Grafana 组成。四个名字放在一起容易让新手觉得复杂，其实它们的职责非常清楚：

```text
GPU 和驱动
    ↓ 读取硬件遥测数据
DCGM
    ↓ 提供统一指标接口
DCGM Exporter
    ↓ 暴露为 /metrics 文本接口
Prometheus
    ↓ 定时采集、保存和查询
Grafana
    ↓
仪表盘、趋势图和告警视图
```

一句话概括：**DCGM 负责懂 GPU，Exporter 负责翻译，Prometheus 负责记账和查询，Grafana 负责展示。**

## 1. DCGM：读取和管理 NVIDIA GPU

DCGM 的全称是 NVIDIA Data Center GPU Manager。它是 NVIDIA 面向数据中心 GPU 提供的一套管理与监控能力，可以从驱动和硬件中读取 GPU 状态，也能执行健康检查、诊断和部分策略管理。

DCGM 能接触到的信息大致包括：

- GPU 利用率、显存使用量、温度、功率和时钟频率；
- PCIe、NVLink 等互联状态和流量；
- SM、Tensor、FP16、FP32、FP64 等 profiling 指标；
- ECC 错误、XID 错误、掉卡等健康信息；
- GPU 型号、UUID、MIG 实例等设备信息。

### Field ID 是什么

DCGM 用 Field ID 标识不同指标。例如：

| DCGM 字段 | 含义 |
| --- | --- |
| `DCGM_FI_DEV_GPU_UTIL` | GPU 利用率 |
| `DCGM_FI_DEV_FB_USED` | 已使用的帧缓冲显存，通常以 MiB 表示 |
| `DCGM_FI_DEV_GPU_TEMP` | GPU 温度 |
| `DCGM_FI_DEV_POWER_USAGE` | GPU 功率 |
| `DCGM_FI_PROF_SM_ACTIVE` | SM Activity |
| `DCGM_FI_PROF_PIPE_TENSOR_ACTIVE` | Tensor Activity |

可以把 Field ID 理解成 DCGM 字典中的“指标名字”。程序按名字请求，DCGM 负责从相应的驱动接口或硬件计数器取得数据。

### DCGM 不负责什么

DCGM 主要负责设备遥测、诊断和管理。它不是专门的长期时序数据库，也不会自己生成完整的 Grafana 仪表盘。如果需要回看昨天的 GPU 利用率，必须把数据交给 Prometheus 一类的监控系统保存。

### dcgmi 是什么

`dcgmi` 是 DCGM 的命令行工具。管理员可以用它发现 GPU、查看字段、运行诊断和检查健康状态。它适合临时排查；持续采集通常交给 DCGM Exporter。

## 2. DCGM Exporter：把 DCGM 指标翻译成 Prometheus 格式

DCGM 能理解 GPU，但 Prometheus 不会直接调用 DCGM API。两者之间需要一个转换层，这就是 DCGM Exporter。

DCGM Exporter 会从 DCGM 读取选定字段，再启动一个 HTTP 服务，把指标暴露在 `/metrics` 路径。返回内容大致如下：

```text
# HELP DCGM_FI_DEV_GPU_UTIL GPU utilization
# TYPE DCGM_FI_DEV_GPU_UTIL gauge
DCGM_FI_DEV_GPU_UTIL{gpu="0",UUID="GPU-...",modelName="..."} 87

# HELP DCGM_FI_DEV_GPU_TEMP GPU temperature
# TYPE DCGM_FI_DEV_GPU_TEMP gauge
DCGM_FI_DEV_GPU_TEMP{gpu="0",UUID="GPU-...",modelName="..."} 68
```

每条数据由三部分组成：

- `DCGM_FI_DEV_GPU_UTIL` 是指标名；
- `{gpu="0",UUID="..."}` 是标签，用于区分设备；
- `87` 是当前值。

### 为什么叫 Exporter

Prometheus 生态把“从某个系统读取数据，并以 Prometheus 格式对外提供”的程序称为 Exporter。它通常不负责长期保存数据，也不会主动把历史数据写进 Grafana；它只是把当前数据准备好，等待 Prometheus 来取。

DCGM Exporter 常使用 `9400` 端口，部署时可以修改。验证它是否工作，最直接的方法是访问：

```bash
curl http://GPU节点地址:9400/metrics
```

如果能看到以 `DCGM_` 开头的指标，说明 Exporter 已经成功暴露数据。若接口存在但缺少 SM、Tensor 或 PCIe 等 profiling 指标，需要检查采集配置、GPU 型号、DCGM 版本、权限以及 MIG 或虚拟化环境是否支持。

### 采集哪些指标由谁决定

DCGM Exporter 使用采集器配置文件选择 Field ID。基础指标通常默认存在，profiling 指标可能需要显式加入。采得越多并不一定越好：每个指标都会增加采集、存储和查询成本，硬件计数器还可能存在兼容性或并发限制。

实用的做法是先覆盖利用率、显存、温度、功率和错误，再按性能分析需要增加 SM、Tensor、各精度管线、PCIe 和 NVLink 指标。

## 3. Prometheus：定时采集并保存时间序列

Prometheus 是监控系统和时序数据库。它最重要的工作有三项：

1. 定期访问 DCGM Exporter 的 `/metrics`；
2. 为每个指标加上采集时间并保存；
3. 使用 PromQL 查询、聚合和计算这些数据。

### 拉取模式

Prometheus 通常采用 pull，也就是拉取模式。假设采集间隔是 15 秒，它就每隔 15 秒请求一次 Exporter：

```text
00:00:00  请求 /metrics，GPU 利用率为 72
00:00:15  请求 /metrics，GPU 利用率为 86
00:00:30  请求 /metrics，GPU 利用率为 91
```

这些带时间戳的样本连起来，就形成了 Grafana 中看到的利用率曲线。

采集间隔越短，曲线越精细，但请求、存储和查询成本越高。GPU 集群常从 15 秒或 30 秒开始，再根据排障精度和集群规模调整。若一个任务只运行 5 秒，而采集周期是 30 秒，它可能完全落在两个采样点之间，这也是短任务监控经常“看不到”的原因。

### 时间序列和标签

Prometheus 通过“指标名 + 一组标签”唯一标识一条时间序列。例如：

```text
DCGM_FI_DEV_GPU_UTIL{instance="node-a:9400",gpu="0",UUID="GPU-123"}
DCGM_FI_DEV_GPU_UTIL{instance="node-a:9400",gpu="1",UUID="GPU-456"}
```

虽然指标名相同，但 `gpu` 和 `UUID` 不同，所以它们是两条独立曲线。在 Kubernetes 环境中，DCGM Exporter 还可能借助 Kubelet Pod Resources API 添加 `namespace`、`pod`、`container` 等标签，使平台能够回答“哪个任务占用了哪张 GPU”。具体能否关联成功取决于部署方式和版本配置。

标签要保持稳定。不要随意加入请求 ID、随机字符串或其他不断变化的值，否则会生成海量时间序列。这叫高基数问题，会明显增加 Prometheus 的内存和存储压力。

### Gauge、Counter 和 rate() 的区别

理解指标类型能避免写错查询：

- **Gauge（仪表值）**可以上升也可以下降，例如温度、利用率、当前显存使用量。它通常直接查询，或使用 `avg_over_time()`、`max_over_time()`。
- **Counter（计数器）**通常只累计增加，例如累计请求数。要计算每秒速率，通常使用 `rate()`。

不能看到“流量”两个字就机械地套 `rate()`。某些 DCGM PCIe 字段本身已经表示 Bytes/s，是 Gauge；再使用 `rate()` 就会变成“每秒速率的变化率”，含义完全不同。应以 `/metrics` 中的 `# TYPE`、DCGM 字段说明和当前版本文档为准。

### 几个入门 PromQL 示例

查看每张 GPU 的当前利用率：

```promql
DCGM_FI_DEV_GPU_UTIL
```

按采集实例计算 GPU 平均利用率：

```promql
avg by (instance) (DCGM_FI_DEV_GPU_UTIL)
```

查看过去 5 分钟的最高温度：

```promql
max_over_time(DCGM_FI_DEV_GPU_TEMP[5m])
```

根据已用和空闲显存计算容量占用率：

```promql
100 * DCGM_FI_DEV_FB_USED
  / (DCGM_FI_DEV_FB_USED + DCGM_FI_DEV_FB_FREE)
```

实际环境应按 `instance`、`gpu` 或 `UUID` 正确匹配时间序列。若两侧标签不一致，需要显式指定向量匹配规则，不能只依赖看起来相同的 GPU 编号。

### Prometheus 不负责什么

Prometheus 有简单的查询页面，但它不是主要的仪表盘制作工具。它负责把数据采进来、存下来并算出来；最终展示通常交给 Grafana。

## 4. Grafana：把查询结果变成监控面板

Grafana 是可视化和仪表盘工具。它把 Prometheus 配置为数据源，通过 PromQL 查询数据，再将结果展示为折线图、仪表盘、表格或热力图。

一个常见 GPU 仪表盘可能包括：

- 每张 GPU 的利用率和 SM Activity；
- 显存使用量与显存占用率；
- Tensor、FP16、FP32、FP64 Activity；
- PCIe 或 NVLink 流量；
- 温度、功率和时钟频率；
- 按节点、命名空间、任务或用户统计的 GPU 使用情况；
- XID、ECC 和设备掉线等健康告警。

### Grafana 不是数据库

Grafana 通常不保存 GPU 指标本身。刷新页面时，它向 Prometheus 发出查询，再把返回结果画出来。因此：

- Grafana 没有曲线，不一定是 Grafana 本身出错；
- 应先确认 Exporter 有数据，再确认 Prometheus 已抓取，最后检查 Grafana 查询；
- 删除 Grafana 面板不会删除 Prometheus 中的原始时间序列。

### 变量让一个仪表盘服务整个集群

Grafana 支持变量，例如 `namespace`、`node`、`pod` 和 `gpu`。用户在页面顶部选择节点后，所有面板都自动过滤到对应设备。变量本质上也是查询标签，因此标签设计会直接影响仪表盘是否好用。

### 告警放在哪里

常见做法包括使用 Prometheus 规则配合 Alertmanager，或者使用 Grafana Alerting。无论选择哪一种，都应关注持续时间而不是单个尖峰。例如“温度连续 10 分钟超过阈值”通常比“某个采样点超过阈值”更有意义。

温度和功率上限应按 GPU 型号、散热设计及厂商建议设置，不能给所有型号套用同一个固定数字。

## 5. 四个组件如何在实际环境中协作

### 单机或裸金属服务器

一条最小链路通常是：

1. 主机正确安装 NVIDIA 驱动，系统能通过 `nvidia-smi` 识别 GPU；
2. DCGM 能读取设备和指标；
3. DCGM Exporter 在 GPU 主机上运行并开放 `/metrics`；
4. Prometheus 将该地址加入采集目标；
5. Grafana 添加 Prometheus 数据源并创建 GPU 面板。

DCGM 可以采用嵌入式方式由 Exporter 使用，也可以连接独立运行的 Host Engine。具体模式取决于部署版本和运维架构。新手首先需要理解的是：**Exporter 必须能够访问 DCGM 和 GPU 设备。**

### Kubernetes 集群

Kubernetes 中通常在每个 GPU 节点运行一个 DCGM Exporter，常见形态是 DaemonSet。Service 负责暴露 `/metrics`，Prometheus Operator 环境中再通过 ServiceMonitor 或 PodMonitor 声明采集目标。

```text
每个 GPU 节点：NVIDIA 驱动 + DCGM Exporter Pod
                         ↓
                 Service / ServiceMonitor
                         ↓
                 Prometheus Server
                         ↓
                     Grafana
```

NVIDIA GPU Operator 可以帮助安装和管理驱动、Device Plugin、DCGM Exporter 等组件，但是否启用以及具体版本仍由集群配置决定。不能因为安装了 GPU Operator，就默认所有 profiling 指标已经采集成功。

## 6. 从零排查“Grafana 为什么没有 GPU 数据”

沿数据方向逐层排查最快。

### 第一步：GPU 和驱动是否正常

```bash
nvidia-smi
```

如果这里都找不到 GPU，应先修复驱动、设备挂载或节点状态，后面的监控组件无法绕过这一层。

### 第二步：Exporter 是否暴露指标

```bash
curl http://GPU节点地址:9400/metrics
```

搜索 `DCGM_FI_DEV_GPU_UTIL` 等基础指标。若接口无法访问，检查 Exporter 进程或 Pod、端口、日志和网络；若基础指标存在但高级指标缺失，检查采集器配置和硬件支持。

### 第三步：Prometheus 是否抓取成功

在 Prometheus 的 Targets 页面检查目标是否为 `UP`，或查询：

```promql
up
```

`up = 1` 表示最近一次抓取成功，`up = 0` 表示目标已发现但抓取失败。目标根本没有出现时，应检查 Prometheus 的服务发现、ServiceMonitor 或 PodMonitor 选择器以及命名空间配置。

### 第四步：Prometheus 中是否能查到指标

直接执行：

```promql
DCGM_FI_DEV_GPU_UTIL
```

如果有结果，说明采集和存储基本正常。此时再检查 Grafana 数据源、时间范围、变量取值和面板 PromQL。

### 第五步：检查标签是否匹配

从其他环境导入的 Grafana 面板可能使用 `node`，而自己的指标只有 `instance`；也可能面板筛选 `pod`，但 Exporter 并未补充 Kubernetes 工作负载标签。查询条件不匹配时，即使 Prometheus 有数据，面板仍会显示 No data。

## 7. 新手最容易产生的几个误解

### 误解一：安装 Grafana 就能自动看到 GPU

Grafana 只负责查询和展示。没有 DCGM Exporter 提供指标、没有 Prometheus 保存数据，Grafana 没有内容可以画。

### 误解二：Exporter 会把数据主动推送给 Prometheus

通常是 Prometheus 定期访问 Exporter，而不是 Exporter 主动发送。网络策略和防火墙需要允许 Prometheus 访问 Exporter 的指标端口。

### 误解三：指标越多，监控越完整

真正有用的是能回答运维问题的指标。采集大量从不使用的高频指标，会增加时间序列数量、存储空间和查询成本。应先定义面板和告警需求，再决定采集范围。

### 误解四：GPU 编号可以跨机器唯一定位设备

`gpu="0"` 只表示某台机器上的第 0 张卡。跨节点定位最好同时使用节点标签和 GPU UUID。MIG 环境还需要区分物理 GPU、GPU Instance 和 Compute Instance。

### 误解五：仪表盘上的 0 和 No data 是一回事

0 表示采集到了一个数值为零的样本；No data 表示查询没有返回时间序列。后者可能是目标掉线、指标不支持、标签筛选错误或时间范围不正确，诊断意义完全不同。

## 8. 规划一套可用 GPU 监控时的建议

第一阶段先建立最小闭环：确保 `nvidia-smi` 正常、Exporter `/metrics` 有基础指标、Prometheus Target 为 UP、Grafana 能画出一条 GPU 利用率曲线。

第二阶段补充资源与健康视图：显存、温度、功率、ECC/XID、设备在线状态，并建立具有持续时间的告警。

第三阶段再做性能分析和平台化：增加 SM/Tensor/FP 管线、PCIe/NVLink 指标，关联 Kubernetes 工作负载标签，按任务和团队统计利用率与资源成本。

最后，为每个面板写清楚单位、聚合方式和查询窗口。一个显示“GPU 利用率 70%”的面板，如果没有说明它是瞬时值、5 分钟平均值，还是多张 GPU 的平均值，很容易让读者得出错误结论。

## 总结

DCGM、DCGM Exporter、Prometheus 和 Grafana 并不是四套互相竞争的 GPU 监控工具，而是一条链路上的四种角色：

- **DCGM** 从 NVIDIA GPU 和驱动读取指标、健康状态与诊断信息；
- **DCGM Exporter** 将选定的 DCGM 字段转换为 Prometheus 指标；
- **Prometheus** 定期采集、保存时间序列，并通过 PromQL 完成计算；
- **Grafana** 查询 Prometheus，把结果做成仪表盘和告警视图。

排查问题时，始终按“GPU/驱动 → DCGM Exporter → Prometheus → Grafana”的方向逐层确认。只要能准确判断数据在哪一层中断，即使刚接触这套技术栈，也能很快缩小问题范围。
