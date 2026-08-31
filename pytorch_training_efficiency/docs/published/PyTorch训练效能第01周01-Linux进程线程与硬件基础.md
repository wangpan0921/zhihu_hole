# PyTorch 训练效能第 1 周第 1 课：Linux 进程、线程与硬件基础

关于训练效率提升，最容易犯的错误是看到“GPU 利用率低”，马上开始调整 batch size、DataLoader worker 数或模型代码。

真正可靠的做法是先回答三个问题：

1. 训练任务由哪些进程和线程组成？
2. 数据从磁盘到 GPU 经过了哪些硬件？
3. 我们测到的时间究竟是哪一种时间？

本课不追求记住所有 Linux 命令，而是建立一张训练任务的系统地图。后续学习 DataLoader、DDP、NCCL、OOM 和 Profiling 时，都会反复使用这张地图。

## 一、本课目标

学完后，你应该能够：

- 解释程序、进程和线程的区别；
- 读懂 PID、PPID、线程数、CPU 使用率和内存占用；
- 画出一批训练数据从存储到 GPU 的基本路径；
- 区分墙钟时间、用户态 CPU 时间和内核态 CPU 时间；
- 解释为什么 CPU、内存、GPU 或 I/O 中任何一环都可能拖慢训练；
- 用 `ps`、`top`、`time` 和 `nvidia-smi` 做第一次系统观察。

## 二、先建立训练任务的全链路认识

一次典型 PyTorch 训练，大致经历下面的路径：

```text
磁盘 / 对象存储
       |
       | 读取图片、视频、标注或文本
       v
CPU 内存
       |
       | DataLoader worker 解码、增强、拼 batch
       v
Pinned Memory（可选）
       |
       | PCIe / NVLink 上的 Host-to-Device 拷贝
       v
GPU 显存
       |
       | 前向、反向、优化器更新
       v
下一次迭代 / 保存 checkpoint / 分布式通信
```

如果 GPU 正在等数据，模型代码再快也没有用；如果 GPU 显存不足，数据读取再快也无法训练；如果多个 rank 的通信被一个慢 rank 拖住，单卡计算再快也无法提高整体吞吐。

训练效能工作的核心不是“只懂 GPU”，而是判断当前瓶颈位于哪一段。

## 三、程序、进程和线程有什么区别

### 1. 程序是磁盘上的文件

例如：

```text
/usr/bin/python3
train.py
```

它们只是文件，还没有执行。执行 `python3 train.py` 后，操作系统才创建进程。

### 2. 进程是正在运行的程序实例

每个进程通常拥有：

- 唯一的进程号 PID；
- 自己的虚拟地址空间；
- 打开的文件和网络连接；
- 至少一个线程；
- 调度状态和资源统计。

同一个 `train.py` 可以启动多次，每次都会形成不同的进程和 PID。

查看当前 shell 的 PID：

```bash
echo $$
```

查看 Python 进程：

```bash
ps -eo pid,ppid,nlwp,stat,%cpu,%mem,rss,etime,cmd | head
```

常用字段：

| 字段 | 含义 | 训练排查时看什么 |
| --- | --- | --- |
| `PID` | 当前进程 ID | 用来继续查看线程、文件、GPU 占用 |
| `PPID` | 父进程 ID | 判断进程是谁拉起的 |
| `NLWP` | 轻量级进程数，通常可理解为线程数 | 判断是否产生过多线程 |
| `STAT` | 进程状态 | `R` 运行、`S` 睡眠、`D` 不可中断等待、`Z` 僵尸 |
| `%CPU` | 一段时间内使用的 CPU 比例 | 多核机器上可能超过 100% |
| `%MEM` | 占系统物理内存的比例 | 只能做粗略判断 |
| `RSS` | 当前驻留在物理内存中的大小 | 判断实际物理内存压力 |
| `ETIME` | 进程已运行时间 | 区分刚启动和长期运行任务 |

注意：一台 32 核机器上，单进程显示 `%CPU=400` 通常表示它大约持续使用了 4 个逻辑 CPU，并不是显示错误。

### 3. 线程是进程中的执行单元

同一进程中的线程通常共享：

- Python 对象和堆内存；
- 模型参数；
- 打开的文件描述符；
- 进程地址空间。

每个线程又有自己的调用栈和调度状态。

PyTorch 程序中可能同时出现：

- Python 主线程；
- OpenMP 或 MKL 计算线程；
- CUDA runtime 相关线程；
- 日志、监控或 checkpoint 后台线程。

查看某个进程中的线程：

```bash
ps -T -p <PID>
```

或者在 `top` 中按 `H` 切换线程显示。

### 4. PyTorch DataLoader 为什么常涉及多进程

设置：

```python
DataLoader(dataset, num_workers=4)
```

通常意味着主训练进程之外，还会产生 4 个 worker 进程。它们并行完成读取、解码和数据增强，再把 batch 交给训练进程。

因此 `num_workers=4` 不等于“4 个线程”。在 Linux 上，它通常是 4 个独立进程。每个 worker 还可能调用会自行创建线程的图像库或数学库，于是总线程数可能远大于 4。

这正是训练数据链路中常见的线程过量问题：

```text
8 个 DataLoader worker × 每个 worker 16 个 OpenMP 线程
= 最多 128 个计算线程
```

如果机器只分配到 16 个 CPU 核，过量线程会带来上下文切换和缓存争用，worker 更多反而可能更慢。

## 四、CPU、内存和 GPU 分别负责什么

### 1. CPU

训练任务中的 CPU 常负责：

- Python 控制逻辑；
- 数据读取与解压；
- JPEG、PNG、视频解码；
- 数据增强和 batch 拼接；
- 向 GPU 提交 kernel；
- 日志、checkpoint 和分布式控制逻辑。

CPU 利用率低不一定代表没有 CPU 瓶颈。例如，程序可能只有一个串行线程跑满一个核，在 64 核机器的整体视图里只占约 1.6%。此时要看单核和单线程，而不是只看整机平均值。

查看 CPU 基本信息：

```bash
lscpu
```

重点关注：

- `CPU(s)`：逻辑 CPU 数；
- `Core(s) per socket`：每个物理 CPU 的核心数；
- `Thread(s) per core`：每核硬件线程数；
- `Socket(s)`：物理 CPU 插槽数；
- `NUMA node(s)`：NUMA 节点数。

### 2. 内存

不要把下面三个概念混为一谈：

- 虚拟内存：进程看到的地址空间；
- 物理内存：机器真正安装的 RAM；
- GPU 显存：GPU 设备上的独立内存。

查看系统内存：

```bash
free -h
```

Linux 会尽量利用空闲内存做 page cache，因此 `free` 很小不一定表示马上 OOM。通常更应该关注 `available`。

典型训练内存消耗包括：

- Python 对象和数据集索引；
- DataLoader worker 的进程内存；
- 预取中的多个 batch；
- 解码后的图像或视频帧；
- pinned memory；
- 文件系统 page cache。

### 3. GPU

GPU 擅长执行大量并行的数值计算。训练时重点关注：

- GPU 利用率；
- 显存已用量；
- 功率和频率；
- 温度；
- PCIe 或 NVLink 传输；
- 具体 SM、Tensor Core 活跃程度。

快速查看：

```bash
nvidia-smi
```

持续观察：

```bash
nvidia-smi dmon -s pucm
```

如果机器没有 NVIDIA GPU，命令不存在或提示没有设备是正常的。第一周的重点是理解字段和观察方法，不要求必须拥有 GPU。

不要只用 `nvidia-smi` 中的 GPU Util 判断训练效率。它表示采样窗口内 GPU 是否在忙，并不直接等于 Tensor Core 利用率、MFU 或训练吞吐。一个频繁运行小 kernel 的任务可能显示较高 GPU Util，但实际计算效率仍然很差。

## 五、墙钟时间和 CPU 时间

### 1. 墙钟时间

墙钟时间就是现实世界经过的时间，也称 elapsed time。

如果任务从 10:00:00 开始，到 10:00:10 结束，墙钟时间就是 10 秒，无论这段时间程序是在计算、睡眠还是等待 I/O。

训练吞吐通常使用墙钟时间计算：

```text
吞吐 = 处理的有效样本数 / 墙钟时间
```

### 2. 用户态 CPU 时间

CPU 在用户态执行程序代码所累计的时间，例如 Python、C++ 或数学库的计算。

多线程程序在 2 秒墙钟时间内，如果 8 个线程都持续计算，用户态 CPU 时间可能接近 16 秒。

### 3. 内核态 CPU 时间

CPU 在内核中代表程序执行系统调用所花的累计时间，例如部分文件读写、网络和进程管理操作。

使用 shell 的 `time` 测量：

```bash
/usr/bin/time -v python3 -c "sum(i * i for i in range(5_000_000))"
```

重点字段：

- `Elapsed (wall clock) time`：墙钟时间；
- `User time`：用户态 CPU 时间；
- `System time`：内核态 CPU 时间；
- `Percent of CPU`：CPU 时间与墙钟时间的比例；
- `Maximum resident set size`：峰值 RSS，通常单位为 KiB。

### 4. 用一个实验观察等待和计算

先测纯等待：

```bash
/usr/bin/time -v python3 -c "import time; time.sleep(2)"
```

你应该看到：

```text
        Command being timed: "python3 -c import time; time.sleep(2)"                                                                          
        User time (seconds): 0.01                                      
        System time (seconds): 0.00                                    
        Percent of CPU this job got: 1%                                
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:02.02                                                                                  
        Average shared text size (kbytes): 0                                                                                                  
        Average unshared data size (kbytes): 0                                                                                                
        Average stack size (kbytes): 0                                 
        Average total size (kbytes): 0                                 
        Maximum resident set size (kbytes): 9332                                                                                              
        Average resident set size (kbytes): 0                                                                                                 
        Major (requiring I/O) page faults: 0                                                                                                  
        Minor (reclaiming a frame) page faults: 902                                                                                           
        Voluntary context switches: 2                                  
        Involuntary context switches: 2                                
        Swaps: 0                   
        File system inputs: 0                                          
        File system outputs: 0                                         
        Socket messages sent: 0                                        
        Socket messages received: 0                                    
        Signals delivered: 0                                           
        Page size (bytes): 4096                                        
        Exit status: 0          
```

- 墙钟时间约 2 秒；
- User 和 System 时间都很少；
- CPU 百分比较低。

再测 CPU 计算：

```bash
/usr/bin/time -v python3 -c "sum(i * i for i in range(20_000_000))"
```

你应该看到 User time 明显增加，并接近墙钟时间。
```text
        Command being timed: "python3 -c sum(i * i for i in range(20_000_000))"
        User time (seconds): 0.83
        System time (seconds): 0.00
        Percent of CPU this job got: 100%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.84
        Average shared text size (kbytes): 0
        Average unshared data size (kbytes): 0
        Average stack size (kbytes): 0
        Average total size (kbytes): 0
        Maximum resident set size (kbytes): 9340
        Average resident set size (kbytes): 0
        Major (requiring I/O) page faults: 0
        Minor (reclaiming a frame) page faults: 903
        Voluntary context switches: 1
        Involuntary context switches: 5
        Swaps: 0
        File system inputs: 0
        File system outputs: 0
        Socket messages sent: 0
        Socket messages received: 0
        Signals delivered: 0
        Page size (bytes): 4096
        Exit status: 0

```

这能帮助你理解：程序运行得慢，不代表 CPU 一直在计算。它也可能在等待磁盘、网络、锁、另一个进程或 GPU。

## 六、常见进程状态与排查直觉

### `R`：正在运行或等待 CPU 调度

如果大量线程长期处于 `R`，CPU 使用率很高，可能是正常计算，也可能是线程过量。

### `S`：可中断睡眠

这是很常见的状态，可能在等待定时器、队列或事件。它不自动等于故障。

### `D`：不可中断睡眠

常见于内核中的 I/O 等待。如果大量 DataLoader worker 长时间处于 `D`，应检查存储、网络文件系统、设备错误和 I/O 延迟。

### `Z`：僵尸进程

进程已经退出，但父进程还没有回收其退出状态。少量短暂僵尸不一定严重，持续积累则说明父进程处理有问题。

## 七、一个最小观察实验

创建文件 `/tmp/process_observe.py`：

```python
import os
import threading
import time


def cpu_work() -> None:
    total = 0
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        total += sum(i * i for i in range(10_000))
    print("worker done", total)


print("PID:", os.getpid())
threads = [threading.Thread(target=cpu_work) for _ in range(2)]
for thread in threads:
    thread.start()

time.sleep(20)
for thread in threads:
    thread.join()
```

在终端一运行：

```bash
python3 /tmp/process_observe.py
```

记下输出的 PID，然后在终端二运行：

```bash
ps -o pid,ppid,nlwp,stat,%cpu,%mem,rss,etime,cmd -p <PID>
ps -T -p <PID>
top -H -p <PID>
```

观察并回答：

```text
ps -o pid,ppid,nlwp,stat,%cpu,%mem,rss,etime,cmd -p 4102648
    PID    PPID NLWP STAT %CPU %MEM   RSS     ELAPSED CMD
4102648 4101195    3 Sl+   100  0.0 10380       00:19 python process_observe.p
```


1. 这个进程共有多少个线程？
2. 两个 Python CPU 线程是否让 `%CPU` 稳定达到约 200%？
3. 如果没有，Python GIL 可能产生了什么影响？
4. `time.sleep` 是否会持续占用 CPU？

不要把答案简化成“Python 多线程一定没用”。线程对于 I/O 等待和部分会释放 GIL 的 C/C++ 扩展仍然可能有效。正确结论应该是：先理解工作负载，再用实验选择线程或进程。

## 八、训练效能中的五个常见误区

### 误区 1：GPU 利用率低，所以模型计算有问题

也可能是数据读取、解码、CPU 增强、H2D 拷贝或分布式同步导致 GPU 等待。

### 误区 2：DataLoader worker 越多越快

worker 会消耗 CPU、内存、文件描述符和进程调度资源。超过甜点值后可能更慢。

### 误区 3：内存 `free` 很少，所以机器马上 OOM

Linux 会使用内存做缓存。应结合 `available`、进程 RSS、cgroup 限制和 OOM 日志判断。

### 误区 4：只看平均 step time

平均值会隐藏慢样本和尾延迟。后续应同时记录中位数、p95、p99 和原始数据。

### 误区 5：程序内部计时一定准确

CUDA 默认异步执行。如果没有正确同步，Python 可能只测到 kernel 提交时间。第 8 周会系统学习正确 benchmark。

## 九、本课练习

### 必做练习

1. 运行 `lscpu`，记录逻辑 CPU、核心、socket 和 NUMA 节点数。
2. 运行 `free -h`，解释 `free` 与 `available` 的区别。
3. 运行两个 `time` 实验，记录墙钟、User、System 和峰值 RSS。
4. 完成最小观察实验，保存 `ps` 和 `top` 结果。
5. 有 GPU 时运行 `nvidia-smi`，记录型号、显存、驱动版本和运行中的进程。

### 思考题

某训练任务每步耗时 500 ms，其中 GPU 计算 180 ms、数据等待 250 ms、H2D 拷贝 40 ms、其他控制逻辑 30 ms。此时优先把 GPU kernel 提速 20%，还是优化数据链路？为什么？

参考方向：GPU kernel 提速 20% 只节省约 36 ms，而数据等待占 250 ms；但最终决策仍需要判断数据等待能否与计算重叠以及优化成本。

## 十、验收标准

满足以下条件才算完成本课：

- 能在不查资料的情况下解释进程与线程的区别；
- 能从 `ps` 输出找出父子关系、线程数、CPU 和 RSS；
- 能解释为何 User time 可能大于墙钟时间；
- 能画出“存储到 CPU，再到 GPU”的训练数据路径；
- 能列出 GPU 利用率低的至少四种非 GPU 原因；
- 完成命令实验并保留原始输出，而不是只写结论。

下一课将使用 PyTorch 环境检查脚本，把这些概念对应到真实机器中的 Python、PyTorch、CUDA、cuDNN、线程池和 GPU 设备信息。
