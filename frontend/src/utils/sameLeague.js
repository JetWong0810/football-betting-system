/** 可开「同赛事」同赔开关的联赛 — 与后端 SAME_LEAGUE_ELIGIBLE 对齐(不含日本) */
const SAME_LEAGUE_ELIGIBLE = new Set([
  '英超', '英冠', '英甲',
  '西甲',
  '意甲',
  '德甲', '德乙',
  '法甲', '法乙',
  '葡超',
  '荷甲', '荷乙',
  '瑞超', '瑞典超',
  '挪超',
  '美职联', '美职',
  '巴甲',
  'K1联赛', '韩职',
  '澳超',
  '俄超',
  '比甲',
  '阿甲',
  '墨西联',
  '欧冠',
  '欧罗巴',
])

export function isSameLeagueEligible(league) {
  const name = String(league || '').trim()
  if (!name) return false
  return SAME_LEAGUE_ELIGIBLE.has(name)
}
