# PyTorch 训练效能第 2 周第 1 课：Tensor 的形状、步长与内存布局

课程使用的源码保存在github 这个项目：https://github.com/wangpan0921/pytorch_training_efficiency。


很多初学者把 Tensor 当成“支持数学运算的 Python 列表”。这个理解能让代码跑起来，却解释不了 view 报错、transpose 后变慢和显存突然增加。本课从 Tensor 的内存映射讲起，并用实验验证哪些操作共享内存、哪些操作会复制。

## 一、本课目标

学完后，你应该能够：

- 读懂 shape、dtype、device 和 stride；
- 解释 contiguous 的含义；
- 判断 view、切片、转置、contiguous 和 clone 是否复制 storage；
- 在训练代码中发现不必要的布局转换；
- 生成 tensor_basics.json 实验产物。

## 二、Tensor 实际保存了什么

可以把 Tensor 抽象成：

    Tensor = storage + dtype + shape + stride + storage_offset + device

storage 是一段元素内存；shape 描述每个维度大小；stride 描述沿某个维度前进一步时，底层 storage 要跳过多少个元素。

    x = torch.arange(12).reshape(3, 4)

典型 shape 是 (3, 4)，stride 是 (4, 1)。地址可以用下面的公式理解：

    offset = storage_offset + i0 * stride[0] + i1 * stride[1]

因此，shape 相同的两个 Tensor，访问速度也可能不同，因为 stride 可能不同。

## 三、transpose 为什么通常不复制

    y = x.t()

y 的 shape 变为 (4, 3)，但仍然使用 x 的 storage，只是把 stride 换了一种解释：

    print(x.data_ptr() == y.data_ptr())  # True
    print(y.is_contiguous())             # False

共享 storage 节省复制时间和显存，但下游算子若要求连续布局，可能在内部产生一次 copy。data_ptr 是本次实验的直观证据，不要把它当作跨进程判断 storage 身份的通用接口。

## 四、view、reshape、contiguous 和 clone

view 只改变 shape，要求当前 stride 支持目标形状：

    x = torch.arange(12).reshape(3, 4)
    z = x.view(2, 6)

对转置结果使用某些 view 可能报错，因为非连续 stride 无法直接映射。

reshape 会先尝试返回 view，做不到时才复制。因此不能凭 reshape 这个名字判断“一定不复制”。性能敏感路径应检查 is_contiguous，并用 profile 证实是否有 copy。

contiguous 返回逻辑数值相同、布局连续的新 Tensor：

    c = x.t().contiguous()

如果输入不连续，它会真正复制。clone 则明确创建独立 storage：

    copy = x.clone()

clone 能解决别名问题，但会增加内存带宽和显存占用，不应随意添加。

## 五、dtype、device 与 shape 也影响效能

相同 shape 的 float32 和 float16，元素大小不同，带宽、显存、数值范围和可用硬件单元也不同。CPU Tensor 与 CUDA Tensor 不能直接相加，to(device) 可能触发 Host-to-Device 拷贝。训练循环中应尽量一次搬运完整 batch，而不是逐个小 Tensor 搬运。

卷积常用 NCHW，也有算子偏好 NHWC。转置本身可能只是改 stride，但后续算子要求 contiguous 时会引入布局复制。布局选择应与主要算子和数据来源一起决定。

## 六、动手实验

从课程目录执行：

    cd pytorch_training_efficiency
    source .venv/bin/activate
    python labs/09_tensor_basics.py

输出会包含 shape、stride、dtype、device、contiguous、data pointer 和共享 storage 检查，并保存：

    artifacts/week02/tensor_basics.json

请再做三个单变量练习：

1. 把 base.t() 改为 base[:, ::2]，观察 stride；
2. 把 view 的形状改成元素总数不匹配的形状，记录报错；
3. 在 contiguous 前后打印 numel() * element_size()，估算复制字节数。

![对比图](./第二周01-1.png)

## 七、常见误区

误区一：shape 一样就代表布局一样。错误，stride 可以完全不同。

误区二：contiguous 是“数值连续”。错误，它描述 storage 的默认排列，随机 Tensor 也可以 contiguous。

误区三：所有 view 都免费。view 本身通常不复制，但后续算子可能复制，必须观察完整算子链。

误区四：看到 clone 就放心。clone 解决别名问题，却可能制造明显的内存流量。

## 八、本课验收

提交一页笔记，回答：

1. reshape 什么时候可能复制？
2. transpose 后为什么常常不是 contiguous？
3. 给出一个会检查 stride 的训练代码位置。
4. 哪一项实验数据说明 view 与原 Tensor 共享内存？

完成标准：能根据 shape、stride 和操作语义预测是否可能复制，并用 JSON 实验验证。
