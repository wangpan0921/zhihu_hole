# 同一篇 PyPI 版本号文章，用 Remotion 和非 Remotion 各做一条视频，效果差在哪？

前面我写过一篇《一文讲透 PyPI 包的版本号：从 PEP 440 到实战选型》，核心内容是解释 Python 打包生态里的版本号规则：`1.10` 为什么大于 `1.9`，`1.0rc1` 为什么默认不会被普通 `pip install` 装上，`1.2.0.post1` 和 `1.2.1` 又应该怎么区分。

这次我拿同一份素材做了一个小实验：让 Codex 基于这篇文章分别生成两条讲解视频。

- 第一条：**Codex + Remotion**，用 React/Remotion 组织画面、时间轴、字幕和渲染。
- 第二条：**Codex + 非 Remotion**，用 Python、Pillow、imageio 和 ffmpeg 这类更底层的方式逐帧生成视频。

两条视频讲的是同一个主题，但成片气质明显不同。下面直接看效果。

## 版本一：Codex + Remotion

<video src="../../artifacts/pypi-version-remotion/out/pypi-version-explainer.mp4" controls width="100%"></video>

视频文件：[`artifacts/pypi-version-remotion/out/pypi-version-explainer.mp4`](../../artifacts/pypi-version-remotion/out/pypi-version-explainer.mp4)

Remotion 版本更像一个“可编程的视频前端页面”。它把视频拆成多个场景：开场提出问题、拆解 public/local version、解释 PEP 440 的五个部件、展示排序链、对比 dev/pre/final/post，最后给出发布建议。

它的优势主要体现在三点。

第一，**结构感更强**。画面是由 React 组件拼出来的：标题、代码块、卡片、时间线、字幕区域都能复用，整体更像一套统一的视频 UI。只要场景数据稳定，改文案、改颜色、改节奏都比较容易。

第二，**动画更自然**。Remotion 里可以直接用 `spring`、`interpolate`、`Sequence` 这些时间轴工具。比如某个版本号卡片什么时候出现、什么时候高亮、什么时候切到下一屏，逻辑都写在组件里，而不是散落在逐帧绘图代码里。

第三，**适合持续迭代**。如果后面要把这个主题扩展成一组视频，比如 PyPI、pip、wheel、依赖解析各做一期，Remotion 版本更容易沉淀成模板。标题区、字幕区、代码卡片、时间线都可以继续复用。

它也有代价：Remotion 这条路线的产物本质上还是一个 Node/React/Remotion 项目目录，只是这些脚手架、组件和渲染命令可以由 Codex 通过 Remotion 插件帮你生成和维护。对使用者来说，不是要手工从零搭工程；真正的取舍在于，你后续维护的是一套组件化视频项目，而不是一个单文件脚本。

## 版本二：Codex + 非 Remotion

<video src="../../artifacts/pypi_version_fresh_video/pypi_version_fresh_explainer.mp4" controls width="100%"></video>

视频文件：[`artifacts/pypi_version_fresh_video/pypi_version_fresh_explainer.mp4`](../../artifacts/pypi_version_fresh_video/pypi_version_fresh_explainer.mp4)

非 Remotion 版本走的是另一条路线：用 Python 脚本定义画布尺寸、字体、颜色、场景时间点，然后用 Pillow 画每一帧，再用 imageio/ffmpeg 合成视频。

这个版本的特点是更“工程脚本化”。

它不依赖浏览器渲染，也不需要 React 组件体系。一个 Python 文件里就能看到完整流程：准备旁白、生成字幕、定义 storyboard、绘制每个场景、导出视频。对于熟悉 Python 的人，这种方式很直接。

它的优点是：

- **依赖少，链路短**：产物形态更接近一个独立 Python 生成脚本。
- **可控性强**：每一帧怎么画、每个元素在哪里，全部由脚本决定。
- **适合批量化任务**：如果目标是把一批 Markdown 快速变成结构类似的视频，Python 脚本很容易接入现有自动化流程。

但缺点也很明显：随着视频复杂度上升，逐帧绘图代码会越来越长。动画缓动、组件复用、布局测量、字幕同步这些事情都要自己处理。能做，但会逐渐变成一个自制的小型视频框架。

## 同一份内容，两种表达

这两条视频都来自同一篇 PyPI 版本号文章，所以知识主线是一致的：

```text
完整版本号 = public version + local version
public version = epoch + release + pre + post + dev
排序规则：不是字符串比较，而是按 PEP 440 语义比较
pip 默认：final/post 可见，pre/dev 默认跳过
发布实践：dev → a/b/rc → final → post 或下一个 patch
```

但是它们对“讲清楚”的处理方式不同。

Remotion 版本更强调**视频作为产品界面**：画面层次、运动节奏、组件一致性更突出。它适合做系列化、品牌化、可复用的视频模板。

非 Remotion 版本更强调**视频作为自动化产物**：一个脚本从内容到成片跑通，路径短，便于快速批量生成。它适合做内部知识库、课程草稿、自动化摘要视频。

简单说：

| 维度 | Codex + Remotion | Codex + 非 Remotion |
| --- | --- | --- |
| 画面组织 | React 组件和时间轴 | Python 逐帧绘制 |
| 动画表达 | 更自然，工具链成熟 | 能实现，但需要手写更多逻辑 |
| 复用能力 | 适合沉淀模板和系列视频 | 适合脚本化批量生成 |
| 维护对象 | Remotion 插件生成的组件化视频项目 | 一个 Python 脚本即可跑通 |
| 适合场景 | 对外发布、系列课程、视觉一致性要求高 | 草稿、内部材料、批量转换、低依赖环境 |

## 回到 PyPI 版本号本身

视频只是载体，真正值得掌握的还是 PEP 440 的版本语义。

如果你维护 Python 包，可以记住这几条：

1. 正式发布用 `1.2.3` 这种 final 版本。
2. 发布前测试用 `1.2.0a1`、`1.2.0b1`、`1.2.0rc1`。
3. `.postN` 只用来修文档、元数据、漏文件这类发布层面问题，不要拿它修代码 bug。
4. `.devN` 适合 CI、nightly、内部快照。
5. `+local` 留给私有源、重打包、硬件编译变体，公共 PyPI 不接受。
6. 不要自创 `1.0-test` 这类版本格式，拿不准就用 `packaging.version.Version` 验证。

版本号不是随便贴的标签，而是在告诉使用者：这个包现在处在什么成熟度、pip 默认该不该把它交给普通用户。

## 小结

这次实验给我的直观感受是：

- 想做**可维护、可迭代、视觉统一**的视频，Remotion 更合适。
- 想做**简单直接、低依赖、脚本批量化**的视频，非 Remotion 方案也完全能跑通。

两条路没有绝对优劣，关键看目标。如果视频是最终产品的一部分，值得用 Remotion 把结构和表现都做扎实；如果视频只是把文章快速转换成另一种知识载体，Python 脚本方案反而更轻。

同一份 PyPI 版本号素材，正好把这两种路线的差异展示出来了：一个像“视频化的前端应用”，一个像“自动化生成的知识切片”。Codex 都能写，差别在于你希望后续维护的是一个视频工程，还是一条内容流水线。
