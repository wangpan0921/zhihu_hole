# 一次训练进程退出段错误（SIGSEGV）的排查：matplotlib 静态 FreeType 惹的祸

## 背景与现象

一次训练任务的执行日志看起来一切正常：训练跑完，后处理也成功产出了结果。但进程在最后退出时崩了——

- 崩溃点在 Python 解释器 finalization（解释器收尾清理）阶段；
- 具体触发在 matplotlib 的 `PyFT2Font_dealloc`（FT2Font 对象析构）；
- 进程以 `SIGSEGV`（信号 11，退出码 -11）结束；
- 调度系统据此把这个任务标记为 **Failed**。

换句话说，业务逻辑其实已经全部成功，段错误纯粹发生在“退出打扫卫生”的阶段。但退出码非零，任务就被判失败了。

根据崩溃函数 `PyFT2Font_dealloc` + 发生在 finalization 阶段，可以先形成一个假设：这是 matplotlib 所使用的 FreeType 在对象析构时的一个已知类问题（use-after-free / double-free）。而 matplotlib 长期以来自带一个非常老的 FreeType（2.6.1，2015 年），很符合“老版本已知缺陷”的画像。

要验证这个假设，第一步得先搞清楚一个关键问题：**matplotlib 用的 FreeType，到底是它自己静态链接进去的，还是用的系统的动态库？** 这决定了后续该怎么修——是升级 matplotlib，还是换系统库。

---

## 核心方法：如何判断 matplotlib 用的是静态还是动态 FreeType

这是本文最值得记下来的部分。判断分三个层次，从“问 matplotlib 自己”到“看运行时真相”，逐层加强证据。

### 方法一：直接问 matplotlib（最快）

matplotlib 的 `ft2font` 扩展模块暴露了两个属性：

```python
import matplotlib.ft2font as m
print(m.__freetype_version__)      # FreeType 版本，例如 2.6.1
print(m.__freetype_build_type__)   # local 或 system
```

判断规则：

- `__freetype_build_type__ == "local"`：matplotlib 在构建时**自己下载并静态链接**了 FreeType；
- `__freetype_build_type__ == "system"`：使用了**系统的** FreeType 动态库。

在本次排查的环境里，输出是：

```
version: 2.6.1
build_type: local
```

即静态链接，版本 2.6.1。这和“老版本已知缺陷”的假设完全吻合。

### 方法二：看扩展模块链接了哪些动态库（ldd）

`ft2font` 是一个 C 扩展 `.so`。先定位它，再用 `ldd` 看它的动态依赖：

```bash
# 找到 ft2font 扩展文件
python -c "import matplotlib.ft2font as m; print(m.__file__)"
# 例如：/usr/local/lib/python3.10/dist-packages/matplotlib/ft2font.cpython-310-x86_64-linux-gnu.so

# 查看动态依赖
ldd $(python -c "import matplotlib.ft2font as m; print(m.__file__)")
```

判断规则：

- `ldd` 输出里**有** `libfreetype.so.x` → 动态链接了某个（通常是系统的）FreeType；
- `ldd` 输出里**没有** `libfreetype`，但 `import` 又正常工作 → FreeType 被静态嵌进了 `ft2font` 扩展本身。

本次环境的 `ldd` 输出只有基础库，没有任何 `libfreetype`：

```
libstdc++.so.6 => ...
libm.so.6 => ...
libgcc_s.so.1 => ...
libpthread.so.0 => ...
libc.so.6 => ...
/lib64/ld-linux-x86-64.so.2
```

没有独立的 freetype 依赖，进一步印证是静态链接。

### 方法三：看进程运行时到底加载了哪些库（最硬的证据）

前两种是“静态信息”。要拿到运行时的真相，可以在真正 `import` 之后读 `/proc/self/maps`，看进程实际映射了哪些库文件：

```python
import matplotlib.ft2font  # 触发加载
libs = sorted({l.split()[-1] for l in open('/proc/self/maps').read().splitlines()
               if l.split()[-1].startswith('/')})
print([p for p in libs if 'freetype' in p.lower()]
      or '（无，说明没有独立 freetype.so 被加载）')
```

本次结果为空——没有任何 `libfreetype.so` 被映射进进程。至此可以下定论：**FreeType 的机器码就嵌在 `ft2font*.so` 内部**，运行时不存在一个独立的 freetype 动态库。

### 一个容易踩的观察坑：nm 无输出但 strings 有输出

排查中有个现象值得解释：对 `ft2font*.so` 执行 `nm -a` 没有任何输出，但 `strings` 能搜到 freetype 相关字符串。

原因是：这个 `.so` 是 **release 构建、strip 过符号表**的，所以 `nm`（读符号表）为空；但静态链进去的 FreeType 代码里的**字符串常量**（版本号、错误信息等）仍在数据段里，所以 `strings` 能搜到。这恰恰是“代码被静态嵌入 + 符号被剥离”的典型表现，不矛盾。

要看残留的动态符号可以用 `nm -D`，要看代码段函数可以用 `objdump -d`。但就“静态还是系统”这个问题而言，方法一的 `build_type: local` 加方法二的 `ldd` 无 `libfreetype` 已经是决定性的了。

---

## 关于“静态链接”的一点澄清

有人会问：静态链接是不是把 FreeType 的代码直接打包进 matplotlib 的 wheel 了？如果不是，那“实际用的 freetype.so 路径”在哪？

答案是：

- 构建时 FreeType 先被编译成静态库 `libfreetype.a`，链接 `ft2font` 扩展时其目标代码被**合并进** `ft2font*.so`；
- wheel 里只有这个 `.so`，**没有独立的 freetype 文件**被打包，运行时也**没有独立的 freetype.so 被加载**；
- 所以“实际使用的 freetype.so 路径”这个问题本身不成立——它不以独立 `.so` 形式存在，就是 `ft2font*.so` 文件内部的那段代码。

作为对比，如果是 conda 或系统包管理器安装的 matplotlib，通常动态链接系统 FreeType，那时 `/proc/self/maps` 里就会出现类似 `/usr/lib/x86_64-linux-gnu/libfreetype.so.6` 的行，那才是可查的外部路径。

顺带一提，这种“自带私有依赖”的做法在 PyPI wheel 里很常见：同一个进程里 Pillow 用自带的 `pillow.libs/`（libjpeg、libtiff 等），numpy 用自带的 `numpy.libs/`（OpenBLAS 等），和 matplotlib 静态链接 FreeType 是同一类思路。

---

## 定位修复版本：升级 matplotlib 应该升到哪一版

既然 FreeType 是静态链接进 matplotlib 的，那么“换掉这个有缺陷的老 FreeType”最干净的做法就是**升级 matplotlib**——因为 FreeType 版本是跟着 matplotlib 版本走的。问题变成：升到哪一版才真正换掉了 2.6.1？

顺着 matplotlib 官方仓库查证：

- 更新 FreeType 的诉求由 issue **#20842**（“Please update freetype version”）追踪；
- 实际由 PR **#29816**（“Update FreeType to 2.13.3”）完成，其 **milestone 是 v3.11.0**；
- matplotlib **3.11.0** 起，bundled FreeType 从 2.6.1 升级到 **2.13.3**；
- 3.10.x 及更早（包括当时环境里的 3.6.2）自带的仍然是 2.6.1。

所以结论是：**要靠升级 matplotlib 解决，最低需要 3.11.0，建议直接用当时的稳定版 3.11.1。**

### 两个升级前必须注意的前提

**1. Python 版本门槛。** matplotlib 3.11 要求 `Requires-Python: >=3.11`。如果环境是 Python 3.10，直接 `pip install -U matplotlib` 并不会报错，而是**静默回退**去装最高的、仍兼容 3.10 的版本（即仍带 FreeType 2.6.1 的 3.10.x），于是“升了个寂寞”。要拿到修复，必须先把 Python 升到 3.11+。

顺便厘清这个约束写在哪里：它源自源码的 `pyproject.toml` 里 `[project]` 表的一行

```toml
[project]
requires-python = ">=3.11"
```

构建时这行被写进 wheel 的元数据 `Requires-Python`，pip 安装时读取它来决定能否安装。注意 `pyproject.toml` 是**构建期**文件，不会被打包进 wheel；在已安装环境里能看到的等价信息在 `matplotlib-<ver>.dist-info/METADATA` 的 `Requires-Python` 字段。这也解释了为什么在 `site-packages/matplotlib/` 里找不到 `pyproject.toml`。

**2. 升级会改变字体渲染。** PR #29816 明确指出，FreeType 2.6.1 → 2.13.3 会改变字形度量、kerning、hinting，导致渲染出现像素级变化（官方为此重新生成了大量基线测试图）。如果你的产物有图像像素级对比/校验，升级后需要相应更新基线。

---

## 不升 Python 时的规避手段

如果短期内不方便动 Python 版本，可以先用更轻量的方式兜住。关键认知是：**段错误发生在训练与后处理都成功之后的解释器退出清理阶段，业务结果其实已经产出**。因此可以设法绕开那次有问题的析构：

- 在进程真正退出前显式 `matplotlib.pyplot.close('all')`，尽早释放 FT2Font 对象，避免拖到 finalization 阶段析构；
- 在任务成功后用 `os._exit(0)` 直接退出，跳过 CPython 的 atexit / GC finalization 流程，从而绕过那次崩溃；
- 在任务包装层做结果判定：把“训练+后处理已成功、仅退出码为 -11”识别为成功，而非 Failed。

这些是规避，不是根治。根治仍然是升级到 3.11+ 换用 FreeType 2.13.3。

---

## 小结

- 现象：训练与后处理成功，但进程在解释器 finalization 阶段于 `PyFT2Font_dealloc` 触发 `SIGSEGV(-11)`，任务被判 Failed。
- 根因：matplotlib **静态链接**了老版本 FreeType **2.6.1**，其对象析构存在已知的 use-after-free / double-free 缺陷。
- 判断静态/动态 FreeType 的三板斧：
  1. `ft2font.__freetype_build_type__`（`local` = 静态自带，`system` = 系统动态）；
  2. `ldd ft2font*.so` 看有没有 `libfreetype`；
  3. `import` 后读 `/proc/self/maps` 看运行时是否真的加载了独立 freetype.so。
  （附带认知：`nm` 空 + `strings` 有，是 strip 过的静态链接的正常表现。）
- 解决：升级 matplotlib 到 **3.11.0+（建议 3.11.1）**，其 bundled FreeType 为 2.13.3；但需先满足 `requires-python >= 3.11`（源自 `pyproject.toml`，落地在 wheel 的 `METADATA`），并注意渲染像素级变化。
- 过渡：不便升 Python 时，可用 `close('all')` / `os._exit(0)` / 退出码重判等方式规避。
