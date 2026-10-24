# Matplotlib 是什么、能做什么：使用场景与后端选择指南

在 Python 生态里，Matplotlib 经常被当作“画折线图的库”。这个说法并不算错，但低估了它的能力：Matplotlib 是一个通用的科学绘图库，负责把数组、表格或计算结果转换成可交互查看、可保存、可复现的图形。

它既可以在 Notebook 里快速探索数据，也可以在没有显示器的训练服务器上批量生成 PNG，还可以输出论文需要的 PDF/SVG。决定这些行为的关键不是 `plot()` 本身，而是 Matplotlib 的**后端（backend）**。

本文先建立 Matplotlib 的整体认识，再按使用环境解释常见后端的差异，最后给出一套可以直接复制的选择和排错方法。

---

## 一、Matplotlib 的作用

### 1. 把数据映射成图形

Matplotlib 提供了坐标轴、刻度、图例、颜色、标注、误差线、网格等基础绘图能力，常见图形包括：

- 折线图、散点图、柱状图、面积图和阶梯图；
- 直方图、箱线图、小提琴图和误差棒，用于观察分布和不确定性；
- 饼图、堆叠图、热力图、等高线图和二维/三维曲面图；
- 事件标记、文本注释、箭头、图片叠加和自定义图例。

它的优势在于“每个视觉元素都可以控制”。一张图中的线、点、坐标轴和文本，最终都属于可组合的 Artist 对象，可以精确修改样式、位置和导出格式。

### 2. 统一探索、报告与自动化

同一套 Python 代码可以覆盖三个阶段：

1. 在 Notebook 中交互缩放，快速验证数据是否合理；
2. 在脚本或 Web 服务中批量生成报表图片；
3. 以 PDF、SVG、PGF 等矢量格式导出，放进论文、幻灯片或排版系统。

这使它很适合作为数据处理代码和最终图表之间的“稳定边界”。NumPy、pandas、SciPy、scikit-learn、PyTorch 等库都可以把结果交给 Matplotlib 绘制。

### 3. 它不负责什么

Matplotlib 是绘图库，不是数据清洗、统计建模或 BI 平台：

- 数据量特别大、需要浏览器级联动时，应考虑 Datashader、Plotly、Bokeh 等工具；
- 需要专业 GIS 投影和地图瓦片时，通常配合 Cartopy 或 GeoPandas；
- 需要出版物风格的高级统计图，可以在 Matplotlib 之上使用 Seaborn；
- 需要三维场景、动画游戏或 GPU 渲染时，应使用专门的三维引擎。

Matplotlib 仍然可以作为这些工具的底层或补充，但不要把它当成所有可视化问题的唯一答案。

---

## 二、核心对象：Figure、Axes 和 Artist

理解对象层次，能避免很多“画错地方”或“改了一个子图却影响全部图”的问题：

- `Figure`：整张画布，可以包含多个子图；
- `Axes`：一个带坐标系的绘图区。日常所说的“子图”通常就是一个 `Axes`；
- `Axis`：`Axes` 中的 x/y 轴，负责刻度和刻度标签；
- `Artist`：线条、散点、矩形、文本、图例等所有可见元素的基类。

推荐优先使用面向对象接口。`pyplot` 适合交互式试验，但在函数、服务或批处理脚本中，显式持有 `fig` 和 `ax` 更容易控制资源和生命周期。

```python
import numpy as np
import matplotlib.pyplot as plt

x = np.linspace(0, 2 * np.pi, 200)
y = np.sin(x)

fig, ax = plt.subplots(figsize=(7, 4), layout="constrained")
ax.plot(x, y, label="sin(x)", color="#1769aa", linewidth=2)
ax.set(title="正弦曲线", xlabel="x", ylabel="sin(x)")
ax.axhline(0, color="0.75", linewidth=0.8)
ax.grid(alpha=0.25)
ax.legend()
fig.savefig("sine.png", dpi=160)
plt.close(fig)
```

在循环中生成大量图片时，`plt.close(fig)` 很重要。它会释放 Figure 及其 Artist 持有的内存，避免长任务逐渐膨胀。

---

## 三、Matplotlib 的典型使用场景

### 1. 数据探索（EDA）

读取 CSV 或 DataFrame 后，先用散点图、直方图、箱线图观察量纲、异常值、偏态和相关性。探索阶段更看重迭代速度，可以使用 Notebook 的交互后端或 `%matplotlib inline`。

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("metrics.csv")
fig, axes = plt.subplots(1, 2, figsize=(10, 3.5), layout="constrained")
df["latency_ms"].plot.hist(bins=40, ax=axes[0], title="延迟分布")
axes[1].scatter(df["batch_size"], df["latency_ms"], s=12, alpha=0.45)
axes[1].set(xlabel="batch size", ylabel="latency (ms)")
plt.show()
```

### 2. 机器学习与深度学习实验

训练曲线、学习率变化、混淆矩阵、ROC/PR 曲线、特征重要性和预测误差都可以用 Matplotlib 完成。常见做法是训练阶段只记录数值，训练结束后单独绘图，这样不会让每个 step 的绘图开销拖慢训练。

```python
epochs = range(1, len(train_loss) + 1)
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(epochs, train_loss, label="train")
ax.plot(epochs, valid_loss, label="validation")
ax.set(xlabel="epoch", ylabel="loss", title="训练与验证损失")
ax.legend()
fig.savefig("loss-curves.svg")
plt.close(fig)
```

服务器没有桌面环境时，应显式使用 `Agg` 后端，后文会解释原因。

### 3. 科研计算与工程报告

实验对比、参数扫描、消融实验、频谱分析、时序信号、有限元结果和性能基准测试，都需要可重复且能导出高质量图片。此时应统一设置字体、颜色、尺寸和 DPI，并记录绘图脚本及数据版本。

对于论文，优先考虑 PDF/SVG 等矢量输出；对于网页、日志和消息通知，PNG 通常更方便。

### 4. 监控与离线报表

定时任务可以从数据库或日志读取指标，为每个服务生成趋势图，然后通过邮件、对象存储或消息系统分发。整个过程无需打开窗口，使用 `Agg` 后端即可在容器中稳定运行。

### 5. 桌面工具和教学演示

在本地桌面程序中，用户可能需要缩放、平移、点击点位或实时刷新图形。Matplotlib 可以嵌入 Tk、Qt、GTK、wx 等 GUI 框架，适合科研小工具、实验室控制台和教学演示。若应用本身就是复杂的商业图表产品，建议评估原生图表组件或 Web 技术。

---

## 四、后端到底是什么

Matplotlib 将“绘图逻辑”和“如何显示/保存”拆开：

- **绘图逻辑层**创建 Figure、Axes 和 Artist；
- **渲染器（renderer）**把 Artist 转换为像素或矢量指令；
- **显示后端（GUI backend）**决定窗口、Notebook 或 Web 页面如何承载结果。

后端通常分为两类：

1. **交互式后端**：可以显示窗口、缩放、平移和响应鼠标事件，例如 `QtAgg`、`TkAgg`、`MacOSX`、`WebAgg`；
2. **非交互式后端**：只负责渲染和保存文件，不需要显示器，例如 `Agg`、`pdf`、`svg`、`ps`、`pgf`。

`Agg` 中的 “Agg” 是 Anti-Grain Geometry 栅格渲染器；它不是“低级模式”，而是服务器端生成 PNG 的常用方案。

查看当前后端和可用后端：

```python
import matplotlib

print(matplotlib.get_backend())
print(matplotlib.rcsetup.all_backends)
```

不同 Matplotlib 版本对后端名称的大小写和别名可能略有差异，实际环境以 `matplotlib.rcsetup.all_backends` 和官方文档为准。

---

## 五、常见后端与具体使用场景

下面的“适合”是选择建议，不代表后端只能用于这一种场景。

### 1. `Agg`：无显示器服务器的默认选择

**适合：** Docker、CI、远程训练机、定时任务、Web API、批量导出 PNG/JPEG。

**特点：** 不创建窗口，不依赖 X11/Wayland，稳定且可复现。缺点是不能交互缩放。

```python
import matplotlib
matplotlib.use("Agg")  # 必须在导入 pyplot 前设置

import matplotlib.pyplot as plt
```

也可以通过环境变量配置：

```bash
MPLBACKEND=Agg python report.py
```

容器镜像中建议在代码入口或环境变量里明确设置，而不要依赖开发机上的默认配置。

### 2. `TkAgg`：Python 自带 Tk 窗口

**适合：** 简单桌面脚本、教学示例、希望少装依赖的本地工具。

它把 Agg 渲染器嵌入 Tk 窗口。Linux 需要 Tk 和显示服务，服务器上通常不可用；Windows 和 macOS 的 Python 安装一般更容易获得 Tk 支持。

```python
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
plt.plot([1, 2, 3])
plt.show()
```

### 3. `QtAgg`：Qt 应用中的高质量交互

**适合：** PyQt/PySide 科研工具、复杂桌面界面、多窗口和信号槽驱动的实时图。

Qt5/Qt6 绑定和 Matplotlib 版本需要匹配。已有 Qt 应用时，通常把 Figure 嵌入 `FigureCanvasQTAgg`，而不是单独调用 `plt.show()`。

```python
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

class Canvas(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        self.figure = Figure(figsize=(5, 3))
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
```

### 4. `MacOSX`：macOS 原生窗口

**适合：** macOS 本地脚本和原生 Cocoa 窗口。

它使用 macOS 原生绘图事件循环，交互体验通常很好，但不能在 Linux/Windows 上使用。跨平台项目不应把它写死为唯一后端。

### 5. `GTK3Agg` / `GTK4Agg` 与 `WXAgg`

**适合：** 已经采用 GTK 或 wxPython 的 Linux 桌面应用。

这类后端把 Agg 画布嵌入对应 GUI。选择它们的主要理由是“项目已经使用该 GUI 框架”，而不是图形质量有本质差异。部署时要同时安装系统 GUI 库和 Python 绑定。

### 6. `WebAgg`：浏览器访问的交互图

**适合：** 远程机器、内部工具、希望通过浏览器查看 Matplotlib 交互图但不想重写绘图逻辑的场景。

`WebAgg` 通过 WebSocket/HTTP 提供一个浏览器页面，支持缩放、平移和工具栏。它不是完整的 Web 图表平台，生产环境还要自行处理鉴权、反向代理和生命周期。

### 7. `nbAgg`、`inline` 与 `ipympl`：Jupyter 生态

- `inline`：把静态图片嵌入 Notebook 输出，最稳定，适合报告和版本控制；
- `nbAgg`：在经典 Jupyter Notebook 中提供基于 JavaScript 的交互；
- `ipympl`（`%matplotlib widget`）：在 JupyterLab/Notebook 中提供更完整的 widget 交互，适合探索数据和调参数。

```python
%matplotlib inline       # 静态输出
# 或
%matplotlib widget       # 需要安装 ipympl，获得缩放、拖拽等交互
```

Notebook 中遇到“窗口不弹出”并不一定是错误：`inline` 本来就不会创建独立窗口。

### 8. `pdf`、`svg`、`ps`：出版和矢量输出

**适合：** 论文、技术文档、Inkscape/Illustrator 后期编辑、需要无损缩放的图表。

```python
fig.savefig("figure.pdf")  # PDF 矢量
fig.savefig("figure.svg")  # SVG 矢量，可在浏览器打开
fig.savefig("figure.png", dpi=300)  # 栅格图，dpi 影响像素尺寸
```

这些后端不需要 GUI。直接调用 `savefig()` 时，Matplotlib 会根据文件扩展名选择合适的输出格式；也可以在配置中显式指定 `pdf`、`svg` 或 `ps`。

### 9. `pgf`：LaTeX 排版链路

**适合：** 论文要求字体、数学公式和正文完全一致，并且使用 LaTeX 编译的场景。

```python
import matplotlib
matplotlib.use("pgf")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "pgf.texsystem": "lualatex",
    "font.family": "serif",
})
```

`pgf` 需要本机安装 LaTeX。构建环境没有 `lualatex`/`xelatex` 时会失败，因此 CI 和容器要把 TeX 依赖作为镜像的一部分管理。

### 10. `cairo` 系列：特殊矢量和跨平台渲染需求

安装 `pycairo` 或 `cairocffi` 后，可以使用 `cairo` 后端输出 Cairo 支持的格式。它适合已有 Cairo 图形管线的应用，但不是普通项目的首选；若只需要 PDF/SVG，Matplotlib 自带后端通常更简单。

---

## 六、后端如何配置，优先级是什么

Matplotlib 常见的配置方式有三种：

### 1. 代码中设置

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
```

必须在首次导入 `matplotlib.pyplot` 之前调用 `use()`。如果已经创建了 Figure，再切换后端通常会报错或行为不符合预期。

### 2. 环境变量设置

```bash
MPLBACKEND=QtAgg python desktop_tool.py
MPLBACKEND=Agg python batch_report.py
```

它对临时运行、CI 和容器特别方便。

### 3. `matplotlibrc` 配置

```text
backend: Agg
```

可以通过下面的代码找到正在使用的配置文件：

```python
import matplotlib
print(matplotlib.matplotlib_fname())
```

实践中可按“临时环境变量 > 项目入口显式设置 > 用户级 matplotlibrc”的思路管理。不要在库代码内部无条件切换后端，否则会干扰调用方的 GUI 或 Notebook。

---

## 七、选择后端的决策表

| 运行环境/目标 | 推荐后端 | 选择理由 |
| --- | --- | --- |
| 服务器、容器、CI 批量生成 PNG | `Agg` | 无显示器依赖，稳定 |
| Jupyter 只需要静态报告 | `inline` | 输出可复现、易保存 |
| Jupyter 需要拖拽缩放 | `ipympl` / `nbAgg` | 提供 Notebook 内交互 |
| 本地简单桌面脚本 | `TkAgg` | 依赖少、上手快 |
| PyQt/PySide 应用 | `QtAgg` | 可嵌入 Qt 事件循环 |
| GTK/wxPython 应用 | `GTK3Agg`/`GTK4Agg`/`WXAgg` | 与现有 GUI 统一 |
| 浏览器访问的内部交互图 | `WebAgg` | 复用 Matplotlib 工具栏 |
| 论文和可编辑矢量图 | `pdf`/`svg` | 无损缩放、便于排版 |
| LaTeX 字体和公式一致 | `pgf` | 交给 TeX 排版 |

一条实用原则是：**先按“是否需要交互”二分，再按承载环境选择具体后端。**没有显示器就不要尝试 GUI 后端；需要窗口就不要把 `Agg` 当成交互后端。

---

## 八、常见问题与排查方法

### 1. `ImportError: Cannot load backend ...`

通常是 GUI 依赖没装，或当前环境没有显示服务。检查后端和显示变量：

```bash
python - <<'PY'
import matplotlib
print("backend:", matplotlib.get_backend())
print("config:", matplotlib.matplotlib_fname())
PY
echo "$DISPLAY"
```

服务器任务直接改用 `Agg`。Linux 桌面需要确认 X11/Wayland 和对应系统库，Qt 项目还要检查 PyQt/PySide 是否安装。

### 2. `FigureCanvasAgg is non-interactive`

这不是绘图失败，而是代码调用了 `plt.show()`，但当前后端只支持渲染文件。批处理脚本应调用 `fig.savefig()`；需要交互则换成 GUI、Notebook 或 Web 后端。

### 3. 远程 SSH 上 `plt.show()` 没反应

SSH 默认没有图形转发。更可靠的做法是保存图片后下载；确实需要窗口时，再配置 X11 forwarding，或改用 `WebAgg`/Notebook。

### 4. 多线程或 Web 服务中的资源问题

Matplotlib 的全局 `pyplot` 状态和部分 Artist 并不适合多个线程同时修改。服务端建议：

- 入口设置 `Agg`；
- 每个请求创建并关闭自己的 Figure；
- 使用面向对象 API，避免共享全局 Figure；
- 高并发场景考虑进程池或专门的图表服务。

### 5. 中文乱码或负号显示异常

后端只负责渲染，字体是否存在仍由运行环境决定。先确认字体文件，再通过 `font.family`、`font.sans-serif` 和 `axes.unicode_minus` 配置。不要只在本地安装字体后就假设容器也能找到它。

---

## 九、可复用的生产级模板

下面的模板适合在服务器或容器中生成图片，并把后端、资源释放和布局都处理好：

```python
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


def save_report(path: str) -> None:
    x = np.linspace(0, 10, 300)
    fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
    try:
        ax.plot(x, np.exp(-x / 4) * np.cos(x), label="signal")
        ax.set(title="Daily signal", xlabel="time", ylabel="value")
        ax.legend()
        fig.savefig(path, dpi=180, facecolor="white")
    finally:
        plt.close(fig)


if __name__ == "__main__":
    save_report("daily-signal.png")
```

模板中的关键点是：后端在 `pyplot` 前设置，函数内部独立创建 Figure，`finally` 中关闭 Figure，并把输出路径作为参数传入。这样更适合测试、重试和批量运行。

---

## 小结

- Matplotlib 是通用科学绘图库，覆盖数据探索、实验分析、自动化报表、桌面工具和出版级输出；
- `Figure`、`Axes`、`Artist` 构成它的对象模型，生产代码优先使用面向对象 API；
- 后端决定图形如何渲染和承载：`Agg` 面向无 GUI 批处理，`QtAgg`/`TkAgg` 等面向桌面交互，`inline`/`ipympl` 面向 Jupyter，`pdf`/`svg`/`pgf` 面向出版；
- 后端应根据运行环境选择。服务器和容器显式使用 `Agg`，需要窗口时再选择匹配的 GUI 后端；
- `use()` 必须在导入 `pyplot` 前调用，批量或服务端代码要及时 `close(fig)`，并把字体、依赖和输出格式纳入部署管理。

掌握后端之后，Matplotlib 就不再只是一个“画图函数集合”，而是一套可以从交互探索平滑过渡到自动化生产的渲染系统。
