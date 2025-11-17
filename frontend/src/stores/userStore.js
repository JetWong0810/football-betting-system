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
        
        return res
      } catch (error) {
        throw error
      }
    },

    // 退出登录
    logout() {
      this.token = ''
      this.user = null
      
      // 清除本地存储
      uni.removeStorageSync('token')
      uni.removeStorageSync('user')
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
    }
  }
})

