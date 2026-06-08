<template>
  <view class="predict-page">
    <!-- 顶部操作区 -->
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

      <view class="predict-trigger" :class="{ disabled: !selectedMatch || analyzing }" @tap="startAnalysis">
        <text>预测</text>
      </view>
    </view>

    <!-- 已选赛事信息 -->
    <view class="match-info-bar" v-if="selectedMatch">
      <text class="info-league" :style="{ backgroundColor: pickLeagueColor(selectedMatch.league) }">{{ selectedMatch.league }}</text>
      <text class="info-time">{{ selectedMatch.matchDate.slice(5) }} {{ selectedMatch.matchTime.slice(0, 5) }}</text>
      <text class="info-handicap" v-if="selectedMatch.handicap != null">{{ formatHandicap(selectedMatch.handicap) }}</text>
      <view class="info-single" v-if="selectedMatch.isSingle"><text>单关</text></view>
    </view>

    <!-- 分析流程区域 -->
    <scroll-view class="analysis-flow" scroll-y>
      <!-- 空状态 -->
      <view v-if="!analyzing && analysisSteps.length === 0 && !analysisComplete" class="empty-hint">
        <text class="hint-text">选择赛事，点击预测开始分析</text>
      </view>

      <!-- 因子分析步骤 - 左侧时间线 -->
      <view class="timeline" v-if="analysisSteps.length > 0">
        <view
          class="timeline-item"
          v-for="(step, idx) in analysisSteps"
          :key="idx"
          :class="{ active: step.status === 'analyzing', done: step.status === 'done', pending: step.status === 'pending' }"
        >
          <!-- 左侧轨道 -->
          <view class="track">
            <view v-if="idx > 0" class="track-line top" :class="{ filled: step.status !== 'pending' }"></view>
            <view class="track-dot" :class="{ spinning: step.status === 'analyzing' }">
              <text v-if="step.status === 'done'" class="dot-check">✓</text>
              <text v-else class="dot-num">{{ idx + 1 }}</text>
            </view>
            <view v-if="idx < analysisSteps.length - 1" class="track-line bottom" :class="{ filled: step.status === 'done' }"></view>
          </view>

          <!-- 右侧内容 -->
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
            <text class="step-reason" v-if="step.status === 'done'">{{ step.reason }}</text>
            <!-- F1子因素详情 -->
            <view class="sub-factors" v-if="step.status === 'done' && step.details && step.details.length > 0">
              <view class="sub-factor-item" v-for="(sub, si) in step.details" :key="si">
                <text class="sub-dir-dot" :class="sub.direction">●</text>
                <text class="sub-name">{{ sub.name }}</text>
                <text class="sub-desc">{{ sub.desc }}</text>
              </view>
            </view>
          </view>
        </view>
      </view>

      <!-- 分析结果 -->
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

        <!-- 已结束比赛：实际结果对比 (有比分才展示) -->
        <view class="actual-result" v-if="selectedMatch?.matchStatus === 'finished' && hasScore">
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
                <text class="compare-label">让球盘口</text>
                <text class="compare-value">{{ formatHandicap(selectedMatch.handicap) }}</text>
              </view>
              <view class="compare-row">
                <text class="compare-label">实际方向</text>
                <text class="compare-value" :class="actualDirection">{{ actualDirectionText }}</text>
              </view>
              <view class="compare-row">
                <text class="compare-label">预测方向</text>
                <text class="compare-value" :class="prediction.direction">{{ directionLabel(prediction.direction) }}</text>
              </view>
              <view class="compare-row verdict">
                <text class="compare-label">预测结果</text>
                <text class="verdict-tag" :class="predictionHit ? 'hit' : 'miss'">{{ predictionHit ? '命中 ✓' : '未中 ✗' }}</text>
              </view>
            </view>
          </view>
        </view>
        <!-- 已结束但暂无比分 -->
        <view class="actual-result" v-else-if="selectedMatch?.matchStatus === 'finished'">
          <view class="actual-header">
            <text class="actual-title">实际结果</text>
          </view>
          <view class="actual-body">
            <text class="no-score-tip">暂无比分数据</text>
          </view>
        </view>

        <view class="ai-analysis">
          <view class="ai-header">
            <text class="ai-icon">✦</text>
            <text class="ai-title">AI 综合分析</text>
          </view>
          <text class="ai-text">{{ aiAnalysis }}</text>
        </view>
      </view>
    </scroll-view>

    <!-- 赛事选择弹窗 -->
    <view class="picker-mask" v-if="showPicker" @tap.self="showPicker = false">
      <view class="picker-sheet">
        <view class="sheet-handle"></view>
        <view class="sheet-header">
          <text class="sheet-title">选择赛事</text>
          <view class="sheet-close" @tap="showPicker = false"><text>✕</text></view>
        </view>

        <view class="sheet-filters">
          <view class="filter-row">
            <view class="date-picker-wrap" @tap="openDatePicker">
              <view class="date-picker-btn">
                <text class="date-picker-text">{{ filterDateLabel }}</text>
                <text class="date-picker-icon">▼</text>
              </view>
            </view>
            <input class="search-input" v-model="searchKey" placeholder="搜索队伍" placeholder-style="color:#b0b7c0" />
          </view>

          <scroll-view class="league-tabs" scroll-x>
            <view
              class="league-tab"
              :class="{ active: filterLeague === 'all' }"
              @tap="filterLeague = 'all'"
            >
              <text>全部</text>
            </view>
            <view
              class="league-tab"
              v-for="lg in availableLeagues"
              :key="lg"
              :class="{ active: filterLeague === lg }"
              @tap="filterLeague = lg"
            >
              <text>{{ lg }}</text>
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
            <text class="row-handicap" v-if="match.handicap">{{ formatHandicap(match.handicap) }}</text>
          </view>
          <view v-if="filteredPickerMatches.length === 0" class="list-empty">
            <text>暂无赛事</text>
          </view>
        </scroll-view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { request } from '@/utils/http'

const matchStatus = ref('not_started')
const selectedMatch = ref(null)
const showPicker = ref(false)
const searchKey = ref('')
const filterDate = ref('all')
const filterLeague = ref('all')
const analyzing = ref(false)
const analysisComplete = ref(false)
const analysisSteps = ref([])
const prediction = ref({ direction: '', confidence: 0 })
const aiAnalysis = ref('')

const allMatches = ref([])
const loadingMatches = ref(false)
const finishedDates = ref([])

async function fetchDates() {
  if (matchStatus.value !== 'finished') return
  try {
    const data = await request({ url: '/api/predict/dates', data: { status: 'finished' } })
    finishedDates.value = data?.dates || []
    if (finishedDates.value.length > 0 && (filterDate.value === 'all' || !filterDate.value)) {
      filterDate.value = finishedDates.value[0]
    }
  } catch (e) {
    finishedDates.value = []
  }
}

async function fetchMatches() {
  loadingMatches.value = true
  try {
    const statusParam = matchStatus.value === 'finished' ? 'finished' : 'not_started'
    const params = { status: statusParam, page_size: 50 }
    if (filterDate.value && filterDate.value !== 'all') {
      params.date = filterDate.value
    }
    const data = await request({ url: '/api/predict/matches', data: params })
    allMatches.value = (data?.items || []).map(item => ({
      matchId: item.matchId,
      matchDate: item.matchDate,
      matchTime: item.matchTime || '00:00:00',
      matchStatus: item.matchStatus || (statusParam === 'finished' ? 'finished' : 'not_started'),
      league: item.league,
      homeTeam: item.homeTeam,
      awayTeam: item.awayTeam,
      homeScore: item.homeScore,
      awayScore: item.awayScore,
      handicap: item.handicap,
      isSingle: item.isSingle,
    }))
  } catch (e) {
    console.error('获取赛事列表失败:', e)
    allMatches.value = []
  } finally {
    loadingMatches.value = false
  }
}

const pickerMatches = computed(() => allMatches.value)

const filterDateLabel = computed(() => {
  if (!filterDate.value || filterDate.value === 'all') return '选择日期'
  return filterDate.value.slice(5)
})

const pickerDateValue = computed(() => {
  if (filterDate.value && filterDate.value !== 'all') return filterDate.value
  return new Date().toISOString().slice(0, 10)
})

const dateRange = computed(() => {
  if (matchStatus.value === 'finished') {
    const end = finishedDates.value[0] || new Date().toISOString().slice(0, 10)
    const start = finishedDates.value[finishedDates.value.length - 1] || '2026-01-01'
    return { start, end }
  }
  const today = new Date().toISOString().slice(0, 10)
  return { start: today, end: '2026-12-31' }
})

function openDatePicker() {
  // #ifdef H5
  const input = document.createElement('input')
  input.type = 'date'
  input.value = pickerDateValue.value
  if (dateRange.value.start) input.min = dateRange.value.start
  if (dateRange.value.end) input.max = dateRange.value.end
  input.style.cssText = 'position:fixed;top:40%;left:50%;transform:translate(-50%,-50%);z-index:99999;opacity:0;pointer-events:none;'
  document.body.appendChild(input)
  input.showPicker ? input.showPicker() : input.click()
  input.addEventListener('change', () => {
    if (input.value) filterDate.value = input.value
    document.body.removeChild(input)
  })
  input.addEventListener('blur', () => {
    setTimeout(() => { if (document.body.contains(input)) document.body.removeChild(input) }, 200)
  })
  // #endif
  // #ifndef H5
  uni.showActionSheet({
    itemList: finishedDates.value.slice(0, 20).map(d => d.slice(5)),
    success: (res) => {
      filterDate.value = finishedDates.value[res.tapIndex]
    }
  })
  // #endif
}

const availableLeagues = computed(() => {
  const leagues = [...new Set(pickerMatches.value.map(m => m.league))].sort()
  return leagues
})

const filteredPickerMatches = computed(() => {
  let list = pickerMatches.value
  if (filterDate.value && filterDate.value !== 'all') {
    list = list.filter(m => m.matchDate === filterDate.value)
  }
  if (filterLeague.value && filterLeague.value !== 'all') {
    list = list.filter(m => m.league === filterLeague.value)
  }
  if (searchKey.value) {
    const key = searchKey.value.toLowerCase()
    list = list.filter(m =>
      m.homeTeam.name.toLowerCase().includes(key) ||
      m.awayTeam.name.toLowerCase().includes(key)
    )
  }
  return list
})

const hasScore = computed(() => {
  const m = selectedMatch.value
  return !!m && m.homeScore != null && m.awayScore != null
})

const actualDirection = computed(() => {
  if (!selectedMatch.value || selectedMatch.value.matchStatus !== 'finished') return ''
  const m = selectedMatch.value
  if (m.homeScore == null || m.awayScore == null) return ''
  const goalDiff = m.homeScore - m.awayScore
  const handicap = Number(m.handicap || 0)
  const adjusted = goalDiff + handicap
  if (adjusted === 0) return 'draw'
  // handicap <= 0: 主队让球，主队是上盘
  // handicap > 0: 客队让球，客队是上盘
  if (handicap <= 0) {
    return adjusted > 0 ? 'upper' : 'lower'
  } else {
    return adjusted > 0 ? 'lower' : 'upper'
  }
})

const actualDirectionText = computed(() => {
  if (actualDirection.value === 'upper') return '上盘'
  if (actualDirection.value === 'lower') return '下盘'
  if (actualDirection.value === 'draw') return '走水'
  return '待定'
})

function directionLabel(dir) {
  if (dir === 'upper') return '上盘'
  if (dir === 'lower') return '下盘'
  return '不明'
}

const predictionHit = computed(() => {
  if (!actualDirection.value || !prediction.value.direction) return false
  if (prediction.value.direction === 'neutral') return false
  return actualDirection.value === prediction.value.direction
})

const factorNames = ['近期状态', '交锋历史', '实力定位', '市场信号', '市场热度', '单关修正']

function selectMatch(match) {
  selectedMatch.value = match
  showPicker.value = false
  analysisSteps.value = []
  analysisComplete.value = false
  prediction.value = { direction: '', confidence: 0 }
  aiAnalysis.value = ''
}

async function startAnalysis() {
  if (!selectedMatch.value || analyzing.value) return

  analyzing.value = true
  analysisComplete.value = false
  prediction.value = { direction: '', confidence: 0 }
  aiAnalysis.value = ''

  // 初始化步骤为 pending 状态
  analysisSteps.value = factorNames.map(name => ({
    name,
    score: 0,
    direction: 'neutral',
    reason: '',
    dirLabel: '中性',
    dirClass: 'neutral',
    details: [],
    status: 'pending'
  }))

  // 逐个展示分析中动画
  let currentStep = 0
  const animateInterval = setInterval(() => {
    if (currentStep < analysisSteps.value.length) {
      analysisSteps.value[currentStep].status = 'analyzing'
      currentStep++
    }
  }, 600)

  try {
    const data = await request({
      url: `/api/predict/${selectedMatch.value.matchId}`,
      method: 'POST',
      data: {},
      timeout: 90000,
    })

    clearInterval(animateInterval)

    // 逐步展示结果（每300ms完成一个因子）
    const factors = data.factors || []
    for (let i = 0; i < analysisSteps.value.length; i++) {
      const factor = factors[i] || {}
      analysisSteps.value[i].status = 'analyzing'
      await new Promise(r => setTimeout(r, 300))
      analysisSteps.value[i].score = factor.score || 5
      analysisSteps.value[i].direction = factor.direction || 'neutral'
      analysisSteps.value[i].reason = factor.reason || ''
      analysisSteps.value[i].dirLabel = factor.direction === 'upper' ? '上盘' : factor.direction === 'lower' ? '下盘' : '中性'
      analysisSteps.value[i].dirClass = factor.direction || 'neutral'
      analysisSteps.value[i].details = factor.details || []
      analysisSteps.value[i].status = 'done'
    }

    // 用API返回的真实盘口和比分更新显示
    if (data.match) {
      if (data.match.handicap != null) {
        selectedMatch.value.handicap = data.match.handicap
      }
      if (data.match.homeScore != null) {
        selectedMatch.value.homeScore = data.match.homeScore
      }
      if (data.match.awayScore != null) {
        selectedMatch.value.awayScore = data.match.awayScore
      }
    }

    // 设置预测结果
    const pred = data.prediction || {}
    prediction.value = {
      direction: pred.direction || 'neutral',
      confidence: pred.confidence || 60
    }
    aiAnalysis.value = pred.analysis || '分析完成'
    analysisComplete.value = true
  } catch (e) {
    clearInterval(animateInterval)
    console.error('预测请求失败:', e)
    analysisSteps.value = []
    uni.showToast({ title: e.message || '预测失败', icon: 'none' })
  } finally {
    analyzing.value = false
  }
}

function formatHandicap(v) {
  if (v === undefined || v === null) return ''
  const num = Number(v)
  return num > 0 ? `+${num}` : `${num}`
}

function pickLeagueColor(league) {
  const colors = { '英超': '#3d195b', '西甲': '#ee8707', '德甲': '#d20515', '意甲': '#008fd7', '法甲': '#91c73e', '欧冠': '#2b2d42' }
  return colors[league] || '#6b7280'
}

watch(matchStatus, () => {
  selectedMatch.value = null
  analysisSteps.value = []
  analysisComplete.value = false
  searchKey.value = ''
  filterLeague.value = 'all'
  if (matchStatus.value === 'finished') {
    filterDate.value = ''
    fetchDates()
  } else {
    filterDate.value = 'all'
    fetchMatches()
  }
})

watch(filterDate, (val) => {
  if (val && val !== 'all') {
    fetchMatches()
  } else if (val === 'all' && matchStatus.value !== 'finished') {
    fetchMatches()
  }
})

onShow(() => {
  uni.$emit('tab-active', 'predict')
  if (matchStatus.value === 'finished') {
    fetchDates()
  } else {
    fetchMatches()
  }
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

  &, view, text, scroll-view {
    box-sizing: border-box;
    max-width: 100%;
  }
}

/* ===== 顶部操作区 ===== */
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
    transition: all 0.2s;

    &.active {
      background: $frbt-primary;
      color: #fff;
      font-weight: 600;
    }
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

  .picker-text {
    font-size: 24rpx;
    color: #1e293b;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .picker-placeholder {
    font-size: 24rpx;
    color: #94a3b8;
    flex: 1;
  }

  .picker-arrow {
    font-size: 22rpx;
    color: #94a3b8;
    margin-left: 4rpx;
  }
}

.predict-trigger {
  flex-shrink: 0;
  height: 56rpx;
  padding: 0 32rpx;
  background: $frbt-primary;
  border-radius: 6rpx;
  display: flex;
  align-items: center;
  justify-content: center;

  text {
    font-size: 26rpx;
    color: #fff;
    font-weight: 600;
  }

  &:active { opacity: 0.85; }
  &.disabled { opacity: 0.4; }
}

/* ===== 赛事信息条 ===== */
.match-info-bar {
  display: flex;
  align-items: center;
  padding: 14rpx 24rpx;
  gap: 12rpx;
  background: #f0fdf9;
  border-bottom: 1px solid #e2f5f0;

  .info-league {
    font-size: 20rpx;
    color: #fff;
    padding: 0 12rpx;
    border-radius: 4rpx;
    height: 36rpx;
    line-height: 36rpx;
    text-align: center;
  }
  .info-time {
    font-size: 22rpx;
    color: #64748b;
    line-height: 36rpx;
    height: 36rpx;
  }
  .info-handicap {
    font-size: 22rpx;
    color: $frbt-primary;
    font-weight: 600;
    line-height: 36rpx;
    height: 36rpx;
  }
  .info-single {
    border: 1px solid rgba(239, 68, 68, 0.4);
    border-radius: 4rpx;
    padding: 0 10rpx;
    height: 36rpx;
    line-height: 36rpx;
    text { font-size: 20rpx; color: #ef4444; line-height: 36rpx; }
  }
}

/* ===== 分析流程 ===== */
.analysis-flow {
  flex: 1;
  padding: 24rpx;
  height: calc(100vh - 180rpx);
}

.empty-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 200rpx 0;

  .hint-text {
    font-size: 26rpx;
    color: #94a3b8;
  }
}

/* ===== 时间线布局 ===== */
.timeline {
  padding: 0 8rpx;
}

.timeline-item {
  display: flex;
  gap: 16rpx;
  position: relative;
  padding-bottom: 24rpx;
  transition: opacity 0.3s;
  overflow: hidden;

  &.pending { opacity: 0.35; }
  &.active { opacity: 1; }
  &.done { opacity: 1; }

  &:last-child { padding-bottom: 0; }
}

.track {
  position: relative;
  width: 40rpx;
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;

  .track-line {
    position: absolute;
    width: 3rpx;
    background: #e2e8f0;
    left: 50%;
    transform: translateX(-50%);
    transition: background 0.3s;

    &.filled { background: $frbt-primary; }
    &.top { top: 0; height: 20rpx; }
    &.bottom { top: 56rpx; bottom: -24rpx; }
  }

  .track-dot {
    width: 36rpx;
    height: 36rpx;
    border-radius: 50%;
    border: 3rpx solid $frbt-primary;
    background: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-top: 4rpx;
    position: relative;
    z-index: 1;
    transition: all 0.3s;

    &.spinning {
      box-shadow: 0 0 0 6rpx rgba(13, 148, 136, 0.12);
      animation: dotPulse 1.2s ease-in-out infinite;
    }

    .dot-check { font-size: 20rpx; color: $frbt-primary; font-weight: 700; }
    .dot-num { font-size: 18rpx; color: $frbt-primary; font-weight: 600; }
  }
}

.step-content {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8rpx;
  margin-bottom: 6rpx;

  .step-name {
    font-size: 26rpx;
    font-weight: 600;
    color: #1e293b;
    flex-shrink: 1;
    min-width: 0;
  }

  .step-analyzing {
    font-size: 20rpx;
    color: $frbt-primary;
    animation: blink 1s ease-in-out infinite;
  }

  .step-score-inline {
    display: flex;
    align-items: center;
    gap: 8rpx;
    margin-left: auto;
    flex-shrink: 0;

    .dir-tag {
      font-size: 20rpx;
      font-weight: 600;
      padding: 2rpx 10rpx;
      border-radius: 3rpx;

      &.upper { color: #dc2626; background: #fef2f2; }
      &.lower { color: #059669; background: #ecfdf5; }
      &.neutral { color: #64748b; background: #f1f5f9; }
    }

    .score-num {
      font-size: 22rpx;
      font-weight: 600;
      color: #1e293b;

      .score-total { font-weight: 400; color: #94a3b8; font-size: 20rpx; }
    }
  }
}

.step-bar {
  height: 4rpx;
  background: #e2e8f0;
  border-radius: 2rpx;
  margin: 8rpx 0;
  overflow: hidden;

  .bar-fill {
    height: 100%;
    background: $frbt-primary;
    border-radius: 2rpx;
    transition: width 0.6s ease-out;
  }
}

.step-reason {
  font-size: 22rpx;
  color: #64748b;
  line-height: 1.5;
  word-break: break-all;
}

.sub-factors {
  margin-top: 12rpx;
  padding: 12rpx 16rpx;
  background: #f8fafb;
  border-radius: 8rpx;
  display: flex;
  flex-direction: column;
  gap: 8rpx;

  .sub-factor-item {
    display: flex;
    align-items: flex-start;
    gap: 8rpx;
    line-height: 1.4;

    .sub-dir-dot {
      font-size: 16rpx;
      flex-shrink: 0;
      margin-top: 2rpx;

      &.upper { color: #dc2626; }
      &.lower { color: #059669; }
      &.neutral { color: #94a3b8; }
    }

    .sub-name {
      font-size: 20rpx;
      color: #475569;
      font-weight: 600;
      flex-shrink: 0;
      min-width: 100rpx;
    }

    .sub-desc {
      font-size: 20rpx;
      color: #64748b;
      flex: 1;
      word-break: break-all;
    }
  }
}

/* ===== 分析结果 ===== */
.analysis-result {
  margin-top: 24rpx;
  padding-top: 8rpx;
}

.result-divider {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-bottom: 20rpx;

  .divider-line { flex: 1; height: 1px; background: #e2e8f0; }
  .divider-text { font-size: 22rpx; color: $frbt-primary; font-weight: 600; letter-spacing: 2rpx; }
}

.result-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28rpx 24rpx;
  border-radius: 12rpx;
  margin-bottom: 20rpx;

  &.upper {
    background: linear-gradient(135deg, #fff5f5 0%, #fee2e2 100%);
    border: 1px solid #fecaca;
  }
  &.lower {
    background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
    border: 1px solid #a7f3d0;
  }
  &.neutral {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border: 1px solid #e2e8f0;
  }

  .result-left {
    display: flex;
    align-items: center;
    gap: 16rpx;

    .dir-arrow {
      font-size: 40rpx;
      font-weight: 700;
      line-height: 1;
    }
    .dir-info {
      display: flex;
      flex-direction: column;

      .dir-text { font-size: 32rpx; font-weight: 700; color: #1e293b; }
      .dir-sub { font-size: 20rpx; color: #64748b; margin-top: 2rpx; }
    }
  }

  .result-right {
    text-align: right;

    .conf-num {
      font-size: 44rpx;
      font-weight: 700;
      color: #1e293b;
      line-height: 1;
      .conf-unit { font-size: 24rpx; font-weight: 500; color: #64748b; }
    }
    .conf-label { font-size: 20rpx; color: #64748b; display: block; margin-top: 4rpx; }
  }
}

/* ===== 实际结果对比 ===== */
.actual-result {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12rpx;
  padding: 24rpx;
  margin-bottom: 20rpx;

  .actual-header {
    margin-bottom: 16rpx;
    .actual-title { font-size: 24rpx; font-weight: 600; color: #1e293b; }
  }

  .no-score-tip {
    display: block;
    text-align: center;
    color: #94a3b8;
    font-size: 24rpx;
    padding: 16rpx 0;
  }

  .actual-score {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16rpx;
    padding: 16rpx 0;
    margin-bottom: 16rpx;
    border-bottom: 1px solid #f1f5f9;

    .actual-home, .actual-away {
      font-size: 26rpx;
      color: #374151;
      font-weight: 500;
    }
    .actual-home { text-align: right; flex: 1; }
    .actual-away { text-align: left; flex: 1; }
    .actual-num {
      font-size: 36rpx;
      font-weight: 700;
      color: #1e293b;
      min-width: 80rpx;
      text-align: center;
    }
  }

  .actual-compare {
    display: flex;
    flex-direction: column;
    gap: 12rpx;
  }

  .compare-row {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .compare-label { font-size: 24rpx; color: #64748b; }
    .compare-value {
      font-size: 24rpx;
      font-weight: 600;
      color: #1e293b;

      &.upper { color: #dc2626; }
      &.lower { color: #059669; }
    }

    &.verdict {
      padding-top: 12rpx;
      border-top: 1px solid #f1f5f9;
    }
  }

  .verdict-tag {
    font-size: 24rpx;
    font-weight: 600;
    padding: 4rpx 16rpx;
    border-radius: 4rpx;

    &.hit { color: #059669; background: #ecfdf5; }
    &.miss { color: #dc2626; background: #fef2f2; }
  }
}

.ai-analysis {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12rpx;
  padding: 24rpx;

  .ai-header {
    display: flex;
    align-items: center;
    gap: 8rpx;
    margin-bottom: 12rpx;

    .ai-icon { font-size: 24rpx; color: $frbt-primary; }
    .ai-title { font-size: 24rpx; font-weight: 600; color: #1e293b; }
  }

  .ai-text {
    font-size: 24rpx;
    color: #475569;
    line-height: 1.7;
  }
}

/* ===== 赛事选择弹窗 ===== */
.picker-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(15, 23, 42, 0.4);
  z-index: 1000;
  display: flex;
  align-items: flex-end;
}

.picker-sheet {
  width: 100%;
  max-height: 72vh;
  background: #fff;
  border-radius: 20rpx 20rpx 0 0;
  display: flex;
  flex-direction: column;
  padding-bottom: env(safe-area-inset-bottom);
  overflow: visible;
}

.sheet-handle {
  width: 64rpx;
  height: 6rpx;
  background: #e2e8f0;
  border-radius: 3rpx;
  margin: 16rpx auto 0;
}

.sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20rpx 28rpx 12rpx;

  .sheet-title { font-size: 30rpx; font-weight: 700; color: #1e293b; }
  .sheet-close {
    width: 48rpx; height: 48rpx;
    display: flex; align-items: center; justify-content: center;
    text { font-size: 28rpx; color: #94a3b8; }
  }
}

.sheet-filters {
  padding: 0 28rpx 12rpx;

  .filter-row {
    display: flex;
    align-items: center;
    gap: 16rpx;
    margin-bottom: 12rpx;
  }

  .date-picker-wrap {
    position: relative;
  }

  .date-picker-btn {
    display: flex;
    align-items: center;
    height: 64rpx;
    padding: 0 20rpx;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8rpx;
    white-space: nowrap;

    .date-picker-text {
      font-size: 26rpx;
      color: #1e293b;
    }
    .date-picker-icon {
      font-size: 20rpx;
      color: #94a3b8;
      margin-left: 8rpx;
    }
  }


  .search-input {
    flex: 1;
    height: 64rpx;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8rpx;
    padding: 0 20rpx;
    font-size: 26rpx;
    color: #1e293b;
  }
}

.league-tabs {
  padding: 0 28rpx 12rpx;
  white-space: nowrap;

  .league-tab {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 8rpx 20rpx;
    margin-right: 12rpx;
    border-radius: 20rpx;
    background: #f1f5f9;
    transition: all 0.2s;

    text { font-size: 22rpx; color: #64748b; }

    &.active {
      background: $frbt-primary;
      text { color: #fff; font-weight: 600; }
    }
  }
}

.match-list {
  flex: 1;
  max-height: 48vh;
  padding: 0 28rpx;
}

.match-row {
  display: flex;
  align-items: center;
  padding: 18rpx 12rpx;
  gap: 12rpx;
  border-bottom: 1px solid #f1f5f9;
  border-radius: 8rpx;
  transition: background 0.15s;

  &:active { background: #f8fafb; }

  &.selected {
    background: #f0fdfa;
    border-bottom-color: #ccfbf1;
  }

  .row-meta {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4rpx;
    min-width: 60rpx;

    .row-league {
      font-size: 18rpx;
      color: #fff;
      padding: 0 8rpx;
      border-radius: 3rpx;
      height: 32rpx;
      line-height: 32rpx;
      text-align: center;
    }
    .row-time { font-size: 20rpx; color: #94a3b8; }
  }

  .row-teams {
    flex: 1;
    font-size: 26rpx;
    color: #1e293b;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row-handicap {
    font-size: 24rpx;
    color: $frbt-primary;
    font-weight: 600;
    flex-shrink: 0;
  }
}

.list-empty {
  text-align: center;
  padding: 80rpx 0;
  text { font-size: 26rpx; color: #94a3b8; }
}

/* ===== 动画 ===== */
@keyframes dotPulse {
  0%, 100% { box-shadow: 0 0 0 4rpx rgba(13, 148, 136, 0.1); }
  50% { box-shadow: 0 0 0 10rpx rgba(13, 148, 136, 0.18); }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>

