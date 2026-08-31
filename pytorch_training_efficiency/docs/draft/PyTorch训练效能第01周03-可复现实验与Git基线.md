# PyTorch 训练效能第 1 周第 3 课：可复现实验与 Git 基线

训练效能团队最重要的工程习惯之一，是让别人能够重复你的实验，并从原始证据得到相同结论。

下面这种描述不能算性能结论：

> 我把 DataLoader worker 从 4 调到 8，感觉快了很多。

它缺少环境、代码版本、完整命令、原始结果、重复次数、正确性检查和波动分析。即使数字真的变快，也无法判断收益来自代码修改、缓存变热、其他任务退出，还是测量误差。

本课将建立第一份实验基线：固定代码与环境，同一训练命令运行三次，保存原始结果，并用 Git 关联到确切代码版本。

## 一、本课目标

学完后，你应该能够：

- 解释为什么性能结果必须绑定代码、环境、配置和数据版本；
- 使用 Git 分支、提交和 commit ID 管理实验代码；
- 设计一个只有单一自变量的对照实验；
- 重复运行实验并计算均值、标准差和变异系数；
- 区分 warmup、缓存效应、系统噪声和真实优化收益；
- 写出一份包含原始证据、正确性门槛和结论边界的实验报告。

## 二、什么叫可复现实验

一份训练性能实验至少由以下要素共同决定：

```text
结果 = f(
    代码版本,
    模型与超参数,
    数据版本和采样方式,
    软件环境,
    硬件与资源配额,
    启动命令,
    随机种子,
    测量方法,
    系统负载
)
```

只要其中一个要素改变，结果就可能改变。

可复现不等于“每次浮点结果逐位相同”。根据目标不同，可以分成：

- 运行可复现：别人能够使用相同命令成功运行；
- 实验可复现：关键指标落在合理误差范围内；
- 数值可复现：loss、梯度或参数满足规定误差；
- 位级可复现：结果的每一位都一致，要求最高且可能影响性能。

第一周先追求运行可复现和实验可复现。第 7 周会深入随机性和确定性。

## 三、Git 在实验中的作用

Git 不只是团队协作工具，它还是实验代码的版本坐标。

### 1. 查看当前状态

```bash
git status --short
git branch --show-current
git log -1 --oneline
```

其中：

- `git status` 告诉你是否存在未提交修改；
- 分支名说明当前工作上下文；
- commit ID 标识一份确定的代码快照。

### 2. 为实验创建分支

在个人练习仓库中可以执行：

```bash
git switch -c learn/week01-baseline
```

不要在团队共享仓库中随意创建或推送分支，应遵循团队命名与评审规范。

### 3. 一次提交只表达一个目的

例如：

```bash
git add <本次实验相关文件>
git commit -m "lab: add week 1 training baseline"
```

好的提交应该：

- 改动范围集中；
- 提交信息说明为什么改；
- 不包含数据集、checkpoint、trace 等巨大产物；
- 不包含 token、cookie、密码和内部凭据；
- 能通过最小正确性检查。

### 4. 工作区不干净时如何记录

实验结果绑定 commit ID 还不够。如果存在未提交修改，同一个 commit 可能对应不同代码。

记录：

```bash
git rev-parse HEAD
git status --short
git diff --stat
```

正式 benchmark 最好在干净工作区运行。若无法做到，必须保存 patch 或明确记录未提交改动。

### 5. 不要把实验产物全部提交到 Git

通常应忽略：

```gitignore
.venv/
artifacts/
__pycache__/
*.pyc
*.pt
*.pth
```

但团队可能要求把小型 JSON 结果、测试基线或报告纳入版本控制。是否提交取决于产物大小、复现价值和仓库规范。

## 四、建立实验目录

进入课程目录：

```bash
cd /media/wangpan/hdd1/0-me/zhihu/pytorch_training_efficiency
source .venv/bin/activate
```

创建本周产物目录：

```bash
mkdir -p artifacts/week01/runs
```

保存环境信息：

```bash
python labs/00_environment.py > artifacts/week01/environment.json
python -m pip freeze > artifacts/week01/pip-freeze.txt
git rev-parse HEAD > artifacts/week01/git-commit.txt
git status --short > artifacts/week01/git-status.txt
```

如果当前目录还不是 Git 仓库，则在自己的练习目录初始化：

```bash
git init
```

本仓库本身已有 Git 历史，不要重复执行 `git init`。

## 五、先定义实验问题与验收标准

本次实验不比较两个优化方案，而是测量基线波动。

实验问题：

```text
同一机器、同一代码、同一命令连续运行三次时，训练吞吐和最终结果波动多大？
```

控制变量：

```text
代码：同一个 commit 和相同工作区
模型：01_train_baseline.py 内置模型
数据：固定合成数据和 seed
设备：同一台机器、同一 CPU 或 GPU
配置：steps=100、batch-size=128、seed=2026
测量：脚本内统一同步和计时
```

正确性门槛：

```text
脚本退出码为 0
final_loss < first_loss × 0.75
accuracy > 0.75
三次运行均满足上述条件
```

性能指标：

```text
samples_per_second
三次结果的均值、最小值、最大值、标准差、变异系数
```

## 六、同一命令运行三次

执行：

```bash
python labs/01_train_baseline.py \
  --steps 100 \
  --batch-size 128 \
  --seed 2026 \
  --output artifacts/week01/runs/run-1.json

python labs/01_train_baseline.py \
  --steps 100 \
  --batch-size 128 \
  --seed 2026 \
  --output artifacts/week01/runs/run-2.json

python labs/01_train_baseline.py \
  --steps 100 \
  --batch-size 128 \
  --seed 2026 \
  --output artifacts/week01/runs/run-3.json
```

为什么不用只运行一次？

因为性能会受到以下噪声影响：

- CPU 频率与功耗状态；
- GPU 动态频率和温度；
- 文件系统与程序缓存；
- 同机其他任务；
- 操作系统调度；
- 首次初始化和库加载；
- 后台监控、日志和网络活动。

三次仍然只是最低要求。正式性能回归通常需要更多重复、稳定机器和统计规则。

## 七、汇总三次结果

使用标准库读取三个 JSON：

```bash
python - <<'PY'
import json
import statistics
from pathlib import Path

paths = sorted(Path("artifacts/week01/runs").glob("run-*.json"))
if len(paths) != 3:
    raise SystemExit(f"expected 3 result files, found {len(paths)}")

records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
throughputs = [record["samples_per_second"] for record in records]

mean = statistics.mean(throughputs)
stdev = statistics.stdev(throughputs)
cv = stdev / mean * 100

for path, record in zip(paths, records):
    print(
        path.name,
        f"throughput={record['samples_per_second']:.2f}",
        f"accuracy={record['accuracy']:.4f}",
        f"final_loss={record['final_loss']:.4f}",
    )

print(f"mean={mean:.2f} samples/s")
print(f"min={min(throughputs):.2f} samples/s")
print(f"max={max(throughputs):.2f} samples/s")
print(f"stdev={stdev:.2f} samples/s")
print(f"coefficient_of_variation={cv:.2f}%")
PY
```

### 1. 均值

三次吞吐的算术平均值：

```text
mean = (x1 + x2 + x3) / 3
```

均值适合作为摘要，但会受极端值影响，不能替代原始数据。

### 2. 标准差

标准差描述结果围绕均值的绝对波动。不同规模的实验只比较标准差不够直观。

### 3. 变异系数

```text
CV = 标准差 / 均值 × 100%
```

CV 将波动表示为均值的百分比，便于跨不同吞吐规模比较。

不要机械规定“CV 小于某个数字就一定合格”。CPU 小实验、GPU 长时间训练、共享集群和微基准的合理波动范围不同。第一周的目标是观察并解释，而不是追求一个漂亮阈值。

## 八、为什么三次结果会不同

按证据逐层分析，不要只写“系统有波动”。

### 情况 1：第一次明显更慢

可能原因：

- Python 模块与动态库首次加载；
- CUDA context 初始化；
- cuDNN 或编译器首次选择算法；
- page cache、代码缓存尚未变热；
- CPU/GPU 尚未升频。

验证方法：增加一次不计入正式结果的 warmup run，再比较后续结果。

### 情况 2：结果随机上下波动

可能原因：

- 共享机器上的其他进程；
- CPU 调度或频率变化；
- GPU 被其他任务共享；
- 温度或功率限制；
- 后台 I/O。

验证方法：同时保存 `top`、`nvidia-smi dmon` 或团队监控时间线，并换到独占资源重测。

### 情况 3：吞吐相同但 accuracy 不同

可能原因：

- 随机种子未覆盖所有随机源；
- 非确定性算子；
- 数据顺序变化；
- 环境或代码实际不同。

不能因为性能数字稳定就忽略正确性差异。任何优化都必须先满足正确性门槛。

### 情况 4：第二次和第三次更快

不要直接把快的结果挑出来作为结论。应说明缓存效应，并根据业务场景决定测冷启动、热启动还是两者都测。

在线训练长期运行通常更关注稳态性能；短任务或频繁弹性重启则不能忽略初始化成本。

## 九、设计对照实验的基本规则

后续每次优化都遵循以下规则。

### 规则 1：一次只改变一个主要变量

错误示例：同时修改 batch size、worker 数、精度和模型代码，然后声称某个参数提速。

正确示例：固定其他条件，只比较 `num_workers=2` 和 `num_workers=4`。

### 规则 2：先写假设，再看结果

例如：

```text
假设：当前数据解码是串行瓶颈，将 worker 从 2 增加到 4 会降低数据等待时间。
证伪条件：worker 增加后等待时间不降，或 CPU 已饱和且吞吐不升。
```

如果先看完所有结果再编故事，很容易产生确认偏误。

### 规则 3：优化前后使用同一正确性门槛

把数据丢掉、少跑 step 或降低数值精度可能让程序变快，但不一定完成相同工作。

至少核对：

- 有效样本或 token 数；
- global batch；
- step 数和优化器更新次数；
- loss/梯度/最终指标；
- 数据是否丢失、重复或损坏。

### 规则 4：保留失败实验

失败的假设同样有价值。它能减少团队重复试错，并帮助缩小问题范围。

## 十、标准实验记录模板

在 `artifacts/week01/report.md` 中写入以下结构：

````markdown
# 第 1 周训练基线实验报告

## 1. 问题

同一训练命令运行三次时，吞吐和正确性指标波动多大？

## 2. 假设

固定 seed 后正确性指标应一致；性能指标会因系统噪声产生小幅波动。

## 3. 环境

- 日期：
- 机器或资源规格：
- Python：
- PyTorch：
- CUDA 构建版本：
- GPU 与驱动：
- CPU 配额与内存：
- Git commit：
- Git 工作区是否干净：

## 4. 完整命令

```bash
python labs/01_train_baseline.py --steps 100 --batch-size 128 --seed 2026 ...
```

## 5. 控制变量与正确性门槛

- 控制变量：
- 正确性门槛：
- warmup 和重复次数：

## 6. 原始结果

| Run | samples/s | first loss | final loss | accuracy |
| --- | ---: | ---: | ---: | ---: |
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

## 7. 汇总

- 吞吐均值：
- 最小值/最大值：
- 标准差：
- 变异系数：

## 8. 观察与解释

- 哪次最慢？
- 是否有缓存或首次初始化影响？
- 同机是否存在其他负载？
- 正确性是否稳定？

## 9. 结论

只写数据能够支持的结论，并注明适用环境。

## 10. 下一步

下一项可以证伪当前解释的实验是什么？
````

报告中不要只放截图。JSON、CSV、trace 等机器可读原始数据更便于复查和自动化。

## 十一、一次完整的 Git 工作流

下面的流程适用于独立练习仓库。团队仓库应服从分支与评审规范。

```bash
# 1. 查看起点
git status --short
git branch --show-current

# 2. 创建实验分支
git switch -c learn/week01-baseline

# 3. 修改代码或文档后检查差异
git diff --stat
git diff --check

# 4. 运行正确性验证
python labs/01_train_baseline.py --steps 100

# 5. 只暂存相关文件
git add <相关文件>
git diff --cached

# 6. 提交
git commit -m "lab: establish week 1 training baseline"

# 7. 记录最终 commit
git rev-parse HEAD
```

不要用 `git add .` 代替审查。仓库中可能存在其他人的改动、实验大文件或敏感配置。

## 十二、如何写性能结论

不严谨的写法：

> 优化后训练速度提升 10%。

更严谨的写法：

> 在同一台独占机器、相同 commit 基线、batch size 128、100 个测量 step 下，方案 B 的三次吞吐均值由 10,100 samples/s 提升至 11,080 samples/s，提升 9.7%；两组 CV 分别为 1.2% 和 1.5%，accuracy 均满足大于 0.75 的门槛。本结论尚未覆盖长时间训练和多 GPU 场景。

一条可信结论应包括：

- 在什么环境；
- 比较什么版本；
- 完成什么等价工作；
- 如何测量；
- 原始值和波动；
- 正确性结果；
- 结论的适用边界。

## 十三、本课练习

### 必做练习

1. 保存环境 JSON、依赖列表、Git commit 和工作区状态。
2. 同一训练命令运行三次，保存三个独立 JSON。
3. 计算吞吐均值、最小值、最大值、标准差和 CV。
4. 按模板完成实验报告。
5. 提交前检查产物中没有 token、密码、私有地址和大文件。

### 进阶练习

增加一次 warmup run，但不纳入三次正式结果。比较加入 warmup 前后 CV 是否变化，并说明：

- 变化是否足以支持“首次初始化是主要噪声”的结论；
- 还需要采集什么证据；
- 实际业务更关注冷启动还是稳态性能。

### 故障练习

在其中一次运行期间启动一个 CPU 密集程序，再观察吞吐。不要在共享生产节点这样做，只能在个人可控环境中实验。

回答：

- 哪些系统指标能够证明资源争用？
- 这次异常结果应该删除、保留还是单独标记？
- 如果正式基准出现相同情况，重跑规则应该是什么？

合理做法通常是保留并标记异常结果，解释排除依据，再按预先定义的规则重跑，而不是看到结果不好就静默删除。

## 十四、第一周总验收

完成以下清单，才算结束第 1 周：

- [ ] 能解释进程、线程、CPU、内存、GPU 和三种时间；
- [ ] 完成环境体检并逐字段解释报告；
- [ ] 能分层排查 PyTorch 看不到 GPU；
- [ ] 保存三次基线训练的原始 JSON；
- [ ] 计算吞吐均值、标准差和变异系数；
- [ ] 三次训练均通过 loss 与 accuracy 门槛；
- [ ] 实验报告包含环境、命令、commit、原始数据、结论和下一步；
- [ ] 能解释本机实验波动，而不是只写“有噪声”；
- [ ] Git 提交范围清晰且未包含敏感信息或大型运行产物。

## 十五、向同事汇报时的 3 分钟结构

可以按下面的顺序汇报：

1. 我测的是什么，为什么要建立这条基线；
2. 环境、代码版本、命令和正确性门槛；
3. 三次原始结果及其波动；
4. 当前数据支持什么结论，不支持什么结论；
5. 下一项用于验证解释的实验。

第一周的目标不是做出显著性能优化，而是建立可信测量的起点。没有这个起点，后续所有“提速百分比”都可能失去意义。
