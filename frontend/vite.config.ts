import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import type { IncomingMessage } from 'http'

const apiProxyTarget = process.env.API_PROXY_TARGET || 'http://localhost:8000'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/': {
        target: apiProxyTarget,
        changeOrigin: true,
        bypass: (req: IncomingMessage) => {
          if (!req.url) return

          // 1. Always let FastAPI handle backend-served image paths.
          if (
            req.url.startsWith('/uploaded_images/') ||
            req.url.startsWith('/validation-cache/') ||
            req.url.startsWith('/training-cache/')
          ) {
            return undefined // Do not bypass -> send to FastAPI
          }

          // 2. Let Vite handle frontend source files, assets, HTML, and HMR
          if (
            req.url.startsWith('/src/') ||
            req.url.startsWith('/@') ||
            req.url.includes('.') ||
            req.headers.accept?.includes('text/html')
          ) {
            return req.url // Bypass proxy, serve locally via Vite
          }
        }
      }
    }
  }
})