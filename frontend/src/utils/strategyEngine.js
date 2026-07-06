import { calcKellyStake } from './kelly'
import { calibrateProbability } from './calibration'

const PRESETS = {
  conservative: {
    label: '保守',
    maxRatio: 0.03,
    kellyFactor: 0.25,
    stopLossLimit: 2,
    maxDrawdown: -0.10,
    minConfidence: 70
  },
  balanced: {
    label: '稳健',
    maxRatio: 0.05,
    kellyFactor: 0.5,
    stopLossLimit: 3,
    maxDrawdown: -0.15,
    minConfidence: 60
  },
  aggressive: {
    label: '激进',
    maxRatio: 0.08,
    kellyFactor: 0.75,
    stopLossLimit: 5,
    maxDrawdown: -0.25,
    minConfidence: 50
  }
}

/**
 * 自定义策略：从 configStore 字段构造 preset
 * customConfig 形如 { fixedRatio, kellyFactor, stopLossLimit, maxDrawdown, minConfidence }
 */
function resolveCustomPreset(customConfig) {
  return {
    label: '自定义',
    maxRatio: Number(customConfig?.fixedRatio ?? 0.05),
    kellyFactor: Number(customConfig?.kellyFactor ?? 0.5),
    stopLossLimit: Number(customConfig?.stopLossLimit ?? 3),
    maxDrawdown: Number(customConfig?.maxDrawdown ?? -0.15),
    minConfidence: Number(customConfig?.minConfidence ?? 55)
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
