# PyTorch训练效能第03周03-FiniteDifference梯度检查与工程验收
课程使用的源码保存在github 这个项目：https://github.com/wangpan0921/pytorch_training_efficiency。

自动微分通常被当作可信的黑盒，但自定义 loss、手写算子或 Python/C++ 扩展一旦写错，训练可能只是悄悄变差。本课用不依赖 autograd 的 finite difference（有限差分）近似梯度，独立核对 `backward()`，并把它变成一个可重复的工程验收。

## 本课目标

- 推导中心差分近似及其误差来源；
- 用 float64、小模型和固定输入做梯度检查；
- 区分绝对误差、相对误差和 bitwise equality；
- 理解 epsilon 太大或太小时为什么都会出问题；
- 产出带阈值、原始梯度和误差的 `finite_difference.json`。

## 现象或问题

若只把实现结果和自己写的参考结果比较，两个实现可能共享同一个 bug。有限差分的思路是把参数某一维稍微向前、向后扰动，用目标函数值的变化估计斜率，不调用反向图：

```text
df/dθ_i ≈ [f(θ + ε e_i) - f(θ - ε e_i)] / (2ε)
```

它慢，因为每个参数至少需要两次前向；但在小模型和单元测试中，这个成本换来了独立性。

## 核心概念与最小模型

实验目标函数是三条样本的线性回归损失：

```python
residual = features @ weight + bias - target
loss = 0.5 * residual.square().mean()
```

参数向量为 `[w0, w1, b]`。脚本先用 `loss.backward()` 得到参考梯度，再逐个参数复制出 `plus` 和 `minus`，计算中心差分。有限差分阶段只调用普通 Tensor 运算，不读取 `parameters.grad`。

使用 `float64` 是为了让舍入误差小一些；这不是说生产训练必须用 float64。梯度检查验证的是数学实现，生产 dtype 仍应根据设备和数值稳定性选择。

## 逐步代码/命令

默认实验：

```bash
cd pytorch_training_efficiency
python labs/14_finite_difference.py --output artifacts/week03/finite_difference.json
```

脚本会记录：

- 输入参数、设备和 dtype；
- 中心差分的 `epsilon` 和验收 `tolerance`；
- autograd 梯度与 finite-difference 梯度；
- 每个参数的绝对误差和最大绝对误差。

验收断言是 `max_absolute_error <= tolerance`。默认 `epsilon=1e-6`、`tolerance=1e-5`，是这个小规模 float64 实验的起点，不是所有模型的通用阈值。

## 动手实验：预测、运行、解释

运行前预测：

1. 两种方法得到的三个梯度应非常接近；
2. `passed` 应为 `true`；
3. 误差最大的维度不应被忽略，而应结合该参数的尺度解释。

运行后打开 JSON，比较 `autograd_gradient`、`finite_difference_gradient` 和 `absolute_error`。如果最大误差小于阈值，这只能证明“这个输入附近的局部导数实现一致”，不能证明任意输入、任意 dtype 或所有分支都正确。

## 故障练习与边界

### 练习 A：故意把 backward 的符号写反

在一个复制版本中把参考梯度乘以 `-1`，再运行同样的比较。预期断言失败，并且误差接近梯度绝对值的两倍。这个结果说明验收确实能抓住方向错误，而不是只检查输出存在。

### 练习 B：改变 epsilon

分别运行：

```bash
python labs/14_finite_difference.py --epsilon 1e-2 --output /tmp/fd-large.json
python labs/14_finite_difference.py --epsilon 1e-8 --output /tmp/fd-small.json
```

较大的 epsilon 可能混入高阶曲率，太小则容易被浮点相减的舍入误差淹没。应记录误差随 epsilon 的变化，而不是挑一个看起来最好的数字。

### 练习 C：不用 float64

把脚本中的 dtype 改为 float32，并保持同一 epsilon。预期误差可能增大，说明容差必须与 dtype、函数尺度和参数尺度一起设定。

## 输出如何解读

`max_absolute_error` 是一个正确性门槛，不是速度指标。finite difference 比 autograd 慢很多也不矛盾，因为它为每个参数重复前向；它适合小规模 CI 或开发期检查，不适合替代真实训练的 backward。还要区分：

- 逻辑近似相等：在容差内；
- bitwise 相等：每一位完全一致，通常不应作为跨设备验收；
- 局部梯度正确：当前点附近通过检查；
- 全域实现正确：需要更多输入、边界和随机测试。

## 与训练效能的连接

梯度检查本身不是优化，但它防止把错误实现当成“性能优化”合入。自定义 CUDA/C++ 算子、复杂 loss、混合精度改造和梯度累积都可以先在小输入上做 finite-difference smoke test，再进行 profiler 和吞吐比较。正确性门槛通过后，性能回归才有意义。

## 本课验收

提交 `artifacts/week03/finite_difference.json`，并回答：

1. 为什么中心差分比单边差分更适合这个检查？
2. 为什么 epsilon 不能无限小？
3. 为什么通过局部梯度检查仍不能证明整个训练系统无 bug？

完成标准：默认命令通过；至少记录一组 epsilon 变化结果；能用最大绝对误差、dtype 和输入尺度解释一次通过或失败，而不是只报告“相等”。
