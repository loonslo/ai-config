import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { join } from '@tauri-apps/api/path'
import { open, save } from '@tauri-apps/plugin-dialog'
import { Command, type Child } from '@tauri-apps/plugin-shell'
import './App.css'
import CloudPanel, { type FeatureReply } from './CloudPanel'
import ExtensionPanel from './ExtensionPanel'
import LocalToolsPanel from './LocalToolsPanel'

type PageId = 'overview' | 'agents' | 'migration' | 'cloud' | 'history' | 'extras'
type Operation = 'status' | 'setup' | 'migrate' | 'declare' | 'rule_library' | 'save_rule' | 'rules' | 'diff' | 'config' | 'verify_load' | 'detach' | 'undo' | 'doctor' | 'inventory' | 'snapshots' | 'memory_setup' | 'project' | 'project_setup' | 'restore_snapshot' | 'start' | 'finish' | 'package_import' | 'package_export' | 'cloud' | 'extension_capture' | 'package_capabilities' | 'portable_restore' | 'portable_project' | 'git_transport' | 'import_config'
type InstalledTool = { tool: string; name?: string; installed: boolean; root?: string; root_origin?: string }
type SetupReport = {
  ready?: boolean
  status?: string
  written?: boolean
  reason?: string
  store?: { action?: string; path?: string; detail?: string }
  config?: { device?: string; state_dir?: string; memory_repo?: string; config_repo?: string; agents?: Record<string, { root?: string }>; codex?: string; claude?: string }
  detected?: { tools?: InstalledTool[] }
}
type MigrationItem = {
  id: string
  kind: string
  instance: string
  path?: string
  lines?: number
  unique_lines?: number
  shared_with?: string[]
  default?: string | null
  choices: string[]
  unique_preview?: Array<{ line_number: number; text: string }>
}
type MigrationReport = {
  status?: string
  items?: MigrationItem[]
  blocked?: Array<{ instance?: string; path?: string; reason?: string }>
  selected?: Record<string, string>
  written?: boolean
  backup?: string | null
  changes?: number
}
type PackageConflictRow = { key: string; scope: string; logical_source: string; instance_id?: string | null; status: string; choices: string[]; decision?: string | null; detail: string }
type PackageImportReport = {
  status?: string
  can_apply?: boolean
  content_id?: string
  source_name?: string
  apply_to_agents?: boolean
  mapping_details?: Array<{ logical_source: string; status: string; detail: string }>
  changed_file_count?: number
  conflicts?: { status?: string; baseline_status?: string; can_update_store?: boolean; can_apply_to_agents?: boolean; rows?: PackageConflictRow[] }
  agent_selections?: Array<{ key: string; logical_source: string; status: string; candidates: Array<{ instance_id: string; profile_id: string; installed: boolean; configured: boolean }> }>
}
type PackageExportReport = {
  status?: string
  can_apply?: boolean
  written?: boolean
  format?: string
  destination_name?: string
  content_id?: string
  selected_sources?: string[]
  scope_items?: Array<{ logical_source: string; data_type: string; status: string; detail?: string; selected: boolean; selectable: boolean }>
  entry_count?: number
  object_count?: number
  exclusion_count?: number
  exclusions?: Array<{ logical_source: string; category: string }>
  review_required?: Array<{ logical_source: string; category: string; detail?: string; line_numbers?: number[] }>
  unsupported?: Array<{ logical_source: string; category: string; detail?: string }>
  unclassified_top_level_count?: number
  reason?: string | null
}
type DeclareReport = { agent?: string; root_exists?: boolean; declaration?: Record<string, unknown>; status?: string; written?: boolean }
type RuleFile = { topic: string; status: string; content: string }
type RuleLibraryReport = { rules?: RuleFile[]; store_path?: string }
type SaveRuleReport = { status?: string; topic?: string; target?: string; bytes?: number; ready?: boolean; written?: boolean; backup?: string | null }
type ApplyRulesReport = { status?: string; changes?: number | Array<{ path: string; action: string; size: number }>; count?: number; written?: boolean }
type DiffItem = { tool: string; field: string; label: string; source: string; shared_value: unknown; local_value: unknown; choices: string[] }
type DiffOutcome = { choice?: string; tool?: string; field?: string; target?: string; effect?: string; status?: string; written?: boolean; backup?: string | null }
type DiffReport = { status?: string; ready?: boolean; diffs?: DiffItem[]; outcomes?: DiffOutcome[]; written?: boolean }
type ManagedTarget = { tool?: string; target_kind?: string; status?: string; load_check?: string }
type DeviceState = {
  capabilities?: { config?: { status?: string } }
  managed?: { targets?: ManagedTarget[] }
}
type RegisteredAgent = { id: string; name: string }
type VerifyLoadReport = { status?: string; agent?: string; applied?: boolean; question?: string; passed?: boolean; expected?: string | null; answered?: string | null; reason?: string | null; recorded?: boolean }
type DetachReport = { status?: string; instance?: string; name?: string; files?: Array<{ path: string; action: string }>; conflicts?: Array<{ path: string; reason: string }>; restored?: string[]; written?: boolean; backup?: string | null }
type UndoOperation = { index: number; operation_id?: string; operation?: string; created_at?: string; tools?: string[]; change_count?: number; backup?: string; targets?: Array<{ path: string; action: string }>; statement: string; status?: string }
type UndoReport = { status?: string; count?: number; operations?: UndoOperation[]; operation?: UndoOperation & { changes?: Array<{ path: string }> }; changes?: number; paths?: string[]; ready?: boolean; note?: string }
type DoctorReport = { ok?: boolean; issues?: string[]; warnings?: string[]; checks?: { transactions?: Array<{ operation_id?: string; status?: string }> } }
type MemorySource = { source_id: string; tool: string; status: string; path?: string | null; project_id?: string | null; suggested_id?: string | null; file_count?: number; capability?: string; enableable?: boolean; needs_mapping?: boolean; reason?: string | null; detail?: string | null }
type MemorySetupReport = { status?: string; sources?: MemorySource[]; mappings?: Array<{ id: string; path: string }>; selection_preview?: { status?: string; mappings?: Array<{ id: string; path: string }>; rejected?: Array<{ path: string; reason: string }>; note?: string }; removed_mappings?: string[]; written?: boolean; backup?: string | null; note?: string }
type InventoryReport = { inventory_id?: string; saved?: string | null; summary?: { total?: number; ready?: number; pending_mapping?: number; unavailable?: number }; sources?: MemorySource[] }
type SnapshotRow = { snapshot_id: string; device_id?: string; created_at?: string; tool?: string; project_id?: string; source_status?: string; file_count?: number; confirmed?: boolean; status?: string; restorable?: boolean }
type SnapshotsReport = { snapshots?: SnapshotRow[]; memory_repository_exists?: boolean }
type ProjectRow = { project_id: string; path?: string; name?: string; has_memory?: boolean }
type HandoffRow = { handoff_id: string; created_at?: string; status?: string; memory_snapshot?: string; missing_fields?: string[] }
type ProjectReport = { status?: string; projects?: ProjectRow[]; project_id?: string; handoff_id?: string; available_handoffs?: HandoffRow[]; ready?: boolean; reason?: string; goal?: string; completed?: string; next_step?: string; remaining?: string; version?: string; unsynced?: string[]; checks?: Record<string, unknown> }
type ProjectSetupReport = { ready?: boolean; project_id?: string; path?: string; previous_path?: string | null; written?: boolean; backup?: string | null }
type RestoreSnapshotReport = { status?: string; snapshot_id?: string; changes?: number; paths?: string[]; written?: boolean }
type StartReport = { status?: string; ready?: boolean; changes?: number; paths?: string[]; reason?: string; note?: string; memory_snapshot?: string; handoff_id?: string }
type FinishReport = { status?: string; project_id?: string; handoff_id?: string; handoff_missing_fields?: string[]; code_ready?: boolean; code_branch?: string | null; code_dirty_files?: string[]; memory_file_count?: number; memory_repository_exists?: boolean; memory_remote_configured?: boolean; config_ready?: boolean; config_version?: string; config_dirty_files?: string[]; transport?: string; snapshot_id?: string; missing_fields?: string[] }
type StatusReport = {
  status?: string
  configured?: boolean
  state?: DeviceState | null
  agents?: RegisteredAgent[]
  receipts?: Array<{ device_id?: string; reported_at?: string }>
  next_step?: string
}
type RpcEvent = {
  type?: string
  status?: string
  stage?: string
  operation?: string
  request_id?: string | null
  plan_id?: string | null
  can_apply?: boolean
  result?: StatusReport & SetupReport & MigrationReport & PackageImportReport & PackageExportReport & DeclareReport & RuleLibraryReport & SaveRuleReport & ApplyRulesReport & DiffReport & VerifyLoadReport & DetachReport & UndoReport & DoctorReport & MemorySetupReport & InventoryReport & SnapshotsReport & ProjectReport & ProjectSetupReport & RestoreSnapshotReport & StartReport & FinishReport
  error?: { code?: string; message?: string }
}

const pages: Array<{ id: PageId; label: string; symbol: string }> = [
  { id: 'overview', label: '总览', symbol: '⌂' },
  { id: 'agents', label: 'Agent 与规则', symbol: '◈' },
  { id: 'migration', label: '设备迁移', symbol: '⇄' },
  { id: 'cloud', label: '云端同步', symbol: '☁' },
  { id: 'history', label: '历史与恢复', symbol: '↶' },
  { id: 'extras', label: '记忆与接续', symbol: '⌘' },
]

const statusLabels: Record<string, string> = {
  not_configured: '未设置',
  pending_sync: '待应用',
  applied: '文件已应用',
  local_modified: '本机有修改',
  conflict: '存在冲突',
  offline: '离线',
  apply_failed: '应用失败',
  restart_required: '需要新会话',
}

const loadLabels: Record<string, string> = {
  verified: '新会话已核验',
  stale: '需要新会话并重新核验',
  failed: '核验未通过',
  unverified: '尚未核验',
}

function statusTone(status?: string): 'good' | 'warning' | 'error' | 'neutral' {
  if (status === 'applied' || status === 'verified') return 'good'
  if (status === 'apply_failed' || status === 'conflict' || status === 'failed' || status === 'offline') return 'error'
  if (status === 'local_modified' || status === 'pending_sync' || status === 'restart_required' || status === 'stale') return 'warning'
  return 'neutral'
}

const migrationChoiceLabels: Record<string, string> = {
  adopt: '迁入共享配置库',
  keep: '保留在原处',
  skip: '暂不处理',
  remove: '从原文件移除（先备份）',
}

const ruleTopicLabels: Record<string, string> = {
  instructions: '通用说明',
  principles: '原则',
  engineering: '工程规范',
  python: 'Python',
  langgraph: 'LangGraph',
  rag: 'RAG',
  security: '安全',
}
const diffChoiceLabels: Record<string, string> = {
  share: '保存为共享值（更新本机规则库）',
  local: '仅保留在本机',
  restore: '恢复共享值到本机 Agent',
}

function displayConfigValue(value: unknown) {
  if (value === null || value === undefined) return '未设置'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  return '复杂结构（当前仅展示，不自动合并）'
}

function labelForStatus(status?: string) {
  return status ? statusLabels[status] ?? `状态：${status}` : '尚无状态'
}

function App() {
  const [advancedReply, setAdvancedReply] = useState<FeatureReply | null>(null)
  const [extensionKinds, setExtensionKinds] = useState<string[]>([])
  const [capabilityKinds, setCapabilityKinds] = useState<string[]>([])
  const commandRef = useRef<Command<string> | null>(null)
  const childRef = useRef<Child | null>(null)
  const spawnRef = useRef<Promise<Child> | null>(null)
  const closeSignalRef = useRef<(() => void) | null>(null)
  const statusRefreshRef = useRef<() => void>(() => {})
  const migrationRefreshRef = useRef<() => void>(() => {})
  const ruleLibraryRefreshRef = useRef<() => void>(() => {})
  const doctorRefreshRef = useRef<() => void>(() => {})
  const projectRefreshRef = useRef<() => void>(() => {})
  const startupDoctorChecked = useRef(false)
  const ruleTopicRef = useRef('instructions')
  const pendingTextRef = useRef('')
  const closingRef = useRef(false)
  const busyRef = useRef(false)
  const operationRef = useRef('')
  const [page, setPage] = useState<PageId>('overview')
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('读取本机状态…')
  const [message, setMessage] = useState('正在读取本地状态；此操作不会修改配置。')
  const [report, setReport] = useState<StatusReport | null>(null)
  const [tools, setTools] = useState<InstalledTool[]>([])
  const [toolScanDone, setToolScanDone] = useState(false)
  const [selectedTools, setSelectedTools] = useState<string[]>([])
  const [toolRoots, setToolRoots] = useState<Record<string, string>>({})
  const [storePath, setStorePath] = useState('')
  const [setupReport, setSetupReport] = useState<SetupReport | null>(null)
  const [setupPlanId, setSetupPlanId] = useState<string | null>(null)
  const [migrationReport, setMigrationReport] = useState<MigrationReport | null>(null)
  const [migrationChoices, setMigrationChoices] = useState<Record<string, string>>({})
  const [migrationPlanId, setMigrationPlanId] = useState<string | null>(null)
  const [migrationApplyResult, setMigrationApplyResult] = useState<MigrationReport | null>(null)
  const [packagePath, setPackagePath] = useState('')
  const [packageImportApplyToAgents, setPackageImportApplyToAgents] = useState(true)
  const [packageImportDecisions, setPackageImportDecisions] = useState<Record<string, string>>({})
  const [packageImportManualValues, setPackageImportManualValues] = useState<Record<string, string>>({})
  const [packageImportSelections, setPackageImportSelections] = useState<Record<string, string>>({})
  const [packageImportReport, setPackageImportReport] = useState<PackageImportReport | null>(null)
  const [packageImportPlanId, setPackageImportPlanId] = useState<string | null>(null)
  const [packageImportResult, setPackageImportResult] = useState<PackageImportReport | null>(null)
  const [packageExportFormat, setPackageExportFormat] = useState<'archive' | 'directory'>('archive')
  const [packageExportParent, setPackageExportParent] = useState('')
  const [packageExportFolderName, setPackageExportFolderName] = useState('ai-config-package')
  const [packageExportDestination, setPackageExportDestination] = useState('')
  const [packageExportReport, setPackageExportReport] = useState<PackageExportReport | null>(null)
  const [packageExportPlanId, setPackageExportPlanId] = useState<string | null>(null)
  const [packageExportResult, setPackageExportResult] = useState<PackageExportReport | null>(null)
  const [packageExportSelectedSources, setPackageExportSelectedSources] = useState<string[]>([])
  const [packageExportScopeInitialized, setPackageExportScopeInitialized] = useState(false)
  const [customAgentId, setCustomAgentId] = useState('')
  const [customAgentRoot, setCustomAgentRoot] = useState('')
  const [customAgentEntry, setCustomAgentEntry] = useState('AGENTS.md')
  const [customAgentMode, setCustomAgentMode] = useState('managed_block')
  const [declarePlanId, setDeclarePlanId] = useState<string | null>(null)
  const [declareReport, setDeclareReport] = useState<DeclareReport | null>(null)
  const [ruleFiles, setRuleFiles] = useState<RuleFile[]>([])
  const [ruleLibraryLoaded, setRuleLibraryLoaded] = useState(false)
  const [selectedRuleTopic, setSelectedRuleTopic] = useState('instructions')
  const [ruleDraft, setRuleDraft] = useState('')
  const [ruleSecretReplacement, setRuleSecretReplacement] = useState(false)
  const [saveRulePlanId, setSaveRulePlanId] = useState<string | null>(null)
  const [saveRuleReport, setSaveRuleReport] = useState<SaveRuleReport | null>(null)
  const [saveRuleResult, setSaveRuleResult] = useState<SaveRuleReport | null>(null)
  const [applyRulesPlanId, setApplyRulesPlanId] = useState<string | null>(null)
  const [applyRulesReport, setApplyRulesReport] = useState<ApplyRulesReport | null>(null)
  const [applyRulesResult, setApplyRulesResult] = useState<ApplyRulesReport | null>(null)
  const [diffReport, setDiffReport] = useState<DiffReport | null>(null)
  const [diffChoice, setDiffChoice] = useState('')
  const [diffPlanId, setDiffPlanId] = useState<string | null>(null)
  const [diffPreview, setDiffPreview] = useState<DiffReport | null>(null)
  const [diffResult, setDiffResult] = useState<DiffReport | null>(null)
  const [settingsPlanId, setSettingsPlanId] = useState<string | null>(null)
  const [settingsReport, setSettingsReport] = useState<ApplyRulesReport | null>(null)
  const [settingsResult, setSettingsResult] = useState<ApplyRulesReport | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [verifyLoadReport, setVerifyLoadReport] = useState<VerifyLoadReport | null>(null)
  const [verifyLoadPlanId, setVerifyLoadPlanId] = useState<string | null>(null)
  const [verifyLoadAnswer, setVerifyLoadAnswer] = useState('')
  const [verifyLoadResult, setVerifyLoadResult] = useState<VerifyLoadReport | null>(null)
  const [restoreOriginal, setRestoreOriginal] = useState(false)
  const [detachReport, setDetachReport] = useState<DetachReport | null>(null)
  const [detachPlanId, setDetachPlanId] = useState<string | null>(null)
  const [detachResult, setDetachResult] = useState<DetachReport | null>(null)
  const [undoReport, setUndoReport] = useState<UndoReport | null>(null)
  const [undoPlanId, setUndoPlanId] = useState<string | null>(null)
  const [undoResult, setUndoResult] = useState<UndoReport | null>(null)
  const [doctorReport, setDoctorReport] = useState<DoctorReport | null>(null)
  const [doctorPlanId, setDoctorPlanId] = useState<string | null>(null)
  const [memorySetupReport, setMemorySetupReport] = useState<MemorySetupReport | null>(null)
  const [memorySetupPlanId, setMemorySetupPlanId] = useState<string | null>(null)
  const [memorySetupResult, setMemorySetupResult] = useState<MemorySetupReport | null>(null)
  const [memorySelectionIds, setMemorySelectionIds] = useState<string[]>([])
  const [memorySelectionProjects, setMemorySelectionProjects] = useState<Record<string, string>>({})
  const [inventoryReport, setInventoryReport] = useState<InventoryReport | null>(null)
  const [inventoryPlanId, setInventoryPlanId] = useState<string | null>(null)
  const [inventoryResult, setInventoryResult] = useState<InventoryReport | null>(null)
  const [snapshotsReport, setSnapshotsReport] = useState<SnapshotsReport | null>(null)
  const [restoreSnapshotPlanId, setRestoreSnapshotPlanId] = useState<string | null>(null)
  const [restoreSnapshotReport, setRestoreSnapshotReport] = useState<RestoreSnapshotReport | null>(null)
  const [restoreSnapshotResult, setRestoreSnapshotResult] = useState<RestoreSnapshotReport | null>(null)
  const [projectReport, setProjectReport] = useState<ProjectReport | null>(null)
  const [projectId, setProjectId] = useState('')
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [projectPath, setProjectPath] = useState('')
  const [projectSetupPlanId, setProjectSetupPlanId] = useState<string | null>(null)
  const [projectSetupReport, setProjectSetupReport] = useState<ProjectSetupReport | null>(null)
  const [projectSetupResult, setProjectSetupResult] = useState<ProjectSetupReport | null>(null)
  const [handoffId, setHandoffId] = useState('')
  const [startReport, setStartReport] = useState<StartReport | null>(null)
  const [startPlanId, setStartPlanId] = useState<string | null>(null)
  const [startResult, setStartResult] = useState<StartReport | null>(null)
  const [handoffText, setHandoffText] = useState('')
  const [finishReport, setFinishReport] = useState<FinishReport | null>(null)
  const [finishPlanId, setFinishPlanId] = useState<string | null>(null)
  const [finishResult, setFinishResult] = useState<FinishReport | null>(null)

  const markBusy = useCallback((value: boolean) => {
    busyRef.current = value
    setBusy(value)
  }, [])

  useEffect(() => {
    let unlisten: (() => void) | undefined
    let disposed = false
    void getCurrentWindow().onCloseRequested(async (event) => {
      if (!commandRef.current) return
      event.preventDefault()
      closingRef.current = true
      setMessage('正在等待本机操作安全结束…')
      try {
        const child = childRef.current ?? await spawnRef.current
        if (child) {
          childRef.current = child
          const exited = new Promise<void>((resolve) => { closeSignalRef.current = resolve })
          await child.write(`${JSON.stringify({ protocol_version: 1, request_id: crypto.randomUUID(), type: 'shutdown' })}\n`)
          await exited
        }
        await getCurrentWindow().destroy()
      } catch (error) {
        setMessage(`关闭辅助程序失败：${String(error)}`)
        closingRef.current = false
      }
    }).then((dispose) => {
      if (disposed) dispose()
      else unlisten = dispose
    })
    return () => { disposed = true; unlisten?.() }
  }, [])

  const handleEvent = useCallback((event: RpcEvent) => {
    if (event.type === 'progress') {
      setStage(event.stage ?? '运行中')
      return
    }
    if (event.type !== 'result') return
    markBusy(false)
    if (['cloud', 'extension_capture', 'package_capabilities', 'portable_restore', 'portable_project', 'git_transport', 'import_config'].includes(operationRef.current ?? '')) {
      setAdvancedReply({ ...event, operation: operationRef.current ?? undefined } as unknown as FeatureReply)
      if (operationRef.current === 'package_capabilities') {
        const data = event.result as unknown as { capabilities?: Array<{ kind: string; implemented: boolean }> }
        setCapabilityKinds((data?.capabilities ?? []).filter(item => item.implemented).map(item => item.kind))
      }
      setStage(event.status === 'failed' ? '操作失败' : event.status === 'preview' ? '等待确认' : '步骤完成')
      return
    }
    if (event.status === 'failed') {
      setStage(operationRef.current === 'setup' ? '设置失败' : '读取失败')
      setMessage(`${event.error?.code ?? '运行失败'}：${event.error?.message ?? '未知错误'}`)
      if (operationRef.current === 'setup') setSetupPlanId(null)
      if (operationRef.current === 'migrate') setMigrationPlanId(null)
      if (operationRef.current === 'package_import') setPackageImportPlanId(null)
      if (operationRef.current === 'package_export') setPackageExportPlanId(null)
      if (operationRef.current === 'declare') setDeclarePlanId(null)
      if (operationRef.current === 'save_rule') setSaveRulePlanId(null)
      if (operationRef.current === 'rules') setApplyRulesPlanId(null)
      if (operationRef.current === 'diff') setDiffPlanId(null)
      if (operationRef.current === 'config') setSettingsPlanId(null)
      if (operationRef.current === 'verify_load') setVerifyLoadPlanId(null)
      if (operationRef.current === 'detach') setDetachPlanId(null)
      if (operationRef.current === 'undo') setUndoPlanId(null)
      if (operationRef.current === 'doctor') setDoctorPlanId(null)
      if (operationRef.current === 'inventory') setInventoryPlanId(null)
      if (operationRef.current === 'memory_setup') setMemorySetupPlanId(null)
      if (operationRef.current === 'restore_snapshot') setRestoreSnapshotPlanId(null)
      if (operationRef.current === 'project_setup') setProjectSetupPlanId(null)
      if (operationRef.current === 'start') setStartPlanId(null)
      if (operationRef.current === 'finish') setFinishPlanId(null)
      return
    }
    const data = event.result
    if (operationRef.current === 'status') {
      const configured = data?.configured ?? data?.status !== 'not_configured'
      setReport(data ?? null)
      setSelectedAgentId((current) => current && data?.agents?.some((agent) => agent.id === current) ? current : data?.agents?.[0]?.id ?? '')
      setStage(configured ? '状态已更新' : '尚未设置')
      setMessage(configured
        ? '状态来自本机配置与目标文件的只读核对。'
        : '当前设备尚未完成首次设置；读取状态没有创建或更改文件。')
      if (configured && !startupDoctorChecked.current) {
        startupDoctorChecked.current = true
        window.setTimeout(() => doctorRefreshRef.current(), 0)
      }
    }
    if (operationRef.current === 'setup') {
      if (event.status === 'applied') {
        setSetupPlanId(null)
        setSetupReport(data ?? null)
        setStage(data?.written ? '首次设置已保存' : '设置未写入')
        setMessage(data?.written ? '本机设备配置已保存。Agent 规则文件尚未因此修改。' : data?.reason ?? '设置没有写入。')
        if (data?.written) window.setTimeout(() => statusRefreshRef.current(), 0)
      } else {
        const detected = data?.detected?.tools ?? []
        setTools(detected)
        setSelectedTools((current) => current.length
          ? current.filter((tool) => detected.some((item) => item.tool === tool))
          : detected.filter((tool) => tool.installed).map((tool) => tool.tool))
        setToolRoots((current) => Object.fromEntries(detected.filter((tool) => tool.root).map((tool) => [tool.tool, current[tool.tool] ?? tool.root ?? ''])))
        setStorePath((current) => current || data?.store?.path || '')
        setSetupReport(data ?? null)
        setSetupPlanId(event.can_apply && data?.ready ? event.plan_id ?? null : null)
        setToolScanDone(true)
        setStage(data?.ready ? '设置方案已生成' : '环境尚未就绪')
        setMessage(data?.reason ?? (data?.ready ? '已生成只读设置方案；确认设备与目录后，才会保存本机配置。' : '当前条件不足以生成设置方案，请检查 Agent 选择与环境提示。'))
      }
    }
    if (operationRef.current === 'migrate') {
      if (event.status === 'applied') {
        setMigrationPlanId(null)
        setStage('迁入操作完成')
        setMigrationApplyResult(data ?? null)
        setMessage(data?.status === 'applied' ? '所选规则已处理，正在更新列表。' : '所选操作没有产生文件改动。')
        window.setTimeout(() => migrationRefreshRef.current(), 0)
      } else {
        setMigrationReport(data ?? null)
        setMigrationPlanId(event.can_apply ? event.plan_id ?? null : null)
        setStage('迁入项已读取')
        setMessage(data?.blocked?.length ? `发现 ${data.blocked.length} 项受保护或无法读取的内容，内容已隐藏。` : `发现 ${data?.items?.length ?? 0} 项可检查内容。`)
      }
    }
    if (operationRef.current === 'package_import') {
      if (event.status === 'applied') {
        setPackageImportPlanId(null)
        setPackageImportResult(data ?? null)
        setPackageImportReport(null)
        setMessage(data?.status === 'unchanged'
          ? '包内容已与本机一致；没有写入文件。'
          : '迁移包已写入并逐项回读核验。Agent 会话是否加载新规则仍需单独核验。')
        if (data?.status === 'applied') window.setTimeout(() => statusRefreshRef.current(), 0)
      } else {
        setPackageImportReport(data ?? null)
        setPackageImportPlanId(event.can_apply ? event.plan_id ?? null : null)
        setPackageImportResult(null)
        setMessage(data?.status === 'unchanged'
          ? '这个离线包与本机受支持内容一致；没有文件需要改动。'
          : data?.can_apply
          ? '导入预览已就绪；确认前会再次检查包和本机目标。'
          : '包已检查。请完成目标选择或冲突决定，再重新生成预览。')
      }
    }
    if (operationRef.current === 'package_export') {
      if (event.status === 'applied') {
        setPackageExportPlanId(null)
        setPackageExportResult(data ?? null)
        setPackageExportReport(null)
        setMessage('离线迁移包已生成在所选位置；没有上传服务器。')
      } else {
        setPackageExportReport(data ?? null)
        setPackageExportPlanId(event.can_apply ? event.plan_id ?? null : null)
        setPackageExportResult(null)
        if (data?.selected_sources) {
          setPackageExportSelectedSources(data.selected_sources)
          setPackageExportScopeInitialized(true)
        }
        setMessage(data?.can_apply
          ? '导出范围与目标已检查；确认后会重新采集并生成离线包。'
          : data?.reason ?? '当前导出范围需要检查，未生成文件。')
      }
    }
    if (operationRef.current === 'declare') {
      setDeclareReport(data ?? null)
      setDeclarePlanId(event.status === 'applied' ? null : event.can_apply ? event.plan_id ?? null : null)
      setStage(event.status === 'applied' ? '自定义 Agent 已登记' : '登记方案已生成')
      setMessage(event.status === 'applied' ? '自定义 Agent 规则入口已登记。应用规则仍需单独预览并确认。' : '请核对根目录和相对 Markdown 入口，再确认登记。')
      if (event.status === 'applied') window.setTimeout(() => statusRefreshRef.current(), 0)
    }
    if (operationRef.current === 'rule_library') {
      const rows = data?.rules ?? []
      setRuleFiles(rows)
      setRuleLibraryLoaded(true)
      const topic = rows.some((row) => row.topic === ruleTopicRef.current) ? ruleTopicRef.current : rows[0]?.topic ?? 'instructions'
      setSelectedRuleTopic(topic)
      setRuleDraft(rows.find((row) => row.topic === topic)?.content ?? '')
      setRuleSecretReplacement(false)
      setSaveRulePlanId(null)
      setSaveRuleReport(null)
      setMessage(`已读取本机规则库：${rows.filter((row) => row.status === 'ready').length} 项可编辑。保存到规则库不会自动写入 Agent。`)
    }
    if (operationRef.current === 'save_rule') {
      if (event.status === 'applied') {
        setSaveRulePlanId(null)
        setSaveRuleResult(data ?? null)
        setSaveRuleReport(null)
        setMessage(data?.written ? '规则已保存到本机共享配置库；Agent 文件尚未更改。' : '规则内容没有变化。')
        if (data?.written) window.setTimeout(() => ruleLibraryRefreshRef.current(), 0)
      } else {
        setSaveRuleReport(data ?? null)
        setSaveRulePlanId(event.can_apply ? event.plan_id ?? null : null)
        setSaveRuleResult(null)
      }
    }
    if (operationRef.current === 'rules') {
      if (event.status === 'applied') {
        setApplyRulesPlanId(null)
        setApplyRulesResult(data ?? null)
        setMessage('规则已应用到当前登记的 Agent 目标；服务器发布仍未执行。')
        window.setTimeout(() => statusRefreshRef.current(), 0)
      } else {
        setApplyRulesReport(data ?? null)
        setApplyRulesPlanId(event.can_apply ? event.plan_id ?? null : null)
        setApplyRulesResult(null)
      }
    }
    if (operationRef.current === 'diff') {
      if (event.status === 'applied') {
        setDiffPlanId(null)
        setDiffResult(data ?? null)
        setDiffPreview(null)
        setMessage('差异选择已保存。共享值修改只留在本机配置库，不会自动发布。')
      } else if (event.can_apply) {
        setDiffPreview(data ?? null)
        setDiffPlanId(event.plan_id ?? null)
        setDiffResult(null)
      } else {
        setDiffReport(data ?? null)
        setDiffPreview(null)
        setDiffPlanId(null)
      }
    }
    if (operationRef.current === 'config') {
      if (event.status === 'applied') {
        setSettingsPlanId(null)
        setSettingsResult(data ?? null)
        setSettingsReport(null)
        setMessage('已应用共享设置；本机状态正在重新核对。')
        window.setTimeout(() => statusRefreshRef.current(), 0)
      } else {
        setSettingsReport(data ?? null)
        setSettingsPlanId(event.can_apply ? event.plan_id ?? null : null)
        setSettingsResult(null)
      }
    }
    if (operationRef.current === 'verify_load') {
      if (event.status === 'applied') {
        setVerifyLoadPlanId(null)
        setVerifyLoadResult(data ?? null)
        setVerifyLoadReport(null)
        setMessage(data?.passed ? '新会话回答与当前规则版本一致，核验结果已记录。' : '回答未通过版本核验；失败结果已记录。')
        window.setTimeout(() => statusRefreshRef.current(), 0)
      } else {
        setVerifyLoadReport((current) => data ? { ...data, question: data.question ?? current?.question } : null)
        setVerifyLoadPlanId(event.can_apply ? event.plan_id ?? null : null)
        setVerifyLoadResult(null)
      }
    }
    if (operationRef.current === 'detach') {
      if (event.status === 'applied') {
        setDetachPlanId(null)
        setDetachResult(data ?? null)
        setDetachReport(null)
        setMessage('已移除该 Agent 的工具受管内容，并保存事务备份。')
        window.setTimeout(() => statusRefreshRef.current(), 0)
      } else {
        setDetachReport(data ?? null)
        setDetachPlanId(event.can_apply ? event.plan_id ?? null : null)
        setDetachResult(null)
      }
    }
    if (operationRef.current === 'undo') {
      if (event.status === 'applied') {
        setUndoPlanId(null)
        setUndoResult(data ?? null)
        setUndoReport(null)
        setMessage('已恢复所选操作之前的本机文件；共享配置源和远端内容未修改。')
        window.setTimeout(() => statusRefreshRef.current(), 0)
      } else if (event.can_apply) {
        setUndoReport(data ?? null)
        setUndoPlanId(event.plan_id ?? null)
        setUndoResult(null)
      } else {
        setUndoReport(data ?? null)
        setUndoPlanId(null)
      }
    }
    if (operationRef.current === 'doctor') {
      setDoctorReport(data ?? null)
      setDoctorPlanId(event.status === 'applied' ? null : event.can_apply ? event.plan_id ?? null : null)
      setMessage(event.status === 'applied' ? '中断事务恢复流程已执行，诊断结果已刷新。' : '本机诊断已完成；检查本身不会改动文件。')
    }
    if (operationRef.current === 'inventory') {
      if (event.status === 'applied') {
        setInventoryResult(data ?? null)
        setInventoryPlanId(null)
        setMessage(data?.saved ? '来源盘点报告已保存在本机状态目录。' : '来源盘点完成。')
      } else {
        setInventoryReport(data ?? null)
        setInventoryPlanId(event.can_apply ? event.plan_id ?? null : null)
        setInventoryResult(null)
      }
    }
    if (operationRef.current === 'memory_setup') {
      if (event.status === 'applied') {
        setMemorySetupResult(data ?? null)
        setMemorySetupPlanId(null)
        setMessage(data?.written ? '记忆映射已更新；源文件本身未被迁移或删除。' : data?.note ?? '记忆设置没有写入。')
        window.setTimeout(() => statusRefreshRef.current(), 0)
      } else {
        setMemorySetupReport(data ?? null)
        setMemorySetupPlanId(event.can_apply ? event.plan_id ?? null : null)
        setMemorySetupResult(null)
        const sources = data?.sources ?? []
        setMemorySelectionProjects((current) => Object.fromEntries(sources.map((source) => [source.source_id, current[source.source_id] ?? source.suggested_id ?? source.project_id ?? ''])))
      }
    }
    if (operationRef.current === 'snapshots') setSnapshotsReport(data ?? null)
    if (operationRef.current === 'restore_snapshot') {
      if (event.status === 'applied') {
        setRestoreSnapshotResult(data ?? null)
        setRestoreSnapshotReport(null)
        setRestoreSnapshotPlanId(null)
        setMessage('记忆快照已恢复到本机映射目录。')
        window.setTimeout(() => statusRefreshRef.current(), 0)
      } else {
        setRestoreSnapshotReport(data ?? null)
        setRestoreSnapshotPlanId(event.can_apply ? event.plan_id ?? null : null)
        setRestoreSnapshotResult(null)
      }
    }
    if (operationRef.current === 'project') {
      setProjectReport(data ?? null)
      if (data?.projects) setSelectedProjectId((current) => current && data.projects?.some((project) => project.project_id === current) ? current : data.projects?.[0]?.project_id ?? '')
      if (data?.available_handoffs?.some((row) => row.handoff_id === handoffId)) {
        setHandoffId(handoffId)
      } else if (data?.available_handoffs?.[0]) {
        setHandoffId(data.available_handoffs[0].handoff_id)
      }
    }
    if (operationRef.current === 'project_setup') {
      setProjectSetupReport(event.status === 'applied' ? null : data ?? null)
      setProjectSetupResult(event.status === 'applied' ? data ?? null : null)
      setProjectSetupPlanId(event.status === 'applied' ? null : event.can_apply ? event.plan_id ?? null : null)
      setMessage(event.status === 'applied' ? '本机项目目录映射已保存。' : data?.ready ? '项目映射预览已生成；只保存在本机设备配置。' : '项目目录不存在，不能登记映射。')
      if (event.status === 'applied') {
        if (data?.project_id) setSelectedProjectId(data.project_id)
        window.setTimeout(() => projectRefreshRef.current(), 0)
      }
    }
    if (operationRef.current === 'start') {
      if (event.status === 'applied') {
        setStartPlanId(null); setStartResult(data ?? null); setStartReport(null)
        setMessage(data?.status === 'ready' ? '项目接续已写入本机记忆映射。' : `接续状态：${data?.status ?? '已完成'}。`)
      } else {
        setStartReport(data ?? null); setStartPlanId(event.can_apply ? event.plan_id ?? null : null); setStartResult(null)
      }
    }
    if (operationRef.current === 'finish') {
      if (event.status === 'applied') {
        setFinishPlanId(null); setFinishResult(data ?? null); setFinishReport(null)
        setMessage(data?.status === 'uploaded' ? '交接与记忆快照已保存，并获得 Git 远端确认。' : data?.status === 'pending' ? '本机交接已保存，但远端传输待处理。' : '交接与记忆快照已在本机保存；当前状态或远端确认仍不完整。')
        window.setTimeout(() => projectRefreshRef.current(), 0)
      } else {
        setFinishReport(data ?? null); setFinishPlanId(event.can_apply ? event.plan_id ?? null : null); setFinishResult(null)
      }
    }
  }, [handoffId, markBusy])

  const requestOperation = useCallback(async (operation: Operation, params: Record<string, unknown> = {}, planId?: string) => {
    if (busyRef.current || closingRef.current) return
    markBusy(true)
    operationRef.current = operation
    setStage(operation === 'status' ? '读取本机状态…' : operation === 'migrate' ? '正在检查原有规则…' : operation === 'package_import' ? planId ? '正在应用离线包…' : '检查离线包与本机差异…' : operation === 'package_export' ? planId ? '正在生成离线包…' : '检查离线导出范围…' : operation === 'declare' ? '正在检查自定义 Agent…' : operation === 'rule_library' ? '读取共享规则…' : operation === 'save_rule' ? planId ? '正在保存共享规则…' : '预览共享规则保存…' : operation === 'rules' ? planId ? '正在应用 Agent 规则…' : '预览 Agent 规则应用…' : operation === 'diff' ? planId ? '正在保存差异选择…' : '预览差异选择…' : operation === 'config' ? planId ? '正在应用共享设置…' : '预览共享设置应用…' : operation === 'verify_load' ? planId ? '正在记录新会话核验…' : '检查新会话核验回答…' : operation === 'detach' ? planId ? '正在退出 Agent 接管…' : '生成退出接管预览…' : operation === 'undo' ? planId ? '正在恢复历史操作…' : '读取本机操作历史…' : operation === 'doctor' ? planId ? '正在恢复未完成事务…' : '检查未完成事务…' : operation === 'inventory' ? planId ? '正在保存本机来源盘点…' : '扫描本机记忆来源…' : operation === 'snapshots' ? '读取记忆快照清单…' : operation === 'memory_setup' ? planId ? '正在保存记忆映射…' : '检查本机记忆来源…' : operation === 'project' ? '读取项目接续状态…' : operation === 'project_setup' ? planId ? '正在保存项目映射…' : '预览本机项目映射…' : operation === 'restore_snapshot' ? planId ? '正在恢复记忆快照…' : '预览记忆快照恢复…' : operation === 'start' ? planId ? '正在接续项目…' : '检查项目接续…' : operation === 'finish' ? planId ? '正在保存交接与快照…' : '检查交接内容…' : planId ? '正在保存首次设置…' : '识别 Agent 环境…')
    if (operation === 'setup' && !planId) setToolScanDone(false)
    try {
      if (!commandRef.current) {
        const command = Command.sidecar('binaries/ai-config-rpc')
        command.stdout.on('data', (chunk) => {
          pendingTextRef.current += chunk
          const lines = pendingTextRef.current.split(/\r?\n/)
          pendingTextRef.current = lines.pop() ?? ''
          for (const line of lines) {
            if (!line.trim()) continue
            try { handleEvent(JSON.parse(line) as RpcEvent) }
            catch (error) {
              setStage('读取失败')
              setMessage(`无法解析本机核心响应：${String(error)}`)
              markBusy(false)
            }
          }
        })
        command.stderr.on('data', (chunk) => {
          if (chunk.trim()) {
            setStage('读取失败')
            setMessage(`本机核心错误：${chunk.trim()}`)
          }
        })
        command.on('error', (error) => {
          setStage('启动失败')
          setMessage(`无法启动本机核心：${String(error)}`)
        })
        command.on('close', () => {
          childRef.current = null
          commandRef.current = null
          spawnRef.current = null
          closeSignalRef.current?.()
          closeSignalRef.current = null
          if (!closingRef.current) markBusy(false)
        })
        commandRef.current = command
        spawnRef.current = command.spawn()
      }
      const child = childRef.current ?? await spawnRef.current
      if (!child || closingRef.current) return
      childRef.current = child
      const request = planId ? {
        protocol_version: 1,
        request_id: crypto.randomUUID(),
        type: 'apply',
        plan_id: planId,
      } : {
        protocol_version: 1,
        request_id: crypto.randomUUID(),
        type: 'preview',
        operation,
        params,
      }
      await child.write(`${JSON.stringify(request)}\n`)
    } catch (error) {
      commandRef.current = null
      spawnRef.current = null
      markBusy(false)
      setStage('启动失败')
      setMessage(`无法启动内置核心：${String(error)}`)
    }
  }, [handleEvent, markBusy])
  useEffect(() => {
    statusRefreshRef.current = () => { void requestOperation('status') }
    migrationRefreshRef.current = () => { void requestOperation('migrate') }
    ruleLibraryRefreshRef.current = () => { void requestOperation('rule_library') }
    doctorRefreshRef.current = () => { void requestOperation('doctor') }
    projectRefreshRef.current = () => { void requestOperation('project') }
  }, [requestOperation])
  useEffect(() => {
    const timer = window.setTimeout(() => { void requestOperation('status') }, 0)
    return () => window.clearTimeout(timer)
  }, [requestOperation])

  const acceptPackagePath = useCallback((path: string) => {
    setPackagePath(path)
    setPackageImportReport(null)
    setPackageImportResult(null)
    setPackageImportPlanId(null)
    setPackageImportDecisions({})
    setPackageImportManualValues({})
    setPackageImportSelections({})
    setPage('migration')
    setMessage('已选中离线包；请先点击“检查包与本机差异”，不会自动写入。')
  }, [])
  useEffect(() => {
    let disposed = false
    let unlistenOpened: (() => void) | undefined
    let unlistenDrop: (() => void) | undefined
    const readPendingPackage = async () => {
      try {
        const path = await invoke<string | null>('take_open_package')
        if (path) acceptPackagePath(path)
      } catch (error) {
        setMessage(`读取系统打开的迁移包失败：${String(error)}`)
      }
    }
    void readPendingPackage()
    void listen('package-opened', () => { void readPendingPackage() }).then((dispose) => {
      if (disposed) dispose()
      else unlistenOpened = dispose
    })
    void getCurrentWindow().onDragDropEvent((event) => {
      if (event.payload.type !== 'drop' || event.payload.paths.length === 0) return
      const archive = event.payload.paths.find((path) => path.toLocaleLowerCase().endsWith('.aiconfig'))
      acceptPackagePath(archive ?? event.payload.paths[0])
    }).then((dispose) => {
      if (disposed) dispose()
      else unlistenDrop = dispose
    })
    return () => {
      disposed = true
      unlistenOpened?.()
      unlistenDrop?.()
    }
  }, [acceptPackagePath])

  const choosePackageFile = async () => {
    try {
      const selected = await open({
        multiple: false,
        directory: false,
        filters: [{ name: 'AI Config package', extensions: ['aiconfig'] }],
      })
      if (typeof selected === 'string') {
        acceptPackagePath(selected)
      }
    } catch (error) {
      setMessage(`打开文件选择框失败：${String(error)}`)
    }
  }
  const choosePackageDirectory = async () => {
    try {
      const selected = await open({ multiple: false, directory: true })
      if (typeof selected === 'string') {
        acceptPackagePath(selected)
      }
    } catch (error) {
      setMessage(`打开文件夹选择框失败：${String(error)}`)
    }
  }
  const choosePackageExportDestination = async () => {
    try {
      if (packageExportFormat === 'archive') {
        const selected = await save({
          defaultPath: 'ai-config-package.aiconfig',
          filters: [{ name: 'AI Config package', extensions: ['aiconfig'] }],
        })
        if (typeof selected === 'string') {
          setPackageExportDestination(selected)
          setPackageExportReport(null)
          setPackageExportResult(null)
          setPackageExportPlanId(null)
        }
        return
      }
      const selected = await open({ multiple: false, directory: true })
      if (typeof selected === 'string') {
        const destination = await join(selected, packageExportFolderName)
        setPackageExportParent(selected)
        setPackageExportDestination(destination)
        setPackageExportReport(null)
        setPackageExportResult(null)
        setPackageExportPlanId(null)
      }
    } catch (error) {
      setMessage(`选择导出位置失败：${String(error)}`)
    }
  }
  const previewPackageImport = () => {
    if (!packagePath) return
    setPackageImportPlanId(null)
    setPackageImportResult(null)
    void requestOperation('package_import', {
      package_path: packagePath,
      decisions: packageImportDecisions,
      manual_values: packageImportManualValues,
      selections: packageImportSelections,
      apply_to_agents: packageImportApplyToAgents,
    })
  }
  const previewPackageExport = () => {
    if (!packageExportDestination) return
    setPackageExportPlanId(null)
    setPackageExportResult(null)
    void requestOperation('package_export', {
      destination: packageExportDestination,
      format: packageExportFormat,
      extension_kinds: extensionKinds,
      ...(packageExportScopeInitialized ? { selected_sources: packageExportSelectedSources } : {}),
    })
  }

  const deviceState = report?.state ?? null
  const isConfigured = report ? report.configured ?? report.status !== 'not_configured' : false
  const configStatus = deviceState?.capabilities?.config?.status
  const targets = deviceState?.managed?.targets ?? []
  const loadChecks = targets.filter((target) => target.load_check)
  const failedStatusRead = stage === '读取失败' || stage === '启动失败'
  const sessionStatus = loadChecks.length === 0
    ? report ? 'unverified' : undefined
    : loadChecks.every((target) => target.load_check === 'verified')
      ? 'verified'
      : loadChecks.some((target) => target.load_check === 'failed')
        ? 'failed'
        : loadChecks.some((target) => target.load_check === 'stale')
          ? 'stale'
          : 'unverified'
  const fileStatusLabel = report
    ? isConfigured ? labelForStatus(configStatus) : '尚未设置'
    : failedStatusRead ? '读取失败' : '读取中'
  const sessionStatusLabel = sessionStatus
    ? loadLabels[sessionStatus]
    : failedStatusRead ? '无法读取' : '读取中'

  return (
    <main className="client-layout">
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand-mark" aria-hidden="true">A</div>
          <div className="brand-copy"><strong>AI Config</strong><span>本机配置客户端</span></div>
        </div>
        <p className="nav-caption">工作区</p>
        <nav aria-label="主导航">
          {pages.map((item) => (
            <button className={`nav-item ${page === item.id ? 'selected' : ''}`} key={item.id} onClick={() => setPage(item.id)} type="button">
              <span className="nav-symbol" aria-hidden="true">{item.symbol}</span>{item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot"><span className="local-badge"><i />仅本机</span><small>状态仅在打开应用时读取</small></div>
      </aside>

      <section className="content-area">
        <header className="page-header">
          <div><p className="eyebrow">设备工作区</p><h1>{pages.find((item) => item.id === page)?.label}</h1></div>
          {page === 'overview' && <button className="subtle-button" type="button" disabled={busy} onClick={() => void requestOperation('status')}>↻ 更新状态</button>}
        </header>

        {page === 'overview' && (
          <>
            <p className="subtitle">分别查看本机文件、会话加载和跨设备传输状态。读取总览不会触发写入或联网。</p>
            <div className="status-grid">
              <StatusCard title="文件应用" value={fileStatusLabel} detail={isConfigured ? '依据本机目标文件重新核对。' : report ? '首次设置尚未完成。' : failedStatusRead ? '无法读取本机状态，请查看错误信息后重试。' : '正在读取本机配置状态。'} tone={isConfigured ? statusTone(configStatus) : failedStatusRead ? 'error' : 'neutral'} />
              <StatusCard title="会话加载" value={sessionStatusLabel} detail={sessionStatus === 'stale' ? '规则版本已变化。请在 Agent 中开启新会话并回答核验问题。' : sessionStatus === 'failed' ? '上次回答与当前规则版本不符，仍未核验通过。' : sessionStatus === 'verified' ? '记录来自真实新会话的版本问答。' : '只有真实新会话通过版本问答后才会标记已核验。'} tone={statusTone(sessionStatus)} />
              <StatusCard title="上传到服务器" value="尚未支持" detail="登录与服务器上传流程尚未实现。" tone="muted" />
              <StatusCard title="从服务器下载" value="尚未支持" detail="目标端下载与解锁流程尚未实现。" tone="muted" />
            </div>
            {targets.length > 0 && (
              <section className="panel target-panel">
                <div className="panel-heading"><div><p className="eyebrow">本机核对</p><h2>受管目标</h2></div><span className="small-note">{targets.length} 个目标</span></div>
                <ul className="target-list">
                  {targets.map((target, index) => (
                    <li key={`${target.tool ?? 'agent'}-${target.target_kind ?? index}`}>
                      <span className="tool-indicator installed" /><span className="target-name">{target.tool ?? 'Agent'} · {target.target_kind ?? '规则'}</span>
                      <span className="tool-state">{labelForStatus(target.status)}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <p className="refresh-note">{busy ? stage : message} {report?.next_step && isConfigured ? `下一步：${report.next_step}` : ''}</p>
          </>
        )}

        {page === 'agents' && (
          <FeaturePage eyebrow="本机设置" title="Agent 与规则" description={isConfigured ? '查看识别结果或登记自定义规则入口。已存在的设备配置不会被首次设置覆盖。' : '先识别 Agent，再选择要登记的实例和本机目录。确认后保存本机设备配置与规则库，不会写入 Agent 规则文件。'} action={<button className="subtle-button" type="button" disabled={busy} onClick={() => void requestOperation('setup')}>{busy ? '处理中…' : isConfigured ? '只读识别 Agent' : '重新识别'}</button>}>
            <section className="setup-guide" aria-label="配置保存与生效说明">
              <h3>保存配置后，原内容还在吗？Agent 会读取吗？</h3>
              <ol>
                <li><strong>保存本机设置：</strong>登记目录并准备规则配置库。Agent 原文件保持原样，此时共享规则还没有应用。</li>
                <li><strong>预览并应用到 Agent：</strong>共享规则写入各 Agent 的规则入口。共享文件只更新 ai-config 区块，区块外原文保留；独立规则文件遇到已有非受管内容会阻止覆盖。写入前备份，可在“历史恢复”查看并撤销。</li>
                <li><strong>开启新会话并核验：</strong>应用成功只证明文件已写入。使用本页“加载核验”获取问题，在目标 Agent 的新会话提问，再回来记录回答。</li>
              </ol>
              <p>“迁移”中选择“采纳到配置库”或“移除”会在备份后从原文件移走对应段落；希望段落留在原处，请选择“保留”。应用共享设置会更新选中的受管字段，其他字段保留。</p>
              <details>
                <summary>查看各 Agent 的规则读取入口</summary>
                <dl>
                  <dt>Codex</dt><dd>所选配置目录下的 AGENTS.md；存在 AGENTS.override.md 时优先读取它。</dd>
                  <dt>Claude Code</dt><dd>所选配置目录下的 CLAUDE.md。配置库中的模板名称不代表实际读取入口。</dd>
                  <dt>CodeBuddy Code（CLI）</dt><dd>所选配置目录下的 rules/ai-config.md；CodeBuddy IDE 的识别情况需另行核验。</dd>
                  <dt>WorkBuddy / workbuddy-ai</dt><dd>当前尝试所选配置目录下的 AGENTS.md；自动识别仍待真实会话核验。</dd>
                </dl>
                <p>路径必须对应 Agent 实际使用的配置目录；仅把文件复制到配置库不会自动生效。检测到目录也不等于 Agent 已加载规则。</p>
              </details>
            </section>
            {!isConfigured && !toolScanDone && <div className="setup-intro"><p className="pending-copy">{message}</p><button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('setup')}>{busy ? '正在识别…' : '开始首次设置'}</button></div>}
            {isConfigured && !toolScanDone && <div className="setup-intro"><p className="pending-copy">此设备已完成首次设置；识别过程只读，不会覆盖设备配置。</p><button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('setup')}>{busy ? '正在识别…' : '只读识别 Agent'}</button></div>}
            {toolScanDone && !isConfigured && <>
              <div className="setup-section-title"><strong>1. 选择 Agent 与配置目录</strong><span>仅会登记勾选项</span></div>
              <ul className="setup-tool-list">{tools.map((tool) => <li key={tool.tool}>
                <label className="setup-tool-heading"><input type="checkbox" checked={selectedTools.includes(tool.tool)} onChange={(event) => {
                  setSelectedTools((current) => event.target.checked ? [...current, tool.tool].sort() : current.filter((item) => item !== tool.tool))
                  setSetupPlanId(null)
                  setSetupReport(null)
                }} /><span className={`tool-indicator ${tool.installed ? 'installed' : ''}`} /><span className="setup-tool-name">{tool.name ?? tool.tool}</span><span className="tool-state">{tool.installed ? '已检测到' : '未检测到'}</span></label>
                <label className="path-field"><span>本机目录 <small>{tool.root_origin ? `· ${tool.root_origin}` : ''}</small></span><input aria-label={`${tool.tool} 配置目录`} value={toolRoots[tool.tool] ?? ''} onChange={(event) => {
                  setToolRoots((current) => ({ ...current, [tool.tool]: event.target.value }))
                  setSetupPlanId(null)
                  setSetupReport(null)
                }} spellCheck={false} /></label>
              </li>)}</ul>
              {tools.length === 0 && <p className="boundary-note">没有检测到 Agent 配置目录。请先安装并启动目标 Agent，或重新识别。</p>}
              <div className="setup-section-title"><strong>2. 共享规则配置库</strong><span>默认使用用户数据目录中的 .ai-sync/store，可自定义</span></div>
              <label className="path-field store-path-field"><span>本机规则配置库目录</span><input aria-label="共享规则配置库目录" placeholder="默认位于用户目录下 .ai-sync\\store" value={storePath} onChange={(event) => { setStorePath(event.target.value); setSetupPlanId(null); setSetupReport(null) }} spellCheck={false} /></label>
              <div className="setup-actions"><button className="primary-button" type="button" disabled={busy || selectedTools.length === 0} onClick={() => {
                const roots = Object.fromEntries(selectedTools.filter((tool) => toolRoots[tool]?.trim()).map((tool) => [tool, toolRoots[tool].trim()]))
                const params: Record<string, unknown> = { tools: selectedTools, tool_roots: roots }
                if (storePath.trim()) params.store_path = storePath.trim()
                setSetupPlanId(null)
                setSetupReport(null)
                void requestOperation('setup', params)
              }}>预览设置方案</button>
                {setupPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('setup', {}, setupPlanId)}>确认并保存本机设置</button>}
              </div>
              {setupReport && <div className="setup-preview" aria-live="polite">
                <div className="setup-preview-heading"><strong>{setupReport.written ? '本机设置已保存' : setupReport.ready ? '设置方案预览' : '当前无法继续'}</strong><span>{setupReport.written ? '已完成' : setupReport.ready ? '尚未写入' : '需处理'}</span></div>
                {setupReport.reason && <p>{setupReport.reason}</p>}
                {setupReport.config && <dl>
                  <dt>本机设备 ID</dt><dd>{setupReport.config.device}</dd>
                  <dt>本机状态与备份目录</dt><dd>{setupReport.config.state_dir}</dd>
                  <dt>记忆仓库（暂未启用映射）</dt><dd>{setupReport.config.memory_repo}</dd>
                  {setupReport.config.config_repo && <><dt>规则配置库</dt><dd>{setupReport.config.config_repo}</dd></>}
                  {!setupReport.config.config_repo && setupReport.store?.path && <><dt>规则配置库（待确认）</dt><dd>{setupReport.store.path}{setupReport.store.detail ? ` · ${setupReport.store.detail}` : ''}</dd></>}
                  {setupReport.config.codex && <><dt>Codex 目录</dt><dd>{setupReport.config.codex}</dd></>}
                  {setupReport.config.claude && <><dt>Claude 目录</dt><dd>{setupReport.config.claude}</dd></>}
                  {Object.entries(setupReport.config.agents ?? {}).map(([agent, config]) => <Fragment key={agent}><dt>{agent} 目录</dt><dd>{config.root}</dd></Fragment>)}
                </dl>}
              </div>}
              <p className="boundary-note">设置方案需你手动确认。此步骤不会迁入旧规则、不会改写 Agent 文件，也不会上传数据。</p>
            </>}
            {toolScanDone && isConfigured && <>
              <p className="boundary-note">首次设置已完成。检测与再次打开本页面都不会覆盖现有设备配置。</p>
              <ul className="tool-list">{tools.map((tool) => <li key={tool.tool}><span className={`tool-indicator ${tool.installed ? 'installed' : ''}`} /><span>{tool.name ?? tool.tool}</span><span className="tool-state">{tool.installed ? '已检测到' : '未检测到'}</span></li>)}</ul>
                <div className="setup-section-title"><strong>自定义 Agent 规则入口</strong><span>只声明一个 Markdown 文件</span></div>
                <div className="custom-agent-form">
                  <label><span>Agent 标识</span><input aria-label="自定义 Agent 标识" placeholder="例如 my-agent" value={customAgentId} onChange={(event) => { setCustomAgentId(event.target.value); setDeclarePlanId(null); setDeclareReport(null) }} /></label>
                  <label><span>Agent 根目录（绝对路径）</span><input aria-label="自定义 Agent 根目录" placeholder="例如 D:\\AI\\MyAgent" value={customAgentRoot} onChange={(event) => { setCustomAgentRoot(event.target.value); setDeclarePlanId(null); setDeclareReport(null) }} spellCheck={false} /></label>
                  <label><span>规则文件（相对路径）</span><input aria-label="自定义 Agent 规则文件" placeholder="例如 AGENTS.md" value={customAgentEntry} onChange={(event) => { setCustomAgentEntry(event.target.value); setDeclarePlanId(null); setDeclareReport(null) }} spellCheck={false} /></label>
                  <label><span>文件管理方式</span><select aria-label="规则文件管理方式" value={customAgentMode} onChange={(event) => { setCustomAgentMode(event.target.value); setDeclarePlanId(null); setDeclareReport(null) }}><option value="managed_block">共享文件中只管理 ai-config 区块</option><option value="owned_file">整个文件由 ai-config 管理</option></select></label>
                  <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || !customAgentId.trim() || !customAgentRoot.trim() || !customAgentEntry.trim()} onClick={() => void requestOperation('declare', { agent_id: customAgentId.trim(), root: customAgentRoot.trim(), entry: customAgentEntry.trim(), entry_mode: customAgentMode })}>预览登记</button>{declarePlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('declare', {}, declarePlanId)}>确认登记</button>}</div>
                  {declareReport && <p className="migration-summary" aria-live="polite">{declareReport.status === 'declared' ? '已登记，可在状态页查看该 Agent。' : `预览：${declareReport.agent} · ${declareReport.root_exists ? '根目录存在' : '根目录尚未创建'}。保存登记不会自动创建目录或写入规则。`}</p>}
                </div>
            </>}
            {isConfigured && <section className="panel agent-lifecycle-panel">
              <div className="panel-heading"><div><p className="eyebrow">Agent 操作</p><h2>加载核验与退出接管</h2></div><span className="small-note">只操作所选 Agent</span></div>
              {(report?.agents ?? []).length === 0 ? <p className="pending-copy">当前设备没有已登记的 Agent。</p> : <>
                <label className="rule-topic-field"><span>Agent 实例</span><select aria-label="选择 Agent 实例" value={selectedAgentId} onChange={(event) => {
                  setSelectedAgentId(event.target.value)
                  setVerifyLoadReport(null); setVerifyLoadPlanId(null); setVerifyLoadResult(null); setVerifyLoadAnswer('')
                  setDetachReport(null); setDetachPlanId(null); setDetachResult(null)
                }}>{(report?.agents ?? []).map((agent) => <option key={agent.id} value={agent.id}>{agent.name} · {agent.id}</option>)}</select></label>
                <div className="lifecycle-grid">
                  <section className="lifecycle-card">
                    <div><strong>新会话加载核验</strong><p>先在目标 Agent 开启新会话并询问下面的问题，再把 Agent 的回答粘贴回来。客户端不会替你操作 Agent。</p></div>
                    <button className="subtle-button" type="button" disabled={busy || !selectedAgentId} onClick={() => {
                      setVerifyLoadReport(null); setVerifyLoadPlanId(null); setVerifyLoadResult(null); setVerifyLoadAnswer('')
                      void requestOperation('verify_load', { agent_id: selectedAgentId })
                    }}>获取核验问题</button>
                    {verifyLoadReport?.question && <div className="setup-preview"><strong>请在新会话中询问</strong><p className="challenge-question">{verifyLoadReport.question}</p><p>{verifyLoadReport.applied ? '本机文件含当前规则版本，可继续核验。' : '当前 Agent 文件尚未应用最新版本；回答不会通过，请先应用规则。'}</p></div>}
                    {verifyLoadReport?.question && <>
                      <label className="path-field"><span>Agent 回答</span><textarea className="answer-editor" value={verifyLoadAnswer} onChange={(event) => { setVerifyLoadAnswer(event.target.value); setVerifyLoadPlanId(null); setVerifyLoadReport((current) => current?.question ? { ...current, status: 'instructions' } : current); setVerifyLoadResult(null) }} /></label>
                      <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || !verifyLoadAnswer.trim()} onClick={() => { setVerifyLoadPlanId(null); void requestOperation('verify_load', { agent_id: selectedAgentId, answer: verifyLoadAnswer, record: true }) }}>预览核验结果</button>{verifyLoadPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('verify_load', {}, verifyLoadPlanId)}>确认记录核验结果</button>}</div>
                    </>}
                    {verifyLoadReport?.status === 'passed' || verifyLoadReport?.status === 'failed' ? <p className={`lifecycle-result ${verifyLoadReport.status === 'passed' ? 'success' : 'failure'}`}>{verifyLoadReport.status === 'passed' ? '回答与当前规则版本一致；确认后才写入核验记录。' : '回答没有通过核验；确认后会记录为未通过。'}</p> : null}
                    {verifyLoadResult && <p className={`lifecycle-result ${verifyLoadResult.passed ? 'success' : 'failure'}`}>{verifyLoadResult.passed ? '新会话已核验。' : `核验未通过：${verifyLoadResult.reason ?? '版本不匹配'}。`}</p>}
                  </section>
                  <section className="lifecycle-card">
                    <div><strong>退出此 Agent 的接管</strong><p>会移除 ai-config 管理的规则区块和登记。勾选后也尝试恢复迁入前原件；如发现原件后来被改动或备份异常，预览会列出冲突并跳过恢复。</p></div>
                    <label className="inline-check"><input type="checkbox" checked={restoreOriginal} onChange={(event) => { setRestoreOriginal(event.target.checked); setDetachReport(null); setDetachPlanId(null); setDetachResult(null) }} /><span>同时恢复迁入前原件（如安全）</span></label>
                    <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || !selectedAgentId} onClick={() => { setDetachPlanId(null); setDetachReport(null); setDetachResult(null); void requestOperation('detach', { agent_id: selectedAgentId, restore_original: restoreOriginal }) }}>预览退出接管</button>{detachPlanId && <button className="primary-button danger-button" type="button" disabled={busy} onClick={() => void requestOperation('detach', {}, detachPlanId)}>确认退出接管</button>}</div>
                    {detachReport && <div className="setup-preview"><div className="setup-preview-heading"><strong>退出接管预览</strong><span>尚未修改文件</span></div><ul className="rule-change-list">{(detachReport.files ?? []).map((file) => <li key={file.path}><span>{file.action === 'remove_block' ? '移除受管区块' : file.action}</span><code>{file.path}</code></li>)}{(detachReport.restored ?? []).map((path) => <li key={`restore-${path}`}><span>恢复迁入前原件</span><code>{path}</code></li>)}</ul>{!(detachReport.files ?? []).length && !(detachReport.restored ?? []).length && <p>没有可移除的受管规则文件；确认后只会解除登记。</p>}{(detachReport.conflicts ?? []).map((conflict) => <p className="boundary-note" key={`${conflict.path}-${conflict.reason}`}>{conflict.reason} · {conflict.path}</p>)}</div>}
                    {detachResult && <div className="setup-preview"><strong>已退出接管</strong>{detachResult.backup && <p>事务备份：{detachResult.backup}</p>}{(detachResult.conflicts ?? []).map((conflict) => <p className="boundary-note" key={`${conflict.path}-${conflict.reason}`}>{conflict.reason} · {conflict.path}</p>)}</div>}
                  </section>
                </div>
              </>}
            </section>}
            {isConfigured && <section className="panel rule-editor-panel">
              <div className="panel-heading"><div><p className="eyebrow">共享内容</p><h2>规则编辑与应用</h2></div><button className="subtle-button" type="button" disabled={busy} onClick={() => void requestOperation('rule_library')}>{busy ? '读取中…' : ruleLibraryLoaded ? '重新读取规则库' : '读取规则库'}</button></div>
              <p className="feature-description">保存会修改本机共享规则库；只有另行预览并应用，才会写入 Agent 规则文件。这里不会发布 Git 或上传服务器。</p>
              {ruleLibraryLoaded && <>
                <label className="rule-topic-field"><span>规则主题</span><select value={selectedRuleTopic} onChange={(event) => {
                  const topic = event.target.value
                  ruleTopicRef.current = topic
                  setSelectedRuleTopic(topic)
                  setRuleDraft(ruleFiles.find((file) => file.topic === topic)?.content ?? '')
                  setRuleSecretReplacement(false)
                  setSaveRulePlanId(null)
                  setSaveRuleReport(null)
                  setSaveRuleResult(null)
                }}>{ruleFiles.map((file) => <option key={file.topic} value={file.topic}>{ruleTopicLabels[file.topic] ?? file.topic}</option>)}</select></label>
                {(() => {
                  const currentRule = ruleFiles.find((file) => file.topic === selectedRuleTopic)
                  const secretBlocked = currentRule?.status === 'blocked_secret'
                  const editable = currentRule?.status === 'ready' || (secretBlocked && ruleSecretReplacement)
                  const dirty = editable && (ruleSecretReplacement || currentRule?.content !== ruleDraft)
                  return <>
                    {!editable && <div className="rule-blocked-note"><p className="boundary-note">此规则文件无法安全读取：{secretBlocked ? '检测到疑似凭据，原内容已隐藏。' : currentRule?.status === 'blocked_symlink' ? '规则入口是符号链接，已阻止编辑。' : currentRule?.status === 'too_large' ? '文件超过 256 KiB，当前编辑器不打开。' : '文件无法读取。'}</p>{secretBlocked && <button className="subtle-button" type="button" disabled={busy} onClick={() => { setRuleSecretReplacement(true); setRuleDraft(''); setSaveRulePlanId(null); setSaveRuleReport(null); setSaveRuleResult(null) }}>新建安全内容并整体替换</button>}</div>}
                    {secretBlocked && editable && <p className="boundary-note">原内容不会显示。保存将整体替换该规则文件，并由本机事务先备份原件。</p>}
                    {editable && <>
                      <textarea className="rule-editor" aria-label={`${ruleTopicLabels[selectedRuleTopic] ?? selectedRuleTopic} 规则内容`} value={ruleDraft} onChange={(event) => { setRuleDraft(event.target.value); setSaveRulePlanId(null); setSaveRuleReport(null); setSaveRuleResult(null); setApplyRulesPlanId(null); setApplyRulesReport(null); setApplyRulesResult(null) }} spellCheck={false} />
                      <div className="setup-actions">
                        <button className="subtle-button" type="button" disabled={busy || !dirty} onClick={() => void requestOperation('save_rule', { topic: selectedRuleTopic, content: ruleDraft })}>预览保存到规则库</button>
                        {saveRulePlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('save_rule', {}, saveRulePlanId)}>确认保存规则</button>}
                        <button className="subtle-button" type="button" disabled={busy || dirty || !ruleLibraryLoaded} onClick={() => void requestOperation('rules')}>预览应用到 Agent</button>
                        {applyRulesPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('rules', {}, applyRulesPlanId)}>确认应用规则</button>}
                      </div>
                    </>}
                    {(saveRuleReport || saveRuleResult) && <div className="setup-preview" aria-live="polite"><div className="setup-preview-heading"><strong>{saveRuleResult?.written ? '已保存到共享规则库' : saveRuleReport?.status === 'unchanged' ? '内容没有变化' : '保存预览'}</strong><span>{saveRuleResult?.written ? '仅本机规则库已更新' : '尚未保存'}</span></div>{(saveRuleReport ?? saveRuleResult)?.target && <dl><dt>目标</dt><dd>{(saveRuleReport ?? saveRuleResult)?.target}</dd><dt>内容大小</dt><dd>{(saveRuleReport ?? saveRuleResult)?.bytes} 字节</dd>{saveRuleResult?.backup && <><dt>备份</dt><dd>{saveRuleResult.backup}</dd></>}</dl>}</div>}
                    {(applyRulesReport || applyRulesResult) && <div className="setup-preview" aria-live="polite"><div className="setup-preview-heading"><strong>{applyRulesResult ? 'Agent 规则应用已完成' : 'Agent 应用预览'}</strong><span>{applyRulesResult ? `${typeof applyRulesResult.changes === 'number' ? applyRulesResult.changes : 0} 项变更` : `${applyRulesReport?.count ?? 0} 个目标`}</span></div><ul className="rule-change-list">{(Array.isArray(applyRulesReport?.changes) ? applyRulesReport.changes : []).map((change) => <li key={change.path}><span>{change.action === 'write' ? '写入' : '删除'} · {change.size} 字节</span><code>{change.path}</code></li>)}</ul></div>}
                    <section className="diff-panel">
                      <div className="panel-heading"><div><p className="eyebrow">受管设置与规则块</p><h2>本机差异</h2></div><button className="subtle-button" type="button" disabled={busy} onClick={() => { setDiffChoice(''); setDiffPlanId(null); setDiffPreview(null); setDiffResult(null); void requestOperation('diff') }}>{busy ? '读取中…' : diffReport ? '重新读取差异' : '读取差异'}</button></div>
                      <p className="feature-description">差异值会遮蔽疑似敏感内容。一次确认会对下方所有兼容项目应用同一种处理方式。</p>
                      {diffReport && (() => {
                        const items = diffReport.diffs ?? []
                        const options = ['share', 'local', 'restore'].filter((choice) => items.length > 0 && items.every((item) => item.choices.includes(choice)))
                        return <>
                          {items.length === 0 ? <p className="pending-copy">目前没有受管设置或规则块差异。</p> : <ul className="diff-list">{items.map((item) => <li key={`${item.tool}-${item.field}`}><div><strong>{item.tool} · {item.label}</strong><span>{item.field === 'rules' ? '规则区块' : item.source === 'local' ? '当前值来自本机覆盖' : item.source === 'template' ? '当前值来自共享规则' : item.source}</span></div><dl><dt>共享值</dt><dd>{displayConfigValue(item.shared_value)}</dd><dt>本机值</dt><dd>{displayConfigValue(item.local_value)}</dd></dl></li>)}</ul>}
                          {items.length > 0 && <div className="diff-controls"><label><span>处理方式（应用到下方所有项目）</span><select value={diffChoice} onChange={(event) => { setDiffChoice(event.target.value); setDiffPlanId(null); setDiffPreview(null); setDiffResult(null) }}><option value="">请选择…</option>{options.map((choice) => <option key={choice} value={choice}>{diffChoiceLabels[choice]}</option>)}</select></label><button className="subtle-button" type="button" disabled={busy || !diffChoice || !options.includes(diffChoice)} onClick={() => void requestOperation('diff', { choice: diffChoice })}>预览处理方式</button>{diffPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('diff', {}, diffPlanId)}>确认处理差异</button>}</div>}
                          {(diffPreview || diffResult) && <div className="setup-preview" aria-live="polite"><div className="setup-preview-heading"><strong>{diffResult ? '差异选择已保存' : '差异处理预览'}</strong><span>{diffResult ? '仅保存归属选择' : '尚未写入'}</span></div><ul className="rule-change-list">{(diffPreview?.outcomes ?? diffResult?.outcomes ?? []).map((item, index) => <li key={`${item.tool}-${item.field}-${index}`}><span>{item.choice ? diffChoiceLabels[item.choice] ?? item.choice : ''} · {item.effect}</span>{item.target && <code>{item.target}</code>}{item.backup && <code>备份：{item.backup}</code>}</li>)}</ul></div>}
                          {diffResult && <div className="diff-settings-apply"><p>需要把当前共享设置写入 Agent 时，再单独预览并应用。保存差异选择本身不会改 Agent 文件。</p><div className="setup-actions"><button className="subtle-button" type="button" disabled={busy} onClick={() => void requestOperation('config')}>预览应用共享设置</button>{settingsPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('config', {}, settingsPlanId)}>确认应用设置</button>}</div>{(settingsReport || settingsResult) && <div className="setup-preview"><div className="setup-preview-heading"><strong>{settingsResult ? '共享设置已应用' : '共享设置应用预览'}</strong><span>{settingsResult ? `${typeof settingsResult.changes === 'number' ? settingsResult.changes : 0} 项变更` : `${settingsReport?.count ?? 0} 个目标`}</span></div><ul className="rule-change-list">{(Array.isArray(settingsReport?.changes) ? settingsReport.changes : []).map((change) => <li key={change.path}><span>{change.action === 'write' ? '写入' : '删除'} · {change.size} 字节</span><code>{change.path}</code></li>)}</ul></div>}</div>}
                        </>
                      })()}
                    </section>
                  </>
                })()}
              </>}
              {ruleLibraryLoaded && <p className="boundary-note">{busy ? stage : message}</p>}
            </section>}
          </FeaturePage>
        )}

        {page === 'migration' && <FeaturePage eyebrow="设备迁移" title="离线包与已有规则迁移" description="通过本机离线包在设备间搬运受支持的共享规则和设置。先检查范围与本机差异，再确认导入；文件落盘状态和 Agent 新会话加载状态分开显示。" action={<button className="subtle-button" type="button" disabled={busy || !isConfigured} onClick={() => void requestOperation('migrate')}>{busy ? '正在检查…' : '读取旧规则迁入项'}</button>}>
          <section className="panel package-panel" aria-labelledby="package-export-title">
            <ExtensionPanel busy={busy} reply={advancedReply} request={(operation, params, plan) => { void requestOperation(operation, params, plan) }} />
            <button className="subtle-button" disabled={busy} type="button" onClick={() => void requestOperation('package_capabilities')}>读取本机扩展适配能力</button>
            <fieldset className="package-scope"><legend>扩展导出范围（默认关闭）</legend>{[['skills', 'skills 文本与资源（实机识别待验收）'], ['mcp', 'Codex 非敏感 MCP（连接未核验）'], ['memory', '可移植记忆快照（Codex 仅参考）'], ['handoffs', '项目交接（源码依赖另行取得）']].map(([kind, label]) => <label className="inline-check" key={kind}><input disabled={busy || !capabilityKinds.includes(kind)} type="checkbox" checked={extensionKinds.includes(kind)} onChange={event => { setExtensionKinds(current => event.target.checked ? [...current, kind] : current.filter(value => value !== kind)); setPackageExportScopeInitialized(false); setPackageExportPlanId(null); setPackageExportReport(null) }} />{label}</label>)}</fieldset>
            <div className="panel-heading"><div><p className="eyebrow">离线迁移包</p><h2 id="package-export-title">从本机导出</h2></div></div>
            <p className="feature-description">生成本机文件或文件夹，供你自行复制到另一台设备。你可以逐项选择本次打包范围；只采集明确支持的共享规则、Agent 声明与所选非敏感设置，扩展选项仅纳入预先明确采集的 skills、非敏感 MCP、可移植快照与交接；认证、会话、缓存和设备绝对路径始终排除，也不会上传。</p>
            <div className="package-form-row">
              <label className="package-field"><span>包格式</span><select value={packageExportFormat} disabled={busy} onChange={(event) => { const value = event.target.value as 'archive' | 'directory'; setPackageExportFormat(value); setPackageExportDestination(''); setPackageExportReport(null); setPackageExportResult(null); setPackageExportPlanId(null) }}><option value="archive">单文件 .aiconfig</option><option value="directory">自包含文件夹</option></select></label>
              {packageExportFormat === 'directory' && <label className="package-field"><span>新文件夹名称</span><input value={packageExportFolderName} disabled={busy} onChange={(event) => { const name = event.target.value; setPackageExportFolderName(name); setPackageExportPlanId(null); setPackageExportReport(null); if (packageExportParent && name.trim()) void join(packageExportParent, name.trim()).then(setPackageExportDestination) }} /></label>}
              <button className="subtle-button" type="button" disabled={busy} onClick={() => void choosePackageExportDestination()}>{packageExportFormat === 'archive' ? '选择保存文件' : '选择保存位置'}</button>
            </div>
            {packageExportDestination && <code className="package-path">{packageExportDestination}</code>}
            <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || !isConfigured || !packageExportDestination} onClick={previewPackageExport}>检查导出范围</button>{packageExportPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('package_export', {}, packageExportPlanId)}>确认生成离线包</button>}</div>
            {packageExportReport && <div className="setup-preview package-preview" aria-live="polite"><div className="setup-preview-heading"><strong>{packageExportReport.can_apply ? '导出预览' : '暂不能导出'}</strong><span>{packageExportReport.entry_count ?? 0} 个条目 · {packageExportReport.exclusion_count ?? 0} 个排除项</span></div>{packageExportReport.reason && <p className="diagnostic-warning">{packageExportReport.reason}</p>}<p>内容版本：<code>{packageExportReport.content_id ?? '未生成'}</code>。目标尚未写入。</p>{!!packageExportReport.scope_items?.length && <details open><summary>选择打包范围（{packageExportReport.entry_count ?? 0} 项可导出）</summary><ul className="package-scope-list">{packageExportReport.scope_items.map((item) => <li key={`${item.logical_source}-${item.status}`}><label><input type="checkbox" disabled={busy || !item.selectable} checked={packageExportSelectedSources.includes(item.logical_source)} onChange={(event) => { setPackageExportSelectedSources((current) => event.target.checked ? [...current, item.logical_source] : current.filter((source) => source !== item.logical_source)); setPackageExportPlanId(null) }} /><span><strong>{item.logical_source}</strong><small>{item.status === 'ready' ? item.data_type : `${item.status} · ${item.detail ?? item.data_type}`}</small></span></label></li>)}</ul><p className="small-note">改动选择后请重新点击“检查导出范围”。未选项目会在包中列作排除，不会要求接收设备删除它们。</p></details>}{!!packageExportReport.exclusions?.length && <details><summary>查看受保护排除项（{packageExportReport.exclusions.length}）</summary><ul className="package-issue-list">{packageExportReport.exclusions.map((item) => <li key={`${item.logical_source}-${item.category}`}>{item.logical_source} · {item.category}</li>)}</ul></details>}{!!packageExportReport.review_required?.length && <details open><summary>需要人工检查（{packageExportReport.review_required.length}）</summary><ul className="package-issue-list">{packageExportReport.review_required.map((item) => <li key={`${item.logical_source}-${item.category}`}>{item.logical_source} · {item.detail ?? item.category}{item.line_numbers?.length ? ` · 第 ${item.line_numbers.join('、')} 行` : ''}</li>)}</ul></details>}{!!packageExportReport.unsupported?.length && <details open><summary>暂不支持（{packageExportReport.unsupported.length}）</summary><ul className="package-issue-list">{packageExportReport.unsupported.map((item) => <li key={`${item.logical_source}-${item.category}`}>{item.logical_source} · {item.detail ?? item.category}</li>)}</ul></details>}{packageExportResult && <p className="diagnostic-ok">文件已生成：{packageExportResult.destination_name} · {packageExportResult.object_count ?? 0} 个内容对象。你需要自行把包复制到另一台设备。</p>}</div>}
            {!packageExportReport && packageExportResult && <p className="diagnostic-ok">已生成 {packageExportResult.destination_name}；包保存在本机所选位置，未上传服务器。</p>}
          </section>

          <section className="panel package-panel" aria-labelledby="package-import-title">
            <div className="panel-heading"><div><p className="eyebrow">接收离线包</p><h2 id="package-import-title">检查并导入到本机</h2></div></div>
            <p className="feature-description">选择文件包或包文件夹，也可以把它拖进窗口，或在系统文件管理器双击 .aiconfig 文件。所有入口都只选中并进入预览，不会直接改动本机配置。</p>
            <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy} onClick={() => void choosePackageFile()}>打开 .aiconfig 文件</button><button className="subtle-button" type="button" disabled={busy} onClick={() => void choosePackageDirectory()}>打开包文件夹</button></div>
            {packagePath && <code className="package-path">{packagePath}</code>}
            {!!packageImportReport?.mapping_details?.length && <details open><summary>目标与依赖范围</summary><ul>{packageImportReport.mapping_details.map((item, index) => <li key={index}>{item.logical_source} · {item.status} · {item.detail}</li>)}</ul></details>}
            <label className="inline-check package-agent-check"><input type="checkbox" checked={packageImportApplyToAgents} disabled={busy} onChange={(event) => { setPackageImportApplyToAgents(event.target.checked); setPackageImportPlanId(null); setPackageImportReport(null) }} /><span>同时预览并应用到已映射的 Agent 设置与规则区块</span></label>
            <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || !packagePath || !isConfigured} onClick={previewPackageImport}>检查包与本机差异</button>{packageImportPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('package_import', {}, packageImportPlanId)}>确认导入并备份本机文件</button>}</div>
            {packageImportReport && <div className="setup-preview package-preview" aria-live="polite"><div className="setup-preview-heading"><strong>{packageImportReport.status === 'unchanged' ? '包与本机内容一致' : packageImportReport.can_apply ? '导入预览已就绪' : '需要完成选择'}</strong><span>{packageImportReport.changed_file_count ?? 0} 个文件将变化</span></div><p>包：{packageImportReport.source_name ?? packagePath.split(/[\\/]/).pop()} · 内容版本：<code>{packageImportReport.content_id ?? '未知'}</code></p><p>共同基线：{packageImportReport.conflicts?.baseline_status === 'verified' ? '已验证，可进行三方比较' : '没有可验证的共同基线；差异需明确选择'}。预览不会写入文件。</p>
              {!!packageImportReport.agent_selections?.length && <div><h3>选择接收端 Agent</h3><ul className="package-issue-list">{packageImportReport.agent_selections.map((item) => <li key={item.key}><span>{item.logical_source}</span><select aria-label={`${item.key} 接收端 Agent`} value={packageImportSelections[item.key] ?? ''} disabled={busy} onChange={(event) => { setPackageImportSelections((current) => ({ ...current, [item.key]: event.target.value })); setPackageImportPlanId(null) }}><option value="">请选择本机实例…</option>{item.candidates.map((candidate) => <option key={candidate.instance_id} value={candidate.instance_id}>{candidate.instance_id} · {candidate.profile_id} · {candidate.installed ? '已安装' : '目录未就绪'}{candidate.configured ? ' · 已登记' : ''}</option>)}</select></li>)}</ul></div>}
              {!!packageImportReport.conflicts?.rows?.length && <div><h3>包与本机的差异</h3><ul className="package-conflict-list">{packageImportReport.conflicts.rows.map((row) => {
                const choice = packageImportDecisions[row.key] ?? row.decision ?? ''
                return <li key={row.key}><div className="package-conflict-heading"><strong>{row.scope === 'agent' || row.scope === 'agent-rules' ? 'Agent 目标' : '本机配置库'}</strong><span>{row.status}</span></div><code>{row.logical_source}{row.instance_id ? ` · ${row.instance_id}` : ''}</code><p>{row.detail}</p>{row.choices.length > 0 && <label className="package-field"><span>本条处理决定</span><select value={choice} disabled={busy} onChange={(event) => { setPackageImportDecisions((current) => { const updated = { ...current }; if (event.target.value) updated[row.key] = event.target.value; else delete updated[row.key]; return updated }); setPackageImportPlanId(null) }}><option value="">明确选择…</option>{row.choices.map((value) => <option key={value} value={value}>{value === 'keep_local' ? '保留本机内容' : value === 'use_package' ? '采用迁移包内容' : '手动合并规则文本'}</option>)}</select></label>}{choice === 'manual_merge' && <label className="package-field"><span>合并后的规则文本</span><textarea className="answer-editor package-merge-editor" value={packageImportManualValues[row.logical_source] ?? ''} disabled={busy} onChange={(event) => { setPackageImportManualValues((current) => ({ ...current, [row.logical_source]: event.target.value })); setPackageImportPlanId(null) }} /></label>}</li>
              })}</ul></div>}
              <p className="boundary-note">{packageImportReport.conflicts?.rows?.length ?? 0} 条差异；文件只有在所有必要选择完成后才可应用。导入完成只证明本机文件已写入并回读一致，不代表 Agent 已在新会话加载。</p>
            </div>}
            {packageImportResult && <div className="setup-preview" aria-live="polite"><div className="setup-preview-heading"><strong>{packageImportResult.status === 'unchanged' ? '本机内容已一致' : '本机文件已应用并回读核验'}</strong><span>{packageImportResult.changed_file_count ?? 0} 个文件变化</span></div><p>操作已记录到本机历史，可在“历史与恢复”预览撤销。需要在 Agent 中开启新会话并完成加载核验，才能确认新会话使用了这些规则。</p></div>}
          </section>

          <p className="boundary-note">离线包只由本客户端在本机读写；设备之间的传输由你自行复制文件完成。云端登录、上传下载、加密托管和服务器版本处理尚未接入。</p>
          {!isConfigured && <p className="pending-copy">请先在“Agent 与规则”完成本机首次设置。离线导入和导出都需要已登记的本机配置库。</p>}
          {!isConfigured && <p className="pending-copy">请先在“Agent 与规则”完成本机首次设置，再回来检查迁入项。</p>}
          {migrationReport && <>
            <p className="migration-summary">{message}</p>
            {migrationApplyResult && <div className="setup-preview" aria-live="polite"><div className="setup-preview-heading"><strong>{migrationApplyResult.status === 'applied' ? '迁入操作已完成' : '没有文件改动'}</strong><span>{migrationApplyResult.changes ?? 0} 项改动</span></div>{migrationApplyResult.backup && <dl><dt>原文件备份</dt><dd>{migrationApplyResult.backup}</dd></dl>}</div>}
            {(migrationReport.items ?? []).length === 0 && !(migrationReport.blocked ?? []).length && <p className="pending-copy">没有需要处理的旧规则。</p>}
            <ul className="migration-list">{migrationReport.items?.map((item) => {
              const choice = migrationChoices[item.id] ?? ''
              const selected = migrationReport.selected?.[item.id]
              return <li key={item.id}>
                <div className="migration-item-heading"><div><strong>{item.instance} · {item.path ?? 'Agent 登记'}</strong><span>{item.kind === 'duplicate' ? '与共享规则重复' : item.kind === 'register' ? '发现未登记 Agent' : `${item.unique_lines ?? 0} 行独有内容`}</span></div><small>{item.lines ?? 0} 行</small></div>
                {item.shared_with && item.shared_with.length > 0 && <p className="migration-origin">相同内容也出现在：{item.shared_with.join('、')}</p>}
                {!!item.unique_preview?.length && <div className="migration-excerpt">{item.unique_preview.map((line) => <pre key={line.line_number}><span>第 {line.line_number} 行</span>{line.text}</pre>)}{(item.unique_lines ?? 0) > item.unique_preview.length && <small>另有 {(item.unique_lines ?? 0) - item.unique_preview.length} 行未展开</small>}</div>}
                <div className="migration-controls"><label><span>处理方式</span><select aria-label={`${item.instance} 处理方式`} value={choice} onChange={(event) => { setMigrationChoices((current) => ({ ...current, [item.id]: event.target.value })); setMigrationPlanId(null) }}><option value="">请选择…</option>{item.choices.map((value) => <option key={value} value={value}>{migrationChoiceLabels[value] ?? value}</option>)}</select></label><button className="subtle-button" type="button" disabled={busy || !choice} onClick={() => void requestOperation('migrate', { item: item.id, choice })}>预览此项</button>{selected && <span className="migration-selected">已选择：{migrationChoiceLabels[selected] ?? selected}</span>}{migrationPlanId && selected === choice && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('migrate', {}, migrationPlanId)}>确认执行</button>}</div>
              </li>
            })}</ul>
            {!!migrationReport.blocked?.length && <details className="migration-blocked"><summary>{migrationReport.blocked.length} 项已跳过（内容未读取）</summary><ul>{migrationReport.blocked.map((item, index) => <li key={`${item.instance}-${item.path}-${index}`}>{item.instance} · {item.path}：{item.reason === 'blocked_secret' ? '疑似包含凭据' : '无法安全读取'}</li>)}</ul></details>}
          </>}
          <p className="boundary-note">迁入只处理你选中的条目。未选内容保留在原处；“移除”会先保存备份。迁入完成后可在 Agent 页面继续编辑与应用共享规则。</p>
        </FeaturePage>}
        {page === 'cloud' && <CloudPanel busy={busy} reply={advancedReply} appliedContentId={packageImportResult?.content_id} request={(operation, params, plan) => { void requestOperation(operation, params, plan) }} openPackage={acceptPackagePath} />}
        {page === 'history' && <FeaturePage eyebrow="本机操作" title="历史与恢复" description="查看本机已提交的配置操作，先预览再撤销；启动后会只读检查未完成事务。这里不显示规则正文。" action={<button className="subtle-button" type="button" disabled={busy || !isConfigured} onClick={() => void requestOperation('undo', { list_only: true })}>读取操作历史</button>}>
          {!isConfigured && <p className="pending-copy">完成本机首次设置后，客户端才有可检查的事务和操作历史。</p>}
          {undoReport?.operations && <>
            {undoReport.operations.length === 0 ? <p className="pending-copy">没有可撤销的已完成配置操作。</p> : <ul className="history-operation-list">{undoReport.operations.map((operation) => <li key={operation.operation_id ?? operation.index}><div><strong>{operation.statement}</strong><span>{operation.created_at?.replace('T', ' ').slice(0, 19) ?? '时间未知'} · {operation.status === 'COMMITTED' ? '已完成' : '状态未知'} · {operation.change_count ?? 0} 项 · {(operation.tools ?? []).join('、') || '本机配置'}</span>{operation.backup && <small>备份：{operation.backup}</small>}<ul className="history-targets">{(operation.targets ?? []).map((target) => <li key={`${target.path}-${target.action}`}>{target.action === 'delete' ? '删除' : '写入'} · {target.path}</li>)}</ul></div><button className="subtle-button" type="button" disabled={busy || !operation.operation_id} onClick={() => { setUndoPlanId(null); setUndoResult(null); void requestOperation('undo', { operation_id: operation.operation_id }) }}>预览撤销</button></li>)}</ul>}
          </>}
          {undoReport?.operation && <div className="setup-preview"><div className="setup-preview-heading"><strong>撤销预览</strong><span>尚未写入 · {undoReport.changes ?? 0} 项</span></div><p>{undoReport.operation.statement}</p><ul className="rule-change-list">{(undoReport.paths ?? []).map((path) => <li key={path}><span>将恢复操作前内容</span><code>{path}</code></li>)}</ul><p>{undoReport.note}</p>{undoPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('undo', {}, undoPlanId)}>确认撤销并恢复文件</button>}</div>}
          {undoResult && <div className="setup-preview"><strong>本机恢复已完成</strong><p>{undoResult.note}</p><p>恢复影响 {undoResult.changes ?? 0} 项；如当前目标在操作后又有改动，核心会拒绝覆盖。</p></div>}
          <section className="panel diagnostic-panel">
            <div className="panel-heading"><div><p className="eyebrow">启动检查</p><h2>未完成事务</h2></div><button className="subtle-button" type="button" disabled={busy || !isConfigured} onClick={() => void requestOperation('doctor')}>重新检查</button></div>
            {!doctorReport && <p className="pending-copy">配置完成后，启动检查会在后台只读扫描未完成事务。</p>}
            {doctorReport && <>
              <p className={doctorReport.ok ? 'diagnostic-ok' : 'diagnostic-alert'}>{doctorReport.ok ? '未发现阻止继续操作的问题。' : `发现 ${(doctorReport.issues ?? []).length} 项需要处理的问题。`}</p>
              {(doctorReport.checks?.transactions ?? []).length > 0 && <ul className="transaction-list">{doctorReport.checks?.transactions?.map((item, index) => <li key={`${item.operation_id}-${index}`}><code>{item.operation_id ?? '事务'}</code><span>{item.status}</span></li>)}</ul>}
              {(doctorReport.issues ?? []).map((issue, index) => <p className="diagnostic-alert" key={`issue-${index}`}>{issue}</p>)}
              {(doctorReport.warnings ?? []).map((warning, index) => <p className="diagnostic-warning" key={`warning-${index}`}>{warning}</p>)}
              {(() => {
                const pending = (doctorReport.checks?.transactions ?? []).filter((item) => ['PREPARED', 'APPLYING', 'INTERRUPTED', 'ROLLBACK_REQUIRED'].includes(item.status ?? ''))
                const invalid = (doctorReport.checks?.transactions ?? []).some((item) => item.status === 'INVALID_JOURNAL')
                return pending.length > 0 ? <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || invalid} onClick={() => { setDoctorPlanId(null); void requestOperation('doctor', { recover: true }) }}>预览回滚未完成事务</button>{doctorPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('doctor', {}, doctorPlanId)}>确认恢复</button>}{invalid && <span className="diagnostic-alert">事务日志损坏，不能自动恢复；请保留现场并按诊断提示处理。</span>}</div> : null
              })()}
            </>}
          </section>
          <p className="boundary-note">撤销只恢复本机备份中的受管文件，不会发布或覆盖远端共享内容。若目标在操作后又被修改，或备份校验失败，恢复会停止并显示错误。</p>
        </FeaturePage>}
        {page === 'extras' && <div className="extras-stack">
          <LocalToolsPanel busy={busy} reply={advancedReply} request={(operation, params, plan) => { void requestOperation(operation, params, plan) }} />
          <FeaturePage eyebrow="可选能力" title="记忆来源与映射" description="记忆同步是可选项，不影响规则配置。先盘点来源，再明确选择要映射的内容。Codex 仅形成参考快照，不会写回原生记忆数据库。" action={<button className="subtle-button" type="button" disabled={busy || !isConfigured} onClick={() => { setMemorySetupPlanId(null); setMemorySetupResult(null); void requestOperation('memory_setup') }}>读取记忆来源</button>}>
            {!isConfigured && <p className="pending-copy">先完成本机首次设置。你可以不启用记忆，照常使用规则同步。</p>}
            {memorySetupReport && <>
              <p className="boundary-note">{(memorySetupReport.mappings ?? []).length} 个记忆映射当前处于启用状态。关闭映射不会删除源文件。</p>
              {(memorySetupReport.sources ?? []).length === 0 ? <p className="pending-copy">未发现可用记忆来源；配置同步仍可独立使用。</p> : <ul className="source-list">{(memorySetupReport.sources ?? []).map((source) => {
                const selected = memorySelectionIds.includes(source.source_id)
                const mappingId = memorySelectionProjects[source.source_id] ?? source.suggested_id ?? ''
                return <li key={source.source_id}>
                  <label className="source-select"><input type="checkbox" disabled={!source.enableable} checked={selected} onChange={(event) => {
                    setMemorySelectionIds((current) => event.target.checked ? [...current, source.source_id] : current.filter((id) => id !== source.source_id))
                    setMemorySetupReport((current) => current ? { ...current, selection_preview: undefined } : current)
                    setMemorySetupPlanId(null); setMemorySetupResult(null)
                  }} /><span><strong>{source.tool} · {source.source_id}</strong><small>{source.status} · {source.file_count ?? 0} 个文件 · {source.capability}</small></span></label>
                  {source.path && <code>{source.path}</code>}
                  {source.enableable && selected && <label className="project-id-field"><span>项目标识（共享逻辑名）</span><input value={mappingId} onChange={(event) => { setMemorySelectionProjects((current) => ({ ...current, [source.source_id]: event.target.value })); setMemorySetupReport((current) => current ? { ...current, selection_preview: undefined } : current); setMemorySetupPlanId(null); setMemorySetupResult(null) }} /></label>}
                  {!source.enableable && <p className="diagnostic-alert">暂不可启用：{source.reason ?? '来源状态需要先处理。未展示文件内容。'}</p>}
                </li>
              })}</ul>}
              <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || memorySelectionIds.length === 0} onClick={() => {
                const selections = (memorySetupReport?.sources ?? []).filter((source) => memorySelectionIds.includes(source.source_id) && source.enableable && source.path).map((source) => ({ id: memorySelectionProjects[source.source_id] ?? source.suggested_id ?? '', path: source.path }))
                setMemorySetupPlanId(null); setMemorySetupResult(null)
                void requestOperation('memory_setup', { selections })
              }}>预览启用所选映射</button>{memorySetupPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('memory_setup', {}, memorySetupPlanId)}>{memorySetupReport?.removed_mappings ? '确认关闭记忆映射' : '确认保存记忆映射'}</button>}<button className="subtle-button" type="button" disabled={busy || (memorySetupReport.mappings ?? []).length === 0} onClick={() => { setMemorySetupPlanId(null); setMemorySetupResult(null); void requestOperation('memory_setup', { disable: true }) }}>预览关闭记忆</button></div>
              {memorySetupReport.selection_preview && <div className="setup-preview"><strong>{memorySetupReport.selection_preview.status === 'ready' ? '映射预览' : '不能启用这些映射'}</strong><ul className="rule-change-list">{(memorySetupReport.selection_preview.mappings ?? []).map((mapping) => <li key={mapping.id}><span>{mapping.id}</span><code>{mapping.path}</code></li>)}{(memorySetupReport.selection_preview.rejected ?? []).map((item, index) => <li key={`${item.path}-${index}`}><span>阻止：{item.reason}</span><code>{item.path}</code></li>)}</ul></div>}
              {(memorySetupResult || memorySetupReport.removed_mappings) && <div className="setup-preview"><strong>{memorySetupResult?.written ? '记忆设置已保存' : '关闭预览'}</strong><p>{memorySetupResult?.note ?? memorySetupReport.note}</p>{memorySetupResult?.backup && <small>设备配置备份：{memorySetupResult.backup}</small>}</div>}
            </>}
          </FeaturePage>

          <FeaturePage eyebrow="来源盘点" title="本机记忆与候选目录" description="盘点只读取文件清单和安全状态，不把记忆正文写入报告。保存报告会在本机状态目录创建一份盘点记录，不会上传。" action={<button className="subtle-button" type="button" disabled={busy || !isConfigured} onClick={() => { setInventoryPlanId(null); setInventoryResult(null); void requestOperation('inventory') }}>重新盘点</button>}>
            {inventoryReport && <><p className="migration-summary">共 {inventoryReport.summary?.total ?? 0} 项；可读 {inventoryReport.summary?.ready ?? 0} 项；待映射 {inventoryReport.summary?.pending_mapping ?? 0} 项；不可用或需处理 {inventoryReport.summary?.unavailable ?? 0} 项。</p><ul className="source-list">{(inventoryReport.sources ?? []).map((source) => <li key={source.source_id}><strong>{source.tool} · {source.source_id}</strong><small>{source.status} · {source.file_count ?? 0} 个文件</small>{source.path && <code>{source.path}</code>}{source.detail && <p>{source.detail}</p>}</li>)}</ul><div className="setup-actions"><button className="subtle-button" type="button" disabled={busy} onClick={() => { setInventoryPlanId(null); setInventoryResult(null); void requestOperation('inventory', { save: true }) }}>预览保存盘点报告</button>{inventoryPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('inventory', {}, inventoryPlanId)}>确认保存到本机</button>}</div></>}
            {inventoryResult?.saved && <p className="boundary-note">已保存：{inventoryResult.saved}</p>}
          </FeaturePage>

          <FeaturePage eyebrow="本机快照" title="记忆快照恢复" description="快照会在项目交接保存时创建。恢复前会校验清单与内容哈希；Codex 快照仅可查看，不能回填 Codex 原生记忆数据库。" action={<button className="subtle-button" type="button" disabled={busy || !isConfigured} onClick={() => { setRestoreSnapshotReport(null); setRestoreSnapshotPlanId(null); setRestoreSnapshotResult(null); void requestOperation('snapshots') }}>读取快照清单</button>}>
            {snapshotsReport && (!(snapshotsReport.snapshots ?? []).length ? <p className="pending-copy">本机没有已保存的记忆快照。</p> : <ul className="snapshot-list">{(snapshotsReport.snapshots ?? []).map((snapshot) => <li key={`${snapshot.device_id}-${snapshot.snapshot_id}`}><div><strong>{snapshot.project_id ?? snapshot.tool ?? '参考快照'} · {snapshot.file_count ?? 0} 个文件</strong><small>{snapshot.created_at ?? '时间未知'} · {snapshot.device_id ?? ''} · {snapshot.confirmed ? '远端已确认' : '仅本机／未确认'}</small><code>{snapshot.snapshot_id}</code>{snapshot.status !== 'valid' && <span className="diagnostic-alert">快照无效或链接受阻</span>}</div>{snapshot.restorable ? <button className="subtle-button" type="button" disabled={busy} onClick={() => { setRestoreSnapshotReport(null); setRestoreSnapshotPlanId(null); setRestoreSnapshotResult(null); void requestOperation('restore_snapshot', { snapshot_id: snapshot.snapshot_id }) }}>预览恢复</button> : <span className="small-note">{snapshot.tool === 'codex' ? '仅参考，不回填' : '缺少本机映射'}</span>}</li>)}</ul>)}
            {restoreSnapshotReport && <div className="setup-preview"><div className="setup-preview-heading"><strong>快照恢复预览</strong><span>{restoreSnapshotReport.changes ?? 0} 项变更 · 尚未写入</span></div><ul className="rule-change-list">{(restoreSnapshotReport.paths ?? []).map((path) => <li key={path}><code>{path}</code></li>)}</ul>{restoreSnapshotPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('restore_snapshot', {}, restoreSnapshotPlanId)}>确认恢复快照</button>}</div>}
            {restoreSnapshotResult && <p className="diagnostic-ok">已恢复快照 {restoreSnapshotResult.snapshot_id}，共 {restoreSnapshotResult.changes ?? 0} 项。</p>}
          </FeaturePage>

          <FeaturePage eyebrow="项目接续" title="登记本机项目目录" description="项目标识在设备间保持一致；本机目录只保存在本机设备配置。不同设备可以把同一项目映射到不同路径。">
            <div className="project-map-form"><label><span>共享项目标识</span><input value={projectId} onChange={(event) => { setProjectId(event.target.value); setProjectSetupPlanId(null); setProjectSetupReport(null); setProjectSetupResult(null) }} placeholder="例如 ai-config" /></label><label><span>本机项目目录（绝对路径）</span><input value={projectPath} onChange={(event) => { setProjectPath(event.target.value); setProjectSetupPlanId(null); setProjectSetupReport(null); setProjectSetupResult(null) }} placeholder="例如 D:\\workspace\\ai-config" spellCheck={false} /></label></div>
            <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || !projectId.trim() || !projectPath.trim()} onClick={() => { setProjectSetupPlanId(null); setProjectSetupResult(null); void requestOperation('project_setup', { project_id: projectId.trim(), path: projectPath.trim() }) }}>预览项目映射</button>{projectSetupPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('project_setup', {}, projectSetupPlanId)}>确认保存本机映射</button>}<button className="subtle-button" type="button" disabled={busy || !isConfigured} onClick={() => void requestOperation('project')}>读取项目</button></div>
            {projectSetupReport && <div className="setup-preview"><strong>{projectSetupReport.ready ? '项目目录可用' : '项目目录不存在'}</strong><p>{projectSetupReport.project_id} · {projectSetupReport.path}</p>{projectSetupReport.previous_path && <p>现有映射：{projectSetupReport.previous_path}。确认后会替换本机映射。</p>}</div>}
            {projectSetupResult && <p className="diagnostic-ok">本机映射已保存。设备配置备份：{projectSetupResult.backup ?? '无文件变化'}</p>}
            {projectReport?.projects && <>
              {projectReport.projects.length === 0 ? <p className="pending-copy">还没有登记项目。填写项目标识和本机目录后保存映射。</p> : <label className="rule-topic-field"><span>项目</span><select value={selectedProjectId} onChange={(event) => { const id = event.target.value; setSelectedProjectId(id); setHandoffId(''); setStartReport(null); setStartPlanId(null); setStartResult(null); void requestOperation('project', { project_id: id }) }}><option value="">请选择项目…</option>{projectReport.projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.name} · {project.project_id}{project.has_memory ? '' : '（未启用记忆映射）'}</option>)}</select></label>}
              {(projectReport.available_handoffs ?? []).length > 0 && <label className="rule-topic-field"><span>交接记录</span><select value={handoffId} onChange={(event) => { const id = event.target.value; setHandoffId(id); setStartReport(null); setStartPlanId(null); setStartResult(null); if (selectedProjectId) void requestOperation('project', { project_id: selectedProjectId, handoff_id: id }) }}>{projectReport.available_handoffs?.map((handoff) => <option key={handoff.handoff_id} value={handoff.handoff_id}>{handoff.created_at ?? '时间未知'} · {handoff.status ?? '未知状态'}</option>)}</select></label>}
              {projectReport.handoff_id && <div className="setup-preview"><strong>{projectReport.ready ? '交接条件齐全' : projectReport.reason ?? '交接资料不完整'}</strong><p>目标：{projectReport.goal ?? '未提供'}</p><p>已完成：{projectReport.completed ?? '未提供'}</p><p>下一步：{projectReport.next_step ?? '未提供'}</p><p>尚未完成：{projectReport.remaining ?? '未提供'}</p><p>记忆快照：{projectReport.version ?? '缺失'} · 未同步项：{projectReport.unsynced?.join('、') || '无'}</p></div>}
              <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || !selectedProjectId || !handoffId} onClick={() => { setStartPlanId(null); setStartResult(null); void requestOperation('start', { project_id: selectedProjectId, handoff_id: handoffId }) }}>预览项目接续</button>{startPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('start', {}, startPlanId)}>确认接续（可能读取 Git 远端）</button>}</div>
              {startReport && <div className="setup-preview"><strong>{startReport.ready ? '可以接续' : startReport.reason ?? '暂不能接续'}</strong><p>{startReport.changes ?? 0} 项本机记忆／基线变化。确认后可能先从已配置的 Git 远端快进读取交接。</p><ul className="rule-change-list">{(startReport.paths ?? []).map((path) => <li key={path}><code>{path}</code></li>)}</ul></div>}
              {startResult && <p className="diagnostic-ok">接续结果：{startResult.status} · {startResult.changes ?? 0} 项。仍需在 Agent 新会话确认内容已加载。</p>}
            </>}
          </FeaturePage>

          <FeaturePage eyebrow="保存交接" title="填写进度并创建快照" description="保存会创建本机记忆快照与交接记录；若记忆仓库配置了 Git 远端，会尝试上传并读取确认。Codex 内容仍是参考快照。">
            <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy} onClick={() => setHandoffText('## Goal\n\n## Acceptance\n\n## Completed\n\n## Remaining\n\n## Decisions\n\n## Blockers\n\n## Next Step\n\n## Tests\n\n## Risks\n')}>插入交接模板</button><button className="subtle-button" type="button" disabled={busy || !isConfigured} onClick={() => void requestOperation('project')}>读取项目</button></div>
            <label className="project-id-field"><span>项目标识</span><input value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)} placeholder="先在上方登记项目目录" /></label>
            <label className="path-field handoff-field"><span>交接正文（本地输入；最多 128 KiB）</span><textarea className="rule-editor handoff-editor" value={handoffText} onChange={(event) => { setHandoffText(event.target.value); setFinishPlanId(null); setFinishReport(null); setFinishResult(null) }} spellCheck={false} /></label>
            <div className="setup-actions"><button className="subtle-button" type="button" disabled={busy || !selectedProjectId || !handoffText.trim()} onClick={() => { setFinishPlanId(null); setFinishResult(null); void requestOperation('finish', { project_id: selectedProjectId, handoff_text: handoffText }) }}>预览交接与快照</button>{finishPlanId && <button className="primary-button" type="button" disabled={busy} onClick={() => void requestOperation('finish', {}, finishPlanId)}>确认保存交接（可能上传 Git）</button>}</div>
            {finishReport && <div className="setup-preview"><div className="setup-preview-heading"><strong>{finishReport.handoff_missing_fields?.length ? '交接内容尚未填完整' : '交接与快照预览'}</strong><span>尚未保存</span></div><p>缺少必填章节：{finishReport.handoff_missing_fields?.join('、') || '无'}</p><p>代码工作区：{finishReport.code_ready ? '已与远端确认' : '未完全确认'} · 分支 {finishReport.code_branch ?? '未知'} · 未提交文件 {finishReport.code_dirty_files?.length ?? 0}</p><p>本机记忆文件：{finishReport.memory_file_count ?? 0} 个 · 仓库 {finishReport.memory_repository_exists ? '存在' : '尚未创建'} · Git 远端 {finishReport.memory_remote_configured ? '已配置' : '未配置'}</p><p>共享配置：{finishReport.config_ready ? '已确认' : '尚未确认'} · {finishReport.config_dirty_files?.length ?? 0} 个未提交文件</p>{finishPlanId && <p className="boundary-note">确认会写入本机快照／交接，并可能通过已配置的 Git 远端上传；不会上传 Agent 会话数据库或认证目录。</p>}</div>}
            {finishResult && <div className="setup-preview"><strong>保存结果：{finishResult.status ?? '已执行'}</strong><p>交接 ID：{finishResult.handoff_id ?? '未生成'} · 记忆快照：{finishResult.snapshot_id ?? '已创建或由核心登记'}</p><p>传输状态：{finishResult.transport ?? '未启动'}。请读取快照清单，并在目标 Agent 新会话核验加载。</p></div>}
          </FeaturePage>
        </div>}
      </section>
    </main>
  )
}

function StatusCard({ title, value, detail, tone }: { title: string; value: string; detail: string; tone: 'good' | 'warning' | 'error' | 'neutral' | 'muted' }) {
  return <article className={`status-card ${tone}`}><p>{title}</p><strong>{value}</strong><span>{detail}</span></article>
}

function FeaturePage({ eyebrow, title, description, action, children }: { eyebrow: string; title: string; description: string; action?: ReactNode; children?: ReactNode }) {
  return <section className="panel feature-panel"><div className="panel-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>{action}</div><p className="feature-description">{description}</p>{children}</section>
}

export default App
