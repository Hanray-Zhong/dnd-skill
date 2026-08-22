# 项目协作约定

## AI 产物语言

所有 AI 生成或修改的产物均以简体中文作为标准语言，包括文档、Issue、规格说明、代码注释、提交说明和其他交付内容。本次创建的配置文档也遵循此规则。代码标识符、命令、API、协议名以及 GitHub triage 标签等必须保留原文的内容，可继续使用英文。

## Agent skills

### Issue tracker

本仓库的 Issue 和 PRD 使用 GitHub Issues 管理，并通过 `gh` CLI 操作。参见 `docs/agents/issue-tracker.md`。

### GitHub CLI 认证诊断

Codex 的受限执行环境可能无法访问 macOS Keychain 或 GitHub 网络端点。此时沙箱内的
`gh auth status` 可能把验证失败概括为 `The token in default is invalid`，该输出本身不足以证明
令牌已被吊销或过期。

遇到该提示时按以下顺序处理：

1. 不读取或输出令牌，不运行 `gh auth token`，也不打印 `GH_TOKEN`、`GITHUB_TOKEN` 等环境变量的值；
   如需排除覆盖，只检查变量名是否存在。
2. 使用需要审批的沙箱外执行重新运行只读的 `gh auth status`，让命令能够访问 Keychain 和网络。
3. 如果沙箱外结果显示已通过 keyring 登录，则视为认证有效；后续 `gh issue`、`gh pr` 等操作使用同样的
   沙箱外执行，不要求用户重新登录。
4. 只有沙箱外检查仍明确失败时，才让用户在自己的终端运行 `gh auth login -h github.com`；不得索取访问令牌。

Git push 可能通过 SSH 或独立的 Git 凭据成功，因此推送成功不能单独证明 `gh` 的 API 认证有效；反之，
沙箱内 `gh auth status` 失败也不能推断 Git 推送必然失败。

### Triage labels

使用默认的 canonical triage labels：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human` 和 `wontfix`。参见 `docs/agents/triage-labels.md`。

### Domain docs

本仓库采用 single-context 布局，使用根目录 `CONTEXT.md` 和 `docs/adr/`。参见 `docs/agents/domain.md`。
