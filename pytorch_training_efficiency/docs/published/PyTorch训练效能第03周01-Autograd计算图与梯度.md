# PyTorch训练效能第03周01-Autograd计算图与梯度
课程使用的源码保存在github 这个项目：https://github.com/wangpan0921/pytorch_training_efficiency。

本课回答一个训练循环中的核心问题：`loss.backward()` 到底计算了什么，以及为什么参数的 `.grad` 有时是 `None`、有时会越来越大。理解这些边界，才能判断训练结果是模型真的学到了，还是梯度 bookkeeping 写错了。

## 本课目标

- 用计算图、叶子张量和链式法则解释 `backward()`；
- 区分 `requires_grad`、`is_leaf`、`.grad` 和 `grad_fn`；
- 解释梯度为什么默认累积，以及 `zero_grad` 的位置；
- 认识 `detach()`、`torch.no_grad()` 的使用边界；
- 能从实验 JSON 中找到梯度正确性和清零证据。

## 现象或问题

下面的代码看起来像普通的标量计算：
> **小白科普**
>
> 标量、向量、矩阵的区别： 
>
> ```python
> torch.tensor(3.0)          # 标量，形状 [] 
> torch.tensor([1.0, 2.0])   # 向量，形状 [2] 
> torch.tensor([[1.0, 2.0]]) # 矩阵，形状 [1, 2] 
> ```

```python
w = torch.tensor(1.5, requires_grad=True)
b = torch.tensor(0.25, requires_grad=True)
x = torch.tensor(2.0)
prediction = w * x + b
loss = 0.5 * (prediction - 5.0) ** 2
loss.backward()
```

训练真正需要的是 `d(loss)/d(w)`（w 对 loss 的影响程度） 和 `d(loss)/d(b)`（b 对 loss 的影响程度）。如果没有自动微分，我们要为每个算子保存中间结果并手动实现链式法则。PyTorch 会在前向执行时记录一张动态计算图，在反向时沿图从输出向输入传播梯度。

> **小白科普**
>
> 这段代码描述的是：模型先算出结果，再反过来追查每个参数对错误的影响有多大。
>
> 可以把计算过程想成一条流水线：
> 
> ```text
> w、b、x
>   ↓
> prediction = w * x + b
>   ↓
> loss = 0.5 * (prediction - 真实值)^2
> ```
>
> 代入本例的数值后：`prediction = 1.5 × 2 + 0.25 = 3.25`，然后 `loss = 0.5 × (3.25 - 5)^2 = 1.53125`。
>
> `d(loss)/d(w)` 可以理解为“`w` 改变一点点时，`loss` 会改变多少”，它描述的是 `w` 对 loss 的影响程度，不是普通的除法。本例中 `d(loss)/d(w) = -3.5`，表示增大 `w` 时，loss 倾向于减小；`d(loss)/d(b) = -1.75` 的含义类似。
>
> 从输入一步步计算到最终结果，叫**前向计算**。PyTorch 会在这个过程中记住每一步运算，把 `w、b、x → prediction → loss` 连成一张**动态计算图**。
>
> 得到 loss 后，PyTorch 从最后的 loss 开始，沿着计算过程反方向计算，追查应该怎样调整 `w` 和 `b` 才能让 loss 变小，这叫**反向传播**。执行 `loss.backward()` 后，计算出的结果会保存在参数的 `.grad` 中：
>
> ```python
> print(w.grad)  # tensor(-3.5)
> print(b.grad)  # tensor(-1.75)
> ```
>
> 因为 `w` 先影响 `prediction`，再影响 `loss`，所以影响要一段一段相乘：`d(loss)/d(w) = d(loss)/d(prediction) × d(prediction)/d(w) = -1.75 × 2 = -3.5`，这就是**链式法则**。
>
> 一句话总结：前向计算负责算出 loss，反向传播负责追查 loss 受到哪些参数影响，并把这种影响记录到参数的 `.grad` 中。


## 核心概念与最小模型

令：

```text
z = w * x + b
L = 1/2 * (z - y)^2
```

设 `r = z - y`，则：

```text
dL/dz = r
dL/dw = r * x
dL/db = r
```

> **小白科普**
> 
> 因为：
> 
> dr/dz = 1
> 
> 所以根据链式法则：
> ```text
> dL/dz = dL/dr * dr/dz
>       = r * 1
>       = r
> ```
> 再由：
> ```text
> z = w * x + b
> ```
> 可得：
> ```text
> dz/dw = x
> dz/db = 1
> ```
> 继续使用链式法则：
> ```text
> dL/dw = dL/dz * dz/dw = r * x
> dL/db = dL/dz * dz/db = r * 1 = r
> ```

本例 `x=2`、`w=1.5`、`b=0.25`、`y=5`，所以 `z=3.25`、`r=-1.75`，预期 `dL/dw=-3.5`、`dL/db=-1.75`。

### 叶子张量和非叶子张量

直接由用户创建、并且需要梯度的 `w`、`b` 是叶子张量（leaf）。`prediction` 是运算结果，是非叶子张量（non-leaf），通常有 `grad_fn`，但 PyTorch 默认只把梯度保存在叶子张量的 `.grad` 中：

```python
prediction.retain_grad()
loss.backward()
print(w.is_leaf, w.grad)                    # True, -3.5
print(prediction.is_leaf, prediction.grad)  # False, -1.75
```

这段代码展示了：PyTorch 默认保存叶子张量的梯度，而中间结果需要调用 retain_grad() 才会保存梯度。`retain_grad()` 是观察中间节点的工具，不应在每个中间 Tensor 上无条件调用，否则会增加保存的内存。

> **小白科普**
> 
> 调用：
> 
> loss.backward()
> 
> 之后，PyTorch 反向计算：
> ```text
> loss
>   ↓ dloss/dr
> r
>   ↓ dr/dprediction
> prediction
>   ↓ dprediction/dw、dprediction/db
> w、b
> ```
> 计算顺序可以写成：
> ```text
> dloss/dloss = 1
> dloss/dr = r
> dloss/dprediction = r
> dloss/dw = r * x
> dloss/db = r
> ```
> 本例中 r = -1.75、x = 2，所以：
> ```text
> prediction.grad = dloss/dprediction = -1.75
> w.grad          = dloss/dw         = -1.75 * 2 = -3.5
> b.grad          = dloss/db         = -1.75
> ```

### 梯度累积

1. 什么是梯度累积

假设某个参数的梯度分别是

```text
loss_a 对参数的梯度 = 2
loss_b 对参数的梯度 = 3
```

`backward()` 会把新梯度加到已有的 `.grad`，不会自动覆盖：

执行：

```python
loss_a.backward()
loss_b.backward()
# parameter.grad == d(loss_a)/d(parameter) + d(loss_b)/d(parameter)
```
之后，参数的 .grad 不是 3，而是：

```text
parameter.grad = 2 + 3 = 5
```
也就是说，backward() 默认执行“加法”，不会覆盖原来的梯度。

2. 为什么训练前要清零

典型训练过程是：

```python
optimizer.zero_grad()  # 清除上一次的梯度

prediction = model(x)  # 前向计算，得到预测值和 loss
loss = loss_fn(prediction, y)

loss.backward()        # 计算当前 batch 的梯度
optimizer.step()       # 根据梯度更新参数
```

忘记清零会让梯度随 batch 累积，等价于改变了优化问题。`optimizer.zero_grad(set_to_none=True)` 还可以让没有梯度的参数保持 `None`，但代码不能把 `None` 当作数值零来直接读取。

### detach 和 no_grad

`detach()` 返回一个不再连接当前计算图的 Tensor，常用于记录数值或把预测传给不需要反向的分支。`torch.no_grad()` 是一段上下文，在评估或推理时关闭图记录：

```python
with torch.no_grad():
    validation_logits = model(validation_batch)
```

两者都会阻止这段操作继续建立反向路径，但不会把已有参数永久改成不需要梯度。不要用 `detach()` 代替“修复错误梯度”的分析；它可能把本该训练的路径切断。

> **小白科普**
> 
> `torch.no_grad()` 的作用是：
> 
> > 在一段代码中，暂时不记录计算图，也不计算梯度。
> 
> 典型用在验证或推理阶段：
> 
> ```python
> with torch.no_grad():
>     validation_logits = model(validation_batch)
> ```
> 
> 正常情况下，如果模型参数需要梯度，前向计算会建立计算图：
> 
> ```text
> 输入 → 模型计算 → 输出
>               ↘ 计算图
> ```
> 
> 这样之后才能调用：
> 
> ```python
> loss.backward()
> ```
> 
> 而在验证或预测时，我们通常只想得到结果，不需要更新参数。这时使用：
> 
> ```python
> with torch.no_grad():
>     prediction = model(x)
> ```
> 
> 可以避免建立计算图，从而：
> 
> - 减少内存占用；
> - 减少计算开销；
> - 防止误用 `backward()` 更新模型。
> 
> 例如：
> 
> ```python
> model.eval()
> 
> with torch.no_grad():
>     prediction = model(x)
>     loss = loss_fn(prediction, y)
> ```
> 
> 这里的 `model.eval()` 和 `torch.no_grad()` 是两件不同的事：
> 
> ```text
> model.eval()
> ```
> 
> 让 Dropout、BatchNorm 等层切换到评估行为。
> 
> ```python
> with torch.no_grad():
> ```
> 
> 关闭这段代码中的梯度记录。
> 
> 验证阶段通常两个都写：
> 
> ```python
> model.eval()
> 
> with torch.no_grad():
>     prediction = model(x)
> ```
> 
> 需要注意，`no_grad()` 只是临时生效：
> 
> ```python
> with torch.no_grad():
>     output = model(x)
> 
> # 离开代码块后，梯度记录功能恢复
> ```
> 
> 它不会永久修改模型参数的 `requires_grad` 属性，也不会永久冻结参数。训练阶段仍然应当正常使用：
> 
> ```python
> model.train()
> 
> optimizer.zero_grad()
> prediction = model(x)
> loss = loss_fn(prediction, y)
> loss.backward()
> optimizer.step()
> ```
> 
> `detach()` 用来把某个 Tensor 从当前计算图中“摘出来”。
> 
> 也就是说，得到一个与原 Tensor 数值相同、但不再参与当前反向传播的新 Tensor：
> 
> ```python
> prediction = model(x)
> prediction_without_grad = prediction.detach()
> ```
> 
> 之后：
> 
> ```python
> prediction_without_grad
> ```
> 
> 参与的计算不会把梯度传回 `prediction`、模型参数或更早的计算。
> 
> ### 什么时候使用
> 
> **1. 只想记录、打印或转成 NumPy**
> 
> ```python
> prediction = model(x)
> 
> values = prediction.detach().cpu().numpy()
> ```
> 
> 如果 `prediction` 还连接着计算图，直接调用 `.numpy()` 通常会报错。`detach()` 表示：“我这里只需要数值，不需要梯度。”
> 
> **2. 有意切断某条梯度路径**
> 
> 例如：
> 
> ```python
> prediction = model(x)
> target = prediction.detach()
> 
> loss = loss_fn(prediction, target)
> loss.backward()
> ```
> 
> 这里 `target` 只作为目标值使用，损失的梯度不会通过 `target` 分支传回模型。
> 
> 这是一种有意的设计，常见于教师模型、目标网络、对抗训练等场景。
> 
> **3. 保存中间结果**
> 
> ```python
> saved_predictions.append(prediction.detach())
> ```
> 
> 否则保存的 Tensor 可能仍然引用计算图，导致计算图无法及时释放，增加内存占用。
> 
> ### 和 `torch.no_grad()` 的区别
> 
> `detach()` 针对的是**某一个 Tensor**：
> 
> ```python
> output_for_logging = output.detach()
> ```
> 
> `torch.no_grad()` 针对的是**一整段计算过程**：
> 
> ```python
> with torch.no_grad():
>     output = model(x)
> ```
> 
> 可以这样理解：
> 
> ```text
> detach()  ：这条结果从这里开始不再传梯度
> no_grad() ：这段代码里的操作都不建立计算图
> ```
> 
> 如果整个阶段都是验证或推理，通常使用 `no_grad()`；如果只是想切断某个分支，使用 `detach()`。
> 
> ### 一个注意点
> 
> `detach()` 得到的 Tensor 通常与原 Tensor 共享底层数据。如果需要一个完全独立的副本，可以写：
> 
> ```python
> independent = tensor.detach().clone()
> ```
> 
> 总结：
> 
> > 想让某个 Tensor 继续保留数值，但不让梯度通过它反向传播时，使用 `detach()`。

## 逐步代码/命令

```bash
cd pytorch_training_efficiency
python labs/13_autograd_basics.py --output artifacts/week03/autograd_basics.json
```

运行前先预测：

1. `weight.grad` 和 `bias.grad` 应分别是多少？
2. 不调用 `retain_grad()` 时，`prediction.grad` 是否会被保存？
3. 连续两次 `backward()`、中间不清零，最终梯度是覆盖还是相加？

![13](./13.png)

脚本会先用手算公式核对 `autograd`，再对两个不同目标各反向一次，最后把 `.grad` 设为 `None`，并将叶子/非叶子状态和梯度写入 JSON。先查看原始字段，再解释它们，不要只看最后的 `wrote` 行。

## 常见误区与故障练习

### 故障 1：漏掉清零

把脚本中第一次反向前的 `weight.grad.zero_()` 和 `bias.grad.zero_()` 删除。预期第二组结果会混入最初示例的梯度，说明 `.grad` 是有状态的累加器。真实训练中，这个错误通常表现为 loss 震荡或学习率像被放大。

### 故障 2：读取非叶子梯度

删除 `prediction.retain_grad()` 后再打印 `prediction.grad`。不要把非叶子 `.grad is None` 解读成“反向传播没发生”；先看参数叶子的梯度是否仍然正确。

### 故障 3：错误使用 no_grad

把训练前向包进 `with torch.no_grad()`，然后调用 `loss.backward()`。预期会得到“没有 requires grad 的 Tensor”类错误，因为图从一开始就没有建立。

## 与训练效能的连接

自动微分不只是数学便利，还决定内存和调度成本：前向为了反向可能保存激活；不必要地保留图会增加显存；验证阶段用 `no_grad()` 能减少图构建和内存占用；梯度累积则改变更新频率和每步 bookkeeping。优化前必须先证明参数更新和梯度语义没有被破坏。

## 本课验收

提交 `artifacts/week03/autograd_basics.json` 和一页故障记录，回答：

1. 为什么 `prediction` 有 `grad_fn` 却默认没有 `.grad`？
2. 为什么 `zero_grad` 必须位于下一次反向之前？
3. 哪个字段证明中间节点的梯度被显式保留？

完成标准：能手算本例的两个梯度，解释一次累积结果，并指出 `no_grad`、`detach` 与 `retain_grad` 各自改变了哪条边界。
