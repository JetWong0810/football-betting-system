export function calcKellyStake ({
  bankroll = 0,
  odds = 1,
  probability = 0,
  adjustment = 0.5
} = {}) {
  const b = Math.max(Number(odds) - 1, 0)
  const p = Math.min(Math.max(probability, 0), 1)
  if (!bankroll || !b) return 0
  const kelly = ((p * (b + 1)) - 1) / b
  const ratio = Math.max(Math.min(kelly * adjustment, 1), 0)
  return Number((bankroll * ratio).toFixed(2))
}
