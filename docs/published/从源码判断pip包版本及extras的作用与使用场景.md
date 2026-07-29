# 从 pip 包源码判断版本号，以及 extras（如 [all]）的作用与使用场景

日常开发中经常会遇到两个相关的小问题：拿到一份第三方包的源码，怎么知道它到底是哪个版本；以及安装时经常看到的 `pip install pkg[extra]` 这种写法，`[extra]`（比如 `[all]`）到底装了什么、什么时候该用。这篇整理一下这两点。

## 一、如何通过源码判断一个 pip 包的版本

Python 包的版本号来源并不是只有一处，不同的包管理方式会把版本号"藏"在不同地方。按优先级和常见程度，可以按下面几种方法逐一排查。

### 1. 已安装环境：直接用工具查，不用翻源码

如果包已经 `pip install` 到当前环境里，最快最准的方式是不看源码，直接问 pip 或 Python 本身：

```bash
pip show ray
# 或者
python -c "import importlib.metadata as m; print(m.version('ray'))"
```

`importlib.metadata.version()`（Python 3.8+ 内置）读取的是安装时生成的分发元数据（`.dist-info`/`.egg-info` 目录下的 `METADATA` 文件），这是最权威的版本来源，因为它是 pip 安装时实际记录的版本号，不依赖源码里怎么写。

只有在**没有安装、只拿到一份源码目录**（比如从 GitHub clone 下来，还没 `pip install`）时，才需要去源码里找版本号，这也是本文重点。

### 2. 查 `__init__.py` 里的 `__version__` 变量

这是最常见、最经典的做法。绝大多数包会在顶层包的 `__init__.py` 里定义一个模块级变量：

```python
# ray/__init__.py 或 requests/__init__.py 等
__version__ = "2.30.0"
```

直接搜索源码：

```bash
grep -r "__version__" ray/__init__.py
# 或者不确定文件名时全局搜
grep -rn "^__version__" --include="*.py" .
```

如果源码已经能被 import（比如你已经在虚拟环境里，只是想确认代码里写的版本号），也可以直接：

```python
import ray
print(ray.__version__)
```

这是 [Python 官方打包指南](https://packaging.python.org/en/latest/guides/single-sourcing-package-version/)推荐的"单一版本来源"写法之一：把版本号写在 `__init__.py`，其他地方（`setup.py`、`pyproject.toml`）再从这里读取，避免多处维护版本号导致不一致。

### 3. 查 `setup.py`

如果项目还在用传统的 `setuptools` + `setup.py`（较老的项目，或者不用 `pyproject.toml` 的项目），版本号常常直接写在 `setup()` 调用里：

```python
# setup.py
setup(
    name="somepkg",
    version="1.4.2",
    ...
)
```

有些项目为了避免维护两处版本号，会让 `setup.py` 反过来去读 `__init__.py` 里的 `__version__`（用正则或 `exec` 读取，避免直接 `import` 触发包的依赖加载），这种情况下源码里搜索 `version=` 可能找到的是一段读取逻辑而不是硬编码的版本号，需要再往 `__init__.py` 或者 `VERSION` 文件里追。

### 4. 查 `pyproject.toml`

现在新项目基本都迁移到了 PEP 517/518 标准的 `pyproject.toml`，版本号在 `[project]` 表里：

```toml
[project]
name = "somepkg"
version = "1.4.2"
```

如果用的是 Poetry，格式类似但在 `[tool.poetry]` 下：

```toml
[tool.poetry]
name = "somepkg"
version = "1.4.2"
```

也有些项目把 `version` 标记为 `dynamic = ["version"]`，意味着版本号不是写死在 `pyproject.toml` 里的，而是运行时/构建时从别处（`__init__.py`、`VERSION` 文件，或 git tag，常见于 `setuptools_scm`）动态取的，这时 `pyproject.toml` 本身查不到具体版本号，要去看它声明的动态来源。

### 5. 查专门的 `VERSION` / `version.py` 文件

一些项目（尤其是大型项目，如 TensorFlow、Ray 的某些子模块）会把版本号单独放在一个文件里，方便构建脚本和源码同时引用：

```
VERSION
# 或
pkg/version.py:  version = "2.30.0"
```

直接翻源码根目录或包目录下有没有 `VERSION`、`version.py`、`_version.py` 这类文件即可。

### 6. 用 git 信息判断（针对 clone 下来的源码）

如果源码是 git 仓库，且项目使用 `setuptools_scm` / `versioneer` 这类"从 git tag 自动生成版本号"的机制（版本号不写死在任何文件里），可以看：

```bash
git describe --tags        # 输出类似 v2.30.0-3-gabcdef1，表示当前比 v2.30.0 tag 多 3 个 commit
git log --oneline -1        # 看当前 commit，配合 tag 列表判断在哪个版本附近
```

### 排查顺序建议

拿到一份不熟悉的源码，建议按这个顺序找版本号，命中就停：

1. 已安装的话，直接 `pip show` / `importlib.metadata.version()`，不用翻源码。
2. 顶层包的 `__init__.py` 搜 `__version__`。
3. `pyproject.toml` 的 `[project].version`（注意是否 `dynamic`）。
4. `setup.py` 里 `version=` 参数。
5. 找 `VERSION` / `version.py` 单独文件。
6. 都没有的话，看是不是靠 `setuptools_scm`/`versioneer` 从 git tag 生成，直接查 git tag。

## 二、pip extras（如 `[all]`）的作用及使用场景

### 1. extras 是什么

`pip install package[extra1,extra2]` 里方括号的部分叫 **extras**（可选依赖组），是 Python 打包规范里的标准机制。包作者在 `setup.py`/`pyproject.toml` 里可以定义多组"可选依赖"，用户安装时按需选择要不要装：

```toml
# pyproject.toml 里典型的定义方式
[project.optional-dependencies]
data = ["pyarrow>=6.0"]
train = ["torch", "tensorboardX"]
all = ["pyarrow>=6.0", "torch", "tensorboardX", "..."]
```

默认 `pip install package` 只装**核心依赖**（`dependencies`，必需的最小依赖集）；写成 `package[extra]` 就是告诉 pip "把 `extra` 这组可选依赖也一起装上"。

### 2. `[all]` 具体做了什么

`all` 本身没有任何语言层面的特殊含义，它只是包作者约定俗成起的一个 extras 组名字（有的项目叫 `full`、`complete`），习惯上用来表示"把所有可选功能模块的依赖都装上"。以 Ray 为例：

```bash
pip install ray            # 只装核心（分布式调度等基础运行时）
pip install "ray[default]" # 核心 + Dashboard/集群管理依赖
pip install "ray[data]"    # 核心 + Ray Data（数据处理，依赖 pyarrow 等）
pip install "ray[train]"   # 核心 + Ray Train（分布式训练）
pip install "ray[tune]"    # 核心 + Ray Tune（超参搜索）
pip install "ray[rllib]"   # 核心 + 强化学习（依赖 gymnasium 等）
pip install "ray[serve]"   # 核心 + Ray Serve（在线服务）
pip install "ray[all]"     # 核心 + 以上全部子系统依赖
```

具体某个包的 `[all]` 包含哪些内容，取决于包作者怎么定义，没有统一标准，遇到不熟悉的包时建议直接查它的 `pyproject.toml`/`setup.py` 里 `optional-dependencies`/`extras_require` 的定义，或者看官方文档里的 extras 说明。

### 3. 什么场景该用 `[all]`，什么场景不该用

**适合用 `[all]` 的场景：**

- 本地开发、调试、探索性使用，想一次装齐全部功能，避免"用到哪个模块才发现缺依赖，再回去重装"的反复折腾。
- 教程、Demo、CI 里跑集成测试，需要覆盖项目的多个子系统。

**不建议用 `[all]` 的场景：**

- **生产环境 / 生产镜像**：`[all]` 会拉入大量你用不到的第三方依赖，直接后果是镜像体积暴涨、构建变慢，还会增加依赖冲突和安全漏洞的暴露面（多一个依赖就多一份供应链风险）。生产环境应该只装真正用到的 extras，比如只用 Ray Serve 就装 `ray[serve]`，而不是 `ray[all]`。
- **依赖版本管理严格的项目**：extras 越多，间接依赖越多，越容易和项目里其他包的版本要求冲突，锁定依赖（`pip freeze`/`poetry lock`）时也更难排查问题根源。
- **只是想用某个特定子功能**：明确知道自己只用 Tune 做超参搜索，就装 `ray[tune]`，没必要为了省事装 `[all]` 而承担不必要的依赖负担。

一般经验：本地探索图方便可以用 `[all]`，一旦要固化到 `requirements.txt`/`Dockerfile`/生产部署里，应该把 extras 收窄到项目实际用到的那一个或几个，让依赖尽量精简可控。

### 4. 命令行写法的一个小提醒

`包名[extras]` 里的方括号在 bash/zsh 等 shell 中是通配符（glob）特殊字符，不加引号时可能被 shell 误解析。因此命令行里习惯把整体括进引号：

```bash
pip install "ray[all]==2.30.0"
```

而不是裸写 `pip install ray[all]==2.30.0`。引号包在哪个位置（`"ray[all]"==2.30.0` 还是 `ray["all"]==2.30.0`）效果是一样的，只要最终拼接给 pip 的字符串是 `ray[all]==2.30.0` 即可，但整体加引号最不容易出错，也是官方文档里的推荐写法。
