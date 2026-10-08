# CLI 兼容说明

> 当前入口（2026-10-08）：桌面客户端的备份、恢复与恢复记录；仅使用原样备份 ZIP。云端冻结，以下旧包与命令流程为历史参考。详见 [当前任务](desktop-offline-migration.md)。


下文保留本轮之前的 CLI 说明与历史范围；最新客户端／迁移／服务器范围请以 [当前 README](../README.md) 为准。

# ai-config：多个 AI agent、多台设备共用一份配置

产品方向（2026-10-01）：以桌面客户端统一完成所有操作，跨设备同时支持用户服务器上传／下载与全量离线迁移包；导入时由客户端检测并调整 agent 目录。详见 [详细方案](desktop-client-plan.md) 与 [40 项实施任务](../DESKTOP-TASKS.md)，每项列出具体工作、依赖、交付物和验收条件。客户端、迁移包和服务器同步尚未实现，下文为现有 CLI 的使用说明。

以「配置库」为唯一真源：先把你系统里各个 AI agent（Codex、Claude Code、CodeBuddy、WorkBuddy、TRAE……）已有的规则识别出来并迁进配置库，再在设备之间同步这份配置，最后让每个 agent 都从这份配置取用。日常只需要一条命令，不需要手工编辑 JSON，也不需要理解 Git 内部结构。

要求 Python 3.11 或更高版本（开发使用 3.14）。支持 Windows 原生 Python 与 macOS Python。

## 能做什么

| 能力 | 说明 | 是否必需 |
| --- | --- | --- |
| 配置同步 | 公共规则和选定的工具设置在多台设备间保持一致 | 必需 |
| 多 agent 接管 | 同一份规则写入 Codex、Claude Code、CodeBuddy、WorkBuddy、TRAE 以及你声明的任何读取 Markdown 规则的 agent | 必需 |
| 识别 | `scan` 只读盘点本机所有 agent：规则入口、手写规则与配置库的重合度、skills、受保护文件（只列名称） | 需要时 |
| 迁入 | `migrate` 把各 agent 里已有的规则按章节迁进配置库：重复的默认移除，独有的由你决定 | 需要时 |
| 加载核验 | `verify-load` 用版本号问答证明 agent 的新会话确实读到了规则 | 需要时 |
| 退出接管 | `detach` 只移除 ai-config 写入的内容，可恢复迁入前的原件 | 需要时 |
| 环境检测 | 自动找到 Python、Git 和已安装的工具目录 | 必需 |
| 状态总览 | 用中文说明本机是否已应用、哪些设备待更新 | 必需 |
| 差异处理 | 工具界面改过的字段由你决定共享还是只留本机 | 需要时 |
| 撤销应用 | 按操作记录撤回上一次配置应用 | 需要时 |
| 记忆同步 | Claude 记忆双向同步，Codex 只导出参考快照 | 可选，不启用不影响配置 |
| 项目接续 | 在新设备上读取某个项目的最近交接 | 可选 |

配置同步**不依赖记忆功能**。只想统一配置时，不需要创建记忆仓库，也不会看到与记忆相关的错误。

## 三分钟上手

### 第一步：第一台设备

Windows 在项目目录运行：

```text
.\ai-config.ps1 setup
```

macOS 首次使用先赋予执行权限：

```text
chmod +x ai-config.command
./ai-config.command setup
```

不带 `--apply` 时只做只读检测，会列出检测到的系统和工具目录，不写入任何文件。确认输出无误后：

```text
.\ai-config.ps1 setup --apply
```

配置和共享规则默认保存在用户数据目录 `~/.ai-sync/`：`device.json` 是本机设备信息，`store/` 是本机配置库，`state/` 存放本机基线与恢复资料。程序安装目录不保存这些用户数据。无需手工编辑这些文件。

本机配置库可在没有 Git 的环境中建立和使用。要克隆已有的 Git 配置源，才需要设置 `--remote` 并安装 Git。

升级时若旧工作目录内已有 `device.json`，先预览导入和备份：

```text
.\ai-config.ps1 import-config --source .\device.json
.\ai-config.ps1 import-config --source .\device.json --apply
```

macOS 使用 `./ai-config.command import-config --source ./device.json`。导入会把经过校验的配置复制到用户数据目录，保留旧文件并在原位置生成备份；若新位置已有不同配置则停止，不会覆盖。

已有配置不会被丢弃：写入前会先备份，并告诉用户备份位置。

### 第二步：让另一台设备连接同一个 Git 配置源

本机离线配置库不会自行出现在第二台设备上。已有 Git 配置源的首台设备用以下方式加入：

```text
.\ai-config.ps1 setup --remote <已有配置源地址> --apply
```

其他设备用同一地址运行 `setup --remote <已有配置源地址> --apply`，各自克隆到本机的 `~/.ai-sync/store`。这一旧 CLI 传输方式需要 Git。桌面客户端的服务器登录同步和复制迁移包还未实现。设备 ID 自动生成；已有本机配置不会被克隆覆盖。

### 第三步：修改一次并同步

在任意一台设备上改好共享内容后：

```text
.\ai-config.ps1 sync            # 预览：会写哪些文件
.\ai-config.ps1 sync --apply    # 应用
```

如果这次修改是在本机用 `diff --choice share` 保存的（或者你想把自己配置源副本里的共享修改发出去），发布是单独的一步：

```text
.\ai-config.ps1 sync --publish --apply   # 先把共享修改提交并推送到配置源远端，再应用到本机
```

在另一台设备上加 `--fetch` 同步，即可拿到这次修改：

```text
.\ai-config.ps1 sync --fetch --apply
```

每次同步都会分别打印四行结果：**下载共享配置 / 远端发布 / 本机应用 / 状态上报**。四件事各自独立，不会互相代替。

### 第四步：确认状态

```text
.\ai-config.ps1 status
```

输出示例：

```text
设备：windows-a
配置源：git（已确认）
共享版本：a30c5a6fcda9
本机配置状态：已应用
  codex · AGENTS.md：已应用（受管：rules）
  codex · config.toml：已应用（受管：approval_policy）
最近成功应用时间：2026-09-15T12:30:57+00:00
下一步：无需操作。
```

如果显示“需要启动新会话”，说明文件已经写好并核对过，但工具要重开才会加载。这两件事是分开的，脚本不会把前者说成后者。

## 接管更多 agent

```text
.\ai-config.ps1 scan                        # 只读：本机有哪些 agent、各自的规则在哪、和配置库重合多少
.\ai-config.ps1 migrate                     # 预览：要登记哪些 agent、哪些旧规则是重复的、哪些是独有的
.\ai-config.ps1 migrate --apply             # 执行默认动作：登记 agent、移除完全重复的段落（先备份）
.\ai-config.ps1 migrate --item 4 --choice adopt --apply   # 独有内容逐项决定：adopt / keep / remove / skip
.\ai-config.ps1 sync --apply                # 把配置库写入每个 agent 的规则入口
.\ai-config.ps1 verify-load --agent workbuddy   # 按提示在新会话里问版本号，再用 --answer 核验
```

各 agent 的规则入口：

| agent | 写入位置 | 方式 |
| --- | --- | --- |
| Codex | `~/.codex/AGENTS.md` | 受管区块（区块外内容归你） |
| Claude Code | `~/.claude/CLAUDE.md` | 受管区块 |
| CodeBuddy | `~/.codebuddy/rules/ai-config.md` | 独占文件（整份归 ai-config） |
| WorkBuddy（含第二个实例 `~/.workbuddy-ai`） | `AGENTS.md` | 受管区块；该入口只有社区资料佐证，请用 `verify-load` 确认 |
| TRAE / TRAE CN | `user_rules/ai-config.md` 或 `user_rules.md` | 先看本机是目录还是文件再决定；两者都没有时不写 |
| 其他 agent | 你声明的入口 | `declare --agent <标识> --root <目录> --entry <相对路径.md>` |

SOUL.md、USER.md、MEMORY.md、记忆目录、skills、MCP、凭据与会话文件都**不写**；`scan` 只列出它们的名称。

## 命令速查

默认输出中文。加 `--json` 得到机器可读结果，加 `--verbose` 查看脱敏技术详情。

| 命令 | 读 / 写 | 用途 |
| --- | --- | --- |
| `setup` | 检测只读；`--apply` 写本机配置 | 首次设置、加入已有配置源；`--store` 使用独立配置库 |
| `import-config` | 预览只读；`--apply` 复制并核验 | 把旧位置的 `device.json` 导入用户数据目录，并在旧位置留备份 |
| `scan` | 只读（`--apply` 只保存报告） | 盘点本机所有 agent、规则、skills 与受保护文件 |
| `migrate` | 预览只读；`--apply` 迁入 | 把已有规则迁进配置库、登记 agent |
| `detach` | 预览只读；`--apply` 退出 | 让某个 agent 退出接管，可 `--restore-original` |
| `verify-load` | 只读（`--apply` 记录结果） | 核验 agent 新会话是否读到规则 |
| `declare` | 预览只读；`--apply` 登记 | 登记自定义 agent，或放在非默认目录的已知 agent |
| `sync` | 预览只读；`--apply` 写目标文件 | 日常同步；`--fetch` 下载配置源，`--publish` 发布本机共享修改 |
| `status` | 只读 | 查看本机状态和其他设备回执 |
| `diff` | 只读；`--apply` 保存选择 | 查看字段差异并决定归属 |
| `undo` | 只读；`--apply` 恢复 | 按操作撤销上一次配置应用 |
| `memory-setup` | 只读；`--apply` 保存映射 | 可选：启用记忆同步 |
| `project` | 只读 | 可选：查看项目交接 |
| `doctor` | 只读（`--recover` 才写） | 检查来源与未完成事务 |

稳定的退出码：`0` 正常或预览、`2` 尚未具备条件、`3` 待上报或网络问题、`4` 冲突、`1` 其他错误。**预览返回 `0` 不代表已经应用**，请以输出中的状态文字为准。

## 进一步阅读

- [入门详解](getting-started.md)：每一步在做什么，以及为什么这样设计。
- [遇到问题](troubleshooting.md)：常见错误编号、含义和处理方式。
- [高级说明](advanced.md)：目录格式、快照与事务、兼容入口、共享字段清单。
- [验收记录](acceptance.md)：三台实机的验收清单与结果。

## 边界说明

- Codex 快照是**跨设备参考资料**，不是已经验证的原生记忆数据库导入。脚本不回填 Codex 原生记忆，不做 Claude/Codex 语义转换。
- 敏感信息（凭据、登录、会话、Cookie）永不进入共享字段集合；配置里出现这类字段会被直接拒绝。记忆中发现凭据时同步停止，且不输出匹配内容。
- 当前是显式同步命令，不安装后台监听服务。
- 新 agent 只接管规则入口：WorkBuddy 的 `AGENTS.md` 入口和 TRAE 的规则形态需要在装有该 agent 的环境里用 `verify-load` 实测，结果记在 [验收记录](acceptance.md)。
- skills 目前只盘点不同步；CC Switch 等管理工具接管的字段（如 `settings.json` 的 `env`）和 skills 链接一律不碰。
- 豆包桌面版的个性化设置存在云端，本地没有规则入口，只做识别。
- 跨设备同步成功不等于模型已经采用共享内容；工具需要新会话加载。
- 真实三机验收需要两台 Windows 和一台 Mac 实机，不能用 Windows 目录模拟 Mac。
