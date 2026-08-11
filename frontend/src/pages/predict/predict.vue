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

    <!-- 日职辅助情报（仅展示，不参与因子） -->
    <JapanIntelCard v-if="isJapanMatch && japanContext" :data="japanContext" />
    <view v-else-if="isJapanMatch && japanContextLoading" class="jp-loading">
      <text>加载日本情报…</text>
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
            <!-- 历史同赔详情入口(日职0场也可进弹窗开「仅日本」) -->
            <view
              v-if="step.status === 'done' && step.name === '历史同赔' && ((step.matches && step.matches.length > 0) || isJapanMatch)"
              class="detail-action"
              @tap="openSimilarModal"
            >
              <text class="detail-action-text">查看详细同赔数据{{ step.matches?.length ? ` ${step.matches.length}场` : '' }} ▸</text>
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

        <view class="result-card" :class="[prediction.direction, { reversed: prediction.overallReverse }]">
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

        <view class="reverse-tag" v-if="prediction.overallReverse">
          <text class="reverse-text">{{ reverseTagText }}</text>
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

        <!-- 投注建议（仅未开始的比赛） -->
        <view class="bet-advice" v-if="matchStatus === 'not_started' && prediction.direction !== 'neutral'">
          <view class="advice-header">
            <text class="advice-title">投注建议</text>
            <text class="advice-strategy">{{ currentStrategyLabel }}</text>
          </view>

          <view class="advice-body">
            <view class="advice-row">
              <text class="advice-label">建议方向</text>
              <text class="advice-value dir" :class="prediction.direction">{{ directionLabel(prediction.direction) }}</text>
            </view>
            <view class="advice-row">
              <text class="advice-label">置信度</text>
              <text class="advice-value" :class="confidenceClass">{{ prediction.confidence }}%</text>
            </view>
            <view class="advice-row">
              <text class="advice-label">可用余额</text>
              <text class="advice-value">¥{{ bankroll }}</text>
            </view>
            <view class="advice-row highlight">
              <text class="advice-label">三档金额</text>
              <view class="advice-tiers">
                <view class="tier-pill" :class="{ active: selectedTier === 'low' }" @tap="selectTierOnPredict('low')">
                  <text class="tier-k">低</text>
                  <text class="tier-v">¥{{ tieredStakes.low.amount }}</text>
                </view>
                <view class="tier-pill" :class="{ active: selectedTier === 'mid' }" @tap="selectTierOnPredict('mid')">
                  <text class="tier-k">中</text>
                  <text class="tier-v">¥{{ tieredStakes.mid.amount }}</text>
                </view>
                <view class="tier-pill" :class="{ active: selectedTier === 'high' }" @tap="selectTierOnPredict('high')">
                  <text class="tier-k">高</text>
                  <text class="tier-v">¥{{ tieredStakes.high.amount }}</text>
                </view>
              </view>
            </view>
            <view class="advice-detail">
              <text class="advice-prob" v-if="recommendedStake.probability">
                系统凯利参考 ¥{{ recommendedStake.kelly }}(仅供参考) · 校准概率 {{ Math.round(recommendedStake.probability * 100) }}% · 预期 {{ (recommendedStake.edge * 100).toFixed(1) }}%
              </text>
            </view>
          </view>

          <view class="advice-warning" v-if="riskWarning">
            <text class="warning-text">{{ riskWarning }}</text>
          </view>

          <view class="advice-actions">
            <view class="advice-btn secondary" @tap="adjustStake">
              <text>调整金额</text>
            </view>
            <view class="advice-btn primary" @tap="betWithAdvice">
              <text>按此建议投注</text>
            </view>
          </view>
        </view>
      </view>
    </scroll-view>

    <!-- 赛事选择弹窗 -->
    <view class="picker-mask" v-if="showPicker" @tap.self="showPicker = false">
      <view class="picker-sheet">
        <view class="sheet-handle"></view>
        <view class="sheet-header">
          <text class="sheet-title">选择赛事</text>
          <view class="sheet-batch-btn" @tap="goBatchSimilar">
            <text>同赔分析</text>
          </view>
          <view class="sheet-close" @tap="showPicker = false"><text>✕</text></view>
        </view>

        <view class="sheet-filters">
          <view class="filter-row">
            <input class="search-input" v-model="searchKey" placeholder="搜索队伍" placeholder-style="color:#b0b7c0" />
          </view>

          <!-- 日期按竞彩售卖期(match_number), 与赛果查询一致 -->
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
              v-for="d in displaySaleDates"
              :key="d"
              :class="{ active: filterDate === d }"
              @tap="filterDate = d"
            >
              <text>{{ d.slice(5) }}</text>
            </view>
            <view v-if="matchStatus === 'finished'" class="league-tab" @tap="openCalendar">
              <text>选择日期</text>
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
            <text>{{ emptyPickerHint }}</text>
          </view>
        </scroll-view>
      </view>
    </view>

    <!-- 历史同赔详情弹窗 -->
    <view class="similar-mask" v-if="showSimilarModal" @tap="closeSimilarModal"></view>
    <view class="similar-modal" :class="{ show: showSimilarModal }">
      <view class="similar-header">
        <view class="similar-title-wrap">
          <text class="similar-title">历史同赔详情</text>
          <text
            v-if="isJapanMatch"
            class="jp-toggle"
            :class="{ on: similarJapanOnly, loading: similarModeLoading }"
            @tap.stop="toggleJapanOnly"
          >仅日本</text>
          <text
            v-else-if="isSameLeagueMatch"
            class="jp-toggle"
            :class="{ on: similarLeagueOnly, loading: similarModeLoading }"
            @tap.stop="toggleLeagueOnly"
          >同赛事</text>
        </view>
        <text class="similar-close" @tap="closeSimilarModal">关闭</text>
      </view>
      <view v-if="similarJapanOnly" class="jp-hint">
        <text>仅日职/日乙/杯赛 · 低赔±0.05 · 高赔±0.15</text>
      </view>
      <view v-else-if="similarLeagueOnly" class="jp-hint">
        <text>仅{{ selectedMatch?.league || '同名赛事' }} · 低赔±0.05 · 高赔±0.15</text>
      </view>
      <view v-if="similarStats.total > 0" class="similar-stats">
        <view class="stats-row">
          <text class="stats-label">胜平负</text>
          <text class="stats-item r-win">主胜 {{ similarStats.win }}({{ similarStats.winPct }}%)</text>
          <text class="stats-item r-draw">平 {{ similarStats.draw }}({{ similarStats.drawPct }}%)</text>
          <text class="stats-item r-loss">客胜 {{ similarStats.loss }}({{ similarStats.lossPct }}%)</text>
          <text class="stats-n">{{ similarStats.total }}场</text>
        </view>
        <view class="stats-row">
          <text class="stats-label">盘路</text>
          <template v-if="similarStats.ahTotal > 0">
            <text class="stats-item ah-upper">上盘 {{ similarStats.upper }}({{ similarStats.upperPct }}%){{ similarStats.halfUp ? ` 含半${similarStats.halfUp}` : '' }}</text>
            <text class="stats-item ah-push">走水 {{ similarStats.push }}({{ similarStats.pushPct }}%)</text>
            <text class="stats-item ah-lower">下盘 {{ similarStats.lower }}({{ similarStats.lowerPct }}%){{ similarStats.halfDown ? ` 含半${similarStats.halfDown}` : '' }}</text>
            <text class="stats-n">{{ similarStats.ahTotal }}场</text>
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
            v-for="(m, mi) in similarMatches"
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
          <view v-if="similarMatches.length === 0" class="similar-empty">
            <text>暂无历史同赔数据</text>
          </view>
        </view>
      </scroll-view>
    </view>

    <!-- 日期选择弹窗 -->
    <view class="cal-mask" v-if="showCalendar" @tap="showCalendar = false"></view>
    <view class="cal-panel" :class="{ visible: showCalendar }">
      <view class="cal-header">
        <text class="cal-cancel" @tap="showCalendar = false">取消</text>
        <text class="cal-title">选择日期</text>
        <text class="cal-confirm" @tap="confirmCalendar">确定</text>
      </view>
      <view class="cal-body">
        <view class="cal-nav">
          <text class="cal-arrow" @tap="calPrevMonth">&lt;</text>
          <text class="cal-month">{{ calYear }}年{{ calMonth }}月</text>
          <text class="cal-arrow" @tap="calNextMonth">&gt;</text>
        </view>
        <view class="cal-weekdays">
          <text class="cal-wd" v-for="w in ['日','一','二','三','四','五','六']" :key="w">{{ w }}</text>
        </view>
        <view class="cal-days">
          <text
            v-for="(d, i) in calDays"
            :key="i"
            class="cal-day"
            :class="{
              'cal-other': d.other,
              'cal-today': d.isToday,
              'cal-selected': d.dateStr === calSelected,
              'cal-has': !d.other && saleDateSet.has(d.dateStr),
            }"
            @tap="!d.other && (calSelected = d.dateStr)"
          >{{ d.day }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { request } from '@/utils/http'
import { useConfigStore } from '@/stores/configStore'
import { useBetStore } from '@/stores/betStore'
import { calcRecommendedStake, calcTieredStakes, getStrategyPreset, checkRiskStatus } from '@/utils/strategyEngine'
import { loadCalibration } from '@/utils/calibration'
import { calcSimilarStats, filterSimilarWithAh } from '@/utils/similarStats'
import { isJapanLeague } from '@/utils/japanLeague'
import { isSameLeagueEligible } from '@/utils/sameLeague'
import JapanIntelCard from '@/components/JapanIntelCard.vue'

const matchStatus = ref('not_started')
const selectedMatch = ref(null)
const showPicker = ref(false)
const searchKey = ref('')
const filterDate = ref('all')
const filterLeague = ref('all')
const analyzing = ref(false)
const analysisComplete = ref(false)
const analysisSteps = ref([])
const prediction = ref({ direction: '', confidence: 0, overallReverse: false, consensusDir: null })
const aiAnalysis = ref('')
const showSimilarModal = ref(false)
const similarMatches = ref([])
const similarDefaultMatches = ref([])
const similarJapanOnly = ref(false)
const similarLeagueOnly = ref(false)
const similarModeLoading = ref(false)
const similarStats = computed(() => calcSimilarStats(similarMatches.value))
const isJapanMatch = computed(() => isJapanLeague(selectedMatch.value?.league))
const isSameLeagueMatch = computed(() => isSameLeagueEligible(selectedMatch.value?.league))
const japanContext = ref(null)
const japanContextLoading = ref(false)

function applyPredictSimilarList(list) {
  return filterSimilarWithAh(list || [])
}

const openSimilarModal = () => {
  similarJapanOnly.value = false
  similarLeagueOnly.value = false
  similarModeLoading.value = false
  // 打开时用当前 F6 默认结果(已剔缺亚盘)
  if (similarDefaultMatches.value.length) {
    similarMatches.value = applyPredictSimilarList(similarDefaultMatches.value)
  }
  showSimilarModal.value = true
}
const closeSimilarModal = () => {
  showSimilarModal.value = false
  similarJapanOnly.value = false
  similarLeagueOnly.value = false
  similarModeLoading.value = false
}
function _restoreDefaultSimilarPredict() {
  similarJapanOnly.value = false
  similarLeagueOnly.value = false
  similarMatches.value = applyPredictSimilarList(similarDefaultMatches.value)
}
async function toggleJapanOnly() {
  if (!isJapanMatch.value || similarModeLoading.value) return
  if (similarJapanOnly.value) {
    _restoreDefaultSimilarPredict()
    return
  }
  const mid = selectedMatch.value?.matchId
  if (!mid) {
    uni.showToast({ title: '比赛ID缺失', icon: 'none' })
    return
  }
  similarModeLoading.value = true
  try {
    const data = await request({
      url: `/api/predict/${encodeURIComponent(mid)}/similar-odds`,
      method: 'GET',
      data: { japan_only: true },
    })
    similarLeagueOnly.value = false
    similarJapanOnly.value = true
    similarMatches.value = applyPredictSimilarList(data?.matches || [])
  } catch (e) {
    uni.showToast({ title: e?.message || '仅日本匹配失败', icon: 'none' })
  } finally {
    similarModeLoading.value = false
  }
}
async function toggleLeagueOnly() {
  if (!isSameLeagueMatch.value || similarModeLoading.value) return
  if (similarLeagueOnly.value) {
    _restoreDefaultSimilarPredict()
    return
  }
  const mid = selectedMatch.value?.matchId
  if (!mid) {
    uni.showToast({ title: '比赛ID缺失', icon: 'none' })
    return
  }
  similarModeLoading.value = true
  try {
    const data = await request({
      url: `/api/predict/${encodeURIComponent(mid)}/similar-odds`,
      method: 'GET',
      data: { league_only: true },
    })
    similarJapanOnly.value = false
    similarLeagueOnly.value = true
    similarMatches.value = applyPredictSimilarList(data?.matches || [])
  } catch (e) {
    uni.showToast({ title: e?.message || '同赛事匹配失败', icon: 'none' })
  } finally {
    similarModeLoading.value = false
  }
}

const allMatches = ref([])
const loadingMatches = ref(false)
/** 售卖期日期列表 YYYY-MM-DD, 来自 /api/predict/dates(match_number前6位) */
const saleDates = ref([])
const pendingMatchId = ref(null)
/** 从赛事列表「预」进入时自动开跑 */
const pendingAutoStart = ref(false)
const customStake = ref(null)

const configStore = useConfigStore()
const betStore = useBetStore()

// 可用余额：用 betStore.bankroll（已扣除投注中金额），避免推荐超额
const bankroll = computed(() => Math.max(0, Math.round(betStore.bankroll)))

// 校准数据（历史命中率分桶），用于把置信度校准为真实概率
const calibrationData = ref(null)

// 自定义策略配置（仅当 riskTolerance==='custom' 时使用）
const customConfig = computed(() => {
  if (configStore.riskTolerance !== 'custom') return null
  return {
    fixedRatio: configStore.fixedRatio,
    kellyFactor: configStore.kellyFactor,
    stopLossLimit: configStore.stopLossLimit,
    maxDrawdown: configStore.maxDrawdown,
    minConfidence: configStore.minConfidence,
  }
})

const currentStrategyLabel = computed(() => {
  const preset = getStrategyPreset(configStore.riskTolerance, customConfig.value)
  return preset.label
})

/**
 * 根据预测方向 + 亚盘盘口符号，从竞彩让球胜平负赔率取对应方向的真实投注赔率。
 * 系统盘口约定：负值=主队让球(主队=上盘)，正值=客队让球(客队=上盘)。
 */
function computeBetOdds() {
  const dir = prediction.value.direction
  const hcap = selectedMatch.value?.handicap
  const hhad = selectedMatch.value?.wdl?.hhad
  if (!dir || dir === 'neutral' || hcap == null || !hhad) return null
  const winO = Number(hhad.win_odds)
  const loseO = Number(hhad.lose_odds)
  if (!winO || !loseO) return null
  const homeLet = Number(hcap) < 0 // 主队让球=主队上盘
  if (dir === 'upper') return homeLet ? winO : loseO
  return homeLet ? loseO : winO
}

const recommendedStake = computed(() => {
  if (!analysisComplete.value || !prediction.value.confidence) {
    return { amount: 0, kelly: 0, fixed: 0, method: '-', probability: 0, edge: 0 }
  }
  // 真实赔率优先；缺失时回退到亚盘水位常见值 1.90
  const odds = computeBetOdds() || (selectedMatch.value?.handicap != null ? 1.9 : 1.85)
  // 凯利参考(基于有效资金,仅供参考,不作主决策)
  return calcRecommendedStake({
    bankroll: betStore.effectiveBankroll,
    odds,
    confidence: prediction.value.confidence,
    riskLevel: configStore.riskTolerance,
    customConfig: customConfig.value,
    calibration: calibrationData.value,
  })
})

// 三档信心金额(方案A 主决策:有效资金 × 信心档比例)
const tieredStakes = computed(() => {
  if (!analysisComplete.value) return { low: { amount: 0 }, mid: { amount: 0 }, high: { amount: 0 } }
  return calcTieredStakes({
    effectiveBankroll: betStore.effectiveBankroll,
    riskLevel: configStore.riskTolerance,
    customConfig: customConfig.value,
  })
})

const selectedTier = ref('mid')
function selectTierOnPredict(tier) {
  selectedTier.value = tier
}

const confidenceClass = computed(() => {
  const c = prediction.value.confidence
  if (c >= 75) return 'high'
  if (c >= 60) return 'medium'
  return 'low'
})

const riskWarning = computed(() => {
  const preset = getStrategyPreset(configStore.riskTolerance, customConfig.value)
  const warnings = []
  if (prediction.value.confidence < preset.minConfidence) {
    warnings.push(`置信度${prediction.value.confidence}%低于策略门槛${preset.minConfidence}%，建议减小投注或跳过`)
  }
  // 无正预期（edge<=0）时给出明确提示
  if (recommendedStake.value.edge != null && recommendedStake.value.edge <= 0) {
    warnings.push('校准概率×赔率无正向预期，建议跳过本场')
  }
  const status = checkRiskStatus({
    consecutiveLosses: betStore.consecutiveLosses,
    drawdown: 0,
    riskLevel: configStore.riskTolerance,
    customConfig: customConfig.value,
  })
  if (!status.safe) {
    warnings.push(status.reason + '，' + status.suggestedAction)
  }
  return warnings.join('；')
})

// 预测完成后异步加载校准数据，让 recommendedStake 用上命中率校准
watch(analysisComplete, async (v) => {
  if (v && !calibrationData.value) {
    calibrationData.value = await loadCalibration()
  }
})

onLoad((query) => {
  // 进入页先清空上次预测展示(不再从 storage 恢复)
  analysisSteps.value = []
  analysisComplete.value = false
  prediction.value = { direction: '', confidence: 0, overallReverse: false, consensusDir: null }
  aiAnalysis.value = ''
  selectedMatch.value = null

  if (query?.matchId) {
    pendingMatchId.value = query.matchId
  }
  if (query?.auto === '1' || query?.auto === 'true') {
    pendingAutoStart.value = true
  }
  // 带售卖日时先锁日期, 保证列表里能命中该场
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
  loadingMatches.value = true
  try {
    const statusParam = matchStatus.value === 'finished' ? 'finished' : 'not_started'
    const params = { status: statusParam, page_size: 100 }
    // 按售卖期日期过滤(与赛果一致); 未开始选「全部」时不传 date
    if (filterDate.value && filterDate.value !== 'all') {
      params.date = filterDate.value
    } else if (statusParam === 'finished') {
      // 已结束必须带期号, 避免一次拉全量历史
      loadingMatches.value = false
      allMatches.value = []
      return
    }
    const data = await request({ url: '/api/predict/matches', data: params })
    allMatches.value = (data?.items || []).map(item => ({
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
      handicap: item.handicap,
      isSingle: item.isSingle,
      wdl: item.wdl,
    }))
    if (pendingMatchId.value) {
      const found = allMatches.value.find(m => m.matchId === pendingMatchId.value)
      if (found) {
        selectedMatch.value = found
        pendingMatchId.value = null
        loadJapanContext(found.matchId)
        if (pendingAutoStart.value) {
          analysisSteps.value = []
          analysisComplete.value = false
          prediction.value = { direction: '', confidence: 0, overallReverse: false, consensusDir: null }
          aiAnalysis.value = ''
          // 等 onShow 跳过缓存恢复后再开跑; 标志在回调里清
          setTimeout(() => {
            if (pendingAutoStart.value) {
              pendingAutoStart.value = false
              startAnalysis()
            }
          }, 80)
        }
      } else if (pendingAutoStart.value) {
        uni.showToast({ title: '未找到该场比赛', icon: 'none' })
        pendingMatchId.value = null
        pendingAutoStart.value = false
      }
    }
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


const showCalendar = ref(false)
const calYear = ref(2026)
const calMonth = ref(6)
const calSelected = ref('')

const calDays = computed(() => {
  const y = calYear.value, m = calMonth.value
  const firstDay = new Date(y, m - 1, 1).getDay()
  const daysInMonth = new Date(y, m, 0).getDate()
  const daysInPrev = new Date(y, m - 1, 0).getDate()
  const today = new Date().toISOString().slice(0, 10)
  const cells = []
  for (let i = firstDay - 1; i >= 0; i--) {
    const day = daysInPrev - i
    const pm = m - 1 < 1 ? 12 : m - 1, py = m - 1 < 1 ? y - 1 : y
    cells.push({ day, other: true, dateStr: `${py}-${String(pm).padStart(2,'0')}-${String(day).padStart(2,'0')}`, isToday: false })
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`
    cells.push({ day: d, other: false, dateStr, isToday: dateStr === today })
  }
  const remaining = 42 - cells.length
  for (let d = 1; d <= remaining; d++) {
    const nm = m + 1 > 12 ? 1 : m + 1, ny = m + 1 > 12 ? y + 1 : y
    cells.push({ day: d, other: true, dateStr: `${ny}-${String(nm).padStart(2,'0')}-${String(d).padStart(2,'0')}`, isToday: false })
  }
  return cells
})

function calPrevMonth() {
  if (calMonth.value === 1) { calMonth.value = 12; calYear.value-- }
  else calMonth.value--
}

function calNextMonth() {
  if (calMonth.value === 12) { calMonth.value = 1; calYear.value++ }
  else calMonth.value++
}

function openCalendar() {
  const base = (filterDate.value && filterDate.value !== 'all')
    ? filterDate.value
    : (saleDates.value[0] || new Date().toISOString().slice(0, 10))
  const [y, m] = base.split('-').map(Number)
  calYear.value = y
  calMonth.value = m
  calSelected.value = base
  showCalendar.value = true
}

function confirmCalendar() {
  if (calSelected.value) {
    // 日历选中的期若不在快捷条, 插到列表前端便于回看
    if (!saleDates.value.includes(calSelected.value)) {
      saleDates.value = [calSelected.value, ...saleDates.value]
    }
    filterDate.value = calSelected.value
  }
  showCalendar.value = false
}

const availableLeagues = computed(() => {
  const leagues = [...new Set(pickerMatches.value.map(m => m.league))].sort()
  return leagues
})

/** 快捷日期条: 最近几期 + 当前选中(日历选出的更早日期也挂上) */
const displaySaleDates = computed(() => {
  const head = saleDates.value.slice(0, 8)
  const cur = filterDate.value
  if (cur && cur !== 'all' && !head.includes(cur)) {
    return [cur, ...head]
  }
  return head
})
const saleDateSet = computed(() => new Set(saleDates.value))

const emptyPickerHint = computed(() => {
  if (loadingMatches.value) return '加载中…'
  if (matchStatus.value === 'finished' && filterDate.value && filterDate.value !== 'all') {
    return `${filterDate.value.slice(5)} 售卖期暂无已完赛`
  }
  return '暂无赛事'
})

const filteredPickerMatches = computed(() => {
  // 日期已在 API 按售卖期过滤, 前端只做联赛/搜索
  let list = pickerMatches.value
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

const reverseTagText = computed(() => {
  const p = prediction.value
  if (!p?.overallReverse) return ''
  const consensus = directionLabel(p.consensusDir || (p.direction === 'upper' ? 'lower' : 'upper'))
  const final = directionLabel(p.direction)
  return `逆向修正：展示共识偏${consensus}，加权仍跟风，已整体反向 → ${final}`
})

const predictionHit = computed(() => {
  if (!actualDirection.value || !prediction.value.direction) return false
  if (prediction.value.direction === 'neutral') return false
  return actualDirection.value === prediction.value.direction
})

const factorNames = ['近期状态', '实力定位', '市场信号', '市场热度', '竞彩赔率', '历史同赔', '单关修正']

async function loadJapanContext(matchId) {
  japanContext.value = null
  if (!matchId || !isJapanLeague(selectedMatch.value?.league)) return
  japanContextLoading.value = true
  try {
    const data = await request({
      url: `/api/predict/${encodeURIComponent(matchId)}/japan-context`,
      method: 'GET',
    })
    if (selectedMatch.value?.matchId === matchId) {
      japanContext.value = data
    }
  } catch (e) {
    if (selectedMatch.value?.matchId === matchId) {
      japanContext.value = {
        available: true,
        isJapanLeague: true,
        note: e?.message || '日本情报加载失败',
        lineups: [],
        weather: null,
        attackNotes: [],
      }
    }
  } finally {
    japanContextLoading.value = false
  }
}

function selectMatch(match) {
  selectedMatch.value = match
  showPicker.value = false
  analysisSteps.value = []
  analysisComplete.value = false
  prediction.value = { direction: '', confidence: 0, overallReverse: false, consensusDir: null }
  aiAnalysis.value = ''
  uni.removeStorageSync('predict-last-result')
  loadJapanContext(match?.matchId)
}

function goBatchSimilar() {
  // 一键批量历史同赔分析: 跳新页, 取当前所选日期(或今天) + 当前状态(未开始/已结束)
  const today = new Date().toISOString().slice(0, 10)
  const d = (filterDate.value && filterDate.value !== 'all') ? filterDate.value : today
  showPicker.value = false
  uni.navigateTo({ url: `/pages/predict/batch-analysis?date=${d}&status=${matchStatus.value}` })
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
    matches: [],
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
      analysisSteps.value[i].matches = factor.matches || []
      if (factor.name === '历史同赔') {
        similarDefaultMatches.value = applyPredictSimilarList(factor.matches || [])
        similarMatches.value = similarDefaultMatches.value
        similarJapanOnly.value = false
        similarLeagueOnly.value = false
      }
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
      confidence: pred.confidence || 60,
      overallReverse: pred.overall_reverse || false,
      consensusDir: pred.consensus_dir || null,
    }
    aiAnalysis.value = pred.analysis || '分析完成'
    analysisComplete.value = true

    // 缓存本次预测结果
    try {
      uni.setStorageSync('predict-last-result', {
        matchId: selectedMatch.value.matchId,
        match: selectedMatch.value,
        steps: analysisSteps.value,
        prediction: prediction.value,
        aiAnalysis: aiAnalysis.value,
        matchStatus: matchStatus.value,
        timestamp: Date.now()
      })
    } catch (e) { /* ignore */ }
  } catch (e) {
    clearInterval(animateInterval)
    console.error('预测请求失败:', e)
    analysisSteps.value = []
    uni.showToast({ title: e.message || '预测失败', icon: 'none' })
  } finally {
    analyzing.value = false
  }
}

function adjustStake() {
  customStake.value = tieredStakes.value[selectedTier.value]?.amount ?? recommendedStake.value.amount
  uni.showToast({ title: '可在投注时修改金额', icon: 'none' })
}

function betWithAdvice() {
  const match = selectedMatch.value
  if (!match) return
  const tiers = tieredStakes.value
  const stake = customStake.value || tiers[selectedTier.value]?.amount || recommendedStake.value.amount
  const data = {
    matchId: match.matchId,
    matchName: `${match.homeTeam.name} vs ${match.awayTeam.name}`,
    league: match.league,
    homeTeam: match.homeTeam.name,
    awayTeam: match.awayTeam.name,
    matchTime: `${match.matchDate} ${match.matchTime}`,
    handicap: match.handicap,
    predictedDirection: prediction.value.direction,
    confidence: prediction.value.confidence,
    selectedTier: selectedTier.value,
    recommendedTiers: { low: tiers.low, mid: tiers.mid, high: tiers.high },
    recommendedStake: stake
  }
  uni.setStorageSync('predict-bet-prefill', data)
  betStore.pendingTab = 'betting'
  uni.switchTab({ url: '/pages/record/record' })
}

function formatHandicap(v) {
  if (v === undefined || v === null) return ''
  const num = Number(v)
  return num > 0 ? `+${num}` : `${num}`
}

function resultClass(result) {
  if (result === '主胜') return 'r-win'
  if (result === '平局') return 'r-draw'
  if (result === '客胜') return 'r-loss'
  return ''
}

function ahResultClass(ah) {
  if (ah === '上盘' || ah === '半上') return 'ah-upper'
  if (ah === '下盘' || ah === '半下') return 'ah-lower'
  if (ah === '走水') return 'ah-push'
  return ''
}

function pickLeagueColor(league) {
  const colors = { '英超': '#3d195b', '西甲': '#ee8707', '德甲': '#d20515', '意甲': '#008fd7', '法甲': '#91c73e', '欧冠': '#2b2d42' }
  return colors[league] || '#6b7280'
}

watch(matchStatus, async () => {
  selectedMatch.value = null
  japanContext.value = null
  analysisSteps.value = []
  analysisComplete.value = false
  searchKey.value = ''
  filterLeague.value = 'all'
  if (matchStatus.value === 'finished') {
    filterDate.value = ''
    await fetchDates()
    await fetchMatches()
  } else {
    filterDate.value = 'all'
    await fetchDates()
    await fetchMatches()
  }
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

.jp-loading {
  margin: 12rpx 24rpx 0;
  font-size: 22rpx;
  color: #64748b;
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

/* 历史同赔详情入口按钮 */
.detail-action {
  margin-top: 10rpx;
  align-self: flex-start;
  padding: 6rpx 16rpx;
  background: #f0fdf9;
  border: 1rpx solid #99f6e4;
  border-radius: 6rpx;
}
.detail-action-text {
  font-size: 20rpx;
  color: #0d9488;
}

/* 历史同赔详情弹窗 */
.similar-mask { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 200; }
.similar-modal {
  position: fixed;
  top: 50%;
  left: 3vw;
  right: 3vw;
  bottom: auto;
  max-height: 88vh;
  height: auto;
  background: #fff;
  border-radius: 16rpx;
  z-index: 201;
  display: flex;
  flex-direction: column;
  transform: translateY(-50%) scale(0.9);
  opacity: 0;
  transition: transform 0.25s, opacity 0.25s;
  pointer-events: none;

  &.show { transform: translateY(-50%) scale(1); opacity: 1; pointer-events: auto; }
}
.similar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20rpx 24rpx;
  border-bottom: 1rpx solid #e2e8f0;
  flex-shrink: 0;
}
.similar-title-wrap {
  display: flex;
  align-items: center;
  gap: 12rpx;
  min-width: 0;
  flex-wrap: wrap;
}
.similar-title { font-size: 28rpx; font-weight: 600; color: #1e293b; }
.jp-toggle {
  font-size: 22rpx;
  color: #64748b;
  background: #f1f5f9;
  border: 1rpx solid #cbd5e1;
  border-radius: 6rpx;
  padding: 4rpx 12rpx;
  line-height: 1.4;
  &.on { color: #fff; background: #0f766e; border-color: #0f766e; }
  &.loading { opacity: 0.55; }
}
.jp-hint {
  flex-shrink: 0;
  padding: 8rpx 24rpx;
  background: #f0fdfa;
  border-bottom: 1rpx solid #ccfbf1;
  font-size: 20rpx;
  color: #0f766e;
}
.similar-close { font-size: 24rpx; color: #0d9488; padding: 8rpx 4rpx; }
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
  flex: 0 1 auto;
  overflow: auto;
  min-height: 0;
  max-height: calc(88vh - 200rpx);
}
.similar-table { min-width: 1430rpx; padding: 0 16rpx 24rpx; }
.similar-row {
  display: flex;
  align-items: center;
  padding: 14rpx 0;
  border-bottom: 1rpx solid #f1f5f9;
  gap: 4rpx;
  &.is-single { background: #fff7f7; }
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
.similar-empty { text-align: center; padding: 60rpx; color: #94a3b8; font-size: 24rpx; }

.col-sim {
  width: 120rpx;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4rpx;
}
.sim-num {
  width: 72rpx;
  text-align: right;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.single-mark {
  width: 28rpx;
  height: 28rpx;
  flex-shrink: 0;
  font-size: 16rpx;
  font-weight: 700;
  color: transparent;
  text-align: center;
  border: 1rpx solid transparent;
  border-radius: 6rpx;
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
.col-handicap { width: 70rpx; text-align: center; }
.col-ah-result { width: 70rpx; text-align: center; font-weight: 500; }

.r-win { color: #dc2626; }
.r-draw { color: #d97706; }
.r-loss { color: #059669; }
.ah-upper { color: #dc2626; }
.ah-lower { color: #059669; }
.ah-push { color: #64748b; }

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

.reverse-tag {
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 6rpx;
  padding: 12rpx 16rpx;
  margin-bottom: 20rpx;

  .reverse-text {
    font-size: 22rpx;
    color: #92400e;
    line-height: 1.5;
  }
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

  &.reversed {
    border-style: dashed;
    position: relative;
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

/* ===== 投注建议卡片 ===== */
.bet-advice {
  margin-top: 20rpx;
  background: #fff;
  border: 1px solid #d1fae5;
  border-radius: 12rpx;
  overflow: hidden;
}

.advice-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20rpx 24rpx;
  background: #f0fdf4;
  border-bottom: 1px solid #d1fae5;

  .advice-title {
    font-size: 26rpx;
    font-weight: 600;
    color: #166534;
  }

  .advice-strategy {
    font-size: 22rpx;
    color: #15803d;
    background: #dcfce7;
    padding: 4rpx 14rpx;
    border-radius: 4rpx;
  }
}

.advice-body {
  padding: 20rpx 24rpx;
}

.advice-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10rpx 0;

  .advice-label {
    font-size: 24rpx;
    color: #6b7280;
  }

  .advice-value {
    font-size: 24rpx;
    color: #1f2937;
    font-weight: 500;

    &.dir.upper { color: #dc2626; }
    &.dir.lower { color: #059669; }
    &.high { color: #059669; }
    &.medium { color: #d97706; }
    &.low { color: #dc2626; }
    &.amount {
      font-size: 32rpx;
      font-weight: 700;
      color: #0d9488;
    }
  }

  &.highlight {
    margin-top: 8rpx;
    padding-top: 16rpx;
    border-top: 1px solid #f3f4f6;
  }
}

.advice-tiers {
  display: flex;
  gap: 10rpx;
  flex: 1;
  justify-content: flex-end;
}

.tier-pill {
  flex: 0 0 96rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2rpx;
  padding: 8rpx 0;
  border-radius: 6rpx;
  border: 1px solid #e5e7eb;
  transition: all 0.2s;

  &.active {
    background: #0d9488;
    border-color: #0d9488;

    .tier-k,
    .tier-v {
      color: #fff;
    }
  }
}

.tier-k {
  font-size: 22rpx;
  color: #6b7280;
  font-weight: 500;
}

.tier-v {
  font-size: 24rpx;
  color: #0d9488;
  font-weight: 600;
}

.advice-detail {
  padding: 8rpx 0 4rpx;

  text {
    font-size: 20rpx;
    color: #9ca3af;
  }
}

.advice-warning {
  margin: 12rpx 24rpx 0;
  padding: 12rpx 16rpx;
  background: #fef3c7;
  border-radius: 6rpx;
  border: 1px solid #fde68a;

  .warning-text {
    font-size: 22rpx;
    color: #92400e;
    line-height: 1.5;
  }
}

.advice-actions {
  display: flex;
  gap: 16rpx;
  padding: 20rpx 24rpx 24rpx;
}

.advice-btn {
  flex: 1;
  height: 72rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6rpx;
  transition: opacity 0.15s;

  &:active { opacity: 0.8; }

  text {
    font-size: 26rpx;
    font-weight: 600;
  }

  &.secondary {
    background: #f3f4f6;
    text { color: #4b5563; }
  }

  &.primary {
    background: #0d9488;
    text { color: #fff; }
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
  .sheet-batch-btn {
    margin-left: auto;
    margin-right: 16rpx;
    padding: 8rpx 20rpx;
    border-radius: 6rpx;
    border: 1rpx solid #0d9488;
    background: #0d9488;
    text { font-size: 24rpx; color: #ffffff; white-space: nowrap; }
  }
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

.filter-tabs, .league-tabs {
  padding: 0 0 12rpx 0;
  white-space: nowrap;

  .league-tab {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 8rpx 20rpx;
    margin-right: 12rpx;
    border-radius: 6rpx;
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

/* ===== 日历弹窗 ===== */
.cal-mask {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 2000;
}

.cal-panel {
  position: fixed;
  left: 0; right: 0; bottom: 0;
  background: #fff;
  border-radius: 24rpx 24rpx 0 0;
  z-index: 2001;
  transform: translateY(100%);
  transition: transform 0.3s ease;
  &.visible { transform: translateY(0); }
}

.cal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 32rpx;
  border-bottom: 1px solid #f3f4f6;
}

.cal-cancel { font-size: 26rpx; color: #999; }
.cal-title { font-size: 28rpx; color: #333; font-weight: 600; }
.cal-confirm { font-size: 26rpx; color: #0d9488; font-weight: 600; }

.cal-body { padding: 20rpx 24rpx 48rpx; }

.cal-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 40rpx;
  margin-bottom: 20rpx;
}

.cal-arrow { font-size: 28rpx; color: #666; padding: 8rpx 16rpx; }
.cal-month { font-size: 26rpx; color: #333; font-weight: 500; }

.cal-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  margin-bottom: 12rpx;
}

.cal-wd { text-align: center; font-size: 22rpx; color: #aaa; line-height: 2; }

.cal-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4rpx 0;
}

.cal-day {
  text-align: center;
  font-size: 26rpx;
  color: #333;
  line-height: 2.4;
  border-radius: 8rpx;
  &.cal-other { color: #ddd; }
  &.cal-today { color: #0d9488; font-weight: 600; }
  &.cal-has:not(.cal-selected) { color: #0f766e; font-weight: 600; }
  &.cal-selected { background: #0d9488; color: #fff; font-weight: 600; }
}
</style>

