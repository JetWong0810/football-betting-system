import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'frbt-config'

export const useConfigStore = defineStore('config', () => {
  const startingCapital = ref(10000)
  const fixedRatio = ref(0.03)
  const kellyFactor = ref(0.5)
  const stopLossLimit = ref(3)
  const targetMonthlyReturn = ref(0.1)
  const theme = ref('light')
  const riskTolerance = ref('balanced')

  function persist () {
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

  async function bootstrap () {
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

  function updateConfig (payload = {}) {
    if (payload.startingCapital !== undefined) startingCapital.value = Number(payload.startingCapital)
    if (payload.fixedRatio !== undefined) fixedRatio.value = Number(payload.fixedRatio)
    if (payload.kellyFactor !== undefined) kellyFactor.value = Number(payload.kellyFactor)
    if (payload.stopLossLimit !== undefined) stopLossLimit.value = Number(payload.stopLossLimit)
    if (payload.targetMonthlyReturn !== undefined) targetMonthlyReturn.value = Number(payload.targetMonthlyReturn)
    if (payload.theme) theme.value = payload.theme
    if (payload.riskTolerance) riskTolerance.value = payload.riskTolerance
    persist()
  }

  return {
    startingCapital,
    fixedRatio,
    kellyFactor,
    stopLossLimit,
    targetMonthlyReturn,
    theme,
    riskTolerance,
    bootstrap,
    updateConfig,
    persist
  }
})
