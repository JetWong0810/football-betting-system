export function checkStopLoss ({
  consecutiveLosses = 0,
  limit = 3,
  drawdown = 0,
  maxDrawdown = -0.2
} = {}) {
  const shouldPause = consecutiveLosses >= limit
  const warnings = []
  if (shouldPause) {
    warnings.push(`已连续亏损 ${consecutiveLosses} 场，建议休息。`)
  }
  // 回撤阈值由调用方传入 preset.maxDrawdown,与策略档一致(修复原硬编码 -0.2 与 maxDrawdown 不一致的 bug)
  if (drawdown < maxDrawdown) {
    const pct = Math.abs(maxDrawdown * 100).toFixed(0)
    warnings.push(`本周期回撤已超过 ${pct}%，请缩减仓位。`)
  }
  return {
    shouldPause,
    warnings
  }
}
