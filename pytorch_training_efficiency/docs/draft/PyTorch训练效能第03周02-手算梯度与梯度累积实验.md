# PyTorch训练效能第03周02-手算梯度与梯度累积实验
课程使用的源码保存在github 这个项目：https://github.com/wangpan0921/pytorch_training_efficiency。

上一课建立了计算图的 mental model。本课把它变成一组可检查的工程证据：固定输入、固定设备、固定 seed，先写出预期，再运行实验，最后用 JSON 复盘。目标不是追求一个 benchmark 数字，而是证明梯度和状态管理满足训练循环的契约。

## 本课目标

- 用一个标量线性模型逐项核对链式法则；
- 观察叶子参数、非叶子中间结果和 `retain_grad()`；
- 证明两个 backward 的梯度是相加的；
- 练习 `grad=None` 和数值零的区别；
- 产出可供同事复核的 `autograd_basics.json`。

## 现象或问题

“loss 能下降”不能单独证明反向传播正确。一个错误的 loss 缩放、漏掉清零或不小心 `detach()`，都可能让代码继续运行一段时间。最小可复现实验应同时检查：数值结果、梯度状态、参数身份和故障边界。

## 核心概念与最小模型

仍使用：

```text
x=2, y=5, w=1.5, b=0.25
z=w*x+b=3.25
L=1/2*(z-y)^2=1.53125       # 损失函数 L 是一个用来衡量模型预测结果和真实目标之间差距多大的函数。
```

手算得到：

```text
r=z-y=-1.75         # 误差 r：预测值 z 和 目标值 y 的差
dL/dw=r*x=-3.5      # 根据链式法则：dL/dw = dL/dr * dr/dz * dz/dw  = r * 1 * x = -1.75 * 2 = -3.5
dL/db=r=-1.75       # dL/db = dL/dr * dr/dz * dz/db = r * 1 * 1 = -1.75
```

第二次反向使用 `y+1` 作为目标。由于没有清零，参数梯度应为两次反向梯度的逐元素和。这个结论与“一个 batch 一个梯度”的直觉不同，正是需要通过实验固定下来的边界。

这里的“逐元素和”是指：如果参数是一个张量，那么两次反向传播得到的梯度张量会在每个对应位置分别相加。例如，第一次梯度是 `[1, 2]`，第二次梯度是 `[3, 4]`，两次 `backward()` 后保存的梯度就是 `[4, 6]`。PyTorch 不会自动覆盖之前的 `.grad`，因此连续调用 `backward()` 相当于把多个损失对同一参数的影响合并起来。

普通训练通常希望每个 batch 单独计算梯度，所以会在前向计算前先调用 `optimizer.zero_grad()`。如果忘记清零，当前 batch 的梯度就会混入前一个 batch 的梯度，参数更新的方向和大小都会发生变化。这个行为也可以被有意利用：把多个小 batch 的梯度累积起来，最后再调用一次 `optimizer.step()`，形成梯度累积训练。

```text
**小白科普**

梯度可以理解为：
损失函数对某个参数的变化有多敏感，以及参数应该往哪个方向调整。

对于参数 w，梯度写作：
dL/dw
它表示：w 发生一点变化时，损失 L 会怎样变化。

```

## 逐步代码/命令

```bash
cd pytorch_training_efficiency
python labs/13_autograd_basics.py --output artifacts/week03/autograd_basics.json
```

实验脚本默认 CPU，不下载数据。它会：

1. 创建 `requires_grad=True` 的 `weight` 和 `bias`；
2. 前向计算 `prediction` 与平方损失；
3. 用 `retain_grad()` 记录非叶子 `prediction` 的梯度；
4. 用手算公式和 `torch.allclose` 做正确性断言；
5. 清零后连续执行两次 backward，验证累加；
6. 将梯度设为 `None`，验证清理动作并写 JSON。

脚本中关键断言的含义是：

```python
assert torch.allclose(autograd_weight_grad, residual * x)
assert torch.allclose(autograd_bias_grad, residual)
assert torch.allclose(accumulated_weight_grad, first_grad + second_grad)
```

这里的 `allclose` 是逻辑数值相等的浮点近似判断，不是 bitwise equality。若换成 CUDA 或其他 dtype，应明确容差，而不是直接比较 Python 浮点数。

## 动手实验：先预测再观察

运行前在纸上写下三个预测：

| 观察项 | 预测 |
| --- | --- |
| 第一次 `weight.grad` | `-3.5` |
| `prediction.grad` | 调用 `retain_grad` 后为 `-1.75` |
| 两次 backward 后的 `.grad` | 第一次和第二次梯度之和 |

运行后打开 JSON，重点看 `manual_grad`、`autograd_grad`、`leaf_and_non_leaf` 和 `accumulation` 四个字段。若它们与预测不符，不要先修改阈值；先检查是否误改了输入、清零位置或目标值。

## 故障练习：每次只改一个变量

### 练习 A：把 `zero_()` 删除

预期：第二次 backward 的结果包含上一段示例的梯度，累积断言失败。这个故障模拟了训练代码漏写 `optimizer.zero_grad()`。

### 练习 B：把 `target + 1.0` 改回 `target`

预期：第二次梯度方向与第一次相同，累积值接近两倍。这个结果不是 bug，而是说明两个相同 loss 被反向了两次。

### 练习 C：把参数改成 `requires_grad=False`

预期：无法为参数生成梯度，或 loss 没有可反向的路径。这个故障模拟了加载冻结模型后忘记解冻待训练层。

## 输出如何解读

JSON 中的 `device` 必须与实际运行路径一致；`manual_grad` 和 `autograd_grad` 应在设定容差内相等；`prediction_is_leaf` 应为 `false`；`cleared_with_none` 应为 `true`。这些字段分别覆盖设备、数值、图结构和状态清理四类证据。

不要从这个标量实验推断大模型的绝对速度或显存收益。它只证明语义；真实模型还要在相同 batch、dtype、设备和更新频率下检查 loss、参数变化和吞吐。

## 与训练效能的连接

梯度错误会污染所有性能结论：如果少除了一次 micro-batch，可能看起来收敛更快；如果没有 `no_grad`，验证阶段会保存无用图；如果错误保留中间梯度，显存会增长。先把正确性断言放进最小实验，再谈 AMP、梯度累积和编译优化，才能把“快”与“仍然在训练同一个问题”同时证明。

## 本课验收

提交 JSON 和故障练习记录，必须包含：

1. 手算梯度与 autograd 梯度的数值；
2. 一次非叶子梯度观察；
3. 一次累积前后对照；
4. 一次删除清零后的失败输出及原因。

完成标准：同事只看命令、JSON 和你的解释，就能复现一次正确运行和一次预期失败。
