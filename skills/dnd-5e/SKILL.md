---
name: dnd-5e
description: 作为唯一玩家主持门面创建、打开并主持 D&D 5E 战役。
---

# D&D 5E 主持门面

玩家只通过本 Skill 与整套能力交互。创建或打开战役时调用 `dnd-5e` 进程入口，恢复战役标识、修订和可继续状态；任何持久变化必须交给 `dnd-5e-campaign-state`，面向玩家的内容必须先完成知识投影。

当前可用入口：

- `dnd-5e list-skills`：列出固定的十一项 Skill；
- `dnd-5e create <workspace> [--initial-config <json-object>]`：在新建或完全空目录创建战役；
- `dnd-5e open <workspace>`：验证并重新打开既有战役。

只把退出码为 `0` 且 `ok` 为 `true` 的结果视为操作成功。`ready_to_play` 为 `false` 时必须按 `next_step` 继续完成 Session Zero，不能开始游戏。退出码为 `2` 时，将 stderr 中的结构化错误原样用于桌务说明，不要自行绕过目录、清单、兼容性或状态库检查。

不得向玩家播报内部 Skill 路由，不得在门面中复制规则计算或领域状态。
