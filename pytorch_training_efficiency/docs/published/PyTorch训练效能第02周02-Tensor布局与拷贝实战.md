# PyTorch 训练效能第 2 周第 2 课：Tensor 布局与拷贝实战

课程使用的源码保存在github 这个项目：https://github.com/wangpan0921/pytorch_training_efficiency。


上一课学习了 shape、stride 和 contiguous。本课把概念变成可观察的证据：同一批数据经过转置、切片、view、contiguous 和 clone 后，哪些对象仍共享 storage，哪些对象已经复制。

## 一、本课目标

- 能用 data_ptr 和 stride 验证 storage 是否共享；
- 理解转置、切片产生的非连续布局；
- 解释 contiguous 和 clone 的差异；
- 认识隐式 copy 对显存和带宽的影响；
- 产出 tensor_layout.json。

## 二、先预测，再运行

对下面的对象先写下预测：

    base = torch.arange(24).reshape(2, 3, 4)
    transposed = base.transpose(1, 2)
    sliced = base[:, :, ::2]
    viewed = base.view(6, 4)
    dense = transposed.contiguous()
    copied = base.clone()

问题：

1. 哪些对象与 base 共享 data_ptr？
2. 哪些对象 is_contiguous 为 False？
3. 哪个操作一定创建独立 storage？

不要先查答案。先根据 stride 公式推导，再运行脚本验证。

![2-1](./2-1.png)
![2-2](./2-2.png)

## 三、运行实验

    cd pytorch_training_efficiency
    source .venv/bin/activate
    python labs/10_tensor_layout.py

脚本会检查：

- transpose 是否只改变 shape 和 stride；
- view 是否保持 storage；
- contiguous 是否得到密集布局；
- clone 是否独立；
- flatten 是否保持元素总数。

![3-1](./3-1.png)

结果保存为：

    artifacts/week02/tensor_layout.json

## 四、为什么这和训练速度有关

一个 batch 经过 permute 或 transpose 后，后续算子可能无法按连续地址读取。如果算子内部先调用 contiguous，真实成本包括：

1. 读取原 storage；
2. 写入新 storage；
3. 等待 copy 完成；
4. 再执行计算。

小 Tensor 上这段成本不明显，大图像、大序列和大 batch 上可能成为主要内存带宽开销。不要因为某一行代码没有写 clone，就认为没有复制；要看 profile 或指针证据。

## 五、三个观察练习

先按第二节的方式对每个练习写下预测，再运行脚本验证。脚本已整理好，位于 `labs/12_tensor_layout_observe.py`：

    cd pytorch_training_efficiency
    source .venv/bin/activate
    python labs/12_tensor_layout_observe.py

结果保存为：

    artifacts/week02/tensor_layout_observe.json

### 练习 1：非连续输入遇到连续性要求

把步长切片和转置结果传给需要连续布局的算子，比较调用前后的 `is_contiguous` 与 `data_ptr`。脚本对应 `observe_slice_contiguous`，核心逻辑：

    base = torch.arange(24, dtype=torch.float32).reshape(2, 3, 4)
    sliced = base[:, :, ::2]          # 非连续，但仍共享 storage
    transposed = base.transpose(1, 2) # 非连续

    # view 并非总在非连续时失败：只要目标形状能用现有 stride 表达就成功。
    # transpose 后的展平无法用 view 表达，会抛 RuntimeError，需改用 reshape。
    try:
        transposed.view(-1)
    except RuntimeError:
        pass                          # view_on_transposed_failed = True

    reshaped = transposed.reshape(-1) # 成功，但对非连续输入复制到新 storage
    dense = sliced.contiguous()       # 复制到新的密集 storage

![5-1](./5-1.png)

观察结论：`is_contiguous` 由 `False` 变 `True`，同时 `data_ptr` 改变，就是复制的指针证据。注意 `view` 不总在非连续时失败，`reshape` 总能成功但可能悄悄复制。

### 练习 2：逻辑字节数与搬运字节数

比较 `element_size() * numel()`（逻辑占用）与 `contiguous` 需要读写的字节数。脚本对应 `observe_byte_budget`：

    base = torch.arange(24, dtype=torch.float32).reshape(2, 3, 4)
    transposed = base.transpose(1, 2)          # 非连续，numel 不变

    logical_bytes = base.element_size() * base.numel()      # 4 * 24 = 96
    moved_bytes = transposed.element_size() * transposed.numel()
    # contiguous 需要读一遍、写一遍：moved_bytes * 2

![5-2](./5-2.png)

观察结论：搬运字节数等于逻辑字节数（每元素读写一遍），`numel` 不变；真正的成本来自非连续 stride 导致的跨步访存，而非字节总量增加。

### 练习 3：复制耗时随 shape 放大的变化

放大最后两维，用 `time.perf_counter` 计时并取中位数（GPU 上需先 `synchronize`）。脚本对应 `observe_copy_scaling`，默认 `--scales 1 10 100 --repeats 20`：

    for scale in (1, 10, 100):
        base = torch.randn(2, 3 * scale, 4 * scale)
        transposed = base.transpose(1, 2)      # 非连续
        transposed.contiguous()                # 预热
        # 多次计时 transposed.contiguous()，记录中位数

![5-3-cpu](./5-3-cpu.png)

在本机 CPU 上一次典型结果：`scale=1` 约 0.0017 ms，`scale=10` 约 0.0031 ms，`scale=100` 约 0.0255 ms。观察结论：`numel` 随两个维度放大按平方增长，复制耗时随之显著上升，说明大张量上的隐式复制才是带宽瓶颈。
但是这里留一个我自己的疑问，在 GPU 上跑了几次，`scale=1` 和 `scale=10` 都差不多。如图：
![5-3](./5-3.png)

每次只改一个变量（如 `--scales` 或 `--repeats`），并记录命令、shape、stride、耗时和结论。

## 六、常见误区

- data_ptr 相同只说明当前对象从同一地址开始，不代表所有高级别别名关系都已解释；要结合 storage_offset 和 stride。
- contiguous 不会改变逻辑数值，但会改变访问布局。
- reshape 可能返回 view，也可能复制；不能把它当作零拷贝承诺。
- 为了“保险”到处 clone，往往是在用显存和带宽换取不必要的简单性。

## 七、本课验收

提交 tensor_layout.json、tensor_layout_observe.json 和一页分析，回答：

1. 为什么 transpose 常常不复制？
2. 为什么后续算子仍可能触发 copy？
3. 在你的训练代码中，哪个维度转换最值得检查？

完成标准：先预测、后运行，至少用 data_ptr、stride、is_contiguous 三类证据解释一次布局变化。
