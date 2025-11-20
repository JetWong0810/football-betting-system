import { defineStore } from 'pinia'
import { ref } from 'vue'
import { request } from '@/utils/http'

const STORAGE_KEY = 'frbt-config'

export const useConfigStore = defineStore('config', () => {
  const startingCapital = ref(10000)
  const fixedRatio = ref(0.03)
  const kellyFactor = ref(0.5)
  const stopLossLimit = ref(3)
  const targetMonthlyReturn = ref(0.1)
  const theme = ref('light')
  const riskTolerance = ref('balanced')
  const loading = ref(false)

  function hasAuthToken() {
    return !!uni.getStorageSync('token')
  }

  /**
   * 从后端API加载用户配置
   */
  async function loadFromServer() {
    if (!hasAuthToken()) {
      loadFromLocal()
      return
    }

    loading.value = true
    try {
      const config = await request({
        url: '/api/user/config',
        method: 'GET'
      })

      if (config) {
        startingCapital.value = Number(config.starting_capital ?? startingCapital.value)
        fixedRatio.value = Number(config.fixed_ratio ?? fixedRatio.value)
        kellyFactor.value = Number(config.kelly_factor ?? kellyFactor.value)
        stopLossLimit.value = Number(config.stop_loss_limit ?? stopLossLimit.value)
        targetMonthlyReturn.value = Number(config.target_monthly_return ?? targetMonthlyReturn.value)
        theme.value = config.theme || theme.value
        // riskTolerance 不在后端配置中，保持本地值
      }
    } catch (error) {
      console.error('加载用户配置失败:', error)
      // 如果加载失败，尝试从本地存储加载（兼容旧数据）
      loadFromLocal()
    } finally {
      loading.value = false
    }
  }

  /**
   * 从本地存储加载配置（兼容旧数据，仅在未登录或API失败时使用）
   */
  function loadFromLocal() {
    const cache = uni.getStorageSync(STORAGE_KEY)
    if (cache && typeof cache === 'object') {
      startingCapital.value = Number(cache.startingCapital ?? startingCapital.value)
      fixedRatio.value = Number(cache.fixedRatio ?? fixedRatio.value)
      kellyFactor.value = Number(cache.kellyFactor ?? kellyFactor.value)
      stopLossLimit.value = Number(cache.stopLossLimit ?? stopLossLimit.value)
      targetMonthlyReturn.value = Number(cache.targetMonthlyReturn ?? targetMonthlyReturn.value)
      theme.value = cache.theme || theme.value
      riskTolerance.value = cache.riskTolerance || riskTolerance.value
    }
  }

  /**
   * 保存配置到后端API
   */
  async function saveToServer() {
    if (!hasAuthToken()) {
      saveToLocal()
      return
    }

    loading.value = true
    try {
      await request({
        url: '/api/user/config',
        method: 'PUT',
        data: {
          starting_capital: startingCapital.value,
          fixed_ratio: fixedRatio.value,
          kelly_factor: kellyFactor.value,
          stop_loss_limit: stopLossLimit.value,
          target_monthly_return: targetMonthlyReturn.value,
          theme: theme.value
        }
      })
    } catch (error) {
      console.error('保存用户配置失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 保存配置到本地存储（兼容旧数据，仅在未登录时使用）
   */
  function saveToLocal() {
    uni.setStorageSync(STORAGE_KEY, {
      startingCapital: startingCapital.value,
      fixedRatio: fixedRatio.value,
      kellyFactor: kellyFactor.value,
      stopLossLimit: stopLossLimit.value,
      targetMonthlyReturn: targetMonthlyReturn.value,
      theme: theme.value,
      riskTolerance: riskTolerance.value
    })
  }

  /**
   * 初始化配置（从后端或本地加载）
   */
  async function bootstrap() {
    await loadFromServer()
  }

  /**
   * 更新配置（同步到后端）
   */
  async function updateConfig(payload = {}) {
    if (payload.startingCapital !== undefined) startingCapital.value = Number(payload.startingCapital)
    if (payload.fixedRatio !== undefined) fixedRatio.value = Number(payload.fixedRatio)
    if (payload.kellyFactor !== undefined) kellyFactor.value = Number(payload.kellyFactor)
    if (payload.stopLossLimit !== undefined) stopLossLimit.value = Number(payload.stopLossLimit)
    if (payload.targetMonthlyReturn !== undefined) targetMonthlyReturn.value = Number(payload.targetMonthlyReturn)
    if (payload.theme) theme.value = payload.theme
    if (payload.riskTolerance) riskTolerance.value = payload.riskTolerance
    
    // 保存到后端（如果已登录）或本地（如果未登录）
    await saveToServer()
  }

  return {
    startingCapital,
    fixedRatio,
    kellyFactor,
    stopLossLimit,
    targetMonthlyReturn,
    theme,
    riskTolerance,
    loading,
    bootstrap,
    updateConfig,
    loadFromServer,
    loadFromLocal,
    saveToServer
  }
})
