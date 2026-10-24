# Ubuntu GRUB 出现 /home/xxx/test 异常启动项排查修复复盘

## 一、故障现象

Ubuntu 系统开机 GRUB 启动菜单异常，存在大量无效启动条目，不能正常进入系统，核心错误特征如下：

- GRUB 启动参数出现异常路径：`linux /home/xxx/test root=/dev/nvme0n1p2 ro quiet splash`
![1.1](./1.1.png)
![1.2](./1.2.png)

- 执行 `sudo update-grub` 时，莫名输出 `Found linux image: test`
![1.4](./1.4.png)

- 生成的 `/boot/grub/grub.cfg` 文件中，残留大量带 `/test` 的无效启动配置
![1.3](./1.3.png)

- 开机手动编辑 GRUB 启动项可临时进系统，重启后故障复现，无法根治
```text
# 手动编辑 search 后面内容是这样的：
linux ($root)/boot/vmlinuz root=/dev/nvme0n1p2 ro quiet splash $vt_handoff
initrd ($root)/boot/initrd.img
```

## 二、初期误判与排查踩坑

本次故障排查初期多次判断失误，走了大量弯路，汇总核心踩坑点：

### 1\. 误判为GRUB临时编辑错误

最初以为是开机GRUB界面手动按e编辑启动参数，残留了 `/test` 错误参数，但GRUB临时编辑仅单次生效，不会永久写入配置，排除该原因。

### 2\. 误判为 /etc/default/grub 配置异常

查看系统核心GRUB配置文件 `/etc/default/grub`，全文无 `test` 相关字符。核心误区：**该文件仅管理内核启动参数，不管理GRUB扫描内核、生成启动项的逻辑**，因此无法查到异常内容。

### 3\. 误判为Xen虚拟化脚本导致

排查发现系统预装了Xen虚拟化组件，默认存在 `/etc/grub.d/20_linux_xen` 脚本。该脚本缺失Xen主程序时，会生成占位启动项，初期判定为故障根源。

后续操作：卸载所有Xen相关包、禁用/删除 `20_linux_xen` 脚本后，**异常test启动项依旧存在**，彻底排除Xen为故障原因。

### 4\. 排查系统文件锁、配置缓存无效

依次排查：

- `grub.cfg` 文件不可变锁（chattr \-i）：无锁定

- `/boot` 目录无 test 内核文件

- GRUB自定义配置 `40_custom` 无异常条目

- BLS启动配置 `/boot/loader/entries/` 无异常配置

- 全局检索 `/etc/grub.d/` 所有脚本，无硬编码 `/home/xxx/test` 内容

## 三、最终真实根因（核心关键）

所有系统配置、GRUB脚本、系统文件均无异常，故障根源来自**Python全局环境干扰**：

用户在Python全局包目录 `/usr/local/lib/python3.12/dist-packages/` 中，手动放置了自定义文件：

- `zz.pth`：Python路径配置文件

- `zz_test.py`：自定义脚本，内部包含 `import test`模块引入逻辑

**故障触发原理**：

GRUB核心扫描脚本 `10_linux` 会全局遍历系统文件、匹配内核特征文件。Python全局环境中存在的 `test` 模块命名，干扰了系统文件扫描逻辑，被GRUB内核探测机制**误判为Linux内核镜像文件**。

因此出现诡异现象：系统中无 `/home/xxx/test` 实体文件，但GRUB依旧扫描出 `test` 镜像、自动生成无效启动条目。

本质：**通用命名test模块冲突 → GRUB文件扫描误识别 → 生成无效启动配置**

## 四、完整修复步骤

### 1\. 移除冲突的Python自定义文件

删除全局Python包目录下的自定义冲突文件，消除命名干扰：

```Plain Text
# 进入Python全局包目录
cd /usr/local/lib/python3.12/dist-packages/
# 删除冲突的pth文件和测试脚本
rm -f zz.pth zz_test.py
```


### 3\. 重新生成纯净GRUB配置

```Plain Text
# 备份当前 grub.cfg
sudo cp /boot/grub/grub.cfg /boot/grub/grub.cfg.bak
# 重新构建GRUB启动配置
sudo update-grub
# 或使用底层命令强制生成
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

### 4\. 验证修复结果

```Plain Text
# 检测是否还存在异常test条目
sudo grub-mkconfig | grep '/test'
sudo grep '/test' /boot/grub/grub.cfg
```

**修复标准**：两条命令均无任何输出，且 `update-grub` 不再打印 `Found linux image: test`，仅识别系统原生内核文件。

## 五、问题总结与避坑建议

### 1\. 核心总结

本次故障属于**跨环境隐性冲突BUG**，非常罕见：Python全局模块命名冲突，干扰了Linux系统GRUB的内核扫描机制，并非GRUB配置、系统文件损坏导致。常规排查思路无法定位，极易误导用户。

### 2\. 长期避坑规则

- **禁止使用通用关键字命名自定义模块**：`test、log、config、sys` 等通用名称，极易和系统、Python原生模块冲突

- **谨慎修改Python全局site\-packages目录**：自定义\.pth路径文件、全局脚本会影响全系统环境，引发各类隐性BUG，优先使用虚拟环境（venv）开发

- GRUB异常不一定是GRUB本身问题：系统全局环境、文件命名、第三方组件都可能干扰启动扫描逻辑

- 普通桌面Ubuntu **完全不需要Xen虚拟化组件**，预装后易产生冗余启动项，建议直接卸载
