/**
 * 模拟投注: 亚盘多盘口枚举 + 同赔历史重算安全分 + 串关乘积
 * 盘口约定: 标准亚盘 负=主让; 无赔率展示。
 */

export const AH_STEP = 0.25
export const AH_SPAN = 3 // 上下各 3 档 → 共 7 线

/** 主盘上下各 N 档 → 主队视角 7 线 */
export function buildAhLines(mainHc, span = AH_SPAN, step = AH_STEP) {
  if (mainHc == null || Number.isNaN(Number(mainHc))) return []
  const hc = Number(mainHc)
  const lines = []
  for (let k = -span; k <= span; k++) {
    const line = roundAh(hc + k * step)
    lines.push({
      line,
      offset: k,
      isMain: k === 0,
      homeLine: line,
      awayLine: roundAh(-line),
    })
  }
  return lines
}

export function roundAh(v) {
  // 避免 0.1+0.2 浮点噪声, 四分盘精确到 0.01
  const n = Math.round(Number(v) * 100) / 100
  return Object.is(n, -0) ? 0 : n
}

/** 展示: 0 / +0.25 / -1 */
export function fmtAhLine(h) {
  if (h == null || h === '') return '-'
  const n = Number(h)
  if (Number.isNaN(n)) return '-'
  if (Object.is(n, -0) || n === 0) return '0'
  const abs = Math.abs(n)
  const s = abs % 1 === 0 ? String(abs) : abs.toFixed(2).replace(/0$/, '')
  return (n > 0 ? '+' : '-') + s
}

/**
 * 主盘下上盘侧。平手盘退用 spf 低赔方(win=主/loss=客)。
 * @returns {'home'|'away'|null}
 */
export function upperSideForHc(hc, lowKey = null) {
  if (hc == null || Number.isNaN(Number(hc))) return null
  const h = Number(hc)
  if (Math.abs(h) < 1e-9) return lowKey === 'loss' ? 'away' : 'home'
  return h < 0 ? 'home' : 'away'
}

/**
 * 结算单侧选择。与后端 settle_ah_selection 同构。
 * @returns {{ label, units, key }|null}
 */
export function settleAhSelection(homeScore, awayScore, side, line) {
  if (side !== 'home' && side !== 'away') return null
  if (line == null || Number.isNaN(Number(line))) return null
  const hs = Number(homeScore)
  const aws = Number(awayScore)
  if (Number.isNaN(hs) || Number.isNaN(aws)) return null
  const ln = Number(line)
  const net = side === 'home' ? (hs - aws) + ln : (aws - hs) + ln
  const a = Math.abs(net)
  if (a < 1e-9) return { label: '走水', units: 0, key: 'push' }
  const half = Math.abs(a - 0.25) < 1e-9
  if (net > 0) {
    return half
      ? { label: '半赢', units: 0.5, key: 'half_win' }
      : { label: '全赢', units: 1, key: 'win' }
  }
  return half
    ? { label: '半输', units: -0.5, key: 'half_lose' }
    : { label: '全输', units: -1, key: 'lose' }
}

function parseScorePair(m) {
  if (m == null) return null
  if (m.homeScore != null && m.awayScore != null) {
    const hs = Number(m.homeScore)
    const aws = Number(m.awayScore)
    if (!Number.isNaN(hs) && !Number.isNaN(aws)) return [hs, aws]
  }
  const s = m.score
  if (typeof s === 'string' && /^\d+-\d+$/.test(s)) {
    const [a, b] = s.split('-').map(Number)
    if (!Number.isNaN(a) && !Number.isNaN(b)) return [a, b]
  }
  return null
}

/**
 * 用同赔历史比分按目标线重算安全分。
 * safetyScore = round(100 * (0.7*notLoseRate + 0.3*clip((expUnit+1)/2,0,1)))
 */
export function scoreSelectionFromHistory(matches, side, line) {
  const list = Array.isArray(matches) ? matches : []
  let n = 0
  let notLose = 0
  let sumU = 0
  const dist = { win: 0, half_win: 0, push: 0, half_lose: 0, lose: 0 }
  for (const m of list) {
    const pair = parseScorePair(m)
    if (!pair) continue
    const settled = settleAhSelection(pair[0], pair[1], side, line)
    if (!settled) continue
    n += 1
    sumU += settled.units
    dist[settled.key] = (dist[settled.key] || 0) + 1
    if (settled.key === 'win' || settled.key === 'half_win' || settled.key === 'push') {
      notLose += 1
    }
  }
  if (n < 3) return null
  const notLoseRate = notLose / n
  const expUnit = sumU / n
  const evNorm = Math.max(0, Math.min(1, (expUnit + 1) / 2))
  const safetyScore = Math.round(100 * (0.7 * notLoseRate + 0.3 * evNorm))
  return {
    source: 'history',
    sample: n,
    notLoseRate: Math.round(notLoseRate * 1000) / 10,
    expUnit: Math.round(expUnit * 1000) / 1000,
    safetyScore,
    dist,
  }
}

/**
 * 样本不足时的偏移启发式。
 * 与 F6 同向且更受让 → 加分; 更让球 → 减分; 反向再扣。
 */
export function scoreSelectionHeuristic({
  mainHc,
  side,
  line,
  f6Direction = 'neutral',
  refScore = 0,
  lowKey = null,
}) {
  const hc = Number(mainHc)
  if (Number.isNaN(hc) || line == null) {
    return { source: 'heuristic', sample: 0, safetyScore: 50, notLoseRate: null, expUnit: null, dist: null }
  }
  const upper = upperSideForHc(hc, lowKey)
  const selLine = Number(line)
  // 主队线视角偏移: home 用 line-hc; away 用 line-(-hc)=line+hc → 统一到「相对主盘受让方向」
  // 受让方向: 对选中侧, line 越大越受让(越安全若同向上盘)
  const mainLineForSide = side === 'home' ? hc : roundAh(-hc)
  const offsetSteps = Math.round((selLine - mainLineForSide) / AH_STEP)

  let score = 50 + Number(refScore || 0) * 0.15
  const aligned =
    (f6Direction === 'upper' && side === upper) ||
    (f6Direction === 'lower' && upper && side !== upper)

  if (f6Direction === 'upper' || f6Direction === 'lower') {
    if (aligned) {
      score += offsetSteps * 8
    } else {
      score -= 15
      score -= offsetSteps * 8 // 反向时更受让反而更差(帮了对面)
    }
  } else {
    // 中性: 略偏保守(受让)加一点
    score += offsetSteps * 3
  }

  const safetyScore = Math.max(15, Math.min(95, Math.round(score)))
  return {
    source: 'heuristic',
    sample: 0,
    safetyScore,
    notLoseRate: null,
    expUnit: null,
    dist: null,
    offsetSteps,
    aligned: !!aligned,
  }
}

/** 综合评分: 有样本用历史, 否则启发式 */
export function scoreSelection(ctx) {
  const hist = scoreSelectionFromHistory(ctx.matches, ctx.side, ctx.line)
  if (hist) return hist
  return scoreSelectionHeuristic(ctx)
}

/** 一场的 14 格(7线×主客)评分表 */
export function buildLineScoreboard(matchCtx) {
  const {
    ahHandicap,
    matches = [],
    f6Direction = 'neutral',
    refScore = 0,
    lowKey = null,
  } = matchCtx || {}
  const lines = buildAhLines(ahHandicap)
  const upper = upperSideForHc(ahHandicap, lowKey)
  return lines.map((row) => {
    const homeScore = scoreSelection({
      matches,
      side: 'home',
      line: row.homeLine,
      mainHc: ahHandicap,
      f6Direction,
      refScore,
      lowKey,
    })
    const awayScore = scoreSelection({
      matches,
      side: 'away',
      line: row.awayLine,
      mainHc: ahHandicap,
      f6Direction,
      refScore,
      lowKey,
    })
    return {
      ...row,
      home: { side: 'home', line: row.homeLine, ...homeScore },
      away: { side: 'away', line: row.awayLine, ...awayScore },
      recommendHome: upper === 'home',
      recommendAway: upper === 'away',
    }
  })
}

/** 串关安全分 = 100 * ∏(safety_i/100) */
export function parlaySafetyScore(scores) {
  const list = (scores || []).map(Number).filter((n) => !Number.isNaN(n))
  if (!list.length) return null
  if (list.length === 1) return Math.round(list[0])
  const prod = list.reduce((p, s) => p * (s / 100), 1)
  return Math.round(100 * prod)
}

export function weakestLeg(legs) {
  if (!legs?.length) return null
  return legs.reduce((w, leg) =>
    (leg.safetyScore ?? 0) < (w.safetyScore ?? 0) ? leg : w
  )
}

/** 从比赛卡 spf 推低赔方 key */
export function lowKeyFromSpf(spf) {
  const odds = spf?.initial || spf?.current
  if (!odds) return null
  const w = Number(odds.win)
  const d = Number(odds.draw)
  const l = Number(odds.lose)
  if ([w, d, l].some((x) => Number.isNaN(x))) return null
  const m = Math.min(w, d, l)
  if (m === w) return 'win'
  if (m === l) return 'loss'
  return 'draw'
}

/**
 * 相对主盘的放宽/收紧说明(串关单用)。
 * 线越大越受让 → 放宽(更保守)。
 */
export function legOffsetHint(leg) {
  if (!leg || leg.mainHc == null || leg.line == null) return ''
  const mainForSide = leg.side === 'home' ? Number(leg.mainHc) : roundAh(-Number(leg.mainHc))
  const steps = Math.round((Number(leg.line) - mainForSide) / AH_STEP)
  if (steps === 0) return '主盘线'
  const delta = Math.abs(steps) * AH_STEP
  const deltaStr = Number.isInteger(delta) ? String(delta) : delta.toFixed(2).replace(/0$/, '')
  if (steps > 0) {
    const nl = leg.notLoseRate != null ? `，不输率 ${leg.notLoseRate}%` : ''
    return `相对主盘放宽 ${deltaStr}${nl}`
  }
  return `相对主盘收紧 ${deltaStr}(更激进)`
}

/** F6 推荐侧是否为该 side */
export function isF6RecommendedSide(side, f6Direction, mainHc, lowKey = null) {
  const upper = upperSideForHc(mainHc, lowKey)
  if (!upper || (f6Direction !== 'upper' && f6Direction !== 'lower')) return false
  if (f6Direction === 'upper') return side === upper
  return side !== upper
}

/**
 * 由安全分建议信心档(可改,不作强制)。
 * 用串关综合分; 样本弱/启发式时最高 mid。
 * @param {object} opts
 * @param {number|null} opts.combinedSafety
 * @param {Array} [opts.legs]
 * @returns {{ tier:'low'|'mid'|'high', reason:string, capped:boolean }}
 */
export function suggestTierFromSafety({ combinedSafety, legs = [] } = {}) {
  const score = Number(combinedSafety)
  let tier = 'mid'
  if (!Number.isNaN(score)) {
    if (score >= 70) tier = 'high'
    else if (score >= 50) tier = 'mid'
    else tier = 'low'
  }
  const weakSample = legs.some(
    (l) => l.scoreSource === 'heuristic' || (l.sample != null && Number(l.sample) < 5)
  )
  const neutralHeavy = legs.length > 0 && legs.every((l) => l.f6Direction === 'neutral')
  let capped = false
  let reason = Number.isNaN(score)
    ? '无安全分,默认中档'
    : `串关安全分 ${Math.round(score)} → ${tier === 'high' ? '高' : tier === 'mid' ? '中' : '低'}档`
  if (tier === 'high' && (weakSample || neutralHeavy)) {
    tier = 'mid'
    capped = true
    reason += weakSample ? '；样本弱封顶中档' : '；同赔中性封顶中档'
  }
  return { tier, reason, capped }
}
