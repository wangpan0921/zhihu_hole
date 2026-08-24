# VS Code Remote SSH 总要重新输密码？Windows 连接 Ubuntu 的完整解决方法

家里的 Windows 笔记本使用 VS Code Remote - SSH 连接公司 Ubuntu 电脑时，可能会遇到这种情况：电脑息屏或网络短暂波动后连接断开，重新连接又要输入 Ubuntu 密码。

这个问题包含两部分：

- Windows 或 Ubuntu 进入睡眠，网络连接随之中断。
- SSH 使用账户密码认证，所以每次重连都要重新输入密码。

完整解决办法是：让两台电脑只关闭屏幕、不进入睡眠；把 SSH 改为密钥认证；再让 Windows 的 `ssh-agent` 在当天保管已解锁的私钥。完成后，每天最多输入一次私钥口令，VS Code 后续重连不再要求 Ubuntu 账户密码。

## 一、准备信息

开始前需要准备：

- 公司 Ubuntu 电脑的 IP 地址或域名。
- Ubuntu 登录用户名。
- 连接公司网络所需的 VPN。
- 当前已经可以通过密码连接 Ubuntu。

本文使用 `company-ubuntu` 作为 SSH 连接别名。实际操作时，请替换用户名和服务器地址。

## 二、在 Windows 生成 SSH Key

打开 PowerShell，确认 Windows 自带的 SSH 客户端可用：

```powershell
ssh -V
```

生成 Ed25519 密钥：

```powershell
ssh-keygen -t ed25519 -C "windows-vscode"
```

询问保存位置时直接按 Enter，使用默认路径：

```text
C:\Users\你的Windows用户名\.ssh\id_ed25519
```

建议设置一个私钥口令。它用于保护 Windows 上的私钥，并不是 Ubuntu 的账户密码。

生成后会得到两个文件：

```text
id_ed25519       私钥，只能保存在自己的电脑上
id_ed25519.pub   公钥，可以安装到 Ubuntu
```

不要把没有 `.pub` 后缀的私钥发送给别人或提交到代码仓库。

查看并复制公钥：

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

复制以 `ssh-ed25519` 开头的完整一行。

## 三、把公钥安装到 Ubuntu

先按原来的方式连接公司 Ubuntu，这一步仍需输入一次 Ubuntu 密码：

```powershell
ssh Ubuntu用户名@公司电脑IP
```

在 Ubuntu 终端执行：

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
```

把公钥粘贴到文件末尾。每个公钥必须单独占一行，不要拆行，也不要删除已有公钥。

在 nano 中按 Ctrl + O，按 Enter 保存，再按 Ctrl + X` 退出。然后设置权限：

```bash
chmod 600 ~/.ssh/authorized_keys
```

暂时保留这个已登录终端，以便新连接测试失败时回来检查。

## 四、验证密钥登录

另开一个 Windows PowerShell，执行：

```powershell
ssh Ubuntu用户名@公司电脑IP
```

正确配置后，SSH 不会再询问 Ubuntu 账户密码。如果密钥设置了口令，此时可能会要求输入私钥口令。

如果仍要求 Ubuntu 密码，可以查看认证日志：

```powershell
ssh -v Ubuntu用户名@公司电脑IP
```

重点查找 `Offering public key` 和 `Server accepts key`。

## 五、启用 Windows ssh-agent

以管理员身份打开 PowerShell，执行：

```powershell
Set-Service ssh-agent -StartupType Automatic
Start-Service ssh-agent
Get-Service ssh-agent
```

最后一条命令显示 `Running`，说明服务已经启动。

在普通 PowerShell 中把私钥加入代理：

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

输入一次私钥口令，然后检查：

```powershell
ssh-add -l
```

只要 Windows 没有重启，VS Code 后续连接和重连通常都不需要再次输入口令。第二天开机后重新执行一次 `ssh-add` 即可。

## 六、配置 SSH 别名和保活

打开 Windows 的 SSH 配置文件：

```powershell
notepad $env:USERPROFILE\.ssh\config
```

加入以下内容：

```sshconfig
Host company-ubuntu
    HostName 公司电脑IP或域名
    User Ubuntu用户名
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    AddKeysToAgent yes
    ServerAliveInterval 60
    ServerAliveCountMax 120
    TCPKeepAlive yes
```

其中：

- `IdentityFile` 指定要使用的私钥。
- `IdentitiesOnly yes` 避免尝试无关密钥。
- `ServerAliveInterval 60` 每 60 秒发送一次保活消息。
- `ServerAliveCountMax 120` 允许较长时间无响应后再判定断线。

保存后测试：

```powershell
ssh company-ubuntu
```

测试成功后，在 VS Code 中按 Ctrl + Shift + P`，选择：

```text
Remote-SSH: Connect to Host...
company-ubuntu
```

以后都通过 `company-ubuntu` 连接。

## 七、设置 Windows 关闭屏幕但不睡眠

SSH 保活无法让已经睡眠的电脑继续联网。在 Windows 11 中打开：

```text
设置 -> 系统 -> 电源和电池 -> 屏幕、睡眠和休眠超时
```

接通电源时建议设置为：

```text
关闭屏幕：10 分钟
进入睡眠：从不
```

也可以在管理员 PowerShell 中执行：

```powershell
powercfg /change monitor-timeout-ac 10
powercfg /change standby-timeout-ac 0
```

如果合上笔记本盖子后仍需保持连接，进入：

```text
控制面板 -> 硬件和声音 -> 电源选项 -> 选择关闭笔记本计算机盖的功能
```

把“接通电源时”的“关闭盖子时”设置为“不采取任何操作”。合盖运行时不要把电脑放入包中，以免散热不良。

不建议把使用电池时也设置为永不睡眠，否则容易耗尽电量。

## 八、确认 Ubuntu 不会自动挂起

公司 Ubuntu 如果进入挂起，网卡也会停止工作。打开：

```text
设置 -> 电源 -> 自动挂起
```

关闭接通电源时的自动挂起。普通锁屏不会中断 SSH，真正影响连接的是睡眠、挂起、关机和网络断开。

如果这些项目由公司统一管理，不要绕过安全策略，应联系 IT 管理员确认。

## 九、常见问题

### 配置公钥后仍要求 Ubuntu 密码

在 Ubuntu 检查权限：

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

确认公钥是完整的一行，并位于实际登录用户的 `~/.ssh/authorized_keys`。

### PowerShell 能免密登录，但 VS Code 仍提示密码

确认 VS Code 连接的是 `company-ubuntu`。在 VS Code 设置中搜索 `Remote.SSH: Path`，必要时指定 Windows 自带的 SSH：

```text
C:\Windows\System32\OpenSSH\ssh.exe
```

### 每次仍提示私钥口令

检查代理状态：

```powershell
Get-Service ssh-agent
ssh-add -l
```

服务应为 `Running`，`ssh-add -l` 应显示刚添加的 Ed25519 密钥。

### 息屏后仍然断开

息屏本身不会断开 SSH，需要检查：

- Windows 是否实际进入睡眠。
- Ubuntu 是否自动挂起。
- VPN 是否在锁屏后自动断开。
- 公司网络是否设置了强制空闲超时。

如果 VPN 或公司安全策略要求定时重新认证，SSH Key 和保活配置不能绕过该要求。

## 十、每天如何使用

每天启动 Windows 后，先连接公司 VPN，然后执行：

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

输入一次私钥口令，再通过 VS Code Remote Explorer 连接 `company-ubuntu`。当天即使因为短暂网络波动发生重连，也不需要再次输入 Ubuntu 账户密码。

最终效果是：屏幕可以按时关闭，但 Windows 和 Ubuntu 均不睡眠；SSH 使用公钥认证；Windows `ssh-agent` 每天只解锁一次私钥；SSH keepalive 减少空闲连接被网络设备清理的概率。