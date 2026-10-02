# ai-config 仓库规则

- `common/` 是跨工具规范的源文件；修改通用规则时先改那里。
- `codex/` 和 `claude/` 只保存可同步的模板，不保存登录状态、缓存、插件或机器专属路径。
- 运行 `scripts/check-secrets.ps1` 后再提交。
- 运行挂载脚本前使用 `-Mode Preview`；脚本必须备份已有全局文件。
- 不要把任何 API Key、Access Token、Cookie、私钥或真实凭据写进仓库。
- 项目自身的开发规则统一放在对应项目根目录的 `AGENTS.md`，不要为了方便把项目细节写进全局规则。
- 运行 pytest 时为每次运行指定全新的 `--basetemp` 目录（例如 `tmp/run-<n>`），避免旧 `tmp_path` 内容干扰本次测试。

## 项目进度摘要

完成有实质进展的任务后，先更新项目原有任务与验证记录，再核对根目录 `PROJECT_STATUS.md` 的概览、进度、下一步、证据和日期。文件变化本身不代表任务完成。

## PROJECT_STATUS 同步契约（v1）

有实质进展时先更新项目内任务和验收记录，再更新根目录 `PROJECT_STATUS.md`；交付前校验以下格式。只维护本项目，不自动写入日常 vault，不把文件存在、格式通过或 Git 改动当作完成。

- 文件以 YAML frontmatter 开始，字段名不得重复；必填 `project_id`、`updated`、`status`、`overview`、`progress`、`next`、`evidence`。
- `project_id` 与登记的工作区相对路径一致，路径中的 `/` 替换为 `-`；本项目为 `ai-config`。
- `updated` 使用未加引号的真实 `YYYY-MM-DD` 日期，表示摘要维护日期；纯格式修订也可更新，但须在正文记录修订日期、原进展日期及未重新验收的边界。
- `status` 只允许 `active`（进行中）、`waiting`（等待输入）、`paused`（已延期）、`unknown`（待核实）；正在推进统一用 `active`，禁止 `in_progress`。它是项目跟进状态，不代表所有功能已经验收，也不使用 `done`。
- `overview`、`progress`、`next` 为非空字符串；复杂文字用 YAML 引号或块字符串。`progress` 区分实际通过、历史记录及尚未验收的事项。
- `evidence` 为非空字符串列表，只填项目内现存文件的相对路径，使用 `/`；禁止网址、描述文字、绝对路径、`.`/`..` 路径段、隐藏目录/文件、越界链接和 `PROJECT_STATUS.md` 自引用。不得读取或引用凭据、认证、运行目录；`runtime/`、`tmp/`、`temp/`、`logs/`、`storage/logs/` 下的文件不能作为 evidence 正本，核对过的结果应写入稳定任务/验收文档。
- URL、测试命令、结果、部署编号和说明写入项目内任务或验收文件，再由 `evidence` 引用该文件；注明实际验证日期、环境、结果及未验证项。迁移旧摘要文字时标为历史记录搬迁，不能冒充本次复测。
- 同步契约说明和模板位于日常库 `output/项目进展同步/README.md`、`PROJECT_STATUS.template.md`；本节保留完整字段规则，项目离开共同工作区后仍适用。跨项目访问须遵守既有项目边界；仅在用户本次明确授权访问日常同步工具且工具可用时，从共同工作区执行 `py -3.14 -B notebook_obsidian/日常/output/项目进展同步/sync_project_status.py --check --project ai-config`，只检查格式和证据路径，不读取或写入待办。

- 未使用同步工具时，仍须在本项目内逐项自检字段、状态与证据路径，并报告未通过项；不能跳过摘要维护。新建独立项目时先补齐本节约束和 PROJECT_STATUS.md，未知业务进度用 unknown，不因目录存在而推断完成。
