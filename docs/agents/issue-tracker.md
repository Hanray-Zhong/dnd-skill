# Issue tracker：GitHub

本仓库的 Issue 和 PRD（产品需求文档）存放于 GitHub Issues。所有操作使用 `gh` CLI。

## 约定

- **创建 Issue**：`gh issue create --title "..." --body "..."`。多行正文使用 heredoc。
- **读取 Issue**：`gh issue view <number> --comments`，使用 `jq` 筛选评论并同时获取 labels。
- **列出 Issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需添加 `--label` 和 `--state` 过滤条件。
- **评论 Issue**：`gh issue comment <number> --body "..."`
- **添加或移除标签**：`gh issue edit <number> --add-label "..."` / `gh issue edit <number> --remove-label "..."`
- **关闭 Issue**：`gh issue close <number> --comment "..."`

通过 `git remote -v` 推断仓库；在 clone 内执行时，`gh` 会自动识别目标仓库。

## 将 PR 作为 triage 请求入口

**将 PR 作为请求入口：否。**（如果本仓库将外部 PR 作为功能请求，可将此值改为 `yes`；`/triage` 会读取该配置。）

当设置为 `yes` 时，PR 使用与 Issue 相同的标签和状态，并使用对应的 `gh pr` 命令：

- **读取 PR**：`gh pr view <number> --comments` 和 `gh pr diff <number>`
- **列出外部 PR 供 triage**：`gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，仅保留 `authorAssociation` 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE` 的项目，排除 `OWNER`、`MEMBER` 和 `COLLABORATOR`
- **评论、添加或移除标签、关闭**：使用 `gh pr comment`、`gh pr edit --add-label` / `--remove-label`、`gh pr close`

GitHub 的 Issue 和 PR 共用编号空间，因此裸写的 `#42` 可能指 Issue 或 PR；需要先运行 `gh pr view 42`，失败后再运行 `gh issue view 42`。

## Wayfinding 操作

这些约定供 `/wayfinder` 使用。map 是一个包含子 Issue 的总 Issue。

- **Map**：创建一个带有 `wayfinder:map` 标签的 Issue，正文包含 Notes、Decisions-so-far 和 Fog。
- **Child ticket**：通过 GitHub sub-issue 将子 Issue 链接到 map。未启用 sub-issue 时，在子 Issue 正文顶部添加 `Part of #<map>`，并在正文任务列表中维护关联关系。标签使用 `wayfinder:<type>`（`research` / `prototype` / `grilling` / `task`）。认领后，将驱动开发者设为 assignee。
- **Blocking**：使用 GitHub 原生 Issue dependency 作为规范的、对用户可见的阻塞关系。调用 `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` 添加关系，其中 `<blocker-db-id>` 必须是阻塞 Issue 的数字 database id（使用 `gh api repos/<owner>/<repo>/issues/<n> --jq .id` 获取），不能使用 `#number` 或 `node_id`。如果无法使用 dependency，则在子 Issue 正文顶部添加 `Blocked by: #<n>, #<n>`。所有阻塞 Issue 关闭后，子 Issue 才算解除阻塞。
- **Frontier query**：列出 map 的开放子 Issue（范围限定为 map 的 sub-issue 或任务列表），排除存在开放阻塞项（`issue_dependencies_summary.blocked_by > 0`，或 `Blocked by` 中存在开放 Issue）或已分配 assignee 的项目，按 map 中的顺序选择第一个。
- **Claim**：`gh issue edit <n> --add-assignee @me`，这是当前会话的第一次写入操作。
- **Resolve**：先运行 `gh issue comment <n> --body "<answer>"`，再运行 `gh issue close <n>`，最后向 map 的 Decisions-so-far 追加一个上下文指针（gist + link）。
