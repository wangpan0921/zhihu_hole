# Git Worktree 基本用法：一个仓库同时开发多个功能

平时使用 Git 时，我们通常在一个工作目录里来回切分支。这个方式简单，但遇到并行任务时会很麻烦：一个功能做到一半，突然要修线上 bug；或者你需要同时开发两个功能分支，又不想反复 `stash`、切分支、恢复现场。

`git worktree` 就是用来解决这类问题的。它允许同一个 Git 仓库拥有多个工作目录，每个目录可以检出不同分支，但底层共享同一份 Git 对象数据。相比重新 clone 一份仓库，`worktree` 更快，也更省磁盘空间。

## 适合什么场景

`git worktree` 最常见的使用场景包括：

- 同时开发多个功能，比如一个目录开发登录功能，另一个目录开发支付功能。
- 当前功能还没做完，但需要马上切出去修线上 bug。
- 想在另一个分支跑测试、看代码或做实验，不影响当前工作区。
- 长期保留一个主干目录，用来随时验证 `main` 或 `master` 的最新状态。

举个例子，你可以把同一个项目组织成这样：

```text
project/          -> main
project-login/    -> feature-login
project-payment/  -> feature-payment
project-hotfix/   -> hotfix-order
```

每个目录都是独立的工作区，但它们属于同一个 Git 仓库体系。这样就不用在一个目录里反复切分支，也不用为了并行开发重复 clone 项目。

## 查看当前 Worktree

在仓库目录中执行：

```bash
git worktree list
```

示例输出：

```text
/path/project       abc1234 [main]
/path/project-login def5678 [feature-login]
```

这表示当前仓库有两个工作目录：`project` 检出了 `main` 分支，`project-login` 检出了 `feature-login` 分支。

## 为已有分支创建新工作目录

假设你当前在 `main` 分支，但想继续开发已有分支 `feature-login`，可以执行：

```bash
git worktree add ../project-login feature-login
```

这个命令会创建一个新目录 `../project-login`，并在里面检出 `feature-login` 分支。

之后你可以这样工作：

```bash
cd ../project-login
# 在 feature-login 分支继续开发
```

原来的 `project` 目录仍然保持在 `main` 分支，不会受到影响。

## 创建新分支并创建 Worktree

如果要从 `main` 新开一个功能分支，可以使用 `-b`：

```bash
git worktree add -b feature-payment ../project-payment main
```

这个命令做了两件事：

1. 基于 `main` 创建新分支 `feature-payment`。
2. 创建 `../project-payment` 目录，并在里面检出这个新分支。

这样你就可以在 `project-payment` 目录里开发支付功能，同时保留原目录的状态。

## 场景示例：同时开发多个功能

假设你正在做两个互不相关的需求：登录改版和支付流程优化。传统方式下，你可能需要在一个目录里频繁切换：

```bash
git switch feature-login
# 开发登录功能

git switch feature-payment
# 开发支付功能
```

如果其中一个分支有未提交改动，切换时就可能被 Git 阻止，或者你需要先 `stash`。时间久了，现场会变得很乱。

使用 `git worktree` 后，可以这样组织：

```bash
git worktree add -b feature-login ../project-login main
git worktree add -b feature-payment ../project-payment main
```

然后分别进入不同目录开发：

```bash
cd ../project-login
# 开发登录功能

cd ../project-payment
# 开发支付功能
```

两个功能互不影响。登录功能目录里的未提交改动，不会出现在支付功能目录里；支付功能目录里的依赖安装、构建产物和临时代码，也不会干扰登录功能。

## 场景示例：临时处理线上 Bug

这是 `git worktree` 非常实用的场景。

假设你正在 `feature-login` 分支开发，代码还没提交，突然需要从 `main` 拉一个 `hotfix` 修线上问题。如果直接切分支，可能会遇到未提交改动冲突。

这时可以直接创建一个新的 hotfix 工作目录：

```bash
git worktree add -b hotfix-order ../project-hotfix main
cd ../project-hotfix
```

然后在新目录里修复问题、提交、推送：

```bash
git add .
git commit -m "fix: correct order status display"
git push origin hotfix-order
```

修完后，删除这个临时工作目录即可：

```bash
git worktree remove ../project-hotfix
```

而你原来 `feature-login` 目录里的开发现场完整保留，不需要 `stash`，也不需要反复恢复上下文。

## 删除不再需要的 Worktree

当某个功能分支已经合并，不再需要对应目录时，可以执行：

```bash
git worktree remove ../project-payment
```

如果你已经手动删除了目录，Git 里可能还残留 worktree 记录，可以清理一下：

```bash
git worktree prune
```

## 常用命令速查

```bash
# 查看所有 worktree
git worktree list

# 为已有分支创建工作目录
git worktree add ../project-login feature-login

# 创建新分支并创建工作目录
git worktree add -b feature-payment ../project-payment main

# 删除 worktree
git worktree remove ../project-payment

# 清理失效的 worktree 记录
git worktree prune
```

## 使用时的注意点

同一个分支默认不能同时被两个 worktree 检出。比如 `main` 已经在 `project/` 目录使用，就不能再直接在另一个 worktree 里检出同一个 `main` 分支。通常的做法是为每个 worktree 使用不同分支。

另外，多个 worktree 共享同一个仓库的 Git 数据，但工作区文件彼此独立。一个目录里的未提交修改不会出现在另一个目录里；提交记录、分支、远程配置等仍然属于同一个仓库体系。

还有一点要注意：删除 worktree 时，优先使用 `git worktree remove`，不要直接 `rm -rf`。这样 Git 能正确更新自己的 worktree 记录。

## 总结

`git worktree` 的核心价值是：不用反复切分支，也不用重复 clone 仓库，就能让多个开发任务并行存在。

当你需要同时开发多个功能、临时修复线上 bug、验证主干代码，或者保留多个分支环境时，`git worktree` 会比传统的“stash 后切分支”更清晰、更稳定，也更高效。
