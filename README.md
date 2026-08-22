# D&D 5E 跑团 Skill Suite

本仓库正在实现由单一 `dnd-5e` 主持门面协调的十一项本地优先 Skill。当前纵向切片支持创建和重新打开空战役、修改团前难度策略，以及在全员确认后完成 Session Zero；状态请求同时贯通幂等重试、乐观并发、不可变事件、修订号与崩溃恢复语义。

## 运行要求

- Python 3.11 或更高版本；
- Python 自带的 `sqlite3`，SQLite 3.37 或更高版本；
- 运行时无第三方依赖。

## 快速开始

从仓库根目录运行：

```bash
PYTHONPATH=src python -m dnd_5e list-skills
PYTHONPATH=src python -m dnd_5e create /path/to/empty-campaign \
  --initial-config '{"advancement":"xp","difficulty":"standard","roll_policy":"players"}'
PYTHONPATH=src python -m dnd_5e configure /path/to/empty-campaign \
  --expected-revision 1 \
  --idempotency-key session-zero-difficulty-v1 \
  --difficulty challenging
PYTHONPATH=src python -m dnd_5e session-zero /path/to/empty-campaign \
  --expected-revision 2 \
  --idempotency-key complete-session-zero-v1 \
  --configuration '{"players":[{"player_id":"alice","display_name":"艾莉丝","character_ids":["aria"],"confirmed":true,"preferences":{},"roll_policy":"player_rolls","absence_policies":{"aria":{"mode":"narrative_exit"}},"pvp_preferences":{"violence":"forbid"}}],"safety":{"boundaries":[],"confirmed_by":["alice"]},"difficulty":"challenging","advancement":"xp","private_roll_policy":"dice_engine","pvp_categories":["violence"]}'
PYTHONPATH=src python -m dnd_5e open /path/to/empty-campaign
```

安装本项目后也可使用等价的 `dnd-5e` 命令。成功结果以 JSON 输出到 stdout；可预期的拒绝以 JSON 输出到 stderr，并使用退出码 `2`。新建空战役返回 `campaign_status: "awaiting_session_zero"`、`next_step: "session_zero"` 和 `ready_to_play: false`：这表示工作区可继续配置，不表示已经可以跳过 Session Zero 开始游戏。

## 当前工作区契约

创建入口只接受新建或完全空目录，并拒绝符号链接、普通文件、文件系统根目录和用户主目录。初始化过程先创建 SQLite 权威状态库，最后才原子写入 `campaign.json` 完成标志；失败时不会留下可被误认为有效战役的根清单。

```text
<campaign-workspace>/
├── campaign.json
├── inputs/{modules,characters,attachments}/
├── state/{campaign.sqlite3,snapshots/}
├── views/{shared,players,dm}/
├── archives/
└── .runtime/
```

打开入口验证根清单、相对存储路径、兼容组合、必要目录和 SQLite 完整性，并以只读方式恢复战役标识、当前修订和初始配置。只有缺失的空投影目录会自动重建；权威状态缺失或损坏时直接停止。

`configure` 当前只修改一项团前难度策略。调用方必须提供从 `create` 或 `open` 取得的前置修订号，以及能够在重试时复用的幂等键。首次成功会返回新修订和事件标识；相同请求重试返回原事务并标记 `replayed: true`，不会增加修订或事件。过期修订会以 `revision_conflict` 拒绝，并在 `details` 中返回当前修订与配置供重新对账。

`session-zero` 通过同一状态协议确认玩家名册、角色控制关系、安全边界、玩家偏好和团前策略。每位玩家可以选择 `player_rolls` 或 `script_rolls`；`absence_policies` 按 `character_ids` 中的每个角色分别设置 `narrative_exit`、`delegate` 或 `agent_custody`。升级方式支持 `xp` 与 `milestone`，秘密投骰来源支持 `dice_engine` 与 `private_pool`。省略可选策略时，命令会以 `session_zero_confirmation_required` 返回 `defaulted_fields` 与完整 `resolved_configuration`，显式展示标准难度、经验值推进、玩家自掷、骰子引擎暗骰、逐角色叙事离队及未回答 PvP 类别的 `forbid`；此预览不写状态。只有用展开后的完整配置再次提交、所有玩家和安全边界均确认且控制/代管关系无冲突时，事务才会写入 `ready_to_play`、初始桌级/玩家级受众和审计事件。重开后会恢复同一配置与受众；旧版全局 `roll_policy` 不进入完成后的权威配置。

## 验证

```bash
python -m unittest discover -s tests -v
uvx --from mypy mypy
```

产品范围、领域术语与架构决策见 [docs/README.md](docs/README.md)。
