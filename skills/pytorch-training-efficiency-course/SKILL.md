---
name: pytorch-training-efficiency-course
description: Generate beginner-friendly PyTorch training-efficiency lessons that connect clear theory to runnable experiments and verifiable engineering artifacts. Use when creating or extending a week, lesson, lab, or syllabus in the pytorch_training_efficiency course.
---

# PyTorch Training Efficiency Course

Use this skill to create or extend the repository's PyTorch training-efficiency curriculum. The audience is a PyTorch beginner who needs to understand both the concept and the evidence produced by a real experiment.

## Scope and discovery

Before writing anything:

1. Read `pytorch_training_efficiency/roadmap.md` to identify the requested week, its three intended lessons, and its acceptance criteria.
2. Read `pytorch_training_efficiency/README.md`, `pytorch_training_efficiency/docs/README.md`, and `pytorch_training_efficiency/labs/README.md`.
3. Read at least two existing lesson articles, including the most recent completed week, plus any lab scripts they reference.
4. Check `git status --short` and preserve unrelated user changes. Do not alter publication metadata, login state, or files outside the course unless requested.

If the requested topic conflicts with the roadmap, follow the roadmap and explain the correction briefly. Do not silently put Autograd, training loops, or later-stage topics into a Tensor week merely because they are nearby concepts.

## Standard weekly deliverables

For a normal week, create three Markdown articles in:

`pytorch_training_efficiency/docs/draft/`

Use this filename form:

`PyTorch训练效能第XX周YY-中文短标题.md`

Each article's first line must be an H1 title matching its filename. Immediately after the title, add this exact line:

    课程使用的源码保存在github 这个项目：https://github.com/wangpan0921/pytorch_training_efficiency。

Keep the articles ordered as the roadmap.s course A, B, and C.

Add one or more runnable labs in:

`pytorch_training_efficiency/labs/`

Use numbered filenames that continue the existing sequence. Each lab must:

- run from `pytorch_training_efficiency/`;
- default to CPU and require no network or external dataset;
- accept useful CLI options such as `--output`;
- use deterministic seeds when randomness is involved;
- assert the key correctness property instead of only printing a result;
- write a small JSON or similarly inspectable artifact under `artifacts/weekXX/`;
- print the output path;
- keep dependencies limited to the existing environment and standard library unless the user explicitly asks otherwise.

Update `labs/README.md` with the lab's purpose and an exact example command. Do not move articles to `pending/` or `published/`, publish them, or create platform metadata unless the user explicitly requests publishing.

## Teaching standard

Write for someone who can read basic Python but is new to PyTorch. Every lesson should answer, in this order:

1. What problem does this concept solve in a training job?
2. What is the smallest mental model or formula that explains it?
3. What does a tiny code example show?
4. What experiment will make the behavior observable?
5. What evidence counts as success, and what common mistake changes it?

Use concrete tensor shapes, values, devices, and units. Explain unfamiliar API arguments at their point of use. Introduce a term before using its abbreviation. Prefer a short runnable example over a long API catalogue.

Use this article shape unless the topic genuinely needs another one:

- 本课目标
- 现象或问题
- 核心概念与最小模型
- 逐步代码/命令
- 动手实验
- 输出如何解读
- 常见误区与故障练习
- 与训练效能的连接
- 本课验收

The article must contain a real practice loop: predict a result, run a command, inspect raw output, then explain why the observation supports or refutes the prediction. Include at least one deliberate failure or single-variable modification when it teaches a boundary.

## Experiment design

Design experiments as teaching instruments, not benchmark theatre:

- Keep the default workload small enough for a laptop CPU.
- Separate correctness checks from performance measurements.
- Record raw inputs, configuration, device, and key results in JSON.
- Use explicit tolerances for floating-point comparisons.
- For CUDA behavior, provide a CPU path and label GPU-only observations as optional.
- If timing asynchronous GPU work, synchronize correctly; never present an unsynchronized wall-clock number as a conclusion.
- Avoid hidden data downloads, random online services, or machine-specific absolute paths.
- Make failure messages identify the violated contract.

For Tensor and layout topics, prefer observable fields such as `shape`, `stride()`, `dtype`, `device`, `is_contiguous()`, `data_ptr()`, `storage_offset()`, `numel()`, and `element_size()`. Explain the limits of pointer-based evidence.

For numerical or gradient topics, compare independent methods where practical, define absolute/relative tolerances, and use a small example that can be hand-checked.

For training-loop topics, assert both learning behavior and bookkeeping behavior: loss trend, accuracy or another task metric, parameter change, seed, and mode boundaries.

## Verification before handoff

Run:

```bash
python3 -m py_compile pytorch_training_efficiency/labs/<new-labs>.py
cd pytorch_training_efficiency
.venv/bin/python labs/<new-lab>.py --output /tmp/weekXX-<name>.json
```

Run every new lab at least once. If the system Python lacks PyTorch, use the course `.venv`. If dependencies are missing there too, do not install packages or use network access without explicit authorization; report the exact blocker and still perform static checks.

Also verify:

- all three articles start with H1 titles;
- commands use repository-relative paths or `cd pytorch_training_efficiency`;
- filenames use the correct week and lesson numbers;
- the lab README entries match actual scripts;
- generated artifacts are not accidentally added to the source tree;
- the final diff contains only requested course files plus necessary index updates.

## Content boundaries

Do not promise production performance from a toy experiment. Distinguish:

- logical equality from bitwise equality;
- a view from a copy;
- CPU behavior from CUDA behavior;
- a correctness assertion from a speed result;
- a single-machine observation from a general rule.

When a lesson builds on an earlier lab, reference and reuse it instead of duplicating a second implementation. Keep comments short and explain only non-obvious behavior.
