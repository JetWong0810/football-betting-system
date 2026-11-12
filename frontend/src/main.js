import App from './App'
import { createSSRApp } from 'vue'
import pinia from './stores/pinia'

// #ifdef H5
// 部署后若浏览器缓存了旧入口页,按需加载的分包会 404 导致白屏;检测到加载失败时自动刷新一次拿新版本
function reloadOnceOnChunkError(msg) {
  if (!/dynamically imported module|Importing a module script failed|Loading chunk|preload/i.test(String(msg || ''))) return
  try {
    if (sessionStorage.getItem('chunk-reloaded')) return
    sessionStorage.setItem('chunk-reloaded', '1')
  } catch (e) { /* 无法写入时仍尝试刷新一次 */ }
  location.reload()
}
if (typeof window !== 'undefined') {
  window.addEventListener('vite:preloadError', (e) => { e.preventDefault && e.preventDefault(); reloadOnceOnChunkError('preload') })
  window.addEventListener('unhandledrejection', (e) => reloadOnceOnChunkError(e.reason && (e.reason.message || e.reason)))
}
// #endif

export function createApp () {
  const app = createSSRApp(App)

  app.use(pinia)
  // 便于在非组件环境（如 utils/http.js）访问 pinia 实例
  if (!app.config.globalProperties.$pinia) {
    app.config.globalProperties.$pinia = pinia
  }

  return {
    app
  }
}
