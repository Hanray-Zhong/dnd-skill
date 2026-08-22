# D&D 5E 可点击战术查看器原型交接

> **THROWAWAY 设计参考。** 本目录从一次性设计实验完整保留而来，用于复核交互与性能结论，不是正式实现，也不能直接进入生产。

## 结论

设计问题的答案是 **可以**：原生 HTML + SVG + 少量 JavaScript 足以提供清楚、快速、严格只读的移动查询。关键前提是浏览器只接收已经完成玩家知识投影的数据；隐藏实体、陷阱和秘密通道必须在序列化前消失，而不是靠 SVG/CSS 隐藏。

该结论已经同步到 ADR-0048：**点击棋子时计算预算内最短路径树，并按 `projectionRevision + entityId + movementMode + movementPolicy` 缓存**。地图修订时只生成玩家投影和渲染输入；可以对当前回合角色做空闲预热，但不默认生成并发布所有玩家的全图树。

## 原型位置与运行

- 原型根目录：`docs/prototypes/tactical-viewer/`
- 启动：`cd docs/prototypes/tactical-viewer && ./run.sh`
- 默认 URL：`http://127.0.0.1:8787/?variant=A&map=small`
- 布局：`?variant=A|B|C`；地图：`&map=small|large`
- 静态回退：[public/artifacts/static-fallback.svg](public/artifacts/static-fallback.svg)
- 完整使用说明：[README.md](README.md)

`run.sh` 只发布 `public/`，不会发布 `fixtures/` 中的 DM 权威测试夹具。按 `Ctrl-C` 停止服务。

## 性能结果

由用户指定的 `browser:control-in-app-browser` 在 Codex 内置浏览器中各运行 20 轮；DOM 指标包含 SVG 节点构建、确定性寻路、覆盖层更新和强制布局，不包含截图编码。

| 场景 | 修订渲染 median / p95 | 点击疾走高亮 median / p95 | 路径预览 median / p95 | 所有玩家全图树 median / p95 | 全图树发布体积 |
|---|---:|---:|---:|---:|---:|
| 14×10，140 格，1 名可控玩家 | 0.8 / 1.5 ms | 0.8 / 1.6 ms | 0.1 / 0.2 ms | 0.5 / 1.1 ms | 4,009 B |
| 50×50，2,500 格，4 名可控玩家 | 8.6 / 10.1 ms | 1.2 / 1.4 ms | 0.1 / 0.2 ms | 33.8 / 46.8 ms | 344,338 B |

50×50 玩家投影本身为 34,601 B；默认发布四棵全图树会把额外负载扩大到约投影的 10 倍，而一次点击只展开 190 个预算内格。虽然全量预计算仍未超过 50 ms，但按点击计算在延迟、失效管理和发布体积上都更合适。结果表明每次地图相关修订后重建 SVG 很安全，路径树则应延迟计算并缓存。

机器可读原始结果：

- [public/artifacts/browser-skill-results.json](public/artifacts/browser-skill-results.json)
- [public/artifacts/verification-results.json](public/artifacts/verification-results.json)

## 交互发现

- A“地图优先”最适合作为默认方案：地图与路径信息同时可见，决策链最短。
- B“路线工作台”最适合教学和规则核对，但占用更多纵向空间。
- C“安静棋桌”适合低干扰查看；Browser 测试发现原浮动摘要会遮挡目标格，现已改为地图下方双列托盘。
- “普通移动 / 疾走”切换清楚。疾走模式同时保留青色普通范围和琥珀色新增范围，比只显示一种总范围更容易理解。
- 点击 `L7` 得到 `C7 → C8 → D8 → E8 → F7 → G6 → H6 → I7 → J7 → K7 → L7`，格距 50 尺、移动消耗 55 尺、剩余 0 尺，并提示从 `K7 → L7` 离开可见哥布林触及范围。
- 全程位置保持 `C7`，投影摘要保持 `authoritySnapshotUnchanged: true`；没有拖拽元素、表单或网络写请求。
- Browser 测试还发现固定性能面板会遮挡窄视口棋子；现已移入普通文档流。新鲜交互标签页无 console warning/error。

## 覆盖层取舍

必要：稳定坐标、墙/门状态、困难地形、公开棋子及完整占地、普通/疾走两档可达范围、选中目标、路径线、距离/消耗/剩余、仅沿当前路径出现的可感知风险、投影修订和“未知信息不参与”的提示。

容易拥挤：所有敌人的常驻触及范围、每格消耗数字、全树父指针、棋子旁完整状态、完整 JSON 诊断。A 中常驻触及范围用于比较，但正式界面应默认关闭，只在敌人聚焦或路径涉及时显示。性能诊断和完整状态 JSON 都是原型专用，不应进入正式查看器。

## 静态 SVG 回退

回退足以完成“读图、查坐标、理解当前范围和既定路径”的最低任务：包含五尺网格、坐标、地形、墙门、公开棋子、普通/疾走范围、完整示例路径、明显风险和文字图例，并且没有 `<script>`。它不能替代探索式点击；无交互环境仍应保留自然语言/坐标查询。窄屏可能需要缩放或横向查看，因此评价为“合格回退”，不是功能等价替代。

## 推荐的最小只读接口

输入只接受玩家投影：

```text
TacticalViewProjection {
  schemaVersion, authorityRevision, projectionRevision, audienceId, readOnly: true,
  grid { width, height, feetPerCell, coordinateStyle, diagonalRule, preventCornerCutting },
  terrain[] { x, y, multiplier },
  barriers[] { id, a, b, kind: wall|door, open },
  entities[] {
    id, publicLabel, relation, position, sizeCells, blocksMovement,
    selectable, movement? { speedFeet, usedFeet }, reachFeet?, observableConditions?
  },
  controllableEntityIds[]
}
```

查看器只暴露三个意图：`selectToken(entityId)`、`setMovementMode(normal|dash)`、`previewCell(coordinate)`。输出为可达格及消耗档、最低消耗路径、格距、消耗、剩余移动力和公开风险。接口中不得出现 `move`、`commit`、`save`、拖拽或权威状态写入口；静态 SVG 与交互 HTML 必须消费同一投影模型。

## ADR-0048 同步结果

已保留“只读 HTML/SVG 查看器、对话确认、可中断结算链、静态回退”的核心决策，并同步两点：

1. 将默认全量预计算改为按点击预算内计算 + 修订缓存，允许当前行动者空闲预热。
2. 明确发布包的算法输入本身必须是知识投影，不能把权威隐藏实体放进 HTML/JavaScript 后再隐藏；缓存和性能诊断也不得包含隐藏输入。

对应工作区、角色状态与战术地图决策同时进入 `docs/dnd-5e-skill-suite-spec.md` 和 `docs/dnd-5e-source-to-behavior-coverage-matrix.md`；本交接继续作为实验数据与设计证据保留。

相关设计来源直接参见仓库的 `CONTEXT.md` 与 ADR-0039、0040、0041、0042、0044、0045、0046、0047、0048；本交接不复述这些决策正文。

## 截图

- [A：疾走与路径](public/artifacts/screenshots/iab-small-a-dash-path.png)
- [B：路线工作台](public/artifacts/screenshots/iab-small-b-route-workbench.png)
- [C：安静棋桌](public/artifacts/screenshots/iab-small-c-quiet-table.png)
- [50×50 路径](public/artifacts/screenshots/iab-large-50x50-path.png)
- [静态 SVG 回退](public/artifacts/screenshots/iab-static-fallback.png)

## 尚未解决

- 原型把盟友占地视为完全阻挡；正式规则引擎应区分“可穿过友方空间”和“不可结束在已占格”，并处理穿越成本。
- 交替 5/10 尺对角状态已在算法中预留，但未做专门 UI/Browser 验收。
- 尚未覆盖可控大型生物的扫掠占地、挤过、攀爬/飞行/高度、开门动作成本、脱离动作、反应是否可用、被墙遮挡的触及和强制移动。
- 性能只在当前本机内置浏览器验证；低端移动设备、超大公开实体数和多个持续区域仍需正式实现阶段基准。
- 静态回退在多名可控玩家时应生成一张默认当前行动者视图，还是每名玩家各一张，仍需产品决定。

## Suggested skills

- `browser:control-in-app-browser`：继续人工比较三种布局或复测响应式交互；按仓库规则需由用户在新任务中再次明确授权。
- `domain-modeling`：把最终缓存键、投影边界和只读查询术语带回领域文档时使用。
- `prototype`：仅在需要继续探索友方占地、交替对角或大型生物移动时再做新的抛弃式实验。
