import { calcKellyStake } from './kelly'
import { calibrateProbability } from './calibration'

const PRESETS = {
  conservative: {
    label: '保守',
    maxRatio: 0.03,
    kellyFactor: 0.25,
    stopLossLimit: 2,
    maxDrawdown: -0.10,
    minConfidence: 70,
    // 信心档比例:低/中/高,高档 = maxRatio 封顶
    tierRatios: { low: 0.015, mid: 0.025, high: 0.03 }
  },
  balanced: {
    label: '稳健',
    maxRatio: 0.05,
    kellyFactor: 0.5,
    stopLossLimit: 3,
    maxDrawdown: -0.15,
    minConfidence: 60,
    tierRatios: { low: 0.02, mid: 0.035, high: 0.05 }
  },
  aggressive: {
    label: '激进',
    maxRatio: 0.08,
    kellyFactor: 0.75,
    stopLossLimit: 5,
    maxDrawdown: -0.25,
    minConfidence: 50,
    tierRatios: { low: 0.03, mid: 0.05, high: 0.08 }
  }
}

/**
 * 自定义策略：从 configStore 字段构造 preset
 * customConfig 形如 { fixedRatio, kellyFactor, stopLossLimit, maxDrawdown, minConfidence }
 */
function resolveCustomPreset(customConfig) {
  const maxRatio = Number(customConfig?.fixedRatio ?? 0.05)
  // 自定义档的 tierRatios:用户显式指定则用,否则按 maxRatio 派生(低=50%/中=75%/高=100%)
  const tierRatios = customConfig?.tierRatios
    ? {
        low: Number(customConfig.tierRatios.low ?? maxRatio * 0.5),
        mid: Number(customConfig.tierRatios.mid ?? maxRatio * 0.75),
        high: Number(customConfig.tierRatios.high ?? maxRatio)
      }
    : { low: maxRatio * 0.5, mid: maxRatio * 0.75, high: maxRatio }
  return {
    label: '自定义',
    maxRatio,
    kellyFactor: Number(customConfig?.kellyFactor ?? 0.5),
    stopLossLimit: Number(customConfig?.stopLossLimit ?? 3),
    maxDrawdown: Number(customConfig?.maxDrawdown ?? -0.15),
    minConfidence: Number(customConfig?.minConfidence ?? 55),
    tierRatios
  }
}

export function getStrategyPreset(riskLevel, customConfig = null) {
  if (riskLevel === 'custom' && customConfig) return resolveCustomPreset(customConfig)
  return PRESETS[riskLevel] || PRESETS.balanced
}

export function getAllPresets() {
  return PRESETS
}

/**
 * 信心档金额计算(方案A:主观信心档 × 固定比例,绕开置信度/EV/凯利作主决策)
 * @param {object} opts
 * @param {number} opts.effectiveBankroll 有效资金(本金 + 盈利金×计入系数)
 * @param {'low'|'mid'|'high'} opts.tier 信心档
 * @param {string} [opts.riskLevel] 预设名
 * @param {object} [opts.customConfig] 自定义配置
 * @returns {{amount:number, tierRatio:number}}
 */
/** 真实投注按 100 元倍数; 四舍五入到最近百元,不足 50 归零 */
export function roundStakeToHundred(amount) {
  const n = Number(amount)
  if (!Number.isFinite(n) || n <= 0) return 0
  return Math.round(n / 100) * 100
}

export function calcTieredStake({ effectiveBankroll, tier, riskLevel = 'balanced', customConfig = null }) {
  const preset = (riskLevel === 'custom' && customConfig)
    ? resolveCustomPreset(customConfig)
    : (PRESETS[riskLevel] || PRESETS.balanced)
  const ratio = Number(preset.tierRatios?.[tier])
  const bank = Math.max(Number(effectiveBankroll) || 0, 0)
  const raw = Number.isFinite(ratio) && ratio > 0 ? bank * ratio : 0
  return { amount: roundStakeToHundred(raw), tierRatio: Number.isFinite(ratio) ? ratio : 0 }
}

/**
 * 一次性算出三档金额
 * @returns {{low:{amount,tierRatio}, mid:{amount,tierRatio}, high:{amount,tierRatio}}}
 */
export function calcTieredStakes({ effectiveBankroll, riskLevel = 'balanced', customConfig = null }) {
  return {
    low: calcTieredStake({ effectiveBankroll, tier: 'low', riskLevel, customConfig }),
    mid: calcTieredStake({ effectiveBankroll, tier: 'mid', riskLevel, customConfig }),
    high: calcTieredStake({ effectiveBankroll, tier: 'high', riskLevel, customConfig })
  }
}

/**
 * 计算建议投注金额。
 *
 * 关键修正：
 * 1. 不再把模型置信度直接当真实概率——用 calibrateProbability 校准
 * 2. 引入 edge 检查：校准概率 * 赔率 <= 1 时（无正预期）注额为 0
 * 3. 自定义策略（riskLevel='custom'）真正使用 configStore 的 kellyFactor/fixedRatio
 *
 * @param {object} opts
 * @param {number} opts.bankroll 当前可用资金
 * @param {number} opts.odds 投注赔率（小数，如 1.90）
 * @param {number} [opts.confidence] 模型置信度 35-92（会被校准为概率）
 * @param {number} [opts.probability] 直接指定概率 0-1（优先于 confidence，跳过校准，用于手动计算器）
 * @param {string} [opts.riskLevel] 预设名 conservative/balanced/aggressive/custom
 * @param {object} [opts.customConfig] 自定义配置（riskLevel='custom' 时必传）
 * @param {object} [opts.calibration] loadCalibration() 的返回
 */
export function calcRecommendedStake({
  bankroll,
  odds,
  confidence,
  probability,
  riskLevel = 'balanced',
  customConfig = null,
  calibration = null
}) {
  const preset = (riskLevel === 'custom' && customConfig)
    ? resolveCustomPreset(customConfig)
    : (PRESETS[riskLevel] || PRESETS.balanced)

  // 概率来源：手动指定优先；否则用校准后的置信度
  const p = probability != null
    ? Math.min(Math.max(Number(probability), 0), 0.95)
    : calibrateProbability(confidence ?? 0, calibration)

  const o = Number(odds)
  const safeBankroll = Math.max(Number(bankroll) || 0, 0)

  // edge 检查：无正向预期（含赔率无效）时直接 0 注额
  const edge = p * o - 1
  const fixed = Math.round(safeBankroll * preset.maxRatio)
  if (!safeBankroll || !o || o <= 1 || edge <= 0) {
    return { amount: 0, kelly: 0, fixed, method: '无价值', probability: Number(p.toFixed(3)), edge: Number(edge.toFixed(3)) }
  }

  const kelly = calcKellyStake({
    bankroll: safeBankroll,
    odds: o,
    probability: p,
    adjustment: preset.kellyFactor
  })

  // Kelly 与固定比例上限取小（原 cap 与 fixed 同值，已合并）
  const amount = Math.min(kelly, fixed)
  const finalAmount = Math.max(amount, 0)

  return {
    amount: finalAmount,
    kelly: Math.round(kelly),
    fixed,
    method: kelly <= fixed ? 'Kelly' : '固定比例',
    probability: Number(p.toFixed(3)),
    edge: Number(edge.toFixed(3))
  }
}

export function generateAdvice({ consecutiveWins = 0, consecutiveLosses = 0, drawdown = 0, riskLevel = 'balanced', customConfig = null }) {
  const preset = getStrategyPreset(riskLevel, customConfig)
  let text = ''
  let suggestedLevel = riskLevel
  let warning = false

  if (consecutiveLosses >= preset.stopLossLimit) {
    text = `已连败${consecutiveLosses}场，达到止损线，建议暂停投注或降低策略等级。`
    suggestedLevel = riskLevel === 'aggressive' ? 'balanced' : 'conservative'
    warning = true
  } else if (drawdown <= preset.maxDrawdown) {
    const dd = Math.abs(drawdown * 100).toFixed(1)
    text = `最大回撤已达${dd}%，接近止损线，建议减小投注金额。`
    suggestedLevel = riskLevel === 'aggressive' ? 'balanced' : 'conservative'
    warning = true
  } else if (consecutiveWins >= 3) {
    text = `连胜${consecutiveWins}场，状态良好，可维持当前策略。`
  } else if (consecutiveLosses >= 1 && consecutiveLosses < preset.stopLossLimit) {
    text = `已连败${consecutiveLosses}场，建议谨慎投注，控制单注金额。`
  } else {
    text = `当前状态正常，维持${preset.label}策略，合理控制仓位。`
  }

  return { text, suggestedLevel, warning }
}

export function checkRiskStatus({ consecutiveLosses = 0, drawdown = 0, riskLevel = 'balanced', customConfig = null }) {
  const preset = getStrategyPreset(riskLevel, customConfig)

  if (consecutiveLosses >= preset.stopLossLimit) {
    return {
      safe: false,
      level: 'danger',
      reason: `连败${consecutiveLosses}场，已达止损阈值(${preset.stopLossLimit}场)`,
      suggestedAction: '建议暂停投注'
    }
  }

  if (drawdown <= preset.maxDrawdown) {
    return {
      safe: false,
      level: 'danger',
      reason: `回撤${Math.abs(drawdown * 100).toFixed(1)}%，已达止损线(${Math.abs(preset.maxDrawdown * 100)}%)`,
      suggestedAction: '建议暂停或降级策略'
    }
  }

  const lossRatio = consecutiveLosses / preset.stopLossLimit
  if (lossRatio >= 0.6) {
    return {
      safe: true,
      level: 'warning',
      reason: `连败${consecutiveLosses}场，接近止损线`,
      suggestedAction: '建议减小投注金额'
    }
  }

  return {
    safe: true,
    level: 'safe',
    reason: '',
    suggestedAction: ''
  }
}

/**
 * 连不中控手告警(信心档挂钩阈值)
 * 高信心档最早触发(高3/中4/低5把 → strong 弹窗;再+1 → pause 隐藏入口)
 * @param {object} opts
 * @param {number} [opts.consecutiveLosses] 当前连不中数
 * @param {'low'|'mid'|'high'} [opts.lastTier] 最近一注的信心档
 * @param {object} [opts.tierThresholds] {high, mid, low} 各档触发 strong 的连不中数
 * @returns {{level:'normal'|'strong'|'pause', message:string, hideEntry:boolean, strongAt:number, pauseAt:number}}
 */
export function checkControlAlert({
  consecutiveLosses = 0,
  lastTier = 'mid',
  tierThresholds = { high: 3, mid: 4, low: 5 }
}) {
  const strongAt = Number(tierThresholds?.[lastTier]) || 4
  const pauseAt = strongAt + 1
  if (consecutiveLosses >= pauseAt) {
    return { level: 'pause', message: `连不中 ${consecutiveLosses} 把，已隐藏下注入口，请冷静后再战`, hideEntry: true, strongAt, pauseAt }
  }
  if (consecutiveLosses >= strongAt) {
    return { level: 'strong', message: `连不中 ${consecutiveLosses} 把，建议冷静，确认后继续`, hideEntry: false, strongAt, pauseAt }
  }
  return { level: 'normal', message: '', hideEntry: false, strongAt, pauseAt }
}
