# 固定第一版十一项 Skill 目录与边界

第一版固定十一项稳定标识：dnd-5e 是唯一玩家主持门面；dnd-5e-campaign-start 负责战役初始化与 Session Zero；dnd-5e-module-import 负责不可信模组导入；dnd-5e-rules 负责规则检索、优先级、公式目录与确定性计算；dnd-5e-character 负责角色生命周期；dnd-5e-session 负责非精确实时主持；dnd-5e-combat 负责精确战斗；dnd-5e-scene 负责空间与视觉投影；dnd-5e-campaign-state 是唯一持久写入边界；dnd-5e-world 负责长期世界语义；dnd-5e-adventure 负责冒险实例与准备期适配。开发构建工具链、确定性计算器和骰子引擎是支持组件，不注册为额外 Skill。模组导入不得承担冒险适配，冒险准备不得写入已发生事实，世界模型不得绕过状态事务，主持门面负责最终知识投影。该选择为实现、测试和覆盖矩阵提供稳定公共边界，代价是职责变化必须同步修改规格、覆盖矩阵和交接契约。
