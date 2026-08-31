# PyTorch 训练效能第 1 周第 2 课：训练环境体检实战

训练任务出现“CUDA 不可用”“找不到 GPU”“性能突然下降”或“同样代码在另一台机器报错”时，第一步不是重装环境，而是把环境事实完整记录下来。

这一课会完成一次训练环境体检。你将运行课程自带的 `00_environment.py`，并用 Linux 与 NVIDIA 工具交叉验证结果。

## 一、本课目标

学完后，你应该能够：

- 区分 NVIDIA 驱动、CUDA runtime、PyTorch CUDA 构建版本和 cuDNN；
- 判断当前安装的是 CPU 版还是 CUDA 版 PyTorch；
- 判断“PyTorch 看不到 GPU”发生在哪一层；
- 读懂环境检查脚本的每个字段；
- 使用 `ps`、`top`、`nvidia-smi` 观察真实训练进程；
- 生成一份可以随故障单或性能报告提交的环境快照。

## 二、最容易混淆的四个版本

### 1. NVIDIA 驱动

驱动负责让操作系统和 NVIDIA GPU 通信。执行：

```bash
nvidia-smi
```

顶部通常会显示：

```text
Driver Version: xxx.xx
CUDA Version: xx.x
```

这里的 `CUDA Version` 表示当前驱动最高支持到哪个 CUDA 兼容级别，并不表示你一定安装了同版本的 CUDA Toolkit，也不表示 PyTorch 一定使用这个版本构建。

### 2. CUDA Toolkit

Toolkit 包含 `nvcc`、头文件、开发库和调试工具等，主要用于编译 CUDA 程序或 CUDA 扩展。

查看 `nvcc`：

```bash
which nvcc
nvcc --version
```

仅运行预编译的 PyTorch wheel 时，本机不一定需要完整 Toolkit。编译自定义 CUDA 扩展时则通常需要匹配的开发环境。

### 3. PyTorch CUDA 构建版本

Python 中执行：

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda)"
```

`torch.version.cuda` 表示当前 PyTorch 是基于哪个 CUDA 版本构建的。若输出 `None`，通常说明安装的是 CPU 版 PyTorch。

### 4. cuDNN

cuDNN 是 NVIDIA 面向深度学习算子的加速库。查看 PyTorch 当前可见的 cuDNN 版本：

```bash
python -c "import torch; print(torch.backends.cudnn.version())"
```

CPU 版 PyTorch 或没有可用 cuDNN 时，可能输出 `None`。

### 5. 它们之间的关系

可以先用下面这张简化图理解：

```text
PyTorch Python API
       |
       v
PyTorch C++ / CUDA 运行库 + cuDNN 等依赖
       |
       v
NVIDIA Driver
       |
       v
GPU Hardware
```

`nvcc --version` 与 `torch.version.cuda` 不一样，并不自动代表错误。真正要检查的是当前组合是否兼容，以及训练是否调用了你预期的运行库。

## 三、准备独立学习环境

进入学习目录，自己决定，随意一个目录即可。
创建独立虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip --version
```

CPU 环境可安装 CPU wheel：

```bash
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

GPU 环境不要盲目复制这条命令。应先确认：

- 公司基础镜像中是否已经安装 PyTorch；
- 驱动版本；
- 团队规定的 PyTorch/CUDA/NCCL 兼容矩阵；
- 是否需要使用内部镜像源；
- 是否依赖团队自定义 C++/CUDA 扩展。


### GPU 环境如何安装 PyTorch

如果是个人学习环境，并且机器上已经有可用的 NVIDIA 驱动，可以按下面的步骤安装。

#### 第一步：确认驱动能够识别 GPU

```bash
nvidia-smi
```

至少要能看到 GPU 型号和 Driver Version。如果 `nvidia-smi` 本身报错，应先解决驱动、设备权限或容器 GPU 映射问题。此时反复安装 PyTorch 没有意义。

#### 第二步：选择 PyTorch 官方提供的 CUDA wheel

打开 PyTorch 官方安装页面的 **Start Locally**，根据操作系统、包管理器和当前提供的 CUDA 版本生成命令：

```text
https://pytorch.org/get-started/locally/
```

官方 wheel 地址中的标签通常类似：

```text
cu126  表示基于 CUDA 12.6 构建
cu128  表示基于 CUDA 12.8 构建
cpu    表示不包含 CUDA 支持
```

这些只是标签示例。PyTorch 官方当前提供哪些版本会随时间变化，应以安装页面当天生成的命令和团队兼容矩阵为准。

例如，假设官方安装页面为你的环境推荐 CUDA 12.6 wheel，可以执行：

```bash
python -m pip install --upgrade pip
python -m pip install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu126
```

如果课程只使用 PyTorch，不需要图像和音频扩展，可以只安装 `torch`：

```bash
python -m pip install torch \
  --index-url https://download.pytorch.org/whl/cu126
```

如果官方页面推荐的是其他标签，例如 `cu128`，就应该使用官方生成的对应地址，不能因为示例写的是 `cu126` 就照抄。

如果虚拟环境中先前误装了 CPU 版，并且 pip 没有按预期替换，可以先确认当前环境，再重新安装：

```bash
which python
python -m pip show torch
python -m pip uninstall -y torch torchvision torchaudio

# 再执行官方页面为当前环境生成的 GPU 安装命令。
python -m pip install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu126
```

不要在生产环境或团队基础镜像中直接执行卸载命令。这里仅适用于你自己创建、可以随时删除重建的 `.venv`。

#### 第三步：验证安装的到底是不是 CUDA 版

```bash
python - <<"PY"
import torch

print("torch version:", torch.__version__)
print("torch CUDA build:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
print("visible GPU count:", torch.cuda.device_count())

if torch.cuda.is_available():
    print("GPU 0:", torch.cuda.get_device_name(0))
    x = torch.tensor([1.0, 2.0, 3.0], device="cuda")
    print("tensor device:", x.device)
    print("calculation result:", (x * 2).cpu().tolist())
PY
```

正常的 GPU 环境至少应满足：

- `torch.version.cuda` 不是 `None`；
- `torch.cuda.is_available()` 为 `True`；
- `torch.cuda.device_count()` 大于 0；
- CUDA tensor 能创建、计算并拷回 CPU。

#### 第四步：理解 wheel、驱动和 Toolkit 的关系

从 PyTorch 官方索引安装的 CUDA wheel 通常会带上运行所需的 CUDA 用户态依赖。因此，仅运行官方预编译 PyTorch 时，一般不要求本机 `nvcc --version` 与 `torch.version.cuda` 完全一致，甚至不一定需要安装完整 CUDA Toolkit。

但下面这些场景通常需要额外关注本机 Toolkit 和编译器：

- 编译 `torch.utils.cpp_extension` CUDA 扩展；
- 编译自定义 CUDA 算子；
- 从源码构建 PyTorch；
- 使用依赖系统 CUDA Toolkit 的第三方库。

无论是否安装 Toolkit，NVIDIA 驱动都必须足够新，能够支持 wheel 使用的 CUDA runtime。不要只看 `nvcc --version` 判断驱动兼容性，应结合 `nvidia-smi`、PyTorch 官方版本说明和团队兼容矩阵。

#### 常见安装结果怎么判断

| 现象 | 常见原因 | 下一步 |
| --- | --- | --- |
| `torch.version.cuda is None` | 安装了 CPU wheel | 检查 pip 源和 wheel 标签，在独立环境中安装官方 CUDA wheel |
| `torch.version.cuda` 有值，但 `is_available()` 为 `False` | 驱动、设备映射、权限或 `CUDA_VISIBLE_DEVICES` 有问题 | 从 `nvidia-smi` 和设备可见性开始分层排查 |
| `nvidia-smi` 正常，但 `device_count()` 为 0 | GPU 被环境变量隐藏或容器没有正确暴露设备 | 检查 `CUDA_VISIBLE_DEVICES` 和容器启动参数 |
| import 时提示动态库错误 | wheel、驱动、系统库或自定义扩展冲突 | 保存完整报错和版本信息，不要随意拼接 `LD_LIBRARY_PATH` |
| 自定义 CUDA 扩展编译失败 | 系统 Toolkit、编译器或 ABI 不匹配 | 按团队的 PyTorch/CUDA/GCC 兼容矩阵重建环境 |

生产环境中随意升级 PyTorch 可能破坏 ABI、CUDA 扩展、checkpoint 或分布式行为。本课程的虚拟环境只用于个人实验。

## 四、运行环境检查脚本

执行：

```bash
python 00_environment.py
```

```text
# 00_environment.py
from __future__ import annotations

import json
import os
import platform
import sys

import torch


def main() -> None:
    report: dict[str, object] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "torch": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "cudnn": torch.backends.cudnn.version(),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "num_threads": torch.get_num_threads(),
        "num_interop_threads": torch.get_num_interop_threads(),
        "devices": [],
    }
    devices: list[dict[str, object]] = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            devices.append(
                {
                    "index": index,
                    "name": props.name,
                    "capability": f"{props.major}.{props.minor}",
                    "total_memory_bytes": props.total_memory,
                }
            )
    report["devices"] = devices
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

```

脚本会输出类似下面的 JSON：

```json
{
  "python": "3.12.3",
  "platform": "Linux-6.x-x86_64-with-glibc2.xx",
  "cpu_count": 32,
  "torch": "2.x.x",
  "torch_cuda_build": "12.x",
  "cuda_available": true,
  "cudnn": 9xxxx,
  "deterministic_algorithms": false,
  "num_threads": 16,
  "num_interop_threads": 16,
  "devices": [
    {
      "index": 0,
      "name": "NVIDIA ...",
      "capability": "8.0",
      "total_memory_bytes": 85899345920
    }
  ]
}
```

实际值以你的机器为准。CPU 学习环境中 `cuda_available` 为 `false`、`devices` 为空是正常结果。

## 五、逐字段读懂报告

### `python`

当前解释器版本。还要确认实际使用的是哪个解释器：

```bash
which python
python -c "import sys; print(sys.executable)"
```

常见故障是 `pip` 安装到了环境 A，运行脚本时却使用环境 B。优先使用：

```bash
python -m pip install ...
```

这样 pip 会跟随当前 `python`。

### `platform`

包含内核、架构和 libc 等平台信息。C++/CUDA 扩展、预编译 wheel 和某些高性能库会受这些信息影响。

额外记录：

```bash
uname -a
uname -m
ldd --version | head -n 1
```

### `cpu_count`

它来自 `os.cpu_count()`，通常表示 Python 可见的逻辑 CPU 数，但在容器或 cgroup 环境中，它未必等于任务真正可使用的 CPU 配额。

交叉检查：

```bash
lscpu
nproc
grep Cpus_allowed_list /proc/self/status
```

如果宿主机有 128 个逻辑 CPU，但任务只允许使用 8 个，DataLoader 和 OpenMP 参数应以实际配额为基础。

### `torch`

PyTorch 版本。为了让实验可复现，只记录 `2.x` 不够，应记录完整版本字符串，例如 `2.5.1+cu124`。

查看安装位置：

```bash
python -c "import torch; print(torch.__file__)"
python -m pip show torch
```

### `torch_cuda_build`

PyTorch 的 CUDA 构建版本，不是驱动版本，也不一定等于本机 `nvcc` 版本。

判断 CPU 版 PyTorch：

```python
import torch

print(torch.version.cuda is None)
```

### `cuda_available`

`torch.cuda.is_available()` 是一个综合结果。它为 `false` 时，可能原因包括：

- 机器没有 NVIDIA GPU；
- 安装了 CPU 版 PyTorch；
- 容器没有映射 GPU；
- 驱动不可访问或版本不兼容；
- `CUDA_VISIBLE_DEVICES` 隐藏了设备；
- 环境中的动态库发生冲突。

它为 `true` 只能说明 PyTorch 当前能初始化 CUDA，并不能证明性能正常。

### `cudnn`

PyTorch 当前识别到的 cuDNN 版本。遇到卷积算子异常、确定性或性能变化时，这是重要环境字段。

### `deterministic_algorithms`

表示是否要求 PyTorch 使用确定性算法。开启确定性有助于复现，但某些操作可能报错或变慢。不能为了“结果一样”在不了解影响时全局打开，也不能为了性能随意关闭团队要求的确定性设置。

### `num_threads` 与 `num_interop_threads`

- `num_threads`：单个算子内部可使用的 CPU 线程数；
- `num_interop_threads`：多个算子之间调度所使用的线程数。

还应记录相关环境变量：

```bash
env | grep -E '^(OMP|MKL|OPENBLAS|NUMEXPR|TORCH)_'
```

注意不要在共享环境报告中泄露包含 token、密码或私有地址的无关环境变量。只筛选必要字段。

### `devices`

包括 PyTorch 可见的 GPU 编号、型号、计算能力和总显存。

`index=0` 表示当前进程看到的逻辑编号 0，不一定是宿主机的物理 GPU 0。若设置：

```bash
CUDA_VISIBLE_DEVICES=3,5 python train.py
```

进程内部通常会把物理设备 3、5 重新编号为逻辑设备 0、1。

## 六、用命令交叉验证

### 1. Python 与 PyTorch

```bash
which python
python --version
python -m pip show torch
python -c "import torch; print(torch.__version__, torch.__file__)"
```

检查点：版本与路径是否属于刚激活的 `.venv`。

### 2. 操作系统与 CPU

```bash
uname -a
lscpu
free -h
df -h
ulimit -a
```

检查点：

- CPU 架构和可见核心数；
- 内存与 swap；
- 数据盘是否接近写满；
- 打开文件数限制是否可能影响大量小文件读取。

### 3. NVIDIA 驱动与 GPU

```bash
nvidia-smi
nvidia-smi -L
nvidia-smi --query-gpu=index,name,uuid,driver_version,memory.total --format=csv
```

检查点：

- 驱动能否正常读取设备；
- GPU 数量和型号是否符合任务申请；
- PyTorch 看到的设备数是否与 `CUDA_VISIBLE_DEVICES` 一致。

### 4. CUDA 可见性

```bash
printf '%s\n' "${CUDA_VISIBLE_DEVICES-<not set>}"
python -c "import torch; print(torch.cuda.device_count())"
```

不要把未定义变量和空字符串混为一谈。空的 `CUDA_VISIBLE_DEVICES` 通常会隐藏所有 GPU。

## 七、运行一个最小 PyTorch 设备实验

创建或直接在终端运行：

```bash
python - <<'PY'
import time
import torch

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("device:", device)

x = torch.randn(2048, 2048, device=device)
y = torch.randn(2048, 2048, device=device)

if device.type == "cuda":
    torch.cuda.synchronize()
started = time.perf_counter()
z = x @ y
if device.type == "cuda":
    torch.cuda.synchronize()

print("shape:", tuple(z.shape))
print("elapsed_seconds:", time.perf_counter() - started)
print("checksum:", z.sum().item())
PY
```

这里在计时前后调用 `torch.cuda.synchronize()`，因为 CUDA 操作通常是异步提交的。第一周只需知道“不同步可能测错”；第 8 周会系统学习 warmup、重复次数、分位数和 CUDA Event。

## 八、观察训练进程

运行一个持续时间足够长的任务：

```bash
python 01_train_baseline.py --steps 1000
```

```python
# lab_utils.py
from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path
from typing import Any

import torch


def seed_everything(seed: int, deterministic: bool = False) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.use_deterministic_algorithms(True)


def best_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)
    return ordered[max(index, 0)]


def write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {output}")


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def torch_load(path: Path) -> dict[str, Any]:
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:  # PyTorch versions before the weights_only argument.
        return torch.load(path, map_location="cpu")


def atomic_torch_save(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    torch.save(payload, temporary)
    os.replace(temporary, path)

```

```python
# 01_train_baseline.py
from __future__ import annotations

import argparse
import time

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from lab_utils import best_device, seed_everything, synchronize, write_json


def make_dataset(samples: int, features: int, classes: int, seed: int) -> TensorDataset:
    generator = torch.Generator().manual_seed(seed)
    inputs = torch.randn(samples, features, generator=generator)
    teacher = torch.randn(features, classes, generator=generator)
    logits = inputs @ teacher + 0.1 * torch.randn(samples, classes, generator=generator)
    targets = logits.argmax(dim=1)
    return TensorDataset(inputs, targets)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a small reproducible classifier baseline.")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", help="Optional JSON result path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_everything(args.seed)
    device = best_device()
    dataset = make_dataset(samples=4096, features=32, classes=4, seed=args.seed)
    loader_generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, generator=loader_generator)
    model = nn.Sequential(nn.Linear(32, 64), nn.ReLU(), nn.Linear(64, 4)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)

    model.train()
    losses: list[float] = []
    processed = 0
    iterator = iter(loader)
    synchronize(device)
    started = time.perf_counter()
    for _ in range(args.steps):
        try:
            inputs, targets = next(iterator)
        except StopIteration:
            iterator = iter(loader)
            inputs, targets = next(iterator)
        inputs = inputs.to(device)
        targets = targets.to(device)
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.cross_entropy(model(inputs), targets)
        loss.backward()
        optimizer.step()
        losses.append(loss.item())
        processed += inputs.shape[0]
    synchronize(device)
    elapsed = time.perf_counter() - started

    model.eval()
    correct = 0
    with torch.no_grad():
        for inputs, targets in DataLoader(dataset, batch_size=512):
            predictions = model(inputs.to(device)).argmax(dim=1).cpu()
            correct += int((predictions == targets).sum())
    accuracy = correct / len(dataset)
    window = min(10, len(losses))
    first_loss = sum(losses[:window]) / window
    final_loss = sum(losses[-window:]) / window
    result = {
        "device": str(device),
        "seed": args.seed,
        "steps": args.steps,
        "samples_per_second": processed / elapsed,
        "first_loss": first_loss,
        "final_loss": final_loss,
        "accuracy": accuracy,
    }
    print(result)
    write_json(args.output, result)

    if args.steps >= 50:
        assert final_loss < first_loss * 0.75, "loss did not decrease enough"
        assert accuracy > 0.75, "accuracy is below the baseline acceptance threshold"


if __name__ == "__main__":
    main()

```

另开终端执行下面这一行，自动查找最新的训练进程，并一次性输出进程摘要与线程快照：

```bash
pid=$(pgrep -n -f '[0]1_train_baseline.py'); if [ -n "$pid" ]; then printf 'PID=%s\n' "$pid"; ps -o pid,ppid,nlwp,stat,%cpu,%mem,rss,etime,cmd -p "$pid"; top -b -n 1 -H -p "$pid"; else echo '未找到正在运行的 01_train_baseline.py'; fi
```

![结果:](./screenshot-20260831-121021.png)

有 GPU 时再运行：

```bash
nvidia-smi pmon -s um -d 1
```

![结果2:](./screenshot-20260831-121109.png)

记录：

- 主进程 PID 和 PPID；
- 线程数；
- CPU 使用率；
- RSS；
- GPU 编号、显存和利用率；
- 任务结束后进程是否正常退出。

如果任务结束太快，可以增大 `--steps`，但不要为了观察而在共享训练机上创建过大的无意义负载。

## 九、`cuda_available=false` 的分层排查

按下面顺序排查，不要直接重装：

### 第 1 层：硬件和驱动

```bash
nvidia-smi
```

如果这里失败，优先检查节点、驱动、容器 GPU 映射或设备权限，而不是 PyTorch 代码。

### 第 2 层：进程是否能看到设备

```bash
printf '%s\n' "${CUDA_VISIBLE_DEVICES-<not set>}"
ls -l /dev/nvidia* 2>/dev/null
```

容器中还要确认启动时是否申请并映射 GPU。

### 第 3 层：PyTorch 是否为 CUDA 构建

```bash
python -c "import torch; print(torch.__version__, torch.version.cuda)"
```

若 `torch.version.cuda` 为 `None`，说明当前 PyTorch 本身不含 CUDA 支持。

### 第 4 层：动态库与版本

记录完整报错、PyTorch 版本、驱动、CUDA 构建版本和容器镜像。不要通过反复修改 `LD_LIBRARY_PATH` 掩盖问题，这可能制造更隐蔽的库冲突。

## 十、生成环境快照

在实验目录中保存非敏感信息：

```bash
mkdir -p artifacts/week01
python labs/00_environment.py > artifacts/week01/environment.json
python -m pip freeze > artifacts/week01/pip-freeze.txt
uname -a > artifacts/week01/uname.txt
lscpu > artifacts/week01/lscpu.txt
```

有 GPU 时：

```bash
nvidia-smi -q > artifacts/week01/nvidia-smi-q.txt
```

提交或共享前检查内容，避免包含：

- API key、token、cookie；
- 内部仓库凭据；
- 私有镜像密码；
- 不必要的用户名、主机名或内部网络信息。

## 十一、本课练习

### 必做练习

1. 运行 `00_environment.py` 并逐字段写一句解释。
2. 用命令确认 `python`、`pip` 和 `torch` 属于同一虚拟环境。
3. 解释 `nvidia-smi` 的 CUDA Version 与 `torch.version.cuda` 的区别。
4. 运行最小矩阵乘实验并记录设备、耗时和 checksum。
5. 观察一次训练进程的 PID、线程数、RSS 和 CPU/GPU 占用。

### 故障演练

在有 GPU 的个人实验环境中运行：

```bash
CUDA_VISIBLE_DEVICES='' python labs/00_environment.py
```

比较正常报告和隐藏 GPU 后的报告，回答：

- `torch.version.cuda` 是否改变？
- `cuda_available` 是否改变？
- 为什么这两个字段可能给出不同层面的信息？

## 十二、验收标准

满足以下条件才算完成本课：

- 环境 JSON 能正常生成；
- 能判断 CPU 版和 CUDA 版 PyTorch；
- 能解释驱动、Toolkit、PyTorch CUDA 构建和 cuDNN 的边界；
- 能根据 `cuda_available=false` 给出分层排查顺序；
- 能找出真实训练进程并记录 CPU、内存和 GPU 信息；
- 环境快照不包含凭据等敏感数据。

下一课会把本次环境快照、训练命令和三次重复测量整理成标准实验记录，并使用 Git 保存可追踪的研发基线。


## 十三、上一课验收问题回顾

上一课要求从进程观察实验和训练链路中回答几个问题。下面给出简短结论，便于在开始本课前复习。

### 1. 这个进程共有多少个线程？

看 `ps` 输出中的 `NLWP`。例如：

```text
PID      PPID    NLWP  STAT  %CPU
4102648  4101195     3  Sl+    100
```

`NLWP=3` 表示这个进程当前有 3 个线程：1 个主线程加上 2 个由实验代码创建的 worker 线程。`ps -T -p <PID>` 可以列出每个线程的 TID，`top -H -p <PID>` 可以按线程观察 CPU 使用率。

### 2. 两个 Python CPU 线程是否让 `%CPU` 稳定达到约 200%？

不一定。你记录到 `%CPU=100` 是正常且有价值的结果：两个线程都执行 Python 字节码时会受到 CPython GIL 影响，同一时刻通常只有一个线程真正执行 Python 字节码，因此整体 CPU 使用率可能接近一个逻辑核，而不是两个逻辑核。

这不是“Python 线程永远不能并行”的证明。I/O 等待，以及会释放 GIL 的 C/C++ 扩展，可能允许线程产生并行收益；CPU 密集型纯 Python 代码通常更适合多进程或改写为向量化/C++ 扩展。

### 3. 如果没有达到 200%，Python GIL 产生了什么影响？

GIL 是 CPython 用来保护解释器内部对象状态的一把锁。多个线程可以并发存在，但执行纯 Python 字节码时通常需要轮流获得 GIL，所以线程数增加不等于 Python 计算吞吐线性增加。

排查时要先确认工作负载：

- 纯 Python CPU 计算：优先考虑多进程、NumPy/PyTorch 向量化或 C/C++ 扩展；
- 文件、网络等 I/O 等待：线程可能有效；
- Pillow、OpenCV、PyTorch 等释放 GIL 的扩展：要用实际 benchmark 验证；
- 多进程：还要额外考虑序列化、进程内存、共享内存和 worker 启动成本。

### 4. `time.sleep` 是否会持续占用 CPU？

不会。`time.sleep` 会让线程进入等待状态，通常不会持续消耗 CPU。它增加的是墙钟时间，而不是相同数量的 User CPU time。

因此“任务运行了 2 秒”和“CPU 计算了 2 秒”是两件事。训练中的磁盘、网络、队列、锁和 GPU 等待，也可能让墙钟时间增加而 CPU 使用率不高。

### 5. 如何从 `ps` 输出判断进程关系、线程数、CPU 和内存？

- `PID`：当前进程编号；
- `PPID`：父进程编号，可判断是谁启动了它；
- `NLWP`：线程数；
- `STAT`：状态，例如 `R` 运行、`S` 睡眠、`D` I/O 等待；
- `%CPU`：一段采样窗口内的 CPU 使用率，多核机器上可能超过 100%；
- `RSS`：实际驻留在物理内存中的大小；
- `ETIME`：进程已运行时间。

不要只看一列就下结论。例如 `%CPU` 低可能是 I/O 等待，也可能是线程没有并行；`RSS` 高可能来自数据预取、page cache 以外的进程内对象或多个 worker。

### 6. 训练数据从哪里到哪里？

最基本的路径是：

```text
磁盘/对象存储 → CPU 内存 →（可选 pinned memory）→ PCIe/NVLink → GPU 显存 → 前向/反向计算
```

其中读取、解码、增强和拼 batch 通常发生在 CPU/DataLoader worker；模型计算和优化器更新主要发生在 GPU。任一环节慢，都会让端到端吞吐下降。

### 7. GPU 利用率低至少有哪些非 GPU 计算原因？

常见原因包括：

1. 磁盘、对象存储或网络文件系统读取慢；
2. 图像/视频解码慢；
3. CPU 数据增强、collate 或 Python 调度慢；
4. Host-to-Device 拷贝慢或没有使用合适的 pinned memory/异步拷贝；
5. DataLoader worker 数量不合适、线程过量或队列供应不足；
6. DDP 中等待慢 rank 或 collective 通信；
7. batch 太小、算子过碎或频繁 kernel launch。

正确做法是用分段计时和 profiler 证明瓶颈，而不是看到 GPU 利用率低就直接修改模型或盲目增加 worker。

### 8. 本课应该带走的结论

上一课的重点不是背命令输出，而是建立排查顺序：

```text
先确认环境事实 → 找到进程和线程 → 区分计算与等待 → 画出数据路径 → 再提出可验证的优化假设
```

本课接下来会把这套顺序落实到 Python、PyTorch、CUDA 和驱动的环境体检中。
