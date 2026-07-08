import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useConfigStore } from './configStore'
import { useBetStore } from './betStore'
import { checkControlAlert } from '@/utils/strategyEngine'

/**
 * 控手 Store:连不中触发暂停 + 冷却恢复 + 降档起步
 *
 * 触发:连不中达阈值(信心档挂钩 高3/中4/低5 → strong;再+1 → pause 隐藏下注入口)
 * 恢复:pause 后需冷静 coolHours(默认2h),倒计时结束点"恢复下注"
 * 降档起步:恢复后 recoveryLock='low',首注只能选低档;赢一把解锁中档,再赢解锁高档
 */
export const useControlStore = defineStore('control', () => {
  const configStore = useConfigStore()
  const pausedAt = ref(null)        // 暂停时间戳;null=未暂停
  const recoveryLock = ref(null)    // 'low'|'mid'|'high'|null(全解锁)

  const isPaused = computed(() => pausedAt.value !== null)
  const coolMs = computed(() => (Number(configStore.coolHours) || 2) * 3600 * 1000)

  // 剩余冷静秒数(组件 setInterval 调用,因 Date.now() 非响应式)
  function getRemainingSeconds() {
    if (!isPaused.value || !pausedAt.value) return 0
    return Math.max(0, Math.ceil((coolMs.value - (Date.now() - pausedAt.value)) / 1000))
  }

  // 当前控手告警(基于连不中数 + 最近一注信心档 + 阈值)
  const controlAlert = computed(() => {
    const betStore = useBetStore()
    return checkControlAlert({
      consecutiveLosses: betStore.consecutiveLosses,
      lastTier: betStore.lastTier,
      tierThresholds: configStore.tierThresholds,
    })
  })

  function pause() {
    pausedAt.value = Date.now()
    save()
  }

  function resume() {
    if (getRemainingSeconds() > 0) return
    recoveryLock.value = 'low'
    pausedAt.value = null
    save()
  }

  // 结算后调用:赢一把 recoveryLock 升级,直到 null(全解锁)
  function onSettled(result) {
    if (recoveryLock.value === null) return
    if (result === 'win' || result === 'half-win') {
      recoveryLock.value = { low: 'mid', mid: 'high', high: null }[recoveryLock.value] ?? null
      save()
    }
  }

  // 档位是否被锁(高于 recoveryLock 的档位禁用)
  function isTierLocked(tier) {
    if (recoveryLock.value === null) return false
    const order = { low: 0, mid: 1, high: 2 }
    return (order[tier] ?? 0) > (order[recoveryLock.value] ?? 0)
  }

  function load() {
    try {
      const s = uni.getStorageSync('frbt-control')
      if (s) {
        pausedAt.value = s.pausedAt ?? null
        recoveryLock.value = s.recoveryLock ?? null
      }
    } catch (e) {
      // storage 读取失败,忽略
    }
  }

  function save() {
    try {
      uni.setStorageSync('frbt-control', {
        pausedAt: pausedAt.value,
        recoveryLock: recoveryLock.value,
      })
    } catch (e) {
      // storage 写入失败,忽略
    }
  }

  load()

  return {
    pausedAt,
    recoveryLock,
    isPaused,
    coolMs,
    controlAlert,
    getRemainingSeconds,
    pause,
    resume,
    onSettled,
    isTierLocked,
    load,
    save,
  }
})
