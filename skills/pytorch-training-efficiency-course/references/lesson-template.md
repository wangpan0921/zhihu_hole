# Lesson template

Use this as a drafting aid. Adapt section names when the topic needs it, but preserve the learning progression.

# PyTorch 训练效能第 XX 周第 Y 课：<标题>

## 一、本课目标

List 3-6 observable outcomes. At least one outcome must mention the experiment artifact or acceptance check.

## 二、先看一个问题

Show a realistic beginner symptom, such as a shape mismatch, unexpected copy, low throughput, or a metric that does not change. State what the learner should predict before running code.

## 三、最小理论模型

Explain the concept with one diagram, equation, table, or concrete tensor. Define terms before abbreviations. Connect each field or formula to an observable PyTorch property.

## 四、逐步实现

Use short code blocks that can be copied into the existing lab or run directly. Explain inputs, outputs, and the reason for each important line.

## 五、动手实验

Give an exact command from the course root. Name the output artifact. Include at least one single-variable modification or deliberate error, and state the expected symptom before asking the learner to run it.

## 六、如何解读结果

Show the important output fields, units, tolerances, and what conclusion they support. Discuss noise and limits instead of claiming more than the experiment proves.

## 七、常见误区

Cover API misuse, shape/dtype/device mistakes, hidden copies or synchronization, and any distinction between training correctness and performance.

## 八、与训练效能的连接

Explain which resource or metric is affected: memory capacity, memory bandwidth, CPU time, GPU time, data wait, numerical stability, or reproducibility.

## 九、本课验收

Require a concrete artifact plus short written answers. A learner should be able to reproduce the result and explain why it is correct.
