/** 日本本土赛事(日职/日乙/天皇杯/联杯等) — 与后端 JP_LEAGUES 对齐 */
const JP_LEAGUES = new Set(['日职', '日职乙', '日乙', '日联杯', '日天皇杯', '日超杯'])

export function isJapanLeague(league) {
  const name = String(league || '').trim()
  if (!name) return false
  if (JP_LEAGUES.has(name)) return true
  return (
    name.startsWith('日职') ||
    name.startsWith('日乙') ||
    name.startsWith('日天皇') ||
    name.startsWith('日联')
  )
}
