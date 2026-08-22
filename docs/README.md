# 文档索引

本仓库正在实现第一版 D&D 5E 跑团 Skill Suite。第一版从已经确认的规格、领域术语和架构决策开始设计与实现。

## 权威关系

1. [GitHub Issue #1](https://github.com/Hanray-Zhong/dnd-skill/issues/1) 是第一版产品规格与范围的权威来源。
2. 根目录的 [CONTEXT.md](../CONTEXT.md) 是领域术语的权威来源。
3. [adr/](adr/) 保存已经确认的架构与产品决策；发现与 Issue 或领域术语冲突时必须显式复核，不能静默覆盖。
4. [dnd-5e-source-to-behavior-coverage-matrix.md](dnd-5e-source-to-behavior-coverage-matrix.md) 是来源覆盖、职责分配和验证状态的权威来源。
5. [dnd-5e-skill-suite-spec.md](dnd-5e-skill-suite-spec.md) 是 Issue #1 正文的本地镜像，便于仓库内审阅；更新规格时必须与远端同步。

## 其他重要文档

- [reference/](reference/) 保存开发期参考资料。它们不属于发布 Skill，也不能成为运行时依赖；具体范围见 [reference/README.md](reference/README.md)。
- [prototypes/](prototypes/) 保存用于验证设计决策的抛弃式原型及实验结果；它们不是正式实现。
- [agents/](agents/) 保存 Issue tracker、triage 标签和领域文档的协作约定。

## 当前实现状态

Issue #2 的首个纵向切片已建立十一项 Skill 目录、`dnd-5e` 统一进程门面、固定战役工作区、根清单和 SQLite 权威状态库边界，并支持安全创建与重新打开空战役。运行方式见仓库根目录的 [README.md](../README.md)。

其余能力仍须从 Issue #1 的验收范围继续实现，并以当前规格、领域术语、ADR 和覆盖矩阵作为完整设计输入；当前切片不代表完整跑团功能已经交付。

[GitHub Issue #4](https://github.com/Hanray-Zhong/dnd-skill/issues/4) 的交付范围是完整构建并查询三宝书 Markdown 规则章节库，不是只处理一份规则样本。具体输入、生成资产、运行时隔离、失败门禁及与 Issue #5、#6、#33 的边界见[来源到行为覆盖矩阵](dnd-5e-source-to-behavior-coverage-matrix.md#issue-4-交付边界)和[开发参考资料边界](reference/README.md#转换与运行时交付)。
