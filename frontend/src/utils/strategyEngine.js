import { calcKellyStake } from './kelly'

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

export function getStrategyPreset(riskLevel) {
  return PRESETS[riskLevel] || PRESETS.balanced
}

export function getAllPresets() {
  return PRESETS
}

export function calcRecommendedStake({ bankroll, odds, confidence, riskLevel = 'balanced', customConfig = null }) {
  const preset = customConfig || getStrategyPreset(riskLevel)
  const probability = Math.min(confidence / 100, 0.95)

  const kelly = calcKellyStake({
    bankroll,
    odds,
    probability,
    adjustment: preset.kellyFactor
  })

  const fixed = Math.round(bankroll * preset.maxRatio)
  const cap = Math.round(bankroll * preset.maxRatio)
  const amount = Math.min(kelly, fixed, cap)
  const finalAmount = Math.max(amount, 0)

  return {
    amount: finalAmount,
    kelly: Math.round(kelly),
    fixed,
    cap,
    method: kelly <= fixed ? 'Kelly' : '固定比例'
  }
}

export function generateAdvice({ consecutiveWins = 0, consecutiveLosses = 0, drawdown = 0, riskLevel = 'balanced' }) {
  const preset = getStrategyPreset(riskLevel)
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

export function checkRiskStatus({ consecutiveLosses = 0, drawdown = 0, riskLevel = 'balanced' }) {
  const preset = getStrategyPreset(riskLevel)

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
