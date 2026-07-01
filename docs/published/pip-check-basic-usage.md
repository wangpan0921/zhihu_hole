# pip check 基本用法：快速发现 Python 环境里的依赖冲突

Python 项目跑不起来时，很多人第一反应是重新执行：

```bash
pip install -r requirements.txt
```

或者更粗暴一点：

```bash
pip install --upgrade 包名
```

有时这样确实能解决问题，但也有时会把环境越修越乱：A 包需要新版依赖，B 包只支持旧版依赖；某个依赖被卸载了，但还有包在使用它；你以为当前环境是干净的，其实里面已经混进了很多历史包。

这时可以先用一个很小的命令做体检：

```bash
python -m pip check
```

`pip check` 的作用很简单：检查当前 Python 环境中已经安装的包，它们声明的依赖关系是否还能互相满足。

它不会安装包，也不会卸载包，更不会自动修复环境。它只回答一个问题：

> 当前环境里，已安装包之间有没有缺失依赖或版本冲突？

这篇文章只讲 `pip check` 的基本用法，以及看到不同输出时应该怎么处理。

## 1. 为什么建议写成 `python -m pip check`

你可能见过两种写法：

```bash
pip check
```

以及：

```bash
python -m pip check
```

在很多情况下，它们效果一样。但更推荐后者，原因是它能更明确地告诉系统：

> 用当前这个 `python` 对应的 pip 来执行 check。

这在多 Python 版本、多虚拟环境的电脑上很重要。

例如你电脑里可能同时有：

- 系统自带 Python。
- Anaconda / Miniconda。
- 项目自己的 `.venv` 虚拟环境。
- `pyenv`、`uv`、Poetry、PDM 等工具创建的环境。

如果直接执行 `pip check`，你需要确认这个 `pip` 到底属于哪个 Python。否则可能出现一种尴尬情况：你以为自己检查的是项目环境，实际检查的是另一个全局环境。

所以日常建议先确认 Python：

```bash
python --version
python -m pip --version
```

然后再执行：

```bash
python -m pip check
```

Windows 上也经常使用：

```powershell
py -m pip check
```

如果项目使用虚拟环境，先激活虚拟环境，再执行检查。

Linux / macOS 常见激活方式：

```bash
source .venv/bin/activate
python -m pip check
```

Windows PowerShell 常见激活方式：

```powershell
.\.venv\Scripts\Activate.ps1
py -m pip check
```

## 2. 环境正常时会看到什么

如果当前环境里的依赖关系没有明显问题，输出通常是：

```text
No broken requirements found.
```

退出码是 `0`。

在命令行里，退出码常用于脚本或 CI 判断一个命令是否成功。简单理解：

- `0`：命令认为检查通过。
- 非 `0`：命令认为检查失败。

Linux / macOS 可以这样查看上一条命令的退出码：

```bash
echo $?
```

Windows 命令提示符可以这样查看：

```bat
echo %errorlevel%
```

在本地手动排查时，你一般只需要看输出内容即可。但在 CI、部署脚本、自动化检查里，退出码就很有用。

例如：

```bash
python -m pip check
```

如果检查失败，CI 可以直接把构建标记为失败，避免把依赖已经冲突的环境继续发布出去。

## 3. 缺少依赖时会看到什么

第一类常见问题是：某个包依赖另一个包，但那个依赖没有安装。

输出可能类似：

```text
pyramid 1.5.2 requires WebOb, which is not installed.
```

这句话的意思是：

- 当前环境里安装了 `pyramid 1.5.2`。
- 这个版本的 `pyramid` 需要 `WebOb`。
- 但是当前环境里没有安装 `WebOb`。

修复思路通常是安装缺失的依赖：

```bash
python -m pip install WebOb
```

安装后再次检查：

```bash
python -m pip check
```

如果没有其他问题，再看到：

```text
No broken requirements found.
```

就说明这类缺失依赖已经处理完。

不过要注意：不要只机械地复制缺什么装什么。更好的做法是回到项目的依赖文件里看一下，例如：

- `requirements.txt`
- `requirements-dev.txt`
- `pyproject.toml`
- `setup.cfg`
- `setup.py`
- `Pipfile`
- `poetry.lock`

如果这是项目运行必须依赖的包，应该把它记录到项目依赖清单里，而不是只装在你自己的电脑上。否则换一台机器、换一个同事、换到 CI 环境，问题还会再出现。

## 4. 版本不兼容时会看到什么

第二类常见问题是：依赖装了，但版本不满足要求。

输出可能类似：

```text
pyramid 1.5.2 has requirement WebOb>=1.3.1, but you have WebOb 0.8.
```

这句话的意思是：

- `pyramid 1.5.2` 要求 `WebOb` 至少是 `1.3.1`。
- 当前环境里虽然安装了 `WebOb`，但版本是 `0.8`。
- 所以依赖关系不满足。

最直接的修复方式是升级对应依赖：

```bash
python -m pip install "WebOb>=1.3.1"
```

或者：

```bash
python -m pip install --upgrade WebOb
```

然后再检查：

```bash
python -m pip check
```

但版本冲突比缺失依赖更需要谨慎。因为升级一个包可能会影响另一个包。

例如你可能遇到这种情况：

```text
package-a 1.0 requires demo-lib<2.0, but you have demo-lib 2.1.
package-b 3.0 requires demo-lib>=2.0, but you have demo-lib 1.9.
```

这类问题不是简单升级或降级一个包就一定能解决。它说明两个包对同一个依赖的版本要求可能互相打架。处理时通常有几种方向：

- 升级 `package-a` 或 `package-b`，看新版本是否放宽了依赖范围。
- 降级某个业务包，回到能共存的版本组合。
- 查项目的 lock 文件，恢复到团队已经验证过的版本。
- 新建干净虚拟环境，按项目依赖文件重新安装。
- 如果确实没有兼容版本，考虑替换其中一个库。

不要在全局 Python 环境里反复试错。越是依赖复杂的项目，越应该在虚拟环境里处理。

## 5. `pip check` 检查的是什么，不检查什么

理解边界很重要。

`pip check` 检查的是“已经安装的包”之间的依赖声明是否满足。它会读取包的元数据，例如某个包声明自己需要 `requests>=2.0`，然后检查当前环境里有没有合适版本的 `requests`。

它适合发现：

- 依赖没有安装。
- 依赖版本太低。
- 依赖版本太高，超出了某个包声明的范围。
- 手动卸载、强制安装、混用工具后留下的环境不一致。

但它不负责检查：

- 你的业务代码是否能运行。
- 包里是否有运行时 bug。
- 可选依赖是否应该安装。
- 系统级依赖是否存在，例如数据库客户端、C 编译器、动态链接库。
- 不同平台上的行为差异。
- 安全漏洞。

所以 `pip check` 不能替代测试，也不能替代安全扫描。它更像一个低成本的依赖健康检查。

一个比较实用的组合是：

```bash
python -m pip check
python -m pytest
```

前者检查包依赖关系，后者检查项目行为。

## 6. 什么时候应该运行 `pip check`

`pip check` 命令很快，适合放在下面几个时机。

第一，安装完依赖之后。

```bash
python -m pip install -r requirements.txt
python -m pip check
```

这样可以立刻发现安装结果是否有冲突。

第二，升级依赖之后。

```bash
python -m pip install --upgrade requests
python -m pip check
```

升级单个包时，pip 可能会调整相关依赖。检查一下能及时发现连带影响。

第三，删除依赖之后。

```bash
python -m pip uninstall some-package
python -m pip check
```

有时你以为某个包没人用，卸载后才发现还有别的包依赖它。

第四，CI 构建过程中。

一个简单的 CI 步骤可以是：

```bash
python -m pip install -r requirements.txt
python -m pip check
python -m pytest
```

这样依赖冲突会在自动化阶段暴露，而不是等到部署或运行时才发现。

第五，接手旧项目时。

当你拿到一个旧环境，不确定里面经历过多少次手动安装和升级，可以先执行：

```bash
python -m pip check
```

如果输出一堆冲突，不要急着逐条修。更稳的方式通常是：

1. 找到项目官方依赖文件。
2. 新建虚拟环境。
3. 重新安装依赖。
4. 再执行 `pip check`。

旧环境本身可能已经没有修复价值，重建比修补更可靠。

## 7. 常见排查流程

如果 `pip check` 报错，可以按下面顺序处理。

第一步，确认自己检查的是正确环境：

```bash
python --version
python -m pip --version
```

看输出里的 Python 路径和 pip 路径是不是你当前项目的虚拟环境。

第二步，查看问题包信息：

```bash
python -m pip show 包名
```

例如：

```bash
python -m pip show pyramid
python -m pip show WebOb
```

`pip show` 会显示包版本、安装位置、依赖列表等信息。

第三步，决定是安装、升级、降级，还是重建环境。

缺少依赖时，通常可以安装缺失包。版本不兼容时，先看项目依赖文件和 lock 文件，不要盲目升级。

第四步，每次调整后都重新运行：

```bash
python -m pip check
```

直到输出：

```text
No broken requirements found.
```

第五步，运行项目测试或启动命令。

依赖检查通过，只能说明包元数据层面没有明显冲突。项目是否真的能跑，还要看测试和实际启动结果。

## 8. 和 `pip install` 的关系

很多人会疑惑：既然 pip 安装包时已经会解析依赖，为什么还需要 `pip check`？

原因是，真实环境可能不是一次干净安装出来的。

例如：

- 你先安装了 A。
- 后来又安装了 B，B 改动了某些依赖版本。
- 你手动卸载了 C。
- 某次安装用了 `--no-deps`。
- 你混用了 pip、conda、系统包管理器。
- 一个旧项目经历了很多次局部升级。

最终环境里“当前安装状态”不一定还满足所有包的声明要求。

`pip install` 更关注这一次安装动作应该怎么做；`pip check` 关注安装动作完成后，整个环境现在是否一致。

可以把它们理解成：

- `pip install`：安装或调整包。
- `pip check`：检查安装结果有没有破损依赖。

所以在依赖复杂的项目里，安装后多跑一次 `pip check` 是一个很便宜的保险。

## 9. 具体场景：检查一个 Docker image 能不能直接拿来 freeze

再看一个很实际的场景。

你手里有一个已经构建好的 Docker image，里面装了一批 Python 包。现在你想进入这个 image，执行：

```bash
python -m pip freeze > constraints.txt
```

然后把这个 `constraints.txt` 当成后续安装依赖时的约束文件使用，例如：

```bash
python -m pip install -r requirements.txt -c constraints.txt
```

在生成约束文件之前，你想先确认这个 image 里已经安装的包有没有冲突。这种情况下，`pip check` 是适用的，而且非常适合先跑一遍。

可以直接在容器里执行：

```bash
docker run --rm your-image:tag python -m pip check
```

如果 image 的默认命令不是 Python，也可以显式进入 shell：

```bash
docker run --rm your-image:tag sh -lc "python -m pip check"
```

如果镜像里命令叫 `python3`：

```bash
docker run --rm your-image:tag python3 -m pip check
```

检查通过时会看到：

```text
No broken requirements found.
```

这说明在这个 image 当前的 Python 环境里，已经安装的包之间没有发现缺失依赖或版本不满足的问题。此时再导出 freeze 文件更合理：

```bash
docker run --rm your-image:tag sh -lc "python -m pip check && python -m pip freeze" > constraints.txt
```

这里用了 `&&`，意思是只有 `pip check` 通过后，才执行 `pip freeze`。如果 `pip check` 发现冲突，命令会失败，避免你把一个已经破损的环境固化成约束文件。

不过要分清两件事。

第一，`pip check` 检查的是 image 里“当前已经安装好的环境”。它不会检查 `constraints.txt` 这个文件本身是否设计合理，也不会模拟未来安装 `requirements.txt -c constraints.txt` 时是否一定成功。

第二，`pip freeze` 产生的是当前环境的完整版本快照，不等于手写的业务依赖清单。把它当约束文件使用时，它更像是在说：

> 后续安装时，尽量把相关包限制在这个 image 里已经验证过的版本集合里。

所以更稳的流程通常是：

```bash
docker run --rm your-image:tag sh -lc "python -m pip check && python -m pip freeze" > constraints.txt
python -m pip install -r requirements.txt -c constraints.txt
python -m pip check
```

第一步检查并导出 image 里的版本快照。第二步在目标环境里按业务依赖和约束文件安装。第三步再次检查目标环境最终安装结果是否有冲突。

如果你想在 Docker 构建过程中阻止坏镜像产出，也可以在 `Dockerfile` 里加一行：

```dockerfile
RUN python -m pip check
```

更常见的是放在安装依赖之后：

```dockerfile
RUN python -m pip install -r requirements.txt \
    && python -m pip check
```

这样镜像构建阶段就能暴露依赖冲突。

结论是：

- 想检查 Docker image 里已安装 Python 包是否有冲突：`pip check` 适用。
- 想在 `pip freeze` 前确认 image 环境是否健康：`pip check` 适用。
- 想验证 `constraints.txt` 文件未来对所有安装场景都没问题：不能只靠 `pip check`，还要在目标安装流程里实际安装并再次检查。

## 10. 新手最容易踩的三个坑

第一个坑：在错误的目录或错误的环境里运行。

`pip check` 不关心你当前目录有没有项目文件，它检查的是当前 Python 环境。你站在哪个目录不是最关键的，关键是你使用的是哪个 `python`。

所以不要只看命令能不能执行，要看：

```bash
python -m pip --version
```

输出里的路径是否属于当前项目虚拟环境。

第二个坑：看到报错就立刻全局升级。

例如：

```bash
python -m pip install --upgrade 某个依赖
```

这可能解决一条报错，也可能引入新的冲突。团队项目应优先尊重项目依赖文件和 lock 文件。

第三个坑：把 `pip check` 当成万能体检。

它只检查 Python 包依赖元数据。即使它通过了，也可能存在数据库连不上、配置文件缺失、环境变量错误、系统动态库缺失、业务测试失败等问题。

## 11. 一句话总结

`pip check` 是一个小而实用的依赖体检命令。

日常可以记住这套流程：

```bash
python -m pip --version
python -m pip check
```

如果输出：

```text
No broken requirements found.
```

说明当前环境中已安装 Python 包的依赖声明没有发现破损。

如果输出某个包 `requires ... which is not installed`，说明缺依赖。

如果输出某个包 `has requirement ..., but you have ...`，说明版本不满足。

修复之后，再跑一次：

```bash
python -m pip check
```

直到检查通过，然后再运行测试或启动项目。

它不能替代虚拟环境、lock 文件和自动化测试，但非常适合做安装依赖之后的第一道健康检查。

参考资料：

- pip 官方文档：`https://pip.pypa.io/en/stable/cli/pip_check/`
