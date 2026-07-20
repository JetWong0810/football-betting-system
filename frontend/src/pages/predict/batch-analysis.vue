<template>
  <view class="batch-page">
    <view class="summary-bar">
      <view class="sum-row">
        <text class="sum-title">{{ date.slice(5) }} 同赔分析</text>
        <text class="sum-total">
          <template v-if="hasFilter">已筛 {{ filteredItems.length }}/{{ summary.total }}</template>
          <template v-else>{{ summary.total }} 场</template>
        </text>
      </view>
      <view class="sum-stats">
        <text class="st upper">上盘 {{ summary.upper }}</text>
        <text class="st-sep">·</text>
        <text class="st lower">下盘 {{ summary.lower }}</text>
        <text class="st-sep">·</text>
        <text class="st neutral">中性 {{ summary.neutral }}</text>
        <template v-if="isFinished && summary.hitTotal">
          <text class="st-sep">·</text>
          <text class="st hit">命中 {{ summary.hitRate }}%</text>
        </template>
      </view>
    </view>

    <view class="ctrl-bar" v-if="!loading && items.length">
      <view class="ctrl-row">
        <text class="ctrl-lab">排序</text>
        <text class="ctrl-btn" :class="{ active: sortMode === 'default' }" @tap="sortMode = 'default'">默认</text>
        <text class="ctrl-btn" :class="{ active: sortMode === 'hitPct' }" @tap="sortMode = 'hitPct'">命中率</text>
        <text class="ctrl-btn" :class="{ active: sortMode === 'refScore' }" @tap="sortMode = 'refScore'">分数</text>
      </view>
      <view class="ctrl-row">
        <text class="ctrl-lab">筛选</text>
        <text class="ctrl-btn" :class="{ active: !dirFilters.length }" @tap="dirFilters = []">全部</text>
        <text class="ctrl-btn upper" :class="{ active: dirFilters.includes('upper') }" @tap="toggleFilter('upper')">上盘</text>
        <text class="ctrl-btn lower" :class="{ active: dirFilters.includes('lower') }" @tap="toggleFilter('lower')">下盘</text>
        <text class="ctrl-btn" :class="{ active: dirFilters.includes('neutral') }" @tap="toggleFilter('neutral')">中性</text>
        <text
          v-if="isFinished && summary.hitTotal"
          class="ctrl-btn hit"
          :class="{ active: dirFilters.includes('hit') }"
          @tap="toggleFilter('hit')"
        >命中</text>
        <text
          class="ctrl-btn sample"
          :class="{ active: dirFilters.includes('sample5') }"
          @tap="toggleFilter('sample5')"
        >同赔≥5</text>
        <text
          class="ctrl-btn hitpct"
          :class="{ active: dirFilters.includes('hitPct65') }"
          @tap="toggleFilter('hitPct65')"
        >命中≥65%</text>
        <text
          class="ctrl-btn score"
          :class="{ active: dirFilters.includes('score60') }"
          @tap="toggleFilter('score60')"
        >分数≥60</text>
        <text
          class="ctrl-btn single"
          :class="{ active: dirFilters.includes('single') }"
          @tap="toggleFilter('single')"
        >单关</text>
      </view>
      <view class="ctrl-row">
        <text class="ctrl-lab">变动</text>
        <text class="ctrl-btn" :class="{ active: !moveFilters.length }" @tap="moveFilters = []">全部</text>
        <text class="ctrl-btn move-up" :class="{ active: moveFilters.includes('up') }" @tap="toggleMoveFilter('up')">上升</text>
        <text class="ctrl-btn move-down" :class="{ active: moveFilters.includes('down') }" @tap="toggleMoveFilter('down')">下降</text>
        <text class="ctrl-btn" :class="{ active: moveFilters.includes('flat') }" @tap="toggleMoveFilter('flat')">不变</text>
      </view>
      <view class="filter-count" v-if="hasFilter">
        <text class="fc-main">已筛 {{ filteredItems.length }} 场</text>
        <text class="fc-sub">共 {{ summary.total }} 场</text>
        <text v-if="isFinished" class="fc-hit">命中 {{ filteredHitCount }}/{{ filteredItems.length }}</text>
        <text class="fc-clear" @tap="clearFilter">清除</text>
      </view>
    </view>

    <view v-if="loading" class="state-hint"><text>分析中…</text></view>
    <view v-else-if="items.length === 0" class="state-hint">
      <text>该日无{{ isFinished ? '已结束' : '在售' }}竞彩比赛</text>
    </view>
    <view v-else-if="filteredItems.length === 0" class="state-hint">
      <text>当前筛选无场次</text>
      <text class="state-clear" @tap="clearFilter">清除筛选</text>
    </view>

    <scroll-view v-else class="card-list" scroll-y>
      <view class="card-list-inner">
        <view
          v-for="it in filteredItems"
          :key="it.matchId"
          class="match-card"
        >
          <view class="row-meta">
            <text class="league">{{ it.league || '-' }}</text>
            <text class="time">{{ (it.matchTime || '').slice(0, 5) }}</text>
            <text v-if="it.isSingle" class="single-tag">单关</text>
            <view class="dir-wrap">
              <text class="dir" :class="[it.f6?.direction || 'neutral', refTier(it.f6)]">{{ dirLabel(it.f6?.direction) }}</text>
              <text
                v-if="it.f6?.refScore != null"
                class="ref-score"
                :class="[it.f6?.direction || 'neutral', refTier(it.f6)]"
              >{{ it.f6.refScore }}</text>
            </view>
          </view>

          <view class="row-teams">
            <text class="team home">{{ it.homeTeam?.name }}</text>
            <text class="vs">vs</text>
            <text class="team away">{{ it.awayTeam?.name }}</text>
          </view>

          <!-- 核心结论 -->
          <view class="row-hit" v-if="ahStats(it.f6).total > 0">
            <view class="hit-top">
              <text class="pct" :class="focusSide(it.f6)">{{ focusPct(it.f6) }}%</text>
              <text class="pct-lab" :class="focusSide(it.f6)">{{ focusHitLabel(it.f6) }}</text>
              <text class="sample">{{ ahStats(it.f6).upper }}/{{ ahStats(it.f6).lower }}/{{ ahStats(it.f6).push }} · {{ ahStats(it.f6).total }}场</text>
            </view>
            <view class="bar">
              <view class="bar-u" :style="{ width: ahStats(it.f6).upperPct + '%' }"></view>
              <view class="bar-l" :style="{ width: ahStats(it.f6).lowerPct + '%' }"></view>
            </view>
            <text class="reason" v-if="it.f6?.reason">{{ shortReason(it.f6.reason) }}</text>
          </view>
          <view class="row-hit empty" v-else>
            <text class="reason">{{ it.f6?.reason || '暂无同赔样本' }}</text>
          </view>

          <!-- 亚盘盘口: 在售/已结束都常显; 无数据时显示「无数据」 -->
          <view class="row-ah">
            <text class="ah-lab">亚盘</text>
            <text v-if="it.ahHandicap != null" class="ah-num">{{ fmtAh(it.ahHandicap) }}</text>
            <text v-else class="ah-miss">无数据</text>
            <template v-if="isFinished && it.actualScore">
              <text class="ac-sep">·</text>
              <text class="ac-score">{{ it.actualScore }}</text>
              <text class="ac-sep">·</text>
              <text :class="resultClass(it.actualResult)">{{ it.actualResult || '-' }}</text>
              <text class="ac-sep">·</text>
              <text :class="ahResultClass(it.actualAh)">{{ it.actualAh || '-' }}</text>
              <text v-if="it.hit === true" class="ac-hit">命中</text>
              <text v-else-if="it.hit === false" class="ac-miss">未中</text>
            </template>
          </view>

          <!-- 赔率一行 -->
          <view class="row-odds" v-if="it.spf">
            <text class="ol-lab">竞彩</text>
            <text class="ol-muted">初</text>
            <text :class="lowClass(it.spf.initial, 'win')">{{ fmt(it.spf.initial.win) }}</text>
            <text :class="lowClass(it.spf.initial, 'draw')">{{ fmt(it.spf.initial.draw) }}</text>
            <text :class="lowClass(it.spf.initial, 'loss')">{{ fmt(it.spf.initial.lose) }}</text>
            <text class="ol-muted">→</text>
            <text class="ol-muted">终</text>
            <text :class="lowClass(it.spf.current, 'win')">{{ fmt(it.spf.current.win) }}</text>
            <text :class="lowClass(it.spf.current, 'draw')">{{ fmt(it.spf.current.draw) }}</text>
            <text :class="lowClass(it.spf.current, 'loss')">{{ fmt(it.spf.current.lose) }}</text>
            <text class="ol-move" :class="moveClass(it.spf)">{{ moveLabel(it.spf) }}</text>
          </view>

          <view class="row-detail" @tap="openSimilar(it)">
            <text>同赔详情 {{ it.f6?.matches?.length || 0 }} 场 ›</text>
          </view>
        </view>
      </view>
    </scroll-view>

    <view class="similar-mask" v-if="showSimilar" @tap="closeSimilar"></view>
    <view class="similar-modal" :class="{ show: showSimilar }">
      <view class="similar-header">
        <view class="similar-title-wrap">
          <text class="similar-title">历史同赔详情</text>
          <text v-if="similarRefScore != null" class="similar-ref">参考分 {{ similarRefScore }}</text>
        </view>
        <text class="similar-close" @tap="closeSimilar">关闭</text>
      </view>
      <scroll-view class="similar-body" scroll-y scroll-x>
        <view class="similar-table">
          <view class="similar-row similar-thead">
            <text class="col-sim">相似度</text>
            <text class="col-team">主队</text>
            <text class="col-score">比分</text>
            <text class="col-team">客队</text>
            <text class="col-result">结果</text>
            <text class="col-handicap">让球</text>
            <text class="col-ah-result">盘路</text>
            <text class="col-odds">初盘</text>
            <text class="col-odds">终盘</text>
            <text class="col-date">日期</text>
            <text class="col-league">联赛</text>
          </view>
          <view class="similar-row" v-for="(m, mi) in similarMatches" :key="mi">
            <text class="col-sim">{{ m.similarity }}%</text>
            <text class="col-team">{{ m.homeTeam }}</text>
            <text class="col-score">{{ m.score }}</text>
            <text class="col-team">{{ m.awayTeam }}</text>
            <text class="col-result" :class="resultClass(m.result)">{{ m.result }}</text>
            <text class="col-handicap">{{ m.handicap || '-' }}</text>
            <text class="col-ah-result" :class="ahResultClass(m.ahResult)">{{ m.ahResult || '-' }}</text>
            <text class="col-odds">{{ m.openOdds }}</text>
            <text class="col-odds">{{ m.closeOdds }}</text>
            <text class="col-date">{{ m.date }}</text>
            <text class="col-league" :class="{ 'league-same': m.sameLeague }">{{ m.league }}</text>
          </view>
          <view v-if="similarMatches.length === 0" class="similar-empty">
            <text>暂无历史同赔数据</text>
          </view>
        </view>
      </scroll-view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { request } from '@/utils/http'

const date = ref('')
const status = ref('not_started')
const loading = ref(true)
const items = ref([])
const summary = ref({ total: 0, upper: 0, lower: 0, neutral: 0 })
const showSimilar = ref(false)
const similarMatches = ref([])
const similarRefScore = ref(null)
/** 多选: upper/lower/neutral/hit */
const dirFilters = ref([])
/** 多选: up/down/flat — 低赔方(让球方)初→终 */
const moveFilters = ref([])
/** default | hitPct | refScore */
const sortMode = ref('default')

const isFinished = computed(() => status.value === 'finished')
const hasFilter = computed(() => dirFilters.value.length > 0 || moveFilters.value.length > 0)

const DIR_ORDER = { upper: 0, lower: 1, neutral: 2 }
function itemHitPct(it) {
  return focusPct(it?.f6) || 0
}
function itemRefScore(it) {
  const s = it?.f6?.refScore
  return s == null ? -1 : Number(s)
}
const sortedItems = computed(() => {
  const list = [...items.value]
  const mode = sortMode.value
  if (mode === 'hitPct') {
    return list.sort((a, b) => {
      const d = itemHitPct(b) - itemHitPct(a)
      if (d !== 0) return d
      return itemRefScore(b) - itemRefScore(a)
    })
  }
  if (mode === 'refScore') {
    return list.sort((a, b) => {
      const d = itemRefScore(b) - itemRefScore(a)
      if (d !== 0) return d
      return itemHitPct(b) - itemHitPct(a)
    })
  }
  return list.sort((a, b) => {
    const da = DIR_ORDER[a.f6?.direction] ?? 2
    const db = DIR_ORDER[b.f6?.direction] ?? 2
    if (da !== db) return da - db
    return itemRefScore(b) - itemRefScore(a)
  })
})
const filteredItems = computed(() => {
  let list = sortedItems.value
  const dirs = dirFilters.value
  if (dirs.length) {
    const dirSet = dirs.filter(k => k !== 'hit' && k !== 'sample5' && k !== 'hitPct65' && k !== 'score60' && k !== 'single')
    const needHit = dirs.includes('hit')
    const needSample5 = dirs.includes('sample5')
    const needHitPct65 = dirs.includes('hitPct65')
    const needScore60 = dirs.includes('score60')
    const needSingle = dirs.includes('single')
    list = list.filter(it => {
      const okDir = !dirSet.length || dirSet.includes(it.f6?.direction || 'neutral')
      const okHit = !needHit || it.hit === true
      const okSample = !needSample5 || similarHistCount(it) >= 5
      const okHitPct = !needHitPct65 || itemHitPct(it) >= 65
      const okScore = !needScore60 || itemRefScore(it) >= 60
      const okSingle = !needSingle || !!it.isSingle
      return okDir && okHit && okSample && okHitPct && okScore && okSingle
    })
  }
  const moves = moveFilters.value
  if (moves.length) {
    list = list.filter(it => moves.includes(lowMoveDir(it.spf)))
  }
  return list
})
const filteredHitCount = computed(() =>
  filteredItems.value.reduce((n, it) => n + (it.hit === true ? 1 : 0), 0)
)

/** 同赔历史匹配场次(详情列表条数) */
function similarHistCount(it) {
  const n = it?.f6?.matches?.length
  return n == null ? 0 : Number(n)
}

function toggleInList(listRef, key) {
  const arr = listRef.value
  const i = arr.indexOf(key)
  if (i >= 0) listRef.value = arr.filter((_, idx) => idx !== i)
  else listRef.value = [...arr, key]
}
function toggleFilter(key) {
  toggleInList(dirFilters, key)
}
function toggleMoveFilter(key) {
  toggleInList(moveFilters, key)
}
function clearFilter() {
  dirFilters.value = []
  moveFilters.value = []
}

function dirLabel(dir) { return dir === 'upper' ? '上盘' : dir === 'lower' ? '下盘' : '中性' }
/** 参考分档: weak <40 / mid 40–64 / strong ≥65 */
function refTier(f6) {
  const s = f6?.refScore
  if (s == null) return ''
  if (s < 40) return 'ref-weak'
  if (s < 65) return 'ref-mid'
  return 'ref-strong'
}
function fmt(v) { return v == null ? '-' : Number(v).toFixed(2) }
/** 亚盘展示: 标准约定负=主让, 保留常见四分盘精度 */
function fmtAh(h) {
  if (h == null || h === '') return '-'
  const n = Number(h)
  if (Number.isNaN(n)) return '-'
  if (Object.is(n, -0) || n === 0) return '0'
  const s = Math.abs(n) % 1 === 0 ? String(Math.abs(n)) : Math.abs(n).toFixed(2).replace(/0$/, '')
  return (n > 0 ? '+' : '-') + s
}
function isLow(odds) {
  if (!odds) return ''
  const w = Number(odds.win), d = Number(odds.draw), l = Number(odds.lose)
  const m = Math.min(w, d, l)
  if (m === w) return 'win'
  if (m === l) return 'loss'
  return 'draw'
}
function lowClass(odds, key) {
  return isLow(odds) === key ? `low-${key}` : 'ol-n'
}
/** 低赔方(=让球方/强方)初→终: up上升 / down下降 / flat不变 */
function lowMoveDir(spf) {
  if (!spf?.initial || !spf?.current) return null
  const key = isLow(spf.initial)
  if (!key) return null
  const field = key === 'loss' ? 'lose' : key
  const o = Number(spf.initial[field])
  const c = Number(spf.current[field])
  if (Number.isNaN(o) || Number.isNaN(c)) return null
  // 与 scraper 变动阈值对齐: ≤0.005 视为不变
  if (c < o - 0.005) return 'down'
  if (c > o + 0.005) return 'up'
  return 'flat'
}
function moveLabel(spf) {
  const d = lowMoveDir(spf)
  if (d === 'up') return '上升'
  if (d === 'down') return '下降'
  if (d === 'flat') return '不变'
  return '-'
}
function moveClass(spf) {
  const d = lowMoveDir(spf)
  return d ? `mv-${d}` : ''
}
function parseHit(desc) {
  if (!desc) return null
  const m = String(desc).match(/(\d+(?:\.\d+)?)%\s*\((\d+)\/(\d+)\)/)
  if (!m) return null
  return { pct: Number(m[1]), n: Number(m[2]), total: Number(m[3]) }
}
function getDetail(f6, name) {
  const d = (f6?.details || []).find(x => x.name === name)
  return d ? d.desc : ''
}
function ahStats(f6) {
  const up = parseHit(getDetail(f6, '上盘命中'))
  const lo = parseHit(getDetail(f6, '下盘命中'))
  const pushDesc = getDetail(f6, '走水')
  const pushM = pushDesc ? String(pushDesc).match(/^(\d+)/) : null
  const total = up?.total || lo?.total || 0
  const upper = up?.n || 0
  const lower = lo?.n || 0
  const push = pushM ? Number(pushM[1]) : 0
  const upperPct = total ? Math.round((upper / total) * 100) : 0
  const lowerPct = total ? Math.round((lower / total) * 100) : 0
  return { total, upper, lower, push, upperPct, lowerPct }
}
function focusSide(f6) {
  const dir = f6?.direction
  if (dir === 'upper' || dir === 'lower') return dir
  const s = ahStats(f6)
  // 比场次更稳: 百分比四舍五入后也可能相等(如 10/10/4 → 42/42)
  if (s.lower > s.upper) return 'lower'
  if (s.upper > s.lower) return 'upper'
  if (s.lowerPct > s.upperPct) return 'lower'
  if (s.upperPct > s.lowerPct) return 'upper'
  return 'neutral' // 上=下, 无领先侧
}
function focusPct(f6) {
  const s = ahStats(f6)
  const side = focusSide(f6)
  if (side === 'upper') return s.upperPct
  if (side === 'lower') return s.lowerPct
  return Math.max(s.upperPct, s.lowerPct)
}
function focusHitLabel(f6) {
  const side = focusSide(f6)
  if (side === 'upper') return '上盘命中'
  if (side === 'lower') return '下盘命中'
  return '两侧持平'
}
function shortReason(reason) {
  if (!reason) return ''
  let s = reason.replace(/^历史同赔\d+场盘路/, '')
  s = s.replace(/^[上下]盘命中\d+(?:\.\d+)?%\(\d+\/\d+\)[,，]\s*/, '')
  return s.trim() || reason
}
function resultClass(r) {
  if (r === '主胜') return 'r-win'
  if (r === '平局') return 'r-draw'
  if (r === '客胜') return 'r-loss'
  return ''
}
function ahResultClass(ah) {
  if (ah === '上盘' || ah === '半上') return 'ah-upper'
  if (ah === '下盘' || ah === '半下') return 'ah-lower'
  if (ah === '走水') return 'ah-push'
  return ''
}
function openSimilar(it) {
  similarMatches.value = it?.f6?.matches || []
  similarRefScore.value = it?.f6?.refScore != null ? it.f6.refScore : null
  showSimilar.value = true
}
function closeSimilar() {
  showSimilar.value = false
  similarRefScore.value = null
}

async function loadBatch() {
  loading.value = true
  dirFilters.value = []
  moveFilters.value = []
  sortMode.value = 'default'
  try {
    const data = await request({ url: '/api/predict/batch-similar', data: { date: date.value, status: status.value } })
    items.value = data?.items || []
    summary.value = data?.summary || { total: 0, upper: 0, lower: 0, neutral: 0 }
  } catch (e) {
    uni.showToast({ title: '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onLoad((options) => {
  const today = new Date().toISOString().slice(0, 10)
  date.value = options?.date || today
  status.value = options?.status || 'not_started'
  loadBatch()
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.batch-page {
  min-height: 100vh;
  width: 100%;
  max-width: 100vw;
  overflow-x: hidden;
  background: #f7faf9;
  display: flex;
  flex-direction: column;

  &, view, text, scroll-view {
    box-sizing: border-box;
    max-width: 100%;
  }
}

/* 顶栏: 纯色 + 文字统计,无 chip 块 */
.summary-bar {
  background: $frbt-primary;
  padding: 22rpx 28rpx 20rpx;
  .sum-row {
    display: flex; align-items: baseline; justify-content: space-between;
    margin-bottom: 10rpx;
  }
  .sum-title { font-size: 28rpx; font-weight: 600; color: #fff; }
  .sum-total { font-size: 22rpx; color: rgba(255,255,255,0.7); }
  .sum-stats {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8rpx;
    .st {
      font-size: 22rpx; color: rgba(255,255,255,0.85);
      &.upper { color: #fecaca; font-weight: 600; }
      &.lower { color: #a7f3d0; font-weight: 600; }
      &.neutral { color: rgba(255,255,255,0.85); font-weight: 500; }
      &.hit { color: #fde68a; font-weight: 600; }
    }
    .st-sep { font-size: 22rpx; color: rgba(255,255,255,0.35); }
  }
}

.ctrl-bar {
  background: #fff;
  border-bottom: 1rpx solid #eef2f5;
  padding: 12rpx 28rpx 14rpx;
  .ctrl-row {
    display: flex; align-items: center; flex-wrap: wrap; gap: 12rpx;
    & + .ctrl-row { margin-top: 10rpx; }
  }
  .ctrl-lab { font-size: 22rpx; color: #94a3b8; margin-right: 4rpx; flex-shrink: 0; }
  .ctrl-btn {
    font-size: 22rpx; color: #64748b;
    padding: 6rpx 16rpx; border-radius: 6rpx;
    border: 1rpx solid #e2e8f0; background: #f8fafc;
    &.active {
      color: $frbt-primary; border-color: rgba($frbt-primary, 0.45);
      background: rgba($frbt-primary, 0.08); font-weight: 600;
    }
    &.upper.active { color: #dc2626; border-color: rgba(#dc2626, 0.4); background: rgba(#dc2626, 0.06); }
    &.lower.active { color: #059669; border-color: rgba(#059669, 0.4); background: rgba(#059669, 0.06); }
    &.hit.active { color: #d97706; border-color: rgba(#d97706, 0.4); background: rgba(#d97706, 0.08); }
    &.sample.active { color: #0369a1; border-color: rgba(#0369a1, 0.4); background: rgba(#0369a1, 0.06); }
    &.hitpct.active { color: #7c3aed; border-color: rgba(#7c3aed, 0.4); background: rgba(#7c3aed, 0.06); }
    &.score.active { color: #0f766e; border-color: rgba(#0f766e, 0.4); background: rgba(#0f766e, 0.06); }
    &.single.active { color: #dc2626; border-color: rgba(#dc2626, 0.4); background: rgba(#dc2626, 0.06); }
    &.move-up.active { color: #dc2626; border-color: rgba(#dc2626, 0.4); background: rgba(#dc2626, 0.06); }
    &.move-down.active { color: #059669; border-color: rgba(#059669, 0.4); background: rgba(#059669, 0.06); }
    &:active { opacity: 0.7; }
  }
  .filter-count {
    display: flex; align-items: baseline; gap: 12rpx;
    margin-top: 12rpx; padding-top: 10rpx;
    border-top: 1rpx solid #f1f5f9;
    .fc-main { font-size: 24rpx; font-weight: 600; color: #0f172a; }
    .fc-sub { font-size: 22rpx; color: #94a3b8; }
    .fc-hit { font-size: 22rpx; font-weight: 600; color: #d97706; }
    .fc-clear {
      margin-left: auto; font-size: 22rpx; color: $frbt-primary; padding: 4rpx 0;
      &:active { opacity: 0.6; }
    }
  }
}

.state-hint {
  padding: 120rpx 0; display: flex; flex-direction: column; align-items: center; gap: 16rpx;
  text { font-size: 26rpx; color: #94a3b8; }
  .state-clear { font-size: 24rpx; color: $frbt-primary; padding: 8rpx 16rpx; }
}

.card-list { flex: 1; width: 100%; height: 0; }
.card-list-inner { padding: 16rpx 24rpx 80rpx; width: 100%; }

/* 卡片: 白底 + 细分隔,无阴影/左边条/内嵌色盒 */
.match-card {
  background: #fff;
  border-radius: 10rpx;
  padding: 22rpx 24rpx 16rpx;
  margin-bottom: 14rpx;
  border: 1rpx solid #e8eef0;
  width: 100%;
}

.row-meta {
  display: flex; align-items: center; gap: 12rpx; margin-bottom: 14rpx;
  .league { font-size: 22rpx; color: #64748b; font-weight: 500; }
  .time { font-size: 22rpx; color: #94a3b8; }
  .single-tag {
    font-size: 20rpx; color: #dc2626; font-weight: 600;
    padding: 2rpx 8rpx; border-radius: 6rpx;
    border: 1rpx solid rgba(#dc2626, 0.4); background: rgba(#dc2626, 0.06);
    flex-shrink: 0;
  }
  .dir-wrap {
    margin-left: auto; display: flex; align-items: baseline; gap: 8rpx; flex-shrink: 0;
  }
  .dir {
    font-size: 24rpx; font-weight: 600;
    &.upper { color: #dc2626; }
    &.lower { color: #059669; }
    &.neutral { color: #94a3b8; }
    &.ref-weak { color: #94a3b8; font-weight: 500; }
    &.ref-strong { font-weight: 700; }
  }
  .ref-score {
    font-size: 24rpx; font-weight: 600; font-variant-numeric: tabular-nums;
    &.upper { color: #dc2626; }
    &.lower { color: #059669; }
    &.neutral { color: #94a3b8; }
    &.ref-weak { color: #94a3b8; font-weight: 500; }
    &.ref-strong { font-weight: 700; }
  }
}

.row-teams {
  display: flex; align-items: center; justify-content: center;
  gap: 16rpx; margin-bottom: 18rpx; width: 100%;
  .team {
    flex: 1; min-width: 0; font-size: 28rpx; font-weight: 600; color: #1e293b;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    &.home { text-align: right; }
    &.away { text-align: left; }
  }
  .vs { font-size: 20rpx; color: #cbd5e1; flex-shrink: 0; }
}

.row-hit {
  margin-bottom: 14rpx;
  &.empty { padding: 4rpx 0; }
  .hit-top {
    display: flex; align-items: baseline; gap: 10rpx; margin-bottom: 10rpx;
  }
  .pct {
    font-size: 40rpx; font-weight: 700; line-height: 1;
    &.upper { color: #dc2626; }
    &.lower { color: #059669; }
    &.neutral { color: #64748b; }
  }
  .pct-lab {
    font-size: 24rpx; font-weight: 500;
    &.upper { color: #dc2626; }
    &.lower { color: #059669; }
    &.neutral { color: #64748b; }
  }
  .sample { margin-left: auto; font-size: 22rpx; color: #94a3b8; }
  .bar {
    display: flex; height: 6rpx; border-radius: 6rpx; overflow: hidden;
    background: #eef2f5; margin-bottom: 10rpx;
    .bar-u { background: #f87171; height: 100%; }
    .bar-l { background: #34d399; height: 100%; }
  }
  .reason { font-size: 24rpx; color: #64748b; line-height: 1.45; word-break: break-word; }
}

.row-ah {
  display: flex; align-items: center; flex-wrap: wrap; gap: 8rpx;
  margin-bottom: 12rpx; padding: 10rpx 0;
  border-top: 1rpx solid #f1f5f9;
  font-size: 24rpx; color: #334155;
  .ah-lab { font-size: 22rpx; color: #94a3b8; }
  .ah-num { font-size: 26rpx; font-weight: 700; color: #0f172a; font-variant-numeric: tabular-nums; }
  .ah-miss { font-size: 22rpx; color: #94a3b8; }
  .ac-score { font-weight: 700; color: #1e293b; }
  .ac-sep { color: #cbd5e1; }
  .ac-hit { margin-left: auto; color: #059669; font-weight: 600; font-size: 22rpx; }
  .ac-miss { margin-left: auto; color: #dc2626; font-weight: 600; font-size: 22rpx; }
}

.row-odds {
  display: flex; align-items: center; flex-wrap: wrap; gap: 8rpx;
  font-size: 22rpx; color: #64748b; margin-bottom: 4rpx;
  .ol-lab { font-size: 22rpx; color: #64748b; font-weight: 500; }
  .ol-muted { color: #94a3b8; }
  .ol-n { color: #64748b; }
  .low-win { color: #dc2626; font-weight: 600; }
  .low-draw { color: #d97706; font-weight: 600; }
  .low-loss { color: #059669; font-weight: 600; }
  .ol-move {
    margin-left: auto; font-size: 20rpx; font-weight: 600;
    &.mv-up { color: #dc2626; }
    &.mv-down { color: #059669; }
    &.mv-flat { color: #94a3b8; font-weight: 500; }
  }
}

.row-detail {
  padding: 10rpx 0 2rpx; text-align: right;
  text { font-size: 22rpx; color: $frbt-primary; }
  &:active { opacity: 0.6; }
}

/* 弹窗 */
.similar-mask {
  position: fixed; inset: 0; background: rgba(15,23,42,0.4); z-index: 200;
}
.similar-modal {
  position: fixed; top: 50%; left: 3vw; right: 3vw; bottom: auto;
  max-height: 88vh; height: auto;
  background: #fff; border-radius: 12rpx; z-index: 201;
  display: flex; flex-direction: column;
  transform: translateY(-50%) scale(0.96); opacity: 0;
  transition: transform 0.2s ease, opacity 0.2s ease;
  pointer-events: none;
  &.show { transform: translateY(-50%) scale(1); opacity: 1; pointer-events: auto; }
}
.similar-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 20rpx 24rpx; border-bottom: 1rpx solid #e2e8f0; flex-shrink: 0;
  .similar-title-wrap { display: flex; align-items: baseline; gap: 12rpx; min-width: 0; }
  .similar-title { font-size: 28rpx; font-weight: 600; color: #1e293b; }
  .similar-ref { font-size: 22rpx; color: #64748b; font-variant-numeric: tabular-nums; }
  .similar-close { font-size: 24rpx; color: $frbt-primary; padding: 8rpx 4rpx; }
}
.similar-body {
  flex: 0 1 auto; overflow: auto; min-height: 0;
  max-height: calc(88vh - 100rpx);
}
.similar-table { min-width: 1300rpx; padding: 0 16rpx 24rpx; }
.similar-row {
  display: flex; align-items: center; padding: 14rpx 0;
  border-bottom: 1rpx solid #f1f5f9; gap: 4rpx;
}
.similar-thead {
  position: sticky; top: 0; background: #f8fafb;
  font-weight: 600; color: #64748b; font-size: 20rpx; z-index: 1;
}
.similar-row:not(.similar-thead) { font-size: 20rpx; color: #334155; }
.similar-empty { text-align: center; padding: 60rpx; color: #94a3b8; font-size: 24rpx; }

.col-sim { width: 90rpx; text-align: center; }
.col-date { width: 110rpx; text-align: center; }
.col-league { width: 90rpx; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-league.league-same { color: #2979ff; font-weight: 600; }
.col-team { width: 130rpx; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-score { width: 70rpx; text-align: center; font-weight: 600; }
.col-result { width: 70rpx; text-align: center; font-weight: 500; }
.col-odds { width: 170rpx; text-align: center; }
.col-handicap { width: 70rpx; text-align: center; }
.col-ah-result { width: 70rpx; text-align: center; font-weight: 500; }

.r-win { color: #dc2626; }
.r-draw { color: #d97706; }
.r-loss { color: #059669; }
.ah-upper { color: #dc2626; }
.ah-lower { color: #059669; }
.ah-push { color: #64748b; }
</style>
