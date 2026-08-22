# 文档索引

本仓库当前处于第一版 D&D 5E 跑团 Skill Suite 的设计阶段，尚无可运行的 Skill 实现。第一版从已经确认的规格、领域术语和架构决策开始设计与实现。

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

仓库当前不包含 Skill 实现。后续实现必须从 Issue #1 的验收范围出发建立目录、接口、数据结构和测试，并以当前规格、领域术语和 ADR 作为完整设计输入。
