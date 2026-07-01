# Windows 如何配置 SSH Key，顺利下载 GitHub 项目

在 Windows 上下载 GitHub 项目，最常见的方式有两种：

- HTTPS：地址长得像 `https://github.com/user/repo.git`。
- SSH：地址长得像 `git@github.com:user/repo.git`。

如果你只是下载公开项目，HTTPS 通常最省事。但如果你要下载私有仓库、频繁 `git pull`、`git push`，或者不想每次都处理账号密码、token，SSH Key 会更顺手。

这篇文章只解决一个具体问题：Windows 电脑如何配置 SSH Key，让你可以通过 SSH 下载 GitHub 项目。

## 1. 先理解 SSH Key 是什么

SSH Key 可以理解成一对钥匙：

- 私钥：保存在你自己的电脑上，文件通常叫 `id_ed25519`，不能发给别人。
- 公钥：上传到 GitHub，文件通常叫 `id_ed25519.pub`，可以公开。

当你访问 GitHub 时，本机用私钥证明“我是这个 GitHub 账号的主人之一”。GitHub 只保存你的公钥，不需要知道你的私钥。

所以最重要的一条原则是：

> 永远不要把没有 `.pub` 后缀的私钥文件发给别人，也不要复制到聊天窗口、网页表单、代码仓库里。

## 2. 准备环境：确认 Git 和 SSH 命令可用

Windows 10、Windows 11 通常已经带有 OpenSSH Client。Git 命令一般需要安装 Git for Windows。

打开 PowerShell，执行：

```powershell
git --version
ssh -V
```

如果 `git --version` 能输出版本号，说明 Git 可用。如果提示找不到 `git`，先安装 Git for Windows：

```text
https://git-scm.com/download/win
```

如果 `ssh -V` 能输出 OpenSSH 版本号，说明 SSH 客户端可用。

后面的命令建议优先在 PowerShell 里执行。Git Bash 也能用，但 Windows 原生 OpenSSH 和 Git for Windows 自带的 SSH 有时会混用，导致 `ssh-agent` 里明明加了 key，Git 操作时仍然要求输入密码。后面会单独讲这个问题。

## 3. 检查电脑上是否已经有 SSH Key

先看当前用户目录下有没有 `.ssh` 文件夹和 key 文件：

```powershell
Get-ChildItem $env:USERPROFILE\.ssh
```

常见文件名包括：

```text
id_ed25519
id_ed25519.pub
id_rsa
id_rsa.pub
known_hosts
config
```

其中：

- `id_ed25519`：私钥。
- `id_ed25519.pub`：公钥。
- `id_rsa` / `id_rsa.pub`：较老但仍常见的 RSA key。
- `known_hosts`：记录你连接过的 SSH 主机指纹。
- `config`：SSH 客户端配置文件。

如果已经有 `id_ed25519.pub`，可以直接跳到“把公钥添加到 GitHub”。如果没有，就生成一对新的 key。

## 4. 生成新的 SSH Key

在 PowerShell 执行：

```powershell
ssh-keygen -t ed25519 -C "your_email@example.com"
```

把 `your_email@example.com` 换成你的 GitHub 邮箱。这个邮箱主要是标签，方便以后识别 key。

命令执行后会出现几个提示。

第一个提示是保存位置：

```text
Enter file in which to save the key (C:\Users\你的用户名/.ssh/id_ed25519):
```

如果你没有特殊需求，直接按 Enter，使用默认路径即可。

第二个提示是 passphrase：

```text
Enter passphrase (empty for no passphrase):
Enter same passphrase again:
```

passphrase 是给私钥再加一层密码。推荐设置一个你能记住的密码。这样即使私钥文件泄露，别人也不能直接使用它。

如果你只是本地学习，也可以直接按 Enter 留空，但从安全角度看，不建议长期使用无密码私钥。

生成完成后，你会得到两个文件：

```text
C:\Users\你的用户名\.ssh\id_ed25519
C:\Users\你的用户名\.ssh\id_ed25519.pub
```

再次强调：上传到 GitHub 的是 `.pub` 公钥，不是私钥。

## 5. 启动 Windows 的 ssh-agent

如果你的私钥设置了 passphrase，每次使用都输入会很麻烦。`ssh-agent` 的作用是帮你在当前 Windows 用户环境里托管私钥。

先用管理员权限打开 PowerShell。可以在开始菜单搜索 PowerShell，右键选择“以管理员身份运行”。

执行：

```powershell
Get-Service -Name ssh-agent | Set-Service -StartupType Automatic
Start-Service ssh-agent
Get-Service -Name ssh-agent
```

如果最后能看到 `Running`，说明服务已经启动。

然后打开一个普通 PowerShell 窗口（其实，也可以在之前的 PowerShell 窗口），不需要管理员权限，执行：

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

如果你生成 key 时设置了 passphrase，这里会要求输入一次。成功后，后续 Git 操作通常不需要反复输入。

可以用下面的命令确认 agent 里有哪些 key：

```powershell
ssh-add -l
```

## 6. 把公钥复制到剪贴板

在 PowerShell 中执行：

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | Set-Clipboard
```

这会把公钥内容复制到剪贴板。

也可以直接打印出来手动复制：

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

公钥通常是一整行，开头类似：

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... your_email@example.com
```

复制时不要多复制空格、换行，也不要漏掉开头的 `ssh-ed25519`。

## 7. 在 GitHub 添加 SSH Key

打开 GitHub 网页：

```text
https://github.com/settings/keys
```

按下面步骤操作：

1. 点击 `New SSH key`。
2. `Title` 写一个容易识别的名字，例如 `Windows Laptop`、`公司台式机`。
3. `Key type` 选择 `Authentication Key`。
4. `Key` 里粘贴刚才复制的公钥内容。
5. 点击 `Add SSH key`。

如果 GitHub 要求重新输入密码或二次验证，按页面提示完成即可。

## 8. 测试 SSH 是否配置成功

回到 PowerShell，执行：

```powershell
ssh -T git@github.com
```

第一次连接时，可能会看到类似提示：

```text
The authenticity of host 'github.com (...)' can't be established.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

这是 SSH 第一次认识 GitHub 主机时的确认提示。确认是连接 GitHub 后，输入：

```text
yes
```

如果配置成功，会看到类似：

```text
Hi your-username! You've successfully authenticated, but GitHub does not provide shell access.
```

这句话的意思是：身份验证成功，但 GitHub 不提供普通 shell 登录。对 Git 下载代码来说，这就是成功。

注意：这个测试命令返回码可能不是 0，不影响判断。重点看是否出现 `successfully authenticated` 和你的 GitHub 用户名。

## 9. 用 SSH 地址下载 GitHub 项目

打开 GitHub 项目页面，点击绿色 `Code` 按钮，选择 `SSH`，复制地址。SSH 地址通常长这样：

```text
git@github.com:owner/repo.git
```

然后在你想保存项目的目录执行：

```powershell
git clone git@github.com:owner/repo.git
```

例如：

```powershell
git clone git@github.com:octocat/Hello-World.git
```

如果你已经用 HTTPS 下载过项目，也可以把已有项目的远程地址改成 SSH。

进入项目目录：

```powershell
cd repo
```

查看当前远程地址：

```powershell
git remote -v
```

修改为 SSH：

```powershell
git remote set-url origin git@github.com:owner/repo.git
```

再确认一次：

```powershell
git remote -v
```

## 10. 常见问题

### 问题一：`Permission denied (publickey)`

这是最常见的错误：

```text
git@github.com: Permission denied (publickey).
fatal: Could not read from remote repository.
```

按顺序检查：

1. GitHub 是否添加了正确的 `.pub` 公钥。
2. 本机私钥是否存在：`Get-ChildItem $env:USERPROFILE\.ssh`。
3. 私钥是否已经加入 agent：`ssh-add -l`。
4. 测试命令是否成功：`ssh -T git@github.com`。
5. 仓库地址是否是 SSH 地址，而不是 HTTPS 地址：`git remote -v`。

如果 `ssh-add -l` 显示没有 key，重新执行：

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

### 问题二：PowerShell 里测试成功，Git Bash 里还是不行

Windows 上可能同时存在两套 SSH：

- Windows 自带的 OpenSSH：`C:\Windows\System32\OpenSSH\ssh.exe`
- Git for Windows 自带的 SSH：通常在 Git 安装目录下

如果你在 PowerShell 里把 key 加进了 Windows `ssh-agent`，但 Git 实际调用的是 Git for Windows 自带的 SSH，就可能读不到同一个 agent。

可以让 Git 明确使用 Windows 自带的 SSH：

```powershell
git config --global core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"
```

然后重新测试：

```powershell
ssh -T git@github.com
git ls-remote git@github.com:owner/repo.git
```

如果不想改全局配置，也可以统一使用 Git Bash 的 `ssh-agent` 和 `ssh-add`，但对新手来说，PowerShell 加 Windows OpenSSH 的路线更清晰。

### 问题三：提示 `Could not open a connection to your authentication agent`

通常是 `ssh-agent` 没启动。

用管理员 PowerShell 执行：

```powershell
Get-Service -Name ssh-agent | Set-Service -StartupType Automatic
Start-Service ssh-agent
```

再回到普通 PowerShell：

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

### 问题四：不小心把私钥传到了 GitHub 或发给别人

立刻作废这把 key：

1. 打开 `https://github.com/settings/keys`。
2. 删除对应的 SSH Key。
3. 在本机删除旧私钥和公钥。
4. 重新生成新的 SSH Key。
5. 把新的公钥添加到 GitHub。

私钥泄露后不要尝试“改名继续用”，应该直接换新。

### 问题五：公司网络连不上 SSH 22 端口

有些公司网络会屏蔽 SSH 默认的 22 端口。如果 HTTPS 能访问 GitHub，但 SSH 一直超时，可以尝试 GitHub 提供的 SSH over HTTPS port 配置。

在 `$env:USERPROFILE\.ssh\config` 文件里添加：

```sshconfig
Host github.com
  Hostname ssh.github.com
  Port 443
  User git
```

如果 `.ssh` 目录下没有 `config` 文件，可以手动创建一个没有后缀名的文本文件，文件名就是 `config`。

然后测试：

```powershell
ssh -T git@github.com
```

## 11. 推荐的一套完整命令

如果你是全新电脑，可以按下面顺序走一遍。

普通 PowerShell：

```powershell
git --version
ssh -V
ssh-keygen -t ed25519 -C "your_email@example.com"
```

管理员 PowerShell：

```powershell
Get-Service -Name ssh-agent | Set-Service -StartupType Automatic
Start-Service ssh-agent
```

普通 PowerShell：

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | Set-Clipboard
```

然后去 GitHub 添加公钥：

```text
https://github.com/settings/keys
```

最后测试并下载：

```powershell
ssh -T git@github.com
git clone git@github.com:owner/repo.git
```

如果 Git 操作仍然读不到 agent，再执行：

```powershell
git config --global core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"
```

## 12. 记住这几个关键点

- Windows 上建议优先用 PowerShell 配置 SSH Key，路径和服务更直观。
- 生成 key 用 `ssh-keygen -t ed25519 -C "你的 GitHub 邮箱"`。
- 上传到 GitHub 的是 `.pub` 公钥，私钥不能泄露。
- `ssh-agent` 用来托管私钥，减少反复输入 passphrase。
- `ssh -T git@github.com` 是最直接的连通性测试。
- 下载项目时要复制 SSH 地址，也就是 `git@github.com:owner/repo.git` 这种格式。
- 如果 PowerShell 成功但 Git 失败，检查 Git 是否用了另一套 SSH。

## 参考资料

- GitHub Docs: Generating a new SSH key and adding it to the ssh-agent  
  https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent
- GitHub Docs: Adding a new SSH key to your GitHub account  
  https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account
- GitHub Docs: Testing your SSH connection  
  https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection
- Microsoft Learn: Key-based authentication in OpenSSH for Windows  
  https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement
