<template>
  <view>
    <view class="similar-mask" v-if="visible" @tap="emit('close')"></view>
    <view class="similar-modal" :class="{ show: visible }">
      <view class="similar-header">
        <view class="similar-title-wrap">
          <text class="similar-title">历史同赔详情</text>
          <text v-if="refScore != null" class="similar-ref">参考分 {{ refScore }}</text>
          <text
            v-if="isJapan"
            class="jp-toggle"
            :class="{ on: japanOnly, loading }"
            @tap.stop="toggleJapan"
          >仅日本</text>
          <text
            v-else-if="isSameLeague"
            class="jp-toggle"
            :class="{ on: leagueOnly, loading }"
            @tap.stop="toggleLeague"
          >同赛事</text>
        </view>
        <text class="similar-close" @tap="emit('close')">关闭</text>
      </view>

      <scroll-view
        v-if="snapshots.length >= 2"
        class="snap-bar"
        scroll-x
        :show-scrollbar="false"
      >
        <view class="snap-row">
          <view
            v-for="s in snapshotsDesc"
            :key="s.id"
            class="snap-chip"
            :class="{ on: s.id === snapshotId }"
            @tap.stop="selectSnapshot(s.id)"
          >
            <text class="snap-lab">{{ s.label }}</text>
            <view class="snap-odds">
              <text :class="lowClass(s, 'win')">{{ fmt(s.win) }}</text>
              <text :class="lowClass(s, 'draw')">{{ fmt(s.draw) }}</text>
              <text :class="lowClass(s, 'loss')">{{ fmt(s.lose) }}</text>
              <text v-if="deltaMark(s)" class="snap-d" :class="deltaClass(s)">{{ deltaMark(s) }}</text>
            </view>
          </view>
        </view>
      </scroll-view>
      <view v-if="isHistorical" class="snap-hint">
        <text>按 {{ selectedLabel }} 赔率匹配 · 初盘固定 · 非最新{{ extraHint }}</text>
      </view>
      <view v-else-if="japanOnly" class="jp-hint">
        <text>仅日职/日乙/杯赛 · 低赔±0.05 · 高赔±0.15</text>
      </view>
      <view v-else-if="leagueOnly" class="jp-hint">
        <text>仅{{ league || '同名赛事' }} · 低赔±0.05 · 高赔±0.15</text>
      </view>

      <view v-if="stats.total > 0" class="similar-stats">
        <view class="stats-row">
          <text class="stats-label">胜平负</text>
          <text class="stats-item r-win">主胜 {{ stats.win }}({{ stats.winPct }}%)</text>
          <text class="stats-item r-draw">平 {{ stats.draw }}({{ stats.drawPct }}%)</text>
          <text class="stats-item r-loss">客胜 {{ stats.loss }}({{ stats.lossPct }}%)</text>
          <text class="stats-n">{{ stats.total }}场</text>
        </view>
        <view class="stats-row">
          <text class="stats-label">盘路</text>
          <template v-if="stats.ahTotal > 0">
            <text class="stats-item ah-upper">上盘 {{ stats.upper }}({{ stats.upperPct }}%){{ stats.halfUp ? ` 含半${stats.halfUp}` : '' }}</text>
            <text class="stats-item ah-push">走水 {{ stats.push }}({{ stats.pushPct }}%)</text>
            <text class="stats-item ah-lower">下盘 {{ stats.lower }}({{ stats.lowerPct }}%){{ stats.halfDown ? ` 含半${stats.halfDown}` : '' }}</text>
            <text class="stats-n">{{ stats.ahTotal }}场</text>
          </template>
          <text v-else class="stats-empty">无亚盘数据</text>
        </view>
      </view>
      <scroll-view class="similar-body" scroll-y scroll-x>
        <view class="similar-table">
          <view class="similar-row similar-thead">
            <text class="col-sim">相似度</text>
            <text class="col-team">主队</text>
            <text class="col-score">比分</text>
            <text class="col-team">客队</text>
            <text class="col-result">结果</text>
            <text class="col-ah-result">盘路</text>
            <text class="col-ah">亚初</text>
            <text class="col-ah">亚终</text>
            <text class="col-odds">初盘</text>
            <text class="col-odds">终盘</text>
            <text class="col-date">日期</text>
            <text class="col-league">联赛</text>
          </view>
          <view
            class="similar-row"
            :class="{ 'is-single': m.isSingle }"
            v-for="(m, mi) in matches"
            :key="mi"
          >
            <view class="col-sim">
              <text class="sim-num">{{ m.similarity }}%</text>
              <text class="single-mark" :class="{ on: m.isSingle }">{{ m.isSingle ? '单' : '' }}</text>
            </view>
            <text class="col-team">{{ m.homeTeam }}</text>
            <text class="col-score">{{ m.score }}</text>
            <text class="col-team">{{ m.awayTeam }}</text>
            <text class="col-result" :class="resultClass(m.result)">{{ m.result }}</text>
            <text class="col-ah-result" :class="ahResultClass(m.ahResult)">{{ m.ahResult || '-' }}</text>
            <text class="col-ah">{{ m.handicapOpen || '-' }}</text>
            <text class="col-ah">{{ m.handicapClose || m.handicap || '-' }}</text>
            <text class="col-odds">{{ m.openOdds }}</text>
            <text class="col-odds">{{ m.closeOdds }}</text>
            <text class="col-date">{{ m.date }}</text>
            <text class="col-league" :class="{ 'league-same': m.sameLeague }">{{ m.league }}</text>
          </view>
          <view v-if="!loading && matches.length === 0" class="similar-empty">
            <text>暂无历史同赔数据</text>
          </view>
        </view>
      </scroll-view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { request } from '@/utils/http'
import { calcSimilarStats, filterSimilarWithAh } from '@/utils/similarStats'
import { isJapanLeague } from '@/utils/japanLeague'
import { isSameLeagueEligible } from '@/utils/sameLeague'

const props = defineProps({
  visible: { type: Boolean, default: false },
  matchId: { type: String, default: '' },
  league: { type: String, default: '' },
  initialMatches: { type: Array, default: () => [] },
  initialRefScore: { type: Number, default: null },
  initialSnapshots: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'same-event'])

const matches = ref([])
const snapshots = ref([])
const snapshotId = ref('latest')
const japanOnly = ref(false)
const leagueOnly = ref(false)
const loading = ref(false)
const refScore = ref(null)
let fetchSeq = 0

const isJapan = computed(() => isJapanLeague(props.league))
const isSameLeague = computed(() => isSameLeagueEligible(props.league))
const snapshotsDesc = computed(() => snapshots.value.slice().reverse())
const stats = computed(() => calcSimilarStats(matches.value))
const isHistorical = computed(() => snapshotId.value !== 'latest')
const selectedLabel = computed(() => {
  const s = snapshots.value.find((x) => x.id === snapshotId.value)
  return s?.label || '该时刻'
})
const extraHint = computed(() => {
  if (japanOnly.value) return ' · 仅日本'
  if (leagueOnly.value) return ` · 仅${props.league || '同名赛事'}`
  return ''
})

function applyList(list) {
  return filterSimilarWithAh(list || [])
}

function fmt(v) {
  return v == null ? '-' : Number(v).toFixed(2)
}

function lowKey(s) {
  if (!s) return ''
  const w = Number(s.win)
  const d = Number(s.draw)
  const l = Number(s.lose)
  const m = Math.min(w, d, l)
  if (m === w) return 'win'
  if (m === l) return 'loss'
  return 'draw'
}

function lowClass(s, key) {
  return lowKey(s) === key ? `low-${key}` : 'od-n'
}

function deltaMark(s) {
  const d = Number(s?.lowDelta)
  if (Number.isNaN(d) || Math.abs(d) <= 0.005) return ''
  return d > 0 ? '升' : '降'
}

function deltaClass(s) {
  const d = Number(s?.lowDelta)
  if (d > 0.005) return 'up'
  if (d < -0.005) return 'down'
  return ''
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

function resetLocal() {
  fetchSeq += 1
  snapshotId.value = 'latest'
  japanOnly.value = false
  leagueOnly.value = false
  loading.value = false
  snapshots.value = Array.isArray(props.initialSnapshots) ? props.initialSnapshots.slice() : []
  matches.value = applyList(props.initialMatches)
  refScore.value = props.initialRefScore != null ? props.initialRefScore : null
}

async function fetchSimilar({ writeSameEvent = false } = {}) {
  const mid = props.matchId
  if (!mid) {
    uni.showToast({ title: '比赛ID缺失', icon: 'none' })
    return
  }
  const seq = ++fetchSeq
  loading.value = true
  try {
    const data = {
      japan_only: !!japanOnly.value,
      league_only: !!leagueOnly.value,
    }
    if (snapshotId.value && snapshotId.value !== 'latest') {
      data.snapshot = snapshotId.value
    }
    const res = await request({
      url: `/api/predict/${encodeURIComponent(mid)}/similar-odds`,
      method: 'GET',
      data,
    })
    if (seq !== fetchSeq) return
    if (Array.isArray(res?.snapshots)) {
      snapshots.value = res.snapshots
    }
    matches.value = applyList(res?.matches || [])
    refScore.value = res?.refScore != null ? res.refScore : null
    if (writeSameEvent && !isHistorical.value) {
      emit('same-event', { matches: res?.matches || [] })
    }
  } catch (e) {
    if (seq !== fetchSeq) return
    uni.showToast({ title: e?.message || '同赔匹配失败', icon: 'none' })
  } finally {
    if (seq === fetchSeq) loading.value = false
  }
}

function selectSnapshot(id) {
  if (!id || id === snapshotId.value || loading.value) return
  snapshotId.value = id
  fetchSimilar()
}

function toggleJapan() {
  if (!isJapan.value || loading.value) return
  japanOnly.value = !japanOnly.value
  if (japanOnly.value) leagueOnly.value = false
  fetchSimilar()
}

function toggleLeague() {
  if (!isSameLeague.value || loading.value) return
  const turningOn = !leagueOnly.value
  leagueOnly.value = turningOn
  if (turningOn) japanOnly.value = false
  fetchSimilar({ writeSameEvent: turningOn })
}

watch(
  () => [props.visible, props.matchId],
  ([vis]) => {
    if (!vis) return
    resetLocal()
    const hasDefault = (props.initialMatches || []).length > 0 || props.initialRefScore != null
    if (!hasDefault) fetchSimilar()
  },
)
</script>

<style lang="scss" scoped>
.similar-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.4); z-index: 200;
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
}
.similar-title-wrap { display: flex; align-items: center; gap: 12rpx; min-width: 0; flex-wrap: wrap; }
.similar-title { font-size: 28rpx; font-weight: 600; color: #1e293b; }
.similar-ref { font-size: 22rpx; color: #64748b; font-variant-numeric: tabular-nums; }
.jp-toggle {
  font-size: 22rpx; color: #64748b; background: #f1f5f9;
  border: 1rpx solid #cbd5e1; border-radius: 6rpx;
  padding: 4rpx 12rpx; line-height: 1.4;
  &.on { color: #fff; background: #0f766e; border-color: #0f766e; }
  &.loading { opacity: 0.55; }
}
.similar-close { font-size: 24rpx; color: #0d9488; padding: 8rpx 4rpx; }

.snap-bar {
  flex-shrink: 0;
  width: 100%;
  white-space: nowrap;
  border-bottom: 1rpx solid #e2e8f0;
  background: #fff;
}
.snap-row {
  display: inline-flex;
  align-items: stretch;
  gap: 8rpx;
  padding: 10rpx 16rpx 12rpx;
}
.snap-chip {
  flex-shrink: 0;
  min-width: 168rpx;
  padding: 8rpx 12rpx;
  background: #f8fafc;
  border: 1rpx solid #e2e8f0;
  border-radius: 6rpx;
  &.on { background: #f0fdfa; border-color: #0f766e; }
}
.snap-lab {
  display: block;
  font-size: 18rpx;
  color: #64748b;
  line-height: 1.3;
  margin-bottom: 4rpx;
}
.snap-chip.on .snap-lab { color: #0f766e; font-weight: 600; }
.snap-odds {
  display: flex;
  align-items: baseline;
  gap: 6rpx;
  font-size: 20rpx;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
.od-n { color: #94a3b8; }
.low-win { color: #dc2626; font-weight: 700; }
.low-draw { color: #d97706; font-weight: 700; }
.low-loss { color: #059669; font-weight: 700; }
.snap-d { font-size: 18rpx; font-weight: 600; }
.snap-d.up { color: #dc2626; }
.snap-d.down { color: #059669; }

.snap-hint,
.jp-hint {
  flex-shrink: 0;
  padding: 8rpx 24rpx;
  background: #f0fdfa;
  border-bottom: 1rpx solid #ccfbf1;
  font-size: 20rpx;
  color: #0f766e;
}
.snap-hint { background: #fff7ed; border-bottom-color: #fed7aa; color: #c2410c; }

.similar-stats {
  flex-shrink: 0;
  padding: 12rpx 24rpx;
  background: #f8fafb;
  border-bottom: 1rpx solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}
.stats-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8rpx 16rpx;
  font-size: 22rpx;
  font-variant-numeric: tabular-nums;
}
.stats-label {
  width: 72rpx;
  flex-shrink: 0;
  color: #64748b;
  font-weight: 600;
  font-size: 20rpx;
}
.stats-item { font-weight: 500; }
.stats-n { color: #94a3b8; font-size: 20rpx; margin-left: 4rpx; }
.stats-empty { color: #94a3b8; font-size: 20rpx; }

.similar-body {
  flex: 0 1 auto; overflow: auto; min-height: 0;
  max-height: calc(88vh - 280rpx);
}
.similar-table { min-width: 1430rpx; padding: 0 16rpx 24rpx; }
.similar-row {
  display: flex; align-items: center; padding: 14rpx 0;
  border-bottom: 1rpx solid #f1f5f9; gap: 4rpx;
  &.is-single { background: #fff7f7; }
}
.similar-thead {
  position: sticky; top: 0; background: #f8fafb;
  font-weight: 600; color: #64748b; font-size: 20rpx; z-index: 1;
}
.similar-row:not(.similar-thead) { font-size: 20rpx; color: #334155; }
.similar-empty { text-align: center; padding: 60rpx; color: #94a3b8; font-size: 24rpx; }

.col-sim {
  width: 120rpx; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; gap: 4rpx;
}
.sim-num {
  width: 72rpx; text-align: right; flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.single-mark {
  width: 28rpx; height: 28rpx; flex-shrink: 0;
  font-size: 16rpx; font-weight: 700;
  color: transparent; text-align: center;
  border: 1rpx solid transparent; border-radius: 6rpx;
  line-height: 26rpx;
  &.on { color: #dc2626; border-color: #dc2626; }
}
.col-date { width: 110rpx; text-align: center; }
.col-league { width: 90rpx; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-league.league-same { color: #2979ff; font-weight: 600; }
.col-team { width: 130rpx; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-score { width: 70rpx; text-align: center; font-weight: 600; }
.col-result { width: 70rpx; text-align: center; font-weight: 500; }
.col-odds { width: 170rpx; text-align: center; }
.col-ah { width: 72rpx; text-align: center; font-variant-numeric: tabular-nums; }
.col-ah-result { width: 70rpx; text-align: center; font-weight: 500; }

.r-win { color: #dc2626; }
.r-draw { color: #d97706; }
.r-loss { color: #059669; }
.ah-upper { color: #dc2626; }
.ah-lower { color: #059669; }
.ah-push { color: #64748b; }
</style>
