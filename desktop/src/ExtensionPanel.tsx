import { useEffect, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import type { FeatureReply } from './CloudPanel'
type Props = { busy: boolean; reply: FeatureReply | null; request: (operation: 'extension_capture', params: Record<string, unknown>, planId?: string) => void }
export default function ExtensionPanel({ busy, reply, request }: Props) {
  const [kind, setKind] = useState('skills')
  const [profile, setProfile] = useState('codex')
  const [name, setName] = useState('')
  const [source, setSource] = useState('')
  const [plan, setPlan] = useState<string>()
  const [notice, setNotice] = useState('只读取你明确选择的来源；此步骤只保存配置库，不部署或执行。')
  useEffect(() => { if (reply?.operation !== 'extension_capture') return; let active = true; queueMicrotask(() => { if (!active) return; setPlan(reply.status === 'preview' && reply.can_apply ? reply.plan_id : undefined); setNotice(reply.error?.message ?? `${reply.result?.file_count ?? 0} 个文件 · ${reply.result?.note ?? reply.status}`) }); return () => { active = false } }, [reply])
  return <section className="panel feature-panel"><h2>采集选定扩展内容</h2><div className="package-form-row"><label className="package-field"><span>内容类型</span><select disabled={busy} value={kind} onChange={event => { setKind(event.target.value); setSource(''); setPlan(undefined) }}><option value="skills">单个技能</option><option value="mcp">Codex MCP</option><option value="memory">已校验记忆快照</option><option value="handoffs">项目交接清单</option></select></label><label className="package-field"><span>来源 Agent</span><select disabled={busy} value={profile} onChange={event => { setProfile(event.target.value); setPlan(undefined) }}><option value="codex">Codex</option><option value="claude">Claude</option></select></label><label className="package-field"><span>技能逻辑名／MCP 服务名／项目 ID</span><input disabled={busy} value={name} onChange={event => { setName(event.target.value); setPlan(undefined) }} placeholder="小写字母、数字、连字符" /></label></div><div className="setup-actions"><button className="subtle-button" disabled={busy} type="button" onClick={async () => { const path = await open({ directory: kind === 'skills', multiple: false }); if (typeof path === 'string') { setSource(path); setPlan(undefined) } }}>选择来源</button><button className="subtle-button" disabled={busy || !source || !name} type="button" onClick={() => request('extension_capture', { kind, profile, name, source })}>检查与预览采集</button>{plan && <button className="primary-button" disabled={busy} type="button" onClick={() => request('extension_capture', {}, plan)}>确认保存到配置库</button>}</div>{source && <code>{source}</code>}<p role="status">{notice}</p><p className="small-note">技能须在已登记 Agent 的 skills 范围内；外部链接与未支持二进制资源阻止完整采集。MCP 含内嵌密钥时停止，变量引用只保留名称。记忆和交接只使用已登记库的清单。Codex 仅作参考。</p></section>
}
