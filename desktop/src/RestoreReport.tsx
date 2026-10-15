export type ConflictChoice = 'overwrite' | 'keep'
export type ConflictChoices = Record<string, ConflictChoice>
export type Conflict = { entry_id: string; agent: string; kind: string; target: string; conflict_group?: string; conflict_scope?: string; field?: string; path?: string; reason: string; decision?: ConflictChoice | 'pending' }
export type Skipped = { entry_id: string; agent: string; kind: string; target?: string; logical_path?: string; project?: string; field?: string; reason: string }
type Check = { label: string; status: string; target?: string; logical_path?: string; project?: string; reason?: string; verified_fields?: string[]; retained_fields?: string[]; skipped_fields?: string[] }
export type VerificationReport = {
  checks: Check[]; counts: Record<string, number>; exit_code: number
  groups: Array<{ label: string; kind: string; counts: Record<string, number>; check_indexes: number[] }>
  questions: Array<{ agent: string; prompt: string; expected: string }>
}
const kinds: Record<string, string> = { rules: '规则', settings_fields: '设置', permissions_local: '项目操作权限', persona: '人设', skills_text: '技能', memory: '记忆', trust_fields: '项目信任', skills: '技能', approvals: '已批准的操作', customizations: '自建指令', scripts: '自写脚本', plans: '计划笔记', env_fields: '环境变量', history_files: '历史记录' }
const agents: Record<string, string> = { claude: 'Claude', codex: 'Codex', workbuddy: 'WorkBuddy', 'workbuddy-ai': 'WorkBuddy AI', shared: '通用技能', system: '环境变量' }
const reasons: Record<string, string> = {
  group_not_selected: '本次未选择这类内容', redacted: '里面的密钥已被隐藏，请重新填写', exported: '已导出到报告文件夹，请自行导入', needs_rebuild: '缺少可重新生成的程序文件，请按来源重装', link_blocked: '目标文件夹被链接接管，已跳过',
  manual_trust: '需要在 Claude 中手动确认项目信任', manual_workbuddy: '未选择复制 WorkBuddy 文本',
  security_not_confirmed: '未确认恢复模型与安全设置', trust_not_confirmed: '未确认 Codex 项目信任',
  kept_local: '按你的选择保留本机内容', memory_not_selected: '未选择恢复记忆',
  agent_not_initialized: '助手目录未初始化', project_missing: '工作文件夹不存在',
  unsafe_target: '目标路径含链接或无法安全读取', agent_not_selected: '本次未选择这个助手',
  file_differs: '文件内容不同', field_differs: '设置字段不同', trust_differs: '项目信任不同',
  field_missing: '本机缺少设置字段', trust_missing: '本机尚无这个项目的信任记录',
  alternate_already_differs: '已有另存副本内容不同',
}
const words: Record<string, string> = { PASS: '一致', FAIL: '核验失败', MANUAL: '需要人工确认', SKIP: '已跳过', KEPT: '保留本机内容', PARTIAL: '部分字段已核验', SAVED: '仅另存副本一致' }
const units: Record<string, string> = { rules: '个文件', settings_fields: '份设置', permissions_local: '个权限文件', persona: '个人设文件', skills_text: '个文件', memory: '个文件', trust_fields: '个文件夹' }

export function ConflictPanel({ conflicts, choices, applied, disabled, onChoose }: {
  conflicts: Conflict[]; choices: ConflictChoices; applied: boolean; disabled: boolean
  onChoose: (ids: string[], value: ConflictChoice) => void
}) {
  const groups = new Map<string, Conflict[]>()
  for (const item of conflicts) {
    const key = item.conflict_group ? `${item.conflict_scope}:${item.conflict_group}` : item.target
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  const ids = [...new Set(conflicts.map(v => v.entry_id))]
  return <section className="restore-conflicts"><h2>{applied ? '已有配置的处理结果' : '选择已有配置的处理方式'}</h2>
    {!applied && <><p>下面 {groups.size} 个文件或技能需要选择处理方式。选择后直接确认恢复。</p>
      <p>覆盖前会备份本机完整原文件，可在恢复记录中撤销。设置文件只覆盖备份中的支持字段，其余字段保留。</p>
      <div className="machine-actions"><button className="subtle-button" disabled={disabled} onClick={() => onChoose(ids, 'overwrite')}>全部备份后覆盖</button><button className="subtle-button" disabled={disabled} onClick={() => onChoose(ids, 'keep')}>全部保留本机内容</button></div></>}
    {[...groups].map(([key, items], index) => {
      const entryIds = [...new Set(items.map(v => v.entry_id))]
      const values = entryIds.map(id => choices[id] ?? items.find(v => v.entry_id === id)?.decision)
      const value = values.every(v => v === values[0]) ? values[0] : undefined
      return <div className="restore-conflict" key={key}><p><strong>{agents[items[0].agent]} · {kinds[items[0].kind]}{items[0].conflict_group && <> · {items[0].conflict_group.split(':').at(-1)}</>}</strong></p>
        {[...new Set(items.map(v => v.target))].map(target => <p key={target}><code>{target}</code></p>)}
        <ul>{items.map((v, i) => <li key={i}>{v.field ? <>设置字段：<code>{v.field}</code>{v.reason === 'field_missing' && '（本机缺少，将新增）'}</> : reasons[v.reason] ?? '内容不同'}{v.path && <> · <code>{v.path}</code></>}</li>)}</ul>
        {applied ? <p>{value === 'overwrite' ? '已备份本机原文件，并使用备份内容覆盖。' : '已保留本机内容。'}</p> : <div className="machine-actions">
          <label className="machine-choice"><input type="radio" name={`conflict-${index}`} checked={value === 'overwrite'} disabled={disabled} onChange={() => onChoose(entryIds, 'overwrite')} />备份后覆盖</label>
          <label className="machine-choice"><input type="radio" name={`conflict-${index}`} checked={value === 'keep'} disabled={disabled} onChange={() => onChoose(entryIds, 'keep')} />保留本机内容</label>
        </div>}
      </div>
    })}
  </section>
}

export function SkippedPanel({ items }: { items: Skipped[] }) {
  const groups = new Map<string, Skipped[]>()
  for (const item of items) {
    const key = `${item.agent}:${item.reason}`
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  return <details><summary>保留与跳过的内容</summary>{[...groups].map(([key, list]) => <details key={key}>
    <summary>{agents[list[0].agent]}：{reasons[list[0].reason] ?? '需要人工核对'}（{list.length} 项）</summary>
    <ul className="verification-details">{list.map((v, i) => <li key={i}><code>{v.target || v.project || v.logical_path}</code>{v.field && <> · 字段 <code>{v.field}</code></>}</li>)}</ul>
  </details>)}</details>
}

export function VerificationPanel({ report }: { report: VerificationReport }) {
  return <section><h2>恢复核验</h2><p>核验文件或已接受的设置字段；助手实际加载需在新会话里确认。</p>
    {report.groups.map((group, i) => <details key={i} open={Boolean(group.counts.FAIL)} className={group.counts.FAIL ? 'verification-failed' : ''}>
      <summary>{group.label}：{group.kind === 'not_selected' ? `本次未选择（${group.check_indexes.length} 个备份条目）` : Object.entries(group.counts).map(([status, count]) => `${count} ${units[group.kind] ?? '项'}${status === 'PASS' && group.kind === 'settings_fields' ? '已接受字段一致' : words[status] ?? status}`).join('；')}</summary>
      <ul className="verification-details">{group.check_indexes.map(index => {
        const item = report.checks[index]
        return <li key={index}><code>{item.target || item.project || item.logical_path || item.label}</code>：{words[item.status] ?? item.status}
          {item.reason && <p>{reasons[item.reason] ?? '需要人工核对'}</p>}
          {!!item.verified_fields?.length && <p>已核验字段：{item.verified_fields.join('、')}</p>}
          {!!item.retained_fields?.length && <p>保留本机字段：{item.retained_fields.join('、')}</p>}
          {!!item.skipped_fields?.length && <p>跳过字段：{item.skipped_fields.join('、')}</p>}
        </li>
      })}</ul>
    </details>)}
    {!!report.questions.length && <><h2>在助手新会话里确认</h2>{report.questions.map((v, i) => <details key={i}><summary>{agents[v.agent]}：{v.prompt}</summary><p>对照原句：{v.expected}</p></details>)}</>}
  </section>
}

export function NextSteps({ text }: { text: string }) {
  const lines = text.split(/\r?\n/).filter(line => line.startsWith('- ')).map(line => line.slice(2))
  return <section><h2>接下来要做的事</h2><ul>{lines.map((line, i) => <li key={i}>{line}</li>)}</ul></section>
}
