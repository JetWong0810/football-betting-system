import { calcSimilarStats } from '@/utils/similarStats'

/** 个人分析星级 + 分类点选结构 */

export const RATING_LABELS = {
  1: '放弃',
  2: '弱看',
  3: '观望',
  4: '看好',
  5: '重点',
}

const FIT_SRC = { similar: '同赔单关同向', sameEvent: '同赛事单关同向', both: '两边单关同向' }
const FIT_SIDE = {
  home: '主胜',
  home_nb: '主不败',
  away: '客胜',
  away_nb: '客不败',
  upper: '上盘',
  lower: '下盘',
}
const OTHER_HEAT = { home: '偏主队', away: '偏客队', unclear: '热度不明' }
const JC = { up: '上盘升水', down: '上盘降水', flat: '不变' }
const SIM = {
  home_nb_high: '主不败概率高',
  home_nb_ext: '主不败概率极大',
  away_nb_high: '客不败概率高',
  away_nb_ext: '客不败概率极大',
  upper_high: '上盘概率高',
  upper_ext: '上盘概率极大',
  lower_high: '下盘概率高',
  lower_ext: '下盘概率极大',
}

export const SINGLE_OPTS = [
  { id: 'yes', text: '单关', tone: 'single' },
  { id: 'no', text: '非单关', tone: 'mute' },
]
export const SIM_SHALLOW_OPTS = [
  { id: 'home_nb_high', text: '主不败高', tone: 'upper' },
  { id: 'home_nb_ext', text: '主不败极大', tone: 'warn' },
  { id: 'away_nb_high', text: '客不败高', tone: 'lower' },
  { id: 'away_nb_ext', text: '客不败极大', tone: 'warn' },
]
export const SIM_DEEP_OPTS = [
  { id: 'upper_high', text: '上盘高', tone: 'upper' },
  { id: 'upper_ext', text: '上盘极大', tone: 'warn' },
  { id: 'lower_high', text: '下盘高', tone: 'lower' },
  { id: 'lower_ext', text: '下盘极大', tone: 'warn' },
]
export const SINGLE_FIT_OPTS = [
  { id: 'similar', text: '同赔单关', tone: 'single' },
  { id: 'sameEvent', text: '同赛事单关', tone: 'single' },
  { id: 'both', text: '两边同向', tone: 'warn' },
]
export const SINGLE_FIT_SIDE_OPTS = [
  { id: 'home', text: '主胜', tone: 'upper' },
  { id: 'home_nb', text: '主不败', tone: 'upper' },
  { id: 'away', text: '客胜', tone: 'lower' },
  { id: 'away_nb', text: '客不败', tone: 'lower' },
  { id: 'upper', text: '上盘', tone: 'upper' },
  { id: 'lower', text: '下盘', tone: 'lower' },
]
export const JC_MOVE_OPTS = [
  { id: 'up', text: '上盘升水', tone: 'upper' },
  { id: 'down', text: '上盘降水', tone: 'lower' },
  { id: 'flat', text: '不变', tone: 'mute' },
]
export const OTHER_HEAT_OPTS = [
  { id: 'home', text: '偏主队', tone: 'upper' },
  { id: 'away', text: '偏客队', tone: 'lower' },
  { id: 'unclear', text: '热度不明', tone: 'mute' },
]

export function ratingLabel(value) {
  if (value == null || value === '') return ''
  const n = Number(value)
  if (!n) return ''
  const key = Math.min(5, Math.max(1, Math.floor(n) || 1))
  return RATING_LABELS[key] || ''
}

export function emptyStructure() {
  return {
    single: null,
    heat: null,
    factorDir: null,
    factorAlign: null,
    factorUpper: null,
    factorLower: null,
    factorNeutral: null,
    factorItems: [],
    similar: null,
    sameEvent: null,
    similarPct: null,
    sameEventPct: null,
    similarSingle: null,
    similarSingleHit: null,
    similarSingleTotal: null,
    sameEventSingle: null,
    sameEventSingleHit: null,
    sameEventSingleTotal: null,
    singleFit: null,
    singleFitSide: null,
    jcMove: null,
    otherHeat: null,
    extra: '',
  }
}

export function cloneStructure(raw) {
  const s = { ...emptyStructure(), ...(raw && typeof raw === 'object' ? raw : {}) }
  s.factorItems = Array.isArray(s.factorItems)
    ? s.factorItems
      .filter((f) => f && f.name)
      .map((f) => ({
        name: f.name,
        direction: f.direction || 'neutral',
        score: f.score ?? null,
      }))
    : []
  return s
}

export function factorDirLabel(name, dir) {
  const hot = name === '市场热度' || name === '单关修正'
  if (dir === 'upper') return hot ? '上盘热' : '上盘'
  if (dir === 'lower') return hot ? '下盘热' : '下盘'
  return '中性'
}

export function factorDirTone(dir) {
  if (dir === 'upper') return 'upper'
  if (dir === 'lower') return 'lower'
  return 'mute'
}

export function hasFactorCounts(s) {
  return s != null && (s.factorUpper != null || s.factorLower != null)
}

/** ≥6 同向=偏, 全部同向=全上/全下, 其余分化 */
export function factorVerdict(s) {
  if (!s) return null
  if (hasFactorCounts(s)) {
    const u = Number(s.factorUpper) || 0
    const l = Number(s.factorLower) || 0
    const n = Number(s.factorNeutral) || 0
    const total = u + l + n
    if (!total) return null
    if (u === total) return { text: '全上盘', tone: 'upper' }
    if (l === total) return { text: '全下盘', tone: 'lower' }
    if (u >= 6) return { text: '偏上盘', tone: 'upper' }
    if (l >= 6) return { text: '偏下盘', tone: 'lower' }
    return { text: '分化', tone: 'mute' }
  }
  if (s.factorAlign === 'all' || s.factorAlign === 'yes') {
    if (s.factorDir === 'upper') return { text: '全上盘', tone: 'upper' }
    if (s.factorDir === 'lower') return { text: '全下盘', tone: 'lower' }
  }
  if (s.factorDir === 'upper') return { text: '偏上盘', tone: 'upper' }
  if (s.factorDir === 'lower') return { text: '偏下盘', tone: 'lower' }
  if (s.factorDir === 'mixed') return { text: '分化', tone: 'mute' }
  return null
}

export function structureHasValue(s) {
  if (!s) return false
  return !!(
    s.single || s.heat || s.factorDir || s.factorAlign || hasFactorCounts(s)
    || s.similar || s.sameEvent || s.similarSingle || s.sameEventSingle
    || s.singleFit || s.singleFitSide
    || s.jcMove || s.otherHeat || String(s.extra || '').trim()
  )
}

export function hasNote(note) {
  if (!note) return false
  return !!(String(note.content || '').trim() || note.rating || structureHasValue(note.structure))
}

export function noteLines(content) {
  return String(content || '').replace(/\s+$/, '')
}

/** |亚盘| ≤0.5 浅盘看不败, ≥0.75 深盘看盘路 */
export function isShallowHc(hc) {
  if (hc == null || hc === '') return null
  const n = Math.abs(Number(hc))
  if (Number.isNaN(n)) return null
  return n <= 0.5
}

function similarLevel(pct) {
  if (pct > 80) return 'ext'
  if (pct > 70) return 'high'
  return null
}

/**
 * 同赔/同赛事回写: 浅盘看主/客不败, 深盘看上/下盘.
 * 只在样本够且概率>70 时返回 id, 否则 null.
 */
export function pickSimilarVerdict(matches, hc, minTotal) {
  const stats = calcSimilarStats(matches)
  if (!stats.total || stats.total < minTotal) return null
  const shallow = isShallowHc(hc)
  let aKey
  let aPct
  let bKey
  let bPct
  if (shallow === false) {
    if (!stats.ahTotal || stats.ahTotal < minTotal) return null
    aKey = 'upper'
    aPct = (stats.upper / stats.ahTotal) * 100
    bKey = 'lower'
    bPct = (stats.lower / stats.ahTotal) * 100
  } else {
    aKey = 'home_nb'
    aPct = ((stats.win + stats.draw) / stats.total) * 100
    bKey = 'away_nb'
    bPct = ((stats.loss + stats.draw) / stats.total) * 100
  }
  const useA = aPct >= bPct
  const key = useA ? aKey : bKey
  const pct = useA ? aPct : bPct
  const lv = similarLevel(pct)
  if (!lv) return null
  return { id: `${key}_${lv}`, pct: Math.round(pct) }
}

export function similarLabel(id, pct) {
  const base = (id && SIM[id]) || ''
  if (!base) return ''
  const n = Number(pct)
  if (pct == null || Number.isNaN(n)) return base
  return `${base}(${Math.round(n)}%)`
}

export function similarTone(id) {
  if (!id || id === 'none') return 'mute'
  if (String(id).includes('ext')) return 'warn'
  if (String(id).startsWith('lower') || String(id).startsWith('away')) return 'lower'
  return 'upper'
}

export function hasTendency(id) {
  return !!id && id !== 'none'
}

export function jcMoveLabel(id) {
  return (id && JC[id]) || ''
}

export function jcMoveTone(id) {
  if (id === 'up') return 'upper'
  if (id === 'down') return 'lower'
  if (id === 'flat') return 'mute'
  return 'mute'
}

/** 列表/弹窗即时展示: 单关 + 竞彩让球方水位, 不依赖已保存备注 */
export function liveObjectiveChips(isSingle, jcMove) {
  const chips = []
  if (isSingle) chips.push({ text: '单关', tone: 'single' })
  const lab = jcMoveLabel(jcMove)
  if (lab) chips.push({ text: lab, tone: jcMoveTone(jcMove) })
  return chips
}

const SINGLE_FIT_MIN = 2

/**
 * 单关匹配回写: 只统计样本里的单关场.
 * 浅盘看主/客不败, 深盘看上/下盘; 取票数更多的一侧, 平票不算.
 * 至少 2 场才写, 不设 70% 门槛(用 hit/total).
 */
export function pickSingleFitVerdict(matches, hc, isSingle, minTotal = SINGLE_FIT_MIN) {
  if (!isSingle) return null
  const singles = (Array.isArray(matches) ? matches : []).filter((m) => m?.isSingle)
  const stats = calcSimilarStats(singles)
  const shallow = isShallowHc(hc)
  if (shallow === false) {
    if (!stats.ahTotal || stats.ahTotal < minTotal) return null
    if (stats.upper === stats.lower) return null
    const useUpper = stats.upper > stats.lower
    return {
      id: useUpper ? 'upper' : 'lower',
      hit: useUpper ? stats.upper : stats.lower,
      total: stats.ahTotal,
    }
  }
  if (!stats.total || stats.total < minTotal) return null
  const homeNb = stats.win + stats.draw
  const awayNb = stats.loss + stats.draw
  if (homeNb === awayNb) return null
  const useHome = homeNb > awayNb
  return {
    id: useHome ? 'home_nb' : 'away_nb',
    hit: useHome ? homeNb : awayNb,
    total: stats.total,
  }
}

export function singleFitLabel(src, side, hit, total) {
  const prefix = src === 'sameEvent' ? '同赛事单关' : '同赔单关'
  const sideText = (side && FIT_SIDE[side]) || ''
  if (!sideText) return ''
  const nHit = Number(hit)
  const nTotal = Number(total)
  if (hit == null || total == null || Number.isNaN(nHit) || Number.isNaN(nTotal)) {
    return `${prefix}${sideText}`
  }
  return `${prefix}${sideText}(${Math.round(nHit)}/${Math.round(nTotal)})`
}

function hasAutoSingleFit(s) {
  return hasTendency(s?.similarSingle) || hasTendency(s?.sameEventSingle)
}

export function bothSingleFitAligned(s) {
  return !!(
    hasTendency(s?.similarSingle)
    && hasTendency(s?.sameEventSingle)
    && s.similarSingle === s.sameEventSingle
  )
}

export function applyHints(structure, hints) {
  const s = cloneStructure(structure)
  if (structureHasValue(s)) return s
  if (hints?.isSingle === true) s.single = 'yes'
  if (hints?.jcMove === 'up' || hints?.jcMove === 'down' || hints?.jcMove === 'flat') {
    s.jcMove = hints.jcMove
  }
  if (hints?.legacyContent) s.extra = String(hints.legacyContent)
  return s
}

function factorLine(s) {
  const v = factorVerdict(s)
  if (hasFactorCounts(s)) {
    const u = Number(s.factorUpper) || 0
    const l = Number(s.factorLower) || 0
    const n = Number(s.factorNeutral) || 0
    let line = `预测因子 上盘${u} 下盘${l} 中性${n}`
    if (v) line += `，${v.text}`
    return line
  }
  return v ? `预测因子${v.text}` : ''
}

export function formatNoteContent(s) {
  if (!structureHasValue(s)) return ''
  const lines = []
  const head = []
  if (s.single === 'yes') head.push('单关')
  if (head.length) lines.push(head.join('，'))
  const fac = factorLine(s)
  if (fac) lines.push(fac)
  if (hasTendency(s.similar) && SIM[s.similar]) lines.push(`同赔${similarLabel(s.similar, s.similarPct)}`)
  if (hasTendency(s.sameEvent) && SIM[s.sameEvent]) lines.push(`同赛事${similarLabel(s.sameEvent, s.sameEventPct)}`)
  const simFit = singleFitLabel('similar', s.similarSingle, s.similarSingleHit, s.similarSingleTotal)
  const evFit = singleFitLabel('sameEvent', s.sameEventSingle, s.sameEventSingleHit, s.sameEventSingleTotal)
  if (simFit) lines.push(simFit)
  if (evFit) lines.push(evFit)
  if (bothSingleFitAligned(s)) lines.push('两边单关同向')
  if (!hasAutoSingleFit(s) && s.singleFit && FIT_SRC[s.singleFit]) {
    const side = s.singleFitSide && FIT_SIDE[s.singleFitSide] ? FIT_SIDE[s.singleFitSide] : ''
    lines.push(side ? `${FIT_SRC[s.singleFit]}${side}` : FIT_SRC[s.singleFit])
  }
  if (s.jcMove && JC[s.jcMove]) lines.push(`竞彩${JC[s.jcMove]}`)
  if (s.otherHeat && OTHER_HEAT[s.otherHeat]) lines.push(`个人热度${OTHER_HEAT[s.otherHeat]}`)
  const extra = String(s.extra || '').trim()
  if (extra) lines.push(extra)
  return lines.join('\n')
}

export function structureChips(s) {
  if (!structureHasValue(s)) return []
  const chips = []
  const push = (text, tone) => { if (text) chips.push({ text, tone: tone || 'mute' }) }
  if (hasFactorCounts(s)) {
    const u = Number(s.factorUpper) || 0
    const l = Number(s.factorLower) || 0
    const n = Number(s.factorNeutral) || 0
    let t = `因子上${u}下${l}`
    if (n) t += `中${n}`
    push(t, 'mute')
    const v = factorVerdict(s)
    if (v) push(v.text, v.tone)
  } else {
    const v = factorVerdict(s)
    if (v) push(`因子${v.text}`, v.tone)
  }
  if (hasTendency(s.similar) && SIM[s.similar]) {
    push(`同赔${similarLabel(s.similar, s.similarPct)}`, similarTone(s.similar))
  }
  if (hasTendency(s.sameEvent) && SIM[s.sameEvent]) {
    push(`同赛事${similarLabel(s.sameEvent, s.sameEventPct)}`, similarTone(s.sameEvent))
  }
  const simFit = singleFitLabel('similar', s.similarSingle, s.similarSingleHit, s.similarSingleTotal)
  const evFit = singleFitLabel('sameEvent', s.sameEventSingle, s.sameEventSingleHit, s.sameEventSingleTotal)
  if (simFit) push(simFit, similarTone(s.similarSingle))
  if (evFit) push(evFit, similarTone(s.sameEventSingle))
  if (bothSingleFitAligned(s)) push('两边同向', 'warn')
  if (!hasAutoSingleFit(s) && s.singleFit) {
    const side = s.singleFitSide && FIT_SIDE[s.singleFitSide] ? FIT_SIDE[s.singleFitSide] : ''
    push(side ? `${FIT_SRC[s.singleFit]}·${side}` : FIT_SRC[s.singleFit], 'warn')
  }
  if (s.otherHeat && OTHER_HEAT[s.otherHeat]) {
    push(`热度${OTHER_HEAT[s.otherHeat]}`, s.otherHeat === 'away' ? 'lower' : s.otherHeat === 'home' ? 'upper' : 'mute')
  }
  return chips
}
