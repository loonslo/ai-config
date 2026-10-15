import { useCallback, useEffect, useRef, useState } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { open } from '@tauri-apps/plugin-dialog'
import { Command, type Child } from '@tauri-apps/plugin-shell'
import { ConflictPanel, SkippedPanel, VerificationPanel, NextSteps, type Conflict, type ConflictChoices, type Skipped, type VerificationReport } from './RestoreReport'
import { UiIcon } from './UiIcon'
import './Machine.css'

type Page = 'backup' | 'restore' | 'history'
type Agent = { id: string; name: string; installed: boolean; root: string }
type ContentGroup = { id: string; name: string; default: boolean; available: boolean }
type Mapping = { from: string; to: string }
type Report = {
  groups?: ContentGroup[]; bundle_groups?: string[]; by_group?: Record<string, { files: number; bytes: number }>
  project_labels?: Record<string, string>
  flagged?: { policy: 'redact' | 'skip'; count: number; items: Array<{ id: string; logical_path: string; lines: number[]; action: string; line_count?: number; lines_truncated?: boolean }> }
  skills?: { total: number; third_party: number; unknown_source: number; diverged_copies: number; unverified_copies?: number }
  coverage?: { unclassified: number; complete: boolean; samples?: string[] }
  history?: { parts: number; files: number; bytes: number; redactions: number; packages: Array<{ name: string }>; exclusions: Array<{ agent: string; relative: string; reason: string }> } | null
  redacted_todo?: number; needs_rebuild?: number; exports?: Array<{ name: string; target: string }>
  agents?: Agent[]; projects?: number | string[] | Record<string, string | null>; entries?: number
  destination?: string; bytes?: number; sha256?: string; writes?: number
  exclusions?: Array<{ logical_path: string; reason: string }>
  warnings?: Array<{ message: string }> | string[]; running?: string[]
  source_projects?: Array<{ id: string; path: string; mapping_source?: string }>; bundle_agents?: string[]
  security_list?: Array<{ agent: string; instance?: string; project?: string | null; field: string; value: unknown }>
  trust_list?: Array<{ path: string }>
  conflicts?: Conflict[]; pending_conflicts?: number; backup?: string
  skipped?: Skipped[]
  operations?: Array<{ operation_id: string; created_at: string; change_count?: number; changes?: Array<{ path: string }> }>
  paths?: string[]; todo?: string; report_dir?: string
  verification?: VerificationReport
}
type Reply = { type: string; request_id?: string; stage?: string; status?: string; can_apply?: boolean; plan_id?: string; result?: Report; error?: { code: string; message: string } }
const labels: Record<string, string> = { claude: 'Claude', codex: 'Codex', workbuddy: 'WorkBuddy', 'workbuddy-ai': 'WorkBuddy AI', shared: '通用技能', system: '环境变量' }
const groupNames: Record<string, string> = { rules: '规则', memory: '记忆与笔记', skills_own: '我写的技能与脚本', skills_third: '第三方技能（含来源）', approvals: '已批准的操作', settings: '设置与信任', history: '历史记录（体积较大）' }
const groupDescriptions: Record<string, string> = { rules: '全局与项目开发规范', memory: '助手记忆、计划与笔记', skills_own: '保留你的指令与工具', skills_third: '携带技能及可用来源信息', approvals: '已登记的操作权限', settings: '支持的设置与信任记录', history: '体积较大，可能需要几分钟；不保证可继续对话。' }
const navigation: Array<{ page: Page; label: string; description: string }> = [
  { page: 'backup', label: '备份', description: '保存这台电脑的配置' },
  { page: 'restore', label: '恢复', description: '从备份迁移到本机' },
  { page: 'history', label: '恢复记录', description: '查看记录与撤销' },
]
const stages: Record<string, string> = { started: '开始检查…', planning: '正在检查内容…', scanning: '正在检查助手文件…', rechecking_preview: '重新检查文件是否变化…', applying: '正在写入并核验…' }
const errors: Record<string, string> = { E_PLAN_STALE: '文件或选项在检查后发生变化，请重新检查后确认。', E_PLAN_UNKNOWN: '检查结果已过期或已使用，请重新检查。' }
const historyExclusions: Record<string, string> = { unsupported_history_format: '当前尚不支持此历史格式', protected_history_path: '凭据或运行文件，未读取', link_blocked: '路径含链接', unsafe_history_path: '路径无法安全迁移', line_too_long: '单行超过处理上限', invalid_jsonl: '历史格式或编码无效', secret_file_skipped: '按选择跳过含密钥文件', redaction_parse_failed: '隐藏密钥后格式无法使用', redaction_incomplete: '仍含无法隐藏的密钥', unreadable: '无法读取', not_regular_file: '不是普通文件', private_key_block_too_long: '私钥块超过安全处理上限，整份未携带', redaction_format_limit: '文件超过格式复查上限，整份未携带' }
const backupExclusions: Record<string, string> = { ...historyExclusions, enumeration_failed: '目录无法枚举', metadata_unreadable: '文件信息无法读取', path_too_long: '路径超过处理上限', too_large: '文件超过大小上限', build_artifact: '可重新生成的文件', secret_hit: '按选择跳过含密钥文件', skipped_by_policy: '按处理规则跳过', excluded_by_config: '按排除设置跳过', non_text: '未作为可迁移文本携带' }
function restoreCompletion(report?: VerificationReport) {
  const failures = report?.counts?.FAIL ?? 0
  return failures ? `写入已结束，但有 ${failures} 项核验失败，请展开检查。` : '恢复写入已完成，请查看核验汇总和后续事项。'
}
function uniquePaths(paths: string[]) {
  const seen = new Set<string>()
  return paths.filter(path => {
    const key = /^[a-z]:|^\\\\/i.test(path) ? path.replace(/\\/g, '/').replace(/\/$/, '').toLowerCase() : path
    if (seen.has(key)) return false
    seen.add(key); return true
  })
}
function folderName(path: string) { return path.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || path }

export default function MachineApp() {
  const [page, setPage] = useState<Page>('backup')
  const [agents, setAgents] = useState<Agent[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [contentGroups, setContentGroups] = useState<ContentGroup[]>([])
  const [backupGroups, setBackupGroups] = useState<string[]>(Object.keys(groupNames).filter(id => id !== 'history'))
  const [restoreGroups, setRestoreGroups] = useState<string[] | null>(null)
  const [flaggedPolicy, setFlaggedPolicy] = useState<'redact' | 'skip'>('redact')
  const [restoreAgents, setRestoreAgents] = useState<string[] | null>(null)
  const [projects, setProjects] = useState<string[]>([])
  const [projectLabels, setProjectLabels] = useState<Record<string, string>>({})
  const [destination, setDestination] = useState('')
  const [bundle, setBundle] = useState('')
  const [maps, setMaps] = useState<Mapping[]>([])
  const [security, setSecurity] = useState(false)
  const [trust, setTrust] = useState(false)
  const [workbuddy, setWorkbuddy] = useState(false)
  const [conflictChoices, setConflictChoices] = useState<ConflictChoices>({})
  const [report, setReport] = useState<Report | null>(null)
  const [history, setHistory] = useState<NonNullable<Report['operations']>>([])
  const [plan, setPlan] = useState<string | null>(null)
  const [message, setMessage] = useState('选择助手与工作文件夹，开始备份。')
  const [busy, setBusy] = useState(false)
  const [applied, setApplied] = useState(false)
  const [restoreDirty, setRestoreDirty] = useState(false)
  const [retryRestore, setRetryRestore] = useState(false)
  const [activeRequest, setActiveRequest] = useState<{ op: string; applying: boolean } | null>(null)
  const child = useRef<Child | null>(null)
  const spawning = useRef<Promise<Child> | null>(null)
  const locked = useRef(false)
  const operation = useRef('')
  const requestId = useRef('')
  const closing = useRef(false)
  const closed = useRef<(() => void) | null>(null)
  const watchdog = useRef<ReturnType<typeof window.setTimeout> | null>(null)
  const queuedBundle = useRef<string | null>(null)
  const acceptRef = useRef<(path: string) => void>(() => {})
  const request = useCallback(async (op: string, params: Record<string, unknown> = {}, planId?: string) => {
    if (locked.current || closing.current) return
    locked.current = true; setBusy(true); setPlan(null); setMessage('正在检查…')
    setActiveRequest({ op, applying: Boolean(planId) }); setRetryRestore(false)
    operation.current = op; requestId.current = crypto.randomUUID()
    if (watchdog.current) window.clearTimeout(watchdog.current)
    watchdog.current = window.setTimeout(() => {
      if (!locked.current) return
      if (!planId && ['machine_detect', 'machine_history'].includes(op)) {
        requestId.current = ''; locked.current = false; setBusy(false)
        setMessage('本机检测暂未响应。可以重新检测；若仍无响应，请关闭客户端后重新打开。')
      } else {
        setMessage('操作仍在进行，尚未收到完成结果。请等待；关闭窗口时会等待写入安全结束。')
      }
    }, 15000)
    try {
      if (!child.current) {
        if (!spawning.current) {
          const command = Command.sidecar('binaries/ai-config-rpc')
          command.stdout.on('data', (chunk) => {
            // The shell plugin delivers a complete line, with or without its delimiter.
            for (const line of chunk.split(/\r?\n/)) {
              if (!line.trim()) continue
              try {
                const event = JSON.parse(line) as Reply
                if (event.request_id !== requestId.current) continue
                if (event.type === 'progress') { setMessage(stages[event.stage ?? ''] ?? '正在处理…'); continue }
                if (event.type !== 'result') continue
                if (watchdog.current) window.clearTimeout(watchdog.current)
                locked.current = false; setBusy(false)
                if (event.status === 'failed' || event.status === 'cancelled') {
                  if (operation.current === 'machine_restore') setRetryRestore(true)
                  setPlan(null); setMessage(errors[event.error?.code ?? ''] ?? `${event.error?.code ?? '已取消'}：${event.error?.message ?? '操作已取消'}`)
                } else {
                  const data = event.result ?? {}
                  if (operation.current === 'machine_detect') {
                    setAgents(data.agents ?? []); setSelected((data.agents ?? []).filter(a => a.installed).map(a => a.id))
                    setProjects(uniquePaths(Array.isArray(data.projects) ? data.projects : []))
                    setProjectLabels(data.project_labels ?? {})
                    if (data.groups) { setContentGroups(data.groups); setBackupGroups(data.groups.filter(g => g.default && g.available).map(g => g.id)) }
                    setMessage('已识别本机助手。选择备份内容与保存位置。')
                  } else if (operation.current === 'machine_history') {
                    setHistory(data.operations ?? []); setMessage('选择一次恢复记录，检查后撤销。')
                  } else {
                    setReport(data); setApplied(event.status === 'applied')
                    setPlan(event.can_apply ? event.plan_id ?? null : null)
                    if (operation.current === 'machine_restore') setRetryRestore(Boolean(data.running?.length))
                    setMessage(event.status === 'applied' ? operation.current === 'machine_backup' ? '备份已生成，请自行复制到新电脑。' : operation.current === 'machine_undo' ? '已撤销选中的恢复。' : restoreCompletion(data.verification) : data.running?.length ? '请关闭正在运行的助手，然后重试。' : data.pending_conflicts ? '请选择已有配置的处理方式，选完后可直接确认恢复。' : '检查完成，确认后才会写入。')
                  }
                }
                if (queuedBundle.current) { const path = queuedBundle.current; queuedBundle.current = null; acceptRef.current(path) }
              } catch { if (watchdog.current) window.clearTimeout(watchdog.current); locked.current = false; setBusy(false); setPlan(null); setRetryRestore(true); setMessage('无法读取本机响应，请重试。') }
            }
          })
          command.on('error', error => { if (watchdog.current) window.clearTimeout(watchdog.current); locked.current = false; setBusy(false); setPlan(null); setRetryRestore(true); setMessage(`本机程序异常：${error}`) })
          command.on('close', () => {
            if (watchdog.current) window.clearTimeout(watchdog.current)
            child.current = null; spawning.current = null; locked.current = false; setBusy(false); setPlan(null)
            setRetryRestore(true)
            if (closing.current) closed.current?.()
            else setMessage('本机程序已退出，请重新检查。')
          })
          spawning.current = command.spawn()
        }
        child.current = await spawning.current
      }
      await child.current.write(JSON.stringify(planId ? { protocol_version: 1, request_id: requestId.current, type: 'apply', plan_id: planId } : { protocol_version: 1, request_id: requestId.current, type: 'preview', operation: op, params }) + '\n')
    } catch (error) {
      if (watchdog.current) window.clearTimeout(watchdog.current)
      locked.current = false; setBusy(false); setPlan(null); spawning.current = null
      setRetryRestore(true)
      setMessage(`无法启动本机程序：${String(error)}`)
    }
  }, [])
  const reset = useCallback(() => { setPlan(null); setReport(null); setApplied(false); setRestoreDirty(false); setRetryRestore(false) }, [])
  const acceptBundle = useCallback((path: string) => {
    if (locked.current) { queuedBundle.current = path; return }
    reset(); setPage('restore'); setBundle(path); setMaps([]); setRestoreAgents(null); setRestoreGroups(null)
    setSecurity(false); setTrust(false); setWorkbuddy(false); setConflictChoices({})
    setMessage('已选择备份文件，点击“检查备份与本机差异”。')
  }, [reset])
  useEffect(() => { acceptRef.current = acceptBundle }, [acceptBundle])
  useEffect(() => {
    const startup = window.setTimeout(() => { void request('machine_detect') }, 0)
    const disposers: Array<() => void> = []; let disposed = false
    const register = (fn: () => void) => { if (disposed) fn(); else disposers.push(fn) }
    const take = async () => { const path = await invoke<string | null>('take_open_package'); if (path) acceptRef.current(path) }
    void take().catch(() => {})
    void listen('package-opened', () => { void take() }).then(register).catch(() => {})
    void getCurrentWindow().onDragDropEvent(event => {
      if (event.payload.type === 'drop') {
        const path = event.payload.paths.find(p => p.toLowerCase().endsWith('.zip'))
        if (path) acceptRef.current(path)
      }
    }).then(register).catch(() => {})
    void getCurrentWindow().onCloseRequested(async event => {
      if (!child.current && !spawning.current) return
      event.preventDefault(); closing.current = true; setMessage('正在等待操作安全结束…')
      try {
        const active = child.current ?? await spawning.current
        if (active) {
          const exit = new Promise<void>(resolve => { closed.current = resolve })
          await active.write(JSON.stringify({ protocol_version: 1, type: 'shutdown', request_id: crypto.randomUUID() }) + '\n'); await exit
        }
        await getCurrentWindow().destroy()
      } catch { closing.current = false; setMessage('关闭失败，请等待当前操作完成后重试。') }
    }).then(register).catch(() => {})
    return () => { window.clearTimeout(startup); disposed = true; disposers.forEach(fn => fn()) }
  }, [request])
  // Option changes refresh a read-only plan automatically; only Confirm can write.
  useEffect(() => {
    if (!restoreDirty || busy || page !== 'restore' || !bundle || restoreAgents?.length === 0 || restoreGroups?.length === 0) return
    const timer = window.setTimeout(() => {
      setRestoreDirty(false)
      void request('machine_restore', { bundle, ...(restoreAgents ? { agents: restoreAgents } : {}), ...(restoreGroups ? { groups: restoreGroups } : {}), root_map: maps, confirm_security: security, confirm_trust: trust, workbuddy_files: workbuddy, conflict_choices: conflictChoices })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [restoreDirty, busy, page, bundle, restoreAgents, restoreGroups, maps, security, trust, workbuddy, conflictChoices, request])
  async function folder(): Promise<string | null> { const value = await open({ directory: true, multiple: false }); return typeof value === 'string' ? value : null }
  function navigate(next: Page) { reset(); setPage(next); setMessage(next === 'restore' ? '选择备份 ZIP，检查后恢复。' : '选择助手与工作文件夹，开始备份。'); if (next === 'history') void request('machine_history') }
  function invalidateRestore() {
    setPlan(null); setApplied(false); setConflictChoices({})
    setReport(current => current ? { ...current, conflicts: [], skipped: [], writes: undefined, pending_conflicts: undefined, verification: undefined, backup: undefined, todo: undefined, report_dir: undefined } : null)
    setRestoreDirty(true); setRetryRestore(false); setMessage('正在更新恢复计划…')
  }
  function chooseConflicts(ids: string[], value: 'overwrite' | 'keep') {
    setPlan(null); setApplied(false)
    setConflictChoices(current => ({ ...current, ...Object.fromEntries(ids.map(id => [id, value])) }))
    setRestoreDirty(true); setRetryRestore(false); setMessage('正在更新恢复计划…')
  }
  const sourceFolders = [...new Map((report?.source_projects ?? []).map(v => [v.mapping_source ?? v.path,v])).values()]
  const trustPaths = uniquePaths((report?.trust_list ?? []).map(v => v.path))
  const restoreUpdating = restoreDirty && restoreAgents?.length !== 0 && restoreGroups?.length !== 0 || busy && activeRequest?.op === 'machine_restore' && !activeRequest.applying
  const verificationFailed = (report?.verification?.counts?.FAIL ?? 0) > 0

  return <div className="client-layout"><aside className="sidebar"><div className="brand-row"><span className="brand-mark"><UiIcon name="archive" /></span><div className="brand-copy"><strong>AI Config</strong><span>离线备份与恢复</span></div></div>
    <p className="nav-caption">换机迁移</p><nav aria-label="主导航">{navigation.map(item => <button key={item.page} className={`nav-item ${page === item.page ? 'selected' : ''}`} aria-current={page === item.page ? 'page' : undefined} disabled={busy} onClick={() => navigate(item.page)}><UiIcon name={item.page} /><span><strong>{item.label}</strong><small>{item.description}</small></span></button>)}</nav>
    <div className="sidebar-foot"><span className="local-badge"><i />本地处理</span><small>备份保存在你选择的位置。<br />换机时自行复制备份文件。</small></div></aside>
    <main className="content-area"><header className="page-header"><div><h1>{page === 'backup' ? '备份 AI 助手' : page === 'restore' ? '在这台电脑恢复' : '恢复记录'}</h1><p className="subtitle">{page === 'backup' ? '把熟悉的规则、记忆与技能，带到下一台电脑。' : page === 'restore' ? '先安装并启动助手一次，再关闭助手。选择自己的备份，检查后恢复。' : '查看本机恢复记录，必要时撤销一次恢复。'}</p></div>{page === 'backup' && <button className="subtle-button" disabled={busy} onClick={() => void request('machine_detect')}><UiIcon name="refresh" />重新检测助手</button>}</header>
    <fieldset disabled={busy} className="machine-form">
    {page === 'backup' && <div className="backup-layout"><section className="panel backup-selection">
      <section className="form-section"><div className="section-heading"><h2><span className="step-number">1</span>选择助手</h2><span className="selection-count">已选 {selected.length} 个</span></div><p className="section-description">选择要带走配置的 AI 助手。</p><div className="agent-grid">{agents.map(a => <label key={a.id} className={`machine-choice agent-choice ${selected.includes(a.id) ? 'is-selected' : ''} ${!a.installed ? 'is-unavailable' : ''}`}><input type="checkbox" checked={selected.includes(a.id)} disabled={!a.installed} onChange={e => { reset(); setSelected(e.target.checked ? [...selected, a.id] : selected.filter(v => v !== a.id)) }} /><span className={`agent-monogram agent-${a.id}`} aria-hidden="true">{a.id === 'codex' ? '>_' : a.name.slice(0, 1)}</span><span className="choice-copy"><strong>{a.name}</strong><small>{a.installed ? '已在本机找到' : '尚未找到'}</small></span></label>)}</div>{!agents.length && <p className="empty-inline">{busy ? '正在检测本机助手…' : '暂无检测结果，请重新检测助手。'}</p>}</section>
      <section className="form-section"><div className="section-heading"><h2><span className="step-number">2</span>选择备份内容</h2><span className="selection-count">已选 {backupGroups.length} 类</span></div><p className="section-description">项目源码和登录凭据需单独准备。</p><div className="content-grid">{contentGroups.map(g => <label key={g.id} className={`machine-choice content-choice ${backupGroups.includes(g.id) ? 'is-selected' : ''} ${!g.available ? 'is-unavailable' : ''}`}><input type="checkbox" checked={backupGroups.includes(g.id)} disabled={!g.available} onChange={e => { reset(); setBackupGroups(e.target.checked ? [...backupGroups, g.id] : backupGroups.filter(id => id !== g.id)) }} /><span className="choice-copy"><strong>{g.name}{!g.available && '（尚未找到）'}</strong><small>{groupDescriptions[g.id]}</small></span></label>)}</div></section>
    </section><section className="panel backup-destination">
      <section className="form-section"><div className="section-heading"><h2><span className="step-number">3</span>工作文件夹</h2><span className="selection-count">{projects.length} 个</span></div><p className="section-description">迁移项目记忆和权限配置。<br />项目源码需单独准备。</p><div className="project-list">{projects.map(p => <div key={p} className="machine-row project-row"><UiIcon name="folder" /><code>{projectLabels[p] ?? p}</code><button className="text-button" aria-label={`移除 ${projectLabels[p] ?? p}`} onClick={() => { reset(); setProjects(projects.filter(v => v !== p)) }}>移除</button></div>)}</div>{!projects.length && <p className="empty-inline">未添加工作文件夹，仅备份全局内容。</p>}
      <button className="subtle-button add-folder-button" onClick={async () => { const p = await folder(); if (p) { reset(); setProjects(v => [...new Set([...v, p])]) } }}><UiIcon name="folder" />添加工作文件夹</button></section>
      <section className="form-section"><h2><span className="step-number">4</span>保存位置</h2><p className="section-description">选择用于存放备份 ZIP 的文件夹。</p><div className={`destination-box ${destination ? 'has-destination' : ''}`}><UiIcon name="folder" /><span>{destination || '尚未选择保存位置'}</span></div><button className="subtle-button destination-button" onClick={async () => { const p = await folder(); if (p) { reset(); setDestination(p) } }}>选择文件夹</button></section>
      <div className="backup-action"><button className="primary-button" disabled={!destination || !selected.length || !backupGroups.length} onClick={() => void request('machine_backup', { destination, agents: selected, projects, groups: backupGroups, flagged_policy: flaggedPolicy })} aria-busy={busy && activeRequest?.op === 'machine_backup' && !activeRequest.applying}><UiIcon name="backup" />{busy && activeRequest?.op === 'machine_backup' && !activeRequest.applying ? '正在检查备份内容…' : '检查备份内容'}</button><p>先检查，再确认生成备份。</p></div>
    </section></div>}
    {page === 'restore' && <section className="panel restore-panel"><h2><span className="step-number">1</span>选择备份 ZIP</h2><div className={`bundle-picker ${bundle ? 'has-bundle' : ''}`}><span className="bundle-icon"><UiIcon name="archive" /></span><div><strong>{bundle ? folderName(bundle) : '把备份带到这台电脑'}</strong><p><code>{bundle || '也可以将备份 ZIP 拖入窗口'}</code></p></div><button className="subtle-button" onClick={async () => { const p = await open({ multiple: false, filters: [{ name: 'AI 备份', extensions: ['zip'] }] }); if (typeof p === 'string') acceptBundle(p) }}>选择备份</button></div>
      {report?.bundle_agents && <><h2>2. 选择要恢复的助手</h2>{report.bundle_agents.map(id => <label className="machine-choice" key={id}><input type="checkbox" checked={(restoreAgents ?? report.bundle_agents ?? []).includes(id)} onChange={e => { const current = restoreAgents ?? report.bundle_agents ?? []; invalidateRestore(); setRestoreAgents(e.target.checked ? [...current, id] : current.filter(v => v !== id)); if (!e.target.checked && current.length === 1) setMessage('请至少选择一个要恢复的助手。') }} />{labels[id]}</label>)}</>}
      {report?.bundle_groups && <><h2>选择恢复内容</h2>{report.bundle_groups.map(id => <label className="machine-choice" key={id}><input type="checkbox" checked={(restoreGroups ?? report.bundle_groups?.filter(g => g !== 'history') ?? []).includes(id)} onChange={e => { const current = restoreGroups ?? report.bundle_groups?.filter(g => g !== 'history') ?? []; invalidateRestore(); setRestoreGroups(e.target.checked ? [...current, id] : current.filter(g => g !== id)); if (!e.target.checked && current.length === 1) setMessage('请至少选择一种恢复内容。') }} />{groupNames[id]}{id === 'history' && <small>不保证可继续对话。</small>}</label>)}</>}
      {!!sourceFolders.length && <details className="restore-folders"><summary>工作文件夹恢复位置（{sourceFolders.length} 个）</summary><p>用于恢复项目记忆和权限。项目源码需先单独复制；路径相同时无需修改。</p>{sourceFolders.map(project => {
        const path = project.path; const mappingSource = project.mapping_source ?? path
        const target = maps.find(m => m.from === mappingSource)?.to || (report?.projects as Record<string, string | null>)?.[project.id]
        return <div className="restore-folder" key={mappingSource}><strong>{folderName(path)}</strong><dl><dt>备份中的位置</dt><dd><code>{path}</code></dd><dt>本机恢复位置</dt><dd>{target ? <code>{target}</code> : '未找到，暂不恢复这个项目'}</dd></dl><button className="subtle-button" onClick={async () => { const target = await folder(); if (target) { invalidateRestore(); setMaps(v => [...v.filter(m => m.from !== mappingSource), { from: mappingSource, to: target }]) } }}>更改本机位置</button></div>
      })}</details>}
      {!!report?.security_list?.length && <details open><summary>模型与安全设置（默认跳过）</summary>{report.security_list.map((v, i) => <p key={i}>{labels[v.agent]} · {v.project ? `工作文件夹：${v.project}` : v.instance === 'desktop' ? '桌面设置' : '全局设置'} · {v.field}：<code>{JSON.stringify(v.value)}</code></p>)}<label className="machine-choice"><input type="checkbox" checked={security} onChange={e => { invalidateRestore(); setSecurity(e.target.checked) }} />恢复上列设置</label></details>}
      {!!trustPaths.length && <section className="restore-trust"><h3>Codex 项目信任</h3><p>默认不恢复信任。启用后助手可以加载这些文件夹的项目配置与运行钩子。</p><details><summary>查看需要信任的文件夹（{trustPaths.length} 个）</summary><ul>{trustPaths.map(path => <li key={path}><strong>{folderName(path)}</strong><br /><span>需要信任的文件夹：<code>{path}</code></span></li>)}</ul></details><label className="machine-choice"><input type="checkbox" checked={trust} onChange={e => { invalidateRestore(); setTrust(e.target.checked) }} />恢复这些文件夹的 Codex 信任</label></section>}
      {report?.bundle_agents?.some(id => id.startsWith('workbuddy')) && <label className="machine-choice"><input type="checkbox" checked={workbuddy} onChange={e => { invalidateRestore(); setWorkbuddy(e.target.checked) }} />复制 WorkBuddy 人设、记忆和技能文本（需人工核验加载）</label>}
      {!applied && (!report?.bundle_agents || retryRestore) && <button className="primary-button" disabled={!bundle || restoreAgents?.length === 0 || restoreGroups?.length === 0 || busy || restoreDirty} aria-busy={busy && activeRequest?.op === 'machine_restore' && !activeRequest.applying} onClick={() => { setRestoreDirty(false); void request('machine_restore', { bundle, ...(restoreAgents ? { agents: restoreAgents } : {}), ...(restoreGroups ? { groups: restoreGroups } : {}), root_map: maps, confirm_security: security, confirm_trust: trust, workbuddy_files: workbuddy, conflict_choices: conflictChoices }) }}>{busy && activeRequest?.op === 'machine_restore' && !activeRequest.applying ? '正在检查差异…' : retryRestore ? '重试检查' : '检查备份与本机差异'}</button>}</section>}

    {page === 'history' && <section className="panel history-panel"><div className="section-heading"><h2>本机恢复记录</h2><button className="subtle-button" onClick={() => { reset(); void request('machine_history') }}><UiIcon name="refresh" />刷新记录</button></div><p className="section-description">撤销前会检查后续修改，保留现场与原有备份。</p>{!history.length && <div className="empty-state"><span className="empty-state-icon"><UiIcon name="history" /></span><h3>{busy ? '正在读取恢复记录…' : '暂无可撤销的恢复'}</h3><p>完成一次恢复后，可在这里查看记录并检查撤销。</p></div>}{history.map(h => <div className="machine-row history-row" key={h.operation_id}><UiIcon name="history" /><div><strong>{new Date(h.created_at).toLocaleString()}</strong><span>{h.change_count ?? h.changes?.length ?? 0} 个文件</span></div><button className="subtle-button" onClick={() => void request('machine_undo', { operation_id: h.operation_id })}>检查撤销</button></div>)}</section>}
    </fieldset>
    <section className={`panel result-panel ${verificationFailed ? 'is-attention' : applied ? 'is-complete' : ''}`} aria-live="polite"><div className="section-heading"><h2>{applied ? '操作结果' : report ? '检查结果' : '检查与结果'}</h2><UiIcon name={applied && !verificationFailed ? 'check' : 'shield'} /></div><p className={`status-message ${busy ? 'is-busy' : ''}`} role="status"><span className="status-indicator" aria-hidden="true" />{message}</p>{report && <div className="report-content">
      {report.entries !== undefined && <p>备份条目：{report.entries}；排除：{report.exclusions?.length ?? 0}；工作文件夹：{typeof report.projects === 'number' ? report.projects : 0}。</p>}
      {report.destination && <p>备份位置：<code>{report.destination}</code></p>}{report.sha256 && <details><summary>完整性校验</summary><code>SHA-256：{report.sha256}</code></details>}
      {report.by_group && <ul className="report-group-list">{Object.entries(report.by_group).map(([id, count]) => <li key={id}><span>{groupNames[id] ?? id}</span><strong>{count.files} 个文件 <small>{(count.bytes / 1024).toFixed(1)} KB</small></strong></li>)}</ul>}
        {page === 'backup' && report.coverage && !report.coverage.complete && <p>部分目录未完成扫描，请核对未携带清单后再确认备份。</p>}
        {!!report.exclusions?.length && <details><summary>未携带内容 {report.exclusions.length} 项</summary><ul>{report.exclusions.slice(0, 20).map((item, index) => <li key={index}><code>{item.logical_path}</code> · {backupExclusions[item.reason] ?? '请核对排除报告'}</li>)}</ul>{report.exclusions.length > 20 && <p>仅显示前 20 项，完整清单见备份摘要。</p>}</details>}
        {report.history && <section><h3>历史记录</h3><p>{report.history.files} 个文件，{(report.history.bytes / 1024 / 1024).toFixed(1)} MB，分为 {report.history.parts} 个独立备份包。</p><p>请将这些分包与主备份放在同一文件夹，一起保存和复制。恢复只新增或另存，不保证可继续对话。</p>{report.history.packages.length > 0 && <details><summary>查看分包文件名</summary><ul>{report.history.packages.map(part => <li key={part.name}><code>{part.name}</code></li>)}</ul></details>}{report.history.exclusions.length > 0 && <details><summary>未携带历史文件 {report.history.exclusions.length} 项</summary><ul>{report.history.exclusions.slice(0, 20).map((item, index) => <li key={index}><code>{labels[item.agent] ?? item.agent}/{item.relative}</code> · {historyExclusions[item.reason] ?? '未携带，请核对历史报告'}</li>)}</ul>{report.history.exclusions.length > 20 && <p>仅显示前 20 项，完整清单见历史报告。</p>}</details>}</section>}
      {page === 'backup' && report.flagged && report.flagged.count > 0 && <section><h3>含密钥的文件 {report.flagged.count} 个</h3><p>{report.flagged.policy === 'skip' ? '已按选择整份跳过这些文件。' : '已把需要隐藏的密钥部分替换为占位符后保存；有来源的示例赋值只提醒。'}</p>{!applied && <div className="machine-actions">{(['redact', 'skip'] as const).map(policy => <label className="machine-choice" key={policy}><input type="radio" name="flagged-policy" disabled={busy} checked={flaggedPolicy === policy} onChange={() => { setFlaggedPolicy(policy); setApplied(false); void request('machine_backup', { destination, agents: selected, projects, groups: backupGroups, flagged_policy: policy }) }} />{policy === 'redact' ? '隐藏密钥后保留文件' : '整份跳过含密钥的文件'}</label>)}</div>}<details><summary>查看文件与行号</summary><ul>{report.flagged.items.map(item => <li key={item.id}><code>{item.logical_path}</code> · {item.lines.length ? `第 ${item.lines.join('、')} 行` : '行号未列出'}{item.lines_truncated && `（仅列部分行号；本次已发现 ${item.line_count ?? item.lines.length} 行命中）`}</li>)}</ul></details></section>}
      {report.skills && <section><p>发现第三方技能 {report.skills.third_party} 个；来源不明 {report.skills.unknown_source} 个，请核对来源报告中的携带情况。</p>{report.skills.diverged_copies > 0 && <p>同名技能 {report.skills.diverged_copies} 组内容不同，各份按选择分别处理。</p>}{!!report.skills.unverified_copies && <p>同名技能 {report.skills.unverified_copies} 组尚未读取比较，请核对来源报告。</p>}</section>}
      {report.coverage && report.coverage.unclassified > 0 && <details><summary>未定性文件 {report.coverage.unclassified} 个，未备份</summary><p>最多显示 20 项；完整统计见备份内的覆盖报告。</p><ul>{report.coverage.samples?.map(path => <li key={path}><code>{path}</code></li>)}</ul></details>}
      {!!report.redacted_todo && <p>需要重新填写密钥的文件：{report.redacted_todo} 个。</p>}{!!report.needs_rebuild && <p>有文件未携带的技能：{report.needs_rebuild} 项，请按来源报告核对缺少的内容。</p>}
      {!!report.exports?.length && <details><summary>导出到报告文件夹的内容</summary>{report.exports.map(item => <p key={item.target}><code>{item.target}</code>，请自行核对并导入。</p>)}</details>}
      {report.writes !== undefined && <p>{applied ? '本次写入' : '计划写入'} {report.writes} 个文件{report.conflicts?.length ? `；${new Set(report.conflicts.map(v => v.target)).size} 个文件存在差异` : ''}{report.pending_conflicts ? `；${report.pending_conflicts} 处差异待选择` : ''}。</p>}
      {!!report.running?.length && <p>请关闭：{report.running.join('、')}</p>}
      {!!report.conflicts?.length && (applied ? <details><summary>已有配置：{new Set(report.conflicts.filter(v => v.decision === 'overwrite').map(v => v.target)).size} 个文件已覆盖；{new Set(report.conflicts.filter(v => v.decision === 'keep').map(v => v.target)).size} 个文件已保留</summary><ConflictPanel conflicts={report.conflicts} choices={conflictChoices} applied disabled={busy} onChoose={chooseConflicts} /></details> : <ConflictPanel conflicts={report.conflicts} choices={conflictChoices} applied={false} disabled={busy} onChoose={chooseConflicts} />)}
      {!!report.skipped?.length && <SkippedPanel items={report.skipped} />}
      {applied && report.backup && <p>本机原文件已备份到：<code>{report.backup}</code>。可在“恢复记录”中撤销本次恢复。</p>}
      {!!report.warnings?.length && <details open><summary>提醒</summary>{report.warnings.map((v, i) => <p key={i}>{typeof v === 'string' ? v : v.message}</p>)}</details>}
      {report.paths && <details open><summary>将撤销这些文件</summary>{report.paths.map(p => <p key={p}><code>{p}</code></p>)}</details>}
      {report.verification && <VerificationPanel report={report.verification} />}
      {report.todo && <NextSteps text={report.todo} />}
      {report.report_dir && <p>核验报告已保存在：<code>{report.report_dir}</code></p>}
    </div>}{page === 'restore' && report?.bundle_agents && !applied ? <button className="primary-button" disabled={busy || restoreDirty || !plan || restoreAgents?.length === 0 || restoreGroups?.length === 0} aria-busy={Boolean(restoreUpdating || busy && activeRequest?.applying)} onClick={() => { if (plan) void request('machine_restore', {}, plan) }}>{busy && activeRequest?.applying ? '正在恢复…' : restoreUpdating ? '正在更新恢复计划…' : '确认恢复'}</button> : plan && <button className="primary-button" disabled={busy} aria-busy={busy && activeRequest?.applying} onClick={() => void request(operation.current, {}, plan)}>确认{page === 'backup' ? '生成备份' : '撤销'}</button>}</section>
    </main></div>
}
