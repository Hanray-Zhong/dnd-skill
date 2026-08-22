# 分离世界模型、冒险准备与实时主持

第一版 Skill Suite 由十一项 Skill 组成：dnd-5e 主持门面与十项专门 Skill。dnd-5e-world 负责长期世界语义，dnd-5e-adventure 负责尚未发生的冒险准备，dnd-5e-session 与 dnd-5e-combat 负责实时主持；实际变化统一提交给 dnd-5e-campaign-state。该拆分保持世界事实、准备内容和已结算事件的边界，代价是专门 Skill 之间必须使用明确交接契约，而玩家仍只通过主持门面使用整套能力。
