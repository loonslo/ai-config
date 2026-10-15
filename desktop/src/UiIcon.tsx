type IconName = 'backup' | 'restore' | 'history' | 'folder' | 'archive' | 'refresh' | 'shield' | 'check'

const paths: Record<IconName, string> = {
  backup: 'M12 16V4m-4 4 4-4 4 4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4',
  restore: 'M12 4v12m-4-4 4 4 4-4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4',
  history: 'M3 11a9 9 0 1 1 2.6 7M3 4v7h7m2-4v5l3 2',
  folder: 'M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z',
  archive: 'M5 3h14v18H5ZM10 3v3m4 0v3m-4 0v3m4 0v3m-4 0v3h4',
  refresh: 'M20 7v5h-5M4 17v-5h5m-4-4a8 8 0 0 1 13-3l2 3M4 16l2 3a8 8 0 0 0 13-3',
  shield: 'M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Zm-4 9 3 3 5-6',
  check: 'm5 12 4 4L19 6',
}

export function UiIcon({ name, className = '' }: { name: IconName; className?: string }) {
  return <svg className={`ui-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}
