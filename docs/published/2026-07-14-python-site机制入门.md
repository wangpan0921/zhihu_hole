# Python site 机制入门：为什么 pip 安装的包能被 import

很多 Python 初学者都会遇到类似问题：

- 我明明 `pip install requests` 了，为什么 `import requests` 还是失败？
- 我电脑上有多个 Python，包到底装到哪里去了？
- 虚拟环境激活后，Python 为什么就能优先用 `.venv` 里的包？
- 有些项目里有 `.pth` 文件，它到底是干什么的？

这些问题背后都和 Python 的 **site 机制**有关。

简单说：

> `site` 机制负责在 Python 启动时，把标准的第三方包目录加入 `sys.path`，并处理一些和包搜索路径相关的初始化工作。

理解它以后，很多“为什么找不到包”“为什么导入了错误版本”“为什么虚拟环境和全局环境不一样”的问题，都会清楚很多。

## 一、先理解 import 是怎么找包的

Python 执行：

```python
import requests
```

并不是在整台电脑上到处搜索 `requests`。它只会按 `sys.path` 里的路径顺序去找。

可以用这个命令查看当前 Python 的搜索路径：

```bash
python -c "import sys; print('\n'.join(sys.path))"
```

输出可能类似：

```text
/home/me/project
/usr/lib/python3.12
/usr/lib/python3.12/lib-dynload
/home/me/project/.venv/lib/python3.12/site-packages
```

这些路径就是 Python 查找模块和包的地方。

所以 `import` 能不能成功，核心问题通常不是“这个包有没有安装过”，而是：

> 当前这个 Python 的 `sys.path` 里，能不能找到这个包？

`site` 机制的作用，就是帮 Python 在启动时把常见的包目录加进 `sys.path`。

## 二、site 是什么

`site` 是 Python 标准库里的一个模块，名字就叫 `site`。

正常启动 Python 时，它会自动导入：

```python
import site
```

你平时不需要手动写这一句，因为 Python 启动过程默认会做。

`site` 主要做几件事：

1. 找到当前 Python 对应的 `site-packages` 目录；
2. 把这些目录加入 `sys.path`；
3. 处理 `.pth` 文件；
4. 尝试导入 `sitecustomize` 和 `usercustomize`；
5. 在虚拟环境中，根据配置决定是否使用全局 site-packages。

这里最关键的是第一点：**把第三方包目录加入 `sys.path`**。

## 三、site-packages 是什么

`site-packages` 是 Python 放第三方包的目录。

你执行：

```bash
python -m pip install requests
```

pip 通常会把 `requests` 安装到当前 Python 对应的 `site-packages` 目录里。

可以用下面命令查看当前环境的 site-packages：

```bash
python -c "import site; print(site.getsitepackages())"
```

在虚拟环境里可能看到：

```text
['/home/me/project/.venv/lib/python3.12/site-packages']
```

在系统 Python 里可能看到：

```text
['/usr/local/lib/python3.12/site-packages']
```

也可以查看用户级 site-packages：

```bash
python -c "import site; print(site.getusersitepackages())"
```

用户级目录通常用于：

```bash
python -m pip install --user requests
```

这类安装方式不会写入系统目录，而是写到当前用户自己的 Python 包目录。

## 四、为什么建议用 python -m pip

很多包找不到的问题，根源是 `python` 和 `pip` 不是同一套环境。

比如你执行：

```bash
pip install requests
python -c "import requests"
```

看起来很自然，但这里有个坑：命令行里的 `pip` 可能属于另一个 Python。

更稳的写法是：

```bash
python -m pip install requests
python -c "import requests; print(requests.__file__)"
```

`python -m pip` 的意思是：

> 用当前这个 `python` 对应的 pip 去安装包。

这样装进去的包，更可能出现在当前 Python 的 `site-packages` 里，也就能被当前 Python import 到。

排查时可以看：

```bash
python -c "import sys; print(sys.executable)"
python -m pip --version
python -c "import site; print(site.getsitepackages())"
```

如果 `pip --version` 输出里的路径和你以为的 Python 环境不一致，就很容易出现“装了但导不进来”的问题。

## 五、虚拟环境和 site 的关系

虚拟环境本质上是在项目里创建一套相对独立的 Python 环境。

常见命令：

```bash
python -m venv .venv
source .venv/bin/activate
```

激活后：

```bash
which python
python -c "import sys; print(sys.prefix)"
python -c "import site; print(site.getsitepackages())"
```

你会看到 Python 路径和 `site-packages` 都指向 `.venv`。

这就是虚拟环境隔离依赖的核心：

> 同一个项目用自己的 `site-packages`，不要和系统 Python、其他项目混在一起。

虚拟环境目录里通常有一个 `pyvenv.cfg` 文件。它会记录一些配置，比如：

```text
include-system-site-packages = false
```

这表示默认不使用系统的 site-packages。

如果改成：

```text
include-system-site-packages = true
```

虚拟环境就可能同时看到全局环境里的包。初学者一般不建议这么做，因为它会让环境变得不够干净：你以为项目依赖都在 `.venv` 里，实际可能偷偷用了系统 Python 里的包。

## 六、.pth 文件是什么

`site` 启动时还会处理 `site-packages` 里的 `.pth` 文件。

`.pth` 文件可以理解成：

> 一个告诉 Python “额外把这些路径加入 `sys.path`” 的小配置文件。

比如 `site-packages/demo.pth` 里写：

```text
/home/me/my-extra-python-libs
```

Python 启动时，`site` 读到这个 `.pth` 文件，就会把这个路径加入 `sys.path`。之后这个目录里的模块也能被 import。

这听起来很神奇，但也容易带来排查问题。

比如你以为当前项目导入的是：

```text
/home/me/project/foo.py
```

实际却因为 `.pth` 文件，导入了另一个目录里的：

```text
/home/me/my-extra-python-libs/foo.py
```

所以遇到“明明代码改了，运行结果却没变”“导入的不是我项目里的文件”时，可以检查：

```bash
python -c "import sys; print('\n'.join(sys.path))"
```

也可以查某个包实际来自哪里：

```bash
python -c "import requests; print(requests.__file__)"
```

## 七、sitecustomize 和 usercustomize

`site` 还有一个比较少见但很有用的机制：启动时尝试导入两个模块。

```text
sitecustomize
usercustomize
```

它们和 `site` 的关系可以这样理解：

```text
Python 启动
  ↓
自动导入 site 模块
  ↓
site 初始化 sys.path / site-packages / .pth
  ↓
site 尝试导入 sitecustomize
  ↓
site 尝试导入 usercustomize
```

也就是说，`sitecustomize` 和 `usercustomize` 不是独立于 `site` 之外的新机制，而是 `site` 模块启动流程里的两个“钩子”。

如果它们存在于 `sys.path` 中，Python 启动时会自动导入它们；如果不存在，Python 会安静地跳过，不会影响正常启动。

可以理解成：

- `sitecustomize`：给整个 Python 环境做统一定制；
- `usercustomize`：给当前用户做定制。

它们通常放在这些位置：

- `sitecustomize.py`：全局 `site-packages` 或某个虚拟环境的 `site-packages`；
- `usercustomize.py`：当前用户的 user site-packages。

可以先查这些目录：

```bash
python -c "import site; print(site.getsitepackages())"
python -c "import site; print(site.getusersitepackages())"
```

实际应用场景包括：

- 公司内部统一配置包源或环境变量；
- 启动时自动加一些内部库路径；
- 在调试环境里打印 Python 路径；
- 做一些运行时监控或初始化。

比如想让某个 Python 环境启动时自动打印调试信息，可以在当前环境的 `site-packages` 里创建 `sitecustomize.py`：

```python
# sitecustomize.py
import sys

print("Python executable:", sys.executable)
print("sys.path:")
for item in sys.path:
    print(" ", item)
```

之后每次运行这个 Python：

```bash
python app.py
```

启动时都会自动执行 `sitecustomize.py`。

再比如自动加入一个内部库路径：

```python
# sitecustomize.py
import sys

internal_lib = "/opt/company/python-libs"
if internal_lib not in sys.path:
    sys.path.append(internal_lib)
```

这样 `/opt/company/python-libs` 里的模块也能被 import。

`usercustomize.py` 的写法类似，只是作用范围更偏向当前用户。比如你只想给自己的开发账号加一段调试逻辑，而不是影响整台机器上的所有 Python 用户，就更适合放到用户级 site-packages。

不过对初学者来说，不建议随便使用它们。因为它们是“自动执行”的，项目里如果有人不知道这层机制，排查问题会很痛苦。

如果怀疑当前环境里有这种自动定制，可以运行：

```bash
python -c "import sitecustomize; print(sitecustomize.__file__)"
```

或者：

```bash
python -c "import usercustomize; print(usercustomize.__file__)"
```

如果不存在，通常会报：

```text
ModuleNotFoundError: No module named sitecustomize
```

这表示没有配置，不是错误。

需要注意：如果用 `python -S` 启动，Python 不会自动导入 `site`，因此也不会自动执行 `sitecustomize` 和 `usercustomize`。这也是为什么它们属于 `site` 机制的一部分。

使用它们时建议保持克制：

- 不要放网络请求、耗时操作；
- 不要悄悄修改太多全局行为；
- 不要在团队项目里依赖只有个人机器才有的 `usercustomize.py`；
- 如果确实使用，最好在文档里写清楚，否则后续排查会很隐蔽。

## 八、如何临时跳过 site

Python 有一个启动参数：

```bash
python -S
```

`-S` 的意思是启动时不要自动导入 `site`。

可以对比一下：

```bash
python -c "import sys; print('\n'.join(sys.path))"
python -S -c "import sys; print('\n'.join(sys.path))"
```

你会发现 `-S` 之后，很多 `site-packages` 路径可能不见了。

这说明平时你能 import 第三方包，很大程度上是因为 `site` 帮你把包目录加到了 `sys.path`。

实际排查时，`python -S` 可以用来确认：

> 某个路径是不是由 site 机制加进来的？

但日常运行项目时，一般不需要使用 `-S`。

## 九、实际应用场景一：排查“pip 装了但 import 失败”

这是最常见的问题。

错误类似：

```text
ModuleNotFoundError: No module named 'requests'
```

排查顺序：

```bash
python -c "import sys; print(sys.executable)"
python -m pip --version
python -c "import site; print(site.getsitepackages())"
python -m pip show requests
```

重点看：

- `python` 是不是你以为的那个 Python；
- `python -m pip --version` 里的路径是不是同一个环境；
- `pip show requests` 里的 `Location` 是否在当前 `site-packages` 里。

如果不是同一个环境，用：

```bash
python -m pip install requests
```

不要直接用不确定来源的：

```bash
pip install requests
```

## 十、实际应用场景二：排查导入了错误版本

有时不是 import 失败，而是导入了错误版本。

比如你以为项目用的是 `requests==2.31.0`，实际运行时却用了别的版本。

可以查：

```bash
python -c "import requests; print(requests.__version__); print(requests.__file__)"
```

输出里的 `__file__` 很关键。它告诉你 Python 实际导入的是哪个路径里的包。

再结合：

```bash
python -c "import sys; print('\n'.join(sys.path))"
```

就能判断是不是：

- 没激活虚拟环境；
- 用户级 site-packages 里有旧包；
- `.pth` 文件额外加入了路径；
- 当前目录里有同名文件挡住了第三方包。

一个常见坑是项目里有文件叫：

```text
requests.py
```

这会遮住真正的第三方 `requests` 包。因为当前目录通常在 `sys.path` 比较靠前的位置。

## 十一、实际应用场景三：理解 editable install

开发 Python 包时，经常会用：

```bash
python -m pip install -e .
```

`-e` 是 editable install，意思是“可编辑安装”。

它的效果是：你修改源码后，不需要重新安装，Python 就能导入最新代码。

它背后也和路径机制有关。安装工具通常会在环境里放入 `.pth` 文件或等价的链接信息，让 Python 能从你的源码目录加载包。

所以当你看到：

```bash
python -m pip list
```

里面某个包显示为 editable，或者 `site-packages` 里有看起来奇怪的 `.pth` 文件，不要惊讶。这通常是开发模式安装带来的。

排查 editable 包实际来源：

```bash
python -c "import your_package; print(your_package.__file__)"
```

如果路径指向你的源码目录，就说明它正在从源码目录加载。

## 十二、实际应用场景四：Docker 镜像里找包路径

Docker 镜像里也经常遇到多个 Python / pip 混用问题。

建议进入容器后先查：

```bash
python -c "import sys; print(sys.executable)"
python -m pip --version
python -c "import site; print(site.getsitepackages())"
python -c "import sys; print('\n'.join(sys.path))"
```

如果 Dockerfile 里写了：

```dockerfile
RUN pip install -r requirements.txt
```

但运行时用的是另一个 Python，就可能出现构建时装了包、运行时找不到包的问题。

更稳的写法是：

```dockerfile
RUN python -m pip install -r requirements.txt
```

如果镜像里明确使用 `/usr/local/bin/python`，那就写得更明确：

```dockerfile
RUN /usr/local/bin/python -m pip install -r requirements.txt
```

核心原则还是同一个：

> 用哪个 Python 运行项目，就用哪个 Python 对应的 pip 安装包。

## 十三、常用排查命令速查

| 目标 | 命令 |
|---|---|
| 看当前 Python 路径 | `python -c "import sys; print(sys.executable)"` |
| 看当前搜索路径 | `python -c "import sys; print('\\n'.join(sys.path))"` |
| 看 site-packages | `python -c "import site; print(site.getsitepackages())"` |
| 看用户级 site-packages | `python -c "import site; print(site.getusersitepackages())"` |
| 看 pip 属于哪个 Python | `python -m pip --version` |
| 看某个包安装位置 | `python -m pip show requests` |
| 看实际 import 的文件 | `python -c "import requests; print(requests.__file__)"` |
| 临时跳过 site 启动 | `python -S` |

## 十四、小结

Python 的 `site` 机制可以用一句话理解：

> Python 启动时，`site` 会把当前环境的第三方包目录加入 `sys.path`，让 pip 安装的包能被 import。

对初学者来说，最重要的是记住这几个判断：

1. `import` 查找包，看的是 `sys.path`。
2. `site-packages` 是第三方包通常被安装的位置。
3. `python -m pip` 比直接 `pip` 更不容易装错环境。
4. 虚拟环境通过自己的 `site-packages` 实现依赖隔离。
5. `.pth`、`sitecustomize`、`usercustomize` 都可能改变 Python 启动后的路径和行为。

以后遇到“包找不到”“版本不对”“Docker 里能装不能用”“虚拟环境不生效”这类问题，不要只盲目重装包。先看当前 Python 是谁、`sys.path` 里有什么、包实际从哪里被 import。大多数问题都能顺着这条线查出来。
