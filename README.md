# D&D 5E 跑团 Skill Suite

本仓库正在实现由单一 `dnd-5e` 主持门面协调的十一项本地优先 Skill。当前纵向切片支持创建和重新打开空战役、修改团前难度策略、在全员确认后完成 Session Zero、分类并记录五类运行期消息、依据版本化公式目录重算代表角色派生数据，并提供完整三宝书的开发构建与固定 Markdown 规则资产查询。状态请求贯通幂等重试、乐观并发、不可变事件、修订号与崩溃恢复语义；规则查询支持稳定 ID、别名和主题入口，并能依据规则库中已复核、具备有界正文证据的例外声明给出具体优先的决策记录。

## 运行要求

- Python 3.11 或更高版本；
- Python 自带的 `sqlite3`，SQLite 3.37 或更高版本；
- 运行时无第三方依赖。

只有开发期 PDF 构建需要 `rules-build` 可选依赖；其版本由 `uv.lock` 固定，并且不会进入运行时依赖或本地预览 wheel。

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
PYTHONPATH=src python -m dnd_5e recalculate /path/to/empty-campaign \
  --expected-revision 3 \
  --idempotency-key aria-strength-modifier-v1 \
  --character aria \
  --formula ability-modifier \
  --inputs '{"ability_score":{"value":15,"unit":"ability_score"}}' \
  --modifiers '[]'
PYTHONPATH=src python -m dnd_5e message /path/to/empty-campaign \
  --speaker alice --character aria --scene table \
  --input-reference message-001 --expected-revision 4 \
  --text '“我们往北门走。”'
PYTHONPATH=src python -m dnd_5e open /path/to/empty-campaign
PYTHONPATH=src python -m dnd_5e rules-query \
  --library build/rules-library --alias '火球术'
PYTHONPATH=src python -m dnd_5e rules-query \
  --library build/rules-library --alias '行动自如' \
  --general-rule-id phb-cn-1.72-condition-d0b19d83ea08
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

`session-zero` 通过同一状态协议确认玩家名册、角色控制关系、安全边界、玩家偏好和团前策略。每位玩家可以选择 `player_rolls` 或 `script_rolls`；`absence_policies` 按 `character_ids` 中的每个角色分别设置 `narrative_exit`、`delegate` 或 `agent_custody`。升级方式支持 `xp` 与 `milestone`，秘密投骰来源支持 `dice_engine` 与 `private_pool`。省略可选策略时，命令会以 `session_zero_confirmation_required` 返回 `defaulted_fields` 与完整 `resolved_configuration`，显式展示标准难度、经验值推进、玩家自掷、骰子引擎暗骰、逐角色叙事离队及未回答 PvP 类别的 `forbid`；此预览不写状态。只有用展开后的完整配置再次提交、所有玩家和安全边界均确认且控制/代管关系无冲突时，事务才会写入 `ready_to_play`、初始桌级/玩家级受众、`table` 共享场景及审计事件。该场景固定参与玩家、角色控制、`shared_table` 交互模式、输出受众和无新增场景事实的投影策略；重开后会恢复同一配置、受众与场景实体。旧版全局 `roll_policy` 不进入完成后的权威配置。

`message` 只在战役进入 `ready_to_play` 后处理运行期输入，并要求 `--scene` 指向权威场景实体；当前首个可用场景是 Session Zero 建立的 `table`。中文双引号、半角星号、`（内心：……）`、`//` 和 `【……】` 分别表示角色对话、角色行动、角色内心、OOC 与待验证的系统消息或人类骰子报告；未标记玩家文本默认按 OOC 处理，显式 `//` 的优先级高于正文中的标记字符。所有输入都必须同时通过稳定玩家名册、场景参与者和交互模式校验，角色消息还要通过名册与场景中的角色控制权校验；`【……】` 只形成待验证桌务项，单靠文本不能改变系统状态。响应固定分为 `scene_narrative`、`table_prompt` 和 `audit_record` 三层并携带目标场景与从场景解析的输出受众：分类阶段不把玩家输入回显成新的场景事实，角色行动进入待解析桌务项，角色内心使用对应玩家私有受众，审计层记录发言者、场景、事件、来源、修订和状态差异。角色对话、行动和内心需要前置修订并原子记录，写入边界会再次核对场景、交互模式、参与者、控制权和受众；原始输入引用同时作为幂等身份。普通 OOC、待验证系统消息、歧义输入与拒绝结果不创建事件或新修订。

`recalculate` 当前提供 Issue #6 的代表性公式 `ability-modifier`。输入必须显式携带 `ability_score` 单位；具名修正项必须声明目标、单位、操作、来源与规则优先级。计算结果记录公式目录版本与哈希、两条规则来源、输入、已采用及被抑制修正项、减法、除法和向下取整步骤，再由唯一状态边界复算后原子保存为角色派生数据。相同幂等请求返回原事务，重新打开战役可恢复同一审计轨迹。缺失输入、单位冲突、越界输入或同优先级覆盖冲突会在写入前拒绝。完整角色构成与输入来源仍由后续角色创建能力负责，本入口不把临时输入冒充角色构成。

安装了本地预览规则资产时，新建战役会在兼容组合中固定该规则章节库的版本和内容哈希；没有安装规则资产的源码开发环境仍使用明确的 `bootstrap-empty-v1` 身份。

## 规则章节库

开发构建、三书固定输入、生成清单、查询方式、本地预览 wheel 和公开发布门禁见 [规则章节库构建与查询](docs/rules-library.md)。生成规则文本只保存在被 Git 忽略的本地输出中；来源授权未完成时，构建清单明确标记“本地预览可用、公开发布被阻止”。

## 验证

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
uvx --from mypy mypy
```

产品范围、领域术语与架构决策见 [docs/README.md](docs/README.md)。
