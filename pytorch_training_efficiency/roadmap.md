# 52 周学习路线：每周三课

每一课都必须留下可检查的产物。`笔记`应回答“原理、边界、常见误区”；`实验`应保存命令和原始数据；`工程产出`应能由同事复现或评审。每周末用 30 分钟复盘：本周学会了什么、证据是什么、哪里仍无法解释、下周如何验证。

本路线按训练效能与数据基础设施岗位定向设计：PyTorch/分布式约占 30%，数据存储、版本、分发与 I/O 约占 30%，Linux/Python/C++ 系统工程约占 20%，框架工程化、CI/CD 与可观测性约占 15%，自动驾驶数据语义与协作约占 5%。

## 第一阶段：基础与单卡训练（第 1 至 13 周）

第 1 周课程文章：

1. [Linux 进程、线程与硬件基础](docs/draft/PyTorch训练效能第01周01-Linux进程线程与硬件基础.md)
2. [训练环境体检实战](docs/draft/PyTorch训练效能第01周02-训练环境体检实战.md)
3. [可复现实验与 Git 基线](docs/draft/PyTorch训练效能第01周03-可复现实验与Git基线.md)

| 周 | 主题 | 课程 A：原理 | 课程 B：动手实验 | 课程 C：工程产出与验收 |
| --- | --- | --- | --- | --- |
| 1 | 环境与研发基线 | Linux 进程/线程、CPU/内存/GPU、墙钟与 CPU 时间；Git 分支与提交 | 运行 `00_environment.py`，配合 `ps`/`top`/`nvidia-smi` 核对环境 | 建实验日志与 Git 仓库模板；同一命令跑 3 次并解释波动 |
| 2 | Tensor 基础 | shape、stride、dtype、device、view/copy、连续内存 | 用切片、transpose、contiguous 验证 storage 与 stride | 写 10 个 tensor 断言；能判断一次操作是否复制内存 |
| 3 | Autograd | 计算图、叶子张量、反向传播、梯度累积、no_grad | 手算线性回归梯度并与 autograd 比较 | 做 finite-difference 梯度检查，误差小于设定阈值 |
| 4 | 训练循环 | Module、loss、optimizer、train/eval、zero_grad | 运行并改造 `01_train_baseline.py` | loss 明显下降、准确率达标；保存完整运行命令与随机种子 |
| 5 | 优化器 | SGD/AdamW、动量、weight decay、学习率与 batch 的关系 | 固定数据比较三组优化器/学习率曲线 | 输出实验表，解释欠拟合、震荡和发散各一例 |
| 6 | 数据入口 | Dataset、Sampler、DataLoader、batch、collate_fn | 为合成数据写 map-style Dataset 与自定义 collate | 验证样本不丢不重，并记录单进程加载吞吐 |
| 7 | 随机性 | Python/NumPy/PyTorch RNG、worker seed、确定性与性能 | 同种子复现两次训练；修改一个随机源观察差异 | 写“可复现清单”，区分完全一致与统计一致 |
| 8 | 正确计时 | warmup、异步 CUDA、synchronize、均值/p50/p95 | 运行 `02_benchmark.py`，比较向量化与 Python 循环 | benchmark JSON 可复现；指出至少两个错误计时方式 |
| 9 | 显存组成 | 参数、梯度、优化器状态、激活、临时 buffer、碎片 | 运行 `08_memory_accounting.py`，手算 AdamW 静态显存 | 估算值与程序输出对应；解释 batch 增大主要影响哪部分 |
| 10 | 混合精度 | FP32/TF32/FP16/BF16、动态范围、loss scaling | 在可用 GPU 上运行 `05_amp_accumulation.py --amp` | 对比速度、显存、loss；无 GPU 时完成数值范围小实验 |
| 11 | 梯度累积 | micro/global batch、loss reduction、更新频率 | 用 `05_amp_accumulation.py` 比较大 batch 与累积梯度 | 参数最大误差达标；能解释除数错误为何改变梯度 |
| 12 | Checkpoint | model/optimizer/scheduler/RNG/进度状态、原子写入 | 运行 `07_checkpoint_resume.py`，中断后恢复 | 连续训练与恢复训练参数一致；列出漏存 optimizer 的后果 |
| 13 | 阶段项目一 | 从指标到假设：单卡训练性能分析方法 | 对真实小模型采集吞吐、step 分位数、显存、GPU 利用率 | 交付 3 页报告：基线、瓶颈证据、一个优化及正确性验证 |

## 第二阶段：性能分析与数据链路（第 14 至 26 周）

| 周 | 主题 | 课程 A：原理 | 课程 B：动手实验 | 课程 C：工程产出与验收 |
| --- | --- | --- | --- | --- |
| 14 | Profiler 入门 | operator、CPU/CUDA activity、record_function、schedule | 运行 `04_profiler.py`，用浏览器打开 trace | 从时间线找出最耗时算子和数据区间，截图并解释依据 |
| 15 | 算子成本 | FLOPs、内存带宽、算术强度、launch overhead | 比较小算子串、融合实现和大矩阵乘 | 用 roofline 思路判断一个算子偏计算还是偏访存 |
| 16 | GPU 执行 | kernel、stream、event、异步队列、host-device copy | 用 CUDA Event 与墙钟分别计时；观察缺少同步的偏差 | 画出一个 step 的 CPU 提交与 GPU 执行时间线 |
| 17 | torch.compile | graph capture、graph break、重编译、动态 shape、后端 | 比较 eager/compile 首次与稳态性能，打开 graph-break 日志 | 明确是否采用及理由；报告编译开销与 break 位置 |
| 18 | DataLoader 进阶 | worker 进程、prefetch、persistent、pin_memory、队列 | 运行 `03_dataloader_benchmark.py` 扫描 worker 数 | 找到甜点配置；报告吞吐、波动、CPU 与内存代价 |
| 19 | Python 并发与内存 | GIL、线程/进程边界、fork/spawn、copy-on-write、pickle、共享内存与引用生命周期 | 比较线程池、进程池、Queue 和 shared memory 传输 Tensor；用 `tracemalloc` 制造并定位泄漏 | 输出延迟/吞吐/内存表；能解释 DataLoader worker 膨胀、句柄泄漏和 Tensor 被意外持有 |
| 20 | Arrow 与 Lance | Arrow 列式内存、RecordBatch、zero-copy、schema evolution；Lance fragment、snapshot、predicate pushdown | 将同一数据写成 Arrow/Lance，比较列裁剪、条件过滤、随机/顺序扫描和版本切换 | 给出格式选型报告；用证据说明何时 zero-copy 成立、schema 如何兼容和快照如何回滚 |
| 21 | LMDB 与 WebDataset | LMDB mmap/B+Tree/事务/单写多读/map_size；WebDataset tar shard/shuffle/resampling | 同一批小文件分别写入 LMDB 和 tar shards，扫描 reader/worker/shard 大小并测冷/热缓存 | 验证多 rank/worker 不丢不重；报告 IOPS、吞吐、内存、恢复语义和适用边界 |
| 22 | 图像视频编解码 | JPEG/PNG、H.264/H.265、关键帧/GOP/seek；Pillow/OpenCV/PyAV/FFmpeg 与 nvJPEG/NVDEC/DALI | profile read/decode/augment/collate 四段；比较单帧随机读、连续 clip 和不同解码后端 | 输出阶段耗时与 CPU/GPU 占用；明确瓶颈在存储、解码、增强还是调度 |
| 23 | CPU/GPU 异构流水线 | 生产者消费者、线程过量、NUMA/亲和性、pinned memory、双缓冲、non_blocking 与 stream | 扫描 worker/OMP 线程/CPU affinity；GPU 上实现异步 H2D、增强与计算重叠并查看 timeline | 证明是否真正重叠并给出资源代价；形成 CPU 配额下的推荐配置和反例 |
| 24 | 自动驾驶数据治理 | scene/clip/frame/camera/timestamp/annotation；manifest、immutable snapshot、血缘、checksum、增量版本与分发缓存 | 建简化数据集版本工具，支持 create/diff/validate/rollback；注入坏文件、重复样本、错标注和相邻帧泄漏 | 质量报告能定位 shard/sample/scene；证明多 rank 覆盖，并说明缓存一致性、回滚和训练/验证集隔离 |
| 25 | C++ 与 Linux 性能工程 | CMake/Ninja、动态链接与 ABI、Debug/Release；gdb、perf、FlameGraph、strace、Sanitizer、heaptrack | 用 pybind11 或 `torch.utils.cpp_extension` 实现一个小算子，比较 Python/C++ 正确性与性能并采集火焰图 | 提交可复现构建脚本和 benchmark；能区分 Python 调度、CPU 计算、内存分配与系统调用瓶颈 |
| 26 | 阶段项目二 | 端到端数据漏斗：对象存储/本地缓存、读取、解码、增强、H2D 到 GPU 的分段指标 | 用真实或模拟自动驾驶数据做格式、分片、并发、缓存和解码后端参数矩阵 | 交付数据优化 PR：吞吐提升、资源代价、版本/质量测试、兼容性和回滚方案 |

## 第三阶段：分布式训练与大模型内存（第 27 至 39 周）

| 周 | 主题 | 课程 A：原理 | 课程 B：动手实验 | 课程 C：工程产出与验收 |
| --- | --- | --- | --- | --- |
| 27 | 分布式基础 | rank/world/local rank、collective、拓扑、带宽与时延 | 用 2 个 CPU 进程运行 `06_ddp_train.py` | 能解释 Store、ProcessGroup、backend 与 DDP 的边界 |
| 28 | torchrun | agent/worker、环境变量、rendezvous、弹性重启 | 分别模拟正常启动、端口冲突、一个 rank 异常退出 | 写启动状态图和故障传播说明，保存关键日志 |
| 29 | DDP 原理 | 梯度 hook、bucket、all-reduce、平均语义、no_sync | 对比单进程与 2 rank 参数更新；改变 bucket 设置 | 正确性先通过，再报告扩展效率与 bucket 影响 |
| 30 | DistributedSampler | epoch seed、set_epoch、drop_last、数据倾斜 | 记录各 rank 的 sample id，连续跑两个 epoch | 证明全局覆盖与每 epoch shuffle；指出漏掉 set_epoch 的表现 |
| 31 | NCCL 基础 | ring/tree、channel、PCIe/NVLink/IB、GPUDirect RDMA | 有 GPU 时跑 collective benchmark，改变消息大小 | 画机器拓扑，并解释小消息和大消息的性能主导项 |
| 32 | 通信分析 | compute/communication ratio、重叠、straggler、尾延迟 | profile 一个 DDP step，标出 backward 与 all-reduce | 量化通信占比和未重叠区间，提出可证伪的优化假设 |
| 33 | DDP hang 排障 | collective 顺序、shape 不一致、rank 分支、超时与日志 | 故意让一个 rank 少调一次 collective，观察超时 | 写最小复现和排障树：进程、网络、collective、数据四层 |
| 34 | 慢 rank | 同步放大、数据倾斜、硬件降频、网络抖动 | 给一个 rank 注入 sleep，采集各 rank step 分位数 | 设计 straggler 指标；能区分偶发慢与持续慢 |
| 35 | FSDP | 参数/梯度/优化器分片、all-gather/reduce-scatter、wrap | 小模型跑 2 卡 FSDP，观察各阶段显存与通信 | 对比 DDP/FSDP 的显存、吞吐、复杂度和适用边界 |
| 36 | ZeRO/DeepSpeed | ZeRO 1/2/3、offload、配置与 PyTorch 原生方案取舍 | 选一个模型跑 ZeRO 配置或阅读并验证官方最小例 | 写选型表，禁止只依据“能放下模型”做结论 |
| 37 | 激活优化 | activation checkpoint、重计算、选择性保存、序列长度 | 对不同 checkpoint 粒度测显存与 step 时间 | 绘制显存-吞吐 Pareto 曲线，说明重计算成本 |
| 38 | 大模型并行 | data/tensor/pipeline/context parallel 基本通信模式 | 用纸面张量 shape 推导一次 TP/PP 通信量；可用环境跑最小例 | 给目标模型做并行策略草案，标明假设和风险 |
| 39 | 阶段项目三 | 训练方案容量规划：显存、通信、容错、成本 | 对 DDP/FSDP/ZeRO 至少两种方案做同口径实验 | 交付选型报告和可复现脚本，包含成本/速度/稳定性权衡 |

## 第四阶段：稳定性、平台化与专家实践（第 40 至 52 周）

| 周 | 主题 | 课程 A：原理 | 课程 B：动手实验 | 课程 C：工程产出与验收 |
| --- | --- | --- | --- | --- |
| 40 | 分布式 checkpoint | full/sharded state、并行保存、重分片、版本兼容 | 2 rank 保存后恢复，验证参数和 optimizer state | 测恢复时间与存储峰值；演练不同 world size 恢复 |
| 41 | 容错与幂等 | 故障模型、重试边界、exactly-once 幻觉、任务租约 | 在若干 step 随机 kill worker，检查恢复后的样本进度 | 给训练任务定义 RPO/RTO，说明重复样本是否可接受 |
| 42 | OOM 系统排查 | capacity/fragmentation/leak、allocator、引用生命周期 | 制造激活过大和 Python 持有 tensor 两类 OOM | 写 OOM 决策树；用 memory snapshot 或计数证明确切原因 |
| 43 | 数值异常 | NaN/Inf、溢出、异常梯度、数据异常、分布式传播 | 注入坏输入，增加 finite check、梯度范数与 sample id | 失败能在首次异常处停止并保留最小诊断上下文 |
| 44 | 可观测性 | RED/USE、GPU/DCGM、训练业务指标、标签基数 | 为训练循环增加吞吐、等待、显存、loss、rank 指标 | 做一个 dashboard 和三条可行动告警，避免只告警 GPU 利用率 |
| 45 | 性能回归 CI | 噪声、机器隔离、阈值、统计比较、基线版本管理 | 把 `02_benchmark.py` JSON 接入一个本地回归检查 | 同时设置正确性和性能门槛，能识别一次人为退化 |
| 46 | 测试体系 | unit/integration/e2e、CPU/单卡/多卡矩阵、数据契约与故障注入 | 为 sampler、数据版本、累积梯度、checkpoint、DDP 和 C++ 扩展各写一个测试 | 测试失败能指出契约被破坏；明确性能测试机器隔离和 flaky case 处理规则 |
| 47 | 构建、配置与发布 | 配置 schema、wheel/镜像、C++/CUDA ABI；PyTorch/CUDA/驱动/NCCL/glibc 兼容矩阵 | 给入口输出代码/镜像/数据版本；构建最小 wheel 或镜像并做 CPU/单卡/多卡 smoke test | 旧配置有迁移策略；产物可追溯、可灰度、可回滚，并有经过验证的兼容矩阵 |
| 48 | 框架设计 | control/data plane、launcher/trainer/callback、扩展点与所有权 | 阅读团队框架一条完整调用链，从提交走到一个 optimizer step | 画组件图，指出三处隐式状态和两处潜在故障边界 |
| 49 | 源码阅读 | 从现象选入口，用调用栈、日志和最小例跨 Python/C++ 边界阅读 PyTorch 源码 | 追踪 DDP 初始化、DataLoader worker 或一个算子从 Python dispatcher 到 C++ kernel 的路径 | 写源码导读：入口、核心对象、关键状态、Python/C++ 边界与一次完整时序 |
| 50 | 专项优化 | 从数据证明选一个深挖方向：数据/通信/显存/编译 | 做不少于 5 组受控实验，包含一个失败假设 | 形成技术设计与 PR；报告收益分布而非只报最好数字 |
| 51 | 事故演练与影响力 | incident command、止损、证据保全、复盘与行动项 | 组织一次 hang/OOM/数据损坏演练，让同事按手册处理 | 输出无责复盘；行动项有 owner、截止时间和验证方式 |
| 52 | 毕业项目 | 回顾全年证据，识别能力短板和下一年专精方向 | 重跑第 13 周基线，用同口径展示全年方法与工具进步 | 技术答辩：生产优化项目、回归机制、排障手册、下一年路线 |

## 建议的季度考核题

### 第 1 季度

给一段“GPU 利用率低”的单卡训练，不能先调参数。要求建立基线、分段计时、profile、提出三个可证伪假设，并在保证 loss 行为一致的条件下优化。通过标准是结论能由另一位同事复现。

### 第 2 季度

给一条自动驾驶数据链路，其中混有慢样本、坏视频、重复标注、相邻帧泄漏和存储抖动。要求定位每种问题，保证数据版本可追溯、多 rank 不丢不重，并给出格式、分片、解码、worker、预取和缓存的选择依据。

### 第 3 季度

给一个 2 到 8 卡扩展效率差或偶发 hang 的任务。要求从 rank 日志和 timeline 定位问题，验证数据采样和参数更新正确，并比较至少两种内存/通信方案。

### 第 4 季度

主导一个真实效能项目：立项指标、容量评估、设计评审、实现、灰度、监控、回归测试、回滚和复盘必须齐全。单次漂亮 benchmark 不能代替生产收益。

## 资料选择原则

资料会变化，因此路线图不绑定大量博客链接。按以下优先级选择当期版本资料：

1. 团队内部框架、事故复盘、监控说明和真实作业。
2. 对应版本的 PyTorch 官方 tutorials、API 文档和 distributed notes。
3. NVIDIA CUDA/NCCL/Nsight 官方文档，以及硬件架构白皮书。
4. Lance、Arrow、LMDB、WebDataset、FFmpeg、DeepSpeed 等项目的官方文档和源码。
5. CMake、GDB、Linux perf、Python 并发与内存管理的官方手册。
6. 高质量论文或技术分享；博客只作为线索，结论必须由实验验证。

每次查资料先确认软件版本。PyTorch、NCCL 和 launcher 的默认行为可能随版本变化，不能把旧文章中的结论直接带进生产环境。
