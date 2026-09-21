<template>
  <view class="predict-page">
    <view class="top-bar">
      <view class="status-toggle">
        <view class="toggle-item" :class="{ active: matchStatus === 'not_started' }" @tap="matchStatus = 'not_started'">
          <text>未开始</text>
        </view>
        <view class="toggle-item" :class="{ active: matchStatus === 'finished' }" @tap="matchStatus = 'finished'">
          <text>已结束</text>
        </view>
      </view>

      <view class="match-picker" @tap="showPicker = true">
        <text class="picker-text" v-if="selectedMatch">{{ selectedMatch.homeTeam.name }} vs {{ selectedMatch.awayTeam.name }}</text>
        <text class="picker-placeholder" v-else>选择赛事</text>
        <text class="picker-arrow">▾</text>
      </view>

      <view class="ah-entry" @tap="goAhPredict">
        <text>让球</text>
      </view>
      <view class="predict-trigger" :class="{ disabled: !selectedMatch || analyzing }" @tap="startAnalysis">
        <text>预测</text>
      </view>
    </view>

    <view class="match-info-bar" v-if="selectedMatch">
      <view class="info-row">
        <text class="info-league" :style="{ backgroundColor: pickLeagueColor(selectedMatch.league) }">{{ selectedMatch.league }}</text>
        <text class="info-time">{{ selectedMatch.matchDate.slice(5) }} {{ selectedMatch.matchTime.slice(0, 5) }}</text>
        <text class="info-handicap" v-if="ouMeta.closeLine != null">{{ ouBookLabel }} {{ formatLine(ouMeta.closeLine) }}</text>
        <text class="info-handicap muted" v-else-if="selectedMatch.ouLine != null">{{ formatLine(selectedMatch.ouLine) }}</text>
      </view>
      <text class="info-summary" v-if="ouMeta.summary">{{ ouMeta.summary }}</text>
    </view>

    <scroll-view class="analysis-flow" scroll-y>
      <view v-if="!analyzing && analysisSteps.length === 0 && !analysisComplete" class="empty-hint">
        <text class="hint-text">选择在售赛事，点击预测。标准盘 Bet365，输出大 / 小。</text>
      </view>

      <view class="timeline" v-if="analysisSteps.length > 0">
        <view
          class="timeline-item"
          v-for="(step, idx) in analysisSteps"
          :key="idx"
          :class="{ active: step.status === 'analyzing', done: step.status === 'done', pending: step.status === 'pending' }"
        >
          <view class="track">
            <view v-if="idx > 0" class="track-line top" :class="{ filled: step.status !== 'pending' }"></view>
            <view class="track-dot" :class="{ spinning: step.status === 'analyzing' }">
              <text v-if="step.status === 'done'" class="dot-check">✓</text>
              <text v-else class="dot-num">{{ idx + 1 }}</text>
            </view>
            <view v-if="idx < analysisSteps.length - 1" class="track-line bottom" :class="{ filled: step.status === 'done' }"></view>
          </view>

          <view class="step-content">
            <view class="step-header">
              <text class="step-name">{{ step.name }}</text>
              <text class="step-analyzing" v-if="step.status === 'analyzing'">分析中</text>
              <view class="step-score-inline" v-if="step.status === 'done'">
                <text class="dir-tag" :class="step.dirClass">{{ step.dirLabel }}</text>
                <text class="score-num">{{ step.score }}<text class="score-total">/10</text></text>
              </view>
            </view>
            <view class="step-bar" v-if="step.status === 'done'">
              <view class="bar-fill" :style="{ width: step.score * 10 + '%' }"></view>
            </view>
            <view class="step-reason-row" v-if="step.status === 'done'">
              <text class="step-reason">{{ step.reason }}</text>
              <view v-if="factorHelpMap[step.name]" class="factor-help-btn" @tap.stop="openFactorHelp(step.name)">
                <text class="factor-help-q">?</text>
              </view>
            </view>
            <view class="sub-factors" v-if="step.status === 'done' && step.details && step.details.length > 0">
              <view class="sub-factor-block" v-for="(sub, si) in step.details" :key="si">
                <view class="sub-factor-item">
                  <text class="sub-dir-dot" :class="sub.direction || 'neutral'">●</text>
                  <text class="sub-name">{{ sub.name }}</text>
                  <text class="sub-desc" v-if="sub.desc">{{ sub.desc }}</text>
                </view>
                <FactorCompareBars v-if="hasChart(sub)" :chart="sub.chart" />
              </view>
            </view>
          </view>
        </view>
      </view>

      <view class="analysis-result" v-if="analysisComplete">
        <view class="result-divider">
          <view class="divider-line"></view>
          <text class="divider-text">分析结果</text>
          <view class="divider-line"></view>
        </view>

        <view class="result-card" :class="prediction.direction">
          <view class="result-left">
            <text class="dir-arrow">{{ prediction.direction === 'upper' ? '↑' : prediction.direction === 'lower' ? '↓' : '−' }}</text>
            <view class="dir-info">
              <text class="dir-text">{{ directionLabel(prediction.direction) }}</text>
              <text class="dir-sub">综合{{ analysisSteps.length }}项因子</text>
            </view>
          </view>
          <view class="result-right">
            <text class="conf-num">{{ prediction.confidence }}<text class="conf-unit">%</text></text>
            <text class="conf-label">置信度</text>
          </view>
        </view>

        <view class="actual-result" v-if="selectedMatch?.matchStatus === 'finished' && hasScore && ouMeta.closeLine != null">
          <view class="actual-header">
            <text class="actual-title">实际结果</text>
          </view>
          <view class="actual-body">
            <view class="actual-score">
              <text class="actual-home">{{ selectedMatch.homeTeam.name }}</text>
              <text class="actual-num">{{ selectedMatch.homeScore }} - {{ selectedMatch.awayScore }}</text>
              <text class="actual-away">{{ selectedMatch.awayTeam.name }}</text>
            </view>
            <view class="actual-compare">
              <view class="compare-row">
                <text class="compare-label">大小盘</text>
                <text class="compare-value">{{ ouBookLabel }} {{ formatLine(ouMeta.closeLine) }}</text>
              </view>
              <view class="compare-row">
                <text class="compare-label">总进球</text>
                <text class="compare-value">{{ totalGoals }}</text>
              </view>
              <view class="compare-row">
                <text class="compare-label">实际方向</text>
                <text class="compare-value" :class="actualDirection">{{ actualDirectionText }}</text>
              </view>
            </view>
          </view>
        </view>

        <view class="analysis-text" v-if="aiAnalysis">
          <text class="analysis-body">{{ aiAnalysis }}</text>
        </view>
      </view>
    </scroll-view>

    <view class="picker-mask" v-if="showPicker" @tap.self="showPicker = false">
      <view class="picker-sheet">
        <view class="sheet-handle"></view>
        <view class="sheet-header">
          <text class="sheet-title">选择赛事</text>
          <view class="sheet-close" @tap="showPicker = false"><text>✕</text></view>
        </view>
        <view class="sheet-filters">
          <view class="filter-row">
            <input class="search-input" v-model="searchKey" placeholder="搜索队伍" placeholder-style="color:#b0b7c0" />
          </view>
          <scroll-view class="filter-tabs" scroll-x>
            <view
              v-if="matchStatus === 'not_started'"
              class="league-tab"
              :class="{ active: filterDate === 'all' }"
              @tap="filterDate = 'all'"
            >
              <text>全部</text>
            </view>
            <view
              class="league-tab"
              v-for="d in saleDates"
              :key="d"
              :class="{ active: filterDate === d }"
              @tap="filterDate = d"
            >
              <text>{{ d.slice(5) }}</text>
            </view>
          </scroll-view>
        </view>
        <scroll-view class="match-list" scroll-y>
          <view
            class="match-row"
            v-for="match in filteredPickerMatches"
            :key="match.matchId"
            :class="{ selected: selectedMatch?.matchId === match.matchId }"
            @tap="selectMatch(match)"
          >
            <view class="row-meta">
              <text class="row-league" :style="{ backgroundColor: pickLeagueColor(match.league) }">{{ match.league }}</text>
              <text class="row-time">{{ match.matchTime.slice(0, 5) }}</text>
            </view>
            <text class="row-teams">{{ match.homeTeam.name }} vs {{ match.awayTeam.name }}</text>
          </view>
          <view v-if="filteredPickerMatches.length === 0" class="list-empty">
            <text>{{ emptyPickerHint }}</text>
          </view>
        </scroll-view>
      </view>
    </view>

    <view class="similar-mask" v-if="showFactorHelp" @tap="closeFactorHelp"></view>
    <view class="factor-help-modal" :class="{ show: showFactorHelp }" @tap.stop>
      <view class="fh-head">
        <view class="fh-badge"><text class="fh-badge-q">?</text></view>
        <text class="fh-title">{{ factorHelpTitle }}</text>
        <text class="fh-close" @tap="closeFactorHelp">关闭</text>
      </view>
      <scroll-view class="factor-help-body" scroll-y>
        <view class="fh-block" v-for="(b, bi) in factorHelpBlocks" :key="bi">
          <text class="fh-idx">{{ bi + 1 }}</text>
          <view class="fh-main">
            <text class="fh-h">{{ b.title }}</text>
            <text class="fh-p" v-for="(p, pi) in b.paras" :key="pi">{{ p }}</text>
          </view>
        </view>
      </scroll-view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { request } from '@/utils/http'
import FactorCompareBars from '@/components/FactorCompareBars.vue'

const factorNames = ['市场信号', '市场热度', '盘口结构', '进球对比', '竞彩总进球']

const matchStatus = ref('not_started')
const selectedMatch = ref(null)
const showPicker = ref(false)
const analyzing = ref(false)
const analysisComplete = ref(false)
const analysisSteps = ref([])
const prediction = ref({ direction: '', confidence: 0 })
const aiAnalysis = ref('')
const ouMeta = ref({})
const allMatches = ref([])
const saleDates = ref([])
const filterDate = ref('all')
const searchKey = ref('')
const pendingMatchId = ref('')
const _initialParams = ref(false)
const showFactorHelp = ref(false)
const factorHelpTitle = ref('')
const factorHelpBlocks = ref([])

const factorHelpMap = {
  市场信号: {
    title: '市场信号说明',
    blocks: [
      { title: '标准盘', paras: ['升降盘、诱盘都钉死 Bet365 即时盘。缺 365 才退 Pinnacle / 皇冠。'] },
      { title: '诱盘要反着读', paras: ['升盘+大球升水=诱大→偏小。降盘+大球降水=诱小→偏大。真升盘偏大，真降盘偏小。'] },
    ],
  },
  市场热度: {
    title: '市场热度说明',
    blocks: [
      { title: '只收没动盘的水位', paras: ['调盘、诱盘归市场信号。热度只看贴着 Bet365 的同盘/近盘降水升水。'] },
      { title: '预测时再翻一次', paras: ['卡片写「大热」加权时翻成偏小，避免和诱盘双重计权。'] },
    ],
  },
  盘口结构: {
    title: '盘口结构说明',
    blocks: [
      { title: '365 vs 中位', paras: ['去掉 Bet365 后算主流中位数。365 开深≥0.5 偏小，开浅偏大。'] },
      { title: '离散', paras: ['立博乱开会把 max-min 拉大。离散≥1.0 本因子中性，整场置信下调。'] },
    ],
  },
  进球对比: {
    title: '进球对比说明',
    blocks: [
      { title: '不是历史大小球', paras: ['用两队近 20 场比分，按本场 Bet365 盘反结算大/小。四分之一球拆半。'] },
    ],
  },
  竞彩总进球: {
    title: '竞彩总进球说明',
    blocks: [
      { title: '有才用', paras: ['看最低赔段中位 vs 365 线。差太大只降置信，不硬给方向。'] },
    ],
  },
}

function hasChart(sub) {
  return !!(sub && sub.chart && sub.chart.items && sub.chart.items.length)
}

function directionLabel(dir) {
  if (dir === 'upper') return '大'
  if (dir === 'lower') return '小'
  return '中性'
}

function heatLabel(dir) {
  if (dir === 'upper') return '大热'
  if (dir === 'lower') return '小热'
  return '中性'
}

function formatLine(v) {
  if (v === undefined || v === null || v === '') return ''
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return String(n)
}

function pickLeagueColor(league) {
  const colors = { '英超': '#3d195b', '西甲': '#ee8707', '德甲': '#d20515', '意甲': '#008fd7', '法甲': '#91c73e', '欧冠': '#2b2d42' }
  return colors[league] || '#6b7280'
}

const ouBookLabel = computed(() => ouMeta.value.book || 'Bet365')

const filteredPickerMatches = computed(() => {
  const q = (searchKey.value || '').trim()
  return allMatches.value.filter((m) => {
    if (!q) return true
    const blob = `${m.homeTeam?.name || ''}${m.awayTeam?.name || ''}${m.league || ''}`
    return blob.includes(q)
  })
})

const emptyPickerHint = computed(() => {
  if (matchStatus.value === 'finished' && (!filterDate.value || filterDate.value === 'all')) {
    return '请选择售卖日期'
  }
  return '没有比赛'
})

const hasScore = computed(() => {
  const m = selectedMatch.value
  return m && m.homeScore != null && m.awayScore != null
})

const totalGoals = computed(() => {
  if (!hasScore.value) return null
  return Number(selectedMatch.value.homeScore) + Number(selectedMatch.value.awayScore)
})

const actualDirection = computed(() => {
  if (totalGoals.value == null || ouMeta.value.closeLine == null) return ''
  const total = totalGoals.value
  const line = Number(ouMeta.value.closeLine)
  const n = Math.round(line * 4)
  const r = n % 4
  if (r === 1 || r === 3) {
    const a = n / 4 - 0.25
    const b = n / 4 + 0.25
    const sa = total === a ? 'push' : (total > a ? 'over' : 'under')
    const sb = total === b ? 'push' : (total > b ? 'over' : 'under')
    if (sa === 'over' && sb === 'over') return 'upper'
    if (sa === 'under' && sb === 'under') return 'lower'
    if ((sa === 'over' && sb === 'push') || (sa === 'push' && sb === 'over')) return 'upper'
    if ((sa === 'under' && sb === 'push') || (sa === 'push' && sb === 'under')) return 'lower'
    return 'neutral'
  }
  if (Math.abs(total - line) < 1e-9) return 'neutral'
  return total > line ? 'upper' : 'lower'
})

const actualDirectionText = computed(() => {
  if (actualDirection.value === 'upper') return '大'
  if (actualDirection.value === 'lower') return '小'
  if (actualDirection.value === 'neutral') return '走'
  return '待定'
})

function openFactorHelp(name) {
  const item = factorHelpMap[name]
  if (!item) return
  factorHelpTitle.value = item.title
  factorHelpBlocks.value = item.blocks
  showFactorHelp.value = true
}
function closeFactorHelp() {
  showFactorHelp.value = false
}

function goAhPredict() {
  const qs = [`status=${matchStatus.value}`]
  if (selectedMatch.value?.matchId) qs.push(`matchId=${encodeURIComponent(selectedMatch.value.matchId)}`)
  if (filterDate.value && filterDate.value !== 'all') qs.push(`date=${filterDate.value}`)
  uni.navigateTo({ url: `/pages/predict/predict?${qs.join('&')}` })
}

function selectMatch(match) {
  selectedMatch.value = match
  showPicker.value = false
  analysisSteps.value = []
  analysisComplete.value = false
  ouMeta.value = {}
}

onLoad((query) => {
  analysisSteps.value = []
  analysisComplete.value = false
  prediction.value = { direction: '', confidence: 0 }
  selectedMatch.value = null
  if (query?.matchId) pendingMatchId.value = query.matchId
  if (query?.status === 'finished' || query?.status === 'not_started') {
    matchStatus.value = query.status
    _initialParams.value = true
  }
  if (query?.date && /^\d{4}-\d{2}-\d{2}$/.test(query.date)) {
    filterDate.value = query.date
  }
})

async function fetchDates() {
  try {
    const statusParam = matchStatus.value === 'finished' ? 'finished' : 'not_started'
    const data = await request({ url: '/api/predict/dates', data: { status: statusParam } })
    saleDates.value = data?.dates || []
    if (matchStatus.value === 'finished') {
      if (saleDates.value.length > 0 && (filterDate.value === 'all' || !filterDate.value)) {
        filterDate.value = saleDates.value[0]
      }
    } else if (filterDate.value && filterDate.value !== 'all' && !saleDates.value.includes(filterDate.value)) {
      filterDate.value = 'all'
    }
  } catch (e) {
    saleDates.value = []
  }
}

async function fetchMatches() {
  try {
    const statusParam = matchStatus.value === 'finished' ? 'finished' : 'not_started'
    const params = { status: statusParam, page_size: 100 }
    if (filterDate.value && filterDate.value !== 'all') {
      params.date = filterDate.value
    } else if (statusParam === 'finished') {
      allMatches.value = []
      return
    }
    const data = await request({ url: '/api/predict/matches', data: params })
    allMatches.value = (data?.items || []).map((item) => ({
      matchId: item.matchId,
      matchNumber: item.matchNumber,
      matchDate: item.matchDate,
      matchTime: item.matchTime || '00:00:00',
      matchStatus: item.matchStatus || (statusParam === 'finished' ? 'finished' : 'not_started'),
      league: item.league,
      homeTeam: item.homeTeam,
      awayTeam: item.awayTeam,
      homeScore: item.homeScore,
      awayScore: item.awayScore,
    }))
    if (pendingMatchId.value) {
      const found = allMatches.value.find((m) => m.matchId === pendingMatchId.value)
      if (found) {
        selectedMatch.value = found
        pendingMatchId.value = ''
      }
    }
  } catch (e) {
    allMatches.value = []
  }
}

async function startAnalysis() {
  if (!selectedMatch.value || analyzing.value) return
  analyzing.value = true
  analysisComplete.value = false
  prediction.value = { direction: '', confidence: 0 }
  aiAnalysis.value = ''
  ouMeta.value = {}
  analysisSteps.value = factorNames.map((name) => ({
    name,
    score: 0,
    direction: 'neutral',
    reason: '',
    dirLabel: '中性',
    dirClass: 'neutral',
    details: [],
    status: 'pending',
  }))
  let currentStep = 0
  const animateInterval = setInterval(() => {
    if (currentStep < analysisSteps.value.length) {
      analysisSteps.value[currentStep].status = 'analyzing'
      currentStep++
    }
  }, 500)
  try {
    const data = await request({
      url: `/api/predict/ou/${selectedMatch.value.matchId}`,
      method: 'POST',
      data: {},
      timeout: 30000,
    })
    clearInterval(animateInterval)
    const factors = data.factors || []
    for (let i = 0; i < analysisSteps.value.length; i++) {
      const factor = factors[i] || {}
      analysisSteps.value[i].score = factor.score || 5
      analysisSteps.value[i].direction = factor.direction || 'neutral'
      analysisSteps.value[i].reason = factor.reason || ''
      const hot = factor.name === '市场热度'
      analysisSteps.value[i].dirLabel = hot
        ? heatLabel(factor.direction)
        : directionLabel(factor.direction)
      analysisSteps.value[i].dirClass = factor.direction || 'neutral'
      analysisSteps.value[i].details = factor.details || []
      analysisSteps.value[i].status = 'done'
    }
    if (data.match) {
      if (data.match.homeScore != null) selectedMatch.value.homeScore = data.match.homeScore
      if (data.match.awayScore != null) selectedMatch.value.awayScore = data.match.awayScore
      if (data.match.ouLine != null) selectedMatch.value.ouLine = data.match.ouLine
    }
    const pred = data.prediction || {}
    prediction.value = {
      direction: pred.direction || 'neutral',
      confidence: pred.confidence || 35,
    }
    aiAnalysis.value = pred.analysis || ''
    ouMeta.value = data.ou || {}
    analysisComplete.value = true
  } catch (e) {
    clearInterval(animateInterval)
    analysisSteps.value = []
    uni.showToast({ title: e.message || '预测失败', icon: 'none' })
  } finally {
    analyzing.value = false
  }
}

watch(matchStatus, async () => {
  selectedMatch.value = null
  analysisSteps.value = []
  analysisComplete.value = false
  ouMeta.value = {}
  searchKey.value = ''
  if (matchStatus.value === 'finished') {
    if (!_initialParams.value) filterDate.value = ''
    _initialParams.value = false
  } else {
    if (!_initialParams.value) filterDate.value = 'all'
    _initialParams.value = false
  }
  await fetchDates()
  await fetchMatches()
})

watch(filterDate, (val) => {
  if (!val) return
  if (matchStatus.value === 'finished' && val === 'all') return
  fetchMatches()
})

onShow(async () => {
  await fetchDates()
  await fetchMatches()
})
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.predict-page {
  min-height: 100vh;
  background: #f7faf9;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  &, view, text, scroll-view { box-sizing: border-box; max-width: 100%; }
}

.top-bar {
  display: flex;
  align-items: center;
  padding: 16rpx 24rpx;
  gap: 12rpx;
  background: #fff;
  box-shadow: 0 1px 0 rgba(0,0,0,0.04);
}

.status-toggle {
  display: flex;
  border: 1px solid #e2e8f0;
  border-radius: 6rpx;
  overflow: hidden;
  flex-shrink: 0;
  .toggle-item {
    padding: 10rpx 16rpx;
    font-size: 22rpx;
    color: #64748b;
    background: #fff;
    &.active { background: $frbt-primary; color: #fff; font-weight: 600; }
  }
}

.match-picker {
  flex: 1;
  display: flex;
  align-items: center;
  height: 56rpx;
  background: #f8fafb;
  border: 1px solid #e2e8f0;
  border-radius: 6rpx;
  padding: 0 16rpx;
  min-width: 0;
  .picker-text { font-size: 24rpx; color: #1e293b; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .picker-placeholder { font-size: 24rpx; color: #94a3b8; flex: 1; }
  .picker-arrow { font-size: 22rpx; color: #94a3b8; margin-left: 4rpx; }
}

.ah-entry, .predict-trigger {
  flex-shrink: 0;
  height: 56rpx;
  padding: 0 20rpx;
  border-radius: 6rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  text { font-size: 24rpx; font-weight: 600; }
}
.ah-entry {
  border: 1px solid #0d9488;
  background: #fff;
  text { color: #0d9488; }
}
.predict-trigger {
  background: $frbt-primary;
  text { color: #fff; }
  &.disabled { opacity: 0.4; }
}

.match-info-bar {
  display: flex;
  flex-direction: column;
  padding: 14rpx 24rpx;
  gap: 8rpx;
  background: #f0fdf9;
  border-bottom: 1px solid #e2f5f0;
  .info-row { display: flex; align-items: center; gap: 12rpx; }
  .info-league { font-size: 20rpx; color: #fff; padding: 0 12rpx; border-radius: 4rpx; }
  .info-time { font-size: 22rpx; color: #64748b; }
  .info-handicap { font-size: 22rpx; font-weight: 700; color: #0f766e; &.muted { font-weight: 500; } }
  .info-summary { font-size: 20rpx; color: #64748b; line-height: 1.4; }
}

.analysis-flow { flex: 1; height: 0; padding: 16rpx 24rpx 40rpx; }
.empty-hint { padding: 80rpx 24rpx; text-align: center; .hint-text { font-size: 26rpx; color: #94a3b8; } }

.timeline { display: flex; flex-direction: column; }
.timeline-item {
  display: flex; gap: 16rpx;
  .track {
    width: 36rpx; display: flex; flex-direction: column; align-items: center; flex-shrink: 0;
    .track-line { width: 2rpx; flex: 1; min-height: 12rpx; background: #e2e8f0; &.filled { background: #99f6e4; } }
    .track-dot {
      width: 36rpx; height: 36rpx; border-radius: 50%;
      background: #e2e8f0; display: flex; align-items: center; justify-content: center;
      .dot-num { font-size: 20rpx; color: #64748b; }
      .dot-check { font-size: 20rpx; color: #fff; }
    }
  }
  &.done .track-dot { background: #0d9488; }
  &.active .track-dot { background: #14b8a6; }
  &.pending { opacity: 0.5; }
}

.step-content { flex: 1; padding-bottom: 24rpx; min-width: 0; }
.step-header { display: flex; align-items: center; gap: 8rpx; }
.step-name { font-size: 26rpx; font-weight: 700; color: #1e293b; }
.step-analyzing { font-size: 20rpx; color: #0d9488; }
.step-score-inline {
  display: flex; align-items: center; gap: 8rpx; margin-left: auto;
  .dir-tag {
    font-size: 20rpx; font-weight: 600; padding: 2rpx 10rpx; border-radius: 6rpx;
    &.upper { color: #dc2626; background: #fef2f2; }
    &.lower { color: #059669; background: #ecfdf5; }
    &.neutral { color: #64748b; background: #f1f5f9; }
  }
  .score-num { font-size: 22rpx; font-weight: 600; color: #1e293b; .score-total { font-weight: 400; color: #94a3b8; } }
}
.step-bar { height: 4rpx; background: #e2e8f0; border-radius: 2rpx; margin: 8rpx 0; overflow: hidden;
  .bar-fill { height: 100%; background: $frbt-primary; }
}
.step-reason-row { display: flex; align-items: flex-start; gap: 8rpx; }
.step-reason { flex: 1; font-size: 22rpx; color: #64748b; line-height: 1.5; }
.factor-help-btn {
  width: 32rpx; height: 32rpx; border-radius: 6rpx; border: 1px solid #cbd5e1;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  .factor-help-q { font-size: 20rpx; color: #64748b; }
}
.sub-factors { margin-top: 8rpx; }
.sub-factor-item { display: flex; align-items: center; gap: 8rpx; margin-top: 6rpx; }
.sub-dir-dot { font-size: 16rpx; &.upper { color: #dc2626; } &.lower { color: #059669; } &.neutral { color: #94a3b8; } }
.sub-name { font-size: 22rpx; color: #334155; font-weight: 600; }
.sub-desc { font-size: 20rpx; color: #64748b; flex: 1; }

.result-divider { display: flex; align-items: center; gap: 12rpx; margin: 12rpx 0 20rpx;
  .divider-line { flex: 1; height: 1px; background: #e2e8f0; }
  .divider-text { font-size: 22rpx; color: #94a3b8; }
}
.result-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 28rpx 24rpx; border-radius: 12rpx; margin-bottom: 20rpx;
  &.upper { background: linear-gradient(135deg, #fff5f5 0%, #fee2e2 100%); border: 1px solid #fecaca; }
  &.lower { background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); border: 1px solid #a7f3d0; }
  &.neutral { background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); border: 1px solid #e2e8f0; }
  .result-left { display: flex; align-items: center; gap: 16rpx;
    .dir-arrow { font-size: 40rpx; font-weight: 700; }
    .dir-text { font-size: 32rpx; font-weight: 700; color: #1e293b; }
    .dir-sub { font-size: 20rpx; color: #64748b; }
  }
  .result-right { text-align: right;
    .conf-num { font-size: 44rpx; font-weight: 800; color: #0f766e; .conf-unit { font-size: 24rpx; } }
    .conf-label { font-size: 20rpx; color: #64748b; display: block; }
  }
}
.actual-result { background: #fff; border: 1px solid #e2e8f0; border-radius: 12rpx; padding: 20rpx; margin-bottom: 16rpx; }
.actual-title { font-size: 22rpx; color: #64748b; }
.actual-score { display: flex; align-items: center; justify-content: space-between; margin: 12rpx 0; gap: 12rpx;
  .actual-home, .actual-away { font-size: 24rpx; color: #1e293b; flex: 1; }
  .actual-away { text-align: right; }
  .actual-num { font-size: 32rpx; font-weight: 700; }
}
.compare-row { display: flex; justify-content: space-between; padding: 6rpx 0;
  .compare-label { font-size: 22rpx; color: #64748b; }
  .compare-value { font-size: 22rpx; font-weight: 600;
    &.upper { color: #dc2626; } &.lower { color: #059669; }
  }
}
.analysis-text { background: #fff; border-radius: 12rpx; padding: 20rpx;
  .analysis-body { font-size: 24rpx; color: #334155; line-height: 1.6; }
}

.picker-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.4); z-index: 1000;
  display: flex; align-items: flex-end;
}
.picker-sheet {
  width: 100%; max-height: 72vh; background: #fff;
  border-radius: 20rpx 20rpx 0 0; display: flex; flex-direction: column;
  padding-bottom: env(safe-area-inset-bottom);
}
.sheet-handle { width: 64rpx; height: 6rpx; background: #e2e8f0; border-radius: 3rpx; margin: 16rpx auto 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 20rpx 28rpx 12rpx;
  .sheet-title { font-size: 30rpx; font-weight: 700; color: #1e293b; }
  .sheet-close { width: 48rpx; height: 48rpx; display: flex; align-items: center; justify-content: center;
    text { font-size: 28rpx; color: #94a3b8; }
  }
}
.sheet-filters { padding: 0 28rpx 12rpx;
  .filter-row { margin-bottom: 12rpx; }
  .search-input {
    width: 100%; height: 64rpx; background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 6rpx; padding: 0 20rpx; font-size: 26rpx; color: #1e293b;
  }
}
.filter-tabs { white-space: nowrap; padding-bottom: 12rpx;
  .league-tab {
    display: inline-flex; padding: 8rpx 20rpx; margin-right: 12rpx;
    border-radius: 6rpx; background: #f1f5f9;
    text { font-size: 22rpx; color: #64748b; }
    &.active { background: $frbt-primary; text { color: #fff; font-weight: 600; } }
  }
}
.match-list { flex: 1; max-height: 48vh; padding: 0 12rpx 16rpx; }
.match-row {
  display: flex; align-items: center; gap: 12rpx; padding: 16rpx 12rpx; border-radius: 6rpx;
  &.selected { background: #f0fdfa; }
  .row-meta { display: flex; flex-direction: column; gap: 4rpx; width: 120rpx; flex-shrink: 0; }
  .row-league { font-size: 18rpx; color: #fff; padding: 0 8rpx; border-radius: 4rpx; align-self: flex-start; }
  .row-time { font-size: 20rpx; color: #94a3b8; }
  .row-teams { flex: 1; font-size: 26rpx; color: #1e293b; }
}
.list-empty { padding: 40rpx; text-align: center; text { font-size: 24rpx; color: #94a3b8; } }

.similar-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 200; }
.factor-help-modal {
  position: fixed; left: 24rpx; right: 24rpx; top: 20%; max-height: 60vh;
  background: #fff; border-radius: 12rpx; z-index: 201; display: none; flex-direction: column;
  &.show { display: flex; }
}
.fh-head { display: flex; align-items: center; gap: 12rpx; padding: 20rpx 24rpx; border-bottom: 1px solid #e2e8f0;
  .fh-badge { width: 40rpx; height: 40rpx; border-radius: 6rpx; background: #f1f5f9; display: flex; align-items: center; justify-content: center; }
  .fh-title { flex: 1; font-size: 28rpx; font-weight: 700; }
  .fh-close { font-size: 24rpx; color: #0d9488; }
}
.factor-help-body { padding: 16rpx 24rpx 28rpx; }
.fh-block { display: flex; gap: 12rpx; margin-bottom: 16rpx;
  .fh-idx { width: 36rpx; height: 36rpx; border-radius: 6rpx; background: #f0fdfa; color: #0d9488; font-size: 22rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; }
  .fh-h { font-size: 24rpx; font-weight: 700; color: #1e293b; display: block; }
  .fh-p { font-size: 22rpx; color: #64748b; line-height: 1.5; display: block; margin-top: 4rpx; }
}
</style>
