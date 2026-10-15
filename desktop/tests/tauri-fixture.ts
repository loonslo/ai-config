// Browser-only test transport, enabled exclusively by Vite's ui-test mode.
type Handler = (value: unknown) => void
const events: Record<string, Handler> = {}
let lastChoices: Record<string, string> = {}
const contentGroups = Object.entries({ rules: '规则', memory: '记忆与笔记', skills_own: '我写的技能与脚本', skills_third: '第三方技能（含来源）', approvals: '已批准的操作', settings: '设置与信任', history: '历史记录（体积较大）' }).map(([id, name]) => ({ id, name, default: id !== 'history', available: true }))
function syncFixture(req: { type: string; operation?: string; params?: { flagged_policy?: string; groups?: string[]; conflict_choices?: Record<string, string> } }) {
  const applied = req.type === 'apply'
  if (req.operation === 'machine_backup') return {
    entries: 14, projects: 2, exclusions: [], destination: 'C:\\Fixture\\AI备份.zip',
    by_group: Object.fromEntries((req.params?.groups ?? []).map(id => [id, { files: 2, bytes: 1024 }])),
    flagged: { policy: req.params?.flagged_policy ?? 'redact', count: 1, items: [{ id: 'f0001', logical_path: 'claude:main/skills/diary/SKILL.md', lines: [12], action: req.params?.flagged_policy === 'skip' ? 'skipped' : 'redacted' }] },
    skills: { total: 5, third_party: 2, unknown_source: 1, diverged_copies: 1 }, coverage: { unclassified: 1, complete: true, samples: ['codex_home/new-feature.json'] },
  }
  const conflicts = ['SKILL.md', 'data.txt'].map((name, i) => ({ entry_id: `skill-${i}`, agent: 'codex', kind: 'skills', target: `C:\\Fixture\\Codex\\skills\\diary\\${name}`, conflict_group: 'skill:diary', conflict_scope: 'codex:main::codex-global', reason: 'file_differs', decision: req.params?.conflict_choices?.[`skill-${i}`] ?? 'pending' }))
  return { bundle_agents: ['codex', 'shared'], bundle_groups: ['rules', 'skills_own', 'settings', 'history'], source_projects: [],
    conflicts, writes: 2, pending_conflicts: conflicts.filter(v => v.decision === 'pending').length, skipped: [], running: [],
    redacted_todo: 1, needs_rebuild: 1, exports: [{ name: 'restore-env.ps1', target: 'C:\\Fixture\\Reports\\restore-env.ps1' }],
    ...(applied ? { todo: '- 需要重新填写密钥。\n- 请核对导出的环境变量脚本。\n' } : {}),
  }
}
type HistoryParams = { flagged_policy?: string; groups?: string[] }
let lastHistoryParams: HistoryParams = {}
function historyFixture(req: { type: string; operation?: string; params?: HistoryParams }) {
  const params = req.type === 'apply' ? lastHistoryParams : req.params ?? {}
  if (req.type === 'preview') lastHistoryParams = params
  const selected = params.groups?.includes('history') ?? false
  const skip = params.flagged_policy === 'skip'
  const history = selected ? { parts: skip ? 2 : 3, files: skip ? 3 : 5, bytes: (skip ? 400 : 600) * 1024 * 1024, redactions: skip ? 0 : 2,
    packages: (skip ? [1, 2] : [1, 2, 3]).map(i => ({ name: `AI备份-历史-${i}.zip` })),
    exclusions: [{ agent: 'codex', relative: 'sessions/long.bin', reason: 'line_too_long' },
      ...(skip ? ['one', 'two'].map(name => ({ agent: 'codex', relative: `sessions/${name}.jsonl`, reason: 'secret_file_skipped' })) : [])] } : null
  if (req.operation === 'machine_backup') return { entries: 7, projects: 0, destination: 'C:\\Fixture\\AI备份.zip', history,
    by_group: { rules: { files: 2, bytes: 512 }, ...(history ? { history: { files: history.files, bytes: history.bytes } } : {}) },
    exclusions: Array.from({ length: 22 }, (_, i) => ({ logical_path: `claude:main/skills/sample/file-${i + 1}.md`, reason: i === 0 ? 'enumeration_failed' : 'metadata_unreadable' })),
    coverage: { complete: false, unclassified: 0 },
    flagged: { policy: params.flagged_policy ?? 'redact', count: selected ? 2 : 0, items: selected ? [
      { id: 'h0001', logical_path: 'codex:history/sessions/one.jsonl', lines: skip ? [5] : [5, 7], line_count: skip ? 1 : 8, lines_truncated: !skip, action: skip ? 'skipped' : 'redacted' },
      { id: 'h0002', logical_path: 'codex:history/sessions/two.jsonl', lines: [], line_count: skip ? 1 : 4, lines_truncated: true, action: skip ? 'skipped' : 'redacted' },
    ] : [] } }
  return { bundle_agents: ['codex'], bundle_groups: ['rules', 'history'], source_projects: [], history,
    conflicts: [], skipped: [], running: [], writes: (params.groups === undefined || params.groups.includes('rules') ? 2 : 0) + (history?.files ?? 0), pending_conflicts: 0,
    ...(req.type === 'apply' ? { todo: '- 历史记录仅新增或另存，不保证可继续对话。\n' } : {}) }
}
function restoreFixture(req: { type: string; params?: { conflict_choices?: Record<string, string> } }, fail: boolean) {
  if (req.type === 'preview') lastChoices = req.params?.conflict_choices ?? {}
  const applied = req.type === 'apply'
  const conflicts = [
    { entry_id: 'rules', agent: 'codex', kind: 'rules', target: 'C:\\Fixture\\Codex\\AGENTS.md', reason: 'file_differs' },
    ...['model_reasoning_effort', 'personality'].map(field => ({ entry_id: 'settings', agent: 'codex', kind: 'settings_fields', target: 'C:\\Fixture\\Codex\\config.toml', reason: 'field_differs', field })),
  ].map(v => ({ ...v, decision: lastChoices[v.entry_id] ?? 'pending' }))
  const checks = [
    { label: 'Codex 规则', status: lastChoices.rules === 'keep' ? 'KEPT' : 'PASS', target: 'C:\\Fixture\\Codex\\AGENTS.md' },
    { label: 'Codex 设置', status: lastChoices.settings === 'keep' ? 'KEPT' : 'PASS', target: 'C:\\Fixture\\Codex\\config.toml', verified_fields: ['model_reasoning_effort', 'personality'] },
    ...Array.from({ length: 26 }, (_, i) => ({ label: 'Codex 技能', status: fail && i === 0 ? 'FAIL' : 'PASS', target: `C:\\Fixture\\Codex\\skills\\demo\\skill-${i + 1}.md` })),
    ...Array.from({ length: 3 }, (_, i) => ({ label: 'WorkBuddy AI 记忆', status: 'SKIP', reason: 'agent_not_selected', logical_path: `workbuddy-ai:memory/note-${i + 1}.md` })),
    { label: '助手实际读取规则与记忆', status: 'MANUAL' },
  ]
  const groups = [
    { label: 'Codex 规则', kind: 'rules', check_indexes: [0] }, { label: 'Codex 设置', kind: 'settings_fields', check_indexes: [1] },
    { label: 'Codex 技能', kind: 'skills_text', check_indexes: Array.from({ length: 26 }, (_, i) => i + 2) },
    { label: 'WorkBuddy AI', kind: 'not_selected', check_indexes: [28, 29, 30] }, { label: '环境与加载确认', kind: 'followup', check_indexes: [31] },
  ].map(g => ({ ...g, counts: g.check_indexes.reduce<Record<string, number>>((acc, index) => { const status = checks[index].status; acc[status] = (acc[status] ?? 0) + 1; return acc }, {}) }))
  return {
    ...(!applied ? { bundle_agents: ['codex', 'workbuddy-ai'], source_projects: [] } : {}),
    writes: 26 + (lastChoices.rules === 'overwrite' ? 1 : 0) + (lastChoices.settings === 'overwrite' ? 1 : 0), conflicts,
    pending_conflicts: conflicts.filter(v => v.decision === 'pending').length,
    skipped: conflicts.filter(v => v.decision === 'keep').map(v => ({ ...v, reason: 'kept_local' })), running: [],
    ...(applied ? { backup: 'C:\\Fixture\\Backups\\originals',
      verification: { checks, groups, counts: checks.reduce<Record<string, number>>((acc, v) => { acc[v.status] = (acc[v.status] ?? 0) + 1; return acc }, {}), exit_code: fail ? 4 : 0, questions: [] },
      todo: '# 接下来要做的事\n\n- 在新会话里确认规则和记忆。\n- 确认所需助手已登录。\n' } : {}),
  }
}
export const Command = { sidecar: () => ({
  stdout: { on: (event: string, callback: Handler) => { events[event] = callback } },
  on: () => {},
  spawn: async () => ({ write: async (text: string) => {
    const req = JSON.parse(text)
    const transport = new URLSearchParams(location.search).get('transport')
    if (transport === 'silent' || transport === 'apply-silent' && req.type === 'apply') return
    const operation = req.operation
    const result = operation === 'machine_detect'
      ? { agents: [{ id: 'codex', name: 'Codex', installed: true, root: 'C:\\Fixture\\Codex' }, ...(transport === 'sync-groups' ? [{ id: 'shared', name: '通用技能', installed: true, root: 'C:\\Fixture\\Shared' }] : [])], projects: transport === 'sync-groups' ? ['C:\\Fixture\\Project1', 'C:\\Fixture\\Project2'] : [], groups: contentGroups }
      : operation === 'machine_history' ? { operations: [] }
      : transport === 'sync-history' ? historyFixture(req)
      : transport === 'sync-mcp' ? { bundle_agents: ['claude'], bundle_groups: ['settings'], source_projects: [],
        writes: req.params?.confirm_security ? 1 : 0, conflicts: [], skipped: [], running: [], security_list: [
          { agent: 'claude', instance: 'main', project: null, field: 'mcpServers.remote.url', value: 'https://global.example/mcp' },
          { agent: 'claude', instance: 'main', project: 'C:\\Fixture\\first.new', field: 'mcpServers.remote.url', value: 'https://first.example/mcp' },
          { agent: 'claude', instance: 'main', project: 'C:\\Fixture\\second.new', field: 'mcpServers.remote.url', value: 'https://second.example/mcp' },
          { agent: 'claude', instance: 'desktop', project: null, field: 'preferences.locale', value: 'zh' },
        ] }
      : transport === 'sync-groups' ? syncFixture(req)
      : operation === 'machine_backup' ? { entries: 7, projects: 1, exclusions: [], destination: 'C:\\Fixture\\AI备份.zip' }
      : ['restore-choices', 'restore-fail'].includes(transport ?? '') ? restoreFixture(req, transport === 'restore-fail')
      : { bundle_agents: ['codex'], writes: 2, conflicts: [], skipped: [], running: [], source_projects: [] }
    window.setTimeout(() => events.data?.(JSON.stringify({ type: 'result', request_id: req.request_id,
      status: req.type === 'apply' ? 'applied' : 'preview', result,
      can_apply: req.type === 'preview' && !['machine_detect', 'machine_history'].includes(operation) && !('pending_conflicts' in result && result.pending_conflicts), plan_id: 'fixture-plan' }) + (transport === 'crlf' ? '\r\n' : '')), 20)
  } }),
}) }
export async function invoke() { return null }
export async function listen() { return () => {} }
export function getCurrentWindow() { return { onDragDropEvent: async () => () => {}, onCloseRequested: async () => () => {}, destroy: async () => {} } }
export async function open(options: { directory?: boolean }) { return options.directory ? 'C:\\Fixture\\Backups' : 'C:\\Fixture\\AI备份.zip' }
