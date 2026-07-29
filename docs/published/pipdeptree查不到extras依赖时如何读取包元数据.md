# pipdeptree 查不到 extras 依赖时，应该去读包元数据

上一篇《查询 pip 包依赖关系的常见指令及使用场景》里，主要讲的是：一个 Python 环境已经装好了，想知道某个包依赖谁、谁又依赖它，可以用 `pip show`、`pipdeptree`、`pip check` 这些工具。

但这里还有一个容易漏掉的场景：

> 如果一个包支持 `pip install "pkg[extra]"` 这种安装方式，想知道某个 extra 到底会额外安装哪些依赖，光看 `pipdeptree` 往往是不够的。

原因很简单：`pipdeptree` 擅长展示“当前环境里已经安装出来的依赖树”，而 extras 本质上是包元数据里的“可选依赖声明”。安装完成以后，pip 不会把“这个环境当时是用 `pkg[dev]` 还是 `pkg[all]` 安装的”作为一条清晰的历史记录留给你。extra 拉进来的包，最后也只是普通的已安装包。

所以要回答“这个 extra 包含哪些依赖”，更可靠的办法是读取包的元数据。

## 一、为什么 pipdeptree 看不全 extras

先用一个常见写法举例：

```bash
pip install "somepkg[postgres]"
```

这里的 `postgres` 就是一个 extra。包作者可能在 `pyproject.toml` 里这样声明：

```toml
[project.optional-dependencies]
postgres = [
  "psycopg[binary]>=3",
]
dev = [
  "pytest",
  "ruff",
]
```

当你安装 `somepkg[postgres]` 时，pip 会把核心依赖和 `postgres` 这组可选依赖一起解析、安装。

但安装完成以后，环境里看到的是：

- `somepkg` 已安装；
- `psycopg` 已安装；
- 其他依赖也已安装。

你很难只靠依赖树判断：

- `psycopg` 是不是因为 `somepkg[postgres]` 被装进来的；
- `somepkg` 还支持哪些没安装的 extra；
- `dev`、`docs`、`all` 这些 extra 分别对应哪些可选依赖。

这就是 `pipdeptree` 的边界。它解决的是“已安装依赖关系”，不是“包声明过哪些可选依赖组”。

## 二、extras 藏在哪里

Python 包安装以后，环境里会有一个元数据目录，通常长这样：

```text
site-packages/
  somepkg-1.2.3.dist-info/
    METADATA
```

`METADATA` 文件里会有两类和 extras 相关的信息：

```text
Provides-Extra: postgres
Provides-Extra: dev
Requires-Dist: psycopg[binary]>=3; extra == "postgres"
Requires-Dist: pytest; extra == "dev"
Requires-Dist: ruff; extra == "dev"
```

重点是：

- `Provides-Extra` 表示这个包声明了哪些 extra 名字；
- `Requires-Dist` 表示这个包声明的依赖；
- 带有 `extra == "xxx"` marker 的 `Requires-Dist`，就是某个 extra 对应的可选依赖。

也就是说，如果要查 `somepkg[postgres]` 到底代表什么，要看的不是依赖树，而是这个包的 `METADATA`。

## 三、用 importlib.metadata 读取 extras

Python 3.8+ 可以直接用标准库 `importlib.metadata` 读取已安装包的元数据。

先看一个最小命令：

```bash
python - <<'PY'
from importlib.metadata import metadata

dist = metadata("somepkg")

print("extras:")
for item in dist.get_all("Provides-Extra") or []:
    print(" -", item)

print("\nrequires:")
for item in dist.get_all("Requires-Dist") or []:
    print(" -", item)
PY
```

把 `somepkg` 换成你要查的包名即可。

输出里如果看到类似：

```text
Requires-Dist: psycopg[binary]>=3; extra == "postgres"
```

就说明 `postgres` 这个 extra 会引入 `psycopg[binary]>=3`。

不过原始输出通常比较长，想看得清楚一点，可以用 `packaging` 做一次解析。如果当前环境没有这个库，先装一下：

```bash
python -m pip install packaging
```

## 四、按 extra 分组打印可选依赖

下面这个脚本更适合日常排查：输入包名，直接按 extra 分组打印依赖。

```bash
python - <<'PY'
from collections import defaultdict
from importlib.metadata import metadata
from packaging.requirements import Requirement

package = "somepkg"
dist = metadata(package)

groups = defaultdict(list)
normal_requires = []

for raw in dist.get_all("Requires-Dist") or []:
    req = Requirement(raw)
    matched_extras = [
        extra
        for extra in dist.get_all("Provides-Extra") or []
        if req.marker and "extra" in str(req.marker) and req.marker.evaluate({"extra": extra})
    ]

    if matched_extras:
        for extra in matched_extras:
            groups[extra].append(raw)
    else:
        normal_requires.append(raw)

print(f"# {package}")

print("\n## normal dependencies")
for item in normal_requires:
    print("-", item)

print("\n## optional dependencies")
for extra, items in sorted(groups.items()):
    print(f"\n[{extra}]")
    for item in items:
        print("-", item)
PY
```

如果你想查的是 `ray`、`fastapi`、`pandas`、`httpx` 这类常见包，把：

```python
package = "somepkg"
```

改成对应包名即可。

需要注意：这个脚本读取的是“当前环境里已安装版本”的元数据。不同版本的包，extras 内容可能不一样，所以排查时最好先确认版本：

```bash
python -m pip show somepkg
```

或者：

```bash
python - <<'PY'
from importlib.metadata import version
print(version("somepkg"))
PY
```

## 五、直接打开 METADATA 文件也可以

如果你不想写脚本，也可以直接找到元数据文件。

先定位包安装位置：

```bash
python - <<'PY'
from importlib.metadata import distribution

dist = distribution("somepkg")
print(dist.locate_file(""))
for file in dist.files or []:
    if str(file).endswith(".dist-info/METADATA"):
        print(dist.locate_file(file))
PY
```

然后打开 `METADATA`，搜索：

```text
Provides-Extra
Requires-Dist
extra ==
```

这种方式最原始，但也最直观。尤其是在排查“为什么文档里说装 `pkg[xxx]`，但我不知道它到底多装了什么”的时候，看 `METADATA` 基本不会绕路。

## 六、源码里也能查，但要注意构建方式

如果包还没安装，只拿到了源码，可以看这些位置：

```text
pyproject.toml
setup.py
setup.cfg
```

现代项目通常在 `pyproject.toml` 里写：

```toml
[project.optional-dependencies]
docs = ["sphinx", "myst-parser"]
test = ["pytest", "pytest-cov"]
```

老项目可能在 `setup.py` 里写：

```python
setup(
    ...
    extras_require={
        "docs": ["sphinx", "myst-parser"],
        "test": ["pytest", "pytest-cov"],
    },
)
```

源码里的定义适合用来了解“项目作者怎么声明 extras”。但如果项目使用动态构建逻辑，最终安装出来的 `METADATA` 才是 pip 真正消费的结果。所以排查当前环境时，我更建议优先看已安装包的元数据。

## 七、反过来查：某个包是被谁依赖的

还有一种常见排查场景是：环境里已经出现了某个包，比如 `gymnasium`，想知道它是被谁依赖进来的。

普通依赖可以先用这两个命令：

```bash
python -m pip show gymnasium
```

看输出里的 `Required-by` 字段。或者用 `pipdeptree` 反向查：

```bash
pipdeptree -r -p gymnasium -w silence
```

这两个方式查的是“当前已安装环境里，哪些包把 `gymnasium` 当作依赖”。如果能看到上游包名，问题通常就解决了。

但如果这里没有结果，并不一定说明 `gymnasium` 不是被别的包带进来的。它可能来自某个 extra 的条件依赖，例如你安装过：

```bash
pip install "ray[all]==2.40.0"
```

这时更适合扫描当前环境里所有包的 `Requires-Dist`，看谁的元数据声明过 `gymnasium`：

```bash
python - <<'PY'
from importlib.metadata import distributions
from packaging.requirements import Requirement

target = "gymnasium"

for dist in distributions():
    name = dist.metadata["Name"]
    version = dist.version

    for raw in dist.metadata.get_all("Requires-Dist") or []:
        try:
            req = Requirement(raw)
        except Exception:
            continue

        if req.name.lower() == target.lower():
            print(f"{name}=={version}")
            print(f"  {raw}")
PY
```

如果输出类似：

```text
ray==2.40.0
  gymnasium==... ; extra == "rllib"
```

就说明 `ray` 的某个 extra 声明过 `gymnasium`。这和 `pipdeptree -r -p gymnasium` 查不到并不矛盾：前者是在读包元数据里的条件依赖声明，后者主要是在看当前环境已经展开出来的依赖树。

不过要注意一个边界：pip 安装完成后，通常不会保存“这个包当初到底是被谁拉进来的”这种安装历史。上面的办法能回答的是“当前哪些已安装包声明依赖它”；如果想重现一次安装解析过程，更适合用：

```bash
python -m pip install --dry-run --report report.json "ray[all]==2.40.0"
```

然后在 `report.json` 里搜索目标包名。

## 八、什么时候用 pipdeptree，什么时候读元数据

可以用这个规则区分：

| 问题 | 推荐方式 |
|---|---|
| 当前环境里某个包实际依赖了谁 | `pipdeptree -p <pkg>` |
| 当前环境里谁依赖了某个包 | `pipdeptree -r -p <pkg>` |
| 反向依赖查不到，但怀疑来自 extras | 扫描所有包的 `Requires-Dist` |
| 当前环境是否有版本冲突 | `pip check` / `pipdeptree --warn fail` |
| 某个包声明了哪些 extras | 读 `METADATA` 的 `Provides-Extra` |
| 某个 extra 会额外安装哪些依赖 | 读 `METADATA` 的 `Requires-Dist` + `extra == "xxx"` |
| 想确认源码里 extras 怎么定义 | 看 `pyproject.toml` / `setup.py` / `setup.cfg` |

一句话总结：

> `pipdeptree` 看的是装出来的树；extras 要看包声明的元数据。

这两个视角不冲突，只是解决的问题不同。排查普通依赖关系时，`pipdeptree` 很高效；一旦问题变成“`pkg[all]`、`pkg[dev]`、`pkg[postgres]` 这些 extra 到底包含什么”，就应该切换到 `METADATA` / `importlib.metadata` 这一层。
