<template>
  <view class="batch-page">
    <!-- 顶部汇总 -->
    <view class="summary-bar">
      <view class="sum-row">
        <text class="sum-date">{{ date.slice(5) }} 同赔分析</text>
        <text class="sum-total">{{ summary.total }} 场</text>
      </view>
      <view class="sum-chips">
        <view class="chip upper"><text>↑ 上盘 {{ summary.upper }}</text></view>
        <view class="chip lower"><text>↓ 下盘 {{ summary.lower }}</text></view>
        <view class="chip neutral"><text>− 中性 {{ summary.neutral }}</text></view>
        <view v-if="isFinished && summary.hitTotal" class="chip hit"><text>命中 {{ summary.hitRate }}% ({{ summary.hitTotal }}场)</text></view>
      </view>
    </view>

    <!-- 加载态 -->
    <view v-if="loading" class="state-hint"><text>批量同赔分析中…</text></view>
    <!-- 空态 -->
    <view v-else-if="items.length === 0" class="state-hint"><text>该日无{{ isFinished ? '已结束' : '在售' }}竞彩比赛</text></view>
    <!-- 列表 -->
    <scroll-view v-else class="card-list" scroll-y>
      <view
        v-for="it in sortedItems"
        :key="it.matchId"
        class="match-card"
        :class="it.f6?.direction || 'neutral'"
      >
        <!-- 头部: 联赛/时间/队名 + 方向 -->
        <view class="card-head">
          <view class="head-left">
            <text class="league-tag" :style="{ backgroundColor: pickLeagueColor(it.league) }">{{ it.league || '-' }}</text>
            <text class="match-time">{{ (it.matchTime || '').slice(0, 5) }}</text>
          </view>
          <view class="dir-badge" :class="it.f6?.direction || 'neutral'">
            <text>{{ dirArrow(it.f6?.direction) }} {{ dirLabel(it.f6?.direction) }} {{ it.f6?.score ?? '' }}</text>
          </view>
        </view>

        <view class="card-teams">
          <text class="team-name">{{ it.homeTeam?.name }}</text>
          <text class="team-vs">VS</text>
          <text class="team-name">{{ it.awayTeam?.name }}</text>
        </view>

        <!-- 初盘/终盘赔率对比 -->
        <view class="odds-box" v-if="it.spf">
          <view class="odds-col">
            <text class="odds-label">初盘</text>
            <view class="odds-row">
              <text class="o-win" :class="{ low: isLow(it.spf.initial) === 'win' }">{{ fmt(it.spf.initial.win) }}</text>
              <text class="o-draw" :class="{ low: isLow(it.spf.initial) === 'draw' }">{{ fmt(it.spf.initial.draw) }}</text>
              <text class="o-loss" :class="{ low: isLow(it.spf.initial) === 'loss' }">{{ fmt(it.spf.initial.lose) }}</text>
            </view>
          </view>
          <text class="odds-arrow">→</text>
          <view class="odds-col">
            <text class="odds-label">终盘</text>
            <view class="odds-row">
              <text class="o-win" :class="{ low: isLow(it.spf.current) === 'win' }">{{ fmt(it.spf.current.win) }}</text>
              <text class="o-draw" :class="{ low: isLow(it.spf.current) === 'draw' }">{{ fmt(it.spf.current.draw) }}</text>
              <text class="o-loss" :class="{ low: isLow(it.spf.current) === 'loss' }">{{ fmt(it.spf.current.lose) }}</text>
            </view>
          </view>
          <view class="move-tag" :class="it.hasMove ? 'move-yes' : 'move-no'">
            <text>{{ it.hasMove ? '有变动' : '无变动' }}</text>
          </view>
        </view>

        <!-- 实际比分/结果/盘路(已结束回测) -->
        <view class="actual-box" v-if="isFinished && it.actualScore">
          <view class="actual-cell">
            <text class="ac-label">比分</text>
            <text class="ac-val score-val">{{ it.actualScore }}</text>
          </view>
          <view class="actual-cell">
            <text class="ac-label">结果</text>
            <text class="ac-val" :class="resultClass(it.actualResult)">{{ it.actualResult || '-' }}</text>
          </view>
          <view class="actual-cell">
            <text class="ac-label">盘路</text>
            <text class="ac-val" :class="ahResultClass(it.actualAh)">{{ it.actualAh || '无亚盘' }}</text>
          </view>
          <view class="hit-tag" v-if="it.hit === true"><text>命中</text></view>
          <view class="hit-tag miss" v-else-if="it.hit === false"><text>未中</text></view>
        </view>

        <!-- 盘路统计摘要 -->
        <view class="stat-row" v-if="getDetail(it.f6, '盘路分布')">
          <text class="stat-desc">{{ getDetail(it.f6, '盘路分布') }}</text>
        </view>
        <view class="reason-row" v-if="it.f6?.reason"><text>{{ it.f6.reason }}</text></view>

        <!-- 查看同赔详情按钮 -->
        <view class="detail-btn" @tap="openSimilar(it)">
          <text>查看同赔详情 ({{ it.f6?.matches?.length || 0 }}场) →</text>
        </view>
      </view>
    </scroll-view>

    <!-- 同赔详情弹窗(复刻预测页) -->
    <view class="similar-mask" v-if="showSimilar" @tap="closeSimilar"></view>
    <view class="similar-modal" :class="{ show: showSimilar }">
      <view class="similar-header">
        <text class="similar-title">历史同赔详情</text>
        <text class="similar-close" @tap="closeSimilar">✕</text>
      </view>
      <scroll-view class="similar-body" scroll-y scroll-x>
        <view class="similar-table">
          <view class="similar-row similar-thead">
            <text class="col-sim">相似度</text>
            <text class="col-date">日期</text>
            <text class="col-league">联赛</text>
            <text class="col-team">主队</text>
            <text class="col-score">比分</text>
            <text class="col-team">客队</text>
            <text class="col-result">结果</text>
            <text class="col-odds">初盘</text>
            <text class="col-odds">终盘</text>
            <text class="col-handicap">让球</text>
            <text class="col-ah-result">盘路</text>
          </view>
          <view class="similar-row" v-for="(m, mi) in similarMatches" :key="mi">
            <text class="col-sim">{{ m.similarity }}%</text>
            <text class="col-date">{{ m.date }}</text>
            <text class="col-league" :class="{ 'league-same': m.sameLeague }">{{ m.league }}</text>
            <text class="col-team">{{ m.homeTeam }}</text>
            <text class="col-score">{{ m.score }}</text>
            <text class="col-team">{{ m.awayTeam }}</text>
            <text class="col-result" :class="resultClass(m.result)">{{ m.result }}</text>
            <text class="col-odds">{{ m.openOdds }}</text>
            <text class="col-odds">{{ m.closeOdds }}</text>
            <text class="col-handicap">{{ m.handicap || '-' }}</text>
            <text class="col-ah-result" :class="ahResultClass(m.ahResult)">{{ m.ahResult || '-' }}</text>
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

const isFinished = computed(() => status.value === 'finished')

const DIR_ORDER = { upper: 0, lower: 1, neutral: 2 }
const sortedItems = computed(() => {
  return [...items.value].sort((a, b) => {
    const da = DIR_ORDER[a.f6?.direction] ?? 2
    const db = DIR_ORDER[b.f6?.direction] ?? 2
    if (da !== db) return da - db
    return (b.f6?.score ?? 0) - (a.f6?.score ?? 0)
  })
})

function dirLabel(dir) { return dir === 'upper' ? '上盘' : dir === 'lower' ? '下盘' : '中性' }
function dirArrow(dir) { return dir === 'upper' ? '↑' : dir === 'lower' ? '↓' : '−' }
function pickLeagueColor(league) {
  const colors = { '英超': '#3d195b', '西甲': '#ee8707', '德甲': '#d20515', '意甲': '#008fd7', '法甲': '#91c73e', '欧冠': '#2b2d42' }
  return colors[league] || '#6b7280'
}
function fmt(v) { return v == null ? '-' : Number(v).toFixed(2) }
function isLow(odds) {
  if (!odds) return ''
  const w = Number(odds.win), d = Number(odds.draw), l = Number(odds.lose)
  const m = Math.min(w, d, l)
  if (m === w) return 'win'
  if (m === l) return 'loss'
  return 'draw'
}
function getDetail(f6, name) {
  const d = (f6?.details || []).find(x => x.name === name)
  return d ? d.desc : ''
}
function resultClass(r) {
  if (r === '主胜') return 'r-win'
  if (r === '平局') return 'r-draw'
  if (r === '客胜') return 'r-loss'
  return ''
}
function ahResultClass(ah) {
  if (ah === '上盘') return 'ah-upper'
  if (ah === '下盘') return 'ah-lower'
  if (ah === '走水') return 'ah-push'
  return ''
}
function openSimilar(it) {
  similarMatches.value = it?.f6?.matches || []
  showSimilar.value = true
}
function closeSimilar() {
  showSimilar.value = false
}

async function loadBatch() {
  loading.value = true
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
.batch-page {
  min-height: 100vh;
  background: #f0fdf9;
  display: flex;
  flex-direction: column;
}

/* 顶部汇总 */
.summary-bar {
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  padding: 28rpx 28rpx 24rpx;
  display: flex;
  flex-direction: column;
  gap: 18rpx;
  box-shadow: 0 4rpx 16rpx rgba(13,148,136,0.25);
  .sum-row { display: flex; align-items: baseline; justify-content: space-between; }
  .sum-date { font-size: 32rpx; font-weight: 700; color: #ffffff; }
  .sum-total { font-size: 24rpx; color: rgba(255,255,255,0.85); }
  .sum-chips { display: flex; gap: 14rpx; }
  .chip {
    padding: 8rpx 20rpx; border-radius: 6rpx;
    text { font-size: 22rpx; color: #ffffff; }
    &.upper { background: rgba(220,38,38,0.9); }
    &.lower { background: rgba(5,150,105,0.9); }
    &.neutral { background: rgba(255,255,255,0.25); }
  }
}

.state-hint { padding: 100rpx 0; text-align: center; text { font-size: 26rpx; color: #94a3b8; } }

/* 卡片列表 */
.card-list { flex: 1; padding: 20rpx 24rpx 60rpx; }

.match-card {
  background: #ffffff;
  border-radius: 12rpx;
  padding: 24rpx;
  margin-bottom: 20rpx;
  box-shadow: 0 2rpx 14rpx rgba(0,0,0,0.06);
  border-left: 6rpx solid #94a3b8;
  &.upper { border-left-color: #dc2626; }
  &.lower { border-left-color: #059669; }
  &.neutral { border-left-color: #94a3b8; }
}

.card-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16rpx;
  .head-left { display: flex; align-items: center; gap: 12rpx; }
  .league-tag { padding: 4rpx 14rpx; border-radius: 6rpx; text { font-size: 20rpx; color: #ffffff; } }
  .match-time { font-size: 22rpx; color: #64748b; }
  .dir-badge {
    padding: 6rpx 18rpx; border-radius: 6rpx;
    text { font-size: 22rpx; font-weight: 600; }
    &.upper { background: #fef2f2; text { color: #dc2626; } }
    &.lower { background: #ecfdf5; text { color: #059669; } }
    &.neutral { background: #f1f5f9; text { color: #64748b; } }
  }
}

.card-teams {
  display: flex; align-items: center; gap: 16rpx;
  margin-bottom: 18rpx;
  .team-name { font-size: 28rpx; font-weight: 600; color: #1e293b; flex: 1; }
  .team-vs { font-size: 20rpx; color: #cbd5e1; }
}

/* 初盘/终盘赔率 */
.odds-box {
  display: flex; align-items: center; gap: 16rpx;
  padding: 16rpx; background: #f8fafb; border-radius: 8rpx;
  margin-bottom: 16rpx;
  .odds-col { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
  .odds-label { font-size: 20rpx; color: #94a3b8; text-align: center; }
  .odds-row { display: flex; justify-content: center; gap: 18rpx; }
  .o-win, .o-draw, .o-loss { font-size: 24rpx; color: #64748b; min-width: 60rpx; text-align: center; }
  .o-win.low { color: #dc2626; font-weight: 700; }
  .o-draw.low { color: #d97706; font-weight: 700; }
  .o-loss.low { color: #059669; font-weight: 700; }
  .odds-arrow { font-size: 24rpx; color: #cbd5e1; }
  .move-tag {
    padding: 4rpx 12rpx; border-radius: 6rpx;
    text { font-size: 18rpx; }
    &.move-yes { background: #e6fffa; text { color: #0d9488; } }
    &.move-no { background: #f1f5f9; text { color: #94a3b8; } }
  }
}

.stat-row {
  margin-bottom: 8rpx;
  .stat-desc { font-size: 22rpx; color: #475569; }
}

/* 实际结果(回测) */
.actual-box {
  display: flex; align-items: center; gap: 20rpx;
  padding: 14rpx 16rpx; background: #fffbeb; border-radius: 8rpx;
  margin-bottom: 14rpx; border: 1rpx solid #fde68a;
  .actual-cell { display: flex; flex-direction: column; gap: 4rpx; }
  .ac-label { font-size: 18rpx; color: #94a3b8; }
  .ac-val { font-size: 24rpx; color: #334155; font-weight: 500; }
  .score-val { font-size: 26rpx; font-weight: 700; color: #1e293b; }
  .hit-tag {
    margin-left: auto; padding: 6rpx 16rpx; border-radius: 6rpx;
    background: #ecfdf5; text { font-size: 20rpx; color: #059669; font-weight: 600; }
    &.miss { background: #fef2f2; text { color: #dc2626; } }
  }
}

.reason-row {
  margin-bottom: 14rpx;
  text { font-size: 22rpx; color: #334155; line-height: 1.5; }
}

.detail-btn {
  margin-top: 8rpx; padding: 14rpx; text-align: center;
  border-radius: 6rpx; background: #f0fdf9; border: 1rpx solid #99f6e4;
  text { font-size: 22rpx; color: #0d9488; font-weight: 500; }
}

/* 同赔弹窗 */
.similar-mask {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5); z-index: 200;
}
.similar-modal {
  position: fixed;
  top: 6vh; left: 3vw; right: 3vw; bottom: 6vh;
  background: #fff; border-radius: 16rpx; z-index: 201;
  display: flex; flex-direction: column;
  transform: scale(0.92); opacity: 0; transition: all 0.25s; pointer-events: none;
  &.show { transform: scale(1); opacity: 1; pointer-events: auto; }
}
.similar-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 20rpx 24rpx; border-bottom: 1rpx solid #e2e8f0; flex-shrink: 0;
  .similar-title { font-size: 28rpx; font-weight: 600; color: #1e293b; }
  .similar-close { font-size: 32rpx; color: #94a3b8; padding: 8rpx; }
}
.similar-body { flex: 1; overflow: auto; }
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
