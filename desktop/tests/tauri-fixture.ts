// Browser-only test transport, enabled exclusively by Vite's ui-test mode.
type Handler = (value: unknown) => void
const events: Record<string, Handler> = {}
export const Command = { sidecar: () => ({
  stdout: { on: (event: string, callback: Handler) => { events[event] = callback } },
  on: () => {},
  spawn: async () => ({ write: async (text: string) => {
    const req = JSON.parse(text)
    const transport = new URLSearchParams(location.search).get('transport')
    if (transport === 'silent' || transport === 'apply-silent' && req.type === 'apply') return
    const operation = req.operation
    const result = operation === 'machine_detect'
      ? { agents: [{ id: 'codex', name: 'Codex', installed: true, root: 'C:\\Fixture\\Codex' }], projects: [] }
      : operation === 'machine_history' ? { operations: [] }
      : operation === 'machine_backup' ? { entries: 7, projects: 1, exclusions: [], destination: 'C:\\Fixture\\AI备份.zip' }
      : { bundle_agents: ['codex'], writes: 2, conflicts: [], skipped: [], running: [], source_projects: [] }
    window.setTimeout(() => events.data?.(JSON.stringify({ type: 'result', request_id: req.request_id,
      status: req.type === 'apply' ? 'applied' : 'preview', result,
      can_apply: !['machine_detect', 'machine_history'].includes(operation), plan_id: 'fixture-plan' }) + (transport === 'crlf' ? '\r\n' : '')), 20)
  } }),
}) }
export async function invoke() { return null }
export async function listen() { return () => {} }
export function getCurrentWindow() { return { onDragDropEvent: async () => () => {}, onCloseRequested: async () => () => {}, destroy: async () => {} } }
export async function open(options: { directory?: boolean }) { return options.directory ? 'C:\\Fixture\\Backups' : 'C:\\Fixture\\AI备份.zip' }
