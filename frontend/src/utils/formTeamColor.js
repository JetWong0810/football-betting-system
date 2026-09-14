/** 近期战绩 / 交锋历史队名着色：只给焦点队上色，对手一律浅黑。 */

export function sameTeamName(a, b) {
  const x = (a || '').trim()
  const y = (b || '').trim()
  if (!x || !y) return false
  return x === y || x.includes(y) || y.includes(x)
}

export function collectAliases(...parts) {
  const out = []
  const seen = new Set()
  const add = (v) => {
    if (Array.isArray(v)) {
      v.forEach(add)
      return
    }
    const s = String(v || '').trim()
    if (!s || seen.has(s)) return
    seen.add(s)
    out.push(s)
  }
  parts.forEach(add)
  return out
}

export function namesMatch(name, aliases) {
  return collectAliases(aliases).some((a) => sameTeamName(name, a))
}

export function inferFocusVenue(row, focusAliases) {
  if (namesMatch(row.homeTeam, focusAliases)) return 'home'
  if (namesMatch(row.awayTeam, focusAliases)) return 'away'
  return null
}

/**
 * @param {object} row { homeTeam, awayTeam, homeScore, awayScore }
 * @param {'home'|'away'} side
 * @param {string|string[]} focus 焦点队名或别名列表
 * @param {'home'|'away'|null} [venue] 焦点队在该行的场地（交锋优先用）
 */
export function teamResultClass(row, side, focus, venue) {
  const name = side === 'home' ? row.homeTeam : row.awayTeam
  const isFocus = venue === 'home'
    ? side === 'home'
    : venue === 'away'
      ? side === 'away'
      : namesMatch(name, focus)
  if (!isFocus) return 'team-muted'
  const hs = row.homeScore
  const as = row.awayScore
  if (hs == null || as == null || hs === as) return 'team-draw'
  const won = side === 'home' ? hs > as : as > hs
  return won ? 'team-win' : 'team-lose'
}
