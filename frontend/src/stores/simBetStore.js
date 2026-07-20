import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  parlaySafetyScore,
  settleAhSelection,
  weakestLeg,
  fmtAhLine,
} from '@/utils/simBet'

const STORAGE_KEY = 'sim_bet_slips_v1'

function loadConfirmed() {
  try {
    const raw = uni.getStorageSync(STORAGE_KEY)
    if (!raw) return []
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveConfirmed(list) {
  try {
    uni.setStorageSync(STORAGE_KEY, JSON.stringify(list))
  } catch (e) {
    console.warn('simBet persist failed', e)
  }
}

/**
 * 模拟投注车: 当前草稿腿 + 已确认单(localStorage)。
 * 每场最多 1 腿; 不接入真实资金。
 */
export const useSimBetStore = defineStore('simBet', () => {
  const simMode = ref(false)
  /** @type {import('vue').Ref<Array>} */
  const legs = ref([])
  /** 已确认的模拟单 */
  const confirmed = ref(loadConfirmed())

  const count = computed(() => legs.value.length)
  const hasLegs = computed(() => count.value > 0)
  const safetyScores = computed(() => legs.value.map((l) => l.safetyScore).filter((s) => s != null))
  const combinedSafety = computed(() => parlaySafetyScore(safetyScores.value))
  const weakLeg = computed(() => weakestLeg(legs.value))
  const parlayLabel = computed(() => {
    const n = count.value
    if (n <= 0) return ''
    if (n === 1) return '单关'
    return `${n}串1`
  })

  function findLeg(matchId) {
    return legs.value.find((l) => l.matchId === matchId) || null
  }

  /**
   * 添加/替换一场的选择
   * @param {Object} leg
   * @param {string} leg.matchId
   * @param {string} leg.homeTeam
   * @param {string} leg.awayTeam
   * @param {string} [leg.league]
   * @param {string} [leg.matchTime]
   * @param {number} leg.mainHc 主盘
   * @param {'home'|'away'} leg.side
   * @param {number} leg.line 所选侧盘口
   * @param {number} leg.safetyScore
   * @param {string} [leg.scoreSource] history|heuristic
   * @param {number} [leg.sample]
   * @param {string} [leg.f6Direction]
   * @param {string} [leg.date] 售卖日期 yyyy-mm-dd
   */
  function setLeg(leg) {
    if (!leg?.matchId || !leg.side || leg.line == null) return
    const next = {
      ...leg,
      line: Number(leg.line),
      mainHc: leg.mainHc != null ? Number(leg.mainHc) : null,
      safetyScore: leg.safetyScore != null ? Number(leg.safetyScore) : null,
      sideLabel: leg.side === 'home' ? '主' : '客',
      lineLabel: fmtAhLine(leg.line),
      pickLabel: `${leg.side === 'home' ? '主' : '客'} ${fmtAhLine(leg.line)}`,
      updatedAt: Date.now(),
    }
    const idx = legs.value.findIndex((l) => l.matchId === leg.matchId)
    if (idx >= 0) {
      legs.value.splice(idx, 1, next)
    } else {
      legs.value.push(next)
    }
  }

  function removeLeg(matchId) {
    legs.value = legs.value.filter((l) => l.matchId !== matchId)
  }

  function clearLegs() {
    legs.value = []
  }

  function toggleSimMode(force) {
    simMode.value = force == null ? !simMode.value : !!force
    if (!simMode.value) {
      // 关闭模式不清草稿, 方便再开; 仅关掉 UI
    }
  }

  /** 确认当前草稿为一次模拟单(可附带推荐档/金额,不进真单) */
  function confirmSlip(extra = {}) {
    if (!legs.value.length) return null
    const slip = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      createdAt: Date.now(),
      date: legs.value[0]?.date || '',
      parlayLabel: parlayLabel.value,
      combinedSafety: combinedSafety.value,
      legs: legs.value.map((l) => ({ ...l })),
      status: 'pending', // pending | settled
      result: null, // win | half | push | lose | null
      suggestedTier: extra.suggestedTier || null,
      suggestedStake: extra.suggestedStake != null ? Number(extra.suggestedStake) : null,
      tierReason: extra.tierReason || '',
    }
    confirmed.value = [slip, ...confirmed.value].slice(0, 50)
    saveConfirmed(confirmed.value)
    legs.value = []
    return slip
  }

  /**
   * 用真实比分结算已确认单中的腿
   * @param {Record<string,{homeScore:number,awayScore:number}>} scoreMap
   */
  function settleWithScores(scoreMap) {
    if (!scoreMap || !confirmed.value.length) return
    let changed = false
    confirmed.value = confirmed.value.map((slip) => {
      if (slip.status === 'settled') return slip
      const settledLegs = slip.legs.map((leg) => {
        const sc = scoreMap[leg.matchId]
        if (!sc || sc.homeScore == null || sc.awayScore == null) {
          return { ...leg, settle: leg.settle || null }
        }
        const s = settleAhSelection(sc.homeScore, sc.awayScore, leg.side, leg.line)
        changed = true
        return { ...leg, settle: s, actualScore: `${sc.homeScore}-${sc.awayScore}` }
      })
      if (settledLegs.some((l) => !l.settle)) {
        return { ...slip, legs: settledLegs }
      }
      // 串关聚合: 有一腿全输→整串输; 全走水→走水; 含半则 half; 否则 win
      const keys = settledLegs.map((l) => l.settle.key)
      let result = 'win'
      if (keys.some((k) => k === 'lose')) result = 'lose'
      else if (keys.every((k) => k === 'push')) result = 'push'
      else if (keys.some((k) => k === 'half_lose') && keys.some((k) => k === 'half_win' || k === 'win' || k === 'push')) {
        result = 'half'
      } else if (keys.some((k) => k === 'half_lose')) result = 'lose'
      else if (keys.some((k) => k === 'half_win') || keys.some((k) => k === 'push')) result = 'half'
      changed = true
      return { ...slip, legs: settledLegs, status: 'settled', result }
    })
    if (changed) saveConfirmed(confirmed.value)
  }

  function removeConfirmed(id) {
    confirmed.value = confirmed.value.filter((s) => s.id !== id)
    saveConfirmed(confirmed.value)
  }

  function clearConfirmed() {
    confirmed.value = []
    saveConfirmed([])
  }

  return {
    simMode,
    legs,
    confirmed,
    count,
    hasLegs,
    combinedSafety,
    weakLeg,
    parlayLabel,
    findLeg,
    setLeg,
    removeLeg,
    clearLegs,
    toggleSimMode,
    confirmSlip,
    settleWithScores,
    removeConfirmed,
    clearConfirmed,
  }
})
