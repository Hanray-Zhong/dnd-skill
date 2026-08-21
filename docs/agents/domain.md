# 领域文档（Domain Docs）

本文件说明工程 skills 在探索代码库时应如何消费本仓库的领域文档。

## 开始探索前读取以下内容

- 根目录的 `CONTEXT.md`，或
- 如果根目录存在 `CONTEXT-MAP.md`，读取它指向的、与当前主题相关的各个 `CONTEXT.md`
- `docs/adr/`：读取涉及当前工作区域的 ADR。在 multi-context 仓库中，还要检查 `src/<context>/docs/adr/` 中与上下文相关的决策。

如果这些文件不存在，静默继续。不要特别指出缺失，也不要提前建议创建它们。`/domain-modeling` skill（通过 `/grill-with-docs` 和 `/improve-codebase-architecture` 进入）会在术语或决策实际确定时按需创建这些文件。

## 文件结构

本仓库采用 single-context 布局（大多数仓库适用）：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

multi-context 仓库的布局如下；只有在根目录存在 `CONTEXT-MAP.md` 时才使用：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← 系统级决策
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← 上下文级决策
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## 使用术语表中的词汇

当输出中命名领域概念（例如 Issue 标题、重构提案、假设或测试名称）时，使用 `CONTEXT.md` 定义的术语。如果术语表明确避免某个同义词，不要改用该同义词。

如果需要的概念尚未出现在术语表中，这通常意味着：你正在发明项目尚未采用的语言（应重新考虑），或者项目确实存在术语缺口（记录给 `/domain-modeling`）。

## 标记 ADR 冲突

如果输出与现有 ADR 矛盾，应明确指出，而不是静默覆盖：

> _与 ADR-0007（event-sourced orders）冲突，但值得重新审议，因为……_
