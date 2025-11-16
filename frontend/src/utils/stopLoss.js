export function checkStopLoss ({
  consecutiveLosses = 0,
  limit = 3,
  drawdown = 0
} = {}) {
  const shouldPause = consecutiveLosses >= limit
  const warnings = []
  if (shouldPause) {
    warnings.push(`已连续亏损 ${consecutiveLosses} 场，建议休息。`)
  }
  if (drawdown < -0.2) {
    warnings.push('本周期回撤已超过 20%，请缩减仓位。')
  }
  return {
    shouldPause,
    warnings
  }
}
