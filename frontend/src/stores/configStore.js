import { defineStore } from 'pinia'
import { ref } from 'vue'
import { request } from '@/utils/http'

const STORAGE_KEY = 'frbt-config'

// 与 strategyEngine.js 的 PRESETS 保持一致（避免循环依赖，这里内联）
const PRESET_DEFAULTS = {
  conservative: { minConfidence: 70, maxDrawdown: -0.10 },
  balanced: { minConfidence: 60, maxDrawdown: -0.15 },
  aggressive: { minConfidence: 50, maxDrawdown: -0.25 },
}

export const useConfigStore = defineStore('config', () => {
  const startingCapital = ref(10000)
  const fixedRatio = ref(0.03)
  const kellyFactor = ref(0.5)
  const stopLossLimit = ref(3)
  const targetMonthlyReturn = ref(0.1)
  const theme = ref('light')
  const riskTolerance = ref('balanced')
  // minConfidence / maxDrawdown 仅前端持久化（后端 user_configs 暂无对应列）
  const minConfidence = ref(60)
  const maxDrawdown = ref(-0.15)
  const loading = ref(false)

  // 命名预设切换时，用预设默认值同步 minConfidence/maxDrawdown；custom 模式保留用户值
  function syncPresetDefaults() {
    if (riskTolerance.value === 'custom') return
    const d = PRESET_DEFAULTS[riskTolerance.value]
    if (d) {
      minConfidence.value = d.minConfidence
      maxDrawdown.value = d.maxDrawdown
    }
  }

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
        riskTolerance.value = config.risk_tolerance || riskTolerance.value
      }
      // 命名预设下，minConfidence/maxDrawdown 由预设派生；自定义模式保留本地值
      syncPresetDefaults()
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
      if (cache.minConfidence != null) minConfidence.value = Number(cache.minConfidence)
      if (cache.maxDrawdown != null) maxDrawdown.value = Number(cache.maxDrawdown)
    }
    syncPresetDefaults()
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
          theme: theme.value,
          risk_tolerance: riskTolerance.value
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
      riskTolerance: riskTolerance.value,
      minConfidence: minConfidence.value,
      maxDrawdown: maxDrawdown.value
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
    if (payload.minConfidence !== undefined) minConfidence.value = Number(payload.minConfidence)
    if (payload.maxDrawdown !== undefined) maxDrawdown.value = Number(payload.maxDrawdown)
    // 命名预设切换时同步 minConfidence/maxDrawdown 默认值
    if (payload.riskTolerance && payload.riskTolerance !== 'custom') syncPresetDefaults()

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
    minConfidence,
    maxDrawdown,
    loading,
    bootstrap,
    updateConfig,
    loadFromServer,
    loadFromLocal,
    saveToServer
  }
})
