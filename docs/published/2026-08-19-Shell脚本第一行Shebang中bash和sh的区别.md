# Shell 脚本第一行 Shebang 写 Bash 还是 sh？

写 Shell 脚本时，第一行经常是下面两种写法之一：

```bash
#!/bin/bash
```

或者：

```sh
#!/bin/sh
```

它们看起来只差一个单词，含义却不一样。简单来说：

- `#!/bin/bash` 表示明确使用 Bash 解释脚本，可以使用 Bash 的数组、`[[ ... ]]`、进程替换等扩展语法；
- `#!/bin/sh` 表示脚本按兼容 POSIX `sh` 的方式编写，语法限制更多，但通常更容易跨系统运行。

顺便说一下，这一行的正式名称通常写作 **Shebang**，也有人称它为 Hashbang。它来自开头的两个字符 `#!`：`#` 常读作 hash，`!` 常读作 bang。

## Shebang 到底做了什么

当我们把脚本当作可执行文件运行时：

```bash
chmod +x hello.sh
./hello.sh
```

操作系统会读取文件开头的 `#!`，并用后面的程序解释这个文件。例如：

```bash
#!/bin/bash
echo "Hello"
```

大致相当于执行：

```bash
/bin/bash ./hello.sh
```

Shebang 必须位于文件开头。前面不要加空行，也不要保存成带 BOM 的文本，否则有些系统无法正确识别它。

还要注意，Shebang 只在“直接执行脚本”时决定解释器。下面这些写法已经在命令中指定了解释器：

```bash
bash hello.sh
sh hello.sh
```

此时脚本第一行写什么都不会改变所用的解释器。即使文件第一行是 `#!/bin/bash`，执行 `sh hello.sh` 时仍然是由 `sh` 读取脚本，Bash 专有语法可能因此报错。

同理，使用点命令加载脚本时：

```sh
. ./hello.sh
```

脚本由当前 Shell 执行，Shebang 也不起决定作用。

## Bash 和 sh 不是同一个概念

`bash` 是一个具体的 Shell 程序，全称是 Bourne Again Shell。

`sh` 更像一种通用接口和基础脚本语言。现代系统中的 `/bin/sh` 不一定指向同一个程序。例如：

- Debian、Ubuntu 的 `/bin/sh` 通常指向 `dash`；
- Alpine Linux 通常使用 BusyBox `ash`；
- 有些发行版的 `/bin/sh` 会指向 `bash`。

可以在当前系统中查看它实际指向谁：

```bash
ls -l /bin/sh
readlink /bin/sh
```

因此，`#!/bin/sh` 的真正含义不是“使用一个叫 sh 的固定实现”，而是“使用系统提供的 sh，并且脚本应只依赖可移植的 sh 语法”。

Bash 能执行大部分普通的 sh 脚本，但反过来不成立：使用了 Bash 扩展的脚本，不能保证能被 `sh` 执行。

## 哪些写法在 Bash 中能用，在 sh 中不一定能用

下面是最常见的差异。

### 1. 数组

Bash 支持数组：

```bash
#!/bin/bash

names=(Alice Bob Charlie)
echo "${names[1]}"
```

POSIX `sh` 没有这种数组语法。用 Ubuntu 默认的 `sh` 执行时，通常会直接报语法错误。

### 2. `[[ ... ]]` 条件判断

Bash 脚本经常这样写：

```bash
if [[ $name == A* ]]; then
    echo "以 A 开头"
fi
```

`[[ ... ]]` 是 Bash、Ksh 等 Shell 提供的扩展，不是可移植的 POSIX `sh` 语法。兼容 `sh` 的写法可以使用 `case`：

```sh
case $name in
    A*) echo "以 A 开头" ;;
esac
```

普通字符串比较则可以使用单中括号：

```sh
if [ "$name" = "Alice" ]; then
    echo "名字是 Alice"
fi
```

### 3. 进程替换

Bash 可以使用进程替换：

```bash
diff <(sort file1.txt) <(sort file2.txt)
```

其中 `<(...)` 不是 POSIX `sh` 语法。可移植脚本一般需要改用临时文件、管道或其他方式组织命令。

### 4. 大括号展开

Bash 支持：

```bash
mkdir -p logs/{app,db,web}
echo {1..5}
```

POSIX `sh` 不要求支持大括号展开。兼容写法可以是：

```sh
mkdir -p logs/app logs/db logs/web
```

### 5. `source` 和 `.`

Bash 中常见：

```bash
source ./env.sh
```

`source` 不是 POSIX 标准命令。需要兼容 `sh` 时应写成：

```sh
. ./env.sh
```

### 6. `pipefail`

Bash 脚本经常在开头写：

```bash
set -euo pipefail
```

其中 `pipefail` 不是 POSIX `sh` 标准选项。某些 `sh` 实现支持它，另一些不支持，所以不能把它当作可移植语法。如果脚本确实依赖 `pipefail`，应明确使用 Bash，并写成更容易定位错误的形式：

```bash
#!/usr/bin/env bash
set -euo pipefail
```

## `#!/bin/bash` 和 `#!/usr/bin/env bash` 怎么选

Bash 脚本还经常使用：

```bash
#!/usr/bin/env bash
```

两者的区别是：

- `#!/bin/bash` 固定使用 `/bin/bash`；
- `#!/usr/bin/env bash` 根据当前 `PATH` 查找 `bash`。

在常见 Linux 系统中，Bash 通常位于 `/bin/bash`。对于需要可控解释器路径的系统脚本，这种写法直观、稳定。

`/usr/bin/env bash` 更适合需要在不同 Unix 系统、开发环境或自定义 Bash 安装路径之间运行的脚本。不过它会受到 `PATH` 的影响，实际找到的 Bash 版本可能不同。

因此不能简单地说哪一种永远更好，需要看运行环境是否固定。

## 为什么脚本写了 `#!/bin/sh`，在自己的机器上仍能运行 Bash 语法

一种常见情况是，本机的 `/bin/sh` 恰好指向 Bash，于是脚本暂时没有出错。换到 `/bin/sh` 指向 `dash` 或 BusyBox `ash` 的系统后，问题才暴露出来。

还有一种情况是，开发者一直这样执行脚本：

```bash
bash script.sh
```

这会直接使用 Bash，根本没有测试 `#!/bin/sh` 所声明的运行方式。

所以，“在 Bash 中运行成功”不能证明它是一个兼容 `sh` 的脚本。如果第一行写的是 `#!/bin/sh`，至少应这样测试：

```bash
sh -n script.sh
sh script.sh
```

还可以用 ShellCheck 指定目标 Shell 做静态检查：

```bash
shellcheck -s sh script.sh
```

`sh -n` 主要检查语法，并不会覆盖所有运行时兼容问题；真正可靠的做法仍是在目标系统或相同基础镜像中执行测试。

## 两个容易误判的问题

### 文件后缀不决定解释器

脚本叫 `deploy.sh`、`deploy.bash`，甚至完全没有后缀，都不会自动决定解释器。直接执行时，真正起作用的是文件第一行的 Shebang。

### Windows 换行符可能让 Shebang 失效

如果脚本使用 Windows 的 CRLF 换行，Linux 可能把解释器路径识别成 `/bin/bash\r`，报出类似错误：

```text
/bin/bash^M: bad interpreter: No such file or directory
```

可以先查看文件格式：

```bash
file script.sh
```

然后将换行符转换为 LF，例如：

```bash
dos2unix script.sh
```

## 实际应该怎么选

如果脚本使用数组、`[[ ... ]]`、进程替换、`pipefail` 等 Bash 功能，就明确写 Bash：

```bash
#!/usr/bin/env bash
```

如果脚本逻辑简单，希望它能在 Debian、Ubuntu、Alpine 以及各种精简容器中使用，可以只写 POSIX 兼容语法，并使用：

```sh
#!/bin/sh
```

最不推荐的是：第一行写 `#!/bin/sh`，正文却随意使用 Bash 专有语法。这种脚本可能在开发机上正常，进入 Docker 容器或换一台服务器后就失败。

一句话总结：**选择 `bash` 还是 `sh`，不是看哪个写法更短，而是看脚本实际使用了哪种语法，以及需要在哪些系统中运行。** 使用 Bash 功能就诚实地声明 Bash；追求可移植性，就使用 `sh` 并严格遵守 POSIX 语法。
