# PyTorch 训练效能第 2 周第 3 课：Tensor 契约与批数据断言

课程使用的源码保存在github 这个项目：https://github.com/wangpan0921/pytorch_training_efficiency。


训练任务中最昂贵的错误，常常不是立刻崩溃，而是悄悄把数据形状、dtype 或 device 搞错。模型可能继续运行，直到很久以后才发现指标异常。本课为 batch 建立一组简单、明确、可自动执行的 Tensor 契约。

## 一、本课目标

- 为图像 batch 和分类标签定义 shape、dtype、device 契约；
- 用断言尽早发现错误；
- 理解 finite 检查与 NaN/Inf 的关系；
- 编写十个可复用的 Tensor 检查；
- 产出 tensor_assertions.json。

## 二、一个 batch 的最低契约

假设分类模型接收图像：

    images:  [N, C, H, W], float32
    labels:  [N],          int64
    logits:  [N, K],       float32

至少要保证：

- N 在三者之间相等；
- images、labels、logits 在同一个 device；
- labels 是整数类别编号；
- logits 的 K 与类别数一致；
- 输入和输出都没有 NaN/Inf。

契约不是多余的防御式代码。它把“训练结果不对”提前变成“第一个 batch 就失败”，诊断成本会低很多。

## 三、运行十个断言

    cd pytorch_training_efficiency
    source .venv/bin/activate
    python labs/11_tensor_assertions.py

代码片段：
```python
    device = best_device()
    batch, channels, height, width = 4, 3, 8, 8
    images = torch.randn(batch, channels, height, width, device=device, dtype=torch.float32)
    labels = torch.randint(0, 10, (batch,), device=device, dtype=torch.long)
    logits = torch.randn(batch, 10, device=device)
    checks = {
        "images_shape": tuple(images.shape) == (batch, channels, height, width),
        "images_float": images.dtype.is_floating_point,
        "labels_shape": tuple(labels.shape) == (batch,),
        "labels_integer": labels.dtype == torch.long,
        "same_device_images_labels": images.device == labels.device,
        "same_device_images_logits": images.device == logits.device,
        "batch_dimension_matches": images.shape[0] == labels.shape[0] == logits.shape[0],
        "class_dimension_matches": logits.shape[1] == 10,
        "finite_images": bool(torch.isfinite(images).all()),
        "finite_logits": bool(torch.isfinite(logits).all()),
    }
    assert all(checks.values()), checks
    report = {"device": str(device), "checks": checks, "image_bytes": images.numel() * images.element_size()}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {output}")
```

脚本会创建一个合成 batch，并验证十项条件：

1. 图像 shape；
2. 浮点 dtype；
3. 标签 shape；
4. 标签为 long；
5. 图像和标签同 device；
6. 图像和 logits 同 device；
7. batch 维相等；
8. 类别维正确；
9. 图像有限；
10. logits 有限。

结果保存为：

    artifacts/week02/tensor_assertions.json

![3-1](./3-1.png)

## 四、故意让断言失败

每次只改一行：

    labels = labels.float()

预期：labels_integer 失败。

![4-1](./4-1.png)
![4-1-result](./4-1-result.png)

再尝试：

    labels = labels[:-1]

预期：batch_dimension_matches 失败。

![4-2](./4-2.png)
![4-2-result](./4-2-result.png)

最后注入：

    logits[0, 0] = float("nan")

预期：finite_logits 失败。

![4-3](./4-3.png)
![4-3-result](./4-3-result.png)


## 五、把契约放在哪里

推荐在边界处检查，而不是每个算子后都检查：

- Dataset 输出进入 DataLoader 后；
- batch 从 CPU 搬到 GPU 后；
- 模型前向入口；
- 外部 checkpoint 或缓存加载后。

性能敏感的正式训练可以降低检查频率，例如每个 epoch 的第一个 batch，或只在 debug 配置开启。但出现异常时，应保留触发错误的 sample id、文件名或数据版本。

## 六、finite 检查不能代替语义检查

全是有限数值，不代表数据正确：

- 标签可能整体偏移一位；
- 图像通道顺序可能错；
- 单位可能从米变成厘米；
- logits 类别数可能与标签字典不一致。

因此 Tensor 契约要和数据语义、类别表、版本信息一起记录。断言负责第一层结构正确性，样本可视化和统计负责第二层语义正确性。

## 七、本课验收

提交 tensor_assertions.json 和故障记录，回答：

1. 为什么 labels 用 float 可能直到 loss 计算才报错？
2. 为什么 device 检查应发生在模型前向之前？
3. 为什么 finite 检查通过仍不能证明数据语义正确？

完成标准：能为自己负责的数据入口写出至少十个断言，并能解释每个断言失败后会阻止哪类错误继续传播。
