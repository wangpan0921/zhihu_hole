# PyTorch 训练效能与数据基础设施：一年学习与实战计划

这套计划面向刚进入训练效能团队、PyTorch 基础较弱的工程师。目标不是一年后“知道很多术语”，而是能够独立完成以下闭环：

1. 建立可复现的训练基线，定义吞吐、时延、显存、扩展效率和收敛质量指标。
2. 用 profiler、时间线、系统指标和最小复现定位计算、通信、I/O 或内存瓶颈。
3. 在不破坏数值正确性和收敛质量的前提下完成优化，并给出可信的对照实验。
4. 维护 DDP/FSDP 等训练链路，处理 OOM、hang、慢卡、数据损坏和 checkpoint 恢复问题。
5. 把优化固化成测试、监控、文档和 CI，而不是一次性的参数调节。
6. 使用 Python/C++ 和 Linux 工具优化 Lance、Arrow、LMDB、WebDataset 及图像视频数据链路。
7. 建设可追溯、可校验、可分发和可回滚的自动驾驶数据集版本体系。

“专家”通常还需要多年生产事故和大规模集群经验。一年更现实的目标是达到训练效能方向的强独立贡献者水平，并在一个子方向（数据、通信、显存或框架稳定性）形成专家深度。

## 使用方式

- 周投入建议：工作日 3 次，每次 60 到 90 分钟；另留 2 到 4 小时完成实验或工作项目。
- 固定节奏：课程 A 学原理，课程 B 做可重复实验，课程 C 产出工程证据。
- 每项实验都记录环境、代码版本、命令、原始结果、结论和下一步。没有基线、重复运行和正确性检查的“提速”不计入成果。
- 优先把当周知识用于真实训练任务；无法接触生产环境时使用本目录的合成数据实验。
- 详细的 52 周课程见 [roadmap.md](roadmap.md)，实验入口见 [labs/README.md](labs/README.md)。

## 开始前的环境

建议使用 Linux、Python 3.10+ 和 PyTorch 2.2+。基础实验无需 GPU；AMP、CUDA profiler、NCCL、FSDP 和多机实验需要相应 GPU 环境。

```bash
cd pytorch_training_efficiency
python3 -m venv .venv
source .venv/bin/activate

# CPU 环境。GPU 环境应按公司 CUDA 版本从 PyTorch 官方索引安装对应 wheel。
pip install torch --index-url https://download.pytorch.org/whl/cpu

python labs/00_environment.py
python labs/01_train_baseline.py --steps 100
python labs/02_benchmark.py --output artifacts/benchmark.json
torchrun --standalone --nproc-per-node=2 labs/06_ddp_train.py
```

不要在不确认驱动、CUDA 和公司镜像规范的情况下直接升级生产环境中的 PyTorch。

## 五条能力主线

| 主线 | 必须掌握 | 最终证据 |
| --- | --- | --- |
| PyTorch 与数值正确性 | tensor/autograd、Module、optimizer、AMP、compile、checkpoint、随机性 | 能实现并验证一条稳定训练基线 |
| 性能分析 | 正确计时、warmup、同步、PyTorch Profiler、Nsight、roofline、显存核算 | 能用时间线和数据解释瓶颈，不靠猜 |
| 数据链路 | Lance/Arrow、LMDB、WebDataset、版本/分发、图像视频解码、缓存、分片、数据质量 | 能区分存储、解码、CPU、拷贝和 GPU 消费瓶颈 |
| 分布式训练 | collective、ProcessGroup、torchrun、DDP、NCCL、FSDP/ZeRO、容错 | 能定位 hang/慢 rank/OOM，并量化扩展效率 |
| 系统与工程化 | Linux、Python 并发/内存、C++/构建/ABI、Git、测试、CI/CD、可观测性与发布 | 优化可构建、可回归、可观测、可灰度、可维护 |

## 一年的四个里程碑

| 时间 | 能力验收 | 建议工作成果 |
| --- | --- | --- |
| 第 13 周 | 能写正确训练循环并完成单卡 profile | 一份单卡瓶颈报告，含 trace、指标和复现实验 |
| 第 26 周 | 能优化数据格式、版本、解码和 CPU/GPU 流水线 | 一个被团队采用的数据链路优化 PR，含质量与回滚机制 |
| 第 39 周 | 能评估 FSDP/ZeRO、checkpoint 和大模型显存方案 | 一份多方案选型报告及可复现 benchmark |
| 第 52 周 | 能主持完整效能项目并建设回归机制 | 一个生产级优化项目、事故手册和技术分享 |

## 每次优化的标准实验模板

先写实验方案，再改代码：

```text
问题：当前哪个业务指标不达标？
假设：瓶颈是什么，什么证据可以证伪？
控制变量：模型、数据、精度、batch、硬件、软件版本、运行时长。
指标：samples/s 或 tokens/s、step p50/p95、GPU 利用率、峰值显存、收敛质量。
方法：warmup 次数、正式测量次数、同步点、profile 范围。
正确性门槛：loss/梯度/最终指标允许多大偏差？
结果：原始数据、均值与波动、trace、失败样本。
决策：采用/拒绝；收益、风险、回滚方式和后续问题。
```

关键公式：

```text
吞吐 = 有效样本数（或 token 数）/ 墙钟时间
数据等待占比 = 等待下一批数据的时间 / step 总时间
扩展效率(N) = N 卡吞吐 / (N × 单卡吞吐)
模型 FLOPs 利用率(MFU) = 实测每秒有效模型 FLOPs / 硬件理论峰值 FLOPs
优化收益 = (新吞吐 / 基线吞吐 - 1) × 100%
```

## 晋级标准

每季度用证据自评，而不是按“看完多少资料”自评：

- 初级：能运行训练和查看指标，但需要他人给出定位路径。
- 独立：能设计对照实验，定位单机或常见分布式问题，并提交带回归测试的修复。
- 高级：能处理跨计算、通信、数据、存储的复杂问题，解释权衡并推动方案落地。
- 专家：能形成方法论和平台能力，解决新型问题，指导他人，并对稳定性与长期演进负责。

第 52 周若尚未满足“专家”项，不代表计划失败。应根据证据选择一个子方向再深挖 6 到 12 个月，而不是继续横向堆术语。
