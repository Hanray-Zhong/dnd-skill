---
name: dnd-5e-campaign-start
description: 创建战役工作区并组织 Session Zero 的内部能力。
disable-model-invocation: true
---

# 战役初始化

通过 `dnd-5e` 门面接收初始化请求，确认战役工作区与持久配置，再交由 `dnd-5e-campaign-state` 建立和保存。Session Zero 必须收集玩家稳定标识、显示名、角色控制关系、安全边界、玩家偏好、投骰策略、难度策略、PvP 桌规、逐角色缺席策略和升级方式；缺省值首次出现时只返回完整展开配置而不写状态，展示后必须用完整配置重新取得确认，未回答的 PvP 类别按禁止处理。只有每位玩家及安全边界均已确认、控制关系和代管关系无冲突时，才能以一个状态事务写入 `ready_to_play`、初始受众和审计事件。不得主持运行中场景，也不得绕过统一状态边界。
