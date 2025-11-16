import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import dayjs from 'dayjs'
import { useConfigStore } from './configStore'

const STORAGE_KEY = 'frbt-bets'

const defaultBet = () => ({
  id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  matchName: '',
  league: '',
  betType: 'win-draw-lose',
  wagerType: 'single',
  stake: 0,
  odds: 1.0,
  platform: '',
  result: 'pending',
  status: 'saved', // saved: 已保存(草稿), betting: 投注中, settled: 已结算
  profit: 0,
  fee: 0,
  betTime: dayjs().format('YYYY-MM-DD HH:mm'),
  tags: [],
  note: '',
  legs: []
})

export const useBetStore = defineStore('bet', () => {
  const bets = ref([])
  const loading = ref(false)
  const snapshots = ref([])

  // 计算总投注金额（只统计投注中和已结算的）
  const totalStake = computed(() => 
    bets.value
      .filter(bet => bet.status === 'betting' || bet.status === 'settled')
      .reduce((sum, bet) => sum + Number(bet.stake || 0), 0)
  )
  
  // 计算总盈亏（只统计已结算的）
  const totalProfit = computed(() => 
    bets.value
      .filter(bet => bet.status === 'settled')
      .reduce((sum, bet) => sum + Number(bet.profit || 0), 0)
  )
  
  // 统计胜负场次（只统计已结算的）
  const winCount = computed(() => 
    bets.value.filter(bet => bet.status === 'settled' && bet.result === 'win').length
  )
  const loseCount = computed(() => 
    bets.value.filter(bet => bet.status === 'settled' && bet.result === 'lose').length
  )
  
  // 胜率计算（只统计已结算的）
  const winningRate = computed(() => {
    const settledBets = bets.value.filter(bet => bet.status === 'settled')
    if (!settledBets.length) return 0
    return winCount.value / settledBets.length
  })
  
  const consecutiveLosses = computed(() => {
    let streak = 0
    const settledBets = bets.value.filter(bet => bet.status === 'settled')
    for (const bet of settledBets) {
      if (bet.result === 'lose') {
        streak += 1
      } else if (bet.result === 'win') {
        break
      }
    }
    return streak
  })

  // 当前余额 = 初始资金 + 已结算盈亏 - 投注中金额
  const bankroll = computed(() => {
    const configStore = useConfigStore()
    const bettingStake = bets.value
      .filter(bet => bet.status === 'betting')
      .reduce((sum, bet) => sum + Number(bet.stake || 0), 0)
    return Number(configStore.startingCapital) + totalProfit.value - bettingStake
  })

  function persist () {
    uni.setStorageSync(STORAGE_KEY, bets.value)
  }

  function recalculateSnapshots () {
    const grouped = bets.value.reduce((acc, bet) => {
      const dayKey = dayjs(bet.betTime).format('YYYY-MM-DD')
      if (!acc[dayKey]) {
        acc[dayKey] = { date: dayKey, stake: 0, profit: 0 }
      }
      acc[dayKey].stake += Number(bet.stake || 0)
      acc[dayKey].profit += Number(bet.profit || 0)
      return acc
    }, {})
    snapshots.value = Object.values(grouped).sort((a, b) => a.date.localeCompare(b.date))
  }

  function normalizeBet (payload = {}) {
    const base = defaultBet()
    const draft = {
      ...base,
      ...payload,
      id: payload.id || base.id,
      status: payload.status || base.status // 保留传入的status
    }

    const normalizedLegs = (() => {
      if (Array.isArray(payload.legs) && payload.legs.length) {
        return payload.legs.map((leg, index) => ({
          id: leg.id || `${draft.id}-leg-${index}`,
          homeTeam: leg.homeTeam || '',
          awayTeam: leg.awayTeam || '',
          league: leg.league || payload.league || '',
          matchTime: leg.matchTime || payload.betTime || base.betTime,
          betType: leg.betType || payload.betType || '胜平负',
          odds: Number(leg.odds || 1),
          stake: Number(leg.stake || 0),
          selection: leg.selection || '',
          note: leg.note || ''
        }))
      }

      // 兼容旧数据：将单场信息转为一个 leg
      return [{
        id: `${draft.id}-leg-0`,
        homeTeam: payload.homeTeam || payload.matchName || '',
        awayTeam: payload.awayTeam || '',
        league: payload.league || '',
        matchTime: payload.betTime || base.betTime,
        betType: payload.betType || '胜平负',
        odds: Number(payload.odds || 1),
        stake: Number(payload.stake || 0),
        selection: '',
        note: payload.note || ''
      }]
    })()

    const legsCount = normalizedLegs.length
    const oddsFromLegs = normalizedLegs.reduce((acc, leg) => acc * (Number(leg.odds) || 1), 1)
    const stake = Number(draft.stake || 0)
    const fee = Number(draft.fee || 0)
    const odds = Number(draft.odds || oddsFromLegs || 1)

    draft.legs = normalizedLegs
    draft.odds = odds
    draft.wagerType = payload.wagerType || (legsCount > 1 ? 'parlay' : 'single')
    draft.betType = draft.wagerType === 'parlay' || legsCount > 1
      ? `串关(${legsCount})`
      : normalizedLegs[0].betType || '胜平负'
    draft.league = legsCount === 1 ? normalizedLegs[0].league : '串关'
    draft.matchName = (() => {
      if (legsCount === 1) {
        const leg = normalizedLegs[0]
        if (leg.homeTeam && leg.awayTeam) {
          return `${leg.homeTeam} vs ${leg.awayTeam}`
        }
        return leg.homeTeam || leg.awayTeam || payload.matchName || '未命名比赛'
      }
      const firstLeg = normalizedLegs[0]
      const anchor = firstLeg.homeTeam || firstLeg.awayTeam || firstLeg.league || '多场串关'
      return `${anchor} 等${legsCount}场`
    })()
    draft.wagerType = draft.wagerType || (legsCount > 1 ? 'parlay' : 'single')

    // 只有已结算状态才计算盈亏
    if (draft.status === 'settled') {
      if (draft.result === 'win') {
        draft.profit = stake * (odds - 1) - fee
      } else if (draft.result === 'lose') {
        draft.profit = -stake - fee
      } else if (draft.result === 'half-win') {
        draft.profit = (stake * (odds - 1)) / 2 - fee
      } else if (draft.result === 'half-lose') {
        draft.profit = -stake / 2 - fee
      } else {
        draft.profit = 0
      }
    } else {
      draft.profit = 0 // 未结算的记录盈亏为0
    }

    return draft
  }

  async function bootstrap () {
    loading.value = true
    try {
      const cache = uni.getStorageSync(STORAGE_KEY)
      if (Array.isArray(cache)) {
        bets.value = cache.map(normalizeBet)
      }
    } finally {
      loading.value = false
      recalculateSnapshots()
    }
  }

  function addBet (payload) {
    const bet = normalizeBet(payload)
    
    // 如果是投注中状态，检查余额是否足够
    if (bet.status === 'betting') {
      const configStore = useConfigStore()
      const currentBalance = bankroll.value
      if (currentBalance < bet.stake) {
        throw new Error('账户余额不足')
      }
    }
    
    bets.value = [bet, ...bets.value]
    persist()
    recalculateSnapshots()
    return bet
  }

  function updateBet (id, payload) {
    const oldBet = bets.value.find(bet => bet.id === id)
    
    // 如果从其他状态变为投注中，检查余额
    if (payload.status === 'betting' && oldBet?.status !== 'betting') {
      const currentBalance = bankroll.value
      const stake = Number(payload.stake || oldBet?.stake || 0)
      if (currentBalance < stake) {
        throw new Error('账户余额不足')
      }
    }
    
    bets.value = bets.value.map(bet => {
      if (bet.id !== id) return bet
      return normalizeBet({ ...bet, ...payload, id })
    })
    persist()
    recalculateSnapshots()
  }

  function removeBet (id) {
    // 删除时不需要特殊处理余额，因为计算会自动更新
    bets.value = bets.value.filter(bet => bet.id !== id)
    persist()
    recalculateSnapshots()
  }
  
  // 将投注记录从"投注中"结算
  function settleBet(id, result) {
    const bet = bets.value.find(b => b.id === id)
    if (!bet) {
      throw new Error('投注记录不存在')
    }
    if (bet.status !== 'betting') {
      throw new Error('只能结算投注中的记录')
    }
    
    updateBet(id, { 
      status: 'settled',
      result: result || bet.result
    })
  }

  function clearBets () {
    bets.value = []
    persist()
    recalculateSnapshots()
  }

  return {
    bets,
    loading,
    snapshots,
    totalStake,
    totalProfit,
    winCount,
    loseCount,
    winningRate,
    consecutiveLosses,
    bankroll,
    bootstrap,
    addBet,
    updateBet,
    removeBet,
    clearBets,
    recalculateSnapshots,
    settleBet
  }
})
