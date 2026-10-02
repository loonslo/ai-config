# 桌面端本机 JSON Lines 协议 v1

状态：DT-04 本机协议已实现；DT-19 增加了本机 `package_import` 事务导入操作并通过定向测试。Windows Tauri 与 Python sidecar 原型现已接入 DT-07～12 的设置、迁入／编辑、差异、接管、加载核验、历史恢复、记忆映射和项目接续操作；离线包导入页面、冲突选择 UI、原生窗口、干净账户安装和真实远端流程仍未验收。客户端尚未全功能交付。协议由 Tauri Shell 插件经 stdin/stdout 调用随程序启动的 Python 辅助程序，业务仍由 `ApplicationService` 执行。客户端和辅助程序运行在同一台电脑；该接口本身不做登录、上传服务器或设备间同步。

## 传输和请求

- 标准输入／输出按 UTF-8 JSON Lines 传输：一行一个 JSON 对象，stdout 仅输出协议事件。辅助程序入口为 `scripts/desktop_rpc.py`；Windows Python 3.14 one-file 构建与 Tauri sidecar 配置已验证，干净账户安装流程仍待验证。
- 每个请求必须有 `protocol_version: 1`、非空且不超过 128 字符的 `request_id`，以及 `type`。允许的请求类型是 `preview`、`apply`、`cancel`；客户端生命周期结束时可发送 `shutdown`。协议不接受 shell 命令，也不提供任意 Python 执行入口。
- `preview` 请求包含允许列表中的 `operation`，以及可选 `params`。运行时会核对操作名、参数名、必填字段和类型；未知协议版本、操作或参数会返回结构化错误。
- `apply` 请求只引用先前预览得到的 `plan_id`。计划保存在本机辅助程序进程内，有效期 20 分钟且只能使用一次；辅助程序重启后，旧计划失效。
- `cancel` 请求带正在运行的 `job_id`。客户端应继续读取事件，直到该作业返回最终结果。
- `shutdown` 是辅助程序生命周期控制消息，不是业务操作。服务先回 `shutdown_accepted`，停止接收后续请求，等待已接受的作业完成后再退出；客户端不应强杀仍在写入的进程。

当前操作清单和允许参数：

| 操作 | 参数 | 说明 |
| --- | --- | --- |
| `import_config` | 必填 `source` | 导入旧设备配置；先预览和确认备份目标 |
| `package_import` | 必填绝对路径 `package_path`；可选 `decisions`、`manual_values`、`selections`、`apply_to_agents` | 检查并预览离线包；应用时重验并通过事务备份、写入、回读和可撤销历史提交。需要对包差异逐项决定；可选择只保存到配置库而暂不应用到 Agent。此操作目前只有本机核心／协议，没有 Tauri 迁移页面 |
| `setup` | `store_path`、`remote`、`state_dir`、`memory_repo`、`tools`、`tool_roots` | 检测目录、预览首次设置；Agent 路径覆盖项必须是绝对路径 |
| `quick` | 无 | 使用保守默认值快速设置 |
| `rules`、`config`、`memory` | 无 | 预览或应用对应本机规划 |
| `scan` | `save` | 盘点已有规则；保存报告需要显式应用计划 |
| `migrate` | `item`、`choice` | 不带选择时只返回清单；桌面必须指定一个条目和动作后才能生成可应用计划 |
| `declare` | 必填 `agent_id`、绝对路径 `root`；可选 `entry`、`entry_mode`、`profile` | 登记自定义 agent；通用 Markdown 入口受核心相对路径校验 |
| `sync` | `fetch`、`publish` | 当前仅协议支持本地预览／应用；见下方限制 |
| `status` | 无 | 只读状态，不生成可应用计划 |
| `diff` | `choice` | 查看或保存明确选择的差异 |
| `detach` | 必填 `agent_id`；可选 `restore_original` | 退出接管并按选项恢复原件 |
| `verify_load` | 必填 `agent_id`；可选 `answer`、`record` | 检查新会话回答，记录操作需应用 |
| `undo` | `list_only`、`operation_id`、`index` | 列出或撤销本机历史操作 |
| `doctor` | `recover` | 检查本机状态；恢复操作需应用 |
| `inventory` | 可选 `save` | 本机来源盘点；保存报告需明确应用 |
| `snapshots` | 无 | 读取本机快照元数据；不返回记忆正文 |
| `memory_setup` | `disable`、`selections` | 预览／启用／关闭受支持的记忆映射 |
| `project` | `project_id`、`handoff_id` | 查看项目接续状态 |
| `project_setup` | 必填 `project_id`、绝对路径 `path` | 预览并登记本机项目目录；写入设备配置时生成备份 |
| `restore_snapshot` | 必填 `snapshot_id` | 预览或恢复受支持的本机记忆快照 |
| `start` | 必填 `project_id`、`handoff_id` | 预览或执行项目接续 |
| `finish` | 必填 `project_id`；二选一 `handoff_file`／`handoff_text` | 预览或保存项目交接；客户端文本最多 128 KiB |

客户端必须区分服务返回的 `preview`、`applied`、`failed` 和 `cancelled`；不能只因进程退出码为 0 就显示成功。操作结果由服务返回，具体字段随操作变化；schema 定义消息外壳与参数约束，不能替代页面对业务字段的解释。

`status` 在设备已配置时额外返回已登记 agent 的本机标识与显示名，供加载核验和退出接管页面选择目标；未配置响应结构保持不变。`verify_load` 不带 `answer` 时只返回核心生成的问题和当前文件版本是否已应用。带回答的预览可生成记录计划；只有用户确认应用计划后才写入核验结果。`detach` 同样先预览受管文件和可安全恢复的迁入原件，应用时写入事务备份；它不会操作 agent 进程或会话。

`package_import` 的 `decisions` 使用冲突计划给出的行键和 `keep_local`／`use_package`／适用时的 `manual_merge`；人工规则文本限制为每条 256 KiB，收到后会再次扫描疑似凭据和本机路径。`selections` 只能把冲突行映射到预览列出的 Agent 实例 ID，不能传本机路径。`apply_to_agents: false` 只允许保存可映射到配置库的内容。成功结果表示目标文件写入并回读一致、父包副本已检查；它不会声称 Agent 会话已加载，需另做新会话加载核验。导入操作以 `migrate` 写入现有事务历史，因而可通过 `undo` 预览和撤销。

`snapshots` 只返回清单元数据；确认文件无效时按“未确认”显示。`restore_snapshot` 在预览时校验快照内容哈希，并只允许恢复到已映射的 Claude 记忆目录；Codex 快照不可恢复。`project_setup` 只写本机设备映射，必须先预览且目标目录存在。`finish` 接受文件或界面输入的交接文本，不能同时提供两者。当前 `start` 应用路径可能在生成本机变更前快进读取已配置的 Git 远端；预览本身不 fetch，界面明确提示该行为，但独立的下载确认步骤尚未实现。

桌面首次设置未指定 `store_path` 时，RPC 使用本机数据目录中的默认规则库（`AI_CONFIG_HOME/store`；未配置环境变量时为用户目录下 `.ai-sync/store`）。该目录在预览阶段只检查、不写入；用户确认 setup 计划后才创建或复用。若设备配置文件已存在，setup 只提供识别结果，不生成可应用计划，避免重置覆盖。

## 预览、应用与失效计划

典型流程：

```json
{"protocol_version":1,"request_id":"r-1","type":"preview","operation":"rules","params":{}}
{"protocol_version":1,"request_id":"r-2","type":"apply","plan_id":"预览返回的计划 ID"}
```

预览结果带 `operation`、`can_apply`、不暴露本机路径的 `content_version` 摘要、操作结果；可应用时还带 `plan_id` 和 `expires_in_seconds`。只读操作或没有可写选择的预览返回 `can_apply: false`，不会分配计划 ID。

应用前辅助程序会重新生成预览并重新计算版本摘要，覆盖设备配置、计划读取的目标文件和相关记忆来源。摘要变化时返回 `E_PLAN_STALE`，不继续应用；计划过期、已使用或属于已退出进程时返回 `E_PLAN_UNKNOWN`。客户端应刷新预览，让用户重新查看变化后再确认。底层事务也会校验目标基线并写入备份；本协议不会把确认旧预览当作对新内容的授权。

`content_version` 是不含原文的摘要，用于检测变化；它不是远端版本 ID，也不代表已应用或 agent 已加载。应用结果和新会话加载核验必须单独展示。

## 作业进度、排队和取消

每个有效请求先收到 `accepted`，随后收到一个或多个 `progress`，最后收到一个 `result`。事件包含 `protocol_version`、`request_id` 和 `job_id`；进度还包含 `stage`。当前阶段包括 `started`、`planning`、`rechecking_preview`、`applying`，同步核心还会报告 `drift`、`fetch`、`publish`、`resolve`、`apply`、`verify`、`receipt`。这些是阶段名，不是百分比；没有总项目数的阶段不能显示虚构进度。

单个辅助程序一次只执行一个业务作业，其余作业排队。这样同一进程里的多次点击不会并发写目标；排队项可以在运行前取消。取消响应状态为 `accepted`、`too_late`、`already_finished` 或 `not_found`；接受取消后，最终结果为 `cancelled`。预览中的取消会在当前核心调用返回后于检查点结束，不会杀掉进程。进入写入边界后取消返回 `too_late`，客户端必须等待最终结果，不能显示已撤销。

窗口关闭时，客户端发送 `shutdown`，等待辅助程序正常退出后再关闭窗口。此机制保证正常退出时不会留下后台 sidecar，也让运行中的事务自行到达安全边界；操作系统强制终止进程不属于正常关闭路径，未完成事务仍由 `doctor` 识别。

辅助程序正常关闭时等待已接收作业收尾，不强行终止正在写入的事务。若进程或系统在写入中异常终止，核心事务日志和备份用于识别未完成事务；客户端启动时应调用 `doctor` 并在历史与恢复页面处理，不能声称本次协议已自动恢复。启动检查与恢复界面由 DT-11 验收。

## 当前边界与验证状态

`sync` 的 `fetch` 会改变本机共享配置源副本，`publish` 会写入远端；二者不属于无副作用预览。因此当前协议在 `fetch=true` 或 `publish=true` 的预览请求上明确返回 `E_PREVIEW_SIDE_EFFECT`，不会悄悄忽略参数。可通过该协议预览／应用不带这两个选项的本地配置同步；Git fetch/publish 桌面流程仍未实现，需之后设计可审核的传输阶段和二次预览，不能用此接口宣称已经支持云同步。

schema 文件为 `schemas/desktop-rpc.schema.json`，运行时实现为 `sync_core/application/protocol.py`，独立入口为 `scripts/desktop_rpc.py`。DT-04 定向测试覆盖协议拒绝、schema 与运行时操作表一致、预览后设备配置变化会阻止应用、作业串行化、排队取消、进度事件、请求 ID 保留，以及真实子进程 UTF-8 JSON Lines 预览不写入目标。DT-05 在受限 PATH 下验证冻结 Python 3.14 sidecar 读取资源、预览并有序退出；DT-06 当前原型只接入只读状态和环境识别。Windows／项目虚拟环境 Python 3.13.14 的定向命令及 Tauri 构建结果登记在 `docs/acceptance.md`。没有在此验收原生窗口是否无冻结、干净账户安装、macOS、Git 远端传输或服务器同步。

## 0.2.0 扩充操作（2026-10-01）

package_export 增加 extension_kinds，支持 skills/mcp/memory/handoffs 的显式开关。extension_capture 只采集选定受限来源到配置库；package_capabilities 返回能力注册表；portable_restore 仅恢复已映射 Claude Markdown；portable_project 是只读操作，以 project_id/profile 和可选 handoff_id 查看清单、正文及源码／依赖缺项，不读取 Git 远端；git_transport 将获取/发布与本机应用分开。cloud 接受 HTTPS server、登记 action 与逐 action 严格 options；预览不登录、不上传、不下载，apply 才执行。上传预览保存完整归档 SHA-256，应用时校验同一组归档字节再加密，不重新读取变化后的源包。login/poll/logout、空间、密钥/恢复、版本、上传/下载、设备撤销/回执分别报告结果。未知 action/字段/资源 ID 拒绝，不开放任意 shell。恢复材料只存在待应用参数与专用结果内存，不写设备文件、包或日志；返回材料时客户端提供隐藏按钮。协议 stdout 只向本机客户端传递结果，不落盘记录。
