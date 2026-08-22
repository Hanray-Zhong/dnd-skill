# 固定战役工作区顶层布局

每个战役工作区固定包含根清单 `campaign.json`、不可变输入目录 `inputs/`、权威状态目录 `state/`、可重建投影目录 `views/`、显式归档目录 `archives/` 和可安全清理的 `.runtime/`；`inputs/` 下按 modules、characters、attachments 分类，`state/` 保存 `campaign.sqlite3` 与一致性 snapshots，`views/` 按 shared、players、dm 受众分区。事件历史保存在战役状态库，会话记录、角色状态表、战术地图和审计展示只属于投影，任何投影或临时文件都不能反向成为权威状态。该选择使备份、恢复、权限审查和后续迁移拥有稳定边界，代价是顶层名称与职责变化必须提供显式工作区迁移。
