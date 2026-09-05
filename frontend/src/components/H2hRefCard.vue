<template>
  <teleport to="body">
    <view v-if="open" class="h2h-portal">
      <view class="app-mask h2h-mask" @tap="close" />
      <view class="app-modal h2h-modal show" @tap.stop>
      <view class="h2h-modal-head">
        <view class="h2h-modal-row">
          <text class="h2h-modal-title">交锋明细</text>
          <text class="h2h-close" @tap="close">关闭</text>
        </view>
        <view class="h2h-filters">
          <view class="h2h-chip" :class="{ on: sameLeagueOnly }" @tap="sameLeagueOnly = !sameLeagueOnly">
            <text>同联赛{{ leagueCount }}</text>
          </view>
          <view class="h2h-chip" :class="{ on: sameVenueOnly }" @tap="sameVenueOnly = !sameVenueOnly">
            <text>同主客{{ venueCount }}</text>
          </view>
        </view>
      </view>
      <view class="h2h-modal-body">
        <view class="h2h-table">
          <view class="h2h-th">
            <view class="col-event">赛事</view>
            <view class="col-teams">主队　比分　客队</view>
            <view class="col-asian">盘口</view>
            <view class="col-ou">大小</view>
          </view>
          <view
            v-for="(row, i) in visibleParsed"
            :key="i"
            class="h2h-tr"
          >
            <view class="col-event">
              <text class="event-date">{{ row.dateShort }}</text>
              <text class="event-name">{{ row.competition }}</text>
            </view>
            <view class="col-teams">
              <view class="team-left">
                <text class="team-name" :class="row.homeClass">{{ row.homeTeam }}</text>
              </view>
              <view class="score-wrap">
                <text class="match-score">{{ row.score }}</text>
                <text v-if="row.halftimeScore" class="halftime-score">{{ row.halftimeScore }}</text>
              </view>
              <view class="team-right">
                <text class="team-name" :class="row.awayClass">{{ row.awayTeam }}</text>
              </view>
            </view>
            <view class="col-asian">
              <text class="data-value" :class="row.asianClass">{{ row.asian || '-' }}</text>
              <text class="data-label" :class="row.asianClass">{{ row.asianLabel }}</text>
            </view>
            <view class="col-ou">
              <text class="data-label" :class="row.ouClass">{{ row.ouLabel }}</text>
            </view>
          </view>
          <view v-if="!visibleParsed.length" class="h2h-modal-empty">
            <text>当前筛选无场次</text>
          </view>
        </view>
      </view>
      </view>
    </view>
    </teleport>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  data: { type: Object, default: null },
  homeName: { type: String, default: '主队' },
  awayName: { type: String, default: '客队' },
  currentHc: { type: [Number, String], default: null },
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

function close() {
  emit('close')
}

const sameLeagueOnly = ref(false)
const sameVenueOnly = ref(false)

const rows = computed(() =>
  (props.data?.matches || []).filter((r) => (r.halfScore || '') !== 'VS')
)
const leagueCount = computed(() => rows.value.filter((r) => r.sameLeague).length)
const venueCount = computed(() => rows.value.filter((r) => r.sameVenue).length)

watch(() => props.data, () => {
  sameLeagueOnly.value = false
  sameVenueOnly.value = false
})

const summaryRows = computed(() => {
  if (leagueCount.value >= 3) return rows.value.filter((r) => r.sameLeague)
  return rows.value
})

const visible = computed(() => {
  return rows.value.filter((r) => {
    if (sameLeagueOnly.value && !r.sameLeague) return false
    if (sameVenueOnly.value && !r.sameVenue) return false
    return true
  })
})

function wdl(list) {
  let w = 0, d = 0, l = 0
  for (const r of list) {
    if (r.result === 'win') w += 1
    else if (r.result === 'draw') d += 1
    else if (r.result === 'lose') l += 1
  }
  return { w, d, l, n: w + d + l }
}

function ah(list, key) {
  let upper = 0, lower = 0, push = 0
  for (const r of list) {
    const v = r[key]
    if (v === 'upper') upper += 1
    else if (v === 'lower') lower += 1
    else if (v === 'push') push += 1
  }
  return { upper, lower, push, n: upper + lower + push }
}

function segsFrom(parts) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1
  return parts
    .filter((p) => p.value > 0)
    .map((p) => ({
      ...p,
      pct: Math.max((p.value / total) * 100, p.value ? 4 : 0),
    }))
}

function fmtHc(v) {
  if (v === undefined || v === null || v === '') return ''
  const num = Number(v)
  if (Number.isNaN(num)) return ''
  return num > 0 ? `+${num}` : `${num}`
}

const kicker = computed(() => {
  const n = summaryRows.value.length
  const all = rows.value.length
  if (leagueCount.value >= 3 && n < all) return `同联赛 ${n}场 · 全部 ${all}场`
  return `近${n}场`
})

const metrics = computed(() => {
  const list = summaryRows.value
  const allWdl = wdl(list)
  const homeList = list.filter((r) => r.venue === 'home')
  const awayList = list.filter((r) => r.venue === 'away')
  const homeWdl = wdl(homeList)
  const awayWdl = wdl(awayList)
  const hist = ah(list, 'histAr')
  const line = ah(list, 'lineAr')
  const recent = ah(list.slice(0, 5), 'lineAr')
  const home = props.homeName
  const away = props.awayName
  const out = [
    {
      key: 'wdl',
      label: '胜负',
      num: `${allWdl.w}-${allWdl.d}-${allWdl.l}`,
      segs: segsFrom([
        { label: home, value: allWdl.w, side: 'upper' },
        { label: '平', value: allWdl.d, side: 'neutral' },
        { label: away, value: allWdl.l, side: 'lower' },
      ]),
    },
  ]
  if (homeWdl.n) {
    out.push({
      key: 'home',
      label: '主场',
      num: `${homeWdl.w}-${homeWdl.d}-${homeWdl.l}`,
      segs: segsFrom([
        { label: '胜', value: homeWdl.w, side: 'upper' },
        { label: '平', value: homeWdl.d, side: 'neutral' },
        { label: '负', value: homeWdl.l, side: 'lower' },
      ]),
    })
  }
  if (awayWdl.n) {
    out.push({
      key: 'away',
      label: '客场',
      num: `${awayWdl.w}-${awayWdl.d}-${awayWdl.l}`,
      segs: segsFrom([
        { label: '胜', value: awayWdl.w, side: 'upper' },
        { label: '平', value: awayWdl.d, side: 'neutral' },
        { label: '负', value: awayWdl.l, side: 'lower' },
      ]),
    })
  }
  if (hist.n) {
    out.push({
      key: 'hist',
      label: '当时盘',
      num: `上${hist.upper} 下${hist.lower}`,
      segs: segsFrom([
        { label: '上盘', value: hist.upper, side: 'upper' },
        { label: '走', value: hist.push, side: 'neutral' },
        { label: '下盘', value: hist.lower, side: 'lower' },
      ]),
    })
  }
  if (line.n) {
    out.push({
      key: 'line',
      label: '本场盘',
      hi: true,
      num: `上${line.upper} 下${line.lower}`,
      segs: segsFrom([
        { label: '上盘', value: line.upper, side: 'upper' },
        { label: '走', value: line.push, side: 'neutral' },
        { label: '下盘', value: line.lower, side: 'lower' },
      ]),
    })
  }
  if (list.length >= 6 && recent.n) {
    out.push({
      key: 'recent',
      label: '近5场',
      num: `上${recent.upper} 下${recent.lower}`,
      segs: segsFrom([
        { label: '上盘', value: recent.upper, side: 'upper' },
        { label: '走', value: recent.push, side: 'neutral' },
        { label: '下盘', value: recent.lower, side: 'lower' },
      ]),
    })
  }
  return out
})

const verdict = computed(() => {
  const list = summaryRows.value
  if (list.length < 3) return null
  const { w, l } = wdl(list)
  const homeW = wdl(list.filter((r) => r.venue === 'home'))
  const line = ah(list, 'lineAr')
  const hist = ah(list, 'histAr')
  const home = props.homeName
  const away = props.awayName
  const parts = []
  if (w - l >= 2) parts.push(`胜负偏${home}`)
  else if (l - w >= 2) parts.push(`胜负偏${away}`)
  if (homeW.n >= 3) {
    if (homeW.l - homeW.w >= 2) parts.push('主场偏弱')
    else if (homeW.w - homeW.l >= 2) parts.push('主场占优')
  }
  const hc = fmtHc(props.currentHc)
  const decided = line.upper + line.lower
  if (decided >= 3) {
    const upPct = line.upper / decided
    if (upPct <= 0.4) parts.push(hc ? `按本场盘${hc}重算偏下` : '按本场盘重算偏下')
    else if (upPct >= 0.6) parts.push(hc ? `按本场盘${hc}重算偏上` : '按本场盘重算偏上')
    else if (hist.n >= 3) {
      const histUp = hist.upper / (hist.upper + hist.lower || 1)
      if (histUp >= 0.55 && upPct <= 0.45) parts.push('当时能赢盘，本场盘更深盖不住')
      else if (histUp <= 0.45 && upPct >= 0.55) parts.push('当时常输盘，本场盘更浅好打')
    }
  }
  if (!parts.length) return { text: '交锋胶着，没有一边倒', side: 'neutral' }
  const last = parts[parts.length - 1]
  const side = last.includes('偏下') || last.includes('偏' + away) || last.includes('主场偏弱')
    ? 'lower'
    : last.includes('偏上') || last.includes('偏' + home)
      ? 'upper'
      : 'neutral'
  return { text: parts.join('，'), side }
})

function dateShort(date) {
  const s = String(date || '').trim()
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (m) return `${m[1].slice(2)}-${m[2]}-${m[3]}`
  return s || '-'
}

function parseMatch(row) {
  const raw = String(row.match || '').replace(/\[[^\]]*\]/g, '')
  const m = raw.match(/^(.*?)(\d+)\s*[:：]\s*(\d+)(.*)$/)
  if (!m) return { homeTeam: raw || '-', awayTeam: '-', score: '-', homeScore: null, awayScore: null }
  return {
    homeTeam: m[1].trim() || '-',
    awayTeam: m[4].trim() || '-',
    score: `${m[2]}:${m[3]}`,
    homeScore: Number(m[2]),
    awayScore: Number(m[3]),
  }
}

const visibleParsed = computed(() => visible.value.map((row) => {
  const p = parseMatch(row)
  let homeClass = 'team-draw'
  let awayClass = 'team-draw'
  if (p.homeScore != null && p.homeScore !== p.awayScore) {
    homeClass = p.homeScore > p.awayScore ? 'team-win' : 'team-lose'
    awayClass = p.awayScore > p.homeScore ? 'team-win' : 'team-lose'
  }
  const asianResult = (row.asianResult || '').trim()
  const ouResult = (row.ouResult || '').trim()
  const half = (row.halfScore || '').trim()
  return {
    ...row,
    ...p,
    dateShort: dateShort(row.date),
    competition: row.competition || '-',
    homeClass,
    awayClass,
    asian: row.asian || '',
    asianLabel: asianResult,
    asianClass: asianResult === '赢' || asianResult === '赢半' ? 'win'
      : asianResult === '输' || asianResult === '输半' ? 'lose' : 'draw',
    ouLabel: ouResult,
    ouClass: ouResult === '大' ? 'big' : ouResult === '小' ? 'small' : '',
    halftimeScore: half && half !== 'VS' ? `(${half})` : '',
  }
}))
</script>

<style lang="scss" scoped>
.h2h-wrap {
  position: relative;
}
.h2h-ref {
  margin: 8rpx 0 24rpx;
  padding: 16rpx 18rpx;
  background: #f8fafb;
  border: 1rpx solid #e2e8f0;
  border-radius: 6rpx;
}
.h2h-head {
  display: flex;
  align-items: center;
  gap: 10rpx;
}
.h2h-title {
  font-size: 24rpx;
  font-weight: 600;
  color: #1e293b;
}
.h2h-tag {
  font-size: 18rpx;
  color: #64748b;
  background: #e2e8f0;
  border-radius: 6rpx;
  padding: 2rpx 8rpx;
}
.h2h-detail {
  margin-left: auto;
  font-size: 22rpx;
  color: #0d9488;
  padding: 4rpx 0 4rpx 12rpx;
}
.h2h-empty {
  padding: 16rpx 0 4rpx;
  font-size: 22rpx;
  color: #94a3b8;
}
.h2h-kicker {
  display: block;
  margin-top: 8rpx;
  font-size: 20rpx;
  color: #94a3b8;
}
.h2h-verdict {
  display: block;
  margin-top: 6rpx;
  font-size: 24rpx;
  font-weight: 600;
  line-height: 1.4;
  &.upper { color: #dc2626; }
  &.lower { color: #059669; }
  &.neutral { color: #475569; font-weight: 500; }
}
.h2h-metrics {
  margin-top: 14rpx;
  display: flex;
  flex-direction: column;
  gap: 10rpx;
}
.metric {
  display: flex;
  align-items: center;
  gap: 10rpx;
  &.hi .metric-lab { color: #0f172a; font-weight: 600; }
}
.metric-lab {
  width: 72rpx;
  flex-shrink: 0;
  font-size: 20rpx;
  color: #64748b;
}
.metric-track {
  flex: 1;
  min-width: 0;
  height: 12rpx;
  display: flex;
  overflow: hidden;
  background: #e2e8f0;
  border-radius: 6rpx;
}
.metric-seg {
  height: 100%;
  &.upper { background: #dc2626; }
  &.lower { background: #059669; }
  &.neutral { background: #94a3b8; }
}
.metric-num {
  width: 120rpx;
  flex-shrink: 0;
  text-align: right;
  font-size: 20rpx;
  color: #334155;
  font-variant-numeric: tabular-nums;
}

.h2h-portal {
  position: static;
}
.h2h-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 210;
}
.h2h-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  right: auto;
  width: min(398px, calc(100vw - 32px));
  max-height: min(88vh, 720px);
  background: #fff;
  border-radius: 12rpx;
  z-index: 211;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 16rpx 48rpx rgba(15, 23, 42, 0.18);
  transform: translate(-50%, -50%);
}
.h2h-modal-head {
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  padding: 16rpx 20rpx 12rpx;
  border-bottom: 1rpx solid #e2e8f0;
  flex-shrink: 0;
}
.h2h-modal-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12rpx;
}
.h2h-modal-title {
  font-size: 28rpx;
  font-weight: 600;
  color: #1e293b;
}
.h2h-filters {
  display: flex;
  gap: 8rpx;
}
.h2h-chip {
  font-size: 20rpx;
  color: #64748b;
  background: #f8fafc;
  border: 1rpx solid #e2e8f0;
  border-radius: 6rpx;
  padding: 4rpx 10rpx;
  &.on {
    color: #0f766e;
    background: #ecfdf5;
    border-color: #99f6e4;
  }
}
.h2h-close {
  font-size: 24rpx;
  color: #64748b;
  padding: 4rpx 0 4rpx 12rpx;
}
.h2h-modal-body {
  flex: 1 1 auto;
  min-height: 0;
  max-height: min(70vh, 560px);
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
}
.h2h-modal-empty {
  padding: 40rpx;
  text-align: center;
  font-size: 24rpx;
  color: #94a3b8;
}
.h2h-table { background: #fff; }
.h2h-th, .h2h-tr {
  display: flex;
  align-items: center;
  padding: 10rpx 12rpx;
  gap: 0;
}
.h2h-th {
  font-size: 20rpx;
  color: #9ca3af;
  position: sticky;
  top: 0;
  z-index: 1;
  background: #fff;
}
.h2h-tr {
  font-size: 22rpx;
}
.col-event {
  width: 112rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2rpx;
  padding-right: 8rpx;
}
.event-date { font-size: 20rpx; color: #6b7280; }
.event-name { font-size: 20rpx; color: #111827; }
.col-teams {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.team-left, .team-right {
  flex: 1;
  min-width: 0;
}
.team-left { text-align: right; padding-right: 10rpx; }
.team-right { text-align: left; padding-left: 10rpx; }
.team-name {
  font-size: 22rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  &.team-win { color: #ef4444; }
  &.team-lose { color: #10b981; }
  &.team-draw { color: #374151; }
}
.score-wrap {
  width: 80rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2rpx;
}
.match-score { font-size: 24rpx; color: #111827; }
.halftime-score { font-size: 20rpx; color: #9ca3af; }
.col-asian,
.col-ou {
  width: 88rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 2rpx;
}
.data-value {
  font-size: 22rpx;
  color: #111827;
  &.win { color: #ef4444; }
  &.lose { color: #10b981; }
}
.data-label {
  font-size: 20rpx;
  &.win, &.big { color: #ef4444; }
  &.lose, &.small { color: #10b981; }
}
</style>
