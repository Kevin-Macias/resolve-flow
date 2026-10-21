import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'
import { nitro } from 'nitro/vite'
import tsconfigPaths from 'vite-tsconfig-paths'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  for (const name of ['API_ORIGIN', 'WEB_ORIGIN']) {
    if (process.env[name] === undefined && env[name]) process.env[name] = env[name]
  }
  return {
    plugins: [tsconfigPaths(), tailwindcss(), tanstackStart(), nitro(), react()],
  }
})
