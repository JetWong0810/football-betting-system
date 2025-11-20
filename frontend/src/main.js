import App from './App'
import { createSSRApp } from 'vue'
import pinia from './stores/pinia'

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
