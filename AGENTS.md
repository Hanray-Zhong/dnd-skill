# 项目协作约定

## AI 产物语言

所有 AI 生成或修改的产物均以简体中文作为标准语言，包括文档、Issue、规格说明、代码注释、提交说明和其他交付内容。本次创建的配置文档也遵循此规则。代码标识符、命令、API、协议名以及 GitHub triage 标签等必须保留原文的内容，可继续使用英文。

## Agent skills

### Issue tracker

本仓库的 Issue 和 PRD 使用 GitHub Issues 管理，并通过 `gh` CLI 操作。参见 `docs/agents/issue-tracker.md`。

### Triage labels

使用默认的 canonical triage labels：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human` 和 `wontfix`。参见 `docs/agents/triage-labels.md`。

### Domain docs

本仓库采用 single-context 布局，使用根目录 `CONTEXT.md` 和 `docs/adr/`。参见 `docs/agents/domain.md`。
