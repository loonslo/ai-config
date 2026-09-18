# 三机验收记录

本文记录跨设备配置一致性的功能验收与零基础可用性验收。

**当前状态：部分完成。** 自动化部分已在单机完成并可复现；三台真实设备的验收需要用户提供硬件与私有远端，尚未执行。

## 一、自动化验收（已完成）

### 复现方式

```text
python -m pip install -r requirements.txt
python -m pytest -q --basetemp=tmp/run-<新编号>
```

必须为每次运行使用**全新的** `--basetemp` 目录。复用同一个目录会与上次运行留下的 `tmp_path` 内容冲突，产生大批与本改动无关的失败。

### 结果

| 项目 | 结果 |
| --- | --- |
| 全量测试 | 145 通过 / 0 失败 |
| 运行时长 | 约 70 秒 |
| 平台 | Windows 11，Python 3.13.14 |
| 敏感信息扫描 | `scripts/check-secrets.py` → 0 findings |

### 覆盖范围

| 需求 | 覆盖方式 |
| --- | --- |
| 结构版本可验证、未知版本拒绝 | `tests/test_config_consistency.py` |
| 受管字段来自设备实际选择 | `tests/test_config_consistency.py` |
| 凭据/会话字段被拒绝共享 | `tests/test_config_consistency.py` |
| 目标文件缺失不判为已应用 | `tests/test_config_consistency.py` |
| 只改未受管内容不误报漂移 | `tests/test_config_consistency.py` |
| 环境检测无写入、缺依赖有中文指引 | `tests/test_config_consistency.py` |
| 启动脚本不依赖当前目录、不重复安装 | `tests/test_ux_flows.py` |
| 首次设置与加入流程幂等 | `tests/test_ux_flows.py` |
| 预览零写入、重复执行无多余写入 | `tests/test_ux_flows.py` |
| 配置同步不要求存在记忆仓库 | `tests/test_ux_flows.py` |
| 状态可读且只配置用户不见记忆错误 | `tests/test_ux_flows.py` |
| 回执分支隔离、并发上报不覆盖 | `tests/test_ux_flows.py` |
| 回执不含真实路径与敏感值 | `tests/test_ux_flows.py` |
| 差异展示遮蔽敏感字段 | `tests/test_ux_flows.py` |
| share / local / restore 三种归属 | `tests/test_ux_flows.py` |
| 手改规则区块后 diff 必须列出该行 | `tests/test_ux_flows.py` |
| 恢复闭环可走完（restore 后 sync 成功） | `tests/test_ux_flows.py` |
| 规则区块拒绝 `local`、提示不列被拒选项 | `tests/test_ux_flows.py` |
| restore 意图一次性，不掩盖后续手改 | `tests/test_ux_flows.py` |
| 敏感值不可共享也不可覆盖 | `tests/test_ux_flows.py` |
| 按操作恢复、备份损坏拒绝 | `tests/test_ux_flows.py` |
| 错误不抛 traceback、JSON 与退出码一致 | `tests/test_config_consistency.py` |
| 记忆不启用时配置独立成功 | `tests/test_onboarding.py` |
| 含凭据来源保持阻断态 | `tests/test_onboarding.py` |
| 新项目自动推导 ID | `tests/test_onboarding.py` |
| 历史交接与当前交接不混淆 | `tests/test_onboarding.py` |

### 端到端手工验证（单机）

在隔离目录中用真实 `device.json` 走完整流程：

| 步骤 | 命令 | 观察结果 |
| --- | --- | --- |
| 1 | `sync.py status --local <dev>` | 中文输出，四个目标均为“未设置” |
| 2 | `sync.py sync --local <dev>` | 列出 5 个将要写入的路径，目录仍为空 |
| 3 | `sync.py sync --local <dev> --apply` | “已应用 5 处共享配置变更” + 需要新会话提示 |
| 4 | `sync.py status --local <dev>` | 三个目标“已应用”，一个无受管字段“未设置” |
| 5 | 手工改受管区块 | 状态变为“存在本机修改” |
| 6 | `sync.py sync --local <dev>` | 退出码 4，E3001，说明运行 diff |
| 7 | `sync.py diff --local <dev>` | 列出“公共规则（rules）”一行，只提供 share / restore |
| 8 | `sync.py diff --local <dev> --choice restore --apply` | 打印“已保存”；此时尚未改目标文件 |
| 9 | `sync.py sync --local <dev> --apply` | 退出码 0；手改内容被共享区块覆盖，区块外原文保留 |
| 10 | `sync.py sync --local <dev> --apply`（再跑一次） | 退出码 0 且零变更，闭环不再报冲突 |
| 11 | `sync.py undo --local <dev> --index 1` | 预览列出 `AGENTS.md`，可找回被覆盖的内容 |

以上第 5–11 步是**回归重点**：修复前第 7 步会打印“没有需要处理的字段差异”，用户按提示操作后第 9 步仍然失败，文档承诺的恢复路径实际走不通。

## 二、三机功能验收（待执行）

需要用户提供以下条件后才能进行。**不能用 Windows 目录模拟 Mac。**

| 条件 | 说明 |
| --- | --- |
| 两台 Windows 设备 | 例如 windows-a、windows-b |
| 一台 Mac | 真实 macOS 实机 |
| 一个配置源远端 | Git 地址，三台设备共同克隆 |
| Python 3.11+ | 三台设备均需满足 |

### 验收清单

每一项需分别记录 Windows A、Windows B、Mac 的版本与结果。

| # | 场景 | 通过标准 |
| --- | --- | --- |
| 1 | 首次安装（A） | 只读检测正确；`--apply` 后配置生成；A 状态为已应用 |
| 2 | 加入（B、Mac） | 复用共享选择，不要求重选全部参数；ID 不冲突 |
| 3 | 重复加入 | 幂等，不产生半套配置 |
| 4 | A 修改 → B 获取 | B 同步后状态为已应用；A 与 B 受管字段一致 |
| 5 | A 修改 → Mac 获取 | 同上，且路径差异不被判为冲突 |
| 6 | 三机回执核对 | 每台能看到另外两台“最近报告于”；无设备被标为在线 |
| 7 | 离线重试 | 断网时退出码 3 且本机状态不变；恢复后重试成功 |
| 8 | 本机覆盖 | `--choice local` 后不影响其他两台 |
| 9 | 远端冲突 | 双方都改同一字段时停止并保留双方内容 |
| 10 | 目标文件被工具改写 | `status` 识别为存在本机修改 |
| 11 | 撤销上次应用 | `undo --apply` 后受管字段回到当时值 |
| 12 | 回执上传失败 | 本机已应用状态保留，另报 E5001 |
| 13 | 单工具设备 | 只装一个工具时正常工作 |
| 14 | 未启用记忆 | 全流程无记忆相关错误 |
| 15 | Mac 执行权限 | `chmod +x ai-config.command` 后可运行 |

### 记录表（填写用）

```text
设备 A：windows-a   版本：          日期：
设备 B：windows-b   版本：          日期：
设备 C：mac         版本：          日期：
配置源提交：
```

## 三、零基础可用性验收（待执行）

需要一位**未参与开发**的使用者，只按 `README.md` 与 `docs/getting-started.md` 操作。

### 记录要求

| 项目 | 记录内容 |
| --- | --- |
| 卡点 | 在哪个步骤停下、停了多久 |
| 误解 | 把什么理解成了什么 |
| 是否需要口头帮助 | 是 / 否；如果需要，帮的是什么 |
| 是否误改 JSON | 是 / 否 |

### 通过标准

- 全程**无需手工编辑 JSON**。
- 日常同步只用**一个入口**。
- 用户能用自己的话准确说明：
  1. 本机是否已应用；
  2. 哪些设备待更新；
  3. 失败后如何继续。
- 三台设备的测试报告完整。

## 四、已知限制

- 三机验收与零基础验收尚未执行，需要实机与外部远端。
- Codex 导出是参考快照，不是原生记忆数据库导入；未验证模型是否采用快照内容。
- 跨设备同步成功不等于工具已加载；需要新会话。
- 敏感检测是启发式的，首次发布共享内容前应人工复核。
- 独立加密备份目的地仍属于原可靠性计划，不因体验改造取消。
