/**
 * 同赔页稳度：用户筛选逻辑的计分版。
 *
 * 入场闸门（不算分）：
 *   1. 方向与低赔变动配对：下盘+下降 / 上盘+上升
 *   2. 推荐还要求同赔≥8（3 场 67% 不如 8 场 63%，小样本没有说服力）
 *   3. 仅让球胜平负(nspf)不同赔：池不可靠，不进推荐、不计同赔/赢盘/分数
 *
 * 稳度 =
 *   +3 下盘 / +1 上盘
 *   +2 深盘 |亚盘|>0.5；0.5 下盘仍算深盘
 *   +2 浅盘上盘 |亚盘|≤0.5（平手/半球上盘可推，与深盘互斥）
 *   +2 单关
 *   +3 同赔≥8  / +1 同赔 5–7
 *   +2 赢盘≥65（仅同赔≥8 才计，避免 2/3=67% 刷分）
 *   +1 分数≥48（仅同赔≥8）
 *   +1 分数≥60（仅同赔≥8）
 *
 * 同分：同赔场次 → 赢盘率 → 分数
 */

export const STABLE_REC_MAX = 2
export const STABLE_REC_GAP = 3
export const SAMPLE_REC_MIN = 8

export function isDirMovePaired(direction, move) {
  return (direction === 'lower' && move === 'down')
    || (direction === 'upper' && move === 'up')
}

export function calcStability({
  direction,
  move,
  handicap,
  isSingle,
  sample,
  hitPct,
  refScore,
  oddsKind,
} = {}) {
  const dir = direction === 'upper' || direction === 'lower' ? direction : 'neutral'
  const nspf = oddsKind === 'nspf'
  const n = Number(sample) || 0
  const paired = isDirMovePaired(dir, move)
  const thick = !nspf && n >= SAMPLE_REC_MIN
  const reasons = []
  let score = 0

  if (dir === 'lower') {
    score += 3
    reasons.push('下盘')
  } else if (dir === 'upper') {
    score += 1
    reasons.push('上盘')
  } else {
    return {
      score: 0, paired: false, recommendable: false,
      reasons, dir, sampleThin: true, nspf: false, shallowUpper: false,
    }
  }

  const hc = handicap == null ? null : Math.abs(Number(handicap))
  const shallow = hc != null && !Number.isNaN(hc) && hc <= 0.5 + 1e-9
  const deep = hc != null && !Number.isNaN(hc) && hc + 1e-9 >= 0.5
  const shallowUpper = dir === 'upper' && shallow
  if (shallowUpper) {
    score += 2
    reasons.push('浅盘上盘')
  } else if (deep) {
    score += 2
    reasons.push('深盘')
  }
  if (isSingle) {
    score += 2
    reasons.push('单关')
  }
  if (!nspf && n >= SAMPLE_REC_MIN) {
    score += 3
    reasons.push('同赔≥8')
  } else if (!nspf && n >= 5) {
    score += 1
    reasons.push('同赔≥5')
  }
  if (thick && (Number(hitPct) || 0) >= 65) {
    score += 2
    reasons.push('赢盘≥65')
  }
  const ref = refScore == null ? -1 : Number(refScore)
  if (thick && ref >= 48) {
    score += 1
    reasons.push('分数≥48')
  }
  if (thick && ref >= 60) {
    score += 1
    reasons.push('分数≥60')
  }
  return {
    score,
    paired,
    recommendable: paired && thick,
    reasons,
    dir,
    sampleThin: !nspf && !thick,
    nspf,
    shallowUpper,
  }
}

export function cmpStability(a, b) {
  if (b.score !== a.score) return b.score - a.score
  if (b.sample !== a.sample) return b.sample - a.sample
  if (b.hitPct !== a.hitPct) return b.hitPct - a.hitPct
  return b.refScore - a.refScore
}

/** ranked 已按 cmpStability 排好。第 2 名稳度差 ≥ gap 则只留第 1；浅盘上盘例外，仍可当稳2。 */
export function pickStableRecs(ranked, { max = STABLE_REC_MAX, gap = STABLE_REC_GAP } = {}) {
  const pool = ranked.filter((x) => x.recommendable !== false)
  if (!pool.length) return []
  if (pool.length === 1) return pool.slice(0, 1)
  if ((pool[0].score - pool[1].score) >= gap && !pool[1].shallowUpper) return pool.slice(0, 1)
  return pool.slice(0, max)
}
