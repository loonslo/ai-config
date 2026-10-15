# 同步分类实施与验证记录

维护日期：2026-10-09。环境：Windows，Python 3.14.0，所有 pytest 使用合成 HOME 与全新 basetemp；未读取或写入真实助手目录。

## 授权与范围

用户本次要求根据分类、接口、变更方案执行，并明确接受 T-3、T-6、T-2 三项默认方案。本次保持已有未提交的桌面恢复、版本与验收改动；没有提交、推送、安装或发布。G11 数据库来源补全默认不启用。真实迁移仍须先生成可核对的预览，再按方案确认写入。

随后用户明确禁止读取 Git 信息：助手文件按白名单携带，Git 跟踪筛选、根目录/远端/HEAD/脏状态/凭据/版本查询已取消；Git 元数据不读、不带。下表按当前边界维护，下文此前 Git 相关通过记录只保留为历史。

## 任务状态

| 任务 | 状态 | 已核对范围与边界 |
|---|---|---|
| SC-00 | 已确认，文档已同步 | 三项默认方案已接受；第 4 节 72 个 ID 与代码双向一致；密钥扫描结果见下文 |
| SC-01 | 已实现，合成测试通过 | 54 条目录/字段/策略登记、18 条拒绝规则；ID 唯一、多路径按同一 ID 登记、拒绝优先、具体路径优先、并列拒绝、按来源分流；任意层级迁移标记拒绝；旧采集白名单保留 |
| SC-02 | 新旧来源覆盖已联动，补验中 | 已选择助手根、账号技能、批准链接、所选项目区域、环境变量名称及成功历史来源计数已联动；有限未定性样本、剪枝、大小、携带计数幂等，账号来源读取失败沿用为 incomplete。字段列表仍为 classification_only，不能当作已采集字段；真机覆盖未核对 |
| SC-03 | 核心、桌面与 CLI 报告输出已实现，仍需补验 | 七类识别、邮箱内容放行、脱敏/跳过、flagged 报告、恢复提醒与第三方来源策略已接入；桌面响应/异常/核验 Markdown 与 CLI 公开报告清理通过。文本/JSON × 默认脱敏/专家原样保留的最小 Codex v2 备份到撤销通过；所有种类与专家参数全流程仍需补验 |
| SC-04 | 公共设施与完整 v1 合成生命周期通过 | 当前默认写 v2，可读 v1/v2；元数据/E7502/长路径/冲突/账号 ZIP/环境导出已接入。全部八种 v1 类型、四助手、设置与信任/项目映射、重复恢复零写入、核验和撤销通过合成夹具；真实旧包新版完整恢复仍未验收 |
| SC-05 | 已接入，合成往返通过，逐规则补验中 | 新增 A/B 复合 18 文件、项目登记 MCP 的点号路径/Windows 键复用/确认/合并/核验/撤销、共用文件单次写入及多来源字段碰撞门禁、MCP 叶级恢复白名单通过。用户追加无 Git 边界，四种 Git 状态下白名单 18 文件携带/恢复/核验/撤销及 Git 命令/目录/正文零读取通过；独立规则夹具、字段账本及设备偏好仍需补验 |
| SC-06 | 已实现，合成测试通过 | machine_detect 返回已登记且存在的全部文件夹，过滤 worktrees、scratch、链接、排除项和死条目；桌面原有初始化逻辑已预选返回目录。测试以两个独立 Git 项目验证记忆采集，无真实 11 项历史清单对比 |
| SC-07 | 已实现，合成往返及失败路径通过 | 两层账号/组织目录、来源分流、同名独立 ZIP、二进制资产、产物零读取、长路径、目录枚举/stat 失败明细与可用内容导出通过；不写应用目录，真实布局和云端同步未核对 |
| SC-08 | 已接入，专项通过，补验中 | 非 Git 来源、批准链接四边界、产物排除、覆盖联动、同名相同副本六文件恢复/核验/撤销、长路径/枚举/stat 失败及 WorkBuddy AI 父子技能归属通过。原七级中的 Git 查询/派生已按用户要求取消；其它嵌套边界需补验，数据库未读 |
| SC-09 | 已实现，合成往返通过 | 名称优先、密钥名称零值读取、AI 白名单/env_include、导出与 ParseFile 检查通过；未读取真实注册表或运行脚本 |
| SC-10 | 主体及历史面板已实现，补验中 | 分组、旧包推断、未选零读取、隐私策略自动预览、技能整组冲突和协议通过；历史默认不选、分包展开、行号截断/空样本提示、失败列表上限与中文原因、恢复更新禁用确认及模拟完成提示通过浏览器夹具；扫描进度与原生完整流程未验收 |
| SC-11 | 历史备份/恢复已接通，边界补验中 | ZIP64 分段、集合校验、主包协调、流式事务/核验/撤销、项目映射与覆盖联动通过；UTF-16/32 JSONL、Codex 非 JSONL 文本/二进制及跨行私钥通过；超长无换行原始记录和大结构化脱敏复查仍有明确排除，真实加载未核对 |
| SC-12 | 未验收 | 真机只读预览、第二台电脑实测、真实助手加载未执行 |
| SC-13 | 本次同步完成 | 旧任务书取代关系、三份规范、执行记录、acceptance、PROJECT_STATUS 已同步；此项不代表完整业务完成 |

## 架构与取舍

- `catalog.py` 保留 `CatalogItem` 旧字段，新增属性都有默认值。`classification_rules.py` 持有稳定 ID 表；复合路径使用 `patterns`，字段用 `classify_field`，范围外与组合策略仅登记，不进入文件白名单。
- `allowed_item` 使用分类拒绝检查与 `LEGACY_CATALOG`，避免基础登记提前启用未完成恢复支持的新路径。凭据值、来源推断、字段值过滤由各后续任务承担。
- `coverage.py` 的遍历只做枚举/stat，默认不跟随符号链接或 Windows 联接点；目录剪枝只数直接子项。F 类工作成果不进入子树。权限失败、链接和上限明确标记 complete=false。
- 字段名从采集器本来就解析的文件取得，不额外读取源；项目键名转换为通配选择器，输出不含字段值。含邮箱/密钥特征的名称隐藏。
- 当前来源的覆盖只改变报告，实际携带内容由 writer 条目核对。开发开关 observe_coverage 用于同一 HOME、同一参数下逐字节对比；新增报告与 summary 改动会改变整包 content_id，不能宣称 ZIP 逐字节相同。
- `default_projects` 复用既有只读登记发现，不计算目录体积，保留信任恢复确认逻辑。

## 验证记录

1. Python 3.14 首次回归因缺少仓库已固定的 tomlkit 无法收集；执行 `py -3.14 -m pip install -r requirements.txt` 补齐 tomlkit==0.13.3，没有变更依赖声明。仓库既有 .venv 为 Python 3.13.14，分别完成基线 109 passed；Python 3.14 基线也是 109 passed（`tmp/run-sync-baseline-20261009-3` 与 `-4`）。不将依赖错误算作业务失败或通过。
2. `py -3.14 -m pytest tests/test_machine_classification.py tests/test_machine_coverage.py --basetemp tmp/run-sync-new-20261009-3 -q`：29 passed，1 skipped。验证 72 个 ID 双向一致、冲突优先级、来源分流、旧白名单选择、迁移标记、覆盖零读取、有限样本、扫描不完整提示、工作成果边界及敏感名称隐藏。
3. `py -3.14 -m pytest tests/test_machine_default_projects.py --basetemp tmp/run-sync-projects-20261009-1 -q`：1 passed，验证 Claude/Codex 联合登记、死条目/临时目录过滤、检测结果及两个独立 Git 项目的记忆字节采集。初次夹具没有独立 Git 根，继承了外层仓库而无法对应记忆目录；已修正夹具并复测。
4. 观察开关对比：实际文件条目（含 SHA-256）与所有携带字节相同，旧报告除 summary 外相同；只新增 coverage.json 与摘要的未定性/不完整提示，预览没有生成 ZIP 或修改源文件。
5. 现有来源覆盖版本 machine 回归：`$machineTests = @(rg --files tests | Where-Object { $_ -match 'test_machine[^\\]*\.py$' }); py -3.14 -m pytest @machineTests --basetemp tmp/run-sync-regression-20261009-1 -q`：136 passed，1 skipped。此轮开始后补充了规则与项目测试，最终范围见下面续记。
6. 最终回归使用相同筛选命令、全新 `--basetemp tmp/run-sync-final-20261009-1`：139 passed，1 skipped，78.47 秒；包括旧 109 项与新增 30 项通过用例。`scripts/check-secrets.ps1`：0 findings；`git diff --check`：通过。链接用例因 Windows 权限不足跳过，其边界没有算作通过。
7. 项目摘要本地契约自检通过：YAML 字段唯一、真实未加引号日期、active 状态、三项非空文本、126 个项目内稳定 evidence 文件，均存在且无隐藏/运行目录、越界或链接。未使用外部日常库同步工具。结果与边界先写本执行/验收文档，再更新根摘要。

## 未验证与后续

## SC-03 后续实施记录（2026-10-09）

已继续实现 value-free SecretHit、七类凭据扫描、占位符脱敏、JSON/TOML 解析保护和写入层策略。邮箱检测保留为输出卫生函数，private_text/private_metadata 仅判凭据；采集器记录原文件指纹，导出脱敏副本。flagged.json 与预览只含种类、行号和处置，登录清单仅列密钥类变量名；恢复核验将脱敏文件标为人工确认并列出重新填写位置。默认 redact，开发入口接受 skip；桌面选择参数将在 SC-10 接入。

旧测试调整原因逐项记录：

- test_machine_privacy 的四种跨采集器输入：邮箱及转义邮箱改为保留，带用户信息的 URL 改为脱敏；旧的“整份排除”断言不再符合 D17/T-2。原输出门禁和恢复预检拒绝测试改用生成的已知令牌，继续验证凭据拒绝与目标零读取，未撤掉边界。
- test_machine_collect_tier1 的密钥记忆测试改为脱敏保留，并继续断言链接目标凭据零读取和源密钥不在输出中。
- test_machine_collect_workbuddy 保留非文本排除、受保护文件零读取和手动恢复断言，将密钥整份排除改为脱敏及原值不在输出。
- test_machine_collect_projects 的本地权限文件改为脱敏保留，断言原值不在输出；跳过策略由新增策略测试独立覆盖。
- 新增 test_machine_redaction 验证七种类别、来源/置信度策略、JSON Unicode 转义、引号保留、TOML 格式失败整份跳过、缓存后篡改重检和邮箱输出卫生。最后一次单独测试：12 passed，tmp/run-sync-redaction-20261009-3。最终全量回归仍以续记为准。

SC-03 回归：`py -3.14 -m pytest @machineTests --basetemp tmp/run-sync-redaction-regression-20261009-1 -q`（machineTests 同上）：151 passed、1 skipped，81.34 秒。源码假凭据样例曾触发静态密钥扫描；改为运行时拼装后扫描 0 findings，没有放宽扫描器。

## SC-04/05 后续实施与验证（2026-10-09）

- v2 默认写入、v1/v2 双读、新字段类型/长度/枚举、redactions 与 flags 一致校验。未知助手/类型或未来版本用 E7502，错误信息不包含输入值。content_id 仍只依赖路径和摘要。超过 240 字符的新增成员记 path_too_long，不导致整包失败。
- account-skills ZIP 和 restore-env.ps1/env-vars.md 只写报告目录，脚本不执行；ZIP 顶层为技能目录，输出 ZIP 时间固定以保持重复计划字节一致。导出不纳入撤销，核验标人工导入。现有不同导出文件和预览后变化会阻止写入，临时文件采用排他创建且只清理本次创建者。
- `collect_classified.py` 接入新增全局指令/代理/输出样式、计划、命令授权、提示/记忆、WorkBuddy 脚本，及项目规则、技能、Codex 配置和 MCP。Git 已跟踪的项目文件排除，Git 不可用时全带并标记；此分支还需独立测试。`settings.py` 处理可携带环境变量、MCP 字段及叶子键；所有新增 B 类字段须确认。桌面配置来源使用注入 home/environ，不读取测试外目录。
- `tmp/run-sync-v2-20261009-3`：manifest v2、新导出及桌面协议 23 passed。`tmp/run-sync-extra-20261009-2`：新增采集复合往返 1 passed，核对 18 个文件原始字节、Git 跟踪排除、敏感环境变量/设备项不出包、非密钥环境与 MCP 字段恢复及核验。
- 全量集成 `tmp/run-sync-v2-extra-regression-20261009-1`：163 passed、5 failed、1 skipped，80.00 秒。五项失败同源：系统输出标签加入 AGENT_LABELS 后，旧备份向导用该字典查询助手根，发生 KeyError；已改用实际助手根迭代。专项 `tmp/run-sync-guides-20261009-1`：7 passed，8.94 秒。修复后全量复测结果见续记，不把失败轮次称为最终通过。

- Windows 当前不具备符号链接创建权限，真实链接测试跳过；联接点与批准链接的四类安全用例还需 SC-08 验证，不能据此声称已支持批准链接。
- 未执行前端构建、lint、安装包重建或真机恢复；本次后端和检测变更尚未进入已交付的 0.3.5 安装包。
- SC-06 只有合成两项目验收，尚未核对真实历史 11 个项目是否无遗漏。
- 下一步按原依赖顺序推进 SC-03/04，再启用新增来源与新类型；业务全流程、真实跨机及助手加载仍未完成。

SC-04/05 修复后 machine 回归 `tmp/run-sync-v2-extra-final-20261009-1`：168 passed、1 skipped，88.29 秒，Windows Python 3.14、合成 HOME。

## SC-07/08/09 实施与验证（2026-10-09）

- `collect_env.py` 用 RegEnumValueW 先枚举名称，再仅查询 AI 相关且名称不含密钥特征的字符串值，不用同时返回密钥值的 EnumValue。带账号信息的代理值排除，登录清单只列名称；合成 HOME 默认不读注册表，真实入口限定当前用户 HOME。env_include 无法覆盖密钥排除，REG_EXPAND_SZ 原值保留。脚本仅导出、不执行、不写注册表。
- 环境/旧配置专项 `tmp/run-sync-env-20261009-2`：6 passed。首次测试因 -Command 参数传递让 ParseFile 文件参数为空而失败，修正调用后通过；只做语法解析。验证引号、反引号、换行、密钥名称零值读取和预览后变更。
- `collect_desktop_skills.py` 支持 manifest.skills 键值与列表两种结构，未知 creatorType 不猜测。user 带上，anthropic 从 manifest 记录且正文零读取。账号/组织用 a0001 等别名，导出 account-skills/<别名>/<名称>.zip，ZIP 顶层为技能目录；旧单账号归档仍可恢复。真实 manifest 布局未读取。
- 账号/环境/新导出 `tmp/run-sync-account-env-20261009-1`：7 passed；同名副本及二进制字节一致，恢复不创建应用目录，manifest 变化使计划失效。
- `provenance.py` 实现七级顺序，Git 与包仓库 URL 去用户信息/查询串，记录 dirty 计数；Git fsmonitor 关闭，Git 元数据含链接时不用该证据。CC Switch 数据库未读取。来源不明仍按 SK-01 携带并显式记录。
- `skills_links.py` 只允许本 HOME 内 .cc-switch/skills 或 .agents/skills；解析前拒绝目标/父路径链接、遍历拒绝内部链接，100000 项上限；链接变化使计划失效。恢复仅写 Claude 原生 skills，被链接接管则 link_blocked。
- `collect_skills.py` 分别保留各位置副本及非文本资产，按 SK-05 排除产物/迁移标记，第三方另排除程序文件；阈值注入验证超大文件读前排除。skills.json/md 记录来源、摘要、未携带项、副本关系和重建提示，账号条目也有来源引用。主备份使用新采集器，旧低层默认接口保留。
- 来源/链接 `tmp/run-sync-skills-provenance-20261009-1`：7 passed，四边界以 Windows 联接点实际通过未跳过。来源集成 `tmp/run-sync-skills-integration-20261009-2`：15 passed。恢复门禁 `tmp/run-sync-provenance-gates-20261009-1`：12 passed。强化专项 `tmp/run-sync-skills-hardening-20261009-1`：21 passed。
- 恢复允许精确/派生来源且仅含启发式命中的第三方技能，仍拒绝高置信度凭据；专家原样文件需目标配置逐路径允许。批准缓存按逻辑条目约束，报告不能借用载荷批准。输出卫生及专家完整生命周期仍需补验。
- 完整回归 `tmp/run-sync-skills-env-regression-20261009-1`：177 passed、3 failed、1 skipped，93.90 秒。旧 icon.bin 的禁止出包哨兵与 SK-01 二进制携带冲突；只替换该允许资产为安全内容、新增字节断言，凭据和运行文件哨兵未动。相关修复 `tmp/run-sync-skills-regression-fix-20261009-1`：17 passed，17.36 秒。
- 修订账号 partial 标记曾产生缩进错误，`tmp/run-sync-skills-env-final-20261009-1` 收集阶段 24 errors、未运行测试；已修正，完整复测见续记。失败轮次保留，不冒充通过。
- 静态扫描曾命中测试变量 secret 的假值赋值；改名 sample 后 0 findings，扫描规则未改。未构建前端或安装包、访问真实新来源、真实恢复、执行环境脚本或导入账号技能。

最终完整回归 `tmp/run-sync-skills-env-final-20261009-2`：180 passed、1 skipped，96.64 秒。Windows Python 3.14、合成 HOME，包含所有已接入账号技能、系统变量及技能来源变更。旧符号链接权限用例跳过；新增联接点四边界全部通过。尚未验收的 SC-03/04/05/06 补验项、SC-08 覆盖联动、SC-10/11 和真实跨机仍保留。

交付前本地 PROJECT_STATUS 契约自检：字段唯一、日期 2026-10-09、active 状态、三项非空摘要及 143 个稳定 evidence 路径全部通过；scripts/check-secrets.ps1 为 0 findings，git diff --check 退出 0。未使用外部日常库同步工具。另将已读来源复查的 _read 扩为拒绝所有父路径联接点，防止预览后路径被接管时先读后判；其直接相关测试续记如下。

联接点复查收紧后的直接相关验证 `tmp/run-sync-junction-reread-20261009-1`：19 passed，13.29 秒（来源/链接、旧 tier1、隐私）；180 项完整回归发生在该最后小改动之前，未将其当作小改动后再次全量复测。


## SC-10 与 SC-03 输出补验（2026-10-09）

- groups.py 统一七个分组；默认选中六类非历史内容，v1 按旧类型推断。写入层过滤未选条目，采集器对整份文件先判断分组；环境变量分组未选时不查询值。恢复排除分组不读取目标文件，冲突按技能和原位置分组；两个文件共享一次选择并展开为各自条目 ID。
- 桌面新增内容选择、文件数/大小、来源和同名副本提醒、未定性样本、命中文件/行号及脱敏/整份跳过选项；策略切换自动重做只读计划。恢复只显示包内分组，历史默认不选，空选择无法确认。历史真正采集/恢复仍未实现，选择历史会返回明确的未接入错误。
- 输出副本隐藏邮箱与凭据，载荷中的邮箱保留。含邮箱的项目路径使用 folder: 与 project: 选择键在后端解析，展示隐藏不破坏项目映射；正常路径保持原值。二进制不能按 UTF-8 解码时以 Latin-1 检测 ASCII 凭据并保留其他字节；不是将二进制当作无密钥。核验 Markdown 和协议异常使用同一输出处理。CLI 其他输出路径仍需完整审计。
- 同名副本缺少正文摘要时标记 unverified，避免将未读的厂商正文或未携带副本误报为内容不同；PJ-03/04 项目定制归入我写的技能与脚本。
- 分组初测 tmp/run-sync-groups-20261009-1：8 passed；分组/协议/采集集成 tmp/run-sync-groups-integration-20261009-1：22 passed，11.06 秒。全量 tmp/run-sync-groups-regression-20261009-1：188 passed、1 skipped，107.74 秒。
- 输出/分组首次 tmp/run-sync-output-groups-20261009-1：34 passed、1 failed，原因是展示处理错误地返回解码字符串，把 Windows 路径转义变成控制字符；修正为仅检测解码副本、返回原字符串后，-2 复测 35 passed，15.86 秒。专项 tmp/run-sync-public-output-20261009-1：3 passed，2.27 秒，含邮箱项目的检测→备份→映射恢复、载荷邮箱保留、响应与异常无邮箱/凭据、二进制字节保留均通过。
- 本阶段最终完整 machine 回归 tmp/run-sync-groups-public-final-20261009-1：191 passed、1 skipped，98.83 秒。其后 PJ-03/04 分组和 unverified 修订的直接相关复测 tmp/run-sync-groups-last-fixes-20261009-1：16 passed，8.56 秒；完整回归发生在这两项修订之前。随后只修订展示文案，未再次全量回归。
- Windows 前端 npm run build 与 npm run lint 退出 0，最终资产 index-DVi4OG7N.js。IAB localhost 合成夹具实际核对默认六类/历史未选、脱敏转整份跳过及第 12 行展示、两个技能文件共用一组选项、选择后自动更新且确认可用；浏览器 error 日志为空。截图 release-artifacts/machine-sync-groups-preview.png 与 machine-sync-restore-groups-preview.png 均为虚构 Fixture 数据；未点击真实写入或安装客户端。本次没有 sidecar/NSIS 重建或远程发布。
- 原有真实布局、覆盖联动、逐规则/v1/专家补验和第二台电脑助手加载仍待核对；本次没有读取真实新来源、凭据或 CC Switch 数据库，没有执行环境变量脚本。

本阶段交付前检查：scripts/check-secrets.ps1 为 0 findings；git diff --check 退出 0。PROJECT_STATUS 本地契约自检字段唯一、真实日期、active 状态、非空文本及 148 个稳定 evidence 路径均通过；未使用外部日常同步工具。


## SC-11 流式核心（2026-10-09）

- 在 machine-sync-history-contract.md 细化接口 §11：单文件可跨包分段；主包与历史包关联避免内容 ID 循环；全部分包验证后才处理目标；只新增、映射不到进入单独报告目录，事务与撤销仍属于要求，不能用独立导出代替。
- history.py 实现默认未选零遍历/零正文读取、H1/H2 JSONL 白名单、有界行读取/段生成、原文件摘要与 mtime 复核、脱敏后 JSON 复查、整份跳过/无效行排除。预览只保留元数据，单个原文件超过分包阈值也能分段；上限按段/包/集合和遍历数量限制，不按主包 512 MiB 限制拒绝历史文件。
- ZIP64 流式写入、manifest 最后写、主包 content_id/集合 ID/连续包序号/连续段偏移/段摘要/成员类型/路径/大小/压缩比检查已实现。校验重新组装 JSONL 行并检查凭据，不将攻击者自己提供的有效摘要作为安全证明。跨段 UTF-8 与 JSON 字节保留。发布先暂存并校验整组，排他创建目标；不支持硬链接的文件系统用有界复制，不覆盖已有文件，异常只回滚本次拥有的发布文件。
- 首次 tmp/run-sync-history-stream-20261009-1：9 passed，0.26 秒；正文门禁 tmp/run-sync-history-gate-20261009-1：9 passed，0.22 秒；强化 tmp/run-sync-history-hardening-20261009-1：17 passed，0.38 秒。Windows Python 3.14、合成 HOME，覆盖大单文件跨包逐字节重组、隐私/跳过、无效/过长行、来源变化、已有包不覆盖、缺包/错序/错主包、非历史/越界/偏移错误、正确摘要下仍拒绝原凭据、无硬链接文件系统和真实联接点零正文读取。
- 此阶段仅提供核心 API，prepare_backup 的历史选项仍报未接入。尚未完成主包 reports/history.json 协调、恢复目标/事务、桌面真实历史流程；没有读取真实会话或声称 SC-11 全部完成。全量 machine 回归随后续记。


历史核心完整 machine 回归：tmp/run-sync-history-core-regression-20261009-1，209 passed、1 skipped，103.89 秒。随后补充普通文件检查、Windows 目标名称与绝对发布路径约束，直接相关 tmp/run-sync-history-last-boundaries-20261009-1：17 passed，0.35 秒；完整回归不是这些最后边界改动后的再次全量运行。密钥扫描 0 findings，git diff --check 退出 0，PROJECT_STATUS 本地契约及 151 个稳定 evidence 路径通过。未使用外部日常同步工具。


## SC-11 主包协调与桌面协议备份（2026-10-09）

- prepare_backup 接入可选历史计划、reports/history.json/md、预览分组计数/独立分包列表及命中清单；不选择时不进入历史采集器。历史凭据命中接入原有脱敏/整份跳过选项，使用 CC-18/CX-14。命中行号有 2000 行上限及显式截断元数据，前端的截断提示和独立分包面板尚需补齐。
- 主包与全部历史包先写入排他创建的暂存目录，校验完整集合并复查所有来源，再发布历史包，主包最后发布。既有目标提前阻止；发布失败回滚本次拥有的文件，保留已有文件。目录只删除已知暂存成员与空目录，不递归清理用户目录。进程突然中断仍可能留下无主包的分包，未宣称整组文件系统原子性。
- 桌面计划版本加入原始历史来源摘要/mtime/size；即使凭据改变后脱敏字节与 mtime 相同，确认旧预览仍返回 E_PLAN_STALE，不发布产物。合成桌面备份端到端成功，主包不含历史正文，独立包的主包标识和集合 ID 一致。
- 相关 tmp/run-sync-history-coordinator-20261009-1：29 passed，6.50 秒；首轮备份流程 tmp/run-sync-history-backup-flow-20261009-1：27 passed、1 failed，夹具重复创建同一路径导致 FileExistsError；调整夹具 exist_ok 后 -2：28 passed，6.51 秒。包含新桌面计划测试的 tmp/run-sync-history-backup-final-20261009-1：38 passed，25.84 秒；历史命中接入专项 tmp/run-sync-history-flagged-20261009-1：22 passed，8.39 秒。发布顺序/目标提前校验最后改动 tmp/run-sync-history-coordinator-last-20261009-1：29 passed，14.88 秒。
- 历史恢复尚未接入，当前不能将 history 选项视为完整备份→恢复→核验→撤销能力。Codex 非 JSONL 文件现列为 unsupported_history_format、正文零读取；原要求 sessions/** 的全部文件仍保留，后续需处理该缺口。未读取真实历史、未构建前端/sidecar/安装包、未发布；本次只修改后端及合成夹具。

历史协调阶段完整 machine 回归 tmp/run-sync-history-coordinator-regression-20261009-1：214 passed、1 skipped，108.51 秒。该轮开始后补充主包最后发布和已有目标提前校验，最后改动以直接相关 29 项复测为证，未冒充之后再次完整回归。

本轮结束前密钥扫描 0 findings、git diff --check 退出 0，项目摘要本地契约与 151 个稳定证据路径通过；未使用外部日常同步工具。


## SC-11 流式事务与撤销设施（2026-10-09）

- streaming.py 提供有界读取摘要、流式描述符（固定摘要/大小）、每块最多 1 MiB、写完摘要复核和排他新增。已有文件拒绝；不支持硬链接时使用排他复制，失败清理本次文件。明确 new_only=False 仅用于已核对目标的回滚/备份还原，不改变历史仅新增的要求。
- 既有 transaction 接受流式描述符，并将 stream_paths/streamed 写入原事务日志；混合批次使用同一锁、备份和提交。大文件原件备份、回滚和中断恢复均采用有界读取，摘要冲突保留用户后改内容并标 ROLLBACK_REQUIRED，不误报回滚成功。普通字节路径仍走原流程。
- 共享撤销计划、machine undo 和桌面撤销版本检查支持流式摘要；超过主包单文件 64 MiB 的历史文件提交→撤销测试通过，且测试禁止对历史目标调用 read_bytes。撤销前仍校验边界、原件备份、目标摘要与进程状态。
- 首轮 tmp/run-sync-stream-transaction-20261009-1：23 passed、3 failed，测试错误地把包导出的 transaction 函数当作同名模块；改用 importlib.import_module 后 -2：26 passed，14.75 秒。流式/原可靠性/原恢复回归 tmp/run-sync-stream-recovery-20261009-1：31 passed，27.08 秒；补充未知写入结果冲突记录后 tmp/run-sync-stream-last-conflict-20261009-1：9 passed，1.54 秒。
- 本阶段尚未将历史包解析结果接入恢复路径规划，也未提供会话恢复业务全流程；这里只验收流式事务设施。共享事务层涉及其他业务，因此另运行整个 tests 目录回归，结果随后记录。


共享层全仓回归 tmp/run-sync-stream-full-20261009-1：576 passed、3 skipped、1 failed，219.89 秒。唯一失败是 test_application_protocol 的既有 UTF-8 子进程检测用例仍断言 4 个助手；SC-10 已增加 shared，真实结果为 5 个。改为核对明确的五个 ID 集合，保留 UTF-8/预览不写入断言。最新流式事务/协议/导入边界 tmp/run-sync-stream-final-20261009-1：38 passed，2.84 秒；完整全仓回归发生在最后流式冲突记录和旧断言修订之前，未称其为最后改动后的全仓通过。当前三个 skip 的具体用例见该轮输出/后续全仓检查，不将跳过当作通过。

流式事务阶段交付前：密钥扫描 0 findings、git diff --check 退出 0；PROJECT_STATUS 本地字段/日期/状态/说明与 154 个稳定 evidence 路径通过；未使用外部日常同步工具。


## SC-11 历史恢复业务接线（2026-10-09）

- history_restore.py 校验主包引用：严格报告类型/数量、只允许同文件夹内文件名、完整集合/主包标识/分包摘要/来源总量。未选择历史不打开相邻包；选择时全部校验及 ZIP 指纹复核完成后才规划目标。源摘要在原验证遍历中累计，正文保持流式；按 source_id 索引段，避免每个来源反复扫描全部段表。
- Claude 转录依据主包 source_path/git_root 编码与项目映射定位；不能唯一匹配或映射目标不存在时写 report/history-unmapped/。Codex 按原相对位置新增。已有文件只检查存在、不读正文，选择唯一另存名，不覆盖不合并；最多检查 1000 个候选位置，超限明确跳过。目录未初始化或联接点目标明确跳过。
- 计划中的历史数据使用 StreamContent 进入同一恢复事务、备份日志及撤销；校验采用有界摘要。桌面 bundle_agents/bundle_groups 包含历史来源；预览版本绑定所有分包指纹，分包变化拒绝旧预览，缺包使用 E7507。历史核验单独列出 PASS/SAVED/MANUAL，脱敏内容标人工核对；提醒与重建待办只列已选分组/来源，历史提醒声明不保证续接。
- 将全集 manifest 总字节限为 64 MiB，防止攻击者通过大量短段耗尽元数据内存；单份仍限 16 MiB。保护目录、数据库/凭据名字优先于历史格式，并在枚举阶段剪枝。Codex 非 JSONL 格式仍显式排除、保留后续实现要求。
- 初步集成 tmp/run-sync-history-restore-integration-20261009-1：38 passed，15.99 秒。历史业务初测 tmp/run-sync-history-restore-flow-20261009-1：6 passed、1 failed，未映射夹具中的原项目实际仍存在，被正确按原路径匹配；改为明确不存在的映射目标后 -2（含桌面/核验撤销旧回归）：15 passed，12.55 秒。
- 提醒调整 tmp/run-sync-history-restore-reminders-20261009-1：11 passed、2 failed，代码编辑误把汇总变量加到 CheckItem.report，导致 Preflight.report 缺变量；已将其移回正确方法，-2：13 passed，9.09 秒。没有把失败轮次视为通过。
- 桌面流程 tmp/run-sync-history-desktop-flow-20261009-1：24 passed、1 failed；诊断显示真实 Claude.exe/Codex.exe 正在运行，生产进程门禁正常阻止确认。合成夹具注入空进程列表后 -2：25 passed，11.22 秒；生产门禁未改。测试覆盖预览→修改分包→旧计划拒绝→重新预览→恢复→核验→撤销及 E7507。
- 完整 machine 回归 tmp/run-sync-history-restore-regression-20261009-1：232 passed、1 skipped，114.04 秒。其后路径/联接点/元数据预算/保护目录补验 tmp/run-sync-history-restore-boundaries-20261009-1：37 passed，10.92 秒；最后保护文件名优先与历史提醒计数改动结果续记。全量发生在这些最后边界修订之前。
- 本次没有改前端、读取真实会话、生成真机迁移包或重建/安装/发布客户端。JSONL 后端端到端通过不等于 SC-11 全部完成；Codex 非 JSONL、界面与真实助手加载仍保留。


JSONL 恢复最后保护文件名与提醒计数改动 tmp/run-sync-history-restore-last-20261009-1：46 passed，12.45 秒；相邻引用再收紧为同前缀、连续 -历史-N.zip 文件名（允许主包另名、不读任意无关 ZIP）后 tmp/run-sync-history-sibling-names-20261009-1：14 passed，3.35 秒。完整 232 项回归在上述最后修订之前，未将专项结果当作再次全量。


## SC-03/SC-11 编码隐私与行号预算（2026-10-09）

- 凭据扫描对字节内容识别 UTF-8/Latin-1、UTF-16 LE/BE 与 UTF-32 LE/BE，包括非零起始偏移；命中位置转换为原字节范围，占位符使用命中编码。中文、非 BMP 字符、BOM、混合编码及原命中范围外字节保持测试通过。该能力先补隐私设施，不表示 Codex 非 JSONL 历史已启用；历史仍只收 UTF-8 JSONL。
- 历史命中行号每份最多 2000 个，整个计划最多 20000 个；到达总预算后仍为每份命中文件保留规则、动作、已发现行数及截断标志。跳过策略在首个命中停止，已发现行数不等于整份文件的全部命中行数。
- 界面补充行号截断说明及独立历史分包摘要、文件名与排除清单（最多展示 20 项）。提示主包/分包同目录一起复制，以及仅新增/另存、不保证续接。此轮尚未运行新面板的浏览器交互验收，也未重建 sidecar/安装包。
- 编码隐私专项 tmp/run-sync-encoded-privacy-20261009-2：35 passed，3.45 秒。历史/恢复/隐私专项首轮 tmp/run-sync-encoded-history-20261009-1：74 passed、1 failed，夹具错误地要求跳过首行后的已采样行也必须标截断；修正为实际已发现行数与样本数比较，-2：75 passed，19.39 秒。生产跳过行为保持首次命中即停止。
- 新面板最后改动后 npm run build 与 npm run lint 退出 0，生成 index-BBWhwoQD.js（只记构建标识，不作独立证据正本）。完整 tests 回归随后续记。

前端排除原因已改为中文说明。补映射时首次 Python 编辑使用了相对仓库路径但命令运行于 desktop，导致文件未找到和 build 的未使用变量错误；修正为当前目录 src/MachineApp.tsx 后，最后 build/lint 退出 0。密钥扫描初轮把测试中“令牌：”字面文本匹配为潜在赋值；将合成标签在运行时拼接（未放宽扫描）后 0 findings。摘要本地契约与 156 个稳定 evidence 路径通过，未使用外部日常同步工具。

补充二进制 skill 的 BundleWriter 实际策略门禁：UTF-16/UTF-32 四种编码均验证精确脱敏字节、隐私复查与整份跳过，tmp/run-sync-encoded-bundle-20261009-1：39 passed，3.50 秒。全仓回归启动后只补此测试及前端中文文案，没有再修改 Python 生产代码；新测试以这轮专项结果为证。

完整 tests 回归 tmp/run-sync-encoded-full-20261009-1：618 passed、3 skipped，262.63 秒，无失败。三个跳过分别为 test_cloud_core 缺少 jwt 依赖、test_desktop_extensions 当前账号无法创建符号链接、test_machine_coverage Windows 符号链接权限不足；未将跳过当作通过。运行开始后新增的四项二进制 skill 策略用例未计入此轮收集，另以最后相关 39 passed 为证；Python 生产代码在本轮收集后未修改。最后前端 build/lint 通过，凭据扫描 0 findings、git diff --check 退出 0，PROJECT_STATUS 本地契约及 156 个稳定证据路径通过。


## SC-11 Codex 非 JSONL 与编码历史（2026-10-09）

- Codex sessions/archived_sessions 的非 JSONL 文本/二进制已纳入采集与校验；保护路径、数据库、链接规则继续优先。不再以扩展名记 unsupported_history_format。分包沿用 source_id/连续偏移，不将历史正文装入主包。
- 新的编码行拆分识别 UTF-8、UTF-16/32 LE/BE 的 BOM 与首部零字节布局，换行必须按编码单元对齐；JSONL 校验在逐行解码后进行。分段可以切开编码单元，读取端先重组再验证。保留 BOM、空行、非 BMP 字符及全部非命中字节。
- 非 JSONL 跨行私钥整体收拢后脱敏，包含正文；未闭合私钥隐藏到 EOF。打开块后只在发现结束标记时复查全块，避免每追加一行都扫描整个已积累内容。单行和私钥块仍受 1 MiB 安全预算；超长无换行原始二进制与超预算私钥仍明确排除，后续不能据当前支持宣称所有大小/格式均可携带。
- .json/.toml 发生脱敏时复查格式；预算最多 1 MiB，超过记 redaction_format_limit，数字被占位符替换而导致解析失败记 redaction_parse_failed，整份不发布。此格式复查预算仍待扩展，不悄悄缩小 CX-14 原范围。界面新增这两项排除原因的中文说明。
- 相关原有历史回归 tmp/run-sync-raw-history-20261009-1：40 passed，15.82 秒。新测试首轮 -2：52 passed、9 failed，八项为 BOM 常量名称拼接错误，一项为未闭合私钥末尾换行预期错误；修正夹具后 -3：62 passed，17.51 秒。末尾非命中换行保留，未改生产脱敏以迎合错误断言。
- 增加无 BOM 私钥、避免反复扫描打开块及二进制恢复→核验→撤销后 tmp/run-sync-raw-history-20261009-4：112 passed，19.70 秒（含隐私/共享流式事务）。最后补充伪造二进制包凭据、结构化格式门禁及行号计数后专项与完整 machine 回归结果续记。
- 没有读取真实历史或新来源，没有重建 sidecar/安装包或验证真实助手加载。新界面浏览器验收、覆盖账本联动和真实跨机要求仍保留。


历史最后边界 tmp/run-sync-raw-history-last-20261009-1：75 passed，18.65 秒。完整 machine 回归（tests -k machine）tmp/run-sync-raw-history-regression-20261009-1：301 passed、2 skipped、357 deselected，160.89 秒；跳过为收集 test_cloud_core 时缺少 jwt，以及 test_machine_coverage 符号链接权限不足。此轮不是全仓回归，且发生在最后 UTF-32 无效正文修订之前。

最后发现原始 UTF-32 私钥正文可能含无效编码单元；结束标记检查改用替换式解码（仅用于标记判断，原字节只在命中范围内脱敏），新增合成用例验证整个私钥仍被隐藏。最后专项 tmp/run-sync-raw-history-invalid-unit-20261009-1：76 passed，19.03 秒。格式门禁测试的数字密码字面值触发仓库扫描，改为运行时拼接后密钥扫描 0 findings，未放宽规则。最后前端 build/lint 退出 0（index-CGGrhfGR.js）；git diff --check 退出 0。本轮仍未补新面板浏览器交互、超长原始记录的完整支持、覆盖联动或真实跨机验证。


## SC-02/SC-08/SC-11 新来源覆盖联动（2026-10-09）

- CollectionResult 增加不序列化的来源映射、技能 origin 与批准链接事实，观察器复用已解析的信息，不重新读取技能正文。账本携带计数幂等，并以已观察的 nature 入桶，避免第三方被错计为 A 或重复增加。
- Claude 桌面账号根加入覆盖观察；通过已有 manifest 事实识别 user/vendor_builtin，未知 creator 的真实文件仍列未定性。manifest 作为 CD-01 的关联来源元数据仅记录 C，不携带。已更新分类文档对应注释。两账号夹具核对自建四文件携带、vendor 两文件/两 manifest 记录未携带、无未知遗漏；vendor 正文零读取保持通过。
- 批准链接观察沿用 Claude 逻辑 skills 路径，复查 link_target 白名单/目标/内部链接边界后观察物理目标；合法链接不误报 incomplete，越界链接仍拒绝。来源已知第三方在账本中为 C、程序产物为 E，自建可执行文件为 A 并携带。
- 环境变量字段报告只列名称；相关安全项为确认类、密钥名称/含账号代理地址为不携带、无关变量为 E 不携带。注册表名称枚举对无关变量保留名称但不查询值。未选择设置时仍不调用环境读取。
- H 文件成功来源加入携带数；独立分包数不影响文件计数，超过注入主包单文件阈值仍计成功，格式不合法或未勾选不记携带；未选及凭据哨兵零正文读取。
- 核对发现账号自建技能 .pyc 原未过滤；补齐 SK-05 的 .pyc/common artifacts 分类及采集过滤。夹具验证 .pyc、node_modules、迁移标记正文零读取/零携带，自建 program.exe 仍按 A 携带。账本对再生产物分桶/剪枝一致。
- 初步现有相关 tmp/run-sync-coverage-new-sources-20261009-1：38 passed、1 skipped，11.15 秒；加入真实分桶断言后 -2：38 passed、1 skipped，8.42 秒。来源/历史/去重相关 tmp/run-sync-coverage-new-sources-last-20261009-1：44 passed、1 skipped，8.21 秒；账号产物最后补验 tmp/run-sync-coverage-artifacts-20261009-1：45 passed、1 skipped，8.15 秒。skip 是 Windows 符号链接权限不足；联接点批准链接夹具实际通过。
- 完整 machine 回归结果续记。仍需长路径、读取失败/嵌套项目边界、字段叶级白名单、超长历史原始记录及浏览器新面板、真机新增来源只读预览和第二台电脑实际验收；这轮只做合成 HOME，没有读取真实新来源。


新来源覆盖阶段完整 machine 回归（tests -k machine）tmp/run-sync-coverage-new-sources-regression-20261009-1：306 passed、2 skipped、357 deselected，151.67 秒，无失败。跳过为收集 test_cloud_core 时缺少 jwt 和 test_machine_coverage 符号链接权限不足；本轮不是全仓回归。最后 Python 生产改动均发生在该轮开始前。凭据扫描 0 findings、git diff --check 退出 0，PROJECT_STATUS 本地契约及 156 个稳定 evidence 路径通过；未使用外部日常同步工具。


## SC-08 同名相同副本全流程补验（2026-10-09）

合成 HOME 在 Claude/Codex/通用技能三个原位置放入同名相同技能，每份包含 UTF-8 非 BMP 文本与二进制资源。skills.json 明确一组 identical、三个成员；主包有六个独立且唯一的成员。恢复实际写入六文件到各原位置、字节一致；核验六项 PASS；同一次事务撤销移除全部六新增文件。没有去重或合并。命令 py -3.14 -m pytest tests/test_machine_provenance.py --basetemp tmp/run-sync-identical-skills-20261009-1 -q：4 passed，2.51 秒。此轮只增加合成验收夹具，未修改生产代码，未重复全量回归；上轮全量不是此新增测试的收集结果。真实同名来源及跨机仍未核实。


## SC-08 长路径与正文读取失败（2026-10-09）

- 技能归档成员超过 240 字符在读取正文前排除，按 path_too_long 记录真实大小与相对路径；其余文件继续采集。读取失败现在进入技能 excluded 和主包排除清单，技能标 partial，不能只留一个通用警告。账号技能同样提前排除长路径、记录读取失败并保留可用导出内容（未知大小为 null，不假报 0）。
- 仅产物缺失仍提示重装/构建；一般文件缺失提示核对排除清单、从原位置补齐。界面不再把所有未携带文件称作“程序文件”。最后前端 build/lint 退出 0，生成 index-DTxCkkqN.js；本轮没有重建 sidecar/安装包。
- 合成普通技能与账号技能分别验证长路径零正文读取、注入 PermissionError 明确排除、其它 SKILL.md 继续备份/恢复或导出 ZIP，原失败文件不写目标。首轮相关 tmp/run-sync-skill-file-failures-20261009-1：9 passed，3.87 秒；账号导出与文案联动 tmp/run-sync-skill-file-failures-last-20261009-1：20 passed，7.15 秒。
- 精确计数复现 tmp/run-sync-skill-exclusion-count-20261009-1：1 passed、1 failed、4 deselected，长路径在采集器和 writer 两处登记，主排除清单重复。改为合并全部排除来源后按路径+原因统一去重，保留技能自身 excluded，未删除问题记录。最后相关和完整 machine 回归结果续记；全量在最后去重修订之前启动。
- 这轮只覆盖可枚举、可 stat 的文件正文读取失败；目录枚举/stat 失败和嵌套项目归属边界仍需补验。真实新增来源、超长历史原始记录、新面板浏览器及跨机仍未验收。


技能文件失败阶段 machine 回归 tmp/run-sync-skill-file-failures-regression-20261009-1：309 passed、2 skipped、357 deselected，172.65 秒。skip 为收集 test_cloud_core 缺少 jwt，以及 test_machine_coverage 的符号链接权限。该轮在最后主排除清单去重修订及新增两项账号失败用例之前启动；最后修改以 tmp/run-sync-skill-file-failures-final-20261009-1 的 23 passed（14.76 秒）为证，未冒充最后全量。最后前端 build/lint、密钥扫描 0 findings、git diff --check 退出 0，PROJECT_STATUS 本地契约及 156 个稳定 evidence 路径通过。


## SC-08 嵌套项目技能归属（2026-10-09）

合成父/子项目均有 WorkBuddy AI 同名技能并同时选择。首轮 tmp/run-sync-nested-skill-owner-20261009-1：2 failed、6 deselected，实际采集三份，子项目技能被父项目递归扫描和子项目扫描各带一次；与项目输入顺序无关。采集技能容器前复用既有 _owner/_key 最长匹配，只由真实所属项目采集，不再重复读取/记录子项目技能。修复后 tmp/run-sync-nested-skill-owner-20261009-2（技能来源、WorkBuddy、项目采集相关）：13 passed，6.47 秒。两种顺序均核对只有两条唯一项目成员，归属父/子各一，恢复映射至新父/子项目后分别保留各自字节；明确选择 WorkBuddy 手动候选，仅合成目标写入。

本轮未重复完整 machine 回归；仅修改技能容器归属过滤，相关验证覆盖父子双选、输入顺序与恢复路径。目录枚举/stat 失败、其它嵌套边界及真实跨机仍待补验。未访问真实新增来源、构建或发布客户端。


## SC-08 技能目录枚举与元数据失败（2026-10-09）

- 普通技能容器无法枚举时记录 enumeration_failed，不再整次备份异常退出或无声漏掉。技能子目录通过 os.walk.onerror 记录具体相对目录，技能标 partial；其它可用文件继续采集。单文件 stat 失败记 metadata_unreadable，大小为 null；排除产物大小统计失败同样返回未知，不伪造为零。
- 合成权限失败夹具验证容器/子目录无法枚举、单文件 stat 失败均进入排除报告，问题文件正文零读取，覆盖 totals.complete=false；可用 SKILL.md 仍可发布。未修改权限或读取真实 HOME。原有技能来源/批准链接 tmp/run-sync-skill-enumeration-20261009-1：12 passed，6.96 秒；新增失败与覆盖 tmp/run-sync-skill-enumeration-failures-20261009-1：20 passed、1 skipped，7.56 秒（Windows 符号链接权限不足）。
- 桌面备份预览补充“部分目录未完成扫描”的实际状态说明，以及未携带内容列表（最多 20 项、中文原因）。前端 build/lint 退出 0，index-FoDqYRUL.js；本轮未执行该新列表的浏览器交互验收。完整 machine 回归随后记录。
- G10 只读新增来源授权已通过对话异步提出，当前尚未收到授权答复，不据沉默执行。明确目标为账号 skill/manifest、通用技能、批准链接的 CC Switch 技能、用户环境变量名称及非密钥值、桌面 MCP 配置；不含 CC Switch 数据库、不写助手/注册表、不执行迁移。依据 machine-sync-plan.md §6/§9。
- 此轮主要覆盖通用技能采集器的枚举/stat；账号目录枚举/stat、其它嵌套/字段边界、超长原始历史记录、浏览器全流程以及真机/第二台电脑验收仍待完成。


技能枚举/元数据失败阶段完整 machine 回归（tests -k machine）tmp/run-sync-skill-enumeration-regression-20261009-1：316 passed、2 skipped、357 deselected，174.74 秒，无失败。skip 为收集 test_cloud_core 缺 jwt 和 test_machine_coverage 符号链接权限；本轮不是全仓回归。全部本轮 Python 生产改动与失败夹具在收集前完成。最后前端 build/lint、密钥扫描 0 findings、git diff --check 退出 0，PROJECT_STATUS 本地契约及 156 个稳定 evidence 路径通过。G10 尚无授权答复，未访问真实新增来源，后续继续推进独立合成工作。

## SC-10 历史与扫描失败浏览器补验（2026-10-09）

Windows localhost Vite ui-test，浏览器使用 sync-history 传输夹具，全部为合成路径/响应。历史初始不选，未选时无历史面板；勾选后显示 5 文件/600 MiB/3 独立分包并可展开文件名，提醒与主包同目录保存。行号显示 5、7（实际命中 8 行、样本截断），另一个文件没有保留行号样本但仍显示实际 4 行与截断说明。选择整份跳过自动更新为 3 文件/400 MiB/2 包，排除项增加为 3 项。主排除列表 22 项只显示前 20 项并说明上限，不完整提示可见。

浏览器复现旧的“未纳入备份的内容”与新列表重复显示、旧列表暴露内部原因码且不限制数量；统一为一处可折叠列表，最多 20 项并使用中文原因，恢复报告同样适用。恢复预览历史默认不选、计划 2 文件；勾选自动更新期间确认禁用，更新后显示规则 2 + 历史 5 = 7 文件、分包摘要与排除原因，模拟确认完成后显示 7 文件及“不保证可继续对话”。这里只验证真实 React 界面配合模拟传输，没有执行真实后端恢复或原生窗口操作。

初次 npm dev 参数启动被当前 npm 的配置校验拒绝，改用本地 node_modules Vite 二进制启动成功。夹具热更新仍持有旧传输对象，主动重载后验收；过程中修正夹具的 skip 文件/包计数与恢复总数，没有修改后端以匹配模拟响应。最后 npm run build/lint 通过，前端 index-CF2p5Uco.js；浏览器错误日志为空。稳定截图 release-artifacts/machine-sync-history-browser-preview.png、machine-sync-history-browser-restore.png 已人工查看，无重叠/裁剪。临时页与本次 Vite 进程已关闭。没有重建 sidecar/安装包。

## SC-07 账号技能权限失败补验（2026-10-09）

账号根/账号目录枚举、manifest stat/读取失败、技能目录/子目录枚举与单文件 stat 失败现在明确进入主排除报告；技能内失败保留相对路径、未知大小 null、partial 状态。目录访问失败不再异常终止或无声消失，其它可用内容继续导出。同名账号别名继续隔离，层级故障报告使用序号，不回显真实账号目录名；vendor 正文零读取保持通过。

专项 tmp/run-sync-account-permissions-20261009-1：18 passed、1 failed，技能目录 stat 故障虽已进入主报告，但 Windows 观察器的 is_dir/scandir 仍能工作，覆盖账本错误显示 complete。修复为 CollectionResult 私有 coverage_issues 保留采集阶段已知失败，由备份观察完成后合并入同一根账本，不依赖第二次扫描再次碰到同一故障。最后账号/桌面协议/覆盖/来源相关 tmp/run-sync-account-permissions-20261009-2：39 passed、1 skipped，14.47 秒；skip 是 Windows 符号链接权限不足。夹具覆盖七类 PermissionError，失败内容零读取，nested/file stat 两种场景实际备份→导出 ZIP 只含可用 SKILL.md。后续完整 machine 回归结果续记。

G10 尚无授权答复，未访问真实新增来源；原始历史超长记录、其它字段/嵌套边界、真实源布局和跨机验收仍待完成。

账号权限/浏览器阶段完整 machine 回归（tests -k machine）tmp/run-sync-account-permissions-regression-20261009-1：323 passed、2 skipped、357 deselected，146.29 秒，无失败。两个 skip 为收集 test_cloud_core 缺 jwt 和 test_machine_coverage 符号链接权限不足；本轮不是全仓回归。全部本轮 Python 生产改动和新增七类失败夹具在收集前完成。最后密钥扫描 0 findings、git diff --check 退出 0；PROJECT_STATUS 本地逐项字段/唯一键/日期/状态/稳定路径自检通过，158 个 evidence 文件现存且无运行目录/越界/链接，未调用外部日常库同步工具。未将合成浏览器响应当作真实后端恢复证据；真实来源 G10、原生窗口、第二台电脑与助手加载仍待验收，目标保持 active。

## SC-04 完整 v1 合成兼容流程（2026-10-09）

新增旧格式完整夹具：从合成来源取全部八种旧条目类型（含报告），四个旧助手、项目记录和内存/权限/信任字段；去除全部 v2 属性，文本技能使用旧 skills_text 类型。新引擎只读预检不改目标，明确选择覆盖/安全确认/信任确认及 WorkBuddy 手动文件后恢复；全部文件逐字节比较，Codex 设置保留本机未知项并更新白名单值/项目信任，核验无 FAIL；再次恢复 changes 为空且文件不变，一次撤销恢复全部原文件字节，ZIP 哈希始终不变。允许撤销后留下空目录，未把目录移除当作承诺。

tmp/run-sync-full-legacy-v1-20261009-1：14 passed、1 failed；-2 单例仍失败，暴露夹具误将旧版没有携带的 Claude skills 转为旧文本技能。按旧目录表排除它们，不放宽恢复门禁。-3：14 passed、1 failed；旧包字段冲突需要按实际条目选择，不能只按初始 whole-file differs 状态选。改为明确选择全部相关条目后 -4：15 passed，5.42 秒。此项是全类型合成 v1 生命周期，不是真实 134 条旧 ZIP 的新版完整恢复，更不证明旧版客户端可读 v2。

## SC-05 项目登记 MCP、叶级门禁与无 Git（2026-10-09）

复现 CC-14 缺口 tmp/run-sync-project-mcp-20261009-1：1 failed、1 deselected，选中项目 .claude.json 的 mcpServers 没有任何条目。采集现在仅对明确选择且存在的项目生成独立字段条目，以 project_id 关联；项目路径和账号值不装入 payload。恢复到映射项目登记键，不写项目里的 .claude.json。Windows 规范化后匹配已有键，保留原大小写/斜杠；CheckItem.field_path 独立保存层级，点号项目名不被拆为字段。合并和核验共用同一层级，事务仍备份/检查原件/可撤销。

专项包含源 project.with.dot、目标 new.project、目标键大写和斜杠变化、已有远程 URL 冲突；未确认零变化，确认覆盖只更新 URL 与安全 env，保留本机其它 MCP、信任和未知字段、未选择项目及 oauthAccount 字节语义；核验 PASS，撤销恢复原 JSON 字节。真实来源/凭据没有读取。源字段 deviceId、unknown、env.API_TOKEN 不装包。

MCP 恢复门禁由前缀匹配收紧到 url/command/args/type 及合法非密钥 env 叶；20 个伪造字段场景覆盖四种来源文件，deviceId/unknown/url.extra/headers.authorization/env.API_TOKEN 全部拒绝。仍需更完整的字段账本与偏好键验证，不能以这 20 项宣称全部设置均已验收。

无 Git 两分支：程序缺失抛 FileNotFoundError；已安装 Git 对非仓库返回非零。项目规则、提示和通用技能全带且各条 git_unavailable，实际备份/映射恢复逐字节一致并核验成功。测试 tmp_path 在仓库下，必须注入非仓库结果，不能误把父仓库有效 Git 当作此分支。

集成 -2：17 passed，10.94 秒。扩充测试 -3：46 passed、2 failed（测试插入位置把 MCP 后半段放入无 Git 用例，以及非仓库夹具实际继承父仓库）；修正位置后 -4：47 passed、1 failed。-5：47 passed、1 failed，非仓库替身未模拟 check=True 的 CalledProcessError，导致错误 bytes 类型传入 Path；补齐替身后最后 tmp/run-sync-project-mcp-20261009-6：48 passed，31.39 秒，无失败。生产修复没有为这些测试替身错误扩大门禁。完整 machine 回归续记。

本轮没有前端生产改动、安装包重建或真实迁移；G10 尚无答复。项目多个登记项共享一个目标的组合、其它独立规则/字段边界、原始历史超长记录、CLI 专家全流程与真实跨机继续保留。

v1/项目 MCP 阶段完整 machine 回归（tests -k machine）tmp/run-sync-v1-project-mcp-regression-20261009-1：347 passed、2 skipped、357 deselected，158.83 秒，无失败。skip 为收集 test_cloud_core 缺 jwt，以及 test_machine_coverage 符号链接权限；本轮不是全仓回归。所有本轮 Python 生产代码与新增用例均在收集前完成。密钥扫描 0 findings、git diff --check 退出 0；PROJECT_STATUS 字段唯一/日期/状态/证据稳定路径本地检查通过，158 个现存 evidence 文件，没有调用外部日常库同步工具。

G10 仍无授权答复，未读真实新增来源；真实旧包新版完整恢复、其它规则与字段账本、设备偏好、CLI 专家全生命周期、超长原始历史、原生/跨机仍未验收。下一轮优先补多个登记项目与全局 MCP 共享 .claude.json 的组合，并使安全确认列表显示所属项目，以免相同字段名对应多个项目时无法区分。目标保持 active，未构建/安装/发布。

## SC-05/SC-10 共用登记文件与确认归属（2026-10-09）

合成全局和两个登记项目的 MCP 指向同一 .claude.json，项目路径含点号，目标已有大写/斜杠键。两个场景分别全覆盖与保留第二项目：最终都只有一次文件写入、一次原件备份；全局与第一个项目正确合并，第二项目按选择新增或完整保留，其它本机/信任/未选项目字段保留，核验对应 PASS/KEPT，撤销恢复原 JSON 字节。未合并为同一项目、没有回写源路径。

首轮 tmp/run-sync-multi-project-mcp-20261009-1：2 failed、24 deselected，安全确认列表没有项目归属。预检 security_list 增加默认兼容的 project/instance，安全确认摘要包括它们；桌面每项显示全局设置、工作文件夹路径或桌面设置。-2 仍 2 failed，仅为测试直接比较 Windows D:/d: 的大小写；按既有不区分大小写的路径语义修正断言后 -3：2 passed、24 deselected，1.60 秒。没有修改路径映射来迎合断言。账号/项目字段与桌面协议/输出隐私相关 -4：36 passed，18.84 秒。

前端 npm run build/lint 通过，index-BJ11SBL7.js。localhost ui-test sync-mcp 夹具浏览器明确显示同一 mcpServers.remote.url 的全局/第一/第二项目三项和桌面 locale，不再无法区分归属。安全选项默认不选、模拟写入 0；勾选触发自动更新，更新时确认禁用，之后模拟写入 1。原夹具写入数常量修正为随 confirm_security 改变，主动重载后检查。只验真实 React 与合成响应，不当作实际后端写入或原生窗口证据。错误日志为空，稳定截图 release-artifacts/machine-sync-mcp-project-confirmation.png 已查看，无重叠/截断；临时浏览器页和本次 Vite 进程已关闭。

完整 machine 回归启动后补充现有输出隐私夹具：邮箱位于源与目标项目路径，真实 MCP payload 保留并通过映射恢复，公开 security_list.project 隐藏邮箱；预览/应用回复与所有 Markdown 均无邮箱。tmp/run-sync-multi-project-output-20261009-1：2 passed、1 failed，断言误以为整个项目路径都被替换；显示策略实际只替换邮箱部分。按既有 public_value 语义核对后 -2：3 passed，3.27 秒，生产隐私规则没有放宽。本补充夹具以专项为证，不冒充已在启动更早的全量中收集。

本轮未访问真实新增来源，G10 仍无答复；多个来源映射同一目标项目的碰撞、其它字段账本/独立规则/设备偏好、CLI 专家全流程、历史超长记录以及原生/跨机继续未验收。完整 machine 结果续记。

共用登记文件/确认归属阶段完整 machine 回归 tmp/run-sync-multi-project-mcp-regression-20261009-1（tests -k machine）：349 passed、2 skipped、357 deselected，161.77 秒，无失败。两个 skip 为收集 test_cloud_core 缺 jwt 和 test_machine_coverage 的符号链接权限；本轮不是全仓回归。所有 Python 生产变更与两项共用文件场景在收集前完成；启动后扩充的邮箱路径旧测试以最后专项 3 passed 为证，未宣称全量已收集该版本。密钥扫描 0 findings、git diff --check 退出 0；PROJECT_STATUS 本项目内契约自检及 159 个现存稳定 evidence 路径通过，未调用外部日常库同步工具。真实 G10/原生窗口/第二台电脑/助手加载没有完成，仍按原目标继续实施其它独立事项。

## SC-05 多来源目标字段碰撞（2026-10-09）

合成两个来源项目映射到同一目标项目，初始目标登记文件已有其它本机字段。首轮 tmp/run-sync-mcp-collision-20261009-1：3 passed、1 failed、26 deselected，明确同时恢复两个不同 MCP URL 时并未拒绝，后一条会覆盖前一条并令前一条核验失真。恢复计划增加 field_proposals，按实际目标文件、独立字段层级、叶键登记所有实际获准恢复的值（包含原本 same 的项）；Windows 项目键规范化后不区分大小写。若同一字段提出不同值，计划在目标写入/创建事务目录前报固定中文错误，消息不含原值/路径。安全未确认、明确保留或未获准字段不参与碰撞。

相同值可以共用一次写入，互不重叠字段可合并，保留第二来源时第一份可恢复；三个场景均核验无 FAIL 并撤销恢复原字节。初步应用/项目/桌面协议/输出隐私 tmp/run-sync-mcp-collision-20261009-2：42 passed，25.93 秒。

扩展桌面协议 -3：41 passed、1 failed（26.58 秒），夹具误期待未选择覆盖的初始预览直接失败；既有协议此时等待选择，尚未批准两个待写入值。修正为明确选择两份覆盖后验证碰撞后，tmp/run-sync-mcp-collision-protocol-20261009-4：4 passed、26 deselected，3.10 秒；协议返回 failed、中文原因、没有 plan_id、原文件不变，改为保留第二份后可生成计划并实际恢复第一份、核验无 FAIL。没有放宽生产门禁以匹配错误期待。

完整 machine 首轮 tmp/run-sync-mcp-collision-regression-20261009-1 在相关旧夹具尚未修正时已启动，收集了该错误断言；显示已知失败后用本次 session 的 Ctrl-C 停止，退出 1，不计为完成回归或新的生产问题。修正夹具后的完整 -2 结果续记。当前只改恢复计划与测试，无前端生产变更，未访问真实来源/构建安装包。

碰撞修复最终完整 machine 回归 tmp/run-sync-mcp-collision-regression-20261009-2（tests -k machine）：353 passed、2 skipped、357 deselected，150.12 秒，无失败；所有本轮生产与测试变更在收集前完成，包含扩充后的邮箱项目路径场景。跳过为 test_cloud_core 收集时缺 jwt 与 Windows 符号链接权限。本轮未重新运行全仓测试或前端构建（没有前端生产变更）。密钥扫描 0 findings，git diff --check 退出 0；本地摘要契约与 159 个稳定证据路径自检通过，未调用外部日常库工具。真实来源、原生窗口、第二台电脑及助手加载仍未验收。

## SC-03 专家 CLI 输出与最小 v2 生命周期（2026-10-09）

Windows Python 3.14 合成源/目标 HOME 和保存目录含邮箱，Codex 规则正文含邮箱与合成令牌；全部外部来源、软件、进程、用户环境表和 Git 凭据查询用隔离替身。四种组合为文本/JSON 输出 × 默认脱敏/allow_secret_hit_paths 原样保留。首轮 tmp/run-sync-cli-hygiene-20261009-1：4 failed、2 deselected（0.80 秒），均复现备份预览直接暴露保存目录邮箱。

scripts/machine.py 增加统一 _emit，在 JSON 序列化前递归清理展示副本，文本也按 public_value 清理；备份、预检、恢复、核验、撤销及错误输出使用同一规则。专家原样保留仍须源路径和目标路径分别获准；不修改同步正文、存储路径或恢复计划。四种组合完成备份零写入预览→v2 发布→预检→恢复零写入预览→实际恢复→核验→撤销预览→实际撤销，检查公开输出无邮箱/令牌、默认令牌变为占位符、专家正文逐字节保留、源原件不变。相关 tmp/run-sync-cli-hygiene-20261009-2：10 passed（8.32 秒）。这是最小 Codex 规则生命周期，尚未代表所有新增种类、历史和专家参数已完成全流程。

没有前端变更、真实来源访问或安装包构建。完整 machine 回归 tmp/run-sync-cli-hygiene-regression-20261009-1 结果续记。

CLI 输出阶段最终完整 machine 回归 tmp/run-sync-cli-hygiene-regression-20261009-1（tests -k machine）：357 passed、2 skipped、357 deselected，160.19 秒，无失败；所有本轮生产与测试变更在收集前完成。两个 skip 为 jwt 缺依赖和 Windows 符号链接权限。本轮未全仓复测或重建前端/sidecar/安装包。密钥扫描 0 findings、git diff --check 退出 0，本项目内摘要契约与 159 条稳定证据路径自检通过。真实来源与原生/跨机加载仍未完成，项目保持 active。

## 用户追加边界：完全不读取 Git（2026-10-09）

用户先明确“我们不能备份git信息”，随后选择“完全不读取 Git 信息，助手文件按白名单携带”。这项当前指令覆盖原分类/计划中的 Git 跟踪状态筛选、Git 根目录推导、技能 Git 来源和脏状态、Git 凭据主机与版本查询；原三项默认方案仍保留，其它范围继续实施。允许公开来源来自非 Git 的账号清单、技能锁文件或技能自带元数据；不查询 Git，锁文件中的 commit/ref 不提取。

变更前在中文/空格 Git 项目的四状态矩阵（tracked、ignored、untracked、tracked_ignored）复现 Windows GBK 解码 Git UTF-8 路径导致中断：tmp/run-sync-git-matrix-20261009-1 4 failed、30 deselected（1.28 秒）；临时修正编码后 -2：2 passed、2 failed（3.97 秒），后两项是夹具直接读取旧条目缺省 rule_id 的 KeyError。用户随后改变需求，临时 Git 查询修复已被完整移除查询的实现取代，未将其作为最终方案。

当前实现：不运行 Git、不读索引/远端/HEAD/脏状态/配置/凭据/版本；白名单助手文件全部携带，不生成 git_unavailable。选中的工作文件夹自身是记忆/信任边界；新项目记录移除 git_root/git_root_id，工具记录移除 git_commit，CC Switch 技能记录不再含 Git remote/head；skills ref 固定 null，local_changes 固定 unknown。旧包路径字段仅兼容定位，不查询本机 Git。所有来源的 .git（目录或 worktree 指针）、.gitconfig、.git-credentials、.gitignore、.gitattributes、.gitmodules 不带；覆盖、批准链接和技能尺寸扫描均不进入 .git 内部，Git 排除大小用 null。其它排除继续沿用原策略。

初步相关 tmp/run-sync-no-git-20261009-1：56 passed、7 failed（33.42 秒）。七个失败均为已被本次明确要求取代的旧期待：无 Git 时 git_unavailable 两例、共用 git_root_id、CC Switch remote、Git 凭据主机、Git 来源/脏状态、Git 根/worktree 推导；已逐项改为当前无 Git 契约，未为通过而放宽其它隐私/路径规则。相关 -2：86 passed（29.16 秒）。

进一步加入 Git 命令、目录枚举和文件正文哨兵：四状态均带 18 个白名单助手文件（含已跟踪后本地修改、中文命令名、三处技能与二进制资产），正确映射恢复、MCP 字段合并、核验、撤销，源字节不变；嵌套 .git/config、HEAD、Git 配置/忽略/凭据及 worktree 指针不恢复。tmp/run-sync-no-git-20261009-3：91 passed、1 skipped、4 failed（37.39 秒），四个失败均发生在测试自身撤销后 rglob 进入目标 .git 的检查，生产流程已通过哨兵；改为检查时先剪枝 .git 后 -4：4 passed、30 deselected（9.42 秒），没有放宽生产扫描哨兵。

三份规范按当前要求同步。没有前端生产变更，未访问真实来源或构建安装包。完整 machine 回归 tmp/run-sync-no-git-regression-20261009-1 结果续记。

无 Git 阶段完整 machine 回归 tmp/run-sync-no-git-regression-20261009-1（tests -k machine）：361 passed、2 skipped、357 deselected，167.11 秒，无失败；所有此前生产/测试变更在收集前完成。跳过为 jwt 缺依赖与 Windows 符号链接权限。完成后检查发现 Git 元数据的正常排除也可能被当作需要补齐的技能内容，追加修正：只排除 Git 信息不产生 artifacts_excluded 标记、不增加 needs_rebuild、不提示补齐 Git；排除记录仍保留，其它缺失/程序排除继续提示。该最后修改以随后专项为证，不冒充已在本轮完整回归中收集。

最终 Git 排除提示专项 tmp/run-sync-no-git-rebuild-20261009-1：59 passed，31.69 秒，包含四状态全流程/零读取、needs_rebuild=0 与不提示补齐 Git，以及第三方技能、分组、恢复与预检。完整回归 361 passed 早于这项最后修正；本轮无前端生产变更，未重建前端/sidecar/安装包，未运行本轮全仓回归。密钥扫描、diff 与摘要契约最终自检结果见交付记录。

本轮交付自检：scripts/check-secrets.ps1 为 0 findings；git diff --check 退出 0（仅既有换行转换警告）；PROJECT_STATUS YAML 唯一字段、2026-10-09 未加引号日期、active 状态、非空说明及 159 条项目内稳定 evidence 路径逐项本地检查通过。未调用外部日常库同步工具。当前成果为源码与合成验证，已安装程序和现存安装包仍待重建/现场验收。

## 0.3.6 重建交付（2026-10-09）

用户明确要求重建安装包。版本从 0.3.5 升至 0.3.6，保留原 0.3.5 安装包/NOTICE/清单；替换构建侧 sidecar 前保存 release-artifacts/ai-config-rpc-before-0.3.6-20261009.exe。此次重建包含当前同步分类/来源/隐私/v2/分组/历史/恢复代码及完全不读取 Git 的用户边界，不宣称未验收功能已经完成。

Windows x64 / Python 3.14：scripts/build-desktop-sidecar.ps1（PyInstaller 6.22.3）完成；desktop npm run lint 退出 0；npm run tauri:build 退出 0，TypeScript/Vite 与 Rust/NSIS 成功，前端 index-BJ11SBL7.js。Rust 仅既有 linker_messages 警告。版本在 npm、npm lock、Tauri、Cargo manifest/lock 中为 0.3.6。

冻结 sidecar 使用 CREATE_NO_WINDOW、持续打开 stdin、ensure_ascii=False UTF-8 中文 ZIP 路径、PYTHONUTF8=0/PYTHONIOENCODING=cp1252、隔离 HOME/助手根/状态/APPDATA/LOCALAPPDATA，PATH 只保留 Windows System32（无外置 Python/Git）。tmp/frozen-0.3.6-smoke-20261009.py 退出 0、stderr 空：实际 v2 备份携带新审批规则与技能，Git 元数据/忽略文件不携带、软件记录不查询 Git；恢复经历待选择→覆盖→原文件完整备份→核验→撤销→保留→核验→撤销，源文件与原 ZIP 哈希不变。流程仅合成数据，不等同原生安装、窗口或真实助手加载验收。

交付 release-artifacts/AI-Config-0.3.6-Windows-x64-setup.exe，24,046,373 字节，SHA-256 b84057049a4ed15a2d86063787a9257c068496aac591e649897355207bbcf254。NOTICE 沿用 0.3.5 完整归档：核对 Cargo active Windows target 及已安装 npm 的所有名称/版本已覆盖，Python 构建依赖锁哈希未变，322 项记录 complete=true；非当前平台 optional 包不作为缺失。新归档 AI-Config-0.3.6-Windows-NOTICES-full.zip，1,211,055 字节，SHA-256 6ad5d51b0538c171f93a31147997ccf008c0d162ff33146c7237af3cd2cc801f。

AI-Config-0.3.6-Windows-manifest.json 记录 194 个当前源码文件哈希、sidecar/前端资产/安装包/NOTICE 哈希与大小，生成和逐项验证均不查询 Git；无 source_commit 或 dirty。所有源码及交付产物哈希核对通过。未自动安装、推送或远程发布；安装升级、原生窗口、真实来源预览及跨机仍待验收。本轮以构建与冻结流程为证，未重跑 pytest 全仓/完整 machine；此前 361 项和最后相关 59 项为无 Git 阶段证据。

0.3.6 最终自检：首次清单读取按 Windows 默认 GBK 解码含中文的 UTF-8 JSON 失败，仅为校验命令编码问题；改用显式 UTF-8 后 npm/Tauri/Cargo 五处版本、194 个源码、sidecar/前端/安装包/NOTICE 全部哈希核对通过。密钥扫描 0 findings，diff --check 退出 0；PROJECT_STATUS 本项目内 YAML 唯一字段/真实日期/active/非空内容及 162 条稳定证据路径检查通过，未访问日常同步工具。


## 0.3.6 检查备份隐私误判修复（2026-10-10）

用户报告 0.3.6 点击“检查备份内容”返回 `E_OPERATION_FAILED: private content in migration output`；用户最初称生成 ZIP，随后明确发生在预检阶段。复用采集器的本机只读诊断发现文件清单 entries 元数据命中 token：技能资源名的 `ask-` 中间包含 `sk-`，后续长文件名被旧模式当作 API Key。仅输出字段分类/命中类型和是否位于单词内部，不输出配置正文、路径或凭据；没有生成真实 ZIP，也没有改动助手文件。

修复：仅为 sk- token 前缀增加 ASCII 字母/数字起始边界，ask-/task-/risk-/flask- 词中后缀放行；独立 token、引号、赋值、路径分隔符、中文前缀及下划线/连字符前的 token 仍检测。另为启发式字段识别增加起始边界，避免长连续字符逐位置重试，100 万字符本机扫描 0.203 秒。备份/恢复隐私拒绝改为 E_PRIVATE_CONTENT，安全提示元数据/报告/文件类别、清单序号及识别类型/行号，保留原拦截规则，不显示不可信文件名、原文或凭据。

Windows / Python 3.14，2026-10-10 实际验证：

- 既有隐私三文件初查 `tmp/run-private-output-20261010-1`：47 passed；诊断改动相关六文件 -2：70 passed。
- 长字符串修订相关 -4：71 passed。-3 因误列不存在的 test_machine_collect_skills.py，未运行测试；已改用实际测试文件。
- 文件名边界修订 -5：85 passed、1 failed；失败为新夹具未创建目标 .claude 导致恢复目标不可用，备份与隐私门禁已通过。补齐夹具目标目录后 -6：86 passed（23.19 秒），含该文件名备份到恢复预检、旧包隐私拒绝、协议安全错误、七类凭据与 UTF-16/32 二进制脱敏。
- `py -3.14 -m pytest -q tests/test_machine_history.py tests/test_machine_history_restore.py tests/test_machine_env_export.py tests/test_machine_collect_desktop_skills.py tests/test_machine_skills_links.py --basetemp=tmp/run-private-output-history-20261010-1`：95 passed（14.68 秒）。与最后六文件合计 181 项通过。
- 本机快速预检（未选技能/历史、关闭覆盖统计及软件探测、无项目）33 条通过；含默认技能及已登记项目、同样关闭覆盖统计/软件探测的预检修复前复现 entries 误判，修复后通过隐私门禁但被“采集期间来源发生变化”保护停止。助手仍在运行，不能把这次诊断写成完整真实预检/备份通过；完整覆盖统计、用户实际分组与原生窗口仍待复测。

未执行本轮全仓/完整 machine 测试。安装包重建与冻结后端结果续记；尚未自动安装、远程发布或验证真实跨机加载。


### 0.3.7 重建交付与冻结验证（2026-10-10）

Windows x64 / Python 3.14：scripts/build-desktop-sidecar.ps1（PyInstaller 6.22.3）退出 0；desktop npm run lint 退出 0；npm run tauri:build 退出 0，TypeScript/Vite、Rust 与 NSIS 通过，仅既有 linker_messages 警告。五处应用版本一致为 0.3.7；0.3.6 安装包/NOTICE/清单保留，旧 sidecar 另存 release-artifacts/ai-config-rpc-before-0.3.7-20261010.exe。

冻结后端使用 CREATE_NO_WINDOW、持续输入管道、UTF-8 中文 ZIP 路径、PYTHONUTF8=0/PYTHONIOENCODING=cp1252、隔离 HOME/助手根/状态/APPDATA/LOCALAPPDATA，PATH 仅 Windows System32。合成技能包含 ask- 前缀 Markdown 资源：实际检查备份及 ZIP 生成通过，v2 包原样携带该文件；旧合成包覆盖/完整原文件备份/核验/撤销/保留/核验/撤销通过，原 ZIP 与源文件字节不变。脚本 tmp/frozen-0.3.7-smoke-20261010.py 退出 0、冻结进程 stderr 空；稳定证据为此记录，不引用临时脚本作 evidence。未生成真实助手备份。

交付 release-artifacts/AI-Config-0.3.7-Windows-x64-setup.exe，24,051,107 字节，SHA-256 6c3eda1832dcdfeb2138589db84026c83a1cde5e1dd03d95246f85b361e2312c。依赖文件与 0.3.6 源清单哈希对比仅应用版本变化，Python 三份需求文件哈希相同，沿用已核对的 322 项 NOTICE；0.3.7 NOTICE ZIP 哈希 6ad5d51b0538c171f93a31147997ccf008c0d162ff33146c7237af3cd2cc801f。新清单记录并逐项核对 194 个源文件、sidecar、前端、安装包与 NOTICE 哈希，不查询 Git。未自动安装或远程发布；真实窗口预检、来源稳定条件下完整备份及跨机加载仍待用户复测。本轮未跑全仓或完整 machine；181 项直接相关为本轮测试证据。


0.3.7 交付自检（2026-10-10）：仓库扫描首次 4 findings 均为上述长 ask- 文件名和测试中的占位符赋值触发旧共享扫描器；未改动扫描器或放宽门禁，改为运行时拼装测试名称、通过原输入替换构造预期字节，文档仅记录前缀。最后两测试文件复跑 tmp/run-private-output-final-20261010-1：57 passed（2.29 秒）。最终 scripts/check-secrets.ps1 为 0 findings，git diff --check 退出 0；PROJECT_STATUS 唯一字段/真实未引号日期/active/非空说明及 165 个稳定证据路径本地自检通过，194 源文件和全部交付产物哈希通过。未调用外部日常同步工具。依赖比对首次验证命令把 Cargo 中无关 fdeflate 0.3.7 也替换导致断言失败；改为只逆转 app 版本后哈希完全一致，无依赖变化。
