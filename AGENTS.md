# 项目协作约定

## AI 产物语言

所有 AI 生成或修改的产物均以简体中文作为标准语言，包括文档、Issue、规格说明、代码注释、提交说明和其他交付内容。本次创建的配置文档也遵循此规则。代码标识符、命令、API、协议名以及 GitHub triage 标签等必须保留原文的内容，可继续使用英文。

## Agent skills

### Issue tracker

本仓库的 Issue 和 PRD 使用 GitHub Issues 管理，并通过 `gh` CLI 操作。参见 `docs/agents/issue-tracker.md`。

### `/implement` Issue 交付流程

在本仓库中，用户显式调用 `/implement` 并提供 GitHub Issue 编号，即授权 Codex 针对该 Issue
创建并推送专用分支、创建和合并 PR，以及更新并关闭 Issue。授权仅限当前 Issue 及其分支和 PR，
不得扩展到其他 Issue、PR、分支或远端操作。缺少 Issue 编号时，必须先向用户索取，不得臆造编号或
使用无关 Issue。

执行 `/implement` 时遵循以下顺序：

1. 读取 Issue 正文、评论、标签和阻塞关系，确认 Issue 仍处于开放状态、需求足以实现且没有未解决的
   blocker。记录当前工作区状态，保留与该 Issue 无关的改动。
2. 获取最新的 `origin/main`，从该提交创建并切换到 `issue/issue#<id>` 分支，例如 Issue `#42`
   使用 `issue/issue#42`。如果该分支已经存在，应先核对其归属和状态，再安全地续接，不得创建重复分支
   或覆盖远端历史。
3. 按 `/implement` 要求完成实现、TDD 和相关验证。只提交当前 Issue 的文件，提交信息引用 `#<id>`，
   然后将该分支推送到 `origin`；禁止直接提交或推送到 `main`。
4. 创建以 `main` 为 base、以 Issue 分支为 head 的 PR。PR 标题和正文应概括改动与验证结果，并使用
   `Closes #<id>` 关联 Issue。
5. 以 `origin/main` 为固定点运行 `/code-review`，同时审查 Standards 与 Issue 需求；再检查 PR 的最终
   diff、CI/checks 和 review 状态。所有阻塞发现必须修复并重新验证、提交和推送；不得通过跳过检查、
   放宽断言或忽略审查意见来换取合并。
6. 仅在 PR 无未解决的阻塞审查意见且必需 checks 全部通过后，按仓库支持的合并策略将 PR 合并到
   `origin/main`，并删除远端 Issue 分支。合并后读取远端状态，确认 PR 已合并且 `origin/main` 包含该改动。
7. 在 Issue 中保留原始需求，勾选已完成项，并补充实现摘要、验证结果和 PR 链接。移除
   `ready-for-agent`、`ready-for-human`、`needs-triage`、`needs-info` 等不再适用的 triage 标签，
   保留无关的领域标签；如果 Issue 未被 PR 自动关闭，则显式关闭。最后重新读取 Issue，确认正文、标签
   和状态均已更新。

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
