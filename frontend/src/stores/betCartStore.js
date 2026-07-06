import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 投注车 Store
 * 管理用户选择的投注项
 */
export const useBetCartStore = defineStore('betCart', () => {
  // 已选择的投注项列表
  const selections = ref([])
  
  // 单注金额（固定为2元）
  const unitStake = 2
  
  // 投注倍数
  const multiple = ref(1)
  
  // 投注类型：'single' 单关 | 'parlay' 串关（自动判断，不需要手动设置）
  // 串关组合类型：'2_1' = 2串1, '3_1' = 3串1, 等
  const parlayType = ref('2_1') // 默认2串1

  /**
   * 添加或移除投注项
   * @param {Object} item - 投注项
   * @param {String} item.matchId - 比赛ID
   * @param {String} item.homeTeam - 主队
   * @param {String} item.awayTeam - 客队
   * @param {String} item.league - 联赛
   * @param {String} item.matchDate - 比赛日期
   * @param {String} item.matchTime - 比赛时间
   * @param {String} item.playType - 玩法类型 'had'|'hhad'|'ttg'|'hafu'|'crs'
   * @param {String} item.playName - 玩法名称 '胜平负'|'让球胜平负'等
   * @param {String} item.selection - 选择项 'win'|'draw'|'lose'|具体选项
   * @param {String} item.selectionLabel - 选择项标签 '胜'|'平'|'负'等
   * @param {Number} item.odds - 赔率
   * @param {Number} item.handicap - 让球数（如果有）
   * @param {Boolean} item.isSingle - 是否支持单关
   */
  function toggleSelection(item) {
    const key = `${item.matchId}-${item.playType}-${item.selection}`
    const existingIndex = selections.value.findIndex(
      s => `${s.matchId}-${s.playType}-${s.selection}` === key
    )

    if (existingIndex > -1) {
      // 如果已存在，则移除
      selections.value.splice(existingIndex, 1)
    } else {
      // 检查同一场比赛已有多少选项
      const sameMatchSelections = selections.value.filter(s => s.matchId === item.matchId)
      if (sameMatchSelections.length >= 2) {
        // 已有2个选项，替换最早添加的那个
        const oldestIndex = selections.value.findIndex(s => s.key === sameMatchSelections[0].key)
        selections.value.splice(oldestIndex, 1, {
          ...item,
          key,
          addedAt: Date.now()
        })
      } else {
        // 未满2个，直接添加
        selections.value.push({
          ...item,
          key,
          addedAt: Date.now()
        })
      }
    }

    // 自动调整串关类型
    updateParlayType()
  }

  /**
   * 已选比赛场次数（去重）
   */
  const matchCount = computed(() => {
    const ids = new Set(selections.value.map(s => s.matchId))
    return ids.size
  })

  /**
   * 按比赛分组的选项
   */
  const groupedSelections = computed(() => {
    const map = {}
    selections.value.forEach(s => {
      if (!map[s.matchId]) {
        map[s.matchId] = {
          matchId: s.matchId,
          homeTeam: s.homeTeam,
          awayTeam: s.awayTeam,
          league: s.league,
          matchDate: s.matchDate,
          matchTime: s.matchTime,
          items: []
        }
      }
      map[s.matchId].items.push(s)
    })
    return Object.values(map)
  })

  /**
   * 自动更新串关类型
   */
  function updateParlayType() {
    const mc = matchCount.value
    if (mc >= 2) {
      const [current] = parlayType.value.split('_').map(Number)
      if (current > mc) {
        parlayType.value = `${mc}_1`
      }
    }
  }

  /**
   * 检查某项是否已选中
   */
  function isSelected(matchId, playType, selection) {
    const key = `${matchId}-${playType}-${selection}`
    return selections.value.some(s => s.key === key)
  }

  /**
   * 清空投注车
   */
  function clearCart() {
    selections.value = []
    multiple.value = 1
    parlayType.value = '2_1'
  }

  /**
   * 移除指定项
   */
  function removeSelection(key) {
    selections.value = selections.value.filter(s => s.key !== key)
    updateParlayType()
  }

  /**
   * 设置串关类型
   */
  function setParlayType(type) {
    parlayType.value = type
  }

  // ========== 计算属性 ==========

  /**
   * 已选数量（总选项数）
   */
  const count = computed(() => selections.value.length)

  /**
   * 是否有选项
   */
  const hasSelections = computed(() => selections.value.length > 0)

  /**
   * 投注模式（基于比赛场次数判断）
   */
  const betMode = computed(() => {
    return matchCount.value >= 2 ? 'parlay' : 'single'
  })

  /**
   * 是否单关模式
   */
  const isSingleMode = computed(() => matchCount.value === 1)

  /**
   * 是否串关模式
   */
  const isParlayMode = computed(() => matchCount.value >= 2)

  /**
   * 计算组合数 C(n, m)
   */
  function getCombinationCount(n, m) {
    if (m > n) return 0
    if (m === 0 || m === n) return 1
    
    let result = 1
    for (let i = 0; i < m; i++) {
      result *= (n - i)
      result /= (i + 1)
    }
    return Math.round(result)
  }

  /**
   * 获取所有组合
   */
  function getCombinations(arr, m) {
    if (m === 1) return arr.map(item => [item])
    if (m === arr.length) return [arr]
    
    const result = []
    for (let i = 0; i <= arr.length - m; i++) {
      const head = arr[i]
      const tailCombinations = getCombinations(arr.slice(i + 1), m - 1)
      for (const tail of tailCombinations) {
        result.push([head, ...tail])
      }
    }
    return result
  }

  /**
   * 串关注数（复式：各场选项数乘积 × 场次组合数）
   */
  const parlayCount = computed(() => {
    if (!isParlayMode.value) return 1

    const [m] = parlayType.value.split('_').map(Number)
    const groups = groupedSelections.value
    const n = groups.length

    if (m > n) return 0

    const matchCombinations = getCombinations(groups, m)
    let totalBets = 0
    for (const combo of matchCombinations) {
      const bets = combo.reduce((acc, group) => acc * group.items.length, 1)
      totalBets += bets
    }
    return totalBets
  })

  /**
   * 总投注金额（自动计算）
   * 金额 = 注数 × 倍数 × 单注金额(2元)
   */
  const totalStake = computed(() => {
    return parlayCount.value * multiple.value * unitStake
  })

  /**
   * 总赔率（串关复式时为所有注的平均赔率）
   */
  const totalOdds = computed(() => {
    if (selections.value.length === 0) return 0

    // 单关模式（只有1场比赛）
    if (isSingleMode.value) {
      // 同一场有多个选项时取平均赔率
      const odds = selections.value.map(s => s.odds || 0)
      return odds.reduce((a, b) => a + b, 0) / odds.length
    }

    // 串关模式：计算所有注的平均赔率
    const [m] = parlayType.value.split('_').map(Number)
    const groups = groupedSelections.value
    const n = groups.length

    if (m > n) return 0

    const matchCombinations = getCombinations(groups, m)
    let totalOddsSum = 0
    let totalBets = 0

    for (const combo of matchCombinations) {
      // 对每个场次组合，展开各场选项的笛卡尔积
      const cartesian = combo.reduce((acc, group) => {
        const result = []
        for (const prev of acc) {
          for (const item of group.items) {
            result.push([...prev, item])
          }
        }
        return result
      }, [[]])

      for (const bet of cartesian) {
        const betOdds = bet.reduce((acc, item) => acc * (item.odds || 1), 1)
        totalOddsSum += betOdds
        totalBets++
      }
    }

    return totalBets > 0 ? totalOddsSum / totalBets : 0
  })

  /**
   * 预计最高奖金
   * 奖金 = 总投注金额 × 平均赔率
   */
  const maxWinning = computed(() => {
    if (selections.value.length === 0) return 0
    
    const total = totalStake.value * totalOdds.value
    return Number(total.toFixed(2))
  })

  /**
   * 串关类型描述（如：单关、2串1、3串1）
   */
  const parlayTypeLabel = computed(() => {
    if (isSingleMode.value) {
      const itemCount = selections.value.length
      return itemCount > 1 ? `单关(复式${itemCount}注)` : '单关'
    }
    return parlayType.value.replace('_', '串')
  })

  /**
   * 是否所有选项都支持单关
   */
  const allSupportSingle = computed(() => {
    if (selections.value.length === 0) return false
    return selections.value.every(s => s.isSingle)
  })

  /**
   * 是否可以投注
   * 规则：
   * 1. 至少有一项选择
   * 2. 如果是单关（仅1场比赛），必须支持单关
   * 3. 如果是串关（>=2场比赛），自动允许
   */
  const canBet = computed(() => {
    if (!hasSelections.value) return false

    // 单关模式：必须支持单关
    if (isSingleMode.value) {
      return allSupportSingle.value
    }

    // 串关模式：自动允许
    return true
  })

  /**
   * 不能投注的原因
   */
  const cannotBetReason = computed(() => {
    if (!hasSelections.value) return '请选择投注项'
    if (isSingleMode.value && !allSupportSingle.value) {
      return '该选项不支持单关，请选择更多场次进行串关'
    }
    return ''
  })

  /**
   * 转换为投注记录格式
   */
  function toBetRecord() {
    if (!canBet.value) return null

    const legs = selections.value.map(s => ({
      id: s.key,
      homeTeam: s.homeTeam,
      awayTeam: s.awayTeam,
      league: s.league,
      matchTime: `${s.matchDate} ${s.matchTime}`,
      matchDate: s.matchDate,
      betType: s.playName,
      selection: s.selectionLabel,
      odds: s.odds,
      handicap: s.handicap,
      note: s.handicap ? `${s.playName} (${s.handicap > 0 ? '+' : ''}${s.handicap})` : s.playName
    }))

    return {
      wagerType: betMode.value,
      parlayType: isParlayMode.value ? parlayType.value : null,
      stake: totalStake.value,
      odds: Number(totalOdds.value.toFixed(2)),
      result: 'pending',
      betTime: new Date().toISOString().slice(0, 16).replace('T', ' '),
      legs
    }
  }

  return {
    // 状态
    selections,
    multiple,
    parlayType,

    // 计算属性
    count,
    matchCount,
    groupedSelections,
    hasSelections,
    betMode,
    isSingleMode,
    isParlayMode,
    parlayCount,
    totalStake,
    totalOdds,
    maxWinning,
    parlayTypeLabel,
    canBet,
    cannotBetReason,
    allSupportSingle,

    // 方法
    toggleSelection,
    isSelected,
    clearCart,
    removeSelection,
    setParlayType,
    toBetRecord
  }
})

