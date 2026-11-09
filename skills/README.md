# 项目内置技能

本目录是 `zhihu_hole` 项目的技能唯一来源，包含：

- `add-weread-book`
- `excalidraw-lesson-images`
- `generate-kid-coding-video`
- `publish-wechat-album-to-zhihu`
- `pytorch-training-efficiency-course`

技能目录保留了 Codex 需要的 `agents/openai.yaml`，并且每个技能都有标准的 `SKILL.md`，因此可以被 Codex 和 Kiro 识别。

## 安装

在项目根目录运行：

```bash
bash scripts/install_project_skills.sh install --force
```

默认会复制到：

- Codex：`$CODEX_HOME/skills`，未设置 `CODEX_HOME` 时为 `~/.codex/skills`
- Kiro：项目内 `.kiro/skills`

只检查是否一致、不修改文件：

```bash
bash scripts/install_project_skills.sh check
```

如需让多个工作区共享同一份项目技能，可使用符号链接安装：

```bash
bash scripts/install_project_skills.sh install --force --link
```

安装器只处理上述五个同名技能，不会删除或覆盖其他技能。目标目录已有同名技能时必须显式传入 `--force`。
