import { useEffect, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import type { FeatureReply } from './CloudPanel'
type Op = 'portable_restore' | 'portable_project' | 'git_transport' | 'import_config'
type Props = { busy: boolean; reply: FeatureReply | null; request: (op: Op, params: Record<string, unknown>, plan?: string) => void }
export default function LocalToolsPanel({ busy, reply, request }: Props) {
  const [project, setProject] = useState('')
  const [profile, setProfile] = useState('claude')
  const [records, setRecords] = useState<Array<{ handoff_id: string; commit?: string }>>([])
  const [handoff, setHandoff] = useState('')
  const [reference, setReference] = useState<Record<string, unknown> | null>(null)
  const [plan, setPlan] = useState<string>()
  const [operation, setOperation] = useState<Op>('portable_restore')
  const [notice, setNotice] = useState('旧设备配置、可移植 Claude 记忆、可选 Git 传输。先预览再确认；离线包不依赖 Git。')
  useEffect(() => {
    if (!reply?.operation || !['portable_restore', 'portable_project', 'git_transport', 'import_config'].includes(reply.operation)) return
    let active = true
    queueMicrotask(() => {
      if (!active) return
      setOperation(reply.operation as Op)
      setPlan(reply.status === 'preview' && reply.can_apply ? reply.plan_id : undefined)
      if (reply.operation === 'portable_project' && reply.result) {
        setReference(reply.result)
        if (Array.isArray(reply.result.handoffs)) setRecords(reply.result.handoffs as Array<{ handoff_id: string; commit?: string }>)
        setNotice(String(reply.result.note ?? '资料已读取'))
      } else setNotice(reply.error?.message ?? JSON.stringify(reply.result))
    })
    return () => { active = false }
  }, [reply])
  const resetReference = () => { setPlan(undefined); setReference(null); setRecords([]); setHandoff('') }
  return <section className="panel feature-panel"><h2>本机迁移与兼容传输</h2>
    <label className="package-field"><span>可移植资料的项目 ID</span><input disabled={busy} value={project} onChange={event => { setProject(event.target.value); resetReference() }} /></label>
    <label className="package-field"><span>资料来源 Agent</span><select disabled={busy} value={profile} onChange={event => { setProfile(event.target.value); resetReference() }}><option value="claude">Claude</option><option value="codex">Codex（记忆仅供参考）</option></select></label>
    <div className="setup-actions">
      <button className="subtle-button" disabled={busy || !project} type="button" onClick={() => request('portable_project', { project_id: project, profile })}>查看本机包中的项目资料</button>
      <button className="subtle-button" disabled={busy || !project || profile !== 'claude'} type="button" onClick={() => request('portable_restore', { project_id: project, profile })}>预览恢复可移植 Markdown</button>
      <button className="subtle-button" disabled={busy} type="button" onClick={async () => { const path = await open({ multiple: false, filters: [{ name: '旧设备配置', extensions: ['json'] }] }); if (typeof path === 'string') request('import_config', { source: path }) }}>预览迁入旧设备配置</button>
      <button className="subtle-button" disabled={busy} type="button" onClick={() => request('git_transport', { action: 'fetch' })}>预览 Git 获取</button>
      <button className="subtle-button" disabled={busy} type="button" onClick={() => request('git_transport', { action: 'publish' })}>预览 Git 发布</button>
      {plan && <button className="primary-button" disabled={busy} type="button" onClick={() => request(operation, {}, plan)}>确认执行本步骤</button>}
    </div>
    {records.length > 0 && <label className="package-field"><span>交接记录</span><select disabled={busy} value={handoff} onChange={event => { const value = event.target.value; setHandoff(value); if (value) request('portable_project', { project_id: project, profile, handoff_id: value }) }}><option value="">选择要查看的记录</option>{records.map(row => <option key={row.handoff_id} value={row.handoff_id}>{row.handoff_id} · {row.commit?.slice(0, 12) ?? '源码版本未知'}</option>)}</select></label>}
    {reference && <div className="setup-preview"><p>可移植记忆文件：{String(reference.memory_files ?? 0)}。接续条件尚未全部核验。</p>{Array.isArray(reference.missing) && <ul>{(reference.missing as string[]).map(item => <li key={item}>{item}</li>)}</ul>}{typeof reference.document === 'string' && <details open><summary>交接正文</summary><pre className="safe-report">{reference.document}</pre></details>}</div>}
    <p role="status">{notice}</p><p className="small-note">查看资料和恢复记忆均不需要 Git 传输。记忆恢复会备份所列文件；不恢复 Codex 原生数据库。源码工作区在下方项目入口重新映射；依赖缺失与版本不符会列出。Git 获取后须重新预览本机应用。旧配置导入保留原件与备份，已有不同设备配置时停止。</p>
  </section>
}
