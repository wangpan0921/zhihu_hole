# `bash script.sh`、`. script.sh` 和 `./script.sh` 有什么区别？

在 Linux 和 macOS 终端中，执行 Shell 脚本时经常会看到三种写法：

```bash
bash script.sh
. script.sh
./script.sh
```

它们看起来只差几个字符，实际的执行方式却不同。最重要的区别是：脚本是否在当前终端的 Shell 中运行，以及脚本由谁来解释执行。

## `bash script.sh`：启动一个新的 Bash 执行脚本

```bash
bash script.sh
```

这条命令会启动一个新的 Bash 进程，再由这个 Bash 读取并执行 `script.sh`。

例如，创建脚本：

```bash
#!/bin/bash

cd /tmp
export MY_NAME="Tom"
echo "脚本中的目录：$(pwd)"
echo "脚本中的 MY_NAME：$MY_NAME"
```

执行：

```bash
bash script.sh
```

脚本内部会进入 `/tmp`，也能读到 `MY_NAME=Tom`。不过脚本结束后，新的 Bash 进程随之结束，当前终端不会保留这些修改：

```bash
pwd
echo "$MY_NAME"
```

当前目录仍是原来的目录，`MY_NAME` 通常也是空的。

这种方式有两个常见特点：

- 不要求 `script.sh` 具有可执行权限；
- 不依赖脚本第一行的 Shebang，命令已经明确指定使用 Bash。

因此，即使脚本没有 `#!/bin/bash`，下面的命令依然会让 Bash 尝试执行它：

```bash
bash script.sh
```

这也是运行 Bash 脚本时最直接、最容易理解的方式。

## `. script.sh`：在当前 Shell 中加载并执行

```bash
. script.sh
```

点号 `.` 是 Shell 内置命令，等价于：

```bash
source script.sh
```

它不会创建新的 Shell 进程，而是把脚本内容直接交给当前 Shell 执行。因此，脚本对变量、函数、环境变量和工作目录的修改都会保留在当前终端。

继续执行刚才的脚本：

```bash
. script.sh
```

再检查当前终端：

```bash
pwd
echo "$MY_NAME"
```

结果会是：

```text
/tmp
Tom
```

因为 `cd /tmp` 和 `export MY_NAME="Tom"` 都直接作用于当前 Shell。

这种写法最适合加载开发环境配置，例如：

```bash
. ./env.sh
```

其中 `env.sh` 可以包含：

```bash
export DATABASE_URL="postgres://localhost/app"
export APP_ENV="development"
```

加载后，当前终端后续启动的程序都能使用这些环境变量。

不过，使用 `.` 时需要格外谨慎。脚本中的以下操作都会影响当前会话：

```bash
cd /tmp
unset PATH
exit
```

特别是 `exit`，它可能直接退出当前终端的 Shell，而不是只结束脚本。

另一个容易忽略的点是，脚本要兼容当前 Shell 的语法。`. script.sh` 用的是当前 Shell，而不是脚本 Shebang 指定的解释器。比如你当前处在 `sh` 中，却加载了使用 Bash 数组或 `[[ ... ]]` 的脚本，就可能出现语法错误。

## `./script.sh`：把脚本当作可执行文件运行

```bash
./script.sh
```

这里的 `./` 表示“当前目录”。这条命令会把 `script.sh` 当成一个可执行文件交给操作系统运行。

要这样执行，脚本通常需要满足两个条件。

第一，脚本要有可执行权限：

```bash
chmod +x script.sh
```

第二，脚本应在第一行声明解释器，也就是 Shebang：

```bash
#!/usr/bin/env bash
```

或：

```bash
#!/bin/bash
```

Shebang 告诉操作系统应该用哪个程序执行该文件。它并不一定是 Bash，例如：

```python
#!/usr/bin/env python3
```

是 Python 脚本的常见写法。

因此，`./script.sh` 的解释器取决于文件第一行，而不是文件扩展名。对于一个正常的 Bash 脚本，`./script.sh` 通常会启动一个新的 Bash 进程，所以它对当前终端环境的影响，与 `bash script.sh` 基本相同：脚本中的 `cd` 和变量赋值不会在脚本结束后留下来。

## 为什么不是直接输入 `script.sh`？

很多系统默认不会把当前目录加入 `PATH`。因此直接执行：

```bash
script.sh
```

Shell 会在 `PATH` 中查找名为 `script.sh` 的命令，通常找不到。

而：

```bash
./script.sh
```

明确告诉 Shell：执行当前目录中的这个文件。这也避免了误执行 `PATH` 中同名命令的风险。

## 三种写法的对比

| 写法 | 是否新建进程 | 是否影响当前 Shell | 是否需要可执行权限 | 解释器来源 |
| --- | --- | --- | --- | --- |
| `bash script.sh` | 是 | 否 | 否 | 命令明确指定 Bash |
| `. script.sh` | 否 | 是 | 否 | 当前 Shell |
| `./script.sh` | 通常是 | 否 | 是 | 文件第一行的 Shebang |

## 该怎么选？

只是运行一个 Bash 脚本，可以使用：

```bash
bash script.sh
```

需要让脚本修改当前终端的环境变量、函数或工作目录，应使用：

```bash
. ./script.sh
```

希望脚本像普通命令一样可直接执行，并让脚本自行声明解释器，则使用：

```bash
chmod +x script.sh
./script.sh
```

一句话总结：`bash script.sh` 是“另开一个 Bash 来执行”，`. script.sh` 是“在当前 Shell 中执行”，`./script.sh` 是“按脚本自身声明的解释器执行”。理解是否会影响当前终端环境，基本就能正确选择写法。
