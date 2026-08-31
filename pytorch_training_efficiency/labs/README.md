# 配套实验

所有命令都从 `pytorch_training_efficiency/` 目录执行。先运行环境检查和基础训练，再按路线图逐步进入 profile、AMP 与分布式实验。

| 文件 | 验证内容 | 示例命令 |
| --- | --- | --- |
| `00_environment.py` | Python、PyTorch、CUDA、设备和确定性配置 | `python labs/00_environment.py` |
| `01_train_baseline.py` | 完整训练/评估循环、seed、吞吐与验收断言 | `python labs/01_train_baseline.py --steps 100` |
| `02_benchmark.py` | warmup、设备同步、p50/p95、JSON 原始结果 | `python labs/02_benchmark.py --output artifacts/benchmark.json` |
| `03_dataloader_benchmark.py` | 不同 worker 数下的数据等待与吞吐 | `python labs/03_dataloader_benchmark.py --workers 0 1 2 4` |
| `04_profiler.py` | operator 表和 Chrome trace | `python labs/04_profiler.py --output artifacts/trace.json` |
| `05_amp_accumulation.py` | 梯度累积等价性；可选 CUDA AMP | `python labs/05_amp_accumulation.py --micro-batch 16 --amp` |
| `06_ddp_train.py` | torchrun、ProcessGroup、DDP、Sampler、指标归约 | `torchrun --standalone --nproc-per-node=2 labs/06_ddp_train.py` |
| `07_checkpoint_resume.py` | 原子 checkpoint、optimizer 与 RNG 恢复 | `python labs/07_checkpoint_resume.py` |
| `08_memory_accounting.py` | 参数/梯度/优化器/激活的显存字节核算 | `python labs/08_memory_accounting.py` |

## 推荐实验记录

每次不要只粘贴终端最后一行。至少记录：

```text
日期、代码 commit：
机器、CPU/GPU、驱动、CUDA、PyTorch：
完整命令：
修改的唯一变量：
warmup / 重复次数：
吞吐、step p50/p95、峰值显存、loss/accuracy：
原始 JSON 或 trace：
结论与可以证伪它的下一项实验：
```

## 练习顺序

1. 原样运行，确认验收断言通过。
2. 故意制造错误，例如删除同步、漏掉 `set_epoch`、错误缩放 micro-batch loss、漏存 RNG。
3. 先描述预期症状，再运行验证。
4. 把实验换成团队真实模型或数据，但保留基线、控制变量和正确性门槛。

这些脚本用于学习，不是生产训练框架。生产代码还需要配置校验、结构化日志、监控、错误处理、版本兼容测试和集群环境适配。
