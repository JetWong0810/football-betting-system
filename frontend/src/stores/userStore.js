import { defineStore } from 'pinia'
import { request } from '@/utils/http'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: uni.getStorageSync('token') || '',
    user: uni.getStorageSync('user') || null,
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
  },

  actions: {
    // 注册
    async register(data) {
      try {
        const res = await request({
          url: '/api/auth/register',
          method: 'POST',
          data
        })
        
        this.token = res.token
        this.user = res.user
        
        // 保存到本地存储
        uni.setStorageSync('token', res.token)
        uni.setStorageSync('user', res.user)
        
        // 注册后加载用户配置（会创建默认配置）和投注记录
        const { useConfigStore } = await import('@/stores/configStore')
        const configStore = useConfigStore()
        await configStore.loadFromServer()
        
        // 加载新用户的投注记录（应该为空）
        const { useBetStore } = await import('@/stores/betStore')
        const betStore = useBetStore()
        await betStore.refreshBets()
        
        return res
      } catch (error) {
        throw error
      }
    },

    // 登录
    async login(data) {
      try {
        const res = await request({
          url: '/api/auth/login',
          method: 'POST',
          data
        })
        
        this.token = res.token
        this.user = res.user
        
        // 保存到本地存储
        uni.setStorageSync('token', res.token)
        uni.setStorageSync('user', res.user)
        
        // 登录后加载用户配置和投注记录
        const { useConfigStore } = await import('@/stores/configStore')
        const configStore = useConfigStore()
        await configStore.loadFromServer()
        
        // 重新加载当前用户的投注记录
        const { useBetStore } = await import('@/stores/betStore')
        const betStore = useBetStore()
        await betStore.refreshBets()
        
        return res
      } catch (error) {
        throw error
      }
    },

    // 微信登录
    async wechatLogin(data) {
      try {
        const res = await request({
          url: '/api/auth/wechat-login',
          method: 'POST',
          data
        })
        
        this.token = res.token
        this.user = res.user
        
        // 保存到本地存储
        uni.setStorageSync('token', res.token)
        uni.setStorageSync('user', res.user)
        
        // 登录后加载用户配置和投注记录
        const { useConfigStore } = await import('@/stores/configStore')
        const configStore = useConfigStore()
        await configStore.loadFromServer()
        
        // 重新加载当前用户的投注记录
        const { useBetStore } = await import('@/stores/betStore')
        const betStore = useBetStore()
        await betStore.refreshBets()
        
        return res
      } catch (error) {
        throw error
      }
    },

    // 退出登录
    async logout() {
      this.token = ''
      this.user = null
      
      // 清除本地存储
      uni.removeStorageSync('token')
      uni.removeStorageSync('user')
      
      // 清空用户相关的store数据
      // 清空投注记录
      const { useBetStore } = await import('@/stores/betStore')
      const betStore = useBetStore()
      betStore.clearBets()
      
      // 重置配置为默认值（从本地加载，如果本地没有则使用默认值）
      const { useConfigStore } = await import('@/stores/configStore')
      const configStore = useConfigStore()
      configStore.loadFromLocal()
    },

    // 获取用户信息
    async fetchUserProfile() {
      if (!this.token) {
        return
      }
      
      try {
        const res = await request({
          url: '/api/user/profile',
          method: 'GET',
          header: {
            'Authorization': `Bearer ${this.token}`
          }
        })
        
        this.user = res
        uni.setStorageSync('user', res)
        
        return res
      } catch (error) {
        // Token失效，清除登录状态
        if (error.statusCode === 401) {
          this.logout()
        }
        throw error
      }
    },

    // 更新用户资料
    async updateProfile(data) {
      try {
        await request({
          url: '/api/user/profile',
          method: 'PUT',
          data,
          header: {
            'Authorization': `Bearer ${this.token}`
          }
        })
        
        // 重新获取用户信息
        await this.fetchUserProfile()
      } catch (error) {
        throw error
      }
    },

    // 获取用户配置
    async fetchUserConfig() {
      if (!this.token) {
        return null
      }
      
      try {
        const res = await request({
          url: '/api/user/config',
          method: 'GET',
          header: {
            'Authorization': `Bearer ${this.token}`
          }
        })
        return res
      } catch (error) {
        throw error
      }
    },

    // 更新用户配置
    async updateConfig(data) {
      try {
        await request({
          url: '/api/user/config',
          method: 'PUT',
          data,
          header: {
            'Authorization': `Bearer ${this.token}`
          }
        })
      } catch (error) {
        throw error
      }
    },

    // 验证token是否有效
    async verifyToken() {
      if (!this.token) {
        return false
      }
      
      try {
        const res = await request({
          url: '/api/auth/verify',
          method: 'GET'
        })
        
        // 如果验证成功，更新用户信息
        if (res && res.user) {
          this.user = res.user
          uni.setStorageSync('user', res.user)
        }
        
        return true
      } catch (error) {
        // token无效，清除登录状态
        if (error.statusCode === 401) {
          this.logout()
        }
        return false
      }
    }
  }
})

