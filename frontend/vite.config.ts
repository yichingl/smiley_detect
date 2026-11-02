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

          // 1. Always let FastAPI handle backend routes and image paths.
          if (
            req.url.startsWith('/dataset/') ||
            req.url.startsWith('/uploaded_images/') ||
            req.url.startsWith('/validation-cache/') ||
            req.url.startsWith('/training-cache/') ||
            req.url.startsWith('/tasks/') ||
            req.url.startsWith('/images/') ||
            req.url.startsWith('/models') ||
            req.url.startsWith('/validation-images') ||
            req.url.startsWith('/training-images')
          ) {
            return undefined // Do not bypass -> send to FastAPI
          }

          // 2. Let Vite handle frontend source files, assets, HTML, and HMR
          if (
            req.url.startsWith('/src/') ||
            req.url.startsWith('/@') ||
            req.url.startsWith('/node_modules/') ||
            req.url.startsWith('/favicon.svg') ||
            req.url.startsWith('/favicon.ico') ||
            req.headers.accept?.includes('text/html')
          ) {
            return req.url // Bypass proxy, serve locally via Vite
          }
        }
      }
    }
  }
})