<template>
  <view class="wc-predict-page">
    <!-- 顶部标题 -->
    <view class="top-bar">
      <view class="match-picker" @tap="showPicker = true">
        <text class="picker-text" v-if="selectedMatch">{{ selectedMatch.homeTeam.name }} vs {{ selectedMatch.awayTeam.name }}</text>
        <text class="picker-placeholder" v-else>选择世界杯赛事</text>
        <text class="picker-arrow">▾</text>
      </view>

      <view class="predict-trigger" :class="{ disabled: !selectedMatch || analyzing }" @tap="startAnalysis">
        <text>预测</text>
      </view>
    </view>

    <!-- 已选赛事信息 -->
    <view class="match-info-bar" v-if="selectedMatch">
      <text class="info-league">世界杯</text>
      <text class="info-time">{{ selectedMatch.matchDate.slice(5) }} {{ selectedMatch.matchTime.slice(0, 5) }}</text>
      <text class="info-handicap" v-if="selectedMatch.handicap != null">{{ formatHandicap(selectedMatch.handicap) }}</text>
      <view class="info-single" v-if="selectedMatch.isSingle"><text>单</text></view>
      <view class="last-pred-badge" v-if="lastPrediction" :class="lastPrediction.direction" @tap="showHistoryModal = true">
        <text class="last-pred-text">上次: {{ lastPrediction.direction === 'upper' ? '上盘' : lastPrediction.direction === 'lower' ? '下盘' : '中性' }} {{ lastPrediction.confidence }}% ▸</text>
      </view>
    </view>

    <!-- 分析流程区域 -->
    <scroll-view class="analysis-flow" scroll-y>
      <view v-if="!analyzing && analysisSteps.length === 0 && !analysisComplete" class="empty-hint">
        <text class="hint-text">选择世界杯赛事，点击预测开始分析</text>
      </view>

      <!-- 因子分析步骤 -->
      <view class="timeline" v-if="analysisSteps.length > 0">
        <view
          class="timeline-item"
          v-for="(step, idx) in analysisSteps"
          :key="idx"
          :class="{ active: step.status === 'analyzing', done: step.status === 'done', pending: step.status === 'pending' }"
        >
          <view class="track">
            <view v-if="idx > 0" class="track-line top" :class="{ filled: step.status !== 'pending' }"></view>
            <view class="track-dot" :class="step.status"></view>
            <view v-if="idx < analysisSteps.length - 1" class="track-line bottom" :class="{ filled: analysisSteps[idx + 1]?.status !== 'pending' }"></view>
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
            <text class="step-reason" v-if="step.status === 'done'">{{ step.reason }}</text>
            <view v-if="step.status === 'done' && step.details && step.details.length > 0" class="sub-factors">
              <view class="sub-factor-item" v-for="(d, di) in step.details" :key="di">
                <text class="sub-dir-dot" :class="d.direction">●</text>
                <text class="sub-name">{{ d.name }}</text>
                <text class="sub-desc">{{ d.desc }}</text>
              </view>
              <view v-if="step.matches && step.matches.length > 0" class="detail-action" @tap="showSimilarModal = true">
                <text class="detail-action-text">查看详细同赔数据 ▸</text>
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
              <text class="dir-text">{{ directionText }}</text>
              <text class="dir-sub">综合7项因子</text>
            </view>
          </view>
          <view class="result-right">
            <text class="conf-num">{{ prediction.confidence }}<text class="conf-unit">%</text></text>
            <text class="conf-label">置信度</text>
          </view>
        </view>

        <view v-if="aiAnalysis" class="ai-analysis">
          <view class="ai-header">
            <text class="ai-icon">✦</text>
            <text class="ai-title">AI 综合分析</text>
          </view>
          <text class="ai-text">{{ aiAnalysis }}</text>
        </view>
      </view>
    </scroll-view>

    <!-- 历史预测详情弹窗 -->
    <view class="history-mask" v-if="showHistoryModal" @tap="showHistoryModal = false"></view>
    <view class="history-modal" :class="{ show: showHistoryModal }">
      <view class="history-header">
        <text class="history-title">上次预测记录</text>
        <text class="history-close" @tap="showHistoryModal = false">✕</text>
      </view>
      <scroll-view class="history-body" scroll-y v-if="lastPrediction">
        <view class="history-meta">
          <text class="history-time">预测时间: {{ lastPrediction.predictedAt }}</text>
          <text class="history-handicap" v-if="lastPrediction.handicap != null">盘口: {{ formatHandicap(lastPrediction.handicap) }}</text>
        </view>

        <view class="history-result-card" :class="lastPrediction.direction">
          <view class="history-result-left">
            <text class="history-dir-arrow">{{ lastPrediction.direction === 'upper' ? '↑' : lastPrediction.direction === 'lower' ? '↓' : '−' }}</text>
            <view class="history-dir-info">
              <text class="history-dir-text">{{ lastPrediction.direction === 'upper' ? '上盘' : lastPrediction.direction === 'lower' ? '下盘' : '中性' }}</text>
              <text class="history-dir-sub" v-if="lastPrediction.overallReverse">触发整体逆向</text>
            </view>
          </view>
          <view class="history-result-right">
            <text class="history-conf-num">{{ lastPrediction.confidence }}<text class="history-conf-unit">%</text></text>
            <text class="history-conf-label">置信度</text>
          </view>
        </view>

        <view class="timeline history-timeline">
          <view class="timeline-item done" v-for="(f, fi) in lastPrediction.factors" :key="fi">
            <view class="track">
              <view v-if="fi > 0" class="track-line top filled"></view>
              <view class="track-dot done"></view>
              <view v-if="fi < lastPrediction.factors.length - 1" class="track-line bottom filled"></view>
            </view>
            <view class="step-content">
              <view class="step-header">
                <text class="step-name">{{ f.name }}</text>
                <view class="step-score-inline">
                  <text class="dir-tag" :class="f.direction">{{ f.direction === 'upper' ? '上盘' : f.direction === 'lower' ? '下盘' : '中性' }}</text>
                  <text class="score-num">{{ f.score }}<text class="score-total">/10</text></text>
                </view>
              </view>
              <view class="step-bar">
                <view class="bar-fill" :style="{ width: f.score * 10 + '%' }"></view>
              </view>
              <text class="step-reason">{{ f.reason }}</text>
              <view v-if="f.details && f.details.length > 0" class="sub-factors">
                <view class="sub-factor-item" v-for="(d, di) in f.details" :key="di">
                  <text class="sub-dir-dot" :class="d.direction">●</text>
                  <text class="sub-name">{{ d.name }}</text>
                  <text class="sub-desc">{{ d.desc }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <view class="history-analysis" v-if="lastPrediction.analysis">
          <text class="history-analysis-title">AI分析</text>
          <text class="history-analysis-text">{{ lastPrediction.analysis }}</text>
        </view>
      </scroll-view>
    </view>

    <!-- 历史同赔详情弹窗 -->
    <view class="similar-mask" v-if="showSimilarModal" @tap="showSimilarModal = false"></view>
    <view class="similar-modal" :class="{ show: showSimilarModal }">
      <view class="similar-header">
        <text class="similar-title">历史同赔详情</text>
        <text class="similar-close" @tap="showSimilarModal = false">✕</text>
      </view>
      <scroll-view class="similar-body" scroll-y scroll-x>
        <view class="similar-table">
          <view class="similar-row similar-thead">
            <text class="col-sim">相似度</text>
            <text class="col-year">届次</text>
            <text class="col-stage">阶段</text>
            <text class="col-team">主队</text>
            <text class="col-score">比分</text>
            <text class="col-team">客队</text>
            <text class="col-result">结果</text>
            <text class="col-odds">竞彩初盘</text>
            <text class="col-odds">竞彩终盘</text>
            <text class="col-ah">亚盘</text>
            <text class="col-ah-result">盘路</text>
            <text class="col-ou">大小球</text>
            <text class="col-ou-result">大小</text>
          </view>
          <view class="similar-row" v-for="(m, mi) in similarMatches" :key="mi">
            <text class="col-sim">{{ m.similarity }}%</text>
            <text class="col-year">{{ m.year }}</text>
            <text class="col-stage">{{ m.stage }}</text>
            <text class="col-team">{{ m.homeTeam }}</text>
            <text class="col-score">{{ m.score }}</text>
            <text class="col-team">{{ m.awayTeam }}</text>
            <text class="col-result" :class="resultClass(m.result)">{{ m.result }}</text>
            <text class="col-odds">{{ m.openOdds }}</text>
            <text class="col-odds">{{ m.closeOdds }}</text>
            <text class="col-ah">{{ m.ahInitial || '-' }}→{{ m.ahClose || '-' }}</text>
            <text class="col-ah-result" :class="ahResultClass(m.ahResult)">{{ m.ahResult || '-' }}</text>
            <text class="col-ou">{{ m.ouCloseLine || '-' }}</text>
            <text class="col-ou-result" :class="ouResultClass(m.ouResult)">{{ m.ouResult || '-' }}</text>
          </view>
        </view>
      </scroll-view>
    </view>

    <!-- 比赛选择弹窗 -->
    <view class="picker-mask" v-if="showPicker" @tap="showPicker = false"></view>
    <view class="picker-sheet" :class="{ show: showPicker }">
      <view class="picker-header">
        <text class="picker-title">世界杯赛事</text>
        <text class="picker-close" @tap="showPicker = false">✕</text>
      </view>
      <view class="picker-loading" v-if="loading">
        <text>加载中...</text>
      </view>
      <scroll-view class="picker-list" scroll-y v-else>
        <view
          class="picker-item"
          v-for="match in allMatches"
          :key="match.matchId"
          @tap="selectMatch(match)"
          :class="{ selected: selectedMatch?.matchId === match.matchId }"
        >
          <view class="picker-match-time">
            <text>{{ match.matchDate.slice(5) }} {{ match.matchTime.slice(0, 5) }}</text>
          </view>
          <view class="picker-match-teams">
            <text class="team-name">{{ match.homeTeam.name }}</text>
            <text class="vs">vs</text>
            <text class="team-name">{{ match.awayTeam.name }}</text>
          </view>
          <view class="picker-match-extra">
            <text v-if="match.isSingle" class="single-tag">单</text>
            <text v-if="match.handicap != null" class="handicap-tag">{{ formatHandicap(match.handicap) }}</text>
          </view>
        </view>
        <view v-if="allMatches.length === 0" class="picker-empty">
          <text>暂无世界杯在售比赛</text>
        </view>
      </scroll-view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { request } from '@/utils/http'

const showPicker = ref(false)
const showSimilarModal = ref(false)
const showHistoryModal = ref(false)
const similarMatches = ref([])
const lastPrediction = ref(null)
const loading = ref(false)
const allMatches = ref([])
const selectedMatch = ref(null)
const analyzing = ref(false)
const analysisComplete = ref(false)
const analysisSteps = ref([])
const prediction = ref({ direction: '', confidence: 0 })
const aiAnalysis = ref('')

const factorNames = ['近期状态', '实力定位', '市场信号', '市场热度', '竞彩赔率', '历史同赔', '单关修正']

const directionText = computed(() => {
  if (prediction.value.direction === 'upper') return '上盘'
  if (prediction.value.direction === 'lower') return '下盘'
  return '不明'
})

const pendingMatchId = ref(null)

onLoad((query) => {
  if (query?.matchId) {
    pendingMatchId.value = query.matchId
  }
})

onMounted(async () => {
  await loadMatches()
  if (pendingMatchId.value) {
    const found = allMatches.value.find(m => m.matchId === pendingMatchId.value)
    if (found) {
      selectedMatch.value = found
      fetchLastPrediction(found.matchId)
    }
  }
})

async function loadMatches() {
  loading.value = true
  try {
    const data = await request({ url: '/api/worldcup/matches', method: 'GET' })
    allMatches.value = (data || []).map(m => ({
      matchId: m.matchId,
      matchDate: m.matchDate,
      matchTime: m.matchTime,
      league: m.league || '世界杯',
      homeTeam: m.homeTeam || { name: m.homeTeamName },
      awayTeam: m.awayTeam || { name: m.awayTeamName },
      handicap: m.handicap,
      isSingle: m.isSingle,
    }))
  } catch (e) {
    console.error('加载世界杯比赛失败:', e)
  } finally {
    loading.value = false
  }
}

function selectMatch(match) {
  selectedMatch.value = match
  showPicker.value = false
  analysisSteps.value = []
  analysisComplete.value = false
  prediction.value = { direction: '', confidence: 0 }
  aiAnalysis.value = ''
  lastPrediction.value = null
  fetchLastPrediction(match.matchId)
}

async function fetchLastPrediction(matchId) {
  try {
    const data = await request({ url: `/api/worldcup/prediction-history/${matchId}`, method: 'GET' })
    if (data && data.direction) {
      lastPrediction.value = data
    }
  } catch (e) {
    // ignore
  }
}

async function startAnalysis() {
  if (!selectedMatch.value || analyzing.value) return

  analyzing.value = true
  analysisComplete.value = false
  prediction.value = { direction: '', confidence: 0 }
  aiAnalysis.value = ''

  analysisSteps.value = factorNames.map(name => ({
    name, score: 0, direction: 'neutral', reason: '',
    dirLabel: '中性', dirClass: 'neutral', details: [], status: 'pending'
  }))

  let currentStep = 0
  const animateInterval = setInterval(() => {
    if (currentStep < analysisSteps.value.length) {
      analysisSteps.value[currentStep].status = 'analyzing'
      currentStep++
    }
  }, 600)

  try {
    const data = await request({
      url: `/api/worldcup/predict/${selectedMatch.value.matchId}`,
      method: 'POST',
      data: {},
      timeout: 90000,
    })

    clearInterval(animateInterval)

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
      analysisSteps.value[i].matches = factor.matches || []
      if (factor.matches && factor.matches.length > 0) {
        similarMatches.value = factor.matches
      }
      analysisSteps.value[i].status = 'done'
    }

    if (data.match && data.match.handicap != null) {
      selectedMatch.value.handicap = data.match.handicap
    }

    const pred = data.prediction || {}
    prediction.value = {
      direction: pred.direction || 'neutral',
      confidence: pred.confidence || 60
    }
    aiAnalysis.value = pred.analysis || '分析完成'
    analysisComplete.value = true
  } catch (e) {
    clearInterval(animateInterval)
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

function resultClass(result) {
  if (result === '主胜') return 'result-home'
  if (result === '客胜') return 'result-away'
  return 'result-draw'
}

function ahResultClass(result) {
  if (result === '上盘') return 'ah-upper'
  if (result === '下盘') return 'ah-lower'
  return 'ah-push'
}

function ouResultClass(result) {
  if (result === '大球') return 'ou-over'
  if (result === '小球') return 'ou-under'
  return 'ou-push'
}
</script>

<style lang="scss" scoped>
@import '@/uni.scss';

.wc-predict-page {
  min-height: 100vh;
  background: #f7faf9;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  padding-bottom: 40rpx;

  &, view, text, scroll-view {
    box-sizing: border-box;
    max-width: 100%;
  }
}

.top-bar {
  display: flex;
  align-items: center;
  padding: 16rpx 24rpx;
  gap: 12rpx;
  background: #fff;
  box-shadow: 0 1px 0 rgba(0,0,0,0.04);
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
}
.picker-text { font-size: 24rpx; color: #1e293b; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker-placeholder { font-size: 24rpx; color: #94a3b8; flex: 1; }
.picker-arrow { font-size: 22rpx; color: #94a3b8; margin-left: 4rpx; }

.predict-trigger {
  flex-shrink: 0;
  height: 56rpx;
  padding: 0 32rpx;
  background: $frbt-primary;
  border-radius: 6rpx;
  display: flex;
  align-items: center;
  justify-content: center;

  text { font-size: 26rpx; color: #fff; font-weight: 600; }
  &:active { opacity: 0.85; }
  &.disabled { opacity: 0.4; }
}

.match-info-bar {
  display: flex;
  align-items: center;
  padding: 14rpx 24rpx;
  gap: 12rpx;
  background: #f0fdf9;
  border-bottom: 1px solid #e2f5f0;
}
.info-league {
  font-size: 20rpx;
  color: #fff;
  padding: 0 12rpx;
  border-radius: 4rpx;
  height: 36rpx;
  line-height: 36rpx;
  text-align: center;
  background: $frbt-primary;
}
.info-time { font-size: 22rpx; color: #64748b; line-height: 36rpx; height: 36rpx; }
.info-handicap { font-size: 22rpx; color: $frbt-primary; font-weight: 600; line-height: 36rpx; height: 36rpx; }
.info-single {
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 4rpx;
  padding: 0 10rpx;
  height: 36rpx;
  line-height: 36rpx;
  text { font-size: 20rpx; color: #ef4444; line-height: 36rpx; }
}
.last-pred-badge {
  margin-left: auto;
  padding: 0 12rpx;
  height: 36rpx;
  line-height: 36rpx;
  border-radius: 4rpx;
  font-size: 20rpx;

  &.upper { background: #fef2f2; }
  &.lower { background: #ecfdf5; }
  &.neutral { background: #f1f5f9; }

  .last-pred-text {
    font-size: 20rpx;
    font-weight: 500;
    color: #475569;
  }
}

.analysis-flow {
  flex: 1;
  padding: 24rpx;
}

.empty-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 200rpx 0;
}
.hint-text { font-size: 26rpx; color: #94a3b8; }

.timeline { padding: 0 8rpx; }

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
}
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

  &.analyzing {
    box-shadow: 0 0 0 6rpx rgba(13, 148, 136, 0.12);
    animation: dotPulse 1.2s ease-in-out infinite;
  }
  &.done {
    background: $frbt-primary;
    border-color: $frbt-primary;
  }
}
@keyframes dotPulse {
  0%, 100% { box-shadow: 0 0 0 6rpx rgba(13, 148, 136, 0.12); }
  50% { box-shadow: 0 0 0 10rpx rgba(13, 148, 136, 0.06); }
}

.step-content { flex: 1; min-width: 0; overflow: hidden; }

.step-header {
  display: flex;
  align-items: center;
  gap: 8rpx;
  margin-bottom: 6rpx;
}
.step-name { font-size: 26rpx; font-weight: 600; color: #1e293b; flex-shrink: 1; min-width: 0; }

.step-analyzing { font-size: 20rpx; color: $frbt-primary; animation: blink 1s ease-in-out infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

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

.step-reason { font-size: 22rpx; color: #64748b; line-height: 1.5; word-break: break-all; }

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

    .sub-name { font-size: 20rpx; color: #475569; font-weight: 600; flex-shrink: 0; min-width: 100rpx; }
    .sub-desc { font-size: 20rpx; color: #64748b; flex: 1; word-break: break-all; }
  }
}

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

    .dir-arrow { font-size: 40rpx; font-weight: 700; line-height: 1; }
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
      font-size: 44rpx; font-weight: 700; color: #1e293b; line-height: 1;
      .conf-unit { font-size: 24rpx; font-weight: 500; color: #64748b; }
    }
    .conf-label { font-size: 20rpx; color: #64748b; display: block; margin-top: 4rpx; }
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
}
.ai-text { font-size: 22rpx; color: #64748b; line-height: 1.6; }

.detail-action {
  margin-top: 12rpx;
  padding: 8rpx 0;
}
.detail-action-text {
  font-size: 22rpx;
  color: $frbt-primary;
  font-weight: 500;
}

.history-mask { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 200; }
.history-modal {
  position: fixed;
  top: 10vh;
  left: 5vw;
  right: 5vw;
  bottom: 10vh;
  background: #fff;
  border-radius: 16rpx;
  z-index: 201;
  display: flex;
  flex-direction: column;
  transform: scale(0.9);
  opacity: 0;
  transition: all 0.25s;
  pointer-events: none;

  &.show { transform: scale(1); opacity: 1; pointer-events: auto; }
}
.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20rpx 24rpx;
  border-bottom: 1rpx solid #e2e8f0;
  flex-shrink: 0;
}
.history-title { font-size: 28rpx; font-weight: 600; color: #1e293b; }
.history-close { font-size: 32rpx; color: #94a3b8; padding: 8rpx; }
.history-body { flex: 1; padding: 24rpx; overflow: auto; }

.history-meta {
  display: flex;
  gap: 16rpx;
  margin-bottom: 20rpx;
  font-size: 22rpx;
  color: #64748b;
}

.history-result-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx;
  border-radius: 12rpx;
  margin-bottom: 24rpx;

  &.upper { background: linear-gradient(135deg, #fff5f5 0%, #fee2e2 100%); border: 1px solid #fecaca; }
  &.lower { background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); border: 1px solid #a7f3d0; }
  &.neutral { background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); border: 1px solid #e2e8f0; }
}
.history-result-left { display: flex; align-items: center; gap: 12rpx; }
.history-dir-arrow { font-size: 36rpx; font-weight: 700; }
.history-dir-info { display: flex; flex-direction: column; }
.history-dir-text { font-size: 28rpx; font-weight: 700; color: #1e293b; }
.history-dir-sub { font-size: 20rpx; color: #64748b; margin-top: 2rpx; }
.history-result-right { text-align: right; }
.history-conf-num { font-size: 40rpx; font-weight: 700; color: #1e293b; }
.history-conf-unit { font-size: 22rpx; font-weight: 500; color: #64748b; }
.history-conf-label { font-size: 20rpx; color: #64748b; display: block; }

.history-timeline { margin-bottom: 24rpx; }

.history-analysis {
  background: #f8fafb;
  border: 1px solid #e2e8f0;
  border-radius: 12rpx;
  padding: 20rpx;
}
.history-analysis-title { font-size: 24rpx; font-weight: 600; color: #1e293b; display: block; margin-bottom: 8rpx; }
.history-analysis-text { font-size: 22rpx; color: #64748b; line-height: 1.6; }

.similar-mask { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 200; }
.similar-modal {
  position: fixed;
  top: 5vh;
  left: 3vw;
  right: 3vw;
  bottom: 5vh;
  background: #fff;
  border-radius: 16rpx;
  z-index: 201;
  display: flex;
  flex-direction: column;
  transform: scale(0.9);
  opacity: 0;
  transition: all 0.25s;
  pointer-events: none;

  &.show { transform: scale(1); opacity: 1; pointer-events: auto; }
}
.similar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20rpx 24rpx;
  border-bottom: 1rpx solid #e2e8f0;
  flex-shrink: 0;
}
.similar-title { font-size: 28rpx; font-weight: 600; color: #1e293b; }
.similar-close { font-size: 32rpx; color: #94a3b8; padding: 8rpx; }

.similar-body { flex: 1; overflow: auto; }

.similar-table { min-width: 1400rpx; padding: 0 16rpx 24rpx; }
.similar-row {
  display: flex;
  align-items: center;
  padding: 14rpx 0;
  border-bottom: 1rpx solid #f1f5f9;
  gap: 4rpx;
}
.similar-thead {
  position: sticky;
  top: 0;
  background: #f8fafb;
  font-weight: 600;
  color: #64748b;
  font-size: 20rpx;
  z-index: 1;
}
.similar-row:not(.similar-thead) { font-size: 20rpx; color: #334155; }

.col-sim { width: 90rpx; text-align: center; }
.col-year { width: 72rpx; text-align: center; }
.col-stage { width: 100rpx; text-align: center; }
.col-team { width: 120rpx; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-score { width: 64rpx; text-align: center; font-weight: 600; }
.col-result { width: 64rpx; text-align: center; font-weight: 500; }
.col-odds { width: 170rpx; text-align: center; }
.col-ah { width: 180rpx; text-align: center; }
.col-ah-result { width: 64rpx; text-align: center; font-weight: 500; }
.col-ou { width: 64rpx; text-align: center; }
.col-ou-result { width: 64rpx; text-align: center; font-weight: 500; }

.result-home { color: #dc2626; }
.result-away { color: #059669; }
.result-draw { color: #d97706; }
.ah-upper { color: #dc2626; }
.ah-lower { color: #059669; }
.ah-push { color: #64748b; }
.ou-over { color: #dc2626; }
.ou-under { color: #059669; }
.ou-push { color: #64748b; }

.picker-mask { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); z-index: 100; }
.picker-sheet {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: white;
  border-radius: 24rpx 24rpx 0 0;
  z-index: 101;
  max-height: 70vh;
  transform: translateY(100%);
  transition: transform 0.3s;

  &.show { transform: translateY(0); }
}
.picker-header { display: flex; justify-content: space-between; align-items: center; padding: 24rpx 32rpx; border-bottom: 1rpx solid #f0f0f0; }
.picker-title { font-size: 30rpx; font-weight: 600; color: #1e293b; }
.picker-close { font-size: 32rpx; color: #94a3b8; padding: 8rpx; }
.picker-loading { text-align: center; padding: 60rpx; color: #94a3b8; }
.picker-list { max-height: 60vh; }
.picker-item {
  display: flex;
  align-items: center;
  padding: 24rpx 32rpx;
  border-bottom: 1rpx solid #f8f8f8;
  gap: 16rpx;

  &.selected { background: #f0fdf9; }
}
.picker-match-time { font-size: 22rpx; color: #64748b; min-width: 140rpx; }
.picker-match-teams { flex: 1; display: flex; align-items: center; gap: 8rpx; }
.team-name { font-size: 26rpx; font-weight: 500; color: #1e293b; }
.vs { font-size: 22rpx; color: #94a3b8; }
.picker-match-extra { display: flex; gap: 8rpx; }
.single-tag {
  border: 1px solid rgba(239, 68, 68, 0.4);
  color: #ef4444;
  padding: 0 10rpx;
  border-radius: 4rpx;
  font-size: 20rpx;
  height: 32rpx;
  line-height: 32rpx;
}
.handicap-tag { background: #f0fdf9; color: $frbt-primary; padding: 2rpx 8rpx; border-radius: 4rpx; font-size: 22rpx; }
.picker-empty { text-align: center; padding: 60rpx; color: #94a3b8; font-size: 26rpx; }
</style>
