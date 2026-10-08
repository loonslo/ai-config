import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  resolve: mode === 'ui-test' ? { alias: Object.fromEntries([
    '@tauri-apps/api/core', '@tauri-apps/api/event', '@tauri-apps/api/window',
    '@tauri-apps/plugin-dialog', '@tauri-apps/plugin-shell',
  ].map(name => [name, fileURLToPath(new URL('./tests/tauri-fixture.ts', import.meta.url))])) } : undefined,
}))
