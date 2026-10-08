import { useCallback, useEffect, useRef, useState } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { open } from '@tauri-apps/plugin-dialog'
import { Command, type Child } from '@tauri-apps/plugin-shell'
import './App.css'
import './Machine.css'

type Page = 'backup' | 'restore' | 'history'
type Agent = { id: string; name: string; installed: boolean; root: string }
type Mapping = { from: string; to: string }
type Report = {
  agents?: Agent[]; projects?: number | string[] | Record<string, string | null>; entries?: number
  destination?: string; bytes?: number; sha256?: string; writes?: number
  exclusions?: Array<{ logical_path: string; reason: string }>
  warnings?: Array<{ message: string }> | string[]; running?: string[]
  source_projects?: Array<{ id: string; path: string }>; bundle_agents?: string[]
  security_list?: Array<{ agent: string; field: string; value: unknown }>
  trust_list?: Array<{ path: string }>
  conflicts?: Array<{ target: string; saved_as?: string; reason: string }>
  skipped?: Array<{ target?: string; reason: string }>
  operations?: Array<{ operation_id: string; created_at: string; change_count?: number; changes?: Array<{ path: string }> }>
  paths?: string[]; todo?: string; report_dir?: string
  verification?: { checks: Array<{ label: string; status: string; target?: string }>; questions: Array<{ agent: string; prompt: string; expected: string }> }
}
type Reply = { type: string; request_id?: string; stage?: string; status?: string; can_apply?: boolean; plan_id?: string; result?: Report; error?: { code: string; message: string } }
const labels: Record<string, string> = { claude: 'Claude', codex: 'Codex', workbuddy: 'WorkBuddy', 'workbuddy-ai': 'WorkBuddy AI' }
const stages: Record<string, string> = { started: '开始检查…', planning: '正在检查内容…', rechecking_preview: '重新检查文件是否变化…', applying: '正在写入并核验…' }
const errors: Record<string, string> = { E_PLAN_STALE: '文件或选项在检查后发生变化，请重新检查后确认。', E_PLAN_UNKNOWN: '检查结果已过期或已使用，请重新检查。' }

export default function MachineApp() {
  const [page, setPage] = useState<Page>('backup')
  const [agents, setAgents] = useState<Agent[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [restoreAgents, setRestoreAgents] = useState<string[] | null>(null)
  const [projects, setProjects] = useState<string[]>([])
  const [destination, setDestination] = useState('')
  const [bundle, setBundle] = useState('')
  const [maps, setMaps] = useState<Mapping[]>([])
  const [security, setSecurity] = useState(false)
  const [trust, setTrust] = useState(false)
  const [workbuddy, setWorkbuddy] = useState(false)
  const [report, setReport] = useState<Report | null>(null)
  const [history, setHistory] = useState<NonNullable<Report['operations']>>([])
  const [plan, setPlan] = useState<string | null>(null)
  const [message, setMessage] = useState('选择助手与工作文件夹，开始备份。')
  const [busy, setBusy] = useState(false)
  const [applied, setApplied] = useState(false)
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
                  setPlan(null); setMessage(errors[event.error?.code ?? ''] ?? `${event.error?.code ?? '已取消'}：${event.error?.message ?? '操作已取消'}`)
                } else {
                  const data = event.result ?? {}
                  if (operation.current === 'machine_detect') {
                    setAgents(data.agents ?? []); setSelected((data.agents ?? []).filter(a => a.installed).map(a => a.id))
                    setProjects(Array.isArray(data.projects) ? data.projects : [])
                    setMessage('已识别本机助手。选择备份内容与保存位置。')
                  } else if (operation.current === 'machine_history') {
                    setHistory(data.operations ?? []); setMessage('选择一次恢复记录，检查后撤销。')
                  } else {
                    setReport(data); setApplied(event.status === 'applied')
                    setPlan(event.can_apply ? event.plan_id ?? null : null)
                    setMessage(event.status === 'applied' ? operation.current === 'machine_backup' ? '备份已生成，请自行复制到新电脑。' : operation.current === 'machine_undo' ? '已撤销选中的恢复。' : '恢复已完成，请检查核验结果和手动事项。' : data.running?.length ? '请关闭正在运行的助手，再重新检查。' : '检查完成，确认后才会写入。')
                  }
                }
                if (queuedBundle.current) { const path = queuedBundle.current; queuedBundle.current = null; acceptRef.current(path) }
              } catch { if (watchdog.current) window.clearTimeout(watchdog.current); locked.current = false; setBusy(false); setPlan(null); setMessage('无法读取本机响应，请重启客户端。') }
            }
          })
          command.on('error', error => { if (watchdog.current) window.clearTimeout(watchdog.current); locked.current = false; setBusy(false); setPlan(null); setMessage(`本机程序异常：${error}`) })
          command.on('close', () => {
            if (watchdog.current) window.clearTimeout(watchdog.current)
            child.current = null; spawning.current = null; locked.current = false; setBusy(false); setPlan(null)
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
      setMessage(`无法启动本机程序：${String(error)}`)
    }
  }, [])
  const reset = useCallback(() => { setPlan(null); setReport(null); setApplied(false) }, [])
  const acceptBundle = useCallback((path: string) => {
    if (locked.current) { queuedBundle.current = path; return }
    reset(); setPage('restore'); setBundle(path); setMaps([]); setRestoreAgents(null)
    setSecurity(false); setTrust(false); setWorkbuddy(false)
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
  async function folder(): Promise<string | null> { const value = await open({ directory: true, multiple: false }); return typeof value === 'string' ? value : null }
  function navigate(next: Page) { reset(); setPage(next); if (next === 'history') void request('machine_history') }

  return <div className="client-layout"><aside className="sidebar"><div className="brand-copy"><strong>AI Config</strong><span>离线备份与恢复</span></div>
    <p className="nav-caption">换机迁移</p><nav>{(['backup', 'restore', 'history'] as Page[]).map(p => <button key={p} className={`nav-item ${page === p ? 'selected' : ''}`} disabled={busy} onClick={() => navigate(p)}>{p === 'backup' ? '备份' : p === 'restore' ? '恢复' : '恢复记录'}</button>)}</nav>
    <div className="sidebar-foot"><span className="local-badge"><i />本地处理</span><small>备份保存在你选择的位置。</small></div></aside>
    <main className="content-area"><header className="page-header"><h1>{page === 'backup' ? '备份 AI 助手' : page === 'restore' ? '在这台电脑恢复' : '恢复记录'}</h1>{page === 'backup' && <button className="subtle-button" disabled={busy} onClick={() => void request('machine_detect')}>重新检测助手</button>}</header>
    <p className="subtitle">{page === 'backup' ? '保存规则、支持的设置、记忆与自建技能。项目源码和登录凭据需单独准备。' : page === 'restore' ? '先安装并启动助手一次，再关闭助手。选择自己的备份，检查后恢复。' : '撤销会检查文件是否有后续修改；保留现场与原有备份。'}</p>
    <fieldset disabled={busy} className="machine-form">
    {page === 'backup' && <section className="panel"><h2>1. 选择助手</h2>{agents.map(a => <label key={a.id} className="machine-choice"><input type="checkbox" checked={selected.includes(a.id)} disabled={!a.installed} onChange={e => { reset(); setSelected(e.target.checked ? [...selected, a.id] : selected.filter(v => v !== a.id)) }} />{a.name}{!a.installed && '（尚未找到）'}</label>)}
      <h2>2. 工作文件夹</h2><p>选择要迁移记忆和权限配置的项目。源码不会进入此备份。</p>{projects.map(p => <div key={p} className="machine-row"><code>{p}</code><button className="subtle-button" onClick={() => { reset(); setProjects(projects.filter(v => v !== p)) }}>移除</button></div>)}
      <button className="subtle-button" onClick={async () => { const p = await folder(); if (p) { reset(); setProjects(v => [...new Set([...v, p])]) } }}>添加工作文件夹</button>
      <h2>3. 保存位置</h2><div className="machine-row"><span>{destination || '尚未选择'}</span><button className="subtle-button" onClick={async () => { const p = await folder(); if (p) { reset(); setDestination(p) } }}>选择文件夹</button></div>
      <button className="primary-button" disabled={!destination || !selected.length} onClick={() => void request('machine_backup', { destination, agents: selected, projects })}>检查备份内容</button></section>}
    {page === 'restore' && <section className="panel"><h2>1. 选择备份 ZIP</h2><div className="machine-row"><code>{bundle || '也可以将备份 ZIP 拖入窗口'}</code><button className="subtle-button" onClick={async () => { const p = await open({ multiple: false, filters: [{ name: 'AI 备份', extensions: ['zip'] }] }); if (typeof p === 'string') acceptBundle(p) }}>选择备份</button></div>
      {report?.bundle_agents && <><h2>2. 选择要恢复的助手</h2>{report.bundle_agents.map(id => <label className="machine-choice" key={id}><input type="checkbox" checked={(restoreAgents ?? report.bundle_agents ?? []).includes(id)} onChange={e => { setPlan(null); const current = restoreAgents ?? report.bundle_agents ?? []; setRestoreAgents(e.target.checked ? [...current, id] : current.filter(v => v !== id)) }} />{labels[id]}</label>)}</>}
      {!!report?.source_projects?.length && <><h2>工作文件夹映射</h2><p>为路径不同的项目选择新目录；项目文件需先单独复制过来。</p>{report.source_projects.map(p => <div className="machine-row" key={p.id}><code>{p.path}<br />→ {maps.find(m => m.from === p.path)?.to || (report.projects as Record<string, string | null>)?.[p.id] || '未找到，可跳过'}</code><button className="subtle-button" onClick={async () => { const target = await folder(); if (target) { setPlan(null); setMaps(v => [...v.filter(m => m.from !== p.path), { from: p.path, to: target }]) } }}>选择新目录</button></div>)}</>}
      {!!report?.security_list?.length && <details open><summary>模型与安全设置（默认跳过）</summary>{report.security_list.map((v, i) => <p key={i}>{labels[v.agent]} · {v.field}：<code>{JSON.stringify(v.value)}</code></p>)}<label className="machine-choice"><input type="checkbox" checked={security} onChange={e => { setPlan(null); setSecurity(e.target.checked) }} />恢复上列设置</label></details>}
      {!!report?.trust_list?.length && <details open><summary>Codex 项目信任（默认跳过）</summary>{report.trust_list.map(v => <p key={v.path}><code>{v.path}</code></p>)}<p>信任后助手可以加载项目配置与运行钩子。</p><label className="machine-choice"><input type="checkbox" checked={trust} onChange={e => { setPlan(null); setTrust(e.target.checked) }} />信任上列工作文件夹</label></details>}
      {report?.bundle_agents?.some(id => id.startsWith('workbuddy')) && <label className="machine-choice"><input type="checkbox" checked={workbuddy} onChange={e => { setPlan(null); setWorkbuddy(e.target.checked) }} />复制 WorkBuddy 人设、记忆和技能文本（需人工核验加载）</label>}
      <button className="primary-button" disabled={!bundle || restoreAgents?.length === 0} onClick={() => void request('machine_restore', { bundle, ...(restoreAgents ? { agents: restoreAgents } : {}), root_map: maps, confirm_security: security, confirm_trust: trust, workbuddy_files: workbuddy })}>检查备份与本机差异</button></section>}
    {page === 'history' && <section className="panel"><button className="subtle-button" onClick={() => { reset(); void request('machine_history') }}>刷新记录</button>{!history.length && <p>暂无可撤销的恢复。</p>}{history.map(h => <div className="machine-row" key={h.operation_id}><span>{new Date(h.created_at).toLocaleString()} · {h.change_count ?? h.changes?.length ?? 0} 个文件</span><button className="subtle-button" onClick={() => void request('machine_undo', { operation_id: h.operation_id })}>检查撤销</button></div>)}</section>}
    </fieldset>
    <section className="panel" aria-live="polite"><p role="status">{busy && '◌ '}{message}</p>{report && <>
      {report.entries !== undefined && <p>备份条目：{report.entries}；排除：{report.exclusions?.length ?? 0}；工作文件夹：{typeof report.projects === 'number' ? report.projects : 0}。</p>}
      {report.destination && <p>备份位置：<code>{report.destination}</code></p>}{report.sha256 && <details><summary>完整性校验</summary><code>SHA-256：{report.sha256}</code></details>}
      {report.writes !== undefined && <p>{applied ? '本次写入' : '计划写入'} {report.writes} 个文件；冲突 {report.conflicts?.length ?? 0} 项；跳过 {report.skipped?.length ?? 0} 项。</p>}
      {!!report.running?.length && <p>请关闭：{report.running.join('、')}</p>}
      {!!report.conflicts?.length && <details open><summary>保留现有内容，备份版本另存</summary>{report.conflicts.map((v, i) => <p key={i}><code>{v.saved_as ?? v.target}</code> · {v.reason}</p>)}</details>}
      {!!report.skipped?.length && <details><summary>本次跳过的内容</summary>{report.skipped.map((v, i) => <p key={i}><code>{v.target}</code> · {v.reason}</p>)}</details>}
      {!!report.exclusions?.length && <details><summary>未纳入备份的内容</summary>{report.exclusions.map((v, i) => <p key={i}><code>{v.logical_path}</code> · {v.reason}</p>)}</details>}
      {!!report.warnings?.length && <details open><summary>提醒</summary>{report.warnings.map((v, i) => <p key={i}>{typeof v === 'string' ? v : v.message}</p>)}</details>}
      {report.paths && <details open><summary>将撤销这些文件</summary>{report.paths.map(p => <p key={p}><code>{p}</code></p>)}</details>}
      {report.verification && <><h2>恢复核验</h2>{report.verification.checks.map((v, i) => <p key={i}>{v.label}：{({ PASS: '一致', FAIL: '需要检查', MANUAL: '需要人工确认', SKIP: '未检查' } as Record<string, string>)[v.status] ?? v.status}</p>)}<h2>在助手新会话里确认</h2>{report.verification.questions.map((v, i) => <details key={i}><summary>{labels[v.agent]}：{v.prompt}</summary><p>对照原句：{v.expected}</p></details>)}</>}
      {report.todo && <pre className="machine-todo">{report.todo}</pre>}
      {report.report_dir && <p>核验报告已保存在：<code>{report.report_dir}</code></p>}
    </>}{plan && <button className="primary-button" disabled={busy} onClick={() => void request(operation.current, {}, plan)}>确认{page === 'backup' ? '生成备份' : page === 'restore' ? '恢复' : '撤销'}</button>}</section>
    </main></div>
}
