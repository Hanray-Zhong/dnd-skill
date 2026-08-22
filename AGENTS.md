# 项目协作约定

## AI 产物语言

所有 AI 生成或修改的产物均以简体中文作为标准语言，包括文档、Issue、规格说明、代码注释、提交说明和其他交付内容。本次创建的配置文档也遵循此规则。代码标识符、命令、API、协议名以及 GitHub triage 标签等必须保留原文的内容，可继续使用英文。

## Agent skills

### PDF 阅读

`pdf:pdf` 技能在本仓库的所有场景中均可用于读取 PDF 文件。只要当前任务涉及读取、审阅、
检查或从 PDF 提取信息，即使用户未在当前任务中点名该技能，也允许读取其 `SKILL.md` 并按只读
工作流执行。

此常驻授权仅涵盖读取 PDF 以及阅读所需的临时渲染和文本提取，不授权创建、编辑、填写、转换、
覆盖或重新导出 PDF。涉及这些写操作时，仍须用户在当前任务中明确指定 `pdf:pdf`，并遵循该技能
的完整工作流。

### Word 与 DOCX 文档

`documents:documents` 技能在本仓库中获得常驻授权。只要当前任务涉及读取、创建、编辑、修订、
评论、检查或验证 `.docx`、Word 或面向 Google Docs 的文档产物，即使用户未在当前任务中点名
该技能，也允许读取其 `SKILL.md`、任务所需的引用资料和脚本，并按其完整工作流执行。

该授权仅用于完成用户当前提出的文档任务，不扩大任务范围。创建或编辑文档时必须遵循技能规定的
依赖加载、操作标记、模板选择及渲染检查要求；只有用户要求交付原生 Google Docs 时，才允许执行
相应的外部导入操作。

### Analytics Dashboard 模板

`openai-templates:artifact-template-analytics-dashboard` 技能在本仓库中获得常驻授权。当前任务选择、
点名或明确要求使用 Analytics Dashboard 模板时，即使用户未另行点名该技能，也允许读取其
`SKILL.md`、`artifact-template.json` 和保留的参考文件，并按模板工作流创建电子表格。

允许在该模板工作流内调用其要求的、提示中已公布的预装电子表格能力；此依赖授权仅限完成
Analytics Dashboard 模板任务，不构成其他电子表格任务的通用 skill 授权。必须保持参考文件不变，
通过克隆或导入保留其结构与视觉系统，并在交付前完成渲染和验证。

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
2. 获取最新的 `origin/main`，并为本次 Issue 生成唯一随机 ID。在创建或切换 `issue/issue#<id>` 分支前，
   必须先以 `origin/main` 为基线，在 `~/.codex/worktrees/{随机id}/` 创建 detached worktree；
   `{随机id}` 是占位符，必须替换为实际生成且未被占用的随机 ID，不得复用已有 worktree 目录。
3. 进入新 worktree 后，再创建并切换到 `issue/issue#<id>` 分支，例如 Issue `#42` 使用
   `issue/issue#42`。如果该分支已经存在，应先核对其归属和状态，再将它安全地检出到新 worktree，
   不得创建重复分支或覆盖远端历史。禁止在项目原始工作树中创建或切换 Issue 分支；后续实现、测试、
   提交和推送必须在新 worktree 中完成。
4. 按 `/implement` 要求完成实现、TDD 和相关验证。只提交当前 Issue 的文件，提交信息引用 `#<id>`，
   然后将该分支推送到 `origin`；禁止直接提交或推送到 `main`。
5. 创建以 `main` 为 base、以 Issue 分支为 head 的 PR。PR 标题和正文应概括改动与验证结果，并使用
   `Closes #<id>` 关联 Issue。
6. 以 `origin/main` 为固定点运行 `/code-review`，同时审查 Standards 与 Issue 需求；再检查 PR 的最终
   diff、CI/checks 和 review 状态。所有阻塞发现必须修复并重新验证、提交和推送；不得通过跳过检查、
   放宽断言或忽略审查意见来换取合并。
7. 仅在 PR 无未解决的阻塞审查意见且必需 checks 全部通过后，按仓库支持的合并策略将 PR 合并到
   `origin/main`，并删除远端 Issue 分支。合并后读取远端状态，确认 PR 已合并且 `origin/main` 包含该改动。
8. 在 Issue 中保留原始需求，勾选已完成项，并补充实现摘要、验证结果和 PR 链接。移除
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
