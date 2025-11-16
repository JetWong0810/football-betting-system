import { defineStore } from 'pinia'
import { computed } from 'vue'
import dayjs from 'dayjs'
import { useBetStore } from './betStore'
import { useConfigStore } from './configStore'

export const useStatStore = defineStore('stats', () => {
  const betStore = useBetStore()
  const configStore = useConfigStore()

  const betCount = computed(() => betStore.bets.length)
  const averageStake = computed(() => betCount.value ? betStore.totalStake / betCount.value : 0)
  const averageOdds = computed(() => {
    if (!betCount.value) return 0
    const total = betStore.bets.reduce((sum, bet) => sum + Number(bet.odds || 0), 0)
    return total / betCount.value
  })

  const roi = computed(() => {
    if (!betStore.totalStake) return 0
    const stakeValue = Number(betStore.totalStake)
    if (!stakeValue) return 0
    return betStore.totalProfit / stakeValue
  })

  const balance = computed(() => Number(configStore.startingCapital) + Number(betStore.totalProfit))
  const targetProgress = computed(() => {
    if (!configStore.targetMonthlyReturn) return 0
    const target = Number(configStore.startingCapital) * Number(configStore.targetMonthlyReturn)
    if (!target) return 0
    return betStore.totalProfit / target
  })

  const pieDataset = computed(() => {
    const groups = betStore.bets.reduce((acc, bet) => {
      const key = bet.betType || '其他'
      acc[key] = acc[key] || 0
      acc[key] += Number(bet.profit || 0)
      return acc
    }, {})
    return Object.keys(groups).map(name => ({ name, value: Number(groups[name].toFixed(2)) }))
  })

  const trendSeries = computed(() => {
    let rolling = Number(configStore.startingCapital)
    return betStore.snapshots.map(item => {
      rolling += Number(item.profit)
      return { ...item, balance: Number(rolling.toFixed(2)) }
    })
  })

  const maxConsecutiveLoss = computed(() => {
    let current = 0
    let max = 0
    betStore.bets.forEach(bet => {
      if (bet.result === 'lose') {
        current += 1
        max = Math.max(max, current)
      } else if (bet.result === 'win') {
        current = 0
      }
    })
    return max
  })

  const drawdown = computed(() => {
    let peak = Number(configStore.startingCapital)
    let maxDd = 0
    let equity = peak
    betStore.bets.forEach(bet => {
      equity += Number(bet.profit)
      if (equity > peak) {
        peak = equity
      }
      const dd = peak ? (equity - peak) / peak : 0
      if (dd < maxDd) {
        maxDd = dd
      }
    })
    return maxDd
  })

  const periodStats = computed(() => {
    const grouped = {}
    betStore.bets.forEach(bet => {
      const week = dayjs(bet.betTime).format('YYYY-[W]WW')
      grouped[week] = grouped[week] || { stake: 0, profit: 0, count: 0 }
      grouped[week].stake += Number(bet.stake || 0)
      grouped[week].profit += Number(bet.profit || 0)
      grouped[week].count += 1
    })
    return grouped
  })

  return {
    betCount,
    averageStake,
    averageOdds,
    roi,
    balance,
    targetProgress,
    pieDataset,
    trendSeries,
    maxConsecutiveLoss,
    drawdown,
    periodStats
  }
})
