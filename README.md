# 三台设备的 AI 配置与自动记忆同步

支持 Windows 原生 Python 和 macOS Python。要求 Python 3.11+，开发使用 3.14。

| 内容 | 维护位置 | 同步方式 |
| --- | --- | --- |
| 全局规则、工具默认值 | ai-config | Git 拉取后应用 |
| 项目开发规则 | 各项目 AGENTS.md / CLAUDE.md | 随代码同步 |
| Claude 自动记忆 | 独立私有 ai-memory | 三方文件合并、Git 传输 |
| Codex 自动记忆 | ai-memory/codex/设备标识/ | 导出快照，全局规则引导按需读取 |
| 路径、设备差异 | 本机 device.json，已忽略 | 分别设置 |
| 凭据、登录、聊天数据库、插件运行状态 | 工具本机目录 | 不进入 Git |

Codex 快照是跨设备参考资料，**不是已经验证的原生记忆数据库导入**。脚本不回填 Codex 原生 memories，不做 Claude/Codex 语义转换，不保证工具记录所有聊天。当前为显式同步命令，不安装后台监听服务。

## 实施范围与可靠性边界

当前版本已完成并以隔离测试验证的能力包括：计划哈希与来源树重验、统一设备锁、可恢复事务、不可变 objects／snapshots、Claude 三方记忆合并、start 前本机快照、交接完整性与配置版本核对、来源盘点、doctor，以及保守 Git 传输。冲突、来源消失、基线消失、路径碰撞、未确认推送及 dirty 工作区都会停止或标记 pending；这不是三台真实设备验收。

P3（三台真机、新会话读取、私有远端及独立加密备份）尚未在本仓库内宣告完成；需要用户提供两个远端、另外两台设备的实际路径与加密备份目的地。Codex 导出仍是参考快照，不是原生记忆数据库导入。

核心资料位于 `sync_core/`，格式定义位于 `schemas/`：

```text
ai-memory/
  registry/projects.json
  objects/<sha256>.md
  snapshots/<device>/<uuid>.json
  heads/<device>/<scope>.json
  integrated/<project>/<branch-id>/MEMORY.md
  handoffs/<project>/<uuid>.json|md
```

快照先写入不可变内容物，再写入带 `schema_version`、父快照、来源状态、文件哈希、删除记录和 manifest 哈希的清单。正常删除最后一份文件会产生有父版本的空清单；来源目录消失只报 unavailable，不生成删除事件。

## 主要命令

所有命令默认只预览；只有加上 `--apply` 才会写入。每次写入前都会重验计划当时的文件／来源树哈希。

```text
python scripts/sync.py quick [--local device.json] [--apply]
python scripts/sync.py doctor --local device.json
python scripts/sync.py doctor --local device.json --recover  # explicit rollback review
python scripts/sync.py inventory --local device.json [--apply]
python scripts/sync.py rules --local device.json [--apply]
python scripts/sync.py config --local device.json [--apply]
python scripts/sync.py memory --local device.json [--apply]
python scripts/sync.py finish --project <id> --handoff <handoff.md> --local device.json [--apply]
python scripts/sync.py start --project <id> --handoff-id <id> --local device.json [--apply]
python scripts/sync.py restore --snapshot <id> --local device.json [--apply]
```

想快速开始时，直接运行 `python scripts/sync.py quick` 做只读盘点；确认输出后运行 `python scripts/sync.py quick --apply`。它会自动使用标准的 Codex／Claude 目录，必要时生成一个已被 Git 忽略的本机 `device.json`，并只应用公共规则。默认不复制凭据、不写入完整工具配置、不同步记忆；要启用记忆，之后再手动配置 `memories` 和私有 `ai-memory` 仓库。

`inventory` 会把来源区分为 `normal`、`normal_but_empty`、`missing`、`unreadable`、`blocked_secret`、`pending_mapping`、`not_configured`、`intentionally_excluded` 等状态；新来源不会被静默跳过。`doctor` 只读并列出需要处理的事务与来源状态。

`finish` 要求 device 设置中的 `projects.<id>`、`memories[].id` 与交接文件同时存在。它依次采集稳定来源、保存快照、登记项目、保存交接，再做 Git 推送确认；缺少必要交接字段、代码 dirty、远端不存在或推送失败均不会报 ready。交接文件可由 `templates/handoff.md` 复制。

`start` 会先稳定采集并保存本机记忆快照，再以交接快照的父版本为基线做三方合并；本机新增会保留，修改／删除冲突会停止，普通 start 不会删除本机已有文件。合并结果和基线标记一起进入事务；它不会自动切换分支、丢弃工作区或执行项目脚本。`restore` 只恢复指定快照，验证哈希后才预览／备份／写入，不会推送或改动远端最新状态。

应用命令退出码固定为：`0` 表示合法预览或已完成，`2` 表示交接／配置／来源尚不具备接续条件，`3` 表示待上载或网络问题，`4` 表示冲突，`1` 表示其他错误。预览返回 `0` 不代表可以接续；请检查输出中的 `status`、`ready` 和阻塞项。

`finish --apply` 要求 ai-config 工作区干净且当前 commit 已在其远端分支确认，并保存共享规则、受管字段选择及模板摘要。`start` 会核对这些配置事实；Windows／macOS 的本机路径仍留在各自 device 文件，不参与配置版本相等判断。`additional_sources` 可显式登记自定义或子代理来源；未登记但在已知工具根目录发现的候选会显示为 `pending_mapping`。

## 首次设置

```text
python -m pip install -r requirements.txt
```

macOS 如只有 python3，将命令中的 python 替换为 python3。最短首次设置路径是：

```text
python scripts/sync.py quick
python scripts/sync.py quick --apply
```

需要记忆映射或自定义路径时，再复制 `examples/device.remote.json` 为 `device.json`（或放在仓库外，通过 `--local` 指定）并按下文填写。

- 三台设备使用不同 device，例如 windows-a、windows-b、mac。
- state_dir 保存本机基线和备份，不同步、不删除。
- memory_repo 必须在 ai-config 外，三台电脑使用同一私有远程的各自克隆。
- 使用自定义 CODEX_HOME / CLAUDE_CONFIG_DIR 时，填写真实工具目录。
- codex_keys / claude_keys 选择共享字段，未选择的字段保留。
- codex_overrides / claude_overrides 保存本机参数，不填凭据。
- 不使用某工具时删除对应字段；没有 Codex 记忆目录时删除 codex_memory。

在 memories 数组添加项目映射，下面路径需要替换为本机真实路径：

```json
{
  "id": "langchain-learning",
  "path": "~/.claude/projects/本机项目目录名/memory"
}
```

同一项目三台设备 id 相同、path 可以不同。不同项目不得共用 id。首次向新设备导入到尚不存在的目录，可加 initialize: true；曾同步过的本机目录整体消失会报错，不推断为删除全部记忆。

记忆中发现凭据时同步停止，不输出匹配内容。需要保留本机原文但排除同步，可在该项目条目添加 `"exclude": ["相对文件名.md"]`。排除列表需在各设备配置；已进入共享历史的敏感文件不能仅靠排除解决。索引若引用被排除文件，其他电脑无法读取该条目。

## 全局规则和配置

```text
python scripts/sync.py rules --local device.json
python scripts/sync.py rules --local device.json --apply
python scripts/sync.py config --local device.json
python scripts/sync.py config --local device.json --apply
```

默认只读预览，列出精确目标，不输出敏感正文。rules 保留原全局文件，在受管区块生成 common/ 全部主题，避免悬空引用。首次迁移后可将旧共享规则整理进 common/，本机规则留在区块外。受管区块被本机直接修改时，后续覆盖会停止。

config 只更新选中字段。Codex TOML 保留其他字段和注释，Claude JSON 保留其他键。MCP、提供商、Windows 沙盒等未选择字段保持本机值。当前不自动转换 codex/mcp.json，也不假定清单中的 ${变量} 会自动展开。

Windows 旧入口 scripts/link-global.ps1 的 Preview / Apply 仍可用，现为 Python 包装，不再创建链接。已有符号链接需先人工迁移为普通文件，脚本会拒绝跟随链接写入。

每批变更先备份并写入事务日志，普通异常会回滚已写入文件；进程中断则由 `doctor` 识别并提供恢复选项。没有变化则不写文件。应用后启动新工具会话。

## 自动记忆

先关闭可能写入记忆的会话，等待后台更新完成。没有远程仓库时先初始化本地目录：

```text
python scripts/git-memory.py init --local device.json
python scripts/sync.py memory --local device.json
python scripts/sync.py memory --local device.json --apply
```

自动采集 Markdown，无需手工提炼。Claude 本机目录与 ai-memory/claude/项目标识/ 双向同步，Codex 只更新自己的设备快照。绝对路径不盲目替换，读取远端记忆时应使用当前项目路径。

在托管平台创建**私有空仓库**后，在 memory_repo 目录添加远程：

```text
git remote add origin <你的私有仓库地址>
```

需要发布时运行（会提交并推送）：

```text
python scripts/git-memory.py push --local device.json
```

推送前检查当前文件，仅允许 claude/、codex/ 下 Markdown；不强制推送。敏感检测是启发式，首次发布应审查内容，历史提交也不得含凭据。

另一台电脑克隆该仓库，设置本机映射后：

```text
python scripts/git-memory.py pull --local device.json
python scripts/sync.py memory --local device.json
python scripts/sync.py memory --local device.json --apply
```

推荐工作结束后同步并推送，另一台开始前拉取并同步。本地记忆仓库有修改时 pull 拒绝；远端分叉时只允许快进，不自动解决。先保留本地提交，人工合并 Git 冲突，再重新 memory 预览。

文件双方都改过时整批停止，保留双方原文；人工合并成一致内容后重试。正常文件删除通过本机基线传播；删除/修改冲突也停止。不要删整个目录模拟删除全部记忆。

## 项目配置维护

templates/project/ 提供两个入口，复制到新项目后填写真实运行、测试命令，随项目提交。项目规则独立演进，全局模板升级不会覆盖它。个人自动记忆保存在 ai-memory，不进入团队项目。大型项目按模块增加 AGENTS.md。

指令文档与工具参数的优先级不同。Codex 项目 .codex/config.toml 需项目受信任才加载；不要把个人默认习惯重复复制到所有项目。

## 恢复和验证

备份位于 `state_dir/backups/<operation-id>/`，事务日志位于 `state_dir/transactions/`。`doctor` 会识别中断事务；先检查 journal 的 `ROLLBACK_REQUIRED`、外部修改和备份，再重新执行或人工恢复，不能只删除锁文件。备份仅留本机。

```text
python -m pytest -q
python scripts/check-secrets.py
```

测试覆盖三方合并、最后文件删除、冲突、NFC／大小写／文件目录碰撞、计划失效、原规则保留、配置字段保留、异常回滚、快照不可变性和 Git 传输。macOS 真机、私有远程和新会话读取需接入后验收，不能把文件同步成功等同于模型采用全部记忆。

参考：[Claude 自动记忆](https://code.claude.com/docs/en/memory)、[Codex 记忆](https://learn.chatgpt.com/zh-Hans/docs/customization/memories)。
