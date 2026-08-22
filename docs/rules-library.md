# 规则章节库构建与查询

Issue #4 的内容构建工具链位于 `tools/rules_library/`，它是开发支持组件，不注册为第十二项 Skill，也不会进入本地预览 wheel。生产基线 `core-cn-baseline.json` 固定三本权威译本的相对路径、版本、SHA-256、页数、书签数、精确资产清单哈希、类别与字符数、表格/侧栏/脚注结构计数、解析器版本、实体识别区域、叶级职责路由和来源授权状态。

## 开发构建

将三本固定文件放在 `docs/reference/` 约定的位置后，从仓库根目录执行：

```bash
uv run --locked --extra rules-build python -m tools.rules_library build \
  --baseline tools/rules_library/core-cn-baseline.json \
  --reference-root docs/reference \
  --output build/rules-library
```

构建器在解析内容前验证全部权威输入。缺失、路径逃逸或 SHA-256 不匹配都会以退出码 `2` 和结构化错误停止，且不会留下规则库输出。PDF 适配器去除重叠字形层，按双栏顺序重建文本，以书签层级和字体标题共同划分最小主题，并把检测到的表格转换为 Markdown 表格、把侧栏与资料板保留为引用块、把带明确编号或符号的页底脚注保留为 Markdown 脚注。施法字段与标题颜色、资料板字段和固定目录区域共同识别法术、状态、怪物、魔法物品及其他实体；生产基线指定的护甲、武器、装备、工具、坐骑、载具、服务与贸易商品表还会为每个命名行生成带父表路径和直接父资产引用的独立实体。无法稳定恢复的结构不会静默降级为普通正文。

固定《怪物图鉴》中的少数字体子集缺少 `ToUnicode`。构建器先把同书同字体的字形轮廓与唯一 Unicode 映射匹配，再使用生产基线中按源文件哈希、字体和 CID 固定的人工复核映射；仍有任何 `(cid:…)` 字形时构建直接失败，不以模型常识或辅助纯文字版补写。

同一固定来源中少数字体子集还带有异常的垂直字形基线。构建器只应用生产基线中按完整嵌入字体名固定的偏移量来恢复视觉阅读行，并始终使用调整前坐标识别页脚；这些偏移与源文件 SHA-256 一同受完整性门禁约束，不会泛化到其他字体或来源。

输出结构如下：

```text
<rules-library>/
├── library.json
├── index.json
├── sources.json
├── coverage.json
├── blocked.json
├── exceptions.json
├── formulas.json
├── sections/*.md
└── entities/*.md
```

每个 Markdown 单元与索引项记录稳定 ID、类别、别名、适用条件、规则状态、源书、版本、源文件哈希、章节路径、PDF 页码与页标签、正向和反向交叉引用、提取状态、内容哈希及文件哈希。`sources.json` 还记录解析器版本、结构计数，并为每个 PDF 物理页记录 `generated` 或经固定基线声明的 `visual_only` 状态；未声明空页、声明失效或精确提取快照漂移都会阻止构建。`coverage.json` 为每个单元保存来源矩阵 ID、主责 Skill、协作 Skill、权威状态、可观察结果、失败路径和验收场景。`exceptions.json` 保存构建期已经复核的具体实体例外。`formulas.json` 保存版本化确定性公式、输入与结果单位、取整依据、允许的具名修正操作、规则优先级和正文来源；两者的文件哈希都纳入规则库身份。

生产基线中的 `rule_exceptions` 必须为每项例外提供稳定 ID、具体实体与一般规则别名、同一情境的有界范围、两侧不同取值、各自正文证据、`verified` 状态和复核依据。构建器必须唯一解析两侧规则，确认双方 `extraction_status` 均为 `verified`、具体实体引用一般规则，并只在 Markdown 正文中核对证据；frontmatter 元数据不属于规则正文。任一别名歧义、`index_only` 占位项、引用缺失、证据不匹配或尚未复核都会阻止生成完整规则库。

生产基线中的 `formula_catalog` 必须为每项公式声明稳定 ID 与版本、输入范围和单位、表达式常量、结果单位、取整方式、允许的修正操作、完整优先级顺序，以及计算和取整各自的规则别名与正文证据。构建器以“别名 + 正文证据”唯一定位已验证默认规则，并把稳定规则 ID、源书哈希和页码写入公式目录。来源歧义、证据不匹配、单位或表达式声明无效都会阻止构建；运行时还会同时复核公式目录自身哈希、`library.json` 中的文件哈希和整个规则库身份。

`uv.lock` 与生产基线共同固定 PDF 解析器版本。相同输入、锁文件、基线和构建器版本会生成相同资产与清单哈希。输入、规范化映射或提取结果变化会改变来源、索引或内容哈希。任何未复核规则、无法恢复字形、精确资产漏项、结构计数漂移、断裂引用或覆盖记录缺失都会阻止质量通过。

## 运行时查询

开发目录可以显式指定规则库：

```bash
PYTHONPATH=src python -m dnd_5e rules-query \
  --library build/rules-library --id phb-cn-1.72-spell-9a2f341bc43d

PYTHONPATH=src python -m dnd_5e rules-query \
  --library build/rules-library --alias '火球术'

PYTHONPATH=src python -m dnd_5e rules-query \
  --library build/rules-library --alias 'longsword'

PYTHONPATH=src python -m dnd_5e rules-query \
  --library build/rules-library --topic '巢穴动作' --limit 10

PYTHONPATH=src python -m dnd_5e rules-query \
  --library build/rules-library --alias '行动自如' \
  --general-rule-id phb-cn-1.72-condition-d0b19d83ea08
```

`--id`、`--alias` 和 `--topic` 必须且只能指定一个。查询先验证规则库身份、内容质量、阻塞清单、叶级覆盖以及正反引用，再只打开命中的 Markdown；无关实体文件不会被读取，命中实体的文件哈希不符则拒绝返回。`review`、未知状态和仅作层级索引的 `index_only` 项不得用于权威查询。成功 JSON 包含规则库版本与哈希、结论 Markdown、适用条件、规则状态、别名、章节路径、页码、来源和交叉引用。

需要裁定实体说明与一般默认规则的冲突时，以 `--id` 或 `--alias` 选择法术、状态、怪物或物品等规则实体，并用 `--general-rule-id` 指定一般规则。运行时只接受 `exceptions.json` 中与这两个稳定标识完全匹配的已复核声明，再打开两侧 Markdown 复验正文证据。成功结果在 `rules` 中返回实体的结构化字段、来源和交叉引用，在 `general_rules` 中返回一般规则，并在 `resolution` 中保留例外声明 ID、冲突范围、两侧值、正文证据、所采用实体、被覆盖规则和“具体实体优先于一般默认规则”的顺序。普通交叉引用、frontmatter 元数据和运行时临时文本均不能授权覆盖；实体名称存在歧义、实体不完整、一般规则不是已验证默认规则、例外声明未命中或正文证据无法复验时，命令拒绝权威裁定。

安装本地预览 wheel 后无需 `--library`，运行时会从包内 `dnd_5e/rule_assets/` 定位固定资产。运行时不导入 `tools.rules_library`，不解析 PDF/XLSX，也不要求 `docs/reference/` 存在。

## 运行时确定性计算

源码开发和本地预览包都通过同一固定公式目录执行计算。当前代表入口为：

```bash
PYTHONPATH=src python -m dnd_5e recalculate /path/to/campaign \
  --expected-revision 2 \
  --idempotency-key aria-strength-modifier-v1 \
  --character aria \
  --formula ability-modifier \
  --inputs '{"ability_score":{"value":15,"unit":"ability_score"}}' \
  --modifiers '[]'
```

`ability-modifier` 来自《玩家手册》第 173 页的“属性值减 10 后除以 2”和第 7 页的向下取整规则。响应保留公式目录身份、输入、具名修正项与优先级、逐步运算和带单位结果；状态写入边界会独立复算后再提交。该纵向切片只保存已确认名册中角色的一项派生数据，不创建角色构成，也不扩大到尚未实现的完整角色生命周期。

## 本地预览 wheel

构建完成后执行：

```bash
PYTHONPATH=src python -m tools.rules_library preview-wheel \
  --library build/rules-library \
  --output-directory dist
```

预览 wheel 包含运行时代码、十一项 Skill manifest、Markdown、索引和来源元数据；不包含开发构建工具、PDF/XLSX、测试、缓存或临时文件。安装后新建战役会把该规则章节库的实际版本与哈希写入 `campaign.json` 的兼容组合。

## 三种状态与公开发布

`library.json` 分别记录：

- `content_quality`：结构、完整性、哈希、引用和覆盖门禁是否通过；
- `local_preview`：是否可以生成本机预览包；
- `public_release`：来源授权清单是否允许公开分发。

三本固定来源的公开分发授权已由仓库维护者核验，并记录在 Issue #33。使用 `--publication public` 的完整构建应显示 `content_quality: passed`、`local_preview: available` 和 `public_release: available`；生成内容可以提交到本公开仓库，但原始 PDF、标准模组样本、缓存、临时文件和个人绝对路径仍不得进入发布物。Issue #33 的其他完整覆盖、运行与整体发布门禁继续独立生效。
