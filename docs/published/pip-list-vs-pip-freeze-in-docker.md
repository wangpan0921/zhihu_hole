# Docker 镜像中 pip list 和 pip freeze 为什么结果不同

在 Docker 镜像里排查 Python 依赖版本时，很多人会执行这两个命令：

```bash
python -m pip list
python -m pip freeze
```

它们看起来都在列出当前环境里的 Python 包和版本，但实际用途并不一样。因此，在容器里看到两者输出不同是很常见的现象。

最典型的情况是：`pip list` 能看到 `pip`、`setuptools`、`wheel` 等包，而 `pip freeze` 默认不显示它们。这个差异不是镜像损坏，也通常不是 pip 出错，而是两个命令的设计目标不同。

## 一句话区别

`pip list` 是环境清单，用来查看当前 Python 环境中安装了哪些包，以及对应版本。

`pip freeze` 是 requirements 输出，用来生成适合写入 `requirements.txt` 的依赖固定格式，重点服务于环境复现。

也就是说，`pip list` 更像是在查看现场，`pip freeze` 更像是在导出依赖文件。

## 输出格式不同

`pip list` 默认输出表格：

```text
Package    Version
---------- -------
pip        26.1
setuptools 80.9.0
requests   2.32.4
```

`pip freeze` 默认输出 requirements 格式：

```text
requests==2.32.4
```

这也是它经常被用来生成依赖文件的原因：

```bash
python -m pip freeze > requirements.txt
```

之后可以在另一个环境里安装相同版本的依赖：

```bash
python -m pip install -r requirements.txt
```

## 为什么 Docker 镜像里两者经常不一致

### 1. pip freeze 默认会隐藏部分基础打包工具

这是最容易被误解的一点。

`pip list` 会列出已安装包，包括 `pip` 自己、`setuptools`、`wheel` 这类构建和安装工具。

但 `pip freeze` 默认会省略一些基础工具包，让输出更聚焦于项目依赖，而不是 Python 环境自带的维护工具。根据 pip 文档：

- Python 3.11 及更早版本中，`pip freeze` 默认排除 `pip`、`setuptools`、`wheel`、`distribute`。
- Python 3.12 及更新版本中，默认只排除 `pip`。
- 如果想让 `pip freeze` 也输出这些包，需要加 `--all`。

例如：

```bash
python -m pip freeze --all
```

所以在 Docker 镜像中看到下面这种差异是正常的：

```bash
python -m pip list | grep -E 'pip|setuptools|wheel'
python -m pip freeze | grep -E 'pip|setuptools|wheel'
```

第一个命令可能都有结果，第二个命令可能没有，或者只少了其中一部分。这不代表包没有安装，而是 `pip freeze` 的默认过滤策略不同。

### 2. Docker 基础镜像通常不是空白 Python 环境

很多基础镜像已经预装了 Python 打包工具。例如 `python:3.x` 镜像通常会带有 `pip`，并可能包含 `setuptools`、`wheel`，或者这些工具在后续构建步骤里被安装过。

这些包属于镜像环境的一部分，不一定是业务项目显式声明的依赖。`pip list` 会忠实展示它们；`pip freeze` 则倾向于输出可复现项目依赖，因此默认弱化这部分工具包。

比如你在容器里执行：

```bash
docker run --rm python:3.11 python -m pip list
```

和：

```bash
docker run --rm python:3.11 python -m pip freeze
```

两者输出长度可能明显不同。这种不同通常是预期行为。

### 3. pip list --format=freeze 也不完全等于 pip freeze

有些人会认为下面两个命令是等价的：

```bash
python -m pip list --format=freeze
python -m pip freeze
```

它们的输出格式确实相似，都是 `name==version`，但语义仍然不同。

`pip list --format=freeze` 仍然是 `pip list` 的清单视角，只是把展示格式换成了 freeze 风格。

`pip freeze` 则是 requirements 导出视角，会应用自己的规则，比如默认排除基础打包工具，并且对 editable install、URL 安装等情况可能输出不同形式。

因此，如果只是想拿到机器可读的完整包版本清单，更推荐：

```bash
python -m pip list --format=json
```

如果想生成可安装的依赖文件，再使用：

```bash
python -m pip freeze
```

## 会不会出现同一个包版本不同

一般来说，如果 `pip list` 和 `pip freeze` 使用的是同一个 Python 环境、同一个 `site-packages`，并且看的是同一个普通已安装包，那么同一个包显示出来的版本号应该是一致的。

更常见的差异是：某些包在 `pip list` 里有，在 `pip freeze` 里没有。比如 `pip`、`setuptools`、`wheel` 这类基础工具，而不是同一个包显示成两个不同版本。

但确实可能出现“看起来版本不同”的情况，常见原因如下。

### 1. 执行的不是同一个 Python 环境

比如：

- `pip list` 用的是系统 Python。
- `pip freeze` 用的是虚拟环境里的 pip。
- Docker 镜像里同时存在多个 Python。
- 构建阶段和运行阶段使用的环境不同。

建议统一使用下面的方式确认：

```bash
python -m pip list
python -m pip freeze
python -c "import sys; print(sys.executable)"
python -m pip --version
```

这样可以确保 pip 操作的是当前 `python` 对应的环境。

### 2. PATH 或 alias 导致 pip 指向不同位置

在容器里直接执行：

```bash
pip list
pip freeze
```

不如下面这种写法稳妥：

```bash
python -m pip list
python -m pip freeze
```

因为 `pip` 命令可能受 `PATH`、alias、虚拟环境激活状态影响。尤其是在镜像里装过多个 Python 或多个 pip 时，直接调用 `pip` 很容易指向和预期不同的位置。

### 3. 容器运行时挂载改变了环境

镜像构建时安装的是一个版本，运行容器时又通过 volume 挂载、虚拟环境激活、`PYTHONPATH`、用户级 `site-packages` 看到另一个位置的包，也可能造成版本判断混乱。

这种情况尤其容易出现在开发镜像中：镜像里有一份依赖，宿主机又挂载了一份项目源码或虚拟环境，最终 Python 实际加载的路径和你以为的不一样。

### 4. editable install 或 URL 安装导致展示形式不同

如果包是用 editable 模式、本地源码路径、Git URL 或直接 URL 安装的，`pip freeze` 可能不会输出简单的：

```text
name==version
```

而是输出类似：

```text
-e git+https://example.com/repo.git@commit#egg=name
name @ file:///path/to/package
```

这时候不一定是版本真的不同，而是 `pip freeze` 为了生成可复现依赖，采用了更接近安装来源的表示方式。

### 5. 同名包在不同路径下重复存在

如果同名包在多个路径下都存在，可能会出现几种信息来源不一致：

- Python 实际 import 到的是一个路径。
- `pip list` 枚举到的是另一个分发信息。
- 你用 `grep` 看到的是某个输出里的某一行。

可以用下面命令确认包到底从哪里加载：

```bash
python -c "import 包名, sys; print(包名.__version__); print(包名.__file__); print(sys.path)"
python -m pip show 包名
```

如果 `__file__`、`pip show` 里的 `Location`、`python -m pip --version` 显示的路径不一致，就说明你看到的很可能不是同一个环境里的同一个包。

## 排查建议

如果你在 Docker 镜像里发现 `pip list` 和 `pip freeze` 输出不一致，可以按下面顺序排查。

先确认是否只是基础工具包被过滤：

```bash
python -m pip freeze --all
```

再确认 pip 和 Python 是否属于同一个环境：

```bash
which python
which pip
python -c "import sys; print(sys.executable)"
python -m pip --version
pip --version
```

然后确认某个具体包的位置和版本：

```bash
python -m pip show requests
python -c "import requests; print(requests.__version__); print(requests.__file__)"
```

如果你需要完整审计镜像里到底装了什么包，用：

```bash
python -m pip list --format=json
```

如果你需要导出项目依赖，用：

```bash
python -m pip freeze > requirements.txt
```

如果你要比较两者差异，优先使用：

```bash
python -m pip list --format=freeze | sort > list.txt
python -m pip freeze --all | sort > freeze.txt
diff -u list.txt freeze.txt
```

这样可以减少默认过滤规则带来的干扰。

## 总结

`pip list` 和 `pip freeze` 的区别不在于谁更准确，而在于用途不同。

`pip list` 面向查看当前环境完整安装清单，适合排查 Docker 镜像中实际安装了哪些包。

`pip freeze` 面向导出 requirements 格式依赖，适合固定项目依赖版本、复现环境。

在同一个 Python 环境里，同一个普通包的真实版本通常不应该在 `pip list` 和 `pip freeze` 中显示成两个不同版本。如果出现这种现象，优先检查是否使用了不同的 Python、不同的 pip、不同的安装路径，或者是否存在 editable、URL 安装、运行时挂载、重复包路径等特殊情况。

参考：

- https://pip.pypa.io/en/stable/cli/pip_list/
- https://pip.pypa.io/en/stable/cli/pip_freeze/
