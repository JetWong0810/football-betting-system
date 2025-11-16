export function calcFixedRatioStake ({ bankroll = 0, ratio = 0.03 } = {}) {
  const pct = Math.min(Math.max(ratio, 0), 1)
  return Number((bankroll * pct).toFixed(2))
}
