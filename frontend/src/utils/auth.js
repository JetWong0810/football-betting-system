/**
 * 认证相关工具函数
 */
import { useUserStore } from '@/stores/userStore'

/**
 * 需要登录的页面列表
 */
export const AUTH_REQUIRED_PAGES = [
  '/pages/profile/profile',
  '/pages/record/record',
  '/pages/settings/settings',
  '/pages/strategy/strategy',
  '/pages/analysis/analysis',
]

/**
 * 登录相关页面（已登录用户访问这些页面时，应该跳转到首页）
 */
export const AUTH_PAGES = [
  '/pages/auth/login',
  '/pages/auth/register',
  '/pages/auth/wechat-login',
]

/**
 * 检查是否已登录
 */
export function isLoggedIn() {
  const userStore = useUserStore()
  return userStore.isLoggedIn
}

/**
 * 检查是否在微信小程序环境
 */
export function isWeChatMiniProgram() {
  // #ifdef MP-WEIXIN
  return true
  // #endif
  // #ifndef MP-WEIXIN
  return false
  // #endif
}

/**
 * 检查当前页面是否需要登录
 * @param {string} path 页面路径，如果不提供则获取当前页面路径
 * @returns {boolean} 是否需要登录
 */
export function isAuthRequired(path = null) {
  if (!path) {
    const pages = getCurrentPages()
    const currentPage = pages[pages.length - 1]
    if (!currentPage) {
      return false
    }
    path = '/' + currentPage.route
  }
  
  return AUTH_REQUIRED_PAGES.includes(path)
}

/**
 * 路由守卫：检查登录状态，未登录则跳转
 * @param {Object} options 选项
 * @param {boolean} options.required 是否必须登录，默认true
 * @param {string} options.redirect 未登录时的跳转路径
 * @param {string} options.path 要检查的页面路径，如果不提供则获取当前页面路径
 * @returns {boolean} 是否已登录
 */
export function requireAuth(options = {}) {
  const { required = true, redirect, path } = options
  
  if (!required) {
    return true
  }
  
  const userStore = useUserStore()
  
  if (!userStore.isLoggedIn) {
    // 根据环境跳转到不同的登录页面
    if (isWeChatMiniProgram()) {
      // 微信小程序环境：跳转到微信授权登录页面
      uni.redirectTo({
        url: redirect || '/pages/auth/wechat-login'
      })
    } else {
      // H5环境：跳转到普通登录页面
      uni.redirectTo({
        url: redirect || '/pages/auth/login'
      })
    }
    return false
  }
  
  return true
}

/**
 * 页面路由守卫混入（用于页面）
 * 在页面的onLoad或onShow中调用
 * @param {Object} options 选项
 * @param {boolean} options.required 是否必须登录，如果不提供则根据页面路径自动判断
 * @param {string} options.redirect 未登录时的跳转路径
 * @returns {boolean} 是否已登录
 */
export function useAuthGuard(options = {}) {
  const { required, redirect } = options
  
  // 获取当前页面路径
  const pages = getCurrentPages()
  const currentPage = pages[pages.length - 1]
  if (!currentPage) {
    return true
  }
  
  const currentPath = '/' + currentPage.route
  
  // 排除登录相关页面
  if (AUTH_PAGES.includes(currentPath)) {
    // 如果已登录，访问登录页面时跳转到首页
    const userStore = useUserStore()
    if (userStore.isLoggedIn) {
      uni.switchTab({
        url: '/pages/home/home'
      })
      return false
    }
    return true
  }
  
  // 如果没有指定required，则根据页面路径自动判断
  const shouldRequireAuth = required !== undefined ? required : isAuthRequired(currentPath)
  
  return requireAuth({ required: shouldRequireAuth, redirect })
}

