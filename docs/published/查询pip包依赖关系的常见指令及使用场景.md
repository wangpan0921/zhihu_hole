# 查询 pip 包依赖关系的常见指令及使用场景

Python 项目一旦依赖多了，"这个包到底依赖了谁""谁又依赖了这个包""升级会不会把别的东西搞坏"就成了日常问题。这篇整理一下查依赖关系时常用的几个指令，以及各自适合的场景，方便按需选用而不是每次都靠猜。

## 一、pip 自带的指令

pip 本身不做完整的依赖树分析，但几个自带子命令能覆盖大部分基础排查需求。

### 1. `pip show <package>`

查看某个包的元信息，重点是 `Requires`（它依赖谁）和 `Required-by`（谁依赖它）。

```bash
$ pip show requests
Name: requests
Version: 2.31.0
...
Requires: charset-normalizer, idna, urllib3, certifi
Required-by: 
```

**使用场景**：

- 快速确认某个包直接依赖了哪些库（一级依赖，不递归）。
- 想删除一个包之前，先看 `Required-by` 是否为空——非空说明还有别的已安装包依赖它，直接卸载可能连带弄坏其他功能。
- 配合 `-f/--files` 参数（`pip show -f <package>`）还能看到这个包装了哪些文件，排查"命令找不到""模块导入报错"之类问题时有用。

局限：`Requires`/`Required-by` 都只是**直接依赖**，不会递归展开，也不会做版本冲突分析。

### 2. `pip list`

列出当前环境已安装的所有包。

```bash
pip list                    # 表格形式列出全部包
pip list --format=freeze    # 输出 requirements.txt 风格，可直接重定向保存
pip list --not-required     # 只列出"没有被其他已安装包依赖"的包，即顶层直接安装的包
pip list --outdated         # 列出有新版本可用的包
```

**使用场景**：

- `--format=freeze` 常用来生成/校对 `requirements.txt`：`pip list --format=freeze > requirements.txt`。
- `--not-required` 很实用：可以从一堆已安装包里筛出"我自己主动装的"，因为间接依赖会被过滤掉，剩下的基本就是显式 `pip install` 过的包，帮助整理臃肿的环境。
- `--outdated` 用于排查升级计划,看哪些依赖落后了，是做依赖升级前的第一步。

### 3. `pip check`

检查当前环境里已安装包的依赖是否满足（版本冲突检测）。

```bash
$ pip check
No broken requirements found.
```

如果有冲突，会输出类似：

```
package-a 1.0 has requirement package-b>=2.0, but you have package-b 1.5.
```

**使用场景**：

- 环境改动之后（手动升级/降级某个包、pip 安装时用了 `--no-deps` 跳过依赖解析）想确认是否引入了版本冲突。
- CI 流水线里加一步 `pip check`，防止环境里存在互相不兼容的包版本却没人发现。

### 4. `pip download` / `pip install --dry-run`

`pip install <pkg> --dry-run --report -` 或较新版本的 `pip install --dry-run` 会解析依赖但不真正安装，可以提前看 pip 打算装哪些版本、会不会有冲突。

**使用场景**：

- 在正式环境升级前，先干跑一遍看 pip 的依赖解析结果，避免直接执行后才发现版本被意外降级。
- 排查"为什么装了 A 之后 B 的版本被改了"，dry-run 能提前暴露解析器的决策。

## 二、pipdeptree：查看完整依赖树

pip 自带命令只能看一层依赖，真正想要一棵完整的依赖树（谁依赖谁，一直往下展开），要用第三方工具 [pipdeptree](https://github.com/tox-dev/pipdeptree)。

```bash
pip install pipdeptree
```

### 1. 查看整棵依赖树

```bash
pipdeptree
```

输出类似：

```
requests==2.31.0
├── certifi [required: >=2017.4.17, installed: 2023.11.17]
├── charset-normalizer [required: >=2,<4, installed: 3.3.2]
├── idna [required: >=2.5,<4, installed: 3.6]
└── urllib3 [required: >=1.21.1,<3, installed: 2.1.0]
```

**使用场景**：一次性看清整个环境的依赖层级关系，比逐个 `pip show` 递归查快得多，尤其适合排查"为什么装了 X 就自动带来了 Y 这个版本"。

### 2. 反向查询：谁依赖了这个包

```bash
pipdeptree --reverse --packages urllib3
# 或简写
pipdeptree -r -p urllib3
```

**使用场景**：想卸载/升级某个基础库（比如 `urllib3`、`setuptools`）之前，先搞清楚有哪些上层包间接依赖它，避免升级后一连串包出问题。这是排查依赖冲突时最常用的一条。

### 3. 只看某个包的依赖子树

```bash
pipdeptree --packages requests
```

只展开你关心的那个包及其依赖，避免整棵树信息过多看不清重点。

### 4. 检测冲突和循环依赖

```bash
pipdeptree --warn fail
```

pipdeptree 会自动检测版本冲突（同一个包被不同上层要求不同版本区间）和循环依赖，并在发现问题时通过退出码/警告提示，适合塞进 CI 做依赖健康检查，比手写脚本解析 `pip show` 输出靠谱。

### 5. 输出 JSON，方便脚本处理

```bash
pipdeptree --json-tree
```

**使用场景**：需要用脚本自动分析依赖关系（比如做许可证扫描、生成依赖图可视化）时，JSON 结构比人读的树状文本更好解析。

## 三、其他辅助手段

### 1. `pip freeze`

```bash
pip freeze > requirements.txt
```

严格来说这不是"查依赖关系"，而是把当前环境所有包及精确版本导出。常和 `pip list --format=freeze` 混用，两者输出基本一致，`freeze` 是更早期、更常见的写法。

**使用场景**：环境固化、复现问题现场、CI 里锁定版本。但注意它是**扁平列表**，不区分直接依赖和间接依赖，也看不出层级关系——这也是为什么直接依赖和间接依赖混在一起的 `requirements.txt` 后期维护困难，很多项目现在改用 `pip-tools`（`pip-compile`）来区分"我要的依赖"和"被动引入的依赖"。

### 2. `importlib.metadata`（标准库，脚本化查询）

如果要在 Python 代码里查依赖关系而不是敲命令行：

```python
from importlib.metadata import requires, metadata

print(requires("requests"))
# ['charset-normalizer<4,>=2', 'idna<4,>=2.5', 'urllib3<3,>=1.21.1', 'certifi>=2017.4.17', ...]
```

**使用场景**：写自动化脚本（比如自研的依赖审计工具、License 扫描工具）时，比 shell 出去解析 `pip show` 的文本输出更稳健，不用担心格式变化。Python 3.8+ 内置，不需要额外装 `pkg_resources`（已废弃）。

## 四、常见指令速查表

| 目标 | 推荐指令 |
|---|---|
| 看某个包依赖了谁（一级） | `pip show <pkg>` |
| 看谁依赖了某个包（一级） | `pip show <pkg>` 的 `Required-by` |
| 看完整依赖树 | `pipdeptree` |
| 看谁（递归）依赖某个包 | `pipdeptree -r -p <pkg>` |
| 筛出自己主动装的顶层包 | `pip list --not-required` |
| 检查版本冲突 | `pip check` 或 `pipdeptree --warn fail` |
| 导出当前环境版本快照 | `pip freeze` / `pip list --format=freeze` |
| 脚本里查依赖 | `importlib.metadata.requires()` |
| 升级前预演解析结果 | `pip install <pkg> --dry-run` |

## 五、小结

日常排查可以按这个顺序来：

1. 先用 `pip show` 做最快速的一级依赖确认；
2. 需要看全局关系或者排查"卸载/升级会不会影响别人"时，上 `pipdeptree`（尤其是 `--reverse`）；
3. 怀疑环境里已经有版本冲突，跑一次 `pip check` 或 `pipdeptree --warn fail` 确认；
4. 需要固化环境或者写自动化脚本，用 `pip freeze` / `importlib.metadata`。

pip 自带指令够用于轻量排查，一旦涉及"完整依赖树""反向查询""冲突检测"这类需求，`pipdeptree` 基本是标配，值得直接装上常备。
