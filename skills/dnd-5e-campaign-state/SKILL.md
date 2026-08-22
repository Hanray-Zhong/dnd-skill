---
name: dnd-5e-campaign-state
description: 管理工作区、SQLite 状态事务、事件与修订的唯一持久化能力。
disable-model-invocation: true
---

# 战役状态

这是唯一持久状态边界。校验带前置修订的状态变更请求，并以 SQLite 事务原子保存实体快照、不可变事件、认知、受众与修订。不得作规则裁定、冒险准备或叙事决定。
