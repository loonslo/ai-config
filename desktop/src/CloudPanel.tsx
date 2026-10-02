import { useEffect, useState } from 'react'
import { open, save } from '@tauri-apps/plugin-dialog'

export type FeatureReply = { operation?: string; status?: string; can_apply?: boolean; plan_id?: string; result?: Record<string, unknown>; error?: { message?: string } }
type Props = { busy: boolean; reply: FeatureReply | null; appliedContentId?: string; request: (operation: 'cloud', params: Record<string, unknown>, planId?: string) => void; openPackage: (path: string) => void }
const actions: Record<string, { label: string; fields: string[] }> = {
  login: { label: '登录（系统浏览器授权）', fields: ['issuer', 'client_id', 'audience'] },
  poll_login: { label: '检查登录授权', fields: [] }, logout: { label: '退出／取消登录', fields: [] },
  spaces: { label: '读取配置空间', fields: [] }, create_space: { label: '创建配置空间', fields: ['name'] },
  generate_key: { label: '首台设备生成密钥与恢复材料', fields: ['space'] }, unlock: { label: '新设备恢复解锁', fields: ['space', 'material'] },
  versions: { label: '读取版本与最近回执', fields: ['space'] }, upload: { label: '加密上传／续传', fields: ['space', 'package_path', 'expected_head'] },
  download: { label: '下载、解密与检查', fields: ['space', 'version', 'destination'] },
  devices: { label: '读取设备', fields: [] }, revoke: { label: '撤销设备访问', fields: ['device'] },
  receipt: { label: '报告此下载版本的本机应用（加载未核验）', fields: ['space', 'version'] },
}
const labels: Record<string, string> = { issuer: 'OIDC 签发方 HTTPS 地址', client_id: '公开客户端 ID', audience: 'API audience', name: '新空间名称', space: '配置空间', material: '恢复材料', package_path: '已导出的 .aiconfig 包', expected_head: '实际共同父版本（无共同基线选 none）', version: '云端版本', destination: '下载为新文件', device: '要撤销的设备' }

function savedSettings(): { server?: string; options?: Record<string, string> } {
  try {
    const value = JSON.parse(localStorage.getItem('ai-config.cloud.public.v1') ?? '{}')
    const allowed = ['issuer', 'client_id', 'audience', 'space', 'name', 'version', 'downloaded_content', 'downloaded_version']
    return { server: typeof value.server === 'string' ? value.server : '', options: Object.fromEntries(allowed.filter(key => typeof value.options?.[key] === 'string').map(key => [key, value.options[key]])) }
  } catch { return {} }
}
export default function CloudPanel({ busy, reply, appliedContentId, request, openPackage }: Props) {
  const [server, setServer] = useState(() => savedSettings().server ?? '')
  const [action, setAction] = useState('login')
  const [options, setOptions] = useState<Record<string, string>>(() => ({ expected_head: 'none', name: 'personal', ...(savedSettings().options ?? {}) }))
  const [plan, setPlan] = useState<string>()
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [notice, setNotice] = useState('离线功能不要求登录。登录与取得解密密钥是两个步骤。')
  const [spaces, setSpaces] = useState<Array<{ space_id: string; name: string }>>([])
  const [versions, setVersions] = useState<Array<{ version_id: string; conflict: boolean }>>([])
  const [devices, setDevices] = useState<Array<{ device_id: string; name: string; revoked: boolean }>>([])
  useEffect(() => {
    const publicOptions = Object.fromEntries(['issuer', 'client_id', 'audience', 'space', 'name', 'version', 'downloaded_content', 'downloaded_version'].filter(key => options[key]).map(key => [key, options[key]]))
    localStorage.setItem('ai-config.cloud.public.v1', JSON.stringify({ server, options: publicOptions }))
  }, [server, options])
  useEffect(() => {
    if (reply?.operation !== 'cloud') return
    let active = true
    queueMicrotask(() => {
    if (!active) return
    if (reply.status === 'failed') { setNotice(reply.error?.message ?? '操作失败'); setPlan(undefined); return }
    if (reply.status === 'preview') { setPlan(reply.can_apply ? reply.plan_id : undefined); return }
    if (reply.status !== 'applied' || !reply.result) return
    const value = reply.result
    setResult(value); setPlan(undefined); setOptions(current => ({ ...current, material: '' }))
    if (Array.isArray(value.spaces)) setSpaces(value.spaces as Array<{ space_id: string; name: string }>)
    if (Array.isArray(value.versions)) setVersions(value.versions as Array<{ version_id: string; conflict: boolean }>)
    if (Array.isArray(value.devices)) setDevices(value.devices as Array<{ device_id: string; name: string; revoked: boolean }>)
    if (typeof value.space_id === 'string') setOptions(current => ({ ...current, space: value.space_id as string }))
    if (value.state === 'logged_in' || value.state === 'logged_out') { setSpaces([]); setVersions([]); setDevices([]); setOptions(current => ({ ...current, space: '', version: '', expected_head: 'none', downloaded_content: '', downloaded_version: '' })) }
    if (value.state === 'downloaded' && typeof value.content_id === 'string') setOptions(current => ({ ...current, downloaded_content: value.content_id as string, downloaded_version: current.version }))
    setNotice(String(value.note ?? value.state ?? '操作已完成'))
    })
    return () => { active = false }
  }, [reply])
  const update = (key: string, value: string) => { setPlan(undefined); setOptions(current => ({ ...current, [key]: value })); if (key === 'space') { setVersions([]); setResult(null); setOptions(current => ({ ...current, material: '', expected_head: 'none', version: '' })) } }
  const chooseFile = async (key: string) => { const path = key === 'destination' ? await save({ defaultPath: 'downloaded.aiconfig', filters: [{ name: 'AI Config', extensions: ['aiconfig'] }] }) : await open({ multiple: false, filters: [{ name: 'AI Config', extensions: ['aiconfig'] }] }); if (typeof path === 'string') update(key, path) }
  const choices = (key: string) => key === 'space' ? spaces.map(row => ({ value: row.space_id, label: row.name })) : key === 'device' ? devices.map(row => ({ value: row.device_id, label: `${row.name}${row.revoked ? ' · 已撤销' : ''}` })) : versions.map(row => ({ value: row.version_id, label: `${row.version_id.slice(0, 12)}${row.conflict ? ' · 分叉保留' : ''}` }))
  return <section className="panel feature-panel"><h2>服务器同步</h2><p>服务器只保存加密包。新设备先登录，再用恢复材料解锁；下载完成后仍需本机导入预览。</p>
    <label className="package-field"><span>服务器 HTTPS 地址</span><input disabled={busy} value={server} autoComplete="off" onChange={event => { setServer(event.target.value); setOptions({ expected_head: 'none', name: 'personal' }); setSpaces([]); setVersions([]); setDevices([]); setPlan(undefined); setResult(null) }} /></label>
    <label className="package-field"><span>操作</span><select disabled={busy} value={action} onChange={event => { setAction(event.target.value); setPlan(undefined); setResult(null) }}>{Object.entries(actions).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}</select></label>
    <div className="package-form-row">{actions[action].fields.map(key => <label key={key} className="package-field"><span>{labels[key]}</span>{['space', 'device', 'version', 'expected_head'].includes(key) ? <select disabled={busy} value={options[key] ?? ''} onChange={event => update(key, event.target.value)}><option value={key === 'expected_head' ? 'none' : ''}>{key === 'expected_head' ? 'none · 无共同父版本' : '请先读取列表并选择'}</option>{choices(key).map(row => <option key={row.value} value={row.value}>{row.label}</option>)}</select> : <input disabled={busy} type={key === 'material' ? 'password' : 'text'} autoComplete="off" value={options[key] ?? ''} onChange={event => update(key, event.target.value)} />}{['destination', 'package_path'].includes(key) && <button className="subtle-button" disabled={busy} type="button" onClick={() => void chooseFile(key)}>选择文件</button>}</label>)}</div>
    <div className="setup-actions"><button className="subtle-button" disabled={busy || !server || actions[action].fields.some(key => !options[key]) || (action === 'receipt' && (!appliedContentId || options.downloaded_content !== appliedContentId || options.downloaded_version !== options.version))} type="button" onClick={() => { setResult(null); const values = action === 'receipt' ? { summary: { space_id: options.space, version_id: options.version, content_id: appliedContentId, state: 'applied', load_verified: false } } : Object.fromEntries(actions[action].fields.map(key => [key, options[key]])); request('cloud', { server, action, options: values }) }}>预览操作</button>{plan && <><button className="primary-button" disabled={busy} type="button" onClick={() => request('cloud', {}, plan)}>确认执行</button><button className="subtle-button" disabled={busy} type="button" onClick={() => { setPlan(undefined); update('material', '') }}>取消</button></>}</div>
    {typeof result?.recovery_material === 'string' && <div className="setup-preview"><strong>请保存到密码管理器或独立安全备份</strong><code className="recovery-material">{result.recovery_material}</code><button className="subtle-button" type="button" onClick={() => setResult(null)}>已保存，隐藏恢复材料</button></div>}
    {typeof result?.package_path === 'string' && <button className="primary-button" disabled={busy} type="button" onClick={() => openPackage(result.package_path as string)}>进入本机映射与冲突预览</button>}
    <p role="status">{notice}</p>{result && !result.recovery_material && <details open><summary>本步骤结果</summary><pre className="safe-report">{JSON.stringify(result, null, 2)}</pre></details>}
    <p className="small-note">共同父版本必须是本次修改实际基于的版本；读取云端列表不会自动选择父版本。并发上传保留双方。历史恢复先下载、导入、重新导出，再上传新版本。回执为最近报告，不代表设备在线。全部密钥丢失时登录不能解密旧包。</p>
  </section>
}
